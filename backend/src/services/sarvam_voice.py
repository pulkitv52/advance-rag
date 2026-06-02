from __future__ import annotations

import re
from typing import Any, Optional

import httpx

from src.core.config import get_settings

settings = get_settings()


class SarvamVoiceError(Exception):
    pass


def _auth_headers() -> dict[str, str]:
    if not settings.SARVAM_API_KEY:
        raise SarvamVoiceError("SARVAM_API_KEY is missing. Set it in your .env file.")
    return {"api-subscription-key": settings.SARVAM_API_KEY}


async def synthesize_tts_stream(
    *,
    text: str,
    target_language_code: str = "en-IN",
    speaker: str = "shubh",
    model: str = "bulbul:v3",
    pace: float = 1.0,
    speech_sample_rate: int = 22050,
    output_audio_codec: str = "mp3",
    enable_preprocessing: bool = True,
) -> tuple[bytes, str]:
    def _normalize_text(raw: str) -> str:
        cleaned = re.sub(r"\s+", " ", (raw or "").strip())
        return cleaned

    def _chunk_text(raw: str, max_chars: int = 1100) -> list[str]:
        text_value = _normalize_text(raw)
        if len(text_value) <= max_chars:
            return [text_value]
        parts: list[str] = []
        cursor = 0
        while cursor < len(text_value):
            end = min(cursor + max_chars, len(text_value))
            if end < len(text_value):
                split_at = text_value.rfind(". ", cursor, end)
                if split_at == -1:
                    split_at = text_value.rfind("; ", cursor, end)
                if split_at == -1:
                    split_at = text_value.rfind(", ", cursor, end)
                if split_at != -1 and split_at > cursor + 200:
                    end = split_at + 1
            chunk = text_value[cursor:end].strip()
            if chunk:
                parts.append(chunk)
            cursor = end
        return parts or [text_value]

    headers = {**_auth_headers(), "Content-Type": "application/json"}
    chunks = _chunk_text(text, max_chars=1100)
    audio_parts: list[bytes] = []
    primary_error: Optional[str] = None

    async with httpx.AsyncClient(timeout=90.0) as client:
        for chunk in chunks:
            payload = {
                "text": chunk,
                "target_language_code": target_language_code,
                "speaker": speaker,
                "model": model,
                "pace": pace,
                "speech_sample_rate": speech_sample_rate,
                "output_audio_codec": output_audio_codec,
                "enable_preprocessing": enable_preprocessing,
            }
            try:
                response = await client.post(settings.SARVAM_TTS_STREAM_URL, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                raise SarvamVoiceError(f"Sarvam TTS request failed: {exc}") from exc

            if response.status_code >= 400:
                primary_error = f"{response.status_code}: {response.text[:220]}"
                fallback_payload = {
                    **payload,
                    "speaker": "anushka",
                    "model": "bulbul:v2",
                    "pace": 1.0,
                    "target_language_code": target_language_code or "en-IN",
                }
                try:
                    fallback_response = await client.post(
                        settings.SARVAM_TTS_STREAM_URL, headers=headers, json=fallback_payload
                    )
                except httpx.HTTPError as exc:
                    raise SarvamVoiceError(f"Sarvam TTS fallback request failed: {exc}") from exc

                if fallback_response.status_code >= 400:
                    raise SarvamVoiceError(
                        "Sarvam TTS failed. "
                        f"Primary ({primary_error}) | "
                        f"Fallback ({fallback_response.status_code}: {fallback_response.text[:220]})"
                    )
                audio_parts.append(fallback_response.content)
                continue

            audio_parts.append(response.content)

    codec = (output_audio_codec or "mp3").lower()
    media_type = f"audio/{codec if codec != 'mp3' else 'mpeg'}"
    return b"".join(audio_parts), media_type


async def transcribe_stt(
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    model: str = "saaras:v3",
    mode: str = "transcribe",
    language_code: Optional[str] = None,
) -> dict[str, Any]:
    headers = _auth_headers()
    normalized_content_type = content_type or "audio/webm"
    files = {"file": (filename, audio_bytes, normalized_content_type)}
    data: dict[str, Any] = {"model": model, "mode": mode}
    if language_code:
        data["language_code"] = language_code
    else:
        data["language_code"] = "unknown"

    codec_by_content_type = {
        "audio/webm": "webm",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/mp4": "mp4",
        "audio/aac": "aac",
        "audio/ogg": "ogg",
        "audio/opus": "opus",
    }
    if normalized_content_type in codec_by_content_type:
        data["input_audio_codec"] = codec_by_content_type[normalized_content_type]

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(settings.SARVAM_STT_URL, headers=headers, data=data, files=files)
    except httpx.HTTPError as exc:
        raise SarvamVoiceError(f"Sarvam STT request failed: {exc}") from exc

    # Fallback: if strict payload fails, retry with minimal fields accepted by REST STT.
    if response.status_code >= 400:
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                fallback_data = {"model": "saarika:v2.5"}
                fallback_response = await client.post(
                    settings.SARVAM_STT_URL,
                    headers=headers,
                    data=fallback_data,
                    files=files,
                )
        except httpx.HTTPError as exc:
            raise SarvamVoiceError(f"Sarvam STT request failed: {exc}") from exc

        if fallback_response.status_code >= 400:
            raise SarvamVoiceError(
                "Sarvam STT failed. "
                f"Primary ({response.status_code}): {response.text[:220]} | "
                f"Fallback ({fallback_response.status_code}): {fallback_response.text[:220]}"
            )
        response = fallback_response

    try:
        return response.json()
    except ValueError as exc:
        raise SarvamVoiceError("Sarvam STT returned a non-JSON response.") from exc
