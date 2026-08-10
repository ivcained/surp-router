import { useEffect, useRef, useState } from "react";

export interface MetricEvent {
  provider: string;
  model: string;
  ttft_ms: number | null;
  tps: number | null;
  f1000_h: number | null;
  total_ms: number;
  source: "request" | "benchmark";
  estimated: boolean;
  ts: number;
}

/** Subscribe to /api/metrics/stream (SSE). Renders at animation-frame cadence. */
export function useMetricsFeed(windowSize = 60) {
  const [samples, setSamples] = useState<MetricEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const buf = useRef<MetricEvent[]>([]);
  const raf = useRef(0);

  useEffect(() => {
    const es = new EventSource("/api/metrics/stream");
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false); // EventSource auto-reconnects
    es.addEventListener("metric", (e) => {
      buf.current.push(JSON.parse((e as MessageEvent).data));
      if (!raf.current) {
        raf.current = requestAnimationFrame(() => {
          setSamples((prev) => [...prev, ...buf.current].slice(-windowSize * 4));
          buf.current = [];
          raf.current = 0;
        });
      }
    });
    return () => {
      es.close();
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [windowSize]);

  return { samples, connected };
}
