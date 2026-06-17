"""
Boot helpers. KERNEL FILE - never self-edited.
Resolves the model against the account (graceful fallback) and detects the
execution environment so dangerous OS/install tools only exist in a sandbox.
"""
from ato import config
from ato.core import sandbox


def resolve_model(get_client):
    """Pick a working model. Falls back instead of leaving A.T.O. 'not alive'."""
    try:
        ids = {m.id for m in get_client().models.list().data}
    except Exception:
        return config.MODEL          # offline / will surface in greet()
    if config.MODEL in ids:
        return config.MODEL
    for cand in ("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"):
        if cand in ids:
            config.MODEL = cand
            return cand
    # last resort: any chat-ish model
    for mid in sorted(ids):
        if "gpt" in mid:
            config.MODEL = mid
            return mid
    return config.MODEL


def boot_banner():
    s = sandbox.status()
    return (f"Model: {config.MODEL} | Mode: {config.START_MODE.upper()} | "
            f"Sandbox: {s['kind']} ({'privileged' if s['privileged'] else 'restricted'}) | "
            f"Boot: {config.BOOT_ID[:8]}")