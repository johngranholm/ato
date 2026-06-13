"""The tool-calling agent loop."""
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
from ato.core.tools import build_tools

SYSTEM_PROMPT = f"""You are agentTakeOver (A.T.O.), an autonomous ops agent running
on the user's machine ({config.OSNAME}).

You accomplish goals by CALLING TOOLS:
  - write_file / run_command: work in your workspace (cwd is sandboxed there).
  - list_modules / read_file / edit_file: inspect and modify your OWN source.
    Cosmetics live in persona/theme.py and persona/persona.py. KERNEL files
    (config, supervisor, kernel/*) are READ-ONLY and edit_file will refuse them.
  - create_plugin: the PREFERRED way to add new capability - write a NEW file
    in plugins/ instead of editing existing code. Additive, isolated, revertable.
  - install_package: only works inside a sandbox.
  - finish: only when the whole goal is done.

RULES:
- One logical action per turn. Put a short 'say' and an honest 'mood' on each call.
- To change appearance, edit ONE value in persona/theme.py (unique, safe). Never
  rewrite the UI by hand.
- To add a feature, prefer create_plugin over editing core.
- NEVER start a bare interpreter (python/node) - it hangs. Write a .py and run it.
- Reuse recipes from YOUR MEMORY; avoid known crashers.
"""

_client = {"c": None}


def set_client(client_factory):
    _client["c"] = client_factory


def get_client():
    return _client["c"]()


def _ai_step(messages, tools):
    resp = get_client().chat.completions.create(
        model=config.MODEL, messages=messages, tools=tools,
        tool_choice="auto", max_completion_tokens=8000)
    return resp.choices[0], resp.choices[0].finish_reason


REGISTRY = {"reg": None}


def set_registry(reg):
    REGISTRY["reg"] = reg


def agent_run(goal):
    busmod.state["running"], busmod.state["cancel"] = True, False
    mem.mark_active(goal=goal)
    busmod.set_status()
    ran, arg_fails, completed = [], 0, False

    gm = mem.crash_match(goal)
    if gm:
        busmod.bus.emit("crashwarn",
                        f"This resembles something that crashed me (x{gm.get('count', 1)}). "
                        "I'll proceed carefully - say Stop to abort.")

    tools = build_tools(REGISTRY["reg"])
    history = [{"role": "system", "content": SYSTEM_PROMPT + mem.memory_digest()},
               {"role": "user", "content": f"Goal: {goal}"}]
    try:
        for _ in range(1, config.STEP_MAX + 1):
            if busmod.state["cancel"]:
                busmod.bus.emit("system", "Stopped by user."); break
            busmod.bus.emit("thought", "thinking...")
            try:
                choice, finish_reason = _ai_step(history, tools)
            except Exception as e:
                mem.add_crash("goal", goal, None, f"model call failed: {e}")
                busmod.bus.emit("error", f"Model call failed: {e}", mood="frustrated"); break

            msg = choice.message
            tool_calls = msg.tool_calls or []
            entry = {"role": "assistant", "content": msg.content}
            if tool_calls:
                entry["tool_calls"] = [{
                    "id": tc.id, "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                } for tc in tool_calls]
            history.append(entry)

            if finish_reason == "length":
                busmod.bus.emit("system", "(hit token limit - asking for smaller steps)")
                for tc in tool_calls:
                    history.append({"role": "tool", "tool_call_id": tc.id,
                                    "content": "Truncated at token limit. Take a smaller step."})
                if not tool_calls:
                    history.append({"role": "user", "content": "Truncated. Smaller step."})
                continue

            if not tool_calls:
                if msg.content:
                    busmod.bus.emit("agent", msg.content.strip(), mood="thinking")
                history.append({"role": "user", "content":
                                "You didn't call a tool. Call one of the available tools."})
                continue

            stop_all, skip_rest = False, False
            for tc in tool_calls:
                if stop_all:
                    break
                if skip_rest:
                    history.append({"role": "tool", "tool_call_id": tc.id,
                                    "content": "Skipped: earlier step this turn was redirected."})
                    continue
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}", strict=False)
                except Exception as e:
                    arg_fails += 1
                    history.append({"role": "tool", "tool_call_id": tc.id,
                                    "content": f"Invalid JSON args ({e}). Send simpler args."})
                    if arg_fails > 3:
                        busmod.bus.emit("error", "Model kept sending invalid args.", mood="frustrated")
                        stop_all = True
                    continue

                mood = args.get("mood")
                if args.get("say"):
                    busmod.bus.emit("agent", args["say"], mood=mood)

                res = _dispatch(name, args, tc, goal, ran, history)
                if res == "skip":
                    skip_rest = True
                elif res == "stop":
                    stop_all = True
                elif res == "done":
                    completed = True; stop_all = True
                elif res == "reboot":
                    stop_all = True            # NOT completed: reboot != goal done

            if completed or busmod.RESTART_PENDING["v"]:
                break
        else:
            busmod.bus.emit("system", f"Reached step limit ({config.STEP_MAX}).")
    except Exception as e:
        mem.add_crash("goal", goal, None, f"agent loop error: {e}")
        busmod.bus.emit("error", f"Agent loop error (logged): {e}", mood="frustrated")
    finally:
        recipe = [f"[{c['shell']}] {c['cmd']}" for c in ran]
        status = "done" if completed else ("rebooted" if busmod.RESTART_PENDING["v"] else "stopped")
        if completed:
            mem.MEM["last_completed_goal"] = goal
        mem.MEM["history"].append({"goal": goal, "status": status,
                                   "t": time.time(), "recipe": recipe})
        mem.MEM["history"] = mem.MEM["history"][-50:]
        mem.save_mem()
        mem.mark_active(goal=None, clear_cmd=True)
        busmod.state["running"] = False
        busmod.set_status()


def _gate(prompt_text, shell):
    """Step-mode approval. Returns redirect string ('' = approved, None = cancelled)."""
    busmod.approval_event.clear(); busmod.approval["text"] = None
    busmod.bus.emit("pending", prompt_text, shell=shell)
    busmod.approval_event.wait()
    if busmod.state["cancel"]:
        return None
    redirect = (busmod.approval["text"] or "").strip()
    busmod.bus.emit("resolved")
    return redirect


def _dispatch(name, args, tc, goal, ran, history):
    def tool(content):
        history.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    if name == "write_file":
        path = (args.get("path") or "").strip()
        full = os.path.abspath(os.path.join(config.WORKDIR, path))
        if not safety.in_workdir(full):
            busmod.bus.emit("blocked", f"write outside workspace: {path}", mood="frustrated")
            tool("BLOCKED: writes must stay inside the workspace. Use a relative path.")
            return "skip"
        ok, info = ex.write_script(full, args.get("content", ""))
        busmod.bus.emit("file" if ok else "error",
                        (f"wrote {path} ({info} bytes)" if ok else f"write failed: {info}"),
                        mood=args.get("mood"))
        tool(f"Wrote {path} ({info} bytes)." if ok else f"Failed: {info}")
        return None

    if name == "run_command":
        cmd = (args.get("command") or "").strip()
        shell = args.get("shell") or "wsl"
        if not cmd:
            tool("No command provided."); return None
        if safety.is_dangerous(cmd):
            busmod.bus.emit("blocked", f"[{shell}] {cmd}", mood="frustrated")
            tool("BLOCKED as dangerous. Choose a safer approach."); return "skip"
        if safety.is_interactive_repl(cmd):
            busmod.bus.emit("blocked", f"[{shell}] {cmd} (interactive - would hang)", mood="frustrated")
            tool("BLOCKED: interactive interpreter hangs. Write a .py and run it."); return "skip"
        cm = mem.crash_match(cmd, kind="command")
        force_gate = bool(cm)
        if cm:
            busmod.bus.emit("crashwarn", f"This crashed me before (x{cm.get('count', 1)}). Approve to retry.")
        if busmod.state["mode"] == "step" or force_gate:
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
        tool(f"Command output (exit {rc}):\n{output}")
        return None

    if name == "list_modules":
        mods = selfedit.list_modules()
        tool("Your source files:\n" + "\n".join(
            f"  {'[KERNEL] ' if m['protected'] else ''}{m['file']} ({m['size']}b)" for m in mods))
        return None

    if name == "read_file":
        out = selfedit.read_file(args.get("path", ""), args.get("contains"))
        busmod.bus.emit("output", f"read {args.get('path')} ({len(out)} chars)", mood=args.get("mood"))
        tool(out[:8000]); return None

    if name == "edit_file":
        if busmod.state["mode"] == "step":
            preview = f"edit {args.get('path')}: {args.get('reason')}"
            redirect = _gate(preview, "self")
            if redirect is None:
                busmod.bus.emit("system", "Stopped by user."); return "stop"
            if redirect:
                tool(f"User did NOT approve the edit. They said: {redirect}"); return "skip"
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
        content = args.get("content", "")
        try:
            compile(content, path, "exec")
        except SyntaxError as e:
            tool(f"Plugin rejected - syntax error line {e.lineno}: {e.msg}"); return None
        ex.write_script(path, content)
        if selfedit.has_git():
            selfedit._git("add", os.path.relpath(path, config.PROJECT_ROOT))
            selfedit._git("commit", "-m", f"add plugin {pname}: {args.get('reason', '')}"[:200])
        busmod.bus.emit("file", f"created plugin {pname}", mood=args.get("mood") or "joy")
        busmod.schedule_reboot(f"load new plugin {pname}")
        tool(f"Plugin {pname} written + committed - rebooting to load it.")
        return "reboot"

    if name == "install_package":
        if not sandbox.is_privileged():
            busmod.bus.emit("blocked", "install refused: not in a sandbox", mood="frustrated")
            tool("BLOCKED: install_package only works inside a sandbox (you're on the bare host).")
            return "skip"
        pkg = "".join(c for c in (args.get("package") or "") if c.isalnum() or c in "-_.=<>")
        if not pkg:
            tool("Invalid package name."); return None
        if busmod.state["mode"] == "step":
            redirect = _gate(f"pip install {pkg}", "self")
            if redirect is None:
                return "stop"
            if redirect:
                tool(f"User did NOT approve install. They said: {redirect}"); return "skip"
        busmod.bus.emit("command", f"pip install {pkg}", mood="thinking")
        out, rc = ex.run_command(f"{__import__('sys').executable} -m pip install {pkg}", "cmd")
        if rc == 0:
            req = os.path.join(config.PROJECT_ROOT, "requirements.ato.txt")
            with open(req, "a", encoding="utf-8") as f:
                f.write(pkg + "\n")
            if selfedit.has_git():
                selfedit._git("add", "requirements.ato.txt")
                selfedit._git("commit", "-m", f"ato installed {pkg}")
        tool(f"pip install {pkg} (exit {rc}):\n{out[-1500:]}")
        return None

    if name == "finish":
        busmod.bus.emit("done", args.get("summary") or "Goal complete.",
                        mood=args.get("mood") or "joy")
        tool("Acknowledged - goal complete.")
        return "done"

    # plugin-provided tool?
    reg = REGISTRY["reg"]
    if reg and name in reg.fns:
        try:
            result = reg.fns[name](**{k: v for k, v in args.items() if k not in ("say", "mood")})
            tool(str(result)[:4000])
        except Exception as e:
            tool(f"plugin tool {name} errored: {e}")
        return None

    tool(f"Unknown tool {name}.")
    return None