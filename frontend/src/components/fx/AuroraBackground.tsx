export default function AuroraBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden>
      <div
        className="absolute -top-24 -left-16 h-[28rem] w-[28rem] rounded-full bg-[#00F0FF] blur-[160px] opacity-[0.06]"
      />
      <div
        className="absolute -right-20 -bottom-28 h-[32rem] w-[32rem] rounded-full bg-[#6366F1] blur-[160px] opacity-[0.07]"
      />
      <div className="absolute inset-0 bg-[radial-gradient(#272A34_1px,transparent_1px)] [background-size:24px_24px] opacity-10" />
    </div>
  );
}
