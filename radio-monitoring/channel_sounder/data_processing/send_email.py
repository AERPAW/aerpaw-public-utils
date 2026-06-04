#!/usr/bin/env python3
import os
import smtplib
from email.mime.text import MIMEText
from email.message import EmailMessage
import argparse
from datetime import date
import pandas as pd
from tabulate import tabulate

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# "aerpaw-operations@ncsu.edu"
sender = os.environ["GMAIL_ADDRESS"]
# the 16 character app password (without spaces)
app_password = os.environ["GMAIL_APP_PW"]

def email_content_gen(content_string, email_text, email_html):
    """
    Append a single plain-text `content_string` to `email_text` and an HTML
    representation to `email_html` and return the updated values.

    Behavior:
    - `content_string` is interpreted as plain text. Newline-separated segments
      are converted to separate HTML paragraphs (<p>...</p>).
    - The plain text is appended to `email_text` (prefixed with a newline
      if needed).
    - HTML is safely escaped and wrapped in <p> tags so it renders correctly
      in HTML email clients.
    """
    import html as _html

    text_part = str(content_string)

    # Append to plain-text body; ensure there's a separating newline
    if not text_part.startswith("\n"):
        email_text = email_text + "\n" + text_part
    else:
        email_text = email_text + text_part

    # Convert newline-separated text into HTML paragraphs, escaping content
    paragraphs = []
    for seg in text_part.split("\n"):
        seg = seg.strip()
        if not seg:
            continue
        paragraphs.append(f"<p>{_html.escape(seg)}</p>")

    email_html = email_html + "".join(paragraphs)
    return email_text, email_html

def read_recipients(recipients_file):
    """
    Read email recipients from a file, one email address per line.
    Empty lines and lines starting with '#' are ignored.
    """
    recipients = []
    with open(recipients_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                recipients.append(line)
    return recipients

def send_email(files, recipients, debug_msg=""):
    date_string = date.today().strftime("%m/%d/%y")
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    subject = f"{date_string} - AERPAW Radio Health Monitoring Report"
    # prepare both plain-text and HTML bodies
    info = f"Please find attached the radio health monitoring report for {date_string}.\n" + debug_msg + "\n"
    email_text, email_html = email_content_gen(info, "", "")

    # Collect attachments first and build the email bodies.
    attachments = []

    # Attach all files
    for filepath in files:
        with open(filepath, "rb") as f:
            data = f.read()
            filename = os.path.basename(filepath)
            if filename.endswith("png"):
                attachments.append(("image", "png", filename, data))
            elif filename.endswith("csv"):
                attachments.append(("text", "csv", filename, data))
                df = pd.read_csv(filepath)

                mask = df["power_deviation"].isin({True})
                alert = mask.any()
                if alert:
                    subject = f"[ALERT] - {subject}"
                    def fmt_cell(x):
                        if isinstance(x, float):
                            return f"{x:.3f}"
                        return x
                    deviation_text = tabulate(
                        df[mask].T.applymap(fmt_cell),
                        headers="keys",
                        tablefmt="github",
                    )
                    deviation_html = tabulate(
                        df[mask].T.applymap(fmt_cell),
                        headers="keys",
                        tablefmt="html",
                    )
                    # build a plain-text representation (table) and append; the helper will
                    # convert newline-separated text into HTML paragraphs for the HTML body
                    alert_text = f"ALERT - Power deviation detected:\n"
                    email_text, email_html = email_content_gen(alert_text, email_text, email_html)
                    email_text += deviation_text + "\n"
                    email_html += f"<p>{deviation_html}</p>"
                else:
                    subject = f"[OK] - {subject}"
                    ok_text = "OK - No power deviation detected.\n"
                    email_text, email_html = email_content_gen(ok_text, email_text, email_html)
            else:
                print(f"Unknown filetype encountered for {filepath}")

    msg["Subject"] = subject
    msg.set_content(email_text)
    email_html = f"""
        <html>
            <body>
            {email_html}
            </body>
        </html>
    """
    msg.add_alternative(email_html, subtype="html")

    # Attach files after setting message body to avoid set_content error
    for maintype, subtype, filename, data in attachments:
        if maintype == "image":
            msg.add_attachment(data, maintype="image", subtype=subtype, filename=filename)
        else:
            # text/csv
            msg.add_attachment(data, maintype="text", subtype=subtype, filename=filename)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(sender, app_password)
        smtp.send_message(msg)

    print(f"Sent email to {msg['To']}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", help="List of files to attach to email")
    parser.add_argument("--debug-msg", type=str, help="Optional debug message", required=False, default="")
    parser.add_argument("--recipients", type=str, help="Path to file containing recipient email addresses (one per line)", required=True)

    args = parser.parse_args()
    recipients = read_recipients(args.recipients)
    send_email(args.files, recipients, args.debug_msg)
