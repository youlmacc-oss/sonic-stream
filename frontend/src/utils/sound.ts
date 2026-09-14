const C6 = 1046.5;
const G6 = 1567.98;

let audioContext: AudioContext | null = null;

function getCtor(): (typeof AudioContext) | null {
  if (typeof window === 'undefined') return null;
  return window.AudioContext
    || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    || null;
}

function createContext(): AudioContext | null {
  if (audioContext) return audioContext;
  const Ctor = getCtor();
  if (!Ctor) return null;
  try {
    audioContext = new Ctor();
    return audioContext;
  } catch {
    audioContext = null;
    return null;
  }
}

export async function unlockAudio(): Promise<void> {
  try {
    const ctx = createContext();
    if (!ctx) return;
    if (ctx.state === 'suspended') {
      await ctx.resume();
    }
  } catch {
    // Autoplay policy / resume rejection — never surface to console.
  }
}

function getReadyContext(): AudioContext | null {
  if (!audioContext || audioContext.state === 'closed') return null;
  return audioContext;
}

function playTone(
  ctx: AudioContext,
  frequency: number,
  startOffset: number,
  duration: number,
  volume = 0.08,
) {
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    const start = ctx.currentTime + startOffset;

    osc.type = 'sine';
    osc.frequency.setValueAtTime(frequency, start);
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(volume, start + 0.018);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);

    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(start);
    osc.stop(start + duration + 0.02);
  } catch {
    // Oscillator setup can fail on a closed context — swallow silently.
  }
}

export function playSuccessChime() {
  try {
    const ctx = getReadyContext();
    if (!ctx || ctx.state !== 'running') return;
    playTone(ctx, C6, 0, 0.16, 0.08);
    playTone(ctx, G6, 0.12, 0.22, 0.07);
  } catch {
    // no-op
  }
}

export function playErrorBeep() {
  try {
    const ctx = getReadyContext();
    if (!ctx || ctx.state !== 'running') return;
    playTone(ctx, 196, 0, 0.18, 0.05);
  } catch {
    // no-op
  }
}
