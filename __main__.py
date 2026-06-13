"""
Entry point. `python -m ato` -> supervisor -> worker.
KERNEL FILE - never self-edited.
"""
import os

from ato.supervisor import supervise


def _run_worker():
    # Imported lazily so the supervisor never pulls in heavy core deps.
    from ato.runtime import main      # arrives in Module 3
    main()


if __name__ == "__main__":
    if os.environ.get("AGENT_WORKER") == "1":
        _run_worker()
    else:
        supervise()