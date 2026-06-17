"""Event bus + shared runtime state + reboot scheduling + mid-run injection."""
import os
import time
import queue
import threading

from ato import config
from ato.core import memory as mem

state = {"mode": config.START_MODE, "running": False, "cancel": False,
         "alive": False, "awaiting": False, "last_activity": time.time()}
goal_lock = threading.Lock()
approval_event = threading.Event()
approval = {"text": None}
RESTART_PENDING = {"v": False}

# messages the user sends WHILE the loop is running -> injected at next step
_inject_lock = threading.Lock()
_inject = []


def inject(text):
    with _inject_lock:
        _inject.append(text)


def drain_injects():
    with _inject_lock:
        out = list(_inject)
        _inject.clear()
    return out


class Bus:
    def __init__(self):
        self.clients, self.log, self.lock = [], [], threading.Lock()

    def subscribe(self):
        q = queue.Queue()
        with self.lock:
            for ev in self.log[-300:]:
                q.put(ev)
            self.clients.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    def emit(self, etype, text="", **kw):
        state["last_activity"] = time.time()
        ev = {"type": etype, "text": text, "t": time.time()}
        ev.update(kw)
        with self.lock:
            self.log.append(ev)
            if len(self.log) > 1500:
                self.log = self.log[-1500:]
            for q in list(self.clients):
                q.put(ev)


bus = Bus()


def set_status():
    if state["running"]:
        s = "running"
    elif state["awaiting"]:
        s = "awaiting"
    elif state["alive"]:
        s = "alive"
    else:
        s = "down"
    bus.emit("status", status=s, mode=state["mode"])


def do_reset(reason="manual reset"):
    from ato.core import execution as ex
    state["cancel"] = True
    approval_event.set()
    ex.kill_current()
    state["running"] = False
    state["awaiting"] = False
    drain_injects()
    bus.emit("reset", f"Reset: {reason}. I've dropped what I was doing.", mood="relief")
    mem.mark_active(clear_cmd=True)
    set_status()


def schedule_reboot(reason=""):
    RESTART_PENDING["v"] = True
    bus.emit("reload", ("Rebuilding myself - " + reason).strip(" -"), mood="joy")

    def _go():
        time.sleep(0.7)
        try:
            mem.MEM["session"]["clean_exit"] = True
            mem.MEM["session"]["restarted"] = True
            mem.save_mem()
        except Exception:
            pass
        os._exit(config.RESTART_CODE)
    threading.Thread(target=_go, daemon=True).start()