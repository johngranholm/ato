"""
Supervisor (parent process). KERNEL FILE - never self-edited.
"""
import os
import sys
import time
import subprocess

from ato import config

RESTART_CODE = config.RESTART_CODE
BOOT_OK_SECS = config.BOOT_OK_SECS
ROOT = config.PROJECT_ROOT
GIT = config.GIT
LASTGOOD_REF = "lastgood"


def _git(*args):
    try:
        return subprocess.run([GIT, "-C", ROOT, *args], capture_output=True, text=True)
    except FileNotFoundError:
        return None


def _has_git():
    r = _git("rev-parse", "--is-inside-work-tree")
    return bool(r) and r.returncode == 0


def _ensure_lastgood():
    if not _has_git():
        print(f"[supervisor] git not found at '{GIT}' - rollback-on-boot disabled.")
        return
    r = _git("rev-parse", "--verify", "--quiet", LASTGOOD_REF)
    if not r or r.returncode != 0:
        _git("branch", "-f", LASTGOOD_REF, "HEAD")
        print(f"[supervisor] seeded '{LASTGOOD_REF}' at HEAD.")


def _rollback_lastgood():
    if not _has_git():
        return False
    r = _git("reset", "--hard", LASTGOOD_REF)
    ok = bool(r) and r.returncode == 0
    print("[supervisor] rolled back to lastgood." if ok else "[supervisor] rollback failed.")
    return ok


def _launch_worker():
    env = dict(os.environ); env["AGENT_WORKER"] = "1"
    return subprocess.run([sys.executable, "-m", "ato"] + sys.argv[1:],
                          cwd=ROOT, env=env).returncode


def supervise():
    _ensure_lastgood()
    while True:
        t0 = time.time()
        try:
            rc = _launch_worker()
        except KeyboardInterrupt:
            rc = 0
        alive = time.time() - t0
        if rc == RESTART_CODE:
            print("[supervisor] reboot requested - relaunching...")
            continue
        if rc != 0 and alive < BOOT_OK_SECS:
            print(f"[supervisor] worker died in {alive:.1f}s (code {rc}); rolling back.")
            _rollback_lastgood()
            continue
        break


if __name__ == "__main__":
    supervise()