"""Command execution + process control."""
import platform
import threading
import subprocess

from ato import config
from ato.core import bus as busmod

proc_lock = threading.Lock()
current_proc = {"p": None}


def kill_current():
    with proc_lock:
        p = current_proc["p"]
    if not p or p.poll() is not None:
        return
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        else:
            p.kill()
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def run_command(cmd, shell):
    if shell == "wsl":
        args, use_shell = ["wsl", "bash", "-lc", cmd], False
    elif shell == "powershell":
        args, use_shell = ["powershell", "-NoProfile", "-Command", cmd], False
    else:
        args, use_shell = cmd, True
    try:
        proc = subprocess.Popen(args, shell=use_shell, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                text=True, bufsize=1, cwd=config.WORKDIR)
    except Exception as e:
        busmod.bus.emit("error", f"Failed to launch command: {e}", mood="frustrated")
        return f"launch error: {e}", -1
    with proc_lock:
        current_proc["p"] = proc
    killer = threading.Timer(config.CMD_TIMEOUT, proc.kill); killer.start()
    lines = []
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            busmod.bus.emit("output", line)
            lines.append(line)
            if busmod.state["cancel"]:
                kill_current(); busmod.bus.emit("system", "Command cancelled."); break
    finally:
        killer.cancel()
        proc.wait()
        with proc_lock:
            current_proc["p"] = None
    tail = "\n".join(lines[-200:]) if lines else "(no output)"
    busmod.bus.emit("system", f"[exit code {proc.returncode}]")
    return tail, proc.returncode


def write_script(path, content):
    import os
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content if content is not None else "")
        return True, os.path.getsize(path)
    except Exception as e:
        return False, str(e)