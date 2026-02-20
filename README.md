<<<<<<< HEAD
# Bulk Email Sender (Streamlit)

Professional Streamlit web application for automated bulk email sending with support for Gmail, Outlook, and custom email domains.

## Features

- **Multi-domain support**: Works with Gmail, Outlook, and custom domains (e.g., info@waderift.in)
- Upload CSV/Excel file with `Name` and `Email` columns
- Preview data table
- Customizable subject/body templates with placeholders like `{Name}`, `{Company}`
- **PDF & Image attachments**: Upload PDF and image files that will be attached to all emails (image appears at the end)
- **Persistent email count**: Tracks total emails sent across all sessions
- Smart delay: 2.5s after 10, 5s after 50, 8s after 100 emails
- Real-time progress bar, live logs, per-recipient success/failure table
- Final summary of total, sent, and failed emails
- Advanced SMTP settings for custom configurations

## Setup

1. Create and activate a virtual environment (recommended):

   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # or
   source venv/bin/activate  # Mac/Linux
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. **For Gmail**: Ensure you have 2‑step verification enabled and create an **App Password** for "Mail".
4. **For custom domains**: Use your email password or app-specific password.

## Running the app

From this folder:

```bash
python -m streamlit run app.py
```

Or if streamlit is in PATH:

```bash
streamlit run app.py
```

This will open the app in your browser (or provide a local URL).

## Using the app

1. Upload your recipients file (see `sample_recipients.csv` for format).
2. Verify that the preview shows correct `Name` and `Email` values.
3. Enter your email address (Gmail or custom domain) and password/app password.
4. Adjust the subject template (default: "Meeting at April High Point 2026 - / {Company}") and body template.
5. **Upload PDF and/or Image files** (optional) - these will be attached to all emails.
6. Click **"Start Sending Emails"** and watch the progress/log area.

The app will respect the smart delay rules to reduce the risk of throttling. A final summary and detailed result table will be shown after completion. The total email count persists across sessions.

pip install --upgrade pip
pip install -r requirements.txt

python -m streamlit run app.py
=======
# Bulk_MAilling
Bulk mailing system
>>>>>>> 384d192b7663056621d4ba8d9c0d4669d70de6e9
