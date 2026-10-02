"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface ApiDataState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
}

/**
 * Load data on mount / when `deps` change, with real loading + error states.
 * Ignores results from superseded or unmounted loads. Never substitutes fake data on failure.
 */
export function useApiData<T>(loader: () => Promise<T>, deps: unknown[] = []): ApiDataState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    const id = ++latest.current;
    setLoading(true);
    setError(null);
    loader()
      .then((result) => {
        if (id === latest.current) setData(result);
      })
      .catch((err) => {
        if (id === latest.current) {
          setData(null);
          setError(err);
        }
      })
      .finally(() => {
        if (id === latest.current) setLoading(false);
      });
    return () => {
      latest.current++;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}
