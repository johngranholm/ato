"""
Single source of truth for constants and paths.
KERNEL FILE - A.T.O. may read this but must never self-edit it.
Cosmetics (THEME/PERSONA) live in ato/persona/, NOT here.
"""
import os
import uuid

# ---- model / runtime ----
MODEL        = "gpt-5.4-mini"      # resolved against /models at boot (bootstrap.py)
START_MODE   = "step"              # "step" (asks first) or "auto"
PORT         = 8765
OPEN_BROWSER = True
STEP_MAX     = 40
CMD_TIMEOUT  = 1800
STALL_WARN   = 45
STALL_AUTO   = 120

# ---- voice ----
TTS_ENABLED  = True
TTS_MODEL    = "gpt-4o-mini-tts"
TTS_VOICE    = "onyx"

# ---- self-restart contract (supervisor <-> worker) ----
RESTART_CODE = 42                  # worker exits with this to request a relaunch
BOOT_OK_SECS = 10                  # survive this long -> promoted to "known-good"

# ---- paths ----
PKG_DIR      = os.path.dirname(os.path.abspath(__file__))      # .../ato
PROJECT_ROOT = os.path.dirname(PKG_DIR)                        # repo root (git lives here)
STATE_DIR    = os.path.join(PKG_DIR, "state")
STATE_FILE   = os.path.join(STATE_DIR, "agent_state.json")
WORKDIR      = os.path.join(PKG_DIR, "workspace")             # A.T.O.'s scratch (gitignored)
PLUGIN_DIR   = os.path.join(PKG_DIR, "plugins")
PERSONA_DIR  = os.path.join(PKG_DIR, "persona")
UI_HTML      = os.path.join(PERSONA_DIR, "ui.html")
GLB_DIR      = os.path.join(PERSONA_DIR, "avatars")

for _d in (STATE_DIR, WORKDIR, PLUGIN_DIR):
    os.makedirs(_d, exist_ok=True)

# ---- per-process identity (browser uses it to detect a fresh worker) ----
BOOT_ID = uuid.uuid4().hex

import platform
OSNAME = f"{platform.system()} {platform.release()}"