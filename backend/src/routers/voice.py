from __future__ import annotations

import io
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.services import sarvam_voice

router = APIRouter(prefix="/api/voice", tags=["Voice"])


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    target_language_code: str = Field(default="en-IN")
    speaker: str = Field(default="shubh")
    model: str = Field(default="bulbul:v3")
    pace: float = Field(default=1.0, ge=0.5, le=2.0)
    speech_sample_rate: int = Field(default=22050)
    output_audio_codec: str = Field(default="mp3")
    enable_preprocessing: bool = Field(default=True)


@router.post("/tts", summary="Generate TTS audio using Sarvam")
async def tts(request: TTSRequest):
    try:
        audio_bytes, media_type = await sarvam_voice.synthesize_tts_stream(
            text=request.text,
            target_language_code=request.target_language_code,
            speaker=request.speaker,
            model=request.model,
            pace=request.pace,
            speech_sample_rate=request.speech_sample_rate,
            output_audio_codec=request.output_audio_codec,
            enable_preprocessing=request.enable_preprocessing,
        )
    except sarvam_voice.SarvamVoiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    filename = f"tts_output.{request.output_audio_codec.lower()}"
    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/stt", summary="Transcribe uploaded audio using Sarvam")
async def stt(
    file: UploadFile = File(...),
    model: str = Form(default="saaras:v3"),
    mode: str = Form(default="transcribe"),
    language_code: Optional[str] = Form(default=None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Audio filename is required.")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    try:
        response = await sarvam_voice.transcribe_stt(
            audio_bytes=audio_bytes,
            filename=file.filename,
            content_type=file.content_type or "audio/webm",
            model=model,
            mode=mode,
            language_code=language_code,
        )
    except sarvam_voice.SarvamVoiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return response
