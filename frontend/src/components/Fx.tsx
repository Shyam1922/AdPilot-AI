import { useEffect, useState } from "react";
import { useIsFetching, useIsMutating } from "@tanstack/react-query";

/** A thin bar at the very top that runs while anything is loading or saving (feedback without a spinner). */
export function TopProgress() {
  const busy = useIsFetching() + useIsMutating() > 0;
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (busy) {
      const t = setTimeout(() => setShow(true), 150);          // skip it for instant responses
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setShow(false), 250);
    return () => clearTimeout(t);
  }, [busy]);
  return (
    <div aria-hidden className={"pointer-events-none fixed inset-x-0 top-0 z-[60] h-0.5 overflow-hidden transition-opacity duration-300 " + (show ? "opacity-100" : "opacity-0")}>
      <div className="h-full w-1/2 bg-gradient-to-r from-transparent via-white/80 to-transparent" style={{ animation: "progress 1.1s ease-in-out infinite" }} />
    </div>
  );
}

/** Feeds the pointer position to cards so their hover spotlight follows the cursor. */
export function useCardSpotlight() {
  useEffect(() => {
    const move = (e: PointerEvent) => {
      const card = (e.target as HTMLElement | null)?.closest?.(".card") as HTMLElement | null;
      if (!card) return;
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", `${e.clientX - r.left}px`);
      card.style.setProperty("--my", `${e.clientY - r.top}px`);
    };
    document.addEventListener("pointermove", move, { passive: true });
    return () => document.removeEventListener("pointermove", move);
  }, []);
}
