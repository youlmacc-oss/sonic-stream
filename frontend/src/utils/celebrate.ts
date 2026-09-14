'use client';

import confetti from 'canvas-confetti';

const COLORS = ['#00F0FF', '#6366F1'];

export function burstNeonConfetti(anchor?: HTMLElement | null) {
  const rect = anchor?.getBoundingClientRect();
  const origin = rect
    ? {
        x: (rect.left + rect.width / 2) / window.innerWidth,
        y: (rect.top + rect.height / 2) / window.innerHeight,
      }
    : { x: 0.5, y: 0.72 };

  void confetti({
    particleCount: 42,
    spread: 52,
    startVelocity: 26,
    gravity: 0.95,
    ticks: 90,
    scalar: 0.68,
    origin,
    colors: COLORS,
    disableForReducedMotion: true,
  });
}
