"""
WhatsApp webhook receiver.

GET  /webhook  — Meta Cloud API verification handshake
POST /webhook  — incoming message events (text + voice)

Each incoming message triggers the full LangGraph pipeline in a background
task so the webhook returns 200 immediately (Meta requires < 20 s response).
"""

import asyncio
import logging
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from api.whatsapp import download_audio, send_message
from orchestrator.graph import app as langgraph_app
from orchestrator.state import AgentState
from utils.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_PIPELINE_TIMEOUT = 180.0  # seconds — 3 retries × ~20s wait + processing time

# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_initial_state(
    user_id: str,
    raw_message: str,
    message_type: str,
    audio_bytes: bytes | None = None,
    audio_mime_type: str = "audio/ogg",
) -> AgentState:
    """Build a fully-initialised AgentState for the start of the pipeline."""
    return AgentState(
        user_id=user_id,
        raw_message=raw_message,
        message_type=message_type,
        audio_bytes=audio_bytes,
        audio_mime_type=audio_mime_type,
        detected_language="hi",
        translated_message="",
        profile={},
        extracted_events=[],
        risk_flags=[],
        interrupt=False,
        nudge_type=None,
        nudge_content=None,
        seekho_content=None,
        final_response="",
        final_response_translated="",
    )


async def _run_pipeline(user_id: str, initial_state: AgentState) -> None:
    """
    Invoke the LangGraph pipeline and send the reply to WhatsApp.

    Runs as a FastAPI BackgroundTask — errors are logged but not re-raised
    so they don't affect the 200 response already sent to Meta.
    """
    start = time.monotonic()
    logger.info("=== Pipeline START  user=%s ===", user_id)

    try:
        result: AgentState = await asyncio.wait_for(
            langgraph_app.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": user_id}},
            ),
            timeout=_PIPELINE_TIMEOUT,
        )
        elapsed = time.monotonic() - start
        reply = result.get("final_response_translated", "").strip()
        if reply:
            await send_message(to=user_id, text=reply)
            logger.info("=== Pipeline DONE   user=%s  elapsed=%.1fs ===", user_id, elapsed)
        else:
            logger.warning("=== Pipeline produced no reply for user=%s ===", user_id)

    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        logger.error("=== Pipeline TIMEOUT after %.0fs for user=%s ===", elapsed, user_id)
        try:
            await send_message(
                to=user_id,
                text="Thoda time lag raha hai, please dobara bhejein. "
                     "(Taking too long, please send again.)",
            )
        except Exception:
            logger.exception("Failed to send timeout message to %s", user_id)

    except Exception:
        elapsed = time.monotonic() - start
        logger.exception("=== Pipeline ERROR  user=%s  elapsed=%.1fs ===", user_id, elapsed)
        try:
            await send_message(
                to=user_id,
                text="Kuch problem aayi. Thodi der baad dobara bhejein. "
                     "(Something went wrong. Please try again in a moment.)",
            )
        except Exception:
            logger.exception("Failed to send fallback message to %s", user_id)


def _parse_incoming(body: dict) -> list[dict]:
    """
    Extract a flat list of message dicts from the raw Meta webhook payload.
    Silently skips status updates (delivered/read receipts) and other non-message events.
    """
    messages = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                messages.append({
                    "user_id": msg.get("from"),
                    "type": msg.get("type"),
                    "text": msg.get("text", {}).get("body", ""),
                    "audio_id": msg.get("audio", {}).get("id"),
                    "audio_mime": msg.get("audio", {}).get("mime_type", "audio/ogg"),
                })
    return messages


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
) -> str:
    """
    Meta Cloud API webhook verification handshake.
    Returns the challenge string if the verify token matches.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("WhatsApp webhook verified successfully.")
        return hub_challenge
    raise HTTPException(status_code=403, detail="Webhook verification failed.")


@router.post("/webhook", status_code=200)
async def receive_message(request: Request, background_tasks: BackgroundTasks) -> dict:
    """
    Receive incoming WhatsApp messages and trigger the LangGraph pipeline.

    Returns 200 immediately — pipeline runs in the background.
    """
    body = await request.json()

    if body.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}

    messages = _parse_incoming(body)

    for msg in messages:
        user_id: str | None = msg.get("user_id")
        if not user_id:
            continue

        msg_type = msg.get("type", "text")

        if msg_type == "text":
            state = _build_initial_state(
                user_id=user_id,
                raw_message=msg.get("text", ""),
                message_type="text",
            )
            background_tasks.add_task(_run_pipeline, user_id, state)

        elif msg_type == "audio":
            audio_id = msg.get("audio_id")
            if not audio_id:
                continue
            # Download audio bytes before handing off to background task
            try:
                audio_bytes, audio_mime = await download_audio(audio_id)
            except Exception:
                logger.exception("Failed to download audio from user %s", user_id)
                continue

            state = _build_initial_state(
                user_id=user_id,
                raw_message="",
                message_type="audio",
                audio_bytes=audio_bytes,
                audio_mime_type=audio_mime,
            )
            background_tasks.add_task(_run_pipeline, user_id, state)

        else:
            # Unsupported message type (image, document, sticker, etc.)
            logger.info("Unsupported message type '%s' from %s", msg_type, user_id)

    return {"status": "ok"}
