import time
import smtplib
import ssl
import os
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Tuple, List, Dict, Any, Optional

import pandas as pd
import streamlit as st


def load_recipients_file(uploaded_file) -> Tuple[pd.DataFrame, str]:
    """Load uploaded Excel/CSV file into a DataFrame."""
    if uploaded_file is None:
        return pd.DataFrame(), "No file uploaded."

    try:
        name = uploaded_file.name.lower()
        if name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded_file)
        elif name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            return pd.DataFrame(), "Unsupported file format. Please upload CSV or Excel."
    except Exception as e:
        return pd.DataFrame(), f"Error reading file: {e}"

    df.columns = [str(c).strip() for c in df.columns]

    required = {"Name", "Email"}
    if not required.issubset(set(df.columns)):
        return pd.DataFrame(), "File must contain 'Name' and 'Email' columns."

    df = df.dropna(subset=["Email"])
    return df, ""


def render_email_template(template: str, context: Dict[str, Any]) -> Tuple[str, str]:
    """Render a template with .format(**context)."""
    try:
        rendered = template.format(**context)
        return rendered, ""
    except KeyError as e:
        missing_key = str(e).strip("'")
        return "", f"Template error: missing placeholder {{{missing_key}}} in data."
    except Exception as e:
        return "", f"Template rendering error: {e}"


def get_smtp_settings(email_address: str) -> Dict[str, Any]:
    """Detect email domain and return appropriate SMTP settings."""
    domain = email_address.split("@")[-1].lower() if "@" in email_address else ""
    
    # Gmail settings
    if "gmail.com" in domain:
        return {
            "host": "smtp.gmail.com",
            "port": 465,
            "use_ssl": True,
            "use_tls": False
        }
    # Outlook/Hotmail settings
    elif domain in ["outlook.com", "hotmail.com", "live.com"]:
        return {
            "host": "smtp-mail.outlook.com",
            "port": 587,
            "use_ssl": False,
            "use_tls": True
        }
    # Generic SMTP (for custom domains like waderift.in)
    else:
        # Try common SMTP ports - user may need to configure
        return {
            "host": f"smtp.{domain}" if domain else "smtp.gmail.com",
            "port": 587,
            "use_ssl": False,
            "use_tls": True
        }


def create_smtp_connection(email_address: str, app_password: str, smtp_host: Optional[str] = None, smtp_port: Optional[int] = None):
    """Create and return an SMTP connection based on email domain."""
    if smtp_host and smtp_port:
        # Use custom SMTP settings
        settings = {
            "host": smtp_host,
            "port": smtp_port,
            "use_ssl": smtp_port == 465,
            "use_tls": smtp_port == 587
        }
    else:
        settings = get_smtp_settings(email_address)
    
    context = ssl.create_default_context()
    
    if settings["use_ssl"]:
        server = smtplib.SMTP_SSL(settings["host"], settings["port"], context=context)
    else:
        server = smtplib.SMTP(settings["host"], settings["port"])
        if settings["use_tls"]:
            server.starttls(context=context)
    
    server.login(email_address, app_password)
    return server


def apply_smart_delay(sent_count: int):
    """Smart delay logic."""
    delay = 0.0
    if sent_count > 0:
        if sent_count % 100 == 0:
            delay = 8.0
        elif sent_count % 50 == 0:
            delay = 5.0
        elif sent_count % 10 == 0:
            delay = 2.5

    if delay > 0:
        time.sleep(delay)


def load_total_sent_count() -> int:
    """Load persistent total email count from file."""
    count_file = "total_emails_sent.json"
    if os.path.exists(count_file):
        try:
            with open(count_file, "r") as f:
                data = json.load(f)
                return data.get("total_sent", 0)
        except Exception:
            return 0
    return 0


def save_total_sent_count(count: int):
    """Save persistent total email count to file."""
    count_file = "total_emails_sent.json"
    try:
        with open(count_file, "w") as f:
            json.dump({"total_sent": count}, f)
    except Exception:
        pass


def attach_file_to_email(message: MIMEMultipart, file_data: bytes, filename: str, content_type: str):
    """Attach a file (PDF or image) to the email message."""
    part = MIMEBase("application", "octet-stream")
    part.set_payload(file_data)
    encoders.encode_base64(part)
    
    if content_type == "pdf":
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    else:  # image
        part.add_header("Content-Disposition", f'inline; filename="{filename}"')
        part.add_header("Content-ID", f"<{filename}>")
    
    message.attach(part)


def send_bulk_emails(
    df: pd.DataFrame,
    email_address: str,
    app_password: str,
    subject_template: str,
    body_template: str,
    progress_slot,
    status_slot,
    pdf_file: Optional[bytes] = None,
    pdf_filename: Optional[str] = None,
    image_file: Optional[bytes] = None,
    image_filename: Optional[str] = None,
    smtp_host: Optional[str] = None,
    smtp_port: Optional[int] = None,
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Main bulk sending loop with PDF and image attachments."""
    total = len(df)
    if total == 0:
        return 0, 0, []

    results: List[Dict[str, Any]] = []
    sent_count = 0
    failed_count = 0

    progress_bar = st.progress(0)
    progress_text = progress_slot.empty()
    log_lines: List[str] = []

    try:
        server = create_smtp_connection(email_address, app_password, smtp_host, smtp_port)
    except Exception as e:
        raise RuntimeError(f"SMTP authentication failed: {e}")

    try:
        for idx, row in df.iterrows():
            name = str(row.get("Name", "")).strip()
            recipient_email = str(row.get("Email", "")).strip()

            context = {col: row[col] for col in df.columns}
            context.setdefault("Name", name)
            context.setdefault("Email", recipient_email)

            subject, err = render_email_template(subject_template, context)
            if err:
                status = "Failed"
                msg = err
                failed_count += 1
            else:
                body, err = render_email_template(body_template, context)
                if err:
                    status = "Failed"
                    msg = err
                    failed_count += 1
                else:
                    message = MIMEMultipart()
                    message["From"] = email_address
                    message["To"] = recipient_email
                    message["Subject"] = subject
                    
                    # Add body text
                    message.attach(MIMEText(body, "plain"))
                    
                    # Attach PDF if provided
                    if pdf_file and pdf_filename:
                        attach_file_to_email(message, pdf_file, pdf_filename, "pdf")
                    
                    # Attach image at the end if provided
                    if image_file and image_filename:
                        attach_file_to_email(message, image_file, image_filename, "image")

                    try:
                        server.sendmail(email_address, recipient_email, message.as_string())
                        status = "Sent"
                        msg = "Email sent successfully."
                        sent_count += 1
                    except Exception as e:
                        status = "Failed"
                        msg = f"SMTP error: {e}"
                        failed_count += 1

            results.append(
                {
                    "Name": name,
                    "Email": recipient_email,
                    "Status": status,
                    "Message": msg,
                }
            )

            log_lines.append(f"[{status}] {name} <{recipient_email}> - {msg}")
            status_slot.text("\n".join(log_lines[-200:]))

            progress = int(((idx + 1) / total) * 100)
            progress_bar.progress(progress)
            progress_text.text(f"Processing {idx + 1} of {total} emails...")

            apply_smart_delay(sent_count)
    finally:
        try:
            server.quit()
        except Exception:
            pass

    return sent_count, failed_count, results


def main():
    st.set_page_config(
        page_title="Bulk Gmail Sender",
        page_icon="📧",
        layout="centered",
    )

    st.sidebar.title("Bulk Email Sender")
    st.sidebar.info(
        "**For Gmail:** Use App Password (not normal password).\n\n"
        "1. Enable 2‑step verification\n"
        "2. Create app password for \"Mail\"\n"
        "3. Paste it here\n\n"
        "**For custom domains:** Use your email password or app-specific password."
    )
    
    # Load and display persistent total count
    total_sent_all_time = load_total_sent_count()
    st.sidebar.metric("📊 Total Emails Sent (All Time)", total_sent_all_time)

    st.title("📧 Professional Bulk Email Sender")
    st.write(
        "Upload a CSV/Excel file with `Name` and `Email` columns, customize your email template, "
        "and send personalized emails in bulk. Supports Gmail and custom email domains."
    )

    st.subheader("1. Upload Recipient List")
    uploaded_file = st.file_uploader(
        "Upload CSV or Excel file with 'Name' and 'Email' columns",
        type=["csv", "xlsx", "xls"],
    )

    df, file_error = load_recipients_file(uploaded_file) if uploaded_file else (pd.DataFrame(), "")

    if file_error:
        st.error(file_error)
    elif not df.empty:
        st.success(f"Loaded {len(df)} rows from file.")
        st.dataframe(df.head(20), use_container_width=True)
    else:
        st.info("Awaiting file upload.")

    st.subheader("2. Email Credentials")
    email_address = st.text_input(
        "Email Address", 
        placeholder="yourname@gmail.com or info@waderift.in",
        help="Supports Gmail, Outlook, and custom domains."
    )
    app_password = st.text_input(
        "Email Password / App Password",
        type="password",
        help="For Gmail: Use App Password. For custom domains: Use your email password or app-specific password.",
    )
    
    # Optional custom SMTP settings
    with st.expander("⚙️ Advanced SMTP Settings (Optional)"):
        st.caption("Leave empty to auto-detect based on email domain")
        custom_smtp_host = st.text_input("SMTP Host", placeholder="e.g., smtp.gmail.com")
        custom_smtp_port = st.number_input("SMTP Port", min_value=25, max_value=9999, value=587, step=1)

    st.subheader("3. Email Template")
    st.write(
        "Use placeholders like `{Name}`, `{Company}` and any other column names from your file."
    )

    default_subject = "Meeting at April High Point 2026 - / {Company}"
    default_body = (
        "Dear {Name},\n\n"
        "We are excited to invite you to our meeting at April High Point 2026.\n\n"
        "Please find the attached documents for your reference.\n\n"
        "Best regards,\n"
        "Your Team"
    )

    subject_template = st.text_input("Email Subject Template", value=default_subject)
    body_template = st.text_area(
        "Email Body Template",
        value=default_body,
        height=200,
    )
    
    st.subheader("4. Attachments (PDF & Image)")
    st.write("Upload PDF and image files that will be attached to all emails. Image will appear at the end.")
    
    col_attach1, col_attach2 = st.columns(2)
    
    with col_attach1:
        pdf_file_uploader = st.file_uploader(
            "Upload PDF File",
            type=["pdf"],
            help="PDF will be attached to all emails"
        )
        pdf_file_data = None
        pdf_filename = None
        if pdf_file_uploader:
            pdf_file_data = pdf_file_uploader.read()
            pdf_filename = pdf_file_uploader.name
            st.success(f"✅ PDF loaded: {pdf_filename}")
    
    with col_attach2:
        image_file_uploader = st.file_uploader(
            "Upload Image File",
            type=["png", "jpg", "jpeg", "gif"],
            help="Image will be attached at the end of all emails"
        )
        image_file_data = None
        image_filename = None
        if image_file_uploader:
            image_file_data = image_file_uploader.read()
            image_filename = image_file_uploader.name
            st.success(f"✅ Image loaded: {image_filename}")

    st.subheader("5. Send Emails")

    col1, col2 = st.columns(2)
    with col1:
        total_emails = len(df) if not df.empty else 0
        st.metric("📋 Recipients in this batch", total_emails)
        st.metric("📊 Total sent (all time)", total_sent_all_time)

    with col2:
        st.caption(
            "**Smart delay rules:**\n"
            "- 2.5s after every 10 emails\n"
            "- 5s after every 50 emails\n"
            "- 8s after every 100 emails"
        )

    can_send = (
        uploaded_file is not None
        and not df.empty
        and email_address.strip() != ""
        and app_password.strip() != ""
        and subject_template.strip() != ""
        and body_template.strip() != ""
    )

    send_button = st.button(
        "🚀 Start Sending Emails",
        type="primary",
        disabled=not can_send,
        help="Fill all required fields and upload a valid file to enable.",
    )

    progress_slot = st.empty()
    status_slot = st.empty()
    summary_slot = st.empty()
    results_slot = st.empty()

    if send_button:
        if not can_send:
            st.error("Please fill in all fields and upload a valid recipient file before sending.")
            return

        smtp_host = custom_smtp_host.strip() if custom_smtp_host.strip() else None
        smtp_port = int(custom_smtp_port) if custom_smtp_host.strip() else None

        with st.spinner("Connecting to email server and sending emails..."):
            try:
                sent, failed, results = send_bulk_emails(
                    df=df,
                    email_address=email_address.strip(),
                    app_password=app_password.strip(),
                    subject_template=subject_template.strip(),
                    body_template=body_template,
                    progress_slot=progress_slot,
                    status_slot=status_slot,
                    pdf_file=pdf_file_data,
                    pdf_filename=pdf_filename,
                    image_file=image_file_data,
                    image_filename=image_filename,
                    smtp_host=smtp_host,
                    smtp_port=smtp_port,
                )
                
                # Update persistent count
                if sent > 0:
                    new_total = total_sent_all_time + sent
                    save_total_sent_count(new_total)
                    st.sidebar.metric("📊 Total Emails Sent (All Time)", new_total)
                
            except RuntimeError as e:
                st.error(str(e))
                return
            except Exception as e:
                st.error(f"Unexpected error while sending emails: {e}")
                return

        summary_slot.markdown(
            f"### ✅ Sending complete\n"
            f"- **Total recipients**: {len(df)}\n"
            f"- **Successfully sent**: {sent}\n"
            f"- **Failed**: {failed}\n"
            f"- **Total sent (all time)**: {total_sent_all_time + sent}"
        )

        if results:
            results_df = pd.DataFrame(results)
            results_slot.dataframe(results_df, use_container_width=True)

        if failed > 0:
            st.warning(
                "Some emails failed to send. Check the results table and logs above "
                "for specific error messages."
            )


if __name__ == "__main__":
    main()

