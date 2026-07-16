import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

interface SpeechAlternativeLike {
  transcript: string
}

interface SpeechResultLike {
  0: SpeechAlternativeLike
  isFinal: boolean
}

interface SpeechResultListLike {
  [index: number]: SpeechResultLike
  length: number
}

interface SpeechResultEventLike extends Event {
  resultIndex: number
  results: SpeechResultListLike
}

interface SpeechErrorEventLike extends Event {
  error: string
}

interface SpeechRecognitionLike {
  continuous: boolean
  interimResults: boolean
  lang: string
  maxAlternatives: number
  onend: (() => void) | null
  onerror: ((event: SpeechErrorEventLike) => void) | null
  onresult: ((event: SpeechResultEventLike) => void) | null
  onstart: (() => void) | null
  abort(): void
  start(): void
  stop(): void
}

interface SpeechRecognitionConstructorLike {
  new (): SpeechRecognitionLike
}

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructorLike
    webkitSpeechRecognition?: SpeechRecognitionConstructorLike
  }
}

type VoiceStatus = 'idle' | 'requesting' | 'listening' | 'stopping' | 'error'

function describeSpeechError(error: string): string {
  if (error === 'not-allowed' || error === 'service-not-allowed') {
    return 'Microphone access was blocked. Allow microphone access in the browser and try again.'
  }
  if (error === 'audio-capture') {
    return 'No working microphone was found. Check the selected input device and try again.'
  }
  if (error === 'network') {
    return 'Live transcription could not reach the browser speech service. Check the connection and try again.'
  }
  return 'Live transcription stopped unexpectedly. You can keep the captured text and try again.'
}

export function useLiveTranscription() {
  const [status, setStatus] = useState<VoiceStatus>('idle')
  const [transcript, setTranscriptState] = useState('')
  const [interimTranscript, setInterimTranscript] = useState('')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [error, setError] = useState('')
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const shouldContinueRef = useRef(false)
  const transcriptRef = useRef('')

  const supported = useMemo(
    () =>
      typeof window !== 'undefined' &&
      Boolean(window.SpeechRecognition ?? window.webkitSpeechRecognition) &&
      Boolean(navigator.mediaDevices?.getUserMedia),
    [],
  )

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }, [])

  const stop = useCallback(() => {
    shouldContinueRef.current = false
    setStatus((current) => (current === 'listening' ? 'stopping' : 'idle'))
    setInterimTranscript('')
    recognitionRef.current?.stop()
    releaseStream()
    window.setTimeout(() => setStatus((current) => (current === 'stopping' ? 'idle' : current)), 200)
  }, [releaseStream])

  const start = useCallback(async () => {
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition
    if (!Recognition || !navigator.mediaDevices?.getUserMedia) {
      setStatus('error')
      setError('Live transcription is not supported in this browser. Use a current Chrome, Edge, or Safari release.')
      return
    }

    setStatus('requesting')
    setError('')
    setInterimTranscript('')

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          autoGainControl: true,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
      streamRef.current = stream

      const recognition = new Recognition()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'
      recognition.maxAlternatives = 1
      recognitionRef.current = recognition
      shouldContinueRef.current = true

      recognition.onstart = () => {
        setStatus('listening')
        setError('')
      }

      recognition.onresult = (event) => {
        let finalText = ''
        let interimText = ''

        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index]
          const words = result[0]?.transcript.trim() ?? ''
          if (!words) continue
          if (result.isFinal) {
            const completePhrase = /[.!?]$/.test(words) ? words : `${words}.`
            finalText += `${completePhrase} `
          }
          else interimText += `${words} `
        }

        if (finalText.trim()) {
          const nextTranscript = `${transcriptRef.current} ${finalText}`.trim()
          transcriptRef.current = nextTranscript
          setTranscriptState(nextTranscript)
        }
        setInterimTranscript(interimText.trim())
      }

      recognition.onerror = (event) => {
        if (event.error === 'no-speech') return
        shouldContinueRef.current = false
        setStatus('error')
        setError(describeSpeechError(event.error))
        setInterimTranscript('')
        releaseStream()
      }

      recognition.onend = () => {
        if (shouldContinueRef.current) {
          window.setTimeout(() => {
            try {
              recognition.start()
            } catch {
              shouldContinueRef.current = false
              setStatus('error')
              setError('Live transcription could not restart. Keep the captured text and try again.')
              releaseStream()
            }
          }, 150)
          return
        }
        setStatus((current) => (current === 'error' ? current : 'idle'))
        releaseStream()
      }

      recognition.start()
    } catch (caughtError) {
      releaseStream()
      setStatus('error')
      if (caughtError instanceof DOMException && caughtError.name === 'NotAllowedError') {
        setError('Microphone access was blocked. Allow microphone access in the browser and try again.')
      } else {
        setError('The microphone could not be started. Check the browser input settings and try again.')
      }
    }
  }, [releaseStream])

  const setTranscript = useCallback((value: string) => {
    transcriptRef.current = value
    setTranscriptState(value)
  }, [])

  const clear = useCallback(() => {
    stop()
    transcriptRef.current = ''
    setTranscriptState('')
    setInterimTranscript('')
    setElapsedSeconds(0)
    setError('')
  }, [stop])

  useEffect(() => {
    if (status !== 'listening') return
    const timer = window.setInterval(() => setElapsedSeconds((current) => current + 1), 1000)
    return () => window.clearInterval(timer)
  }, [status])

  useEffect(
    () => () => {
      shouldContinueRef.current = false
      recognitionRef.current?.abort()
      releaseStream()
    },
    [releaseStream],
  )

  return {
    clear,
    elapsedSeconds,
    error,
    interimTranscript,
    isListening: status === 'listening',
    isRequesting: status === 'requesting',
    setTranscript,
    start,
    status,
    stop,
    supported,
    transcript,
  }
}

export function formatElapsedTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function splitTranscriptIntoFacts(transcript: string): string[] {
  return transcript
    .replace(/\s+/g, ' ')
    .split(/(?<=[.!?])\s+|\n+/)
    .map((part) => part.trim())
    .filter(Boolean)
}
