export default function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 shadow-[0_0_20px_rgba(139,92,246,0.35)]">
        <svg viewBox="0 0 24 24" className="h-4 w-4 text-white" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 17 L12 4 L21 17" />
          <path d="M7.5 12.5 H16.5" />
        </svg>
      </div>
      <span className="font-serif text-lg font-semibold tracking-tight text-ink">AdPilot</span>
    </div>
  );
}
