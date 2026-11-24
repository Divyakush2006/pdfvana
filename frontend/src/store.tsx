import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { fetchCatalog, type Catalog } from "./api";

type Ctx = {
  catalog: Catalog | null;
  error: string | null;
  /** Files handed from one tool's result to the next tool ("Continue with…"). */
  handoff: (files: File[]) => void;
  takeHandoff: () => File[];
};

const AppCtx = createContext<Ctx>(null as unknown as Ctx);

export function AppProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<File[]>([]);

  useEffect(() => {
    let cancelled = false;
    let attempt = 0;
    const load = () => {
      fetchCatalog()
        .then((c) => {
          if (!cancelled) {
            setCatalog(c);
            setError(null);
          }
        })
        .catch(() => {
          if (cancelled) return;
          attempt += 1;
          if (attempt >= 3) setError("The service is starting up or temporarily unavailable. Retrying…");
          window.setTimeout(load, Math.min(8000, 600 * 2 ** attempt)); // keep retrying with back-off
        });
    };
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const handoff = useCallback((files: File[]) => {
    pending.current = files;
  }, []);
  const takeHandoff = useCallback(() => {
    const f = pending.current;
    pending.current = [];
    return f;
  }, []);

  return <AppCtx.Provider value={{ catalog, error, handoff, takeHandoff }}>{children}</AppCtx.Provider>;
}

export const useApp = () => useContext(AppCtx);

export function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      /* private mode */
    }
    setDark(next);
  };
  return { dark, toggle };
}
