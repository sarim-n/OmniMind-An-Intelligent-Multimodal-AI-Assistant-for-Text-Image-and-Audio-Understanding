import React, { useEffect, useState } from "react";
import {
  X,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Layers,
  AlertTriangle,
  Eye,
  Tag,
  MessageSquare,
  Send,
  Loader2,
} from "lucide-react";
import { apiClient } from "../api/client";

export interface DetectedObject {
  label: string;
  confidence: number;
  box: [number, number, number, number]; // [ymin, xmin, ymax, xmax] or [x, y, w, h]
}

export interface ImageAnalysisData {
  id?: string;
  attachment_id: string;
  caption?: string;
  objects?: DetectedObject[];
  quality?: Record<string, unknown>;
  warnings?: string[];
  annotated_path?: string;
}

interface ImageViewerModalProps {
  attachmentId: string;
  filename?: string;
  initialAnalysis?: ImageAnalysisData;
  onClose: () => void;
}

export const ImageViewerModal: React.FC<ImageViewerModalProps> = ({
  attachmentId,
  filename,
  initialAnalysis,
  onClose,
}) => {
  const [zoom, setZoom] = useState<number>(1);
  const [showAnnotated, setShowAnnotated] = useState<boolean>(false);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [annotatedUrl, setAnnotatedUrl] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<ImageAnalysisData | null>(initialAnalysis || null);
  const [loadingMedia, setLoadingMedia] = useState<boolean>(true);
  const [loadingAnnotated, setLoadingAnnotated] = useState<boolean>(false);
  const [vqaQuestion, setVqaQuestion] = useState("");
  const [vqaAnswer, setVqaAnswer] = useState<string | null>(null);
  const [askingVqa, setAskingVqa] = useState(false);

  // Load original image and analysis
  useEffect(() => {
    let active = true;
    let origBlobUrl: string | null = null;

    setLoadingMedia(true);

    // Fetch original file
    apiClient
      .fetchBlobUrl(`/images/${attachmentId}/file`)
      .then((url) => {
        if (!active) {
          URL.revokeObjectURL(url);
          return;
        }
        origBlobUrl = url;
        setOriginalUrl(url);
      })
      .catch((err) => {
        console.error("Failed to load original image:", err);
      })
      .finally(() => {
        if (active) setLoadingMedia(false);
      });

    // Fetch analysis if not provided
    if (!initialAnalysis) {
      apiClient
        .get<ImageAnalysisData>(`/images/${attachmentId}/analysis`)
        .then((data) => {
          if (active) setAnalysis(data);
        })
        .catch(() => {
          // May not have analysis if uploaded as generic image
        });
    }

    return () => {
      active = false;
      if (origBlobUrl) URL.revokeObjectURL(origBlobUrl);
    };
  }, [attachmentId, initialAnalysis]);

  // Load annotated image when toggle is requested
  useEffect(() => {
    let active = true;
    let annBlobUrl: string | null = null;

    if (showAnnotated && !annotatedUrl) {
      setLoadingAnnotated(true);
      apiClient
        .fetchBlobUrl(`/images/${attachmentId}/annotated`)
        .then((url) => {
          if (!active) {
            URL.revokeObjectURL(url);
            return;
          }
          annBlobUrl = url;
          setAnnotatedUrl(url);
        })
        .catch((err) => {
          console.warn("No annotated image available:", err);
          setShowAnnotated(false);
        })
        .finally(() => {
          if (active) setLoadingAnnotated(false);
        });
    }

    return () => {
      active = false;
      if (annBlobUrl) URL.revokeObjectURL(annBlobUrl);
    };
  }, [showAnnotated, annotatedUrl, attachmentId]);

  // Handle ESC key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const handleAskVqa = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!vqaQuestion.trim() || askingVqa) return;
    setAskingVqa(true);
    setVqaAnswer(null);
    try {
      const res = await apiClient.post<{ answer: string }>(`/images/${attachmentId}/ask`, {
        question: vqaQuestion.trim(),
      });
      setVqaAnswer(res.answer);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to answer question";
      setVqaAnswer(`Error: ${msg}`);
    } finally {
      setAskingVqa(false);
    }
  };

  const currentDisplayUrl = showAnnotated && annotatedUrl ? annotatedUrl : originalUrl;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Image viewer"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
    >
      <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-5xl h-[90vh] flex flex-col overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
              <Eye className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white">
                {filename || "Image Inspection & Object Detection"}
              </h2>
              <p className="text-xs text-slate-400 font-mono">ID: {attachmentId}</p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            {/* Zoom Controls */}
            <div className="flex items-center bg-slate-800/80 rounded-xl p-1 border border-slate-700">
              <button
                onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
                className="p-1.5 hover:text-white text-slate-300 transition-colors"
                title="Zoom Out"
                aria-label="Zoom Out"
              >
                <ZoomOut className="w-4 h-4" />
              </button>
              <span className="text-xs font-mono px-2 text-slate-300">{Math.round(zoom * 100)}%</span>
              <button
                onClick={() => setZoom((z) => Math.min(3, z + 0.25))}
                className="p-1.5 hover:text-white text-slate-300 transition-colors"
                title="Zoom In"
                aria-label="Zoom In"
              >
                <ZoomIn className="w-4 h-4" />
              </button>
              <button
                onClick={() => setZoom(1)}
                className="p-1.5 hover:text-white text-slate-300 transition-colors border-l border-slate-700 ml-1 pl-2"
                title="Reset Zoom"
                aria-label="Reset Zoom"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Toggle Annotated */}
            <button
              onClick={() => setShowAnnotated((prev) => !prev)}
              disabled={loadingAnnotated}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-colors ${
                showAnnotated
                  ? "bg-purple-600 border-purple-500 text-white"
                  : "bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-300"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>{showAnnotated ? "Annotated View" : "Show Bounding Boxes"}</span>
              {loadingAnnotated && <Loader2 className="w-3 h-3 animate-spin ml-1" />}
            </button>

            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-xl transition-colors"
              aria-label="Close image viewer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content Body: Split View */}
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Main Image Viewport */}
          <div className="flex-1 bg-slate-950/50 flex items-center justify-center p-4 overflow-auto relative">
            {loadingMedia ? (
              <div className="flex flex-col items-center space-y-2 text-slate-400">
                <Loader2 className="w-8 h-8 animate-spin text-purple-400" />
                <span className="text-xs">Loading visual asset...</span>
              </div>
            ) : currentDisplayUrl ? (
              <div
                className="transition-transform duration-100 ease-out flex items-center justify-center"
                style={{ transform: `scale(${zoom})` }}
              >
                <img
                  src={currentDisplayUrl}
                  alt={analysis?.caption || "Visual Attachment"}
                  className="max-h-[70vh] max-w-full rounded-xl object-contain shadow-2xl border border-slate-800"
                />
              </div>
            ) : (
              <div className="text-xs text-slate-500">Failed to render image content</div>
            )}
          </div>

          {/* Right Sidebar: Details, Objects, Warnings, VQA */}
          <div className="w-full md:w-80 lg:w-96 border-t md:border-t-0 md:border-l border-slate-800 bg-slate-900/60 p-5 overflow-y-auto space-y-5">
            {/* Caption */}
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                Vision Caption
              </h3>
              <p className="text-sm text-slate-200 bg-slate-800/40 p-3 rounded-xl border border-slate-800 leading-relaxed">
                {analysis?.caption || "Caption generated upon vision inference."}
              </p>
            </div>

            {/* Quality Warnings */}
            {analysis?.warnings && analysis.warnings.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-amber-400 mb-2 flex items-center space-x-1.5">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>Quality Warnings</span>
                </h3>
                <div className="space-y-1.5">
                  {analysis.warnings.map((w, idx) => (
                    <div
                      key={idx}
                      className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 px-3 py-1.5 rounded-lg"
                    >
                      {w}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Detected Objects */}
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center space-x-1.5">
                <Tag className="w-3.5 h-3.5" />
                <span>Detected Objects ({analysis?.objects?.length ?? 0})</span>
              </h3>
              {analysis?.objects && analysis.objects.length > 0 ? (
                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {analysis.objects.map((obj, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between p-2 rounded-lg bg-slate-800/40 border border-slate-800 text-xs"
                    >
                      <span className="font-medium text-slate-200 capitalize">{obj.label}</span>
                      <span className="font-mono px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30">
                        {Math.round(obj.confidence * 100)}%
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500 italic">No discrete objects detected.</p>
              )}
            </div>

            {/* Interactive Visual Q&A (VQA) */}
            <div className="pt-2 border-t border-slate-800">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center space-x-1.5">
                <MessageSquare className="w-3.5 h-3.5" />
                <span>Ask About Image (VQA)</span>
              </h3>
              <form onSubmit={handleAskVqa} className="space-y-2">
                <div className="relative">
                  <input
                    type="text"
                    value={vqaQuestion}
                    onChange={(e) => setVqaQuestion(e.target.value)}
                    placeholder="What is written on the sign?"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 pr-9 focus:outline-none focus:border-purple-500"
                  />
                  <button
                    type="submit"
                    disabled={askingVqa || !vqaQuestion.trim()}
                    className="absolute right-1.5 top-1.5 p-1 rounded-lg bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50 transition-colors"
                  >
                    {askingVqa ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Send className="w-3 h-3" />
                    )}
                  </button>
                </div>
              </form>

              {vqaAnswer && (
                <div className="mt-3 p-3 rounded-xl bg-purple-950/20 border border-purple-800/40 text-xs text-purple-200 animate-in fade-in">
                  <p className="font-semibold text-purple-300 mb-1">VLM Answer:</p>
                  <p className="leading-relaxed">{vqaAnswer}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
