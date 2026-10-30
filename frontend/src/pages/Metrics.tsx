import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Cpu,
  HardDrive,
  Clock,
  Layers,
  RefreshCw,
  Loader2,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";
import { apiClient } from "../api/client";

interface ComponentMetric {
  component: string;
  operation: string;
  count: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  avg_latency_ms: number;
  avg_tokens_per_sec?: number | null;
  avg_rtf?: number | null;
  avg_cpu_pct?: number | null;
  avg_ram_mb?: number | null;
  avg_gpu_mem_mb?: number | null;
}

interface TimeSeriesPoint {
  id: string;
  timestamp: string;
  component: string;
  operation: string;
  latency_ms: number;
  cpu_pct?: number | null;
  ram_mb?: number | null;
  gpu_mem_mb?: number | null;
  tokens_per_sec?: number | null;
}

interface MetricsSummaryResponse {
  total_operations: number;
  average_latency_ms: number;
  components: ComponentMetric[];
  recent_time_series: TimeSeriesPoint[];
  system_status?: {
    cpu_percent?: number;
    ram_used_mb?: number;
    ram_total_mb?: number;
    gpu_allocated_mb?: number;
  };
}

export const Metrics: React.FC = () => {
  const { data, isLoading, refetch, isFetching } = useQuery<MetricsSummaryResponse>({
    queryKey: ["metricsSummary"],
    queryFn: () => apiClient.get<MetricsSummaryResponse>("/metrics/summary"),
    refetchInterval: 10_000,
  });

  const components = data?.components || [];
  const timeSeries = data?.recent_time_series || [];
  const status = data?.system_status;

  // Format latency bar chart data
  const latencyChartData = components.map((c) => ({
    name: `${c.component}:${c.operation}`,
    p50: c.p50_latency_ms,
    p95: c.p95_latency_ms,
    avg: c.avg_latency_ms,
  }));

  // Format time series data for line chart
  const timelineChartData = timeSeries.map((pt, idx) => ({
    index: idx + 1,
    latency: pt.latency_ms,
    label: `${pt.component} (${pt.operation})`,
    tokensPerSec: pt.tokens_per_sec || 0,
    time: pt.timestamp ? new Date(pt.timestamp).toLocaleTimeString() : `#${idx + 1}`,
  }));

  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-8 space-y-6">
      {/* Header and Refresh */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-3xl bg-slate-900/60 border border-slate-800 shadow-xl backdrop-blur-md">
        <div className="flex items-center space-x-3.5">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-emerald-500 to-teal-600 flex items-center justify-center text-white shadow-lg shadow-emerald-500/20">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white tracking-tight">Telemetry & Performance Dashboard</h2>
            <p className="text-xs text-slate-400">
              Live p50/p95 latency metrics, LLM generation speed, Real-Time Factor (RTF), and hardware resources
            </p>
          </div>
        </div>

        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin text-emerald-400" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {isLoading ? (
        <div className="p-16 flex flex-col items-center justify-center space-y-3 text-slate-400">
          <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
          <span className="text-xs">Aggregating system telemetry records...</span>
        </div>
      ) : (
        <>
          {/* Top KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Total Operations */}
            <div className="p-5 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-2">
              <div className="flex items-center justify-between text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">Inference Operations</span>
                <Layers className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="text-2xl font-bold font-mono text-white">
                {data?.total_operations ?? 0}
              </div>
              <p className="text-[11px] text-slate-500">Tracked operations across all pipelines</p>
            </div>

            {/* Average Latency */}
            <div className="p-5 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-2">
              <div className="flex items-center justify-between text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">Average Latency</span>
                <Clock className="w-4 h-4 text-sky-400" />
              </div>
              <div className="text-2xl font-bold font-mono text-white">
                {data?.average_latency_ms ?? 0} <span className="text-sm font-normal text-slate-400">ms</span>
              </div>
              <p className="text-[11px] text-slate-500">Mean duration per inference invocation</p>
            </div>

            {/* CPU Load */}
            <div className="p-5 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-2">
              <div className="flex items-center justify-between text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">CPU Utilization</span>
                <Cpu className="w-4 h-4 text-indigo-400" />
              </div>
              <div className="text-2xl font-bold font-mono text-white">
                {status?.cpu_percent !== undefined ? `${status.cpu_percent}%` : "—"}
              </div>
              <p className="text-[11px] text-slate-500">Current host processor utilization</p>
            </div>

            {/* RAM Memory */}
            <div className="p-5 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-2">
              <div className="flex items-center justify-between text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">RAM Allocation</span>
                <HardDrive className="w-4 h-4 text-purple-400" />
              </div>
              <div className="text-2xl font-bold font-mono text-white">
                {status?.ram_used_mb ? (status.ram_used_mb / 1024).toFixed(1) : "—"}
                <span className="text-sm font-normal text-slate-400"> GB</span>
              </div>
              <p className="text-[11px] text-slate-500">
                {status?.ram_total_mb
                  ? `of ${(status.ram_total_mb / 1024).toFixed(1)} GB total host RAM`
                  : "Resident set memory allocation"}
              </p>
            </div>
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Component Latency Bar Chart (p50 vs p95) */}
            <div className="p-5 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white">Component Latencies</h3>
                  <p className="text-xs text-slate-400">p50 and p95 response time per pipeline (ms)</p>
                </div>
              </div>

              <div className="h-64 w-full">
                {latencyChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={latencyChartData} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="name" stroke="#64748b" fontSize={10} angle={-25} textAnchor="end" />
                      <YAxis stroke="#64748b" fontSize={11} unit="ms" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#0f172a",
                          borderColor: "#334155",
                          borderRadius: "0.75rem",
                          fontSize: "0.75rem",
                        }}
                      />
                      <Legend verticalAlign="top" height={36} />
                      <Bar dataKey="p50" name="p50 Latency" fill="#10b981" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="p95" name="p95 Latency" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-slate-500">
                    No operations recorded yet
                  </div>
                )}
              </div>
            </div>

            {/* Recent Latency Time Series Line Chart */}
            <div className="p-5 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white">Execution Latency Over Time</h3>
                  <p className="text-xs text-slate-400">Sequential chronological operation history (ms)</p>
                </div>
              </div>

              <div className="h-64 w-full">
                {timelineChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={timelineChartData} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="time" stroke="#64748b" fontSize={10} />
                      <YAxis stroke="#64748b" fontSize={11} unit="ms" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#0f172a",
                          borderColor: "#334155",
                          borderRadius: "0.75rem",
                          fontSize: "0.75rem",
                        }}
                        formatter={(val: any, _name: any, item: any) => [ // eslint-disable-line @typescript-eslint/no-explicit-any
                          `${val} ms (${item.payload.label})`,
                          "Duration",
                        ]}
                      />
                      <Line
                        type="monotone"
                        dataKey="latency"
                        name="Latency"
                        stroke="#6366f1"
                        strokeWidth={2}
                        dot={{ r: 3, fill: "#6366f1" }}
                        activeDot={{ r: 6 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-slate-500">
                    No time-series points recorded
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Detailed Telemetry Breakdown Table */}
          <div className="rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl overflow-hidden">
            <div className="p-4 border-b border-slate-800/80">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Pipeline Telemetry & Resource Breakdown
              </h3>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 text-slate-400 font-semibold uppercase border-b border-slate-800">
                  <tr>
                    <th className="p-3.5">Component</th>
                    <th className="p-3.5">Operation</th>
                    <th className="p-3.5 text-right">Invocations</th>
                    <th className="p-3.5 text-right">p50 Latency</th>
                    <th className="p-3.5 text-right">p95 Latency</th>
                    <th className="p-3.5 text-right">Avg Latency</th>
                    <th className="p-3.5 text-right">Throughput</th>
                    <th className="p-3.5 text-right">Avg CPU</th>
                    <th className="p-3.5 text-right">Avg RAM</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80 text-slate-300 font-mono">
                  {components.length > 0 ? (
                    components.map((c, idx) => (
                      <tr key={idx} className="hover:bg-slate-850/50 transition-colors">
                        <td className="p-3.5 font-semibold text-slate-200 uppercase">{c.component}</td>
                        <td className="p-3.5 text-slate-400">{c.operation}</td>
                        <td className="p-3.5 text-right">{c.count}</td>
                        <td className="p-3.5 text-right text-emerald-400">{c.p50_latency_ms} ms</td>
                        <td className="p-3.5 text-right text-amber-400">{c.p95_latency_ms} ms</td>
                        <td className="p-3.5 text-right">{c.avg_latency_ms} ms</td>
                        <td className="p-3.5 text-right">
                          {c.avg_tokens_per_sec !== null && c.avg_tokens_per_sec !== undefined ? (
                            <span className="text-indigo-400">{c.avg_tokens_per_sec} tok/s</span>
                          ) : c.avg_rtf !== null && c.avg_rtf !== undefined ? (
                            <span className="text-teal-400">{c.avg_rtf} RTF</span>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                        <td className="p-3.5 text-right">
                          {c.avg_cpu_pct !== null && c.avg_cpu_pct !== undefined
                            ? `${c.avg_cpu_pct}%`
                            : "—"}
                        </td>
                        <td className="p-3.5 text-right">
                          {c.avg_ram_mb !== null && c.avg_ram_mb !== undefined
                            ? `${c.avg_ram_mb} MB`
                            : "—"}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={9} className="p-6 text-center text-slate-500 font-sans">
                        No telemetry metrics collected yet. Inferences will automatically record latencies and memory usage here.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
