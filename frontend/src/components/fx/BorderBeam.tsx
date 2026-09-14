'use client';

export default function BorderBeam({ durationClass = 'animate-border-beam' }: { durationClass?: string }) {
  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden rounded-[inherit]" aria-hidden>
      <div
        className={`absolute top-1/2 left-1/2 aspect-square w-[220%] ${durationClass} opacity-90`}
        style={{
          background:
            'conic-gradient(from 0deg, transparent 0%, transparent 68%, rgba(0,240,255,0) 74%, #00F0FF 84%, #6366F1 92%, transparent 100%)',
        }}
      />
    </div>
  );
}
