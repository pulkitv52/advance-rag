import axios from "axios"

export interface TTSRequestPayload {
  text: string
  target_language_code?: string
  speaker?: string
  model?: string
  pace?: number
  speech_sample_rate?: number
  output_audio_codec?: string
  enable_preprocessing?: boolean
}

export const requestTTSAudio = async (apiBaseUrl: string, payload: TTSRequestPayload): Promise<Blob> => {
  const res = await axios.post(`${apiBaseUrl}/api/voice/tts`, payload, { responseType: "blob" })
  return res.data as Blob
}

export interface STTRequestPayload {
  file: Blob
  filename?: string
  model?: string
  mode?: string
  language_code?: string
}

export const requestSTTTranscript = async (
  apiBaseUrl: string,
  payload: STTRequestPayload,
): Promise<{ transcript: string; raw: any }> => {
  const formData = new FormData()
  formData.append("file", payload.file, payload.filename || "speech.webm")
  formData.append("model", payload.model || "saaras:v3")
  formData.append("mode", payload.mode || "transcribe")
  if (payload.language_code) formData.append("language_code", payload.language_code)

  const res = await axios.post(`${apiBaseUrl}/api/voice/stt`, formData)
  const raw = res.data || {}
  const transcript =
    raw.transcript ||
    raw.text ||
    raw.output_text ||
    raw.result?.transcript ||
    raw.data?.transcript ||
    ""

  return { transcript: String(transcript || "").trim(), raw }
}

const writeString = (view: DataView, offset: number, value: string): void => {
  for (let i = 0; i < value.length; i += 1) {
    view.setUint8(offset + i, value.charCodeAt(i))
  }
}

const audioBufferToWavBlob = (audioBuffer: AudioBuffer): Blob => {
  const numberOfChannels = Math.min(audioBuffer.numberOfChannels, 2)
  const sampleRate = audioBuffer.sampleRate
  const format = 1 // PCM
  const bitDepth = 16

  const channelData = Array.from({ length: numberOfChannels }, (_, i) => audioBuffer.getChannelData(i))
  const blockAlign = (numberOfChannels * bitDepth) / 8
  const byteRate = sampleRate * blockAlign
  const dataLength = audioBuffer.length * blockAlign
  const buffer = new ArrayBuffer(44 + dataLength)
  const view = new DataView(buffer)

  writeString(view, 0, "RIFF")
  view.setUint32(4, 36 + dataLength, true)
  writeString(view, 8, "WAVE")
  writeString(view, 12, "fmt ")
  view.setUint32(16, 16, true)
  view.setUint16(20, format, true)
  view.setUint16(22, numberOfChannels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, byteRate, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, bitDepth, true)
  writeString(view, 36, "data")
  view.setUint32(40, dataLength, true)

  let offset = 44
  for (let i = 0; i < audioBuffer.length; i += 1) {
    for (let ch = 0; ch < numberOfChannels; ch += 1) {
      const sample = Math.max(-1, Math.min(1, channelData[ch][i]))
      const pcm = sample < 0 ? sample * 0x8000 : sample * 0x7fff
      view.setInt16(offset, pcm, true)
      offset += 2
    }
  }

  return new Blob([buffer], { type: "audio/wav" })
}

export const convertAudioBlobToWav = async (inputBlob: Blob): Promise<Blob> => {
  const arrayBuffer = await inputBlob.arrayBuffer()
  const audioContext = new AudioContext()
  try {
    const decoded = await audioContext.decodeAudioData(arrayBuffer.slice(0))
    return audioBufferToWavBlob(decoded)
  } finally {
    await audioContext.close()
  }
}
