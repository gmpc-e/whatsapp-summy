from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Iterator, List, Tuple

from app.config import settings

# Optional LLM deps (only used by summarize_llm)
try:
    from app.connectors.openai_client import chat_json
    from app.services.llm_prompts import MAP_SYS, MAP_USER, REDUCE_SYS, REDUCE_USER
    _LLM_AVAILABLE = True
except Exception:
    _LLM_AVAILABLE = False

log = logging.getLogger("summary")
EVENTS_PATH = Path(settings.EVENTS_JSONL)


# -----------------------------
# Time window helpers
# -----------------------------
@dataclass
class TimeWindow:
    start_ms: int
    end_ms: int


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def parse_range(range_str: str | None) -> TimeWindow:
    """
    Supported:
      'today' (default), 'yesterday', '7d', '14d',
      'YYYY-MM-DD',
      'YYYY-MM-DD..YYYY-MM-DD'  (inclusive of last day)
    Range is applied to server-side ts_server (UTC).
    """
    now = _now_utc()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if not range_str or range_str == "today":
        start = midnight
        end = now
    elif range_str == "yesterday":
        start = midnight - timedelta(days=1)
        end = midnight
    elif range_str.endswith("d") and range_str[:-1].isdigit():
        days = int(range_str[:-1])
        start = now - timedelta(days=days)
        end = now
    elif ".." in (range_str or ""):
        a, b = range_str.split("..", 1)
        start = datetime.fromisoformat(a).replace(tzinfo=timezone.utc)
        # include entire end day
        end = datetime.fromisoformat(b).replace(tzinfo=timezone.utc) + timedelta(days=1)
    else:
        # single day
        d = datetime.fromisoformat(range_str).replace(tzinfo=timezone.utc)
        start = d
        end = d + timedelta(days=1)

    return TimeWindow(_to_ms(start), _to_ms(end))


# -----------------------------
# Event iteration & utilities
# -----------------------------
def _iter_events_between(tw: TimeWindow) -> Iterator[Dict[str, Any]]:
    if not EVENTS_PATH.exists():
        return
    with EVENTS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            ts = int(rec.get("ts_server") or 0)
            if tw.start_ms <= ts < tw.end_ms:
                yield rec


def _key_chat(rec: Dict[str, Any]) -> Tuple[str, str]:
    chat = rec.get("chat") or {}
    jid = chat.get("jid") or "unknown"
    title = chat.get("title") or jid
    return jid, title


def _fmt_time_utc(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")


# -----------------------------
# Plain (non-LLM) summarizer
# -----------------------------
def summarize(range_str: str | None, limit_per_chat: int = 5) -> Dict[str, Any]:
    """
    Lightweight digest: groups by chat and shows last N lines per chat.
    No LLM used here.
    """
    tw = parse_range(range_str)
    by_chat: Dict[str, Dict[str, Any]] = {}
    count = 0

    for rec in _iter_events_between(tw):
        if rec.get("type") != "message":
            continue
        jid, title = _key_chat(rec)
        msg = rec.get("msg") or {}
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        by_chat.setdefault(jid, {"title": title, "messages": []})["messages"].append({
            "ts": int(msg.get("ts") or rec.get("ts_server") or 0),
            "sender": (msg.get("sender") or {}).get("name") or (msg.get("sender") or {}).get("jid") or "unknown",
            "text": text,
        })
        count += 1

    # sort & cap
    for chat in by_chat.values():
        chat["messages"].sort(key=lambda m: m["ts"])
        if limit_per_chat > 0:
            chat["messages"] = chat["messages"][-limit_per_chat:]

    # top chats by activity
    top = sorted(by_chat.values(), key=lambda c: len(c["messages"]), reverse=True)

    if not top:
        return {
            "range": range_str or "today",
            "window": {"start_ms": tw.start_ms, "end_ms": tw.end_ms},
            "summary_text": "📭 No messages in the selected range.",
            "per_chat": [],
            "total_messages": 0,
        }

    # render
    out_lines: List[str] = [f"🧾 WhatsApp digest — {range_str or 'today'}"]
    for chat in top:
        msgs = chat["messages"]
        out_lines.append(f"\n# {chat['title']} · last {len(msgs)}")
        for m in msgs:
            out_lines.append(f"• [{_fmt_time_utc(m['ts'])}] {m['sender']}: {m['text']}")

    return {
        "range": range_str or "today",
        "window": {"start_ms": tw.start_ms, "end_ms": tw.end_ms},
        "summary_text": "\n".join(out_lines),
        "per_chat": top,
        "total_messages": count,
    }


# -----------------------------
# LLM-powered summarizer (map → reduce)
# -----------------------------
def summarize_llm(
    range_str: str | None,
    max_chats: int = 8,
    msgs_per_chat: int = 120,
    bullets_limit: int = 6,
) -> Dict[str, Any]:
    """
    LLM-powered digest:
      1) Select the window & most active chats
      2) Send capped recent messages per chat to MAP prompt
      3) Merge all per-chat JSON via REDUCE prompt
      4) Render a compact digest

    Requires OPENAI_API_KEY and app.connectors.openai_client to be available.
    """
    if not _LLM_AVAILABLE:
        return {
            "error": "LLM components not available. Set OPENAI_API_KEY and ensure openai_client/prompts are importable."
        }

    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))

    tw = parse_range(range_str)

    # Collect messages per chat
    raw_by_chat: Dict[str, Dict[str, Any]] = {}
    for rec in _iter_events_between(tw):
        if rec.get("type") != "message":
            continue
        jid, title = _key_chat(rec)
        m = rec.get("msg") or {}
        text = (m.get("text") or "").strip()
        if not text:
            continue
        raw_by_chat.setdefault(jid, {"title": title, "messages": []})["messages"].append({
            "ts": int(m.get("ts") or rec.get("ts_server") or 0),
            "sender": (m.get("sender") or {}).get("name") or (m.get("sender") or {}).get("jid") or "unknown",
            "text": text,
        })

    # Keep most active chats; cap messages per chat (newest first)
    chats = sorted(raw_by_chat.values(), key=lambda c: len(c["messages"]), reverse=True)[:max_chats]
    for c in chats:
        c["messages"].sort(key=lambda x: x["ts"], reverse=True)
        c["messages"] = c["messages"][:msgs_per_chat]

    # MAP — per-chat JSON extraction
    per_chat_json: List[Dict[str, Any]] = []
    for c in chats:
        # Newest first lines, "sender: text"
        lines = [f"{m['sender']}: {m['text']}" for m in c["messages"]]
        map_messages = [
            {"role": "system", "content": MAP_SYS},
            {"role": "user", "content": MAP_USER.replace("{{MESSAGES}}", "\n".join(lines))},
        ]
        try:
            content = chat_json(model, map_messages, max_tokens=1200, temperature=temperature)
            obj = json.loads(content or "{}")
            if "chat_title" not in obj:
                obj["chat_title"] = c["title"]
            per_chat_json.append(obj)
        except Exception as e:
            log.warning("MAP step failed for chat '%s': %s", c["title"], e)
            per_chat_json.append({
                "chat_title": c["title"],
                "highlights": [], "decisions": [],
                "action_items": [], "dates": [], "questions": [],
            })

    # REDUCE — global merge
    reduce_messages = [
        {"role": "system", "content": REDUCE_SYS},
        {"role": "user",
         "content": (REDUCE_USER
                     .replace("{{LIMIT}}", str(bullets_limit))
                     .replace("{{JSON_ARRAY}}", json.dumps(per_chat_json, ensure_ascii=False)))}
    ]
    try:
        merged_s = chat_json(model, reduce_messages, max_tokens=1500, temperature=temperature)
        merged = json.loads(merged_s or "{}")
    except Exception as e:
        log.warning("REDUCE step failed: %s", e)
        merged = {"top_highlights": [], "action_items": [], "upcoming_dates": [], "unresolved_questions": [], "per_chat": []}

    # Render compact digest
    def _section(title: str, items: List[Any]) -> List[str]:
        if not items:
            return []
        out = [f"\n{title}"]
        for it in items[:bullets_limit]:
            if isinstance(it, str):
                out.append(f"• {it}")
            else:
                out.append(f"• {json.dumps(it, ensure_ascii=False)}")
        return out

    lines: List[str] = [f"🧾 WhatsApp digest — {range_str or 'today'}"]
    lines += _section("⭐ Top Highlights", merged.get("top_highlights", []))

    # Action items special rendering
    ai = merged.get("action_items", [])[:bullets_limit]
    if ai:
        lines.append("\n✅ Action Items")
        for a in ai:
            assignee = a.get("assignee") or "Someone"
            task = a.get("task") or ""
            due = f' (due {a.get("due")})' if a.get("due") else ""
            lines.append(f"• {assignee}: {task}{due}")

    lines += _section("🗓️ Dates", merged.get("upcoming_dates", []))
    lines += _section("❓ Questions", merged.get("unresolved_questions", []))

    for c in merged.get("per_chat", []):
        title = c.get("title") or "Chat"
        bullets = c.get("bullets") or []
        lines.append(f"\n# {title}")
        for b in bullets[:bullets_limit]:
            lines.append(f"• {b}")

    return {
        "range": range_str or "today",
        "window": {"start_ms": tw.start_ms, "end_ms": tw.end_ms},
        "summary_text": "\n".join(lines),
        "llm": {"per_chat": per_chat_json, "merged": merged},
    }
