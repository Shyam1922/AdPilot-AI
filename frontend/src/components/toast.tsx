import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";

type Tone = "success" | "error" | "info";
interface Toast {
  id: number;
  tone: Tone;
  msg: string;
}
interface Ctx {
  success: (msg: string) => void;
  error: (msg: string) => void;
  info: (msg: string) => void;
}

const ToastCtx = createContext<Ctx | null>(null);

const ICON = {
  success: <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />,
  error: <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />,
  info: <Info className="mt-0.5 h-4 w-4 shrink-0 text-white" />,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (tone: Tone, msg: string) => {
      const id = Date.now() + Math.random();
      setItems((xs) => [...xs, { id, tone, msg }]);
      setTimeout(() => dismiss(id), tone === "error" ? 6000 : 3500);
    },
    [dismiss],
  );
  const ctx = useMemo<Ctx>(
    () => ({ success: (m) => push("success", m), error: (m) => push("error", m), info: (m) => push("info", m) }),
    [push],
  );

  return (
    <ToastCtx.Provider value={ctx}>
      {children}
      <div className="pointer-events-none fixed bottom-6 right-6 z-50 flex w-80 flex-col gap-2">
        {items.map((t) => (
          <div key={t.id} className="pointer-events-auto flex items-start gap-3 rounded-2xl border border-line bg-[#16171a]/95 px-4 py-3 text-sm shadow-panel backdrop-blur-xl">
            {ICON[t.tone]}
            <span className="flex-1 text-ink">{t.msg}</span>
            <button onClick={() => dismiss(t.id)} className="text-muted hover:text-ink">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const c = useContext(ToastCtx);
  if (!c) throw new Error("useToast must be used inside ToastProvider");
  return c;
}
