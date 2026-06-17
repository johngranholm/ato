"""Boot helpers. KERNEL FILE - never self-edited."""
from ato import config
from ato.core import sandbox


def resolve_model(get_client):
    try:
        ids = {m.id for m in get_client().models.list().data}
    except Exception:
        return config.MODEL
    if config.MODEL in ids:
        return config.MODEL
    for cand in ("gpt-5.5", "gpt-5.4", "gpt-5.3-codex", "gpt-5.4-mini",
                 "gpt-5", "gpt-4.1", "gpt-4o"):
        if cand in ids:
            config.MODEL = cand
            return cand
    for mid in sorted(ids):
        if "gpt-5" in mid or "gpt-4" in mid:
            config.MODEL = mid
            return mid
    return config.MODEL


def boot_banner():
    s = sandbox.status()
    return (f"Model: {config.MODEL} | Mode: {config.START_MODE.upper()} | "
            f"Restrictions: {'ON' if config.RESTRICTIONS else 'OFF'} | "
            f"Boot: {config.BOOT_ID[:8]}")