"""Persistent memory: completed-goal recipes + crash black box. Atomic saves."""
import os
import re
import time
import json
import difflib
import threading

from ato import config

mem_lock = threading.Lock()
MEM = {
    "last_completed_goal": None,
    "history": [],
    "crashes": [],
    "session": {},
    "memory_on": True,
}


def load_mem():
    global MEM
    try:
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k in MEM:
            if k in data:
                MEM[k] = data[k]
    except Exception:
        pass


def save_mem():
    with mem_lock:
        try:
            tmp = config.STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                json.dump(MEM, f, indent=2)
            os.replace(tmp, config.STATE_FILE)          # atomic
        except Exception:
            pass


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def similar(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def add_crash(kind, text, shell, error):
    if not text:
        return
    for c in MEM["crashes"]:
        if similar(text, c["text"]) >= 0.9 and c["kind"] == kind:
            c["count"] = c.get("count", 1) + 1
            c["t"] = time.time(); c["error"] = error
            save_mem(); return
    MEM["crashes"].append({"kind": kind, "text": text, "shell": shell,
                           "error": error, "t": time.time(), "count": 1})
    MEM["crashes"] = MEM["crashes"][-50:]
    save_mem()


def crash_match(text, kind=None):
    best, bestr = None, 0.0
    for c in MEM["crashes"]:
        if kind and c["kind"] != kind:
            continue
        r = similar(text, c["text"])
        if r > bestr:
            bestr, best = r, c
    return best if bestr >= 0.82 else None


def memory_digest(max_wins=4, max_steps=6, max_crashers=5):
    if not MEM.get("memory_on"):
        return ""
    lines = []
    wins = [h for h in MEM.get("history", []) if h.get("status") == "done"][-max_wins:]
    if wins:
        lines.append("GOALS YOU'VE COMPLETED BEFORE - reuse these recipes, don't re-derive:")
        for h in wins:
            lines.append(f'  Goal: "{norm(h.get("goal"))[:100]}"')
            for step in (h.get("recipe") or [])[:max_steps]:
                lines.append(f"    -> {step.replace(chr(10), ' ')[:100]}")
    crashes = sorted(MEM.get("crashes", []), key=lambda c: c.get("count", 1),
                     reverse=True)[:max_crashers]
    if crashes:
        lines.append("THINGS THAT CRASHED/HUNG YOU BEFORE - avoid or be careful:")
        for c in crashes:
            txt = (c.get("text") or "").strip().replace("\n", " ")[:100]
            lines.append(f"  - [{c['kind']} x{c.get('count', 1)}] {txt}")
    return ("\n\nYOUR MEMORY (persisted across sessions):\n" + "\n".join(lines)) if lines else ""


# ---- session / crash black box ----
_crash_report = {"info": None}


def detect_previous_crash():
    sess = MEM.get("session") or {}
    if sess and not sess.get("clean_exit", True):
        ac, ag, sh = sess.get("active_command"), sess.get("active_goal"), sess.get("active_shell")
        if ac or ag:
            add_crash("command" if ac else "goal", ac or ag, sh,
                      "Process ended without clean shutdown.")
            _crash_report["info"] = {"goal": ag, "command": ac, "shell": sh}


def begin_session():
    MEM["session"] = {"clean_exit": False, "active_goal": None,
                      "active_command": None, "active_shell": None,
                      "started": time.time(), "pid": os.getpid()}
    save_mem()


def mark_active(goal=False, command=None, shell=None, clear_cmd=False):
    s = MEM["session"]
    if goal is not False:
        s["active_goal"] = goal
    if command is not None:
        s["active_command"], s["active_shell"] = command, shell
    if clear_cmd:
        s["active_command"], s["active_shell"] = None, None
    save_mem()