import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiClientError } from '../api/client'
import { cancelIntent, confirmIntent, parseIntent, type IntentParseResponse } from '../api/intent'
import { speakText, transcribeAudio } from '../api/voice'
import { playSpeakableChunks } from '../audio/ttsSession'
import { maybeNotifyShopMutation } from '../lib/shopRecords'
import { sttLanguageForMode } from '../lib/languagePreference'
import { ttsLanguage } from '../lib/ttsLanguage'
import { applyTtsPlayback } from '../lib/ttsPlayback'
import {
  AdaptiveVad,
  MAX_BUFFER_SAMPLES,
  POST_TTS_COOLDOWN_MS,
  downsampleTo16k,
  openMicrophone,
  rms,
} from '../audio/vad'
import { encodeWav } from '../audio/wav'

export type VoiceSessionState =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'processing'
  | 'speaking'
  | 'interrupted'
  | 'reconnecting'
  | 'error'

export type ChatLine = { role: 'user' | 'assistant'; text: string; visualization?: unknown }

type Rec = {
  stream: MediaStream
  context: AudioContext
  processor: ScriptProcessorNode
  source: MediaStreamAudioSourceNode
}

export function useVoiceSession(open: boolean, languageMode: string = 'auto') {
  const [state, setState] = useState<VoiceSessionState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [level, setLevel] = useState(0)
  const [lines, setLines] = useState<ChatLine[]>([])
  const [pending, setPending] = useState<IntentParseResponse | null>(null)
  const [turn, setTurn] = useState(0)

  const recRef = useRef<Rec | null>(null)
  const chunksRef = useRef<Float32Array[]>([])
  const chunkSamplesRef = useRef(0)
  const stateRef = useRef<VoiceSessionState>('idle')
  const turnRef = useRef(0)
  const speechMsRef = useRef(0)
  const silenceMsRef = useRef(0)
  const utteredRef = useRef(false)
  const startedAtRef = useRef(0)
  const coolUntilRef = useRef(0)
  const sendingRef = useRef(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const objectUrlRef = useRef<string | null>(null)
  const playWaitRef = useRef<(() => void) | null>(null)
  const vadEosAtRef = useRef(0)
  const closedRef = useRef(false)
  const sessionIdRef = useRef('')
  const vadRef = useRef(new AdaptiveVad())
  const lastLangRef = useRef('en')
  const languageModeRef = useRef(languageMode)
  languageModeRef.current = languageMode
  const pendingRef = useRef<IntentParseResponse | null>(null)
  const onFrameRef = useRef<(frame: Float32Array, sampleRate: number) => void>(() => {})

  const setS = (s: VoiceSessionState) => {
    stateRef.current = s
    setState(s)
  }

  const bumpTurn = () => {
    turnRef.current += 1
    setTurn(turnRef.current)
    return turnRef.current
  }

  const stopPlayback = () => {
    const el = audioRef.current
    if (el) {
      el.pause()
      el.src = ''
      audioRef.current = null
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    const done = playWaitRef.current
    playWaitRef.current = null
    if (done) done()
  }

  const teardownMic = async () => {
    const rec = recRef.current
    recRef.current = null
    chunksRef.current = []
    chunkSamplesRef.current = 0
    if (!rec) return
    try {
      rec.processor.disconnect()
      rec.source.disconnect()
    } catch {
      /* ignore */
    }
    rec.stream.getTracks().forEach((t) => t.stop())
    try {
      await rec.context.close()
    } catch {
      /* ignore */
    }
  }

  const takePcm = () => {
    const parts = chunksRef.current
    chunksRef.current = []
    chunkSamplesRef.current = 0
    const n = parts.reduce((a, p) => a + p.length, 0)
    const merged = new Float32Array(n)
    let o = 0
    for (const p of parts) {
      merged.set(p, o)
      o += p.length
    }
    return merged
  }

  const listenReset = (recalibrate = false) => {
    chunksRef.current = []
    chunkSamplesRef.current = 0
    speechMsRef.current = 0
    silenceMsRef.current = 0
    utteredRef.current = false
    startedAtRef.current = Date.now()
    sendingRef.current = false
    if (recalibrate) vadRef.current.recalibrate()
    else vadRef.current.resetUtterance()
  }

  const playChunk = (blob: Blob) =>
    new Promise<void>((resolve) => {
      stopPlayback()
      const url = URL.createObjectURL(blob)
      objectUrlRef.current = url
      const el = new Audio()
      audioRef.current = el
      el.src = url
      applyTtsPlayback(el)
      const done = () => {
        if (playWaitRef.current === done) playWaitRef.current = null
        if (objectUrlRef.current === url) {
          URL.revokeObjectURL(url)
          objectUrlRef.current = null
        }
        if (audioRef.current === el) {
          el.onended = null
          el.onerror = null
          audioRef.current = null
        }
        resolve()
      }
      playWaitRef.current = done
      el.onended = done
      el.onerror = done
      void el.play().catch(() => done())
    })

  const playAndListen = useCallback(async (myTurn: number, text: string, language: string) => {
    if (closedRef.current || myTurn !== turnRef.current) return
    if (!text.trim()) {
      coolUntilRef.current = Date.now() + POST_TTS_COOLDOWN_MS
      listenReset()
      setS('listening')
      return
    }
    setS('speaking')
    try {
      const timings = await playSpeakableChunks({
        text,
        language,
        turn: myTurn,
        isCurrent: (t) => !closedRef.current && t === turnRef.current,
        speak: speakText,
        play: playChunk,
      })
      console.info('[voice-timing]', {
        first_tts_request_ms: timings.first_tts_request_ms,
        first_tts_complete_ms: timings.first_tts_complete_ms,
        first_play_start_ms: timings.first_play_start_ms,
        playback_total_ms: timings.playback_total_ms,
        tts_requests: timings.tts_requests,
        chunks: timings.chunks,
        skipped: timings.skipped,
        inter_sentence_gap_ms: timings.inter_sentence_gap_ms,
      })
    } catch {
      /* show text even if TTS fails */
    } finally {
      stopPlayback()
    }
    if (closedRef.current || myTurn !== turnRef.current) return
    coolUntilRef.current = Date.now() + POST_TTS_COOLDOWN_MS
    listenReset()
    setS('listening')
  }, [])

  const runTurn = useCallback(
    async (pcm: Float32Array, sampleRate: number) => {
      const myTurn = bumpTurn()
      sendingRef.current = true
      setS('processing')
      try {
        const at16 = downsampleTo16k(pcm, sampleRate)
        const wav = encodeWav(at16, 16000)
        if (wav.size < 200) {
          listenReset()
          setS('listening')
          return
        }
        let stt
        try {
          const t2 = performance.now()
          const vadToStt = vadEosAtRef.current ? Math.round(t2 - vadEosAtRef.current) : null
          stt = await transcribeAudio(wav, sttLanguageForMode(languageModeRef.current as 'auto' | 'en' | 'hi' | 'kn' | 'mr'))
          console.info(
            `[voice-timing] vad_eos_to_stt_start_ms=${vadToStt} stt_ms=${Math.round(performance.now() - t2)}`,
          )
        } catch (err) {
          if (err instanceof ApiClientError && err.code === 'empty_transcript') {
            const msg =
              lastLangRef.current === 'hi'
                ? 'साफ़ नहीं सुना। कृपया एक बार फिर कहें।'
                : lastLangRef.current === 'kn'
                  ? 'ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ.'
                  : lastLangRef.current === 'mr'
                    ? 'स्पष्ट ऐकू आले नाही. कृपया पुन्हा सांगा.'
                    : "I couldn't hear that clearly. Could you repeat it?"
            setLines((prev) => [...prev, { role: 'assistant', text: msg }])
            await playAndListen(myTurn, msg, lastLangRef.current)
            return
          }
          throw err
        }
        if (closedRef.current || myTurn !== turnRef.current) return
        const said = stt.transcript.trim()
        if (!said) {
          listenReset()
          setS('listening')
          return
        }
        setLines((prev) => [...prev, { role: 'user', text: said }])
        const t3 = performance.now()
        const parsed = await parseIntent(said, sessionIdRef.current, languageModeRef.current)
        const t4 = performance.now()
        if (closedRef.current || myTurn !== turnRef.current) return
        const reply = (parsed.reply_text || parsed.message || '').trim()
        const lang = ttsLanguage(parsed.reply_language, lastLangRef.current)
        lastLangRef.current = lang
        const priorIntent = pendingRef.current?.intent
        if (parsed.needs_confirmation && parsed.pending_id) {
          pendingRef.current = parsed
          setPending(parsed)
        } else {
          pendingRef.current = null
          setPending(null)
        }
        maybeNotifyShopMutation({
          executed: parsed.executed,
          intent: parsed.intent,
          pendingIntent: priorIntent,
        })
        if (reply)
          setLines((prev) => [
            ...prev,
            { role: 'assistant', text: reply, visualization: parsed.visualization },
          ])
        console.info(
          `[voice-timing] intent_ms=${Math.round(t4 - t3)} text_ready_ms=${Math.round(t4 - t3)} reply_chars=${reply.length}`,
        )
        await playAndListen(myTurn, reply, lang)
      } catch (err) {
        if (closedRef.current || myTurn !== turnRef.current) return
        const msg = err instanceof ApiClientError ? err.message : 'Could not process speech.'
        setError(msg)
        setS('error')
        coolUntilRef.current = Date.now() + 800
        listenReset()
        window.setTimeout(() => {
          if (!closedRef.current && stateRef.current === 'error') {
            setError(null)
            setS('listening')
          }
        }, 1600)
      } finally {
        sendingRef.current = false
      }
    },
    [playAndListen],
  )

  const onFrame = useCallback(
    (frame: Float32Array, sampleRate: number) => {
      const now = Date.now()
      const energy = rms(frame)
      setLevel(energy)
      const st = stateRef.current
      const ms = (frame.length / sampleRate) * 1000
      const d = vadRef.current.process(energy, ms, {
        speaking: st === 'speaking',
        cooldown: now < coolUntilRef.current,
      })
      if (d.barge) {
        setS('interrupted')
        bumpTurn()
        stopPlayback()
        listenReset()
        chunksRef.current = [new Float32Array(frame)]
        chunkSamplesRef.current = frame.length
        utteredRef.current = true
        setS('listening')
        return
      }
      if (st !== 'listening' || sendingRef.current) return
      if (now < coolUntilRef.current) return
      if (!d.keepFrame && !d.inSpeech) {
        chunksRef.current = []
        chunkSamplesRef.current = 0
        return
      }
      if (chunkSamplesRef.current + frame.length > MAX_BUFFER_SAMPLES) {
        chunksRef.current.shift()
        chunkSamplesRef.current = chunksRef.current.reduce((a, p) => a + p.length, 0)
      }
      chunksRef.current.push(new Float32Array(frame))
      chunkSamplesRef.current += frame.length
      if (!d.inSpeech && !d.end) {
        const maxPre = Math.floor(sampleRate * 0.22)
        while (chunkSamplesRef.current > maxPre && chunksRef.current.length > 1) {
          const drop = chunksRef.current.shift()
          chunkSamplesRef.current -= drop?.length ?? 0
        }
      }
      if (d.end) {
        vadEosAtRef.current = performance.now()
        const pcm = takePcm()
        void runTurn(pcm, sampleRate)
      }
    },
    [runTurn],
  )
  onFrameRef.current = onFrame

  const startMic = useCallback(async () => {
    closedRef.current = false
    if (!sessionIdRef.current) {
      sessionIdRef.current =
        typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : `s-${Date.now()}`
    }
    setError(null)
    setS('connecting')
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('This browser cannot use the microphone.')
      setS('error')
      return
    }
    let stream: MediaStream
    try {
      const opened = await openMicrophone()
      stream = opened.stream
    } catch {
      setError('Microphone permission was denied. Enable it in the browser settings.')
      setS('error')
      return
    }
    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    const context = new Ctx()
    const source = context.createMediaStreamSource(stream)
    const processor = context.createScriptProcessor(4096, 1, 1)
    processor.onaudioprocess = (ev) => {
      onFrameRef.current(ev.inputBuffer.getChannelData(0), context.sampleRate)
    }
    source.connect(processor)
    const mute = context.createGain()
    mute.gain.value = 0
    processor.connect(mute)
    mute.connect(context.destination)
    recRef.current = { stream, context, processor, source }
    listenReset(true)
    coolUntilRef.current = Date.now() + 400
    setS('listening')
  }, [])

  const close = useCallback(async () => {
    closedRef.current = true
    bumpTurn()
    stopPlayback()
    await teardownMic()
    sessionIdRef.current = ''
    pendingRef.current = null
    setPending(null)
    setLines([])
    setLevel(0)
    setError(null)
    setS('idle')
  }, [])

  useEffect(() => {
    if (open) void startMic()
    else void close()
    return () => {
      closedRef.current = true
      stopPlayback()
      void teardownMic()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const onConfirm = async () => {
    const current = pendingRef.current || pending
    if (!current?.pending_id) return
    const myTurn = bumpTurn()
    const lang = ttsLanguage(current.reply_language, lastLangRef.current)
    setS('processing')
    try {
      const res = await confirmIntent(current.pending_id, sessionIdRef.current)
      pendingRef.current = null
      setPending(null)
      maybeNotifyShopMutation({
        executed: res.executed,
        intent: res.intent,
        pendingIntent: current.intent,
      })
      const msg = res.message || 'Done.'
      setLines((prev) => [...prev, { role: 'assistant', text: msg }])
      await playAndListen(myTurn, msg, lang)
    } catch (err) {
      const msg = err instanceof ApiClientError ? err.message : 'Could not confirm.'
      setError(msg)
      setS('error')
    }
  }

  const onCancel = async () => {
    const current = pendingRef.current || pending
    if (!current?.pending_id) return
    const myTurn = bumpTurn()
    const lang = ttsLanguage(current.reply_language, lastLangRef.current)
    try {
      const res = await cancelIntent(current.pending_id)
      pendingRef.current = null
      setPending(null)
      const msg = res.message || 'Cancelled.'
      setLines((prev) => [...prev, { role: 'assistant', text: msg }])
      await playAndListen(myTurn, msg, lang)
    } catch {
      pendingRef.current = null
      setPending(null)
      listenReset()
      setS('listening')
    }
  }

  return {
    state,
    error,
    level,
    lines,
    pending,
    turn,
    onConfirm,
    onCancel,
    close,
  }
}
