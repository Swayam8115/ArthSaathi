# ArthSaathi

> "ArthSaathi doesn't track your money, it helps you understand it, one conversation at a time."

A WhatsApp-first Agentic AI for financial literacy, built for India's diverse and underserved population.

## Architecture

4-agent LangGraph pipeline: **Language → Profile → Pattern → Nudge → Language**

## Setup

```bash
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
cp .env.example .env        # Fill in your keys
```

## Run

```bash
uvicorn api.main:app --reload
```
