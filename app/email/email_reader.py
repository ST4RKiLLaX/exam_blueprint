from imap_tools import MailBox, AND
from email.header import decode_header
import re

def decode_subject(subject_raw):
    try:
        parts = decode_header(subject_raw)
        decoded = ''.join([
            str(t[0], t[1] or "utf-8") if isinstance(t[0], bytes) else t[0]
            for t in parts
        ])
        return decoded
    except Exception as e:
        return subject_raw

def fetch_unread_emails(imap_host, imap_user, imap_pass, limit=5, port=993, use_ssl=True):
    emails = []
    # MailBox from imap_tools handles SSL automatically based on port
    # Port 993 = SSL, Port 143 = non-SSL
    with MailBox(host=imap_host, port=port).login(imap_user, imap_pass) as mailbox:
        for msg in mailbox.fetch(AND(seen=False), limit=limit, reverse=True):
            headers = getattr(msg, "headers", {}) or {}

            def hget(key):
                try:
                    return headers.get(key) or headers.get(key.lower()) or headers.get(key.title())
                except Exception:
                    try:
                        for k, v in headers:
                            if str(k).lower() == key.lower():
                                return v
                    except Exception:
                        pass
                    return None

            in_reply_to = hget("In-Reply-To")
            references_raw = hget("References")

            references = []
            if isinstance(references_raw, str):
                refs = re.findall(r"<[^>]+>", references_raw)
                if refs:
                    references = refs
                else:
                    references = [r.strip() for r in references_raw.replace(",", " ").split() if r.strip()]

            emails.append({
                "subject": decode_subject(msg.subject),
                "from": msg.from_,
                "body": msg.text or msg.html,
                "uid": msg.uid,
                "date": getattr(msg, "date", None),
                "message_id": getattr(msg, "message_id", None),
                "in_reply_to": in_reply_to,
                "references": references,
            })
    return emails

def mark_emails_as_read(imap_host, imap_user, imap_pass, email_uids, port=993, use_ssl=True):
    """Mark specific emails as read by their UIDs"""
    try:
        with MailBox(host=imap_host, port=port).login(imap_user, imap_pass) as mailbox:
            for uid in email_uids:
                mailbox.seen(uid, True)
        return True
    except Exception as e:
        print(f"Error marking emails as read: {e}")
        return False
