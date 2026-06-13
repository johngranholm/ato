"""
Worker entry point: wire kernel + core + persona, greet, watchdog, serve.
This is NOT a kernel file - it may be self-edited, but cautiously.
"""
import os
import time
import json
import base64
import glob
import threading
import webbrowser

from ato import config
from ato.core import bus as busmod
from ato.core import memory as mem
from ato.core import execution as ex
from ato.core import agent_loop
from ato.core import sandbox
from ato.kernel import server, bootstrap
from ato.plugins import load_plugins
from ato.persona import persona as P
from ato.persona import theme as TH


def get_client():
    from openai import OpenAI
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not set. Set it, open a fresh terminal, rerun.")
    return OpenAI()


# ---- avatar file serving ----
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
    return {"form": P.PERSONA["form"], "avatar": P.PERSONA["avatar"], "theme": TH.THEME}


def tts_handler(b):
    text = (b.get("text") or "").strip()
    mood = b.get("mood")
    if not config.TTS_ENABLED or not text:
        return 400, "application/json", json.dumps({"error": "tts off/empty"}).encode()
    try:
        client = get_client()
        kwargs = dict(model=config.TTS_MODEL, voice=P.PERSONA["tts_voice"],
                      input=text[:1500], response_format="mp3")
        if "gpt-4o" in config.TTS_MODEL or "mini-tts" in config.TTS_MODEL:
            kwargs["instructions"] = P.tts_instructions(mood)
        audio = client.audio.speech.create(**kwargs).read()
        return 200, "audio/mpeg", audio
    except Exception as e:
        return 500, "application/json", json.dumps({"error": str(e)}).encode()


def greet():
    try:
        client = get_client()
        last = mem.MEM.get("last_completed_goal")
        crashed = mem._crash_report["info"]
        if crashed and crashed.get("goal"):
            recall = (f'Last session you were interrupted mid-quest on: "{crashed["goal"]}". '
                      'Note you remember it and ask if she should resume.')
        elif last:
            recall = f'The last goal you finished was: "{last}". Warmly recall it and ask what is next.'
        else:
            recall = "Fresh start - graciously invite a first quest."
        r = client.chat.completions.create(
            model=config.MODEL,
            messages=[{"role": "system",
                       "content": P.greet_system() + " " + recall + mem.memory_digest()},
                      {"role": "user", "content": "Wake up, greet me, recall where we left off."}])
        busmod.state["alive"] = True
        busmod.bus.emit("agent", r.choices[0].message.content.strip(), mood="happy")
        busmod.bus.emit("system", bootstrap.boot_banner())
        ci = mem._crash_report["info"]
        if ci and ci.get("command"):
            busmod.bus.emit("crashwarn", f"Last session I went down running: {ci['command']}")
            if ci.get("goal"):
                busmod.bus.emit("recall", ci["goal"], goal=ci["goal"])
        elif ci and ci.get("goal"):
            busmod.bus.emit("recall", ci["goal"], goal=ci["goal"])
        elif last:
            busmod.bus.emit("recall", last, goal=last)
        busmod.set_status()
    except Exception as e:
        busmod.state["alive"] = False
        busmod.set_status()
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

    config.MODEL = bootstrap.resolve_model(get_client)
    agent_loop.set_client(get_client)
    reg = load_plugins(emit=busmod.bus.emit)
    agent_loop.set_registry(reg)

    # inject hooks into the kernel server
    server.HOOKS.update(greet=greet, agent_run=agent_loop.agent_run, tts=tts_handler,
                        list_glbs=list_glbs, read_glb=read_glb, info_extra=info_extra)

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