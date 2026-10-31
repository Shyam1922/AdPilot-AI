import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { Language } from "@/lib/types";
import { useToast } from "./toast";
import { Spinner } from "./ui";

/** POST /concepts/generate with a language choice (en / hi / hinglish). */
export default function GenerateConcepts({
  campaignId,
  label = "Generate creatives",
  ghost,
  onDone,
}: {
  campaignId: number;
  label?: string;
  ghost?: boolean;
  onDone?: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [language, setLanguage] = useState<Language>("en");
  const generate = useMutation({
    mutationFn: () => api.generateConcepts(campaignId, { count: 5, language }),
    onSuccess: (made) => {
      qc.invalidateQueries({ queryKey: ["campaign", campaignId] });
      toast.success(`${made.length} concepts generated`);
      onDone?.();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <div className="flex items-center gap-2">
      <select
        className="input w-auto py-2"
        value={language}
        onChange={(e) => setLanguage(e.target.value as Language)}
        disabled={generate.isPending}
        aria-label="Copy language"
      >
        <option value="en">English</option>
        <option value="hi">Hindi</option>
        <option value="hinglish">Hinglish</option>
      </select>
      <button className={ghost ? "btn-ghost" : "btn-primary"} onClick={() => generate.mutate()} disabled={generate.isPending}>
        {generate.isPending ? <Spinner /> : <Sparkles className="h-4 w-4" />}
        {generate.isPending ? "Generating…" : label}
      </button>
    </div>
  );
}
