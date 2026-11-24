import { useCallback, useEffect, useRef } from "react";

/**
 * Runs a latest-request-wins telemetry refresh. Polling is serialized (the next
 * poll starts after the previous one settles), and every replacement/unmount
 * invalidates older responses even when an underlying API cannot be aborted.
 */
export function useTelemetryRefresh(
  refresh: (signal: AbortSignal) => void | Promise<void>,
  intervalMs = 5000
): () => void {
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;

  const mountedRef = useRef(false);
  const generationRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const timerRef = useRef<number | null>(null);
  const runningRef = useRef(false);
  const queuedRef = useRef(false);

  const runRefresh = useCallback(async () => {
    if (!mountedRef.current) return;
    if (runningRef.current) {
      queuedRef.current = true;
      return;
    }

    runningRef.current = true;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const generation = ++generationRef.current;
    const isCurrent = () =>
      mountedRef.current && !controller.signal.aborted && generation === generationRef.current;

    try {
      await refreshRef.current(controller.signal);
    } catch {
      // Callers may surface their own errors; polling should continue after a
      // failed snapshot rather than terminate permanently.
    } finally {
      if (isCurrent()) {
        runningRef.current = false;
        controllerRef.current = null;
        if (queuedRef.current) {
          queuedRef.current = false;
          void runRefresh();
        } else if (intervalMs > 0) {
          timerRef.current = window.setTimeout(() => void runRefresh(), intervalMs);
        }
      }
    }
  }, [intervalMs]);

  useEffect(() => {
    mountedRef.current = true;
    void runRefresh();

    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      controllerRef.current?.abort();
      controllerRef.current = null;
      runningRef.current = false;
      queuedRef.current = false;
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = null;
    };
  }, [runRefresh]);

  return useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    void runRefresh();
  }, [runRefresh]);
}
