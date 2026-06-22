"""
WhatsApp Business API client (Meta Cloud).

Provides two async functions:
  send_message()    — send a text reply to a user
  download_audio()  — download voice note bytes from the WhatsApp media endpoint
"""

import httpx

from utils.config import settings

_BASE_URL = "https://graph.facebook.com/v20.0"
_HEADERS = {
    "Authorization": f"Bearer {settings.whatsapp_token}",
    "Content-Type": "application/json",
}


async def send_message(to: str, text: str) -> None:
    """
    Send a text message to a WhatsApp user via Meta Cloud API.

    Args:
        to:   Recipient phone number in E.164 format (e.g. "919876543210").
        text: Message body (already translated to user's language).
    """
    url = f"{_BASE_URL}/{settings.whatsapp_phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text,
        },
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload, headers=_HEADERS)
        response.raise_for_status()


async def download_audio(media_id: str) -> tuple[bytes, str]:
    """
    Download a WhatsApp voice note by its media_id.

    Meta requires two steps:
      1. GET /{media_id} → resolves to a temporary download URL
      2. GET {download_url} → returns the raw audio bytes

    Args:
        media_id: The media object ID from the incoming webhook payload.

    Returns:
        Tuple of (audio_bytes, mime_type) e.g. (b"...", "audio/ogg; codecs=opus")
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: resolve the media URL
        meta_resp = await client.get(
            f"{_BASE_URL}/{media_id}",
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()

        download_url: str = meta["url"]
        mime_type: str = meta.get("mime_type", "audio/ogg")

        # Step 2: download the audio bytes
        audio_resp = await client.get(
            download_url,
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
        )
        audio_resp.raise_for_status()

    return audio_resp.content, mime_type
