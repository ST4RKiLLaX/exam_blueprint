import os
from dotenv import load_dotenv
from app.email.email_reader import fetch_unread_emails
from app.email.email_sender import send_email
from app.agents.email_agent import generate_reply
from app.email.thread_store import add_inbound, add_outbound, get_history

load_dotenv()

imap_host = os.getenv("IMAP_HOST")
smtp_host = os.getenv("SMTP_HOST")
email_user = os.getenv("EMAIL_USER")
email_pass = os.getenv("EMAIL_PASS")

print("🤖 Starting automated email reply process...")

emails = fetch_unread_emails(imap_host, email_user, email_pass)

if not emails:
    print("📭 No unread emails found.")
else:
    print(f"📨 Found {len(emails)} unread email(s)")

for i, email in enumerate(emails, 1):
    print(f"\n--- Processing Email {i}/{len(emails)} ---")
    print(f"📨 From: {email['from']}")
    print(f"Subject: {email['subject']}")
    print("Generating reply...")

    try:
        thread_key = add_inbound(email)
        history = get_history(thread_key, limit=10)
        reply = generate_reply(email["body"], history=history)

        print("✉️ Sending automated reply...")
        in_reply_to = email.get("message_id")
        references = list(set((email.get("references") or []) + ([in_reply_to] if in_reply_to else [])))
        sent_id = send_email(smtp_host, email_user, email_pass, email["from"], email["subject"], reply, in_reply_to=in_reply_to, references=references)
        add_outbound(thread_key, email["from"], email["subject"], reply, sent_id, in_reply_to=in_reply_to, references=references)
        print("✅ Email sent successfully!")
        
    except Exception as e:
        print(f"❌ Error processing email: {e}")
        continue

print(f"\n🎉 Automated reply process completed! Processed {len(emails)} email(s)") 