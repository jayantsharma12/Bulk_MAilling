import streamlit as st
import smtplib
import ssl
import os
import json
import socket
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import pandas as pd

st.set_page_config(page_title="App Diagnostics", page_icon="🔍",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Serif+Display&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem !important; max-width: 1100px; }
.page-title { font-family:'DM Serif Display',serif;font-size:1.8rem;color:#1a1a1a;border-bottom:2px solid #8B1A1A;padding-bottom:12px;margin-bottom:24px; }
.test-card { background:#fff;border:1px solid #e8e8e8;border-radius:10px;padding:20px 24px;margin-bottom:16px; }
.test-card h3 { font-size:0.75rem;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:#8B1A1A;margin-bottom:14px;margin-top:0; }
.check-row { display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #f5f5f5;font-size:0.88rem; }
.check-row:last-child { border-bottom:none; }
.badge-pass { background:#dcfce7;color:#166534;padding:2px 10px;border-radius:20px;font-size:0.75rem;font-weight:600; }
.badge-fail { background:#fee2e2;color:#991b1b;padding:2px 10px;border-radius:20px;font-size:0.75rem;font-weight:600; }
.badge-warn { background:#fef9c3;color:#854d0e;padding:2px 10px;border-radius:20px;font-size:0.75rem;font-weight:600; }
.badge-info { background:#e0f2fe;color:#075985;padding:2px 10px;border-radius:20px;font-size:0.75rem;font-weight:600; }
.stButton > button[kind="primary"] { background:#8B1A1A !important;color:white !important;border:none !important;border-radius:6px !important;font-weight:500 !important; }
.stButton > button[kind="secondary"] { background:transparent !important;color:#8B1A1A !important;border:1.5px solid #8B1A1A !important;border-radius:6px !important; }
.stTextInput > div > div > input { border:1px solid #ddd !important;border-radius:6px !important; }
.result-box { background:#f8f8f8;border:1px solid #e5e5e5;border-radius:8px;padding:14px 18px;font-size:0.82rem;font-family:monospace;margin-top:10px;white-space:pre-wrap;max-height:180px;overflow-y:auto; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="page-title">🔍 App Diagnostics & Testing</div>', unsafe_allow_html=True)
st.caption("Deploy se pehle sab kuch test karo — files, SMTP, test email, recipient file validator")


def badge(status):
    if status == "PASS":
        return '<span class="badge-pass">✓ PASS</span>'
    elif status == "FAIL":
        return '<span class="badge-fail">✗ FAIL</span>'
    elif status == "WARN":
        return '<span class="badge-warn">⚠ WARN</span>'
    else:
        return '<span class="badge-info">ℹ INFO</span>'


def check_row(status, name, detail=""):
    st.markdown(
        '<div class="check-row">' + badge(status) + ' <span><b>' + name + '</b>' +
        (' — ' + detail if detail else '') + '</span></div>',
        unsafe_allow_html=True
    )


# ── SECTION 1: File & Library Checks ────────────────────────────────────────
col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown('<div class="test-card"><h3>📁 File & Folder Check</h3>', unsafe_allow_html=True)

    # app.py
    if os.path.exists("app.py"):
        check_row("PASS", "app.py", "Found")
    else:
        check_row("FAIL", "app.py", "Not found — wrong folder mein ho?")

    # requirements.txt
    if os.path.exists("requirements.txt"):
        check_row("PASS", "requirements.txt", "Found")
    else:
        check_row("WARN", "requirements.txt", "Missing — needed for deployment")

    # firstmail signature
    firstmail_found = None
    for ext in ["jpg", "png", "jpeg"]:
        p = "firstmail." + ext
        if os.path.exists(p):
            size = os.path.getsize(p) // 1024
            firstmail_found = p + " (" + str(size) + " KB)"
            break
    if firstmail_found:
        check_row("PASS", "firstmail signature", firstmail_found)
    else:
        check_row("WARN", "firstmail signature", "Not found — place firstmail.jpg in project folder")

    # followup signature
    followup_found = None
    for ext in ["jpg", "png", "jpeg"]:
        p = "followup." + ext
        if os.path.exists(p):
            size = os.path.getsize(p) // 1024
            followup_found = p + " (" + str(size) + " KB)"
            break
    if followup_found:
        check_row("PASS", "followup signature", followup_found)
    else:
        check_row("WARN", "followup signature", "Not found — place followup.jpg in project folder")

    # campaign_db.json
    if os.path.exists("campaign_db.json"):
        try:
            db = json.load(open("campaign_db.json"))
            check_row("PASS", "campaign_db.json", str(len(db)) + " campaign(s)")
        except Exception:
            check_row("WARN", "campaign_db.json", "File exists but unreadable")
    else:
        check_row("INFO", "campaign_db.json", "Will be created on first campaign")

    # total_emails_sent.json
    if os.path.exists("total_emails_sent.json"):
        try:
            count = json.load(open("total_emails_sent.json")).get("total_sent", 0)
            check_row("PASS", "total_emails_sent.json", "Total sent: " + str(count))
        except Exception:
            check_row("WARN", "total_emails_sent.json", "Unreadable")
    else:
        check_row("INFO", "total_emails_sent.json", "Will be created automatically")

    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="test-card"><h3>📦 Python Libraries</h3>', unsafe_allow_html=True)
    for lib in ["streamlit", "pandas", "openpyxl", "smtplib", "ssl"]:
        try:
            mod = __import__(lib)
            ver = getattr(mod, "__version__", "built-in")
            check_row("PASS", lib, str(ver))
        except ImportError:
            check_row("FAIL", lib, "pip install " + lib)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="test-card"><h3>📊 Campaign Database</h3>', unsafe_allow_html=True)
    if os.path.exists("campaign_db.json"):
        try:
            db = json.load(open("campaign_db.json"))
            if db:
                for cname, cdata in db.items():
                    recs = cdata.get("recipients", {})
                    done = sum(1 for r in recs.values() if r.get("followups_sent", 0) >= cdata.get("total_followups_planned", 5))
                    due = sum(
                        1 for r in recs.values()
                        if r.get("followups_sent", 0) < cdata.get("total_followups_planned", 5)
                        and datetime.fromisoformat(r["next_followup_date"]) <= datetime.now()
                    )
                    due_color = "#8B1A1A" if due > 0 else "#666"
                    st.markdown(
                        '<div class="check-row"><span class="badge-info">📁</span>'
                        ' <span><b>' + cname + '</b> — ' + str(len(recs)) + ' recipients · '
                        + str(done) + ' done · <span style="color:' + due_color + ';">'
                        + str(due) + ' due</span></span></div>',
                        unsafe_allow_html=True
                    )
            else:
                check_row("INFO", "No campaigns yet", "")
        except Exception as e:
            st.error("DB read error: " + str(e))
    else:
        check_row("INFO", "No DB file yet", "Will be created on first send")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🗑️ Clear DB", type="secondary", key="clr_db"):
            json.dump({}, open("campaign_db.json", "w"))
            st.success("Cleared!")
            st.rerun()
    with c2:
        if st.button("🔄 Refresh", type="secondary", key="refresh"):
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")

# ── SECTION 2: SMTP Connection Test ─────────────────────────────────────────
st.markdown('<div class="test-card"><h3>🔌 SMTP Connection Test</h3>', unsafe_allow_html=True)
sc1, sc2, sc3, sc4 = st.columns(4)
with sc1:
    te = st.text_input("Email", placeholder="info-intl@indsource.net", key="te")
with sc2:
    tp = st.text_input("Password", type="password", key="tp")
with sc3:
    th = st.text_input("SMTP Host (optional)", key="th", placeholder="mail.indsource.net")
with sc4:
    tport = st.number_input("Port", min_value=25, max_value=9999, value=587, key="tport")

if st.button("🔌 Test Connection", type="primary", key="test_conn"):
    if not te or not tp:
        st.warning("Email aur password dalo")
    else:
        logs = []
        conn_ok = False
        with st.spinner("Connecting..."):
            try:
                domain = te.split("@")[-1].lower()
                if th.strip():
                    host = th.strip()
                    port = int(tport)
                elif "gmail.com" in domain:
                    host, port = "smtp.gmail.com", 465
                elif domain in ["outlook.com", "hotmail.com", "live.com"]:
                    host, port = "smtp-mail.outlook.com", 587
                else:
                    host = "smtp." + domain
                    port = 587

                logs.append("Connecting to " + host + ":" + str(port))
                ctx = ssl.create_default_context()

                if port == 465:
                    srv = smtplib.SMTP_SSL(host, port, context=ctx, timeout=10)
                    logs.append("SSL connection established")
                else:
                    srv = smtplib.SMTP(host, port, timeout=10)
                    srv.starttls(context=ctx)
                    logs.append("STARTTLS established")

                srv.login(te, tp)
                logs.append("Login successful!")
                srv.quit()
                conn_ok = True

            except smtplib.SMTPAuthenticationError:
                logs.append("AUTH FAILED — wrong password or App Password needed")
            except socket.timeout:
                logs.append("TIMEOUT — host unreachable or port blocked")
            except Exception as e:
                logs.append("ERROR: " + type(e).__name__ + " — " + str(e))

        if conn_ok:
            st.success("✅ SMTP Connection Successful!")
        else:
            st.error("❌ Connection Failed")

        log_text = "\n".join(logs)
        st.markdown('<div class="result-box">' + log_text + '</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ── SECTION 3: Send Test Email ───────────────────────────────────────────────
st.markdown('<div class="test-card"><h3>📧 Send Test Email</h3>', unsafe_allow_html=True)
st.caption("Apne aap ko test email bhejo — signature, formatting sab check karo")

te1, te2 = st.columns(2)
with te1:
    s_from = st.text_input("From Email", placeholder="info-intl@indsource.net", key="s_from")
    s_pass = st.text_input("Password", type="password", key="s_pass")
    s_host = st.text_input("SMTP Host (optional)", key="s_host", placeholder="mail.indsource.net")
    s_port = st.number_input("Port", min_value=25, max_value=9999, value=587, key="s_port")
with te2:
    s_to = st.text_input("To Email", placeholder="test@youremail.com", key="s_to")
    s_subj = st.text_input("Subject", value="Test — Indsource Email Sender", key="s_subj")
    s_body = st.text_area("Body", height=130, key="s_body", value=(
        "Hi,\n\nThis is a test email from Indsource Bulk Email Sender.\n\n"
        "If you see this with the signature below, everything is working!\n\n"
        "Best regards,\nIndsource Team"
    ))

# Check signature
sig_data = None
sig_name = None
for ext in ["jpg", "png", "jpeg"]:
    p = "firstmail." + ext
    if os.path.exists(p):
        sig_name = p
        with open(p, "rb") as f:
            sig_data = f.read()
        break

if sig_data:
    st.markdown(
        '<div style="font-size:0.82rem;color:#166534;background:#f0fff4;border:1px solid #bbf7d0;'
        'border-radius:6px;padding:8px 14px;margin:6px 0;">📌 Signature will attach: <b>'
        + sig_name + '</b> — full width, email ke bilkul end mein</div>',
        unsafe_allow_html=True
    )
else:
    st.markdown(
        '<div style="font-size:0.82rem;color:#854d0e;background:#fef9c3;border:1px solid #fde68a;'
        'border-radius:6px;padding:8px 14px;margin:6px 0;">⚠️ firstmail.jpg not found — '
        'email without signature bhejega</div>',
        unsafe_allow_html=True
    )

if st.button("📤 Send Test Email", type="primary", key="send_test"):
    if not s_from or not s_pass or not s_to:
        st.warning("From, password aur To email sab bharo")
    else:
        with st.spinner("Sending..."):
            try:
                domain = s_from.split("@")[-1].lower()
                if s_host.strip():
                    host = s_host.strip()
                    port = int(s_port)
                elif "gmail.com" in domain:
                    host, port = "smtp.gmail.com", 465
                elif domain in ["outlook.com", "hotmail.com", "live.com"]:
                    host, port = "smtp-mail.outlook.com", 587
                else:
                    host = "smtp." + domain
                    port = int(s_port)

                if sig_data and sig_name:
                    ext = sig_name.rsplit(".", 1)[-1].lower()
                    mime_sub = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png"}.get(ext, "jpeg")
                    body_html = s_body.replace("\n", "<br/>")
                    html_content = (
                        '<html><body style="margin:0;padding:0;">'
                        '<div style="font-family:Calibri,Arial,sans-serif;font-size:14px;line-height:1.6;padding:16px 0;">'
                        + body_html +
                        '</div>'
                        '<div style="width:100%;margin:0;padding:0;display:block;">'
                        '<img src="cid:signature_image" style="width:100%;max-width:100%;display:block;margin:0;padding:0;border:none;" alt="Signature"/>'
                        '</div></body></html>'
                    )
                    msg = MIMEMultipart("related")
                    msg["From"] = s_from
                    msg["To"] = s_to
                    msg["Subject"] = s_subj
                    alt = MIMEMultipart("alternative")
                    alt.attach(MIMEText(s_body, "plain"))
                    alt.attach(MIMEText(html_content, "html"))
                    msg.attach(alt)
                    sp = MIMEImage(sig_data, _subtype=mime_sub)
                    sp.add_header("Content-Disposition", 'inline; filename="' + sig_name + '"')
                    sp.add_header("Content-ID", "<signature_image>")
                    msg.attach(sp)
                else:
                    msg = MIMEMultipart()
                    msg["From"] = s_from
                    msg["To"] = s_to
                    msg["Subject"] = s_subj
                    msg.attach(MIMEText(s_body, "plain"))

                ctx = ssl.create_default_context()
                if port == 465:
                    srv = smtplib.SMTP_SSL(host, port, context=ctx, timeout=15)
                else:
                    srv = smtplib.SMTP(host, port, timeout=15)
                    srv.starttls(context=ctx)

                srv.login(s_from, s_pass)
                srv.sendmail(s_from, s_to, msg.as_string())
                srv.quit()
                st.success("✅ Test email sent to **" + s_to + "** — inbox check karo!")
                st.balloons()

            except smtplib.SMTPAuthenticationError:
                st.error("❌ Auth failed — password check karo")
            except Exception as e:
                st.error("❌ " + type(e).__name__ + ": " + str(e))

st.markdown('</div>', unsafe_allow_html=True)

# ── SECTION 4: Recipient File Validator ─────────────────────────────────────
st.markdown('<div class="test-card"><h3>📋 Recipient File Validator</h3>', unsafe_allow_html=True)
st.caption("CSV ya Excel upload karo — check karo format sahi hai")

vf = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"], key="vfile")
if vf:
    try:
        if vf.name.lower().endswith((".xlsx", ".xls")):
            df_v = pd.read_excel(vf)
        else:
            df_v = pd.read_csv(vf)

        df_v.columns = [str(c).strip() for c in df_v.columns]

        vc1, vc2, vc3 = st.columns(3)
        vc1.metric("Total Rows", len(df_v))
        vc2.metric("Columns", len(df_v.columns))
        if "Email" in df_v.columns:
            vc3.metric("Empty Emails", int(df_v["Email"].isna().sum()))
        else:
            vc3.metric("Empty Emails", "N/A")

        if "Name" in df_v.columns:
            check_row("PASS", "Name column", "Found")
        else:
            check_row("FAIL", "Name column", "Missing — add a 'Name' column")

        if "Email" in df_v.columns:
            check_row("PASS", "Email column", "Found")
            valid = int(df_v["Email"].dropna().astype(str).str.contains("@").sum())
            total = len(df_v)
            if valid == total:
                check_row("PASS", "Email format", str(valid) + "/" + str(total) + " valid")
            else:
                check_row("WARN", "Email format", str(valid) + "/" + str(total) + " valid — kuch emails invalid hain")
        else:
            check_row("FAIL", "Email column", "Missing — add an 'Email' column")

        extra = [c for c in df_v.columns if c not in ["Name", "Email"]]
        if extra:
            check_row("INFO", "Template placeholders", "{" + "}, {".join(extra) + "}")

        st.dataframe(df_v.head(5), use_container_width=True, hide_index=True)

    except Exception as e:
        st.error("File error: " + str(e))

st.markdown('</div>', unsafe_allow_html=True)

st.markdown(
    '<div style="text-align:center;padding:20px 0 4px;font-size:0.75rem;color:#bbb;">'
    'Indsource International · Diagnostics Page</div>',
    unsafe_allow_html=True
)