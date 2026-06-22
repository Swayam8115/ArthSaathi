"""
FastAPI application entry point.

Run with:
  uvicorn api.main:app --reload --port 8000
"""

import logging

from fastapi import FastAPI

from api.webhook import router as webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
# Show Gemini retry warnings (DEBUG level) so we can see rate-limit waits
logging.getLogger("utils.gemini_client").setLevel(logging.DEBUG)

app = FastAPI(
    title="ArthSaathi",
    description="WhatsApp-first Agentic AI for financial literacy in India.",
    version="0.1.0",
)

app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict:
    """Health check — used by load balancers and Docker health checks."""
    return {"status": "ok", "service": "ArthSaathi"}
