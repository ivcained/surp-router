import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { useMetricsFeed, MetricEvent } from "./useMetricsFeed";

const COLORS = ["#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#a855f7"];
const fmt = (v: number | null | undefined, d = 1) => (v == null ? "—" : v.toFixed(d));

export default function LiveTpsDashboard() {
  const { samples, connected } = useMetricsFeed(60);

  const latest: MetricEvent | undefined = samples[samples.length - 1];
  const keys = useMemo(
    () => [...new Set(samples.map((s) => `${s.provider}|${s.model}`))].slice(-5),
    [samples]
  );
  const chartData = useMemo(
    () =>
      samples.map((s) => ({
        t: new Date(s.ts * 1000).toLocaleTimeString(),
        [`${s.provider}|${s.model}`]: s.tps ?? undefined,
      })),
    [samples]
  );

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-red-500"}`}
        />
        <h2 className="text-lg font-semibold">Live Throughput</h2>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card label="TTFT" value={`${fmt(latest?.ttft_ms, 0)} ms`} sub={latest?.model} />
        <Card label="TPS" value={fmt(latest?.tps)} sub={latest?.provider} />
        <Card label="F1000" value={`${fmt(latest?.f1000_h, 2)} h`} sub="1000 × ~300 tok" />
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData}>
          <XAxis dataKey="t" hide />
          <YAxis label={{ value: "tok/s", angle: -90, position: "insideLeft" }} />
          <Tooltip />
          <Legend />
          {keys.map((k, i) => (
            <Line
              key={k}
              dataKey={k}
              dot={false}
              isAnimationActive={false}
              stroke={COLORS[i % COLORS.length]}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Card({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border p-4">
      <div className="text-xs uppercase text-gray-500">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs text-gray-400 truncate">{sub}</div>}
    </div>
  );
}
