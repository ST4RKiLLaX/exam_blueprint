import os
import time
from datetime import datetime
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

def auto_reply_to_emails():
    """Automatically reply to unread emails without confirmation"""
    print(f"🤖 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for unread emails...")
    
    # Fetch unread emails
    emails = fetch_unread_emails(imap_host, email_user, email_pass)
    
    if not emails:
        print("📭 No unread emails found.")
        return
    
    print(f"📨 Found {len(emails)} unread email(s)")
    
    for i, email in enumerate(emails, 1):
        print(f"\n--- Processing Email {i}/{len(emails)} ---")
        print(f"📧 From: {email['from']}")
        print(f"📋 Subject: {email['subject']}")
        print("🤖 Generating AI reply...")
        
        try:
            thread_key = add_inbound(email)
            history = get_history(thread_key, limit=10)
            # Generate AI reply
            reply = generate_reply(email["body"], history=history)
            
            print("✉️ Sending automated reply...")
            
            # Send the email automatically
            in_reply_to = email.get("message_id")
            references = list(set((email.get("references") or []) + ([in_reply_to] if in_reply_to else [])))
            sent_id = send_email(smtp_host, email_user, email_pass, email["from"], email["subject"], reply, in_reply_to=in_reply_to, references=references)
            add_outbound(thread_key, email["from"], email["subject"], reply, sent_id, in_reply_to=in_reply_to, references=references)
            
            print("✅ Email sent successfully!")
            
        except Exception as e:
            print(f"❌ Error processing email: {e}")
            continue
    
    print(f"🎉 Processed {len(emails)} email(s)")

def run_daemon(check_interval=60):
    """Run the email auto-reply daemon continuously"""
    print("🚀 Starting Email Auto-Reply Daemon...")
    print(f"⏰ Check interval: {check_interval} seconds")
    print("🛑 Press Ctrl+C to stop")
    print("-" * 50)
    
    try:
        while True:
            try:
                auto_reply_to_emails()
            except KeyboardInterrupt:
                print("\n🛑 Daemon stopped by user.")
                break
            except Exception as e:
                print(f"❌ Daemon error: {e}")
            
            print(f"⏳ Waiting {check_interval} seconds until next check...")
            time.sleep(check_interval)
            
    except KeyboardInterrupt:
        print("\n🛑 Daemon stopped by user.")

if __name__ == "__main__":
    import sys
    
    # Check if daemon mode is requested
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        check_interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        run_daemon(check_interval)
    else:
        # Single run mode
        auto_reply_to_emails() 