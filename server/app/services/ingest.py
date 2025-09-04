from __future__ import annotations
import json, time, logging
from pathlib import Path
from typing import Dict, Any
import jwt
from fastapi import HTTPException
from app.config import settings

log = logging.getLogger("ingest")
EVENTS_PATH = Path(settings.EVENTS_JSONL)


def _verify_jwt(auth_header: str) -> Dict[str, Any]:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer")
    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.WA_JWT_SECRET, algorithms=["HS256"], audience="ingest")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"invalid token: {e}")
    if payload.get("sub") != "wa-bridge":
        raise HTTPException(status_code=401, detail="bad subject")
    return payload


def ingest_batch(auth_header: str, batch: Dict[str, Any]) -> Dict[str, Any]:
    _verify_jwt(auth_header)
    bridge_id = (batch.get("bridge_id") or "").strip()
    allow = {b.strip() for b in (settings.WA_ALLOWLIST_BRIDGES or "").split(",") if b.strip()}
    if allow and bridge_id not in allow:
        raise HTTPException(status_code=403, detail=f"bridge {bridge_id!r} not allowed")

    events = batch.get("events") or []
    if not isinstance(events, list):
        raise HTTPException(status_code=400, detail="events must be a list")
    if len(events) > settings.WA_INGEST_MAX_BATCH:
        raise HTTPException(status_code=413, detail="batch too large")

    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    stored = 0
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        for e in events:
            rec = {"ts_server": int(time.time() * 1000), **e}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            stored += 1
    log.info("Stored %d event(s) from bridge=%s", stored, bridge_id or "(unknown)")
    return {"ok": True, "stored": stored}


def tail_events(n: int = 20):
    if not EVENTS_PATH.exists():
        return []
    lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()[-n:]
    return [json.loads(x) for x in lines]


def count_events():
    if not EVENTS_PATH.exists():
        return 0
    with EVENTS_PATH.open("r", encoding="utf-8") as f:
        return sum(1 for _ in f)
