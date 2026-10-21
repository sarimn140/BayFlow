'use client'

/**
 * The incoming-call ring (spec 05 §9.3), made with the Web Audio API: no audio files to license.
 * A soft two-tone burst every 3 s. It stays silent when the browser blocks autoplay.
 */
let context: AudioContext | null = null
let timer: ReturnType<typeof setInterval> | undefined

function burst(audio: AudioContext) {
  const now = audio.currentTime
  const gain = audio.createGain()
  gain.gain.setValueAtTime(0, now)
  gain.gain.linearRampToValueAtTime(0.08, now + 0.05)
  gain.gain.setValueAtTime(0.08, now + 0.9)
  gain.gain.linearRampToValueAtTime(0, now + 1.0)
  gain.connect(audio.destination)
  for (const frequency of [440, 480]) {
    const tone = audio.createOscillator()
    tone.frequency.value = frequency
    tone.connect(gain)
    tone.start(now)
    tone.stop(now + 1.0)
  }
}

export function startRinging() {
  if (timer || typeof window === 'undefined' || !('AudioContext' in window)) return
  try {
    context ??= new AudioContext()
    void context.resume().catch(() => undefined)
    burst(context)
    timer = setInterval(() => context && burst(context), 3000)
  } catch {
    // autoplay blocked or no audio device: the panel still shows the call
  }
}

export function stopRinging() {
  clearInterval(timer)
  timer = undefined
}
