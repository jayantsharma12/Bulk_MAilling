# 🗄️ SUPABASE SETUP — Step by Step Guide

---

## STEP 1 — Account Banao (Free)

1. Jao → https://supabase.com
2. **"Start your project"** click karo
3. GitHub se sign up karo (free hai)
4. **"New project"** click karo:
   - **Name:** `indsource-emails`
   - **Database Password:** koi bhi strong password (save kar lo)
   - **Region:** `Southeast Asia (Singapore)` ← India ke sabse paas
5. **"Create new project"** → 1-2 minute wait karo

---

## STEP 2 — 2 Tables Banao

Left sidebar mein → **SQL Editor** click karo → **"New query"**

Yeh poora SQL copy karke paste karo aur **"Run"** button dabao:

```sql
-- Table 1: Campaigns (campaign_db.json ki jagah)
CREATE TABLE campaigns (
    id BIGSERIAL PRIMARY KEY,
    campaign_name TEXT UNIQUE NOT NULL,
    sender_email TEXT DEFAULT '',
    subject_template TEXT DEFAULT '',
    body_template TEXT DEFAULT '',
    total_followups_planned INTEGER DEFAULT 5,
    followup_interval_days INTEGER DEFAULT 3,
    recipients JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 2: Stats (total_emails_sent.json ki jagah)
CREATE TABLE stats (
    id INTEGER PRIMARY KEY,
    total_sent INTEGER DEFAULT 0
);

-- Pehla row insert karo
INSERT INTO stats (id, total_sent) VALUES (1, 0);
```

**"Run"** dabao → **"Success. No rows returned"** aana chahiye ✅

---

## STEP 3 — API Keys Copy Karo

1. Left sidebar mein → **Settings** (gear ⚙️ icon, bilkul neeche)
2. **"API"** click karo
3. Yahan se 2 cheezein copy karo:

```
Project URL:   https://XXXXXXXX.supabase.co
anon public:   eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.XXXXX...
```

---

## STEP 4 — Streamlit Secrets Set Karo

### Agar Streamlit Community Cloud pe deploy kar rahe ho:
1. https://share.streamlit.io → Apni app → **Settings** → **Secrets**
2. Yeh paste karo (apni values daalo):

```toml
SUPABASE_URL = "https://XXXXXXXX.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.XXXXX..."
```

### Agar local machine pe chala rahe ho:
Project folder mein `.streamlit/secrets.toml` file banao:

```
📁 Tumhara Folder/
├── app.py
├── requirements.txt
├── firstmail.jpg
├── followup.jpg
└── .streamlit/
    └── secrets.toml   ← yeh file banao
```

`secrets.toml` mein yeh likho:
```toml
SUPABASE_URL = "https://XXXXXXXX.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.XXXXX..."
```

---

## STEP 5 — Run Karo

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## ✅ Test Karo

App khulne ke baad:
- Koi campaign launch karo
- App band karo → wapas kholo
- **Data wapas aayega** Supabase se ✅
- Supabase Dashboard → Table Editor → `campaigns` mein data dikhega ✅

---

## ❓ Common Errors

| Error | Fix |
|-------|-----|
| `Database load error` | SUPABASE_URL ya KEY galat hai — dobara copy karo |
| `relation does not exist` | Step 2 ka SQL dobara run karo |
| `Invalid API key` | anon public key use karo, service_role nahi |

