import React, { useState } from "react";
import {
  Sparkles,
  Copy,
  Check,
  Calendar,
  User,
  ListTodo,
  CheckCircle,
  HelpCircle,
  Clock,
  Mic,
  Loader2,
  RefreshCw,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  PieChart,
  Pie,
  Legend,
} from "recharts";
import { apiClient } from "../api/client";
import { useToast } from "../context/ToastContext";

export interface ActionItemData {
  task: string;
  owner: string;
  deadline?: string | null;
  source_timestamp?: string | null;
}

export interface TopicTimelineItemData {
  topic: string;
  start: number;
  end: number;
  summary: string;
}

export interface TalkTimeItemData {
  speaker: string;
  duration_sec: number;
  percentage: number;
}

export interface MeetingInsightsData {
  executive_summary?: string;
  inferred_agenda?: string[];
  key_points?: string[];
  decisions?: string[];
  action_items?: ActionItemData[];
  unresolved_questions?: string[];
  per_topic_timeline?: TopicTimelineItemData[];
  talk_time?: TalkTimeItemData[];
}

interface InsightsPanelProps {
  attachmentId: string;
  initialInsights?: MeetingInsightsData | null;
  onSeekAudio?: (seconds: number) => void;
}

const COLORS = ["#6366f1", "#a855f7", "#ec4899", "#14b8a6", "#f59e0b", "#3b82f6"];

export const InsightsPanel: React.FC<InsightsPanelProps> = ({
  attachmentId,
  initialInsights,
  onSeekAudio,
}) => {
  const { toast } = useToast();
  const [insights, setInsights] = useState<MeetingInsightsData | null>(initialInsights || null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const fetchOrGenerateInsights = async (force: boolean = false) => {
    setLoading(true);
    try {
      const endpoint = `/audio/${attachmentId}/meeting`;
      const data = force
        ? await apiClient.post<MeetingInsightsData>(endpoint)
        : await apiClient.get<MeetingInsightsData>(endpoint);
      setInsights(data);
      toast.success(force ? "Regenerated meeting insights" : "Loaded meeting insights");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to generate meeting insights";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyActionItems = () => {
    if (!insights?.action_items || insights.action_items.length === 0) {
      toast.info("No action items to copy");
      return;
    }
    const text = insights.action_items
      .map((item, idx) => {
        const deadline = item.deadline ? ` (Due: ${item.deadline})` : "";
        const owner = item.owner ? ` [@${item.owner}]` : "";
        return `${idx + 1}. [ ] ${item.task}${owner}${deadline}`;
      })
      .join("\n");

    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success("Action items copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  // Prepare topic timeline data for BarChart
  const timelineChartData =
    insights?.per_topic_timeline?.map((item) => ({
      topic: item.topic.length > 20 ? item.topic.slice(0, 18) + "…" : item.topic,
      duration: Math.max(1, Math.round(item.end - item.start)),
      start: item.start,
      summary: item.summary,
    })) || [];

  // Check if speaker data exists and is non-empty
  const hasSpeakerData =
    Boolean(insights?.talk_time) && (insights?.talk_time?.length ?? 0) > 0;

  return (
    <div className="space-y-6">
      {/* Header Actions */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-2xl bg-slate-900/40 border border-slate-800">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">Spoken Conversation Insights</h3>
            <p className="text-xs text-slate-400">NLP extraction, agenda synthesis, and action logs</p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          {!insights ? (
            <button
              onClick={() => fetchOrGenerateInsights(false)}
              disabled={loading}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors shadow-lg shadow-indigo-600/20 disabled:opacity-50"
            >
              {loading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Sparkles className="w-3.5 h-3.5" />
              )}
              <span>Generate Meeting Insights</span>
            </button>
          ) : (
            <button
              onClick={() => fetchOrGenerateInsights(true)}
              disabled={loading}
              className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition-colors disabled:opacity-50"
              title="Regenerate insights with fresh LLM pass"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Regenerate</span>
            </button>
          )}

          {insights?.action_items && insights.action_items.length > 0 && (
            <button
              onClick={handleCopyActionItems}
              className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? "Copied" : "Copy Action Items"}</span>
            </button>
          )}
        </div>
      </div>

      {!insights && !loading && (
        <div className="p-8 text-center rounded-2xl border border-dashed border-slate-800 text-slate-500 text-xs">
          Click "Generate Meeting Insights" to extract agenda, decisions, action items, and topic timelines.
        </div>
      )}

      {loading && (
        <div className="p-12 flex flex-col items-center justify-center space-y-3 text-slate-400">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
          <p className="text-xs">Extracting conversational entities and decisions...</p>
        </div>
      )}

      {insights && (
        <div className="space-y-6">
          {/* Executive Summary */}
          {insights.executive_summary && (
            <div className="p-4 rounded-2xl bg-indigo-950/20 border border-indigo-500/20">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-2">
                Executive Summary
              </h4>
              <p className="text-sm text-slate-200 leading-relaxed">{insights.executive_summary}</p>
            </div>
          )}

          {/* Agenda / Key Points */}
          {(insights.inferred_agenda || insights.key_points) && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-1.5">
                <CheckCircle className="w-3.5 h-3.5 text-indigo-400" />
                <span>Discussion Agenda & Key Points</span>
              </h4>
              <ul className="space-y-1.5">
                {(insights.inferred_agenda || insights.key_points || []).map((point, idx) => (
                  <li
                    key={idx}
                    className="text-xs text-slate-300 flex items-start space-x-2 bg-slate-900/40 p-2.5 rounded-xl border border-slate-800/80"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 shrink-0" />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Decisions */}
          {insights.decisions && insights.decisions.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-emerald-400 flex items-center space-x-1.5">
                <CheckCircle className="w-3.5 h-3.5" />
                <span>Agreements & Decisions Reached</span>
              </h4>
              <div className="space-y-1.5">
                {insights.decisions.map((dec, idx) => (
                  <div
                    key={idx}
                    className="text-xs text-emerald-200 bg-emerald-950/20 border border-emerald-800/30 p-2.5 rounded-xl flex items-start space-x-2"
                  >
                    <span className="text-emerald-400 font-bold shrink-0">✓</span>
                    <span>{dec}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action Items Table */}
          {insights.action_items && insights.action_items.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-1.5">
                <ListTodo className="w-3.5 h-3.5 text-indigo-400" />
                <span>Action Items ({insights.action_items.length})</span>
              </h4>
              <div className="overflow-x-auto rounded-xl border border-slate-800">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-800/60 text-slate-400 font-semibold uppercase border-b border-slate-800">
                    <tr>
                      <th className="p-3">Task Deliverable</th>
                      <th className="p-3">Owner</th>
                      <th className="p-3">Deadline</th>
                      <th className="p-3 text-right">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300">
                    {insights.action_items.map((item, idx) => (
                      <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                        <td className="p-3 font-medium text-slate-200">{item.task}</td>
                        <td className="p-3">
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                            <User className="w-3 h-3 text-slate-400" />
                            <span>{item.owner || "Unassigned"}</span>
                          </span>
                        </td>
                        <td className="p-3">
                          {item.deadline ? (
                            <span className="inline-flex items-center space-x-1 text-slate-400">
                              <Calendar className="w-3 h-3 text-slate-500" />
                              <span>{item.deadline}</span>
                            </span>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                        <td className="p-3 text-right">
                          {item.source_timestamp ? (
                            <button
                              onClick={() => {
                                const parts = item.source_timestamp!.split(":");
                                const sec =
                                  parts.length === 2
                                    ? Number(parts[0]) * 60 + Number(parts[1])
                                    : Number(item.source_timestamp);
                                if (!isNaN(sec) && onSeekAudio) onSeekAudio(sec);
                              }}
                              className="inline-flex items-center space-x-1 font-mono text-indigo-400 hover:text-indigo-300 underline"
                              title="Seek audio to timestamp"
                            >
                              <Clock className="w-3 h-3" />
                              <span>{item.source_timestamp}</span>
                            </button>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Open / Unresolved Questions */}
          {insights.unresolved_questions && insights.unresolved_questions.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-amber-400 flex items-center space-x-1.5">
                <HelpCircle className="w-3.5 h-3.5" />
                <span>Open & Unresolved Questions</span>
              </h4>
              <div className="space-y-1.5">
                {insights.unresolved_questions.map((q, idx) => (
                  <div
                    key={idx}
                    className="text-xs text-amber-200 bg-amber-500/10 border border-amber-500/20 p-2.5 rounded-xl flex items-start space-x-2"
                  >
                    <span className="text-amber-400 font-bold shrink-0">?</span>
                    <span>{q}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Topic Timeline Chart (Recharts) */}
          {timelineChartData.length > 0 && (
            <div className="p-4 rounded-2xl bg-slate-900/40 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-1.5">
                  <Clock className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Topic Timeline (Duration per segment)</span>
                </h4>
              </div>
              <div className="h-48 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={timelineChartData} layout="vertical" margin={{ left: 20, right: 20 }}>
                    <XAxis type="number" unit="s" stroke="#64748b" fontSize={11} />
                    <YAxis dataKey="topic" type="category" stroke="#94a3b8" fontSize={11} width={100} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#0f172a",
                        borderColor: "#334155",
                        borderRadius: "0.75rem",
                        fontSize: "0.75rem",
                      }}
                      formatter={(val: any, _name: any, item: any) => [ // eslint-disable-line @typescript-eslint/no-explicit-any
                        `${val} seconds (starts at ${item.payload.start}s)`,
                        "Duration",
                      ]}
                    />
                    <Bar dataKey="duration" radius={[0, 6, 6, 0]}>
                      {timelineChartData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Speaker Talk-Time Chart (Recharts) - STRICTLY HIDDEN WHEN EMPTY */}
          {hasSpeakerData && insights?.talk_time && (
            <div className="p-4 rounded-2xl bg-slate-900/40 border border-slate-800 space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-1.5">
                <Mic className="w-3.5 h-3.5 text-purple-400" />
                <span>Speaker Talk-Time Distribution</span>
              </h4>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={insights.talk_time}
                      dataKey="percentage"
                      nameKey="speaker"
                      cx="50%"
                      cy="50%"
                      outerRadius={70}
                      label={(entry: any) => `${entry.name || entry.speaker || "Speaker"}: ${entry.value || entry.percentage}%`} // eslint-disable-line @typescript-eslint/no-explicit-any
                      fontSize={11}
                    >
                      {insights.talk_time.map((_, index) => (
                        <Cell key={`spk-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#0f172a",
                        borderColor: "#334155",
                        borderRadius: "0.75rem",
                        fontSize: "0.75rem",
                      }}
                      formatter={(val: any, _name: any, item: any) => [ // eslint-disable-line @typescript-eslint/no-explicit-any
                        `${val}% (${item.payload.duration_sec}s)`,
                        item.payload.speaker,
                      ]}
                    />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
