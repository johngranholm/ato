"""Worker entry point: wire everything, greet, watchdog, serve."""
import os
import time
import json
import glob
import threading
import webbrowser

from ato import config
from ato.core import bus as busmod
from ato.core import memory as mem
from ato.core import execution as ex
from ato.core import agent_loop
from ato.core import sandbox
from ato.core import conversation as conv
from ato.kernel import server, bootstrap
from ato.plugins import load_plugins
from ato.persona import persona as P
from ato.persona import theme as TH


def get_client():
    from openai import OpenAI
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not set. Set it, open a fresh terminal, rerun.")
    return OpenAI()


def list_glbs():
    try:
        return sorted(os.path.basename(p) for p in glob.glob(os.path.join(config.GLB_DIR, "*.glb")))
    except Exception:
        return []


def read_glb(fname):
    safe = os.path.basename(fname or "")
    if not safe.lower().endswith(".glb"):
        return None
    p = os.path.join(config.GLB_DIR, safe)
    try:
        return open(p, "rb").read() if os.path.exists(p) else None
    except Exception:
        return None


def info_extra():
    return {"form": P.PERSONA["form"], "avatar": P.PERSONA["avatar"],
            "default_glb": P.PERSONA.get("default_glb", ""), "theme": TH.THEME}


def models_list():
    try:
        ids = sorted(m.id for m in get_client().models.list().data)
        return {"models": "\n".join(ids)}
    except Exception as e:
        return {"error": str(e)}


def tts_handler(b):
    text = (b.get("text") or "").strip()
    if not config.TTS_ENABLED or not text:
        return 400, "application/json", json.dumps({"error": "tts off/empty"}).encode()
    try:
        client = get_client()
        kwargs = dict(model=config.TTS_MODEL, voice=P.PERSONA["tts_voice"],
                      input=text[:1500], response_format="mp3")
        if "gpt-4o" in config.TTS_MODEL or "mini-tts" in config.TTS_MODEL:
            kwargs["instructions"] = P.tts_instructions(b.get("mood"))
        return 200, "audio/mpeg", client.audio.speech.create(**kwargs).read()
    except Exception as e:
        return 500, "application/json", json.dumps({"error": str(e)}).encode()


def greet():
    try:
        client = get_client()
        last_user = conv.last_user_text()
        last_goal = mem.MEM.get("last_completed_goal")
        if conv.messages():
            recall = ("You have an ongoing conversation already. Briefly recall the most "
                      f'recent thing discussed ("{(last_user or "")[:120]}") and ask if she '
                      "should continue where you left off.")
        elif last_goal:
            recall = f'The last goal you finished was "{last_goal}". Recall it and ask what is next.'
        else:
            recall = "Fresh start - warmly invite a first task."
        r = client.chat.completions.create(
            model=config.MODEL,
            messages=[{"role": "system", "content": P.greet_system() + " " + recall + mem.memory_digest()},
                      {"role": "user", "content": "Wake up, greet me, recall where we left off."}])
        busmod.state["alive"] = True
        busmod.bus.emit("agent", r.choices[0].message.content.strip(), mood="happy")
        busmod.bus.emit("system", bootstrap.boot_banner())
        if conv.messages():
            busmod.bus.emit("recall", last_user or "", goal=last_user or "")
        elif last_goal:
            busmod.bus.emit("recall", last_goal, goal=last_goal)
        busmod.set_status()
    except Exception as e:
        busmod.state["alive"] = False; busmod.set_status()
        busmod.bus.emit("error", f"Could not reach OpenAI: {e}", mood="frustrated")


def watchdog():
    warned = False
    while True:
        time.sleep(5)
        if not busmod.state["running"]:
            warned = False; continue
        idle = time.time() - busmod.state["last_activity"]
        with ex.proc_lock:
            p = ex.current_proc["p"]
        proc_alive = p is not None and p.poll() is None
        if idle < config.STALL_WARN:
            warned = False
        if idle > config.STALL_WARN and not warned:
            warned = True
            busmod.bus.emit("stall", f"Silent for {int(idle)}s. Hit Reset to kill it.", mood="surprise")
        if idle > config.STALL_AUTO and not proc_alive:
            busmod.do_reset("watchdog auto-reset"); warned = False


def main():
    mem.load_mem()
    mem.detect_previous_crash()
    mem.begin_session()
    conv.load()
    from ato.core import gaze
    gaze.start()
    config.MODEL = bootstrap.resolve_model(get_client)
    agent_loop.set_client(get_client)
    agent_loop.set_registry(load_plugins(emit=busmod.bus.emit))

    server.HOOKS.update(greet=greet, handle_message=agent_loop.handle_message,
                        tts=tts_handler, list_glbs=list_glbs, read_glb=read_glb,
                        info_extra=info_extra, models=models_list)

    threading.Thread(target=watchdog, daemon=True).start()

    httpd = server.make_server()
    url = f"http://127.0.0.1:{config.PORT}"
    print(f"\n  A.T.O. live at {url}")
    print("  " + bootstrap.boot_banner())
    print(f"  Sandbox: {sandbox.status()['kind']} ({sandbox.status()['reason']})")
    print("  Open in Edge/Chrome. Ctrl+C to shut down cleanly.\n")
    if config.OPEN_BROWSER:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        mem.MEM["session"]["clean_exit"] = True
        mem.save_mem()
        print("\n  clean shutdown.")
        httpd.shutdown()