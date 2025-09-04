# server/app/services/llm_prompts.py

# MAP = run once per chat
MAP_SYS = """You are an assistant that extracts key information from WhatsApp messages.
Be concise. Do not invent content. Preserve Hebrew/English as written."""

MAP_USER = """You will receive a list of WhatsApp messages (newest first) from ONE chat.
Return a JSON object in this structure:
{
  "chat_title": string,
  "highlights": [string],
  "decisions": [string],
  "action_items": [{"assignee": string, "task": string, "due": string|null}],
  "dates": [{"what": string, "when": string}],
  "questions": [string]
}

If a section has nothing, return an empty list.

MESSAGES:
{{MESSAGES}}
"""

# REDUCE = run once for all chats together
REDUCE_SYS = """You merge multiple chat summaries into one overall digest.
Prioritize actionable, time-bound items. Remove duplicates. Stay concise."""

REDUCE_USER = """Given a JSON array of per-chat summaries, produce one combined JSON:
{
  "top_highlights": [string],
  "action_items": [{"assignee": string, "task": string, "due": string|null}],
  "upcoming_dates": [{"what": string, "when": string}],
  "unresolved_questions": [string],
  "per_chat": [{"title": string, "bullets": [string]}]
}

Limit each list to {{LIMIT}} items.

PER-CHAT INPUT:
{{JSON_ARRAY}}
"""
