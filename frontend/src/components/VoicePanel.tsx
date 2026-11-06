import { useEffect, useRef, useState } from 'react'
import { ApiClientError } from '../api/client'
import { transcribeAudio } from '../api/voice'
import { encodeWav } from '../audio/wav'

const LANGUAGES = [
  { value: 'auto', label: 'Automatic' },
  { value: 'kn-IN', label: 'Kannada' },
  { value: 'hi-IN', label: 'Hindi' },
  { value: 'en-IN', label: 'English' },
  { value: 'mr-IN', label: 'Marathi' },
] as const

const MAX_SECONDS = 30

type Result = {
  transcript: string
  detected_language: string | null
  model: string
  request_id: string | null
  processing_time: number
}

export function VoicePanel() {
  const [language, setLanguage] = useState<string>('auto')
  const [recording, setRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const recRef = useRef<{
    stop: () => Promise<Blob>
  } | null>(null)
  const timerRef = useRef<number | null>(null)
  const submitting = useRef(false)

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
    }
  }, [])

  async function startRecording() {
    setError(null)
    setResult(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('This browser cannot record audio.')
      return
    }
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      setError('Microphone permission was denied. Enable it in the browser settings.')
      return
    }

    const AudioContextClass =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    if (!AudioContextClass) {
      stream.getTracks().forEach((t) => t.stop())
      setError('This browser cannot record WAV audio for speech recognition.')
      return
    }

    const context = new AudioContextClass()
    const source = context.createMediaStreamSource(stream)
    const processor = context.createScriptProcessor(4096, 1, 1)
    const chunks: Float32Array[] = []
    processor.onaudioprocess = (event) => {
      chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)))
    }
    source.connect(processor)
    processor.connect(context.destination)

    recRef.current = {
      stop: async () => {
        processor.disconnect()
        source.disconnect()
        stream.getTracks().forEach((t) => t.stop())
        const rate = context.sampleRate
        await context.close()
        const length = chunks.reduce((n, c) => n + c.length, 0)
        const merged = new Float32Array(length)
        let offset = 0
        for (const part of chunks) {
          merged.set(part, offset)
          offset += part.length
        }
        return encodeWav(merged, rate)
      },
    }

    setRecording(true)
    setElapsed(0)
    const started = Date.now()
    timerRef.current = window.setInterval(() => {
      const sec = (Date.now() - started) / 1000
      setElapsed(sec)
      if (sec >= MAX_SECONDS) {
        void stopAndSend()
      }
    }, 200)
  }

  async function stopAndSend() {
    if (submitting.current) return
    submitting.current = true
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    setRecording(false)
    const rec = recRef.current
    recRef.current = null
    if (!rec) {
      submitting.current = false
      return
    }
    setBusy(true)
    try {
      const blob = await rec.stop()
      if (blob.size < 100) {
        setError('Recording is empty. Hold the microphone and speak, then stop.')
        return
      }
      const data = await transcribeAudio(blob, language)
      setResult({
        transcript: data.transcript,
        detected_language: data.detected_language,
        model: data.model,
        request_id: data.request_id,
        processing_time: data.processing_time,
      })
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message)
      } else {
        setError('Could not transcribe the recording.')
      }
    } finally {
      setBusy(false)
      submitting.current = false
    }
  }

  return (
    <section className="rounded-2xl border border-stone-300 bg-white p-5 shadow-sm">
      <h2 className="text-xl font-medium">Voice (Prisma STT)</h2>
      <p className="mt-2 text-stone-700">
        Recording uses the microphone only. Speech-to-text runs on the Flask server via Gnani Prisma
        V3. Transcripts are not used for sales yet.
      </p>

      <label className="mt-4 block text-lg">
        Language
        <select
          className="mt-1 min-h-12 w-full rounded-xl border border-stone-300 bg-white px-3 text-lg"
          value={language}
          disabled={recording || busy}
          onChange={(e) => setLanguage(e.target.value)}
        >
          {LANGUAGES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>

      <div className="mt-6 flex flex-col items-center gap-3">
        {recording && (
          <p className="text-lg font-medium text-red-800" role="status">
            Recording… {elapsed.toFixed(1)}s / {MAX_SECONDS}s
          </p>
        )}
        {!recording && (
          <button
            type="button"
            className="min-h-24 min-w-24 rounded-full bg-amber-700 px-6 text-xl font-semibold text-white"
            onClick={() => void startRecording()}
            disabled={busy}
          >
            Mic
          </button>
        )}
        {recording && (
          <button
            type="button"
            className="min-h-14 w-full rounded-xl bg-stone-800 px-4 text-lg font-medium text-white"
            onClick={() => void stopAndSend()}
            disabled={busy}
          >
            Stop and transcribe
          </button>
        )}
      </div>

      {busy && (
        <p className="mt-4 text-lg" role="status">
          Sending audio to VyaparMitra…
        </p>
      )}
      {error && (
        <p className="mt-4 text-lg text-red-800" role="alert">
          {error}
        </p>
      )}
      {result && (
        <dl className="mt-4 grid gap-2 text-lg">
          <div>
            <dt className="text-stone-500">Transcript</dt>
            <dd className="font-medium">{result.transcript}</dd>
          </div>
          <div>
            <dt className="text-stone-500">Detected language</dt>
            <dd>{result.detected_language ?? 'not returned'}</dd>
          </div>
          <div>
            <dt className="text-stone-500">Model</dt>
            <dd>{result.model}</dd>
          </div>
          <div>
            <dt className="text-stone-500">Request ID</dt>
            <dd>{result.request_id ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-stone-500">Processing time</dt>
            <dd>{result.processing_time}s</dd>
          </div>
        </dl>
      )}
    </section>
  )
}
