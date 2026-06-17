"""
Single source of truth for constants and paths.
KERNEL FILE - A.T.O. may read this but must never self-edit it.
"""
import os
import uuid
import shutil

# ---- model / runtime ----
MODEL        = "gpt-5.5"           # resolved against your account at boot
START_MODE   = "step"
PORT         = 8765
OPEN_BROWSER = True
STEP_MAX     = 0                   # 0 = unlimited (loop until ask_user/finish/stop)
CMD_TIMEOUT  = 3600
STALL_WARN   = 60
STALL_AUTO   = 0                   # 0 = never auto-reset on stall

# ---- shell ----
DEFAULT_SHELL = "cmd"             # Windows command prompt by default

# ---- freedom switches ----
RESTRICTIONS    = False           # False = no command denylist, no path jail
ALLOW_KERNEL_EDIT = True          # True = self-edit any file except the recovery harness

# ---- voice ----
TTS_ENABLED  = True
TTS_MODEL    = "gpt-4o-mini-tts"
TTS_VOICE    = "onyx"

# ---- self-restart contract ----
RESTART_CODE = 42
BOOT_OK_SECS = 10

# ---- paths ----
PKG_DIR      = os.path.dirname(os.path.abspath(__file__))      # C:\ato\ato
PROJECT_ROOT = os.path.dirname(PKG_DIR)                        # C:\ato
STATE_DIR    = os.path.join(PKG_DIR, "state")
STATE_FILE   = os.path.join(STATE_DIR, "agent_state.json")
PLUGIN_DIR   = os.path.join(PKG_DIR, "plugins")
PERSONA_DIR  = os.path.join(PKG_DIR, "persona")
UI_HTML      = os.path.join(PERSONA_DIR, "ui.html")
GLB_DIR      = os.path.join(PERSONA_DIR, "avatars")

WORKDIR      = os.environ.get("ATO_WORKSPACE") or os.path.join(PROJECT_ROOT, "workspace")
ARCHIVE_DIR  = os.path.join(PROJECT_ROOT, "script_archive")    # every version of every script

for _d in (STATE_DIR, PLUGIN_DIR, WORKDIR, ARCHIVE_DIR):
    os.makedirs(_d, exist_ok=True)


# ---- git locator (fixes 'git not found' when git isn't on PATH) ----
def find_git():
    g = shutil.which("git")
    if g:
        return g
    for p in (r"C:\Program Files\Git\cmd\git.exe",
              r"C:\Program Files (x86)\Git\cmd\git.exe",
              os.path.expanduser(r"~\AppData\Local\Programs\Git\cmd\git.exe")):
        if os.path.exists(p):
            return p
    return "git"


GIT = find_git()

# ---- per-process identity ----
BOOT_ID = uuid.uuid4().hex

import platform
OSNAME = f"{platform.system()} {platform.release()}"