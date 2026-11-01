import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import Logo from "./Logo";

/** Sticky, translucent header shared by every page. */
export default function TopBar({ nav, right }: { nav?: ReactNode; right?: ReactNode }) {
  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.08] bg-black/70 backdrop-blur-xl backdrop-saturate-150">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4 sm:px-6 md:grid md:grid-cols-[1fr_auto_1fr]">
        <Link to="/" className="mr-auto md:mr-0 md:justify-self-start">
          <Logo />
        </Link>
        <nav className="hidden items-center gap-8 md:flex">{nav}</nav>
        <div className="flex items-center gap-2 md:justify-self-end">{right}</div>
      </div>
      {nav && <nav className="flex gap-6 overflow-x-auto border-t border-white/[0.06] px-4 py-2.5 sm:px-6 md:hidden">{nav}</nav>}
    </header>
  );
}

/** Soft cool glow behind hero sections. */
export function HeroGlow() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[640px]"
      style={{ background: "radial-gradient(45% 35% at 50% 62%, rgba(40,58,92,0.32), transparent 70%)" }}
    />
  );
}
