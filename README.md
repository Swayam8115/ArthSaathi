# ArthSaathi

> "ArthSaathi doesn't track your money, it helps you understand it, one conversation at a time."

A WhatsApp-first Agentic AI for financial literacy, built for India's diverse and underserved population. Users send a message in their native language — ArthSaathi understands it, builds a financial profile, detects risk patterns, and replies with a personalised nudge and a micro-lesson, all on WhatsApp.

---

## Architecture

```
WhatsApp User
     │
     ▼
Meta Cloud API  ──POST──►  FastAPI Webhook  ──►  LangGraph Pipeline
                                                        │
                    ┌───────────────────────────────────┤
                    ▼                                   ▼
            Language Agent (in)               Pattern Agent
            · Detect language                 · Rule-based checks
            · Translate → English             · Semantic risk (Gemini)
                    │                                   │
                    ▼                                   ▼
            Profile Agent                      Nudge Agent
            · Extract financial events         · Decide + generate nudge
            · Infer persona                    · Seekho micro-lesson
            · Update Supabase                  · Answer query
                    │                                   │
                    └───────────────────────────────────┘
                                    │
                                    ▼
                          Language Agent (out)
                          · Translate → user's language
                                    │
                                    ▼
                          WhatsApp reply sent
```

**Pipeline:** Language In → Profile → Pattern → Nudge → Language Out → WhatsApp

**Interrupt path** (predatory loan / distress signal detected): Pattern Agent generates an urgent nudge directly, skipping the Nudge Agent.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Orchestration | LangGraph (StateGraph) |
| LLM | Gemini 2.5 Flash (Google AI) |
| Database | Supabase (PostgreSQL + pgvector) |
| ORM | SQLAlchemy 2.x async |
| Task Queue | Celery + Redis |
| WhatsApp | Meta Cloud API v20.0 |
| Containerisation | Docker + Docker Compose |

---

## Agents

| Agent | Gemini Calls | What it does |
|---|---|---|
| Language In | 1 | Detect language + translate to English (combined) |
| Profile | 1 | Extract financial events + infer persona (combined) |
| Pattern | 1 | Semantic risk check (predatory loan, distress signal) |
| Nudge | 1 | Decide nudge + generate nudge + Seekho lesson (combined) |
| Language Out | 1 | Translate reply back to user's language |
| **Total** | **5 calls** | |

---

## Supported Languages

Hindi · Marathi · Kannada · Tamil · Telugu · Bengali · English

---

## Project Structure

```
ArthSaathi/
├── agents/
│   ├── prompts/          # All LLM prompts (separated from logic)
│   ├── schemas/          # Pydantic structured output schemas
│   ├── language_agent.py
│   ├── profile_agent.py
│   ├── pattern_agent.py
│   └── nudge_agent.py
├── api/
│   ├── main.py           # FastAPI app
│   ├── webhook.py        # WhatsApp webhook (GET verify + POST receive)
│   └── whatsapp.py       # Meta Cloud API client
├── db/
│   ├── schema.sql        # Supabase table definitions
│   ├── models.py         # SQLAlchemy models
│   ├── supabase_client.py
│   └── user_profile.py   # CRUD operations
├── orchestrator/
│   ├── state.py          # AgentState TypedDict
│   └── graph.py          # LangGraph StateGraph wiring
├── scheduler/
│   ├── celery_app.py     # Celery + beat schedule
│   └── nudge_tasks.py    # Scheduled nudge tasks
├── utils/
│   ├── config.py         # Pydantic Settings
│   ├── constants.py
│   └── gemini_client.py  # Gemini SDK wrapper with retry + timeout
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/ArthSaathi.git
cd ArthSaathi
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in `.env` with your keys:

| Variable | Where to get it |
|---|---|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com) |
| `SUPABASE_URL` | Supabase Dashboard → Project Settings |
| `SUPABASE_KEY` | Supabase Dashboard → Project Settings → API |
| `DATABASE_URL` | Supabase Dashboard → Settings → Database → Connection pooling (Session mode) — change prefix to `postgresql+asyncpg://` |
| `WHATSAPP_TOKEN` | Meta Developer Console → WhatsApp → API Setup |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta Developer Console → WhatsApp → API Setup |
| `WHATSAPP_VERIFY_TOKEN` | Any string you choose — used to verify the webhook |

### 3. Create database tables

Run the SQL in `db/schema.sql` in your Supabase SQL editor.

---

## Run with Docker (recommended)

```bash
docker compose up --build
```

This starts 4 services: `redis`, `api` (port 8000), `worker` (Celery), `beat` (scheduler).

### Expose for WhatsApp webhook

```bash
ngrok http 8000
```

Register the ngrok URL in **Meta Developer Console → WhatsApp → Configuration → Webhook**:
- **Callback URL**: `https://your-ngrok-url.ngrok-free.app/webhook`
- **Verify Token**: value of `WHATSAPP_VERIFY_TOKEN` in your `.env`

Then subscribe to the **messages** field under Webhook → Manage.

---

## Run locally (without Docker)

Requires Redis running locally.

```bash
# Terminal 1 — API
uvicorn api.main:app --reload --port 8000

# Terminal 2 — Celery worker
celery -A scheduler.celery_app worker --loglevel=info

# Terminal 3 — Celery beat
celery -A scheduler.celery_app beat --loglevel=info --schedule=/tmp/celerybeat-schedule
```

---

## Scheduled Tasks (Celery Beat)

| Task | Schedule | What it does |
|---|---|---|
| `check_inactive_users` | Daily 9 AM IST | Nudges users inactive for 7+ days |
| `seasonal_farmer_check` | 1st of every month | Seasonal scheme reminders for farmer persona |

---

## Free Tier Notes

- Uses **Gemini 2.5 Flash** (5 RPM free tier)
- Pipeline makes **5 Gemini calls** per message
- A 14-second delay between calls keeps usage within the free tier
- Expect ~30–45 second response time per message on free tier
- For production, enable billing on Google AI Studio (~₹0.02/message)

---

## WhatsApp Token

Meta test tokens expire every **24 hours**. For production, generate a **System User token** in Meta Business Suite → System Users with `whatsapp_business_messaging` permission and set expiry to **Never**.
