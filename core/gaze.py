"""
Gaze bridge. A running OpenCV/tracker app writes normalized coords to
gaze.json; this watcher emits a 'gaze' bus event the avatar reacts to.

gaze.json format:  {"x": 0.0-1.0, "y": 0.0-1.0, "label": "intruder"}
  x,y are normalized screen position (0,0 = top-left, 1,1 = bottom-right).
"""
import os
import json
import time
import threading

from ato import config
from ato.core import bus as busmod

GAZE_FILE = os.path.join(config.STATE_DIR, "gaze.json")
_last_mtime = {"v": 0}


def _watch():
    while True:
        try:
            m = os.path.getmtime(GAZE_FILE)
            if m != _last_mtime["v"]:
                _last_mtime["v"] = m
                with open(GAZE_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                x = float(d.get("x", 0.5)); y = float(d.get("y", 0.5))
                busmod.bus.emit("gaze", d.get("label", ""), x=x, y=y)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            pass
        except Exception:
            pass
        time.sleep(0.1)          # 10 Hz - smooth enough for head tracking


def start():
    threading.Thread(target=_watch, daemon=True).start()