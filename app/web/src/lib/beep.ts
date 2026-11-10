/** A short tone for the end of a rest or a timed hold. iOS only allows sound after a tap, so `unlockSound()` is called from the buttons that start a workout or finish a set. */
let ctx: AudioContext | null = null;

function context(): AudioContext | null {
  try {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    ctx = ctx ?? new Ctor();
    if (ctx.state === "suspended") void ctx.resume();
    return ctx;
  } catch {
    return null;
  }
}

export const unlockSound = () => void context();

export function beep(times = 1, freq = 880, ms = 140): void {
  const c = context();
  if (!c) return;
  for (let i = 0; i < times; i++) {
    const start = c.currentTime + i * (ms + 90) / 1000;
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.25, start + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + ms / 1000);
    osc.connect(gain).connect(c.destination);
    osc.start(start);
    osc.stop(start + ms / 1000 + 0.02);
  }
  try { navigator.vibrate?.(times > 1 ? [120, 80, 120] : 200); } catch { /* not supported (iOS) */ }
}
