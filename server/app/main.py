from __future__ import annotations
import logging
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from app.config import settings
from app.utils.logging import configure_logging
from app.services.ingest import ingest_batch
import hashlib
from app.config import settings
from app.services.ingest import ingest_batch, tail_events, count_events
from app.services.summary import summarize_llm

configure_logging()
log = logging.getLogger("app")
app = FastAPI(title="WA Summarizer – Local Ingest")

@app.get("/")
def health():
    return {"ok": True}

@app.get("/debug")
def debug():
    return {
        "log_level": settings.LOG_LEVEL,
        "debug": settings.DEBUG,
        "events_jsonl": settings.EVENTS_JSONL,
        "log_file": settings.LOG_FILE,
    }

@app.post("/ingest/wa")
async def ingest_wa(batch: dict, authorization: str | None = Header(None)):
    res = ingest_batch(authorization or "", batch)
    return JSONResponse(res)

# add near the other routes
@app.get("/_debug/jwt_fp")
def jwt_fp():
    fp = hashlib.sha256(settings.WA_JWT_SECRET.encode()).hexdigest()
    return {"alg": "HS256", "len": len(settings.WA_JWT_SECRET), "sha256_16": fp[:16]}

@app.get("/ingest/_stats")
def ingest_stats():
    return {"events_total": count_events(), "file": settings.EVENTS_JSONL}

@app.get("/ingest/_tail")
def ingest_tail(n: int = 10):
    return {"last": tail_events(n)}

@app.get("/summary/whatsapp_llm")
def summary_whatsapp_llm(range: str | None = None, max_chats:int = 8, msgs_per_chat:int = 120, bullets_limit:int = 6):
    """
    LLM-powered summary.
    Examples:
      /summary/whatsapp_llm
      /summary/whatsapp_llm?range=7d&max_chats=5&msgs_per_chat=80
    """
    return summarize_llm(range, max_chats=max_chats, msgs_per_chat=msgs_per_chat, bullets_limit=bullets_limit)
