"""Run: python -m app.jobs.reminders          (once)
       python -m app.jobs.reminders --loop   (every 15 minutes; used by the docker-compose worker)"""

import sys
import time

from ..db import SessionLocal
from ..services import reminders


def once() -> dict:
    from ..api.documents import purge_expired

    with SessionLocal() as db:
        out = reminders.run(db)
        out["purged_documents"] = purge_expired(db)
        return out


if __name__ == "__main__":
    if "--loop" in sys.argv:
        while True:
            print(once(), flush=True)
            time.sleep(900)
    else:
        print(once())
