"""
Environment detection. Decides whether privileged tools (package install,
OS edits) are allowed THIS run. The rule: A.T.O. gets full reign INSIDE a
disposable sandbox, never on the bare host.
"""
import os
import platform

_cache = {"v": None}


def _detect():
    # explicit override (set by the sandbox launcher)
    forced = os.environ.get("ATO_SANDBOX")
    if forced:
        return {"kind": forced, "privileged": True,
                "reason": "ATO_SANDBOX env set by launcher"}
    # container?
    if os.path.exists("/.dockerenv") or os.environ.get("container"):
        return {"kind": "container", "privileged": True, "reason": "container detected"}
    # WSL?
    rel = platform.release().lower()
    if "microsoft" in rel or "wsl" in rel:
        return {"kind": "wsl", "privileged": True, "reason": "WSL detected"}
    # bare host -> restricted
    return {"kind": "host", "privileged": False,
            "reason": "running on bare host - privileged tools disabled"}


def status():
    if _cache["v"] is None:
        _cache["v"] = _detect()
    return _cache["v"]


def is_privileged():
    return status()["privileged"]