import asyncio
import json
import logging
import os
import tempfile

import boto3
import httpx
from botocore.exceptions import ClientError

from utils.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 5.0


def _get_bedrock_client():
    return boto3.client(
        service_name="bedrock-runtime",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


async def _invoke_bedrock(body: dict) -> dict:
    def _call():
        client = _get_bedrock_client()
        response = client.invoke_model(
            modelId=settings.bedrock_model_id,
            body=json.dumps(body),
        )
        return json.loads(response["body"].read())

    for attempt in range(_MAX_RETRIES):
        try:
            return await asyncio.to_thread(_call)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "ThrottlingException" and attempt < _MAX_RETRIES - 1:
                logger.warning("Bedrock throttled — retry %d/%d", attempt + 2, _MAX_RETRIES)
                await asyncio.sleep(_RETRY_DELAY)
            else:
                raise


async def generate_text(prompt: str, system_instruction: str | None = None) -> str:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_instruction:
        body["system"] = system_instruction

    result = await _invoke_bedrock(body)
    return result["content"][0]["text"].strip()


async def generate_json(
    prompt: str,
    system_instruction: str | None = None,
    response_schema=None,
) -> dict | list:
    json_instruction = "Respond with valid JSON only. No explanation, no markdown."
    system = f"{system_instruction}\n\n{json_instruction}" if system_instruction else json_instruction

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0.1,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }

    result = await _invoke_bedrock(body)
    return json.loads(result["content"][0]["text"].strip())


async def get_embedding(text: str) -> list[float]:
    def _call():
        client = _get_bedrock_client()
        response = client.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=json.dumps({"inputText": text}),
        )
        return json.loads(response["body"].read())["embedding"]

    return await asyncio.to_thread(_call)


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    extension = mime_type.split("/")[-1]

    with tempfile.NamedTemporaryFile(suffix=f".{extension}", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        async with httpx.AsyncClient() as client:
            with open(tmp_path, "rb") as audio_file:
                response = await client.post(
                    "https://api.sarvam.ai/speech-to-text",
                    headers={"api-subscription-key": settings.sarvam_api_key},
                    files={"file": (f"audio.{extension}", audio_file, mime_type)},
                    data={"model": "saarika:v2"},
                    timeout=30.0,
                )
        response.raise_for_status()
        return response.json().get("transcript", "").strip()
    finally:
        os.remove(tmp_path)
