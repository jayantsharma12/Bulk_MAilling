import time
import smtplib
import ssl
import os
import json
import uuid
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from typing import Tuple, List, Dict, Any, Optional

import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────
#  SIGNATURE IMAGE — FILE BASED
#  firstmail.jpg/png/jpeg  → initial emails
#  followup.jpg/png/jpeg   → follow-up emails
#  Place these files in same folder as app.py
# ─────────────────────────────────────────────

def load_signature_from_file(sig_type: str = "firstmail"):
    """
    Load signature image from project folder.
    sig_type: "firstmail" or "followup"
    Looks for: firstmail.jpg, firstmail.png, firstmail.jpeg
               followup.jpg, followup.png, followup.jpeg
    Returns (bytes, filename) or (None, None) if not found.
    """
    for ext in ["jpg", "png", "jpeg"]:
        filename = f"{sig_type}.{ext}"
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                return f.read(), filename
    return None, None


# ─────────────────────────────────────────────
#  FILE HELPERS
# ─────────────────────────────────────────────

def load_recipients_file(uploaded_file) -> Tuple[pd.DataFrame, str]:
    if uploaded_file is None:
        return pd.DataFrame(), "No file uploaded."
    try:
        name = uploaded_file.name.lower()
        if name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded_file)
        elif name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            return pd.DataFrame(), "Unsupported file format."
    except Exception as e:
        return pd.DataFrame(), f"Error reading file: {e}"
    df.columns = [str(c).strip() for c in df.columns]
    if not {"Name", "Email"}.issubset(set(df.columns)):
        return pd.DataFrame(), "File must contain 'Name' and 'Email' columns."
    df = df.dropna(subset=["Email"])
    return df, ""


def load_campaign_db() -> Dict:
    if os.path.exists("campaign_db.json"):
        try:
            with open("campaign_db.json", "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_campaign_db(db: Dict):
    with open("campaign_db.json", "w") as f:
        json.dump(db, f, indent=2, default=str)


def load_total_sent_count() -> int:
    if os.path.exists("total_emails_sent.json"):
        try:
            with open("total_emails_sent.json", "r") as f:
                return json.load(f).get("total_sent", 0)
        except Exception:
            return 0
    return 0


def save_total_sent_count(count: int):
    with open("total_emails_sent.json", "w") as f:
        json.dump({"total_sent": count}, f)


# ─────────────────────────────────────────────
#  EMAIL HELPERS
# ─────────────────────────────────────────────

def render_email_template(template: str, context: Dict[str, Any]) -> Tuple[str, str]:
    try:
        return template.format(**context), ""
    except KeyError as e:
        return "", f"Template error: missing placeholder {{{str(e).strip(chr(39))}}}"
    except Exception as e:
        return "", f"Template rendering error: {e}"


def get_smtp_settings(email_address: str) -> Dict[str, Any]:
    domain = email_address.split("@")[-1].lower() if "@" in email_address else ""
    if "gmail.com" in domain:
        return {"host": "smtp.gmail.com", "port": 465, "use_ssl": True, "use_tls": False}
    elif domain in ["outlook.com", "hotmail.com", "live.com"]:
        return {"host": "smtp-mail.outlook.com", "port": 587, "use_ssl": False, "use_tls": True}
    else:
        return {"host": f"smtp.{domain}" if domain else "smtp.gmail.com", "port": 587, "use_ssl": False, "use_tls": True}


def create_smtp_connection(email_address: str, app_password: str,
                           smtp_host: Optional[str] = None, smtp_port: Optional[int] = None):
    if smtp_host and smtp_port:
        settings = {"host": smtp_host, "port": smtp_port,
                    "use_ssl": smtp_port == 465, "use_tls": smtp_port != 465}
    else:
        settings = get_smtp_settings(email_address)
    ctx = ssl.create_default_context()
    if settings["use_ssl"]:
        server = smtplib.SMTP_SSL(settings["host"], settings["port"], context=ctx)
    else:
        server = smtplib.SMTP(settings["host"], settings["port"])
        if settings["use_tls"]:
            server.starttls(context=ctx)
    server.login(email_address, app_password)
    return server


def apply_smart_delay(sent_count: int):
    if sent_count > 0:
        if sent_count % 100 == 0:
            time.sleep(8.0)
        elif sent_count % 50 == 0:
            time.sleep(5.0)
        elif sent_count % 10 == 0:
            time.sleep(2.5)


def generate_message_id(email_address: str) -> str:
    domain = email_address.split("@")[-1] if "@" in email_address else "mail.local"
    return f"<{uuid.uuid4().hex}@{domain}>"


def generate_thread_index(parent_index: str = None) -> str:
    """
    Generate Microsoft Outlook Thread-Index header.
    
    Outlook threading REQUIRES:
    - Initial mail: 22-byte base64 encoded header
    - Reply: parent bytes + 5 new bytes appended
    
    This is the EXACT Microsoft spec for conversation threading.
    """
    import base64 as _b64, struct as _struct
    
    # Windows FILETIME: 100-nanosecond intervals since Jan 1, 1601
    filetime = int(time.time() * 10_000_000) + 116_444_736_000_000_000
    
    if parent_index is None:
        # Initial email: 6 bytes filetime + 16 bytes random GUID = 22 bytes
        filetime_bytes = _struct.pack("<Q", filetime)[:6]  # little-endian, take 6 bytes
        guid_bytes = uuid.uuid4().bytes  # 16 bytes
        thread_bytes = filetime_bytes + guid_bytes  # 22 bytes total
        return _b64.b64encode(thread_bytes).decode("ascii")
    else:
        # Reply: decode parent + append 5 bytes (filetime delta)
        try:
            # Pad base64 if needed
            pad = len(parent_index) % 4
            if pad:
                parent_index += "=" * (4 - pad)
            parent_bytes = _b64.b64decode(parent_index)
            # 5-byte suffix: lower 5 bytes of current filetime
            suffix = _struct.pack("<Q", filetime)[:5]
            child_bytes = parent_bytes + suffix
            return _b64.b64encode(child_bytes).decode("ascii")
        except Exception:
            # Fallback: generate fresh
            filetime_bytes = _struct.pack("<Q", filetime)[:6]
            guid_bytes = uuid.uuid4().bytes
            return _b64.b64encode(filetime_bytes + guid_bytes).decode("ascii")



def build_message(from_addr, to_addr, subject, body,
                  msg_id, in_reply_to=None, references=None,
                  thread_index=None,
                  pdf_file=None, pdf_filename=None,
                  image_file=None, image_filename=None,
                  signature_image=None, signature_filename=None):
    """Build a MIME email message with optional attachments and signature."""
    msg = MIMEMultipart("related")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Message-ID"] = msg_id
    msg["X-Mailer"] = "Microsoft Outlook 16.0"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
        # Outlook threading: Thread-Index child entry
        child_ti = generate_thread_index(thread_index)
        msg["Thread-Index"] = child_ti
        # Strip all Re:/RE:/re: prefixes for Thread-Topic
        clean_subject = subject
        for prefix in ["Re: ", "RE: ", "re: ", "Re:", "RE:", "re:"]:
            while clean_subject.startswith(prefix):
                clean_subject = clean_subject[len(prefix):].strip()
        msg["Thread-Topic"] = clean_subject
    else:
        # Initial email: new Thread-Index
        msg["Thread-Index"] = generate_thread_index()
        msg["Thread-Topic"] = subject

    if signature_image and signature_filename:
        ext = signature_filename.rsplit(".", 1)[-1].lower()
        mime_sub = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif"}.get(ext, "jpeg")
        html_body = (
            '<html><body style="margin:0;padding:0;">'
            f'<div style="font-family:Calibri,Arial,sans-serif;font-size:14px;line-height:1.6;padding:16px 0;">'
            f'{body.replace(chr(10), "<br/>")}</div>'
            '<div style="width:100%;margin:0;padding:0;display:block;">'
            '<img src="cid:signature_image" '
            'style="width:100%;max-width:100%;display:block;margin:0;padding:0;border:none;" '
            'alt="Signature"/>'
            '</div>'
            "</body></html>"
        )
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body, "plain"))
        alt.attach(MIMEText(html_body, "html"))
        msg.attach(alt)
        sig_part = MIMEImage(signature_image, _subtype=mime_sub)
        sig_part.add_header("Content-Disposition", f'inline; filename="{signature_filename}"')
        sig_part.add_header("Content-ID", "<signature_image>")
        sig_part.add_header("X-Attachment-Id", "signature_image")
        msg.attach(sig_part)
    else:
        msg.attach(MIMEText(body, "plain"))

    if pdf_file and pdf_filename:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(pdf_file)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{pdf_filename}"')
        msg.attach(part)

    if image_file and image_filename:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(image_file)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'inline; filename="{image_filename}"')
        part.add_header("Content-ID", f"<{image_filename}>")
        msg.attach(part)

    return msg


# ─────────────────────────────────────────────
#  SEND FUNCTIONS
# ─────────────────────────────────────────────

def send_bulk_emails(df, campaign_name, email_address, app_password,
                     subject_template, body_template, progress_slot, status_slot,
                     pdf_file=None, pdf_filename=None, image_file=None, image_filename=None,
                     signature_image=None, signature_filename=None,
                     smtp_host=None, smtp_port=None):

    total = len(df)
    if total == 0:
        return 0, 0, []

    db = load_campaign_db()
    if campaign_name in db:
        st.warning(f"Campaign '{campaign_name}' already exists!")
        return 0, 0, []

    results, sent_count, failed_count = [], 0, 0
    progress_bar = progress_slot.progress(0)
    progress_text = progress_slot.empty()
    log_lines = []

    try:
        server = create_smtp_connection(email_address, app_password, smtp_host, smtp_port)
    except Exception as e:
        raise RuntimeError(f"SMTP authentication failed: {e}")

    campaign_recipients = {}
    try:
        for i, (idx, row) in enumerate(df.iterrows()):
            name = str(row.get("Name", "")).strip()
            recipient_email = str(row.get("Email", "")).strip()
            context = {col: row[col] for col in df.columns}
            context.setdefault("Name", name)
            context.setdefault("Email", recipient_email)

            subject, err = render_email_template(subject_template, context)
            if err:
                results.append({"Name": name, "Email": recipient_email, "Status": "Failed", "Message": err})
                failed_count += 1
                continue

            body, err = render_email_template(body_template, context)
            if err:
                results.append({"Name": name, "Email": recipient_email, "Status": "Failed", "Message": err})
                failed_count += 1
                continue

            msg_id = generate_message_id(email_address)
            message = build_message(
                email_address, recipient_email, subject, body, msg_id,
                pdf_file=pdf_file, pdf_filename=pdf_filename,
                image_file=image_file, image_filename=image_filename,
                signature_image=signature_image, signature_filename=signature_filename
            )

            try:
                server.sendmail(email_address, recipient_email, message.as_string())
                sent_count += 1
                status, msg = "Sent", "Initial email sent."
                campaign_recipients[recipient_email] = {
                    "name": name, "message_id": msg_id, "subject": subject,
                    "thread_index": message["Thread-Index"] if "Thread-Index" in message else "",
                    "followups_sent": 0,
                    "last_sent_date": datetime.now().isoformat(),
                    "next_followup_date": (datetime.now() + timedelta(days=3)).isoformat(),
                }
            except Exception as e:
                status, msg = "Failed", f"SMTP error: {e}"
                failed_count += 1

            results.append({"Name": name, "Email": recipient_email, "Status": status, "Message": msg})
            log_lines.append(f"[{status}] {name} <{recipient_email}> - {msg}")
            status_slot.text("\n".join(log_lines[-200:]))
            progress_bar.progress(int(((i + 1) / total) * 100))
            progress_text.text(f"Processing {i + 1} of {total} emails...")
            apply_smart_delay(sent_count)
    finally:
        try:
            server.quit()
        except Exception:
            pass

    db[campaign_name] = {
        "created_at": datetime.now().isoformat(),
        "sender_email": email_address,
        "subject_template": subject_template,
        "body_template": body_template,
        "total_followups_planned": 5,
        "followup_interval_days": 3,
        "recipients": campaign_recipients,
    }
    save_campaign_db(db)
    return sent_count, failed_count, results


def send_followup_emails(campaign_name, email_address, app_password,
                         followup_subject_template, followup_body_template,
                         progress_slot, status_slot,
                         pdf_file=None, pdf_filename=None,
                         image_file=None, image_filename=None,
                         signature_image=None, signature_filename=None,
                         smtp_host=None, smtp_port=None,
                         force_send_now=False):

    db = load_campaign_db()
    if campaign_name not in db:
        raise RuntimeError(f"Campaign '{campaign_name}' not found!")

    campaign = db[campaign_name]
    recipients = campaign["recipients"]
    max_followups = campaign.get("total_followups_planned", 5)
    interval_days = campaign.get("followup_interval_days", 3)
    now = datetime.now()

    due_recipients = {
        email: data for email, data in recipients.items()
        if data["followups_sent"] < max_followups
        and (force_send_now or datetime.fromisoformat(data["next_followup_date"]) <= now)
    }

    if not due_recipients:
        st.info("No recipients due for follow-up right now!")
        return 0, 0, []

    total = len(due_recipients)
    results, sent_count, failed_count = [], 0, 0
    progress_bar = progress_slot.progress(0)
    progress_text = progress_slot.empty()
    log_lines = []

    try:
        server = create_smtp_connection(email_address, app_password, smtp_host, smtp_port)
    except Exception as e:
        raise RuntimeError(f"SMTP authentication failed: {e}")

    try:
        for i, (recipient_email, data) in enumerate(due_recipients.items()):
            name = data["name"]
            original_msg_id = data["message_id"]
            original_subject = data["subject"]
            followup_num = data["followups_sent"] + 1

            context = {"Name": name, "Email": recipient_email, "followup_num": followup_num}
            subject, err = render_email_template(followup_subject_template, context)
            if err:
                subject = f"Re: {original_subject}"

            body, err = render_email_template(followup_body_template, context)
            if err:
                results.append({"Name": name, "Email": recipient_email, "Status": "Failed", "Message": err})
                failed_count += 1
                continue

            new_msg_id = generate_message_id(email_address)
            original_thread_index = data.get("thread_index", "")
            message = build_message(
                email_address, recipient_email,
                f"Re: {original_subject}", body, new_msg_id,
                in_reply_to=original_msg_id, references=original_msg_id,
                thread_index=original_thread_index,
                pdf_file=pdf_file, pdf_filename=pdf_filename,
                image_file=image_file, image_filename=image_filename,
                signature_image=signature_image, signature_filename=signature_filename
            )

            try:
                server.sendmail(email_address, recipient_email, message.as_string())
                sent_count += 1
                status, msg = "Sent", f"Follow-up #{followup_num} sent."
                recipients[recipient_email]["followups_sent"] = followup_num
                recipients[recipient_email]["message_id"] = new_msg_id
                recipients[recipient_email]["thread_index"] = message["Thread-Index"] if "Thread-Index" in message else original_thread_index
                recipients[recipient_email]["last_sent_date"] = now.isoformat()
                recipients[recipient_email]["next_followup_date"] = (now + timedelta(days=interval_days)).isoformat()
            except Exception as e:
                status, msg = "Failed", f"SMTP error: {e}"
                failed_count += 1

            results.append({"Name": name, "Email": recipient_email, "Status": status, "Message": msg, "Follow-up #": followup_num})
            log_lines.append(f"[{status}] FU#{followup_num} → {name} <{recipient_email}>")
            status_slot.text("\n".join(log_lines[-200:]))
            progress_bar.progress(int(((i + 1) / total) * 100))
            progress_text.text(f"Processing {i + 1} of {total}...")
            apply_smart_delay(sent_count)
    finally:
        try:
            server.quit()
        except Exception:
            pass

    db[campaign_name]["recipients"] = recipients
    save_campaign_db(db)
    return sent_count, failed_count, results


# ─────────────────────────────────────────────
#  SHARED ATTACHMENT UI
# ─────────────────────────────────────────────

def render_attachment_ui(key_prefix: str, sig_type: str = "firstmail"):
    """
    Render PDF and image uploaders.
    Signature auto-loaded from: firstmail.jpg/png/jpeg or followup.jpg/png/jpeg
    sig_type: "firstmail" for initial emails, "followup" for follow-up emails
    """
    col_a, col_b = st.columns(2)
    with col_a:
        pdf_up = st.file_uploader("Upload PDF", type=["pdf"], key=f"{key_prefix}_pdf")
    with col_b:
        img_up = st.file_uploader("Upload Image", type=["png","jpg","jpeg","gif"], key=f"{key_prefix}_img")

    # Auto-load signature from file
    sig_data, sig_name = load_signature_from_file(sig_type)
    if sig_data:
        st.success(f"✅ Signature auto-loaded: **{sig_name}** (full width, email ke end mein)")
    else:
        st.warning(f"⚠️ Signature file nahi mili! Project folder mein **{sig_type}.jpg** ya **{sig_type}.png** rakho.")

    return (
        pdf_up.read() if pdf_up else None,
        pdf_up.name if pdf_up else None,
        img_up.read() if img_up else None,
        img_up.name if img_up else None,
        sig_data,
        sig_name,
    )


# ─────────────────────────────────────────────
#  MAIN APP
# ─────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Indsource — Bulk Email Sender",
        page_icon="📨",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # ── Custom CSS ──────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Serif+Display:ital@0;1&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    /* Hide default streamlit elements */
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.5rem !important; max-width: 1100px; }

    /* Hide sidebar and ALL its controls completely */
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    [data-testid="stSidebarCollapseButton"] { display: none !important; }
    section[data-testid="stSidebar"] { display: none !important; }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: #0f0f0f;
        border-right: 1px solid #222;
    }
    [data-testid="stSidebar"] * { color: #e8e8e8 !important; }
    [data-testid="stSidebar"] .stMetric {
        background: #1a1a1a;
        border: 1px solid #2a2a2a;
        border-radius: 8px;
        padding: 12px 16px;
    }
    [data-testid="stSidebar"] [data-testid="stMetricValue"] {
        font-family: 'DM Serif Display', serif;
        font-size: 2rem !important;
        color: #c8a97e !important;
    }

    /* ── Page Header ── */
    .app-header {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 24px 0 8px 0;
        border-bottom: 2px solid #8B1A1A;
        margin-bottom: 28px;
    }
    .app-header h1 {
        font-family: 'DM Serif Display', serif;
        font-size: 2.1rem;
        color: #1a1a1a;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .app-header .tagline {
        font-size: 0.85rem;
        color: #888;
        margin: 0;
        font-weight: 400;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 2px solid #e5e5e5;
        background: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.85rem;
        font-weight: 500;
        color: #888 !important;
        padding: 10px 22px;
        border: none;
        border-bottom: 2px solid transparent;
        margin-bottom: -2px;
        background: transparent;
        letter-spacing: 0.3px;
        text-transform: uppercase;
    }
    .stTabs [aria-selected="true"] {
        color: #8B1A1A !important;
        border-bottom: 2px solid #8B1A1A !important;
        background: transparent !important;
    }

    /* ── Section Labels ── */
    .section-label {
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        color: #8B1A1A;
        margin-bottom: 8px;
        margin-top: 24px;
        display: block;
    }

    /* ── Cards ── */
    .info-card {
        background: #fafafa;
        border: 1px solid #ebebeb;
        border-left: 3px solid #8B1A1A;
        border-radius: 6px;
        padding: 14px 18px;
        margin: 12px 0;
        font-size: 0.88rem;
        color: #444;
    }
    .stat-card {
        background: #fff;
        border: 1px solid #e8e8e8;
        border-radius: 8px;
        padding: 16px 20px;
        text-align: center;
    }
    .stat-card .stat-num {
        font-family: 'DM Serif Display', serif;
        font-size: 2rem;
        color: #8B1A1A;
        line-height: 1;
    }
    .stat-card .stat-label {
        font-size: 0.75rem;
        color: #999;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-top: 4px;
    }

    /* ── Inputs ── */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div {
        border: 1px solid #ddd !important;
        border-radius: 6px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.9rem !important;
        background: #fff !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #8B1A1A !important;
        box-shadow: 0 0 0 2px rgba(139,26,26,0.08) !important;
    }

    /* ── Buttons ── */
    .stButton > button[kind="primary"] {
        background: #8B1A1A !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 500 !important;
        font-size: 0.88rem !important;
        padding: 10px 28px !important;
        letter-spacing: 0.3px !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: #6d1414 !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(139,26,26,0.25) !important;
    }
    .stButton > button[kind="secondary"] {
        background: transparent !important;
        color: #8B1A1A !important;
        border: 1.5px solid #8B1A1A !important;
        border-radius: 6px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 500 !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background: #8B1A1A !important;
        color: white !important;
    }
    .stButton > button:disabled {
        opacity: 0.4 !important;
        cursor: not-allowed !important;
        transform: none !important;
    }

    /* ── File Uploader ── */
    .stFileUploader > div {
        border: 1.5px dashed #ddd !important;
        border-radius: 8px !important;
        background: #fafafa !important;
    }
    .stFileUploader > div:hover {
        border-color: #8B1A1A !important;
        background: #fff8f8 !important;
    }

    /* ── Alerts ── */
    .stSuccess > div {
        background: #f0fff4 !important;
        border-left: 3px solid #22c55e !important;
        border-radius: 6px !important;
    }
    .stWarning > div {
        background: #fffbeb !important;
        border-left: 3px solid #f59e0b !important;
        border-radius: 6px !important;
    }
    .stInfo > div {
        background: #f0f9ff !important;
        border-left: 3px solid #0ea5e9 !important;
        border-radius: 6px !important;
    }
    .stError > div {
        background: #fff1f2 !important;
        border-left: 3px solid #ef4444 !important;
        border-radius: 6px !important;
    }

    /* ── Divider ── */
    hr { border: none; border-top: 1px solid #ebebeb; margin: 20px 0; }

    /* ── DataFrame ── */
    .stDataFrame { border-radius: 8px; overflow: hidden; border: 1px solid #e8e8e8; }

    /* ── Expander ── */
    .streamlit-expanderHeader {
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        color: #555 !important;
        background: #fafafa !important;
        border-radius: 6px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Top Info Bar (replaces sidebar) ───────────────────────────────────
    total_sent_all_time = load_total_sent_count()
    db_sidebar = load_campaign_db()

    # Build campaign summary text
    campaign_summary = ""
    if db_sidebar:
        parts = []
        for cname, cdata in db_sidebar.items():
            recs = cdata.get("recipients", {})
            due = sum(1 for r in recs.values()
                      if r["followups_sent"] < cdata.get("total_followups_planned", 5)
                      and datetime.fromisoformat(r["next_followup_date"]) <= datetime.now())
            parts.append(f"<b>{cname}</b>: {len(recs)} recipients" + (f", <span style='color:#c8a97e;'>{due} due</span>" if due > 0 else ""))
        campaign_summary = " &nbsp;|&nbsp; ".join(parts)

    st.markdown(f"""
    <div style="background:#0f0f0f;border-radius:10px;padding:14px 24px;margin-bottom:20px;
                display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
        <div style="display:flex;align-items:center;gap:20px;">
            <div>
                <span style="font-family:'DM Serif Display',serif;font-size:1.3rem;color:#c8a97e;">Inds<span style="color:#8B1A1A;">•</span>urce</span>
                <span style="font-size:0.65rem;letter-spacing:2px;color:#555;text-transform:uppercase;margin-left:10px;">Bulk Email Sender</span>
            </div>
            <div style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;padding:6px 16px;text-align:center;">
                <div style="font-family:'DM Serif Display',serif;font-size:1.4rem;color:#c8a97e;line-height:1;">{total_sent_all_time}</div>
                <div style="font-size:0.62rem;color:#555;letter-spacing:1px;text-transform:uppercase;">Total Sent</div>
            </div>
        </div>
        <div style="font-size:0.78rem;color:#888;">
            {"&nbsp;&nbsp;" + campaign_summary if campaign_summary else "<span style='color:#444;'>No campaigns yet</span>"}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Page Header ─────────────────────────────────────────────────────────
    st.markdown("""
    <div class="app-header">
        <div>
            <h1>📨 Bulk Email Sender</h1>
            <p class="tagline">Personalized campaigns with follow-up threading · Indsource International</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 4 TABS ───────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "NEW CAMPAIGN",
        "SEND FOLLOW-UPS",
        "⚡ FORCE SEND",
        "CAMPAIGN STATUS",
    ])

    # ════════════════════════════════════════════════════════════════════
    #  TAB 1 — NEW CAMPAIGN
    # ════════════════════════════════════════════════════════════════════
    with tab1:
        col_main, col_side = st.columns([2, 1], gap="large")

        with col_main:
            st.markdown('<span class="section-label">Campaign Identity</span>', unsafe_allow_html=True)
            campaign_name = st.text_input("Campaign Name", placeholder="e.g., HighPoint_April2026",
                                          key="t1_campaign", label_visibility="collapsed")
            if not campaign_name:
                st.markdown('<div class="info-card">Give this campaign a unique name — it will be used to track follow-ups.</div>', unsafe_allow_html=True)

            st.markdown('<span class="section-label">Recipients</span>', unsafe_allow_html=True)
            uploaded_file = st.file_uploader("Upload CSV or Excel",
                                             type=["csv", "xlsx", "xls"], key="t1_recipients",
                                             label_visibility="collapsed")
            df, file_error = load_recipients_file(uploaded_file) if uploaded_file else (pd.DataFrame(), "")
            if file_error:
                st.error(file_error)
            elif not df.empty:
                st.success(f"✅ {len(df)} recipients loaded successfully")
                with st.expander("Preview recipients"):
                    st.dataframe(df.head(10), use_container_width=True, hide_index=True)
            else:
                st.markdown('<div class="info-card">Upload a CSV or Excel file with <b>Name</b> and <b>Email</b> columns. Additional columns can be used as template placeholders.</div>', unsafe_allow_html=True)

            st.markdown('<span class="section-label">Email Template</span>', unsafe_allow_html=True)
            st.caption("Use `{Name}`, `{Email}`, or any column name as placeholder")
            t1_subject = st.text_input("Subject", value="Meeting at April High Point 2026 - {Company}",
                                       key="t1_subject")
            t1_body = st.text_area("Body", height=220, key="t1_body", value=(
                "Dear {Name},\n\n"
                "We are excited to invite you to our meeting at April High Point 2026.\n\n"
                "Please find the attached documents for your reference.\n\n"
                "Best regards,\nYour Team"
            ))

            st.markdown('<span class="section-label">Attachments</span>', unsafe_allow_html=True)
            col_att1, col_att2 = st.columns(2)
            with col_att1:
                st.caption("PDF Document")
                pdf_up = st.file_uploader("PDF", type=["pdf"], key="t1_pdf", label_visibility="collapsed")
            with col_att2:
                st.caption("Inline Image")
                img_up = st.file_uploader("Image", type=["png","jpg","jpeg","gif"], key="t1_img", label_visibility="collapsed")

            # Signature status
            sig_data, sig_name = load_signature_from_file("firstmail")
            if sig_data:
                st.markdown(f'<div class="info-card" style="border-left-color:#22c55e;">📌 Signature auto-loaded: <b>{sig_name}</b> — will appear at the very end of email</div>', unsafe_allow_html=True)
            else:
                st.warning("⚠️ No signature found. Place `firstmail.jpg` or `firstmail.png` in project folder.")

        with col_side:
            st.markdown('<span class="section-label">Credentials</span>', unsafe_allow_html=True)
            t1_email = st.text_input("Email Address", placeholder="info@indsource.net", key="t1_email")
            t1_pass = st.text_input("Password", type="password", key="t1_pass")

            with st.expander("⚙️ SMTP Settings"):
                t1_smtp_host = st.text_input("SMTP Host", key="t1_smtp_host", placeholder="mail.indsource.net")
                t1_smtp_port = st.number_input("Port", min_value=25, max_value=9999, value=587, step=1, key="t1_smtp_port")

            st.markdown('<span class="section-label">Schedule</span>', unsafe_allow_html=True)
            st.markdown("""
            <div style="background:#fafafa;border:1px solid #e8e8e8;border-radius:8px;padding:16px;font-size:0.82rem;color:#555;line-height:1.8;">
                After sending, follow-ups are<br>scheduled automatically:<br><br>
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                    <span style="color:#8B1A1A;font-weight:600;">5</span> follow-up emails
                </div>
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                    <span style="color:#8B1A1A;font-weight:600;">3</span> days interval
                </div>
                <div style="display:flex;align-items:center;gap:8px;">
                    <span style="color:#8B1A1A;font-weight:600;">📧</span> same thread
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            can_send = (campaign_name.strip() and uploaded_file and not df.empty
                        and t1_email.strip() and t1_pass.strip()
                        and t1_subject.strip() and t1_body.strip())

            if st.button("🚀 Launch Campaign", type="primary", disabled=not can_send,
                         key="t1_send", use_container_width=True):
                smtp_h = t1_smtp_host.strip() or None
                smtp_p = int(t1_smtp_port) if smtp_h else None
                prog = st.empty()
                stat = st.empty()
                with st.spinner("Sending emails..."):
                    try:
                        sent, failed, results = send_bulk_emails(
                            df=df, campaign_name=campaign_name.strip(),
                            email_address=t1_email.strip(), app_password=t1_pass.strip(),
                            subject_template=t1_subject.strip(), body_template=t1_body,
                            progress_slot=prog, status_slot=stat,
                            pdf_file=pdf_up.read() if pdf_up else None,
                            pdf_filename=pdf_up.name if pdf_up else None,
                            image_file=img_up.read() if img_up else None,
                            image_filename=img_up.name if img_up else None,
                            signature_image=sig_data, signature_filename=sig_name,
                            smtp_host=smtp_h, smtp_port=smtp_p,
                        )
                    except RuntimeError as e:
                        st.error(str(e))
                        sent, failed, results = 0, 0, []

                if sent > 0:
                    save_total_sent_count(load_total_sent_count() + sent)

                st.markdown(f"""
                <div style="background:#f0fff4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin-top:12px;">
                    <div style="font-size:1rem;font-weight:600;color:#166534;margin-bottom:8px;">✅ Campaign Launched!</div>
                    <div style="font-size:0.85rem;color:#166534;">
                        Sent: <b>{sent}</b> &nbsp;·&nbsp; Failed: <b>{failed}</b><br>
                        Follow-ups scheduled every 3 days
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if results:
                    with st.expander("View send results"):
                        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

    # ════════════════════════════════════════════════════════════════════
    #  TAB 2 — SEND FOLLOW-UPS
    # ════════════════════════════════════════════════════════════════════
    with tab2:
        db2 = load_campaign_db()
        if not db2:
            st.markdown('<div class="info-card">No campaigns found. Launch a campaign first from the <b>New Campaign</b> tab.</div>', unsafe_allow_html=True)
        else:
            col_main2, col_side2 = st.columns([2, 1], gap="large")
            with col_main2:
                st.markdown('<span class="section-label">Select Campaign</span>', unsafe_allow_html=True)
                t2_campaign = st.selectbox("Campaign", list(db2.keys()), key="t2_campaign",
                                           label_visibility="collapsed")
                if t2_campaign:
                    cdata2 = db2[t2_campaign]
                    recs2 = cdata2["recipients"]
                    max_fu2 = cdata2.get("total_followups_planned", 5)
                    interval2 = cdata2.get("followup_interval_days", 3)
                    now2 = datetime.now()

                    due2 = [e for e, r in recs2.items() if r["followups_sent"] < max_fu2
                            and datetime.fromisoformat(r["next_followup_date"]) <= now2]
                    pending2 = [e for e, r in recs2.items() if r["followups_sent"] < max_fu2
                                and datetime.fromisoformat(r["next_followup_date"]) > now2]
                    completed2 = [e for e, r in recs2.items() if r["followups_sent"] >= max_fu2]

                    # Stats row
                    s1, s2, s3 = st.columns(3)
                    with s1:
                        st.markdown(f'<div class="stat-card"><div class="stat-num">{len(due2)}</div><div class="stat-label">Due Now</div></div>', unsafe_allow_html=True)
                    with s2:
                        st.markdown(f'<div class="stat-card"><div class="stat-num">{len(pending2)}</div><div class="stat-label">Pending</div></div>', unsafe_allow_html=True)
                    with s3:
                        st.markdown(f'<div class="stat-card"><div class="stat-num">{len(completed2)}</div><div class="stat-label">Completed</div></div>', unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)

                    if due2:
                        st.success(f"📬 {len(due2)} recipients ready for Follow-up #{recs2[due2[0]]['followups_sent']+1}")
                    elif pending2:
                        nxt = min(datetime.fromisoformat(recs2[e]["next_followup_date"]) for e in pending2)
                        st.info(f"⏰ Next batch due: **{nxt.strftime('%d %b %Y, %I:%M %p')}**")

                    st.markdown('<span class="section-label">Follow-up Template</span>', unsafe_allow_html=True)
                    st.caption("Placeholders: `{Name}`, `{Email}`, `{followup_num}` · Leave subject blank to auto-use original subject")
                    t2_subject = st.text_input("Subject", value="", placeholder="Leave blank to use original subject (recommended)",
                                               key="t2_subject")
                    t2_body = st.text_area("Body", height=200, key="t2_body", value=(
                        "Dear {Name},\n\n"
                        "I wanted to follow up on my previous email.\n\n"
                        "Please let me know if you have any questions.\n\n"
                        "Best regards,\nYour Team"
                    ))

                    st.markdown('<span class="section-label">Attachments</span>', unsafe_allow_html=True)
                    col_att3, col_att4 = st.columns(2)
                    with col_att3:
                        st.caption("PDF")
                        t2_pdf = st.file_uploader("PDF", type=["pdf"], key="t2_pdf", label_visibility="collapsed")
                    with col_att4:
                        st.caption("Inline Image")
                        t2_img = st.file_uploader("Image", type=["png","jpg","jpeg","gif"], key="t2_img", label_visibility="collapsed")

                    sig2, sig2_name = load_signature_from_file("followup")
                    if sig2:
                        st.markdown(f'<div class="info-card" style="border-left-color:#22c55e;">📌 Follow-up signature: <b>{sig2_name}</b></div>', unsafe_allow_html=True)
                    else:
                        st.warning("Place `followup.jpg` or `followup.png` in project folder for signature.")

            with col_side2:
                st.markdown('<span class="section-label">Credentials</span>', unsafe_allow_html=True)
                t2_email = st.text_input("Email", value=db2[t2_campaign].get("sender_email","") if t2_campaign else "", key="t2_email")
                t2_pass = st.text_input("Password", type="password", key="t2_pass")
                with st.expander("⚙️ SMTP Settings"):
                    t2_smtp_host = st.text_input("SMTP Host", key="t2_smtp_host")
                    t2_smtp_port = st.number_input("Port", min_value=25, max_value=9999, value=587, key="t2_smtp_port")

                st.markdown("<br>", unsafe_allow_html=True)
                can_t2 = t2_email.strip() and t2_pass.strip() and len(due2) > 0 if t2_campaign else False
                if st.button(f"🔁 Send Follow-ups ({len(due2) if t2_campaign else 0} due)",
                             type="primary", disabled=not can_t2, key="t2_send", use_container_width=True):
                    smtp_h2 = t2_smtp_host.strip() or None
                    smtp_p2 = int(t2_smtp_port) if smtp_h2 else None
                    subj2 = t2_subject.strip() if t2_subject.strip() else "Re: {Name}"
                    prog2, stat2 = st.empty(), st.empty()
                    with st.spinner("Sending follow-ups..."):
                        try:
                            sent2, failed2, res2 = send_followup_emails(
                                t2_campaign, t2_email.strip(), t2_pass.strip(),
                                subj2, t2_body, prog2, stat2,
                                pdf_file=t2_pdf.read() if t2_pdf else None,
                                pdf_filename=t2_pdf.name if t2_pdf else None,
                                image_file=t2_img.read() if t2_img else None,
                                image_filename=t2_img.name if t2_img else None,
                                signature_image=sig2, signature_filename=sig2_name,
                                smtp_host=smtp_h2, smtp_port=smtp_p2, force_send_now=False,
                            )
                        except RuntimeError as e:
                            st.error(str(e))
                            sent2, failed2, res2 = 0, 0, []
                    if sent2 > 0:
                        save_total_sent_count(load_total_sent_count() + sent2)
                    st.success(f"✅ Sent: {sent2} · Failed: {failed2}")
                    if res2:
                        with st.expander("Results"):
                            st.dataframe(pd.DataFrame(res2), use_container_width=True, hide_index=True)

    # ════════════════════════════════════════════════════════════════════
    #  TAB 3 — FORCE SEND NOW
    # ════════════════════════════════════════════════════════════════════
    with tab3:
        db3 = load_campaign_db()
        if not db3:
            st.markdown('<div class="info-card">No campaigns found. Launch a campaign first.</div>', unsafe_allow_html=True)
        else:
            col_main3, col_side3 = st.columns([2, 1], gap="large")
            with col_main3:
                st.markdown('<span class="section-label">Select Campaign</span>', unsafe_allow_html=True)
                t3_campaign = st.selectbox("Campaign", list(db3.keys()), key="t3_campaign",
                                           label_visibility="collapsed")
                if t3_campaign:
                    cdata3 = db3[t3_campaign]
                    recs3 = cdata3["recipients"]
                    fc_max3 = cdata3.get("total_followups_planned", 5)

                    all_pending3 = {e: r for e, r in recs3.items() if r["followups_sent"] < fc_max3}
                    completed3 = [e for e, r in recs3.items() if r["followups_sent"] >= fc_max3]

                    s1, s2 = st.columns(2)
                    with s1:
                        st.markdown(f'<div class="stat-card"><div class="stat-num">{len(all_pending3)}</div><div class="stat-label">Pending</div></div>', unsafe_allow_html=True)
                    with s2:
                        st.markdown(f'<div class="stat-card"><div class="stat-num">{len(completed3)}</div><div class="stat-label">Completed</div></div>', unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)

                    if not all_pending3:
                        st.success("🎉 All follow-ups complete for this campaign!")
                    else:
                        next_num3 = list(all_pending3.values())[0]["followups_sent"] + 1
                        st.markdown(f'<div class="info-card" style="border-left-color:#f59e0b;">⚡ Will send <b>Follow-up #{next_num3}</b> to <b>{len(all_pending3)} recipients</b> immediately — ignoring the 3-day schedule.</div>', unsafe_allow_html=True)

                        st.markdown('<span class="section-label">Follow-up Template</span>', unsafe_allow_html=True)
                        st.caption("Leave subject blank to use original subject")
                        t3_subject = st.text_input("Subject", value="", placeholder="Leave blank (recommended)",
                                                   key="t3_subject")
                        t3_body = st.text_area("Body", height=200, key="t3_body", value=(
                            "Dear {Name},\n\n"
                            "I wanted to follow up on my previous email.\n\n"
                            "Please let me know if you have any questions.\n\n"
                            "Best regards,\nYour Team"
                        ))

                        st.markdown('<span class="section-label">Attachments</span>', unsafe_allow_html=True)
                        col_att5, col_att6 = st.columns(2)
                        with col_att5:
                            st.caption("PDF")
                            t3_pdf = st.file_uploader("PDF", type=["pdf"], key="t3_pdf", label_visibility="collapsed")
                        with col_att6:
                            st.caption("Inline Image")
                            t3_img = st.file_uploader("Image", type=["png","jpg","jpeg","gif"], key="t3_img", label_visibility="collapsed")

                        sig3, sig3_name = load_signature_from_file("followup")
                        if sig3:
                            st.markdown(f'<div class="info-card" style="border-left-color:#22c55e;">📌 Signature: <b>{sig3_name}</b></div>', unsafe_allow_html=True)

            with col_side3:
                if t3_campaign and all_pending3:
                    st.markdown('<span class="section-label">Credentials</span>', unsafe_allow_html=True)
                    t3_email = st.text_input("Email", value=db3[t3_campaign].get("sender_email",""), key="t3_email")
                    t3_pass = st.text_input("Password", type="password", key="t3_pass")
                    with st.expander("⚙️ SMTP Settings"):
                        t3_smtp_host = st.text_input("SMTP Host", key="t3_smtp_host")
                        t3_smtp_port = st.number_input("Port", min_value=25, max_value=9999, value=587, key="t3_smtp_port")

                    st.markdown("<br>", unsafe_allow_html=True)
                    can_t3 = t3_email.strip() and t3_pass.strip()
                    if st.button(f"⚡ Force Send to {len(all_pending3)}",
                                 type="primary", disabled=not can_t3, key="t3_send", use_container_width=True):
                        smtp_h3 = t3_smtp_host.strip() or None
                        smtp_p3 = int(t3_smtp_port) if smtp_h3 else None
                        subj3 = t3_subject.strip() if t3_subject.strip() else "Re: {Name}"
                        prog3, stat3 = st.empty(), st.empty()
                        with st.spinner(f"Force sending to {len(all_pending3)} recipients..."):
                            try:
                                sent3, failed3, res3 = send_followup_emails(
                                    t3_campaign, t3_email.strip(), t3_pass.strip(),
                                    subj3, t3_body, prog3, stat3,
                                    pdf_file=t3_pdf.read() if t3_pdf else None,
                                    pdf_filename=t3_pdf.name if t3_pdf else None,
                                    image_file=t3_img.read() if t3_img else None,
                                    image_filename=t3_img.name if t3_img else None,
                                    signature_image=sig3, signature_filename=sig3_name,
                                    smtp_host=smtp_h3, smtp_port=smtp_p3, force_send_now=True,
                                )
                            except RuntimeError as e:
                                st.error(str(e))
                                sent3, failed3, res3 = 0, 0, []
                        if sent3 > 0:
                            save_total_sent_count(load_total_sent_count() + sent3)
                        st.success(f"✅ Sent: {sent3} · Failed: {failed3}")
                        if res3:
                            with st.expander("Results"):
                                st.dataframe(pd.DataFrame(res3), use_container_width=True, hide_index=True)

    # ════════════════════════════════════════════════════════════════════
    #  TAB 4 — CAMPAIGN STATUS
    # ════════════════════════════════════════════════════════════════════
    with tab4:
        db4 = load_campaign_db()
        if not db4:
            st.markdown('<div class="info-card">No campaigns yet. Launch one from <b>New Campaign</b>.</div>', unsafe_allow_html=True)
        else:
            for cname, cdata in db4.items():
                recs4 = cdata["recipients"]
                now4 = datetime.now()
                total4 = len(recs4)
                done4 = sum(1 for r in recs4.values() if r["followups_sent"] >= cdata.get("total_followups_planned", 5))
                due4 = sum(1 for r in recs4.values()
                           if r["followups_sent"] < cdata.get("total_followups_planned", 5)
                           and datetime.fromisoformat(r["next_followup_date"]) <= now4)

                with st.expander(f"📁 {cname}   ·   {total4} recipients   ·   {done4} completed   ·   {due4} due now"):
                    rows4 = []
                    for email, r in recs4.items():
                        nxt = datetime.fromisoformat(r["next_followup_date"])
                        s = ("✅ Completed" if r["followups_sent"] >= cdata.get("total_followups_planned", 5)
                             else ("🔴 Due Now" if nxt <= now4 else f"⏳ {nxt.strftime('%d %b %Y')}"))
                        rows4.append({
                            "Name": r["name"],
                            "Email": email,
                            "Follow-ups Sent": f"{r['followups_sent']} / {cdata.get('total_followups_planned',5)}",
                            "Status": s
                        })
                    st.dataframe(pd.DataFrame(rows4), use_container_width=True, hide_index=True)

            st.markdown("---")
            col_clear1, col_clear2 = st.columns([1, 3])
            with col_clear1:
                if st.button("🗑️ Clear All Data", type="secondary", key="clear_all"):
                    save_campaign_db({})
                    st.success("All campaign data cleared.")
                    st.rerun()


if __name__ == "__main__":
    main()