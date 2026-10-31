export default function Logo() {
  return (
    <div className="flex items-center gap-2">
      <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 19 L12 4 L21 19" />
        <path d="M7.5 13.5 H16.5" />
      </svg>
      <span className="font-serif text-[21px] font-normal tracking-tight text-white">AdPilot</span>
    </div>
  );
}
