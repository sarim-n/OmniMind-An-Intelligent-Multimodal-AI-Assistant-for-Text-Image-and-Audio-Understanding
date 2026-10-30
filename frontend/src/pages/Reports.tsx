import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  Plus,
  Download,
  Trash2,
  Eye,
  Calendar,
  AlertTriangle,
  X,
  Loader2,
  Sparkles,
} from "lucide-react";
import { apiClient } from "../api/client";
import { useToast } from "../context/ToastContext";

interface ReportListItem {
  id: string;
  conversation_id: string;
  title: string;
  created_at: string;
  pdf_path?: string | null;
}

interface ReportDetailResponse {
  id: string;
  conversation_id: string;
  title: string;
  created_at: string;
  content: {
    executive_summary?: string;
    sections?: Array<{ heading: string; body: string; bullet_points?: string[] }>;
    cross_modal_observations?: string[];
    conclusions?: string[];
    recommendations?: string[];
  };
}

export const Reports: React.FC = () => {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [isGenerateOpen, setIsGenerateOpen] = useState(false);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Generate Dialog Form state
  const [targetConvId, setTargetConvId] = useState("");
  const [reportLang, setReportLang] = useState("en");
  const [reportLength, setReportLength] = useState<"brief" | "standard" | "detailed">("standard");
  const [includeImages, setIncludeImages] = useState(true);
  const [includeMetrics, setIncludeMetrics] = useState(true);
  const [generatingJobId, setGeneratingJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<number>(0);

  // Fetch Reports List
  const { data: reports, isLoading } = useQuery<ReportListItem[]>({
    queryKey: ["reports"],
    queryFn: () => apiClient.get<ReportListItem[]>("/reports"),
  });

  // Fetch Conversations for dropdown
  const { data: convData } = useQuery<{ items: Array<{ id: string; title: string }> }>({
    queryKey: ["conversationsForReports"],
    queryFn: () => apiClient.get("/conversations", { page_size: 50 }),
    enabled: isGenerateOpen,
  });

  // Fetch active report detail for preview
  const { data: activeReport, isLoading: isLoadingDetail } = useQuery<ReportDetailResponse>({
    queryKey: ["reportDetail", selectedReportId],
    queryFn: () => apiClient.get<ReportDetailResponse>(`/reports/${selectedReportId}`),
    enabled: Boolean(selectedReportId),
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/reports/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      setDeletingId(null);
      if (selectedReportId === deletingId) setSelectedReportId(null);
      toast.success("Report deleted successfully");
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to delete report";
      toast.error(msg);
    },
  });

  // Generate Report mutation
  const handleStartGeneration = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetConvId) {
      toast.info("Please select a conversation to synthesize.");
      return;
    }

    try {
      const res = await apiClient.post<{ job_id: string; status: string }>("/reports", {
        conversation_id: targetConvId,
        options: {
          language: reportLang,
          length: reportLength,
          include_images: includeImages,
          include_metrics: includeMetrics,
        },
      });

      const jobId = res.job_id;
      setGeneratingJobId(jobId);
      setJobProgress(10);
      toast.info("Report synthesis initiated...");

      // Poll job progress
      const interval = setInterval(async () => {
        try {
          const job = await apiClient.get<{ status: string; progress: number; result?: { report_id?: string } }>(
            `/jobs/${jobId}`
          );
          if (job.progress) setJobProgress(Math.round(job.progress * 100));

          if (job.status === "done") {
            clearInterval(interval);
            setGeneratingJobId(null);
            setIsGenerateOpen(false);
            queryClient.invalidateQueries({ queryKey: ["reports"] });
            toast.success("Report compiled successfully!");
            if (job.result?.report_id) {
              setSelectedReportId(job.result.report_id);
            }
          } else if (job.status === "failed") {
            clearInterval(interval);
            setGeneratingJobId(null);
            toast.error("Report generation failed");
          }
        } catch {
          clearInterval(interval);
          setGeneratingJobId(null);
        }
      }, 1000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to start report generation";
      toast.error(msg);
      setGeneratingJobId(null);
    }
  };

  const handleDownloadPdf = async (reportId: string, title: string) => {
    try {
      toast.info("Downloading PDF document...");
      const blob = await apiClient.fetchBlob(`/reports/${reportId}/pdf`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${title.replace(/\s+/g, "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("PDF downloaded");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to download PDF";
      toast.error(msg);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-8 space-y-6">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-3xl bg-slate-900/60 border border-slate-800 shadow-xl backdrop-blur-md">
        <div className="flex items-center space-x-3.5">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-amber-500 to-orange-600 flex items-center justify-center text-white shadow-lg shadow-amber-500/20">
            <FileText className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white tracking-tight">Structured Reports & PDF Export</h2>
            <p className="text-xs text-slate-400">
              Multilingual cross-asset synthesis rendered via Platypus and Noto Sans
            </p>
          </div>
        </div>

        <button
          onClick={() => {
            if (convData?.items && convData.items.length > 0 && !targetConvId) {
              setTargetConvId(convData.items[0]!.id);
            }
            setIsGenerateOpen(true);
          }}
          className="flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-400 hover:to-orange-500 text-white text-xs font-semibold rounded-xl shadow-lg shadow-amber-500/20 transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>Generate Report</span>
        </button>
      </div>

      {/* Reports List */}
      <div className="rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl overflow-hidden">
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Compiled Intelligence Reports ({reports?.length ?? 0})
          </span>
        </div>

        {isLoading ? (
          <div className="p-12 flex flex-col items-center justify-center space-y-2 text-slate-400">
            <Loader2 className="w-6 h-6 animate-spin text-amber-500" />
            <span className="text-xs">Loading reports catalog...</span>
          </div>
        ) : !reports || reports.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-500">
            No reports generated yet. Click &ldquo;Generate Report&rdquo; to compile conversation evidence into an auditable PDF.
          </div>
        ) : (
          <div className="divide-y divide-slate-800/80">
            {reports.map((rep) => (
              <div
                key={rep.id}
                className="p-4 flex flex-wrap items-center justify-between gap-3 hover:bg-slate-850/50 transition-colors"
              >
                <div className="flex items-center space-x-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 shrink-0">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <h4 className="text-xs font-semibold text-white truncate">{rep.title}</h4>
                    <div className="flex items-center space-x-2 text-[11px] text-slate-400 mt-0.5">
                      <span className="flex items-center space-x-1">
                        <Calendar className="w-3 h-3 text-slate-500" />
                        <span>{new Date(rep.created_at).toLocaleDateString()}</span>
                      </span>
                      <span>&bull;</span>
                      <span className="font-mono text-slate-500 text-[10px]">
                        Conv: {rep.conversation_id.slice(0, 8)}...
                      </span>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setSelectedReportId(rep.id)}
                    className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-colors"
                  >
                    <Eye className="w-3.5 h-3.5 text-sky-400" />
                    <span>Preview</span>
                  </button>

                  <button
                    onClick={() => handleDownloadPdf(rep.id, rep.title)}
                    className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium transition-colors shadow-sm"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>PDF</span>
                  </button>

                  <button
                    onClick={() => setDeletingId(rep.id)}
                    className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-slate-800 rounded-lg transition-colors"
                    title="Delete report"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Generate Report Dialog Modal */}
      {isGenerateOpen && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in"
        >
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 max-w-lg w-full shadow-2xl space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2.5">
                <div className="w-8 h-8 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                  <Sparkles className="w-4 h-4" />
                </div>
                <h3 className="text-sm font-bold text-white">Generate Intelligence Report</h3>
              </div>
              <button
                onClick={() => !generatingJobId && setIsGenerateOpen(false)}
                disabled={Boolean(generatingJobId)}
                className="text-slate-400 hover:text-white p-1 rounded-lg"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {generatingJobId ? (
              <div className="p-8 text-center space-y-4">
                <Loader2 className="w-8 h-8 animate-spin text-amber-500 mx-auto" />
                <div>
                  <h4 className="text-sm font-semibold text-white">Synthesizing Artifacts...</h4>
                  <p className="text-xs text-slate-400 mt-1">
                    Generating structured sections, forensic observations, and PDF layout.
                  </p>
                </div>
                {/* Progress bar */}
                <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
                  <div
                    className="bg-amber-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${jobProgress || 20}%` }}
                  />
                </div>
                <p className="text-[11px] font-mono text-slate-400">{jobProgress}% complete</p>
              </div>
            ) : (
              <form onSubmit={handleStartGeneration} className="space-y-4">
                {/* Conversation Picker */}
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                    Select Target Conversation
                  </label>
                  <select
                    value={targetConvId}
                    onChange={(e) => setTargetConvId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500"
                  >
                    {convData?.items?.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.title}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Language Picker */}
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                    Target Report Language
                  </label>
                  <select
                    value={reportLang}
                    onChange={(e) => setReportLang(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500"
                  >
                    <option value="en">English</option>
                    <option value="hi">Hindi (हिंदी - Devanagari)</option>
                    <option value="ta">Tamil (தமிழ்)</option>
                  </select>
                </div>

                {/* Synthesis Length */}
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                    Synthesis Scope & Length
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {(["brief", "standard", "detailed"] as const).map((len) => (
                      <button
                        key={len}
                        type="button"
                        onClick={() => setReportLength(len)}
                        className={`p-2 rounded-xl text-xs font-medium capitalize border transition-colors ${
                          reportLength === len
                            ? "bg-amber-500/20 border-amber-500/50 text-amber-200"
                            : "bg-slate-950 border-slate-800 text-slate-400 hover:text-white"
                        }`}
                      >
                        {len}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Checkboxes */}
                <div className="space-y-2 pt-2 border-t border-slate-800">
                  <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeImages}
                      onChange={(e) => setIncludeImages(e.target.checked)}
                      className="rounded bg-slate-950 border-slate-700 text-amber-500 focus:ring-0"
                    />
                    <span>Include visual evidence tables & object counts</span>
                  </label>
                  <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeMetrics}
                      onChange={(e) => setIncludeMetrics(e.target.checked)}
                      className="rounded bg-slate-950 border-slate-700 text-amber-500 focus:ring-0"
                    />
                    <span>Include appendix with models used & latency telemetry</span>
                  </label>
                </div>

                <div className="flex items-center justify-end space-x-2 pt-3">
                  <button
                    type="button"
                    onClick={() => setIsGenerateOpen(false)}
                    className="px-3 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white shadow-md transition-colors"
                  >
                    Compile Report
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Report Preview Modal */}
      {selectedReportId && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in"
        >
          <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-4xl h-[85vh] flex flex-col overflow-hidden shadow-2xl">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center space-x-2.5">
                <FileText className="w-5 h-5 text-amber-400" />
                <h3 className="text-sm font-bold text-white truncate max-w-md">
                  {activeReport?.title || "Report Preview"}
                </h3>
              </div>

              <div className="flex items-center space-x-2">
                {activeReport && (
                  <button
                    onClick={() => handleDownloadPdf(activeReport.id, activeReport.title)}
                    className="flex items-center space-x-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold rounded-xl shadow-md transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download PDF</span>
                  </button>
                )}
                <button
                  onClick={() => setSelectedReportId(null)}
                  className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs text-slate-300">
              {isLoadingDetail ? (
                <div className="p-12 flex flex-col items-center justify-center space-y-2 text-slate-400">
                  <Loader2 className="w-6 h-6 animate-spin text-amber-500" />
                  <span>Loading report content...</span>
                </div>
              ) : activeReport ? (
                <>
                  {/* Executive Summary */}
                  {activeReport.content.executive_summary && (
                    <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 space-y-2">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-amber-400">
                        1. Executive Summary
                      </h4>
                      <p className="leading-relaxed text-slate-200">
                        {activeReport.content.executive_summary}
                      </p>
                    </div>
                  )}

                  {/* Sections */}
                  {activeReport.content.sections?.map((sec, idx) => (
                    <div key={idx} className="p-4 rounded-2xl bg-slate-950 border border-slate-800 space-y-2">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                        {sec.heading}
                      </h4>
                      <p className="leading-relaxed text-slate-300">{sec.body}</p>
                      {sec.bullet_points && sec.bullet_points.length > 0 && (
                        <ul className="space-y-1 pl-3 list-disc text-slate-400">
                          {sec.bullet_points.map((pt, pidx) => (
                            <li key={pidx}>{pt}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}

                  {/* Observations */}
                  {activeReport.content.cross_modal_observations &&
                    activeReport.content.cross_modal_observations.length > 0 && (
                      <div className="p-4 rounded-2xl bg-indigo-950/20 border border-indigo-500/20 space-y-2">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
                          Cross-Modal Observations
                        </h4>
                        <ul className="space-y-1.5">
                          {activeReport.content.cross_modal_observations.map((obs, oidx) => (
                            <li key={oidx} className="flex items-start space-x-2 text-slate-300">
                              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 shrink-0" />
                              <span>{obs}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                  {/* Conclusions & Recommendations */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {activeReport.content.conclusions && activeReport.content.conclusions.length > 0 && (
                      <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 space-y-2">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-emerald-400">
                          Conclusions
                        </h4>
                        <ul className="space-y-1 list-disc pl-3 text-slate-300">
                          {activeReport.content.conclusions.map((c, cidx) => (
                            <li key={cidx}>{c}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {activeReport.content.recommendations &&
                      activeReport.content.recommendations.length > 0 && (
                        <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 space-y-2">
                          <h4 className="text-xs font-semibold uppercase tracking-wider text-amber-400">
                            Recommendations
                          </h4>
                          <ul className="space-y-1 list-disc pl-3 text-slate-300">
                            {activeReport.content.recommendations.map((r, ridx) => (
                              <li key={ridx}>{r}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                  </div>
                </>
              ) : (
                <div>Report content unavailable</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingId && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in"
        >
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 max-w-sm w-full shadow-2xl space-y-4">
            <div className="w-10 h-10 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">Delete Report?</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                This will permanently delete this report record and purge its compiled PDF file from storage disk.
              </p>
            </div>
            <div className="flex items-center justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setDeletingId(null)}
                className="px-3 py-1.5 rounded-xl text-xs font-medium text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => deleteMutation.mutate(deletingId)}
                className="px-4 py-1.5 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
