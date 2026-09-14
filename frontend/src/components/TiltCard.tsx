'use client';

import React, { useRef } from 'react';
import {
  motion,
  useMotionTemplate,
  useMotionValue,
  useSpring,
  useTransform,
} from 'framer-motion';

const SPRING = { stiffness: 200, damping: 22, mass: 0.35 };

interface TiltCardProps {
  children: React.ReactNode;
  className?: string;
  innerClassName?: string;
  appear?: boolean;
}

export default function TiltCard({
  children,
  className = '',
  innerClassName = '',
  appear = false,
}: TiltCardProps) {
  const ref = useRef<HTMLDivElement>(null);
  const pointerX = useMotionValue(0.5);
  const pointerY = useMotionValue(0.5);

  const rotateX = useSpring(useTransform(pointerY, [0, 1], [8, -8]), SPRING);
  const rotateY = useSpring(useTransform(pointerX, [0, 1], [-8, 8]), SPRING);
  const glareX = useSpring(useTransform(pointerX, [0, 1], [0, 100]), SPRING);
  const glareY = useSpring(useTransform(pointerY, [0, 1], [0, 100]), SPRING);
  const glare = useMotionTemplate`radial-gradient(240px circle at ${glareX}% ${glareY}%, rgba(255,255,255,0.2), transparent 55%)`;

  const handleMove = (event: React.MouseEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    pointerX.set((event.clientX - rect.left) / rect.width);
    pointerY.set((event.clientY - rect.top) / rect.height);
  };

  const handleLeave = () => {
    pointerX.set(0.5);
    pointerY.set(0.5);
  };

  return (
    <motion.div
      className={`relative z-10 w-full max-w-xl [perspective:1000px] ${className}`}
      initial={appear ? { opacity: 0, y: 15 } : undefined}
      animate={appear ? { opacity: 1, y: 0 } : undefined}
      transition={appear ? { duration: 0.3 } : undefined}
    >
      <motion.div
        ref={ref}
        onMouseMove={handleMove}
        onMouseLeave={handleLeave}
        style={{ rotateX, rotateY, transformStyle: 'preserve-3d' }}
        className={`group relative overflow-hidden rounded-2xl border border-zinc-800/70 border-t border-t-white/15 bg-zinc-900/65 shadow-[0_24px_60px_-28px_rgba(0,0,0,0.85)] backdrop-blur-xl ${innerClassName}`}
      >
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0 z-20 rounded-2xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          style={{ background: glare }}
        />
        <div className="relative z-10">{children}</div>
      </motion.div>
    </motion.div>
  );
}
