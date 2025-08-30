import json
from pathlib import Path
import re
from typing import Dict, Any, List

STORE_PATH = Path(__file__).resolve().parents[1] / "data" / "thread_store.json"

def _ensure_store_dir():
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)

def load_store() -> Dict[str, Any]:
    _ensure_store_dir()
    if STORE_PATH.exists():
        try:
            with open(STORE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"threads": {}, "message_index": {}}

def save_store(store: Dict[str, Any]) -> None:
    _ensure_store_dir()
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)

def normalize_subject(subject: str) -> str:
    if not subject:
        return ""
    s = subject.strip()
    while True:
        s2 = re.sub(r"^(re|fwd|fw)\s*:\s*", "", s, flags=re.IGNORECASE)
        if s2 == s:
            break
        s = s2
    s = re.sub(r"\s+", " ", s)
    return s.lower()

def _refs_list(references) -> List[str]:
    if not references:
        return []
    if isinstance(references, str):
        references = [references]
    out = []
    for r in references:
        if not r:
            continue
        r = str(r).strip()
        if r.startswith("<") and r.endswith(">"):
            out.append(r)
        else:
            out.append(f"<{r.strip('<>')}>")
    return out

def compute_thread_key(email_obj: Dict[str, Any], store: Dict[str, Any]) -> str:
    msg_index = store.get("message_index", {})
    for ref in _refs_list(email_obj.get("references")) + _refs_list([email_obj.get("in_reply_to")]):
        if ref in msg_index:
            return msg_index[ref]
    subj = normalize_subject(email_obj.get("subject", ""))
    sender = (email_obj.get("from") or "").lower()
    return f"{subj}|{sender}"

def add_inbound(email_obj: Dict[str, Any]) -> str:
    store = load_store()
    threads = store["threads"]
    msg_index = store["message_index"]

    thread_key = compute_thread_key(email_obj, store)
    thread = threads.setdefault(thread_key, {"messages": []})
    thread["messages"].append({
        "role": "user",
        "from": email_obj.get("from"),
        "subject": email_obj.get("subject"),
        "content": email_obj.get("body") or "",
        "message_id": email_obj.get("message_id"),
        "in_reply_to": email_obj.get("in_reply_to"),
        "references": _refs_list(email_obj.get("references")),
    })
    mid = email_obj.get("message_id")
    if mid:
        mid_norm = mid if (mid.startswith("<") and mid.endswith(">")) else f"<{str(mid).strip('<>')}>"
        msg_index[mid_norm] = thread_key

    save_store(store)
    return thread_key

def add_outbound(thread_key: str, to_email: str, subject: str, body: str, message_id: str, in_reply_to=None, references=None):
    store = load_store()
    threads = store["threads"]
    msg_index = store["message_index"]

    thread = threads.setdefault(thread_key, {"messages": []})
    thread["messages"].append({
        "role": "assistant",
        "to": to_email,
        "subject": subject,
        "content": body,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "references": _refs_list(references),
    })

    if message_id:
        mid_norm = message_id if (message_id.startswith("<") and message_id.endswith(">")) else f"<{str(message_id).strip('<>')}>"
        msg_index[mid_norm] = thread_key

    save_store(store)

def get_history(thread_key: str, limit: int = 10) -> List[Dict[str, str]]:
    store = load_store()
    thread = store.get("threads", {}).get(thread_key)
    if not thread:
        return []
    msgs = thread.get("messages", [])
    return [{"role": m.get("role"), "content": m.get("content", "")} for m in msgs[-limit:]]

