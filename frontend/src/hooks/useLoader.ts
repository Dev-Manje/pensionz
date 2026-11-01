import { useCallback, useEffect, useRef, useState } from "react";

// Runs a screen's initial load (and later reloads) with the three states
// every screen needs: `loading` until the first answer, `error` with the
// API's message if it fails (instead of a silently blank table), and
// `reload()` for a Retry button or after an action. A reload after the first
// keeps the current data on screen rather than flashing back to "loading".
export function useLoader(load: () => Promise<unknown>) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(async () => {
    setError(null);
    try {
      await loadRef.current();
    } catch (err) {
      setError((err as Error).message || "Couldn't load this. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { loading, error, reload };
}
