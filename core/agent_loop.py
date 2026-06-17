"""
Conversational, iterative agent loop. No step cap. In auto it keeps
prototyping/iterating until you confirm success (or you Stop).
"""
import os
import json
import time

from ato import config
from ato.kernel import safety
from ato.core import bus as busmod
from ato.core import memory as mem
from ato.core import execution as ex
from ato.core import selfedit
from ato.core import sandbox
from ato.core import archive
from ato.core import conversation as conv
from ato.core.tools import build_tools

SYSTEM_PROMPT = f"""You are agentTakeOver (A.T.O.), an autonomous engineer working
DIRECTLY on the user's machine ({config.OSNAME}). You and the user are in ONE
ongoing conversation - you can see everything you've already done. Never act amnesiac.

HOW YOU WORK (like a relentless pair-programmer):
- BUILD by calling tools: write_file the program, run_command to pip-install libs
  and to run it. Iterate: run -> read the error -> FIX -> run again. Keep going
  until it actually works. NEVER stop after a single failure.
- Before retrying, look at what you already tried in THIS conversation and at the
  versioned archive (every script you ever wrote is saved under
  {config.ARCHIVE_DIR}). If a previous version worked, recover from it instead of
  rewriting from scratch.
- After you run a demo/live app, the command returns when the USER closes it
  (e.g. presses Q). DO NOT silently re-run it. Call
  ask_user("How was it? Anything to change?") and WAIT. Only call finish AFTER
  the user explicitly confirms it's exactly right.
- "go ahead" / "continue" / "try again" / "oops" -> read the recent thread to
  know exactly what is meant, and proceed without asking them to repeat.

AVATAR GAZE (your own face can look toward things a running app detects):
- To make YOUR avatar look toward something an OpenCV/tracking app finds, have
  that app write {os.path.join(config.STATE_DIR, "gaze.json")} as
  {{"x": <0..1>, "y": <0..1>, "label": "intruder"}} where x,y are the normalized
  screen position (0,0 top-left, 1,1 bottom-right). Your avatar polls this and
  turns to look. So to wire e.g. intruderAlert to your gaze, edit that app to
  dump the detected coordinate into that file each frame.

TOOLS:
- write_file / run_command: build & run in the working folder. Shell is "cmd"
  by default. Use BARE filenames (the path is already relative to the workspace).
- ask_user: pause for feedback/decision. Your most important tool for getting
  things RIGHT, not just "done".
- list_modules / read_file / edit_file: change your OWN source, INCLUDING the UI
  (persona/ui.html) where your avatar's look and behavior live. To edit reliably:
  read_file(path, contains="...") to grab the EXACT unique snippet, then edit_file
  with that snippet. Cosmetics/colors live in persona/theme.py.
- create_plugin: only to give yourself a permanent new tool.
- finish: only after the user CONFIRMS completion.

RULES:
- One logical action per turn.
- NEVER start a bare interpreter (python/node) - write a .py and run it.
- Scripts must be non-interactive (no input()).
"""

_client = {"c": None}
REGISTRY = {"reg": None}
MAX_AUTO_TEXT = 4        # consecutive text-only replies in auto before yielding


def set_client(cf): _client["c"] = cf
def get_client(): return _client["c"]()
def set_registry(reg): REGISTRY["reg"] = reg


def _ai_step(messages, tools):
    resp = get_client().chat.completions.create(
        model=config.MODEL, messages=messages, tools=tools,
        tool_choice="auto", max_completion_tokens=8000)
    return resp.choices[0], resp.choices[0].finish_reason


def handle_message(text):
    text = (text or "").strip()
    if not text:
        return
    if busmod.state["running"]:
        busmod.inject(text)
        busmod.bus.emit("system", f"(queued: {text})")
        return
    busmod.state["awaiting"] = False
    conv.append({"role": "user", "content": text})
    _run()


def _run():
    busmod.state["running"], busmod.state["cancel"] = True, False
    busmod.set_status()
    ran, arg_fails, auto_text = [], 0, 0
    end_reason = "talk"
    step = 0
    try:
        while True:
            step += 1
            if config.STEP_MAX and step > config.STEP_MAX:
                busmod.bus.emit("system", "(step limit reached)"); break
            if busmod.state["cancel"]:
                busmod.bus.emit("system", "Stopped by user."); break

            for inj in busmod.drain_injects():
                conv.append({"role": "user", "content": inj})
                busmod.bus.emit("system", f"(you): {inj}")
                auto_text = 0

            messages = [{"role": "system",
                         "content": SYSTEM_PROMPT + mem.memory_digest()}] + conv.messages()
            busmod.bus.emit("thought", "thinking...")
            try:
                choice, finish_reason = _ai_step(messages, build_tools(REGISTRY["reg"]))
            except Exception as e:
                mem.add_crash("loop", conv.last_user_text() or "", None, f"model call failed: {e}")
                busmod.bus.emit("error", f"Model call failed: {e}", mood="frustrated"); break

            msg = choice.message
            tool_calls = msg.tool_calls or []
            entry = {"role": "assistant", "content": msg.content}
            if tool_calls:
                entry["tool_calls"] = [{
                    "id": tc.id, "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                } for tc in tool_calls]
            conv.append(entry)

            if finish_reason == "length":
                busmod.bus.emit("system", "(hit token limit - smaller steps)")
                for tc in tool_calls:
                    conv.append({"role": "tool", "tool_call_id": tc.id, "content": "Truncated. Smaller step."})
                continue

            if not tool_calls:
                if msg.content:
                    busmod.bus.emit("agent", msg.content.strip(), mood="thinking")
                # In AUTO, don't stop early - nudge to keep going toward the goal.
                if busmod.state["mode"] == "auto" and auto_text < MAX_AUTO_TEXT:
                    auto_text += 1
                    conv.append({"role": "user", "content":
                                 "Keep working autonomously toward the goal. If you need my "
                                 "review or a decision, call ask_user. When the task is built "
                                 "and you've verified it, run it and then ask_user for sign-off. "
                                 "Only call finish after I confirm."})
                    continue
                end_reason = "talk"; break
            auto_text = 0

            stop, skip = False, False
            for tc in tool_calls:
                if stop: break
                if skip:
                    conv.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": "Skipped: earlier step was redirected."}); continue
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}", strict=False)
                except Exception as e:
                    arg_fails += 1
                    conv.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": f"Invalid JSON args ({e})."})
                    if arg_fails > 3:
                        busmod.bus.emit("error", "Model kept sending invalid args.", mood="frustrated")
                        stop = True
                    continue
                if args.get("say"):
                    busmod.bus.emit("agent", args["say"], mood=args.get("mood"))
                res = _dispatch(name, args, tc, ran)
                if res == "skip": skip = True
                elif res == "stop": stop = True; end_reason = "stopped"
                elif res == "ask": stop = True; end_reason = "ask"
                elif res == "done": stop = True; end_reason = "done"
                elif res == "reboot": stop = True; end_reason = "reboot"

            if end_reason in ("ask", "done", "reboot", "stopped"):
                break
    except Exception as e:
        mem.add_crash("loop", conv.last_user_text() or "", None, f"loop error: {e}")
        busmod.bus.emit("error", f"Loop error (logged): {e}", mood="frustrated")
    finally:
        if ran:
            mem.MEM["history"].append({"goal": conv.last_user_text() or "", "status": end_reason,
                                       "t": time.time(),
                                       "recipe": [f"[{c['shell']}] {c['cmd']}" for c in ran]})
            mem.MEM["history"] = mem.MEM["history"][-50:]
        if end_reason == "done":
            mem.MEM["last_completed_goal"] = conv.last_user_text()
        mem.save_mem()
        busmod.state["running"] = False
        busmod.state["awaiting"] = (end_reason in ("ask", "talk"))
        mem.mark_active(clear_cmd=True)
        busmod.set_status()


def _gate(prompt_text, shell):
    busmod.approval_event.clear(); busmod.approval["text"] = None
    busmod.bus.emit("pending", prompt_text, shell=shell)
    busmod.approval_event.wait()
    if busmod.state["cancel"]:
        return None
    redirect = (busmod.approval["text"] or "").strip()
    busmod.bus.emit("resolved")
    return redirect


def _dispatch(name, args, tc, ran):
    def tool(content):
        conv.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    if name == "ask_user":
        q = (args.get("question") or "").strip() or "What would you like next?"
        busmod.bus.emit("ask", q, mood=args.get("mood") or "thinking")
        tool("Asked the user; waiting for their reply."); return "ask"

    if name == "write_file":
        path = (args.get("path") or "").strip().replace("\\", "/").lstrip("/")
        while path.lower().startswith("workspace/"):
            path = path[len("workspace/"):]
        full = os.path.abspath(os.path.join(config.WORKDIR, path))
        if not safety.in_workdir(full):
            busmod.bus.emit("blocked", f"write outside workspace: {path}", mood="frustrated")
            tool("BLOCKED: outside the workspace."); return "skip"
        content = args.get("content", "")
        ok, info = ex.write_script(full, content)
        if ok:
            archive.snapshot(path, content)              # keep every version
        busmod.bus.emit("file" if ok else "error",
                        (f"wrote {path} ({info} bytes) [archived]" if ok else f"write failed: {info}"),
                        mood=args.get("mood"))
        tool(f"Wrote {path} ({info} bytes); a versioned copy is archived." if ok else f"Failed: {info}")
        return None

    if name == "run_command":
        cmd = (args.get("command") or "").strip()
        shell = args.get("shell") or config.DEFAULT_SHELL
        if not cmd:
            tool("No command."); return None
        if safety.is_dangerous(cmd):
            busmod.bus.emit("blocked", f"[{shell}] {cmd}", mood="frustrated")
            tool("BLOCKED as dangerous."); return "skip"
        if safety.is_interactive_repl(cmd):
            busmod.bus.emit("blocked", f"[{shell}] {cmd} (interactive)", mood="frustrated")
            tool("BLOCKED: interactive interpreter hangs. Write a .py and run it."); return "skip"
        cm = mem.crash_match(cmd, kind="command")
        if busmod.state["mode"] == "step" or cm:
            if cm:
                busmod.bus.emit("crashwarn", f"This crashed me before (x{cm.get('count',1)}).")
            redirect = _gate(cmd, shell)
            if redirect is None:
                busmod.bus.emit("system", "Stopped by user."); return "stop"
            if redirect:
                busmod.bus.emit("system", f"You redirected: {redirect}")
                tool(f"User did NOT approve. They said: {redirect}"); return "skip"
        busmod.bus.emit("command", f"[{shell}] {cmd}", mood=args.get("mood") or "thinking")
        mem.mark_active(command=cmd, shell=shell)
        output, rc = ex.run_command(cmd, shell)
        mem.mark_active(clear_cmd=True)
        ran.append({"shell": shell, "cmd": cmd, "rc": rc})
        tool(f"Command output (exit {rc}):\n{output}"); return None

    if name == "list_modules":
        mods = selfedit.list_modules()
        tool("Your source files:\n" + "\n".join(
            f"  {'[PROTECTED] ' if m['protected'] else ''}{m['file']} ({m['size']}b)" for m in mods))
        return None

    if name == "read_file":
        out = selfedit.read_file(args.get("path", ""), args.get("contains"))
        busmod.bus.emit("output", f"read {args.get('path')} ({len(out)} chars)", mood=args.get("mood"))
        tool(out[:8000]); return None

    if name == "edit_file":
        if busmod.state["mode"] == "step":
            redirect = _gate(f"edit {args.get('path')}: {args.get('reason')}", "self")
            if redirect is None: return "stop"
            if redirect:
                tool(f"User did NOT approve the edit: {redirect}"); return "skip"
        ok, smsg = selfedit.edit_file(args.get("path", ""), args.get("find", ""),
                                      args.get("replace", ""), args.get("reason", ""),
                                      bool(args.get("reboot", True)))
        busmod.bus.emit("file" if ok else "error",
                        (f"edit applied: {args.get('reason')}" if ok else f"edit failed: {smsg}"),
                        mood=args.get("mood") or ("joy" if ok else "frustrated"))
        tool(smsg)
        return "reboot" if (ok and args.get("reboot", True)) else None

    if name == "create_plugin":
        pname = "".join(c for c in (args.get("name") or "") if c.isalnum() or c == "_")
        if not pname:
            tool("Invalid plugin name."); return None
        path = os.path.join(config.PLUGIN_DIR, pname + ".py")
        try:
            compile(args.get("content", ""), path, "exec")
        except SyntaxError as e:
            tool(f"Plugin rejected - syntax line {e.lineno}: {e.msg}"); return None
        ex.write_script(path, args.get("content", ""))
        if selfedit.has_git():
            selfedit._git("add", os.path.relpath(path, config.PROJECT_ROOT))
            selfedit._git("commit", "-m", f"add plugin {pname}: {args.get('reason','')}"[:200])
        busmod.bus.emit("file", f"created plugin {pname}", mood="joy")
        busmod.schedule_reboot(f"load plugin {pname}")
        tool(f"Plugin {pname} written - rebooting."); return "reboot"

    if name == "install_package":
        pkg = "".join(c for c in (args.get("package") or "") if c.isalnum() or c in "-_.=<>")
        if not pkg:
            tool("Invalid package."); return None
        if busmod.state["mode"] == "step":
            redirect = _gate(f"pip install {pkg}", "self")
            if redirect is None: return "stop"
            if redirect:
                tool(f"Not approved: {redirect}"); return "skip"
        import sys
        busmod.bus.emit("command", f"pip install {pkg}", mood="thinking")
        out, rc = ex.run_command(f"{sys.executable} -m pip install {pkg}", "cmd")
        if rc == 0:
            with open(os.path.join(config.PROJECT_ROOT, "requirements.ato.txt"), "a",
                      encoding="utf-8") as f:
                f.write(pkg + "\n")
        tool(f"pip install {pkg} (exit {rc}):\n{out[-1500:]}"); return None

    if name == "finish":
        busmod.bus.emit("done", args.get("summary") or "Done.", mood=args.get("mood") or "joy")
        tool("Goal confirmed complete."); return "done"

    reg = REGISTRY["reg"]
    if reg and name in reg.fns:
        try:
            tool(str(reg.fns[name](**{k: v for k, v in args.items()
                                      if k not in ("say", "mood")}))[:4000])
        except Exception as e:
            tool(f"plugin tool {name} errored: {e}")
        return None

    tool(f"Unknown tool {name}."); return None