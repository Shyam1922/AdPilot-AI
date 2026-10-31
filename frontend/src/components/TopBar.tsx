import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import Logo from "./Logo";

/** Sticky, translucent header shared by every page. */
export default function TopBar({ nav, right }: { nav?: ReactNode; right?: ReactNode }) {
  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.08] bg-black/70 backdrop-blur-xl backdrop-saturate-150">
      <div className="mx-auto grid h-16 max-w-6xl grid-cols-[1fr_auto_1fr] items-center gap-6 px-6">
        <Link to="/" className="justify-self-start">
          <Logo />
        </Link>
        <nav className="flex items-center gap-8">{nav}</nav>
        <div className="flex items-center justify-self-end gap-2">{right}</div>
      </div>
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
