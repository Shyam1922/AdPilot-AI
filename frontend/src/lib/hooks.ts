import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

/** Sets the browser tab title, e.g. "Velvaa Skin · AdPilot". Empty parts are skipped. */
export function useTitle(...parts: (string | false | null | undefined)[]) {
  const title = [...parts.filter(Boolean), "AdPilot"].join(" · ");
  useEffect(() => {
    document.title = title;
  }, [title]);
}

const shape = (path: string) => path.replace(/\{[^}]+\}/g, "{}");

/**
 * True when the backend exposes `method path` (read from FastAPI's /openapi.json), e.g.
 * useSupports("delete", "/api/brands/{id}"). Lets the UI ship a feature before the endpoint exists.
 */
export function useSupports(method: "delete" | "get" | "post" | "patch", path: string): boolean {
  const { data } = useQuery({ queryKey: ["routes"], queryFn: api.routes, staleTime: Infinity, retry: false });
  if (!data) return false;
  return Object.entries(data).some(([p, ops]) => shape(p) === shape(path) && method in ops);
}
