import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

def send_email(smtp_host, smtp_user, smtp_pass, to_email, subject, body, port=465, use_ssl=True, in_reply_to=None, references=None):
    msg = EmailMessage()
    subj = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    msg["Subject"] = subj
    msg["From"] = smtp_user
    msg["To"] = to_email

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to

    if references:
        if isinstance(references, str):
            references = [references]
        norm_refs = []
        for r in references:
            if not r:
                continue
            r_stripped = str(r).strip()
            if r_stripped.startswith("<") and r_stripped.endswith(">"):
                norm_refs.append(r_stripped)
            else:
                norm_refs.append(f"<{r_stripped.strip('<>')}>")
        if norm_refs:
            msg["References"] = " ".join(norm_refs)

    msg["Message-ID"] = make_msgid()
    msg.set_content(body)

    if use_ssl:
        with smtplib.SMTP_SSL(smtp_host, port) as smtp:
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, port) as smtp:
            smtp.starttls()  # Enable TLS encryption
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)

    return msg["Message-ID"]
