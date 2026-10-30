import React, { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Search as SearchIcon,
  Image as ImageIcon,
  Headphones,
  FileText,
  RefreshCw,
  SlidersHorizontal,
  ExternalLink,
  Clock,
  Layers,
  Upload,
  X,
  Loader2,
  Database,
} from "lucide-react";
import { apiClient } from "../api/client";
import { useToast } from "../context/ToastContext";
import { formatSecondsToTime } from "../utils/citations";

interface SearchResultItem {
  id: string;
  modality: "text" | "audio" | "image";
  score: number;
  snippet: string;
  attachment_id?: string | null;
  conversation_id?: string | null;
  start?: number | null;
  end?: number | null;
  metadata?: Record<string, unknown>;
}

interface SearchResponse {
  query: string;
  total_results: number;
  results: SearchResultItem[];
  latency_ms: number;
}

interface SearchStats {
  text_count: number;
  audio_count: number;
  image_count: number;
  total: number;
}

export const Search: React.FC = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [query, setQuery] = useState("");
  const [selectedModality, setSelectedModality] = useState<string>("all");
  const [rerank, setRerank] = useState(false);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [reindexing, setReindexing] = useState(false);

  const imageInputRef = useRef<HTMLInputElement | null>(null);

  // Fetch Vault stats
  const { data: stats } = useQuery<SearchStats>({
    queryKey: ["vaultStats"],
    queryFn: () => apiClient.get<SearchStats>("/search/stats"),
  });

  // Reindex Vault mutation
  const reindexMutation = useMutation({
    mutationFn: () => apiClient.post<{ job_id: string; status: string }>("/search/reindex"),
    onSuccess: async (data) => {
      setReindexing(true);
      toast.info("Vault reindexing queued...");
      const jobId = data.job_id;

      // Poll job
      const interval = setInterval(async () => {
        try {
          const job = await apiClient.get<{ status: string; progress: number }>(`/jobs/${jobId}`);
          if (job.status === "done") {
            clearInterval(interval);
            setReindexing(false);
            toast.success("Knowledge Vault successfully reindexed!");
            queryClient.invalidateQueries({ queryKey: ["vaultStats"] });
          } else if (job.status === "failed") {
            clearInterval(interval);
            setReindexing(false);
            toast.error("Reindex job failed");
          }
        } catch {
          clearInterval(interval);
          setReindexing(false);
        }
      }, 1000);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to trigger reindex";
      toast.error(msg);
    },
  });

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim() && !imageFile) {
      toast.info("Enter a search query or attach an image");
      return;
    }

    setIsSearching(true);
    try {
      if (imageFile) {
        // Image-based search
        const formData = new FormData();
        formData.append("file", imageFile);
        formData.append("rerank", String(rerank));
        formData.append("top_k", "15");

        const res = await apiClient.request<SearchResponse>("/search/by-image", {
          method: "POST",
          body: formData,
        });
        setSearchResponse(res);
      } else {
        // Text-based cross-modal search
        const modalities =
          selectedModality === "all" ? undefined : [selectedModality];

        const res = await apiClient.post<SearchResponse>("/search", {
          query: query.trim(),
          modalities,
          rerank,
          top_k: 20,
        });
        setSearchResponse(res);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Search failed";
      toast.error(msg);
    } finally {
      setIsSearching(false);
    }
  };

  const handleImageSelected = (file: File) => {
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setImageFile(file);
    setImagePreview(URL.createObjectURL(file));
  };

  const handleClearImage = () => {
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setImageFile(null);
    setImagePreview(null);
  };

  const handleJumpToResult = (item: SearchResultItem) => {
    if (!item.conversation_id) {
      toast.info("No linked conversation found for this item");
      return;
    }
    const params = new URLSearchParams();
    params.set("conversation_id", item.conversation_id);
    if (item.attachment_id) params.set("attachment_id", item.attachment_id);
    if (item.start) params.set("t", String(item.start));
    params.set("modality", item.modality);

    navigate(`/chat?${params.toString()}`);
  };

  // Group results by modality
  const results = searchResponse?.results || [];
  const textResults = results.filter((r) => r.modality === "text");
  const audioResults = results.filter((r) => r.modality === "audio");
  const imageResults = results.filter((r) => r.modality === "image");

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-8 space-y-6">
      {/* Header and Vault Index Stats */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-3xl bg-slate-900/60 border border-slate-800 shadow-xl backdrop-blur-md">
        <div className="flex items-center space-x-3.5">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-sky-500/20">
            <Database className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white tracking-tight">
              Knowledge Vault & Semantic Search
            </h2>
            <p className="text-xs text-slate-400">
              Cross-modal vector embeddings powered by multilingual SigLIP & BAAI/BGE
            </p>
          </div>
        </div>

        {/* Index Stats & Reindex Action */}
        <div className="flex items-center space-x-3">
          <div className="hidden sm:flex items-center space-x-3 text-xs font-mono bg-slate-950/70 px-3.5 py-1.5 rounded-xl border border-slate-800">
            <span className="text-slate-400">Indexed:</span>
            <span className="text-sky-400">{stats?.text_count ?? 0} texts</span>
            <span className="text-slate-600">&bull;</span>
            <span className="text-indigo-400">{stats?.audio_count ?? 0} audio</span>
            <span className="text-slate-600">&bull;</span>
            <span className="text-purple-400">{stats?.image_count ?? 0} images</span>
          </div>

          <button
            onClick={() => reindexMutation.mutate()}
            disabled={reindexing || reindexMutation.isPending}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition-colors disabled:opacity-50"
            title="Rebuild user Knowledge Vault indices"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${reindexing ? "animate-spin text-sky-400" : ""}`} />
            <span>{reindexing ? "Reindexing..." : "Reindex"}</span>
          </button>
        </div>
      </div>

      {/* Search Input Box */}
      <div className="p-5 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-2xl space-y-4">
        <form onSubmit={handleSearch} className="space-y-4">
          <div className="relative flex items-center">
            <SearchIcon className="w-5 h-5 text-slate-500 absolute left-4" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search across conversations, speech transcripts, and scene descriptions..."
              disabled={Boolean(imageFile)}
              className="w-full bg-slate-950 border border-slate-800 rounded-2xl pl-12 pr-28 py-3.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 shadow-inner disabled:opacity-50 transition-colors"
            />
            <button
              type="submit"
              disabled={isSearching || (!query.trim() && !imageFile)}
              className="absolute right-2 px-4 py-2 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white text-xs font-semibold rounded-xl shadow-md transition-all disabled:opacity-40"
            >
              {isSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : "Search"}
            </button>
          </div>

          {/* Controls: Modality Filters, Rerank Toggle, Search by Image Upload */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            {/* Modality Chips */}
            <div className="flex items-center space-x-1.5">
              <span className="text-xs text-slate-500 mr-1">Modality:</span>
              {[
                { id: "all", label: "All Assets", icon: Layers },
                { id: "text", label: "Text Chunks", icon: FileText },
                { id: "audio", label: "Audio Transcripts", icon: Headphones },
                { id: "image", label: "Visual Scenes", icon: ImageIcon },
              ].map((m) => {
                const Icon = m.icon;
                const isSelected = selectedModality === m.id;
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => setSelectedModality(m.id)}
                    className={`flex items-center space-x-1 px-3 py-1.5 rounded-xl text-xs font-medium border transition-colors ${
                      isSelected
                        ? "bg-sky-500/20 text-sky-300 border-sky-500/40 shadow-sm"
                        : "bg-slate-950 text-slate-400 hover:text-white border-slate-800"
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{m.label}</span>
                  </button>
                );
              })}
            </div>

            <div className="flex items-center space-x-3">
              {/* Optional LLM Rerank Toggle */}
              <label className="flex items-center space-x-2 text-xs text-slate-400 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={rerank}
                  onChange={(e) => setRerank(e.target.checked)}
                  className="rounded bg-slate-950 border-slate-700 text-indigo-600 focus:ring-0"
                />
                <span className="inline-flex items-center space-x-1">
                  <SlidersHorizontal className="w-3 h-3 text-indigo-400" />
                  <span>LLM Rerank</span>
                </span>
              </label>

              {/* Search by Image Button */}
              <input
                ref={imageInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.[0]) handleImageSelected(e.target.files[0]);
                  e.target.value = "";
                }}
              />
              <button
                type="button"
                onClick={() => imageInputRef.current?.click()}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-colors ${
                  imageFile
                    ? "bg-purple-600 text-white border-purple-500"
                    : "bg-slate-950 text-slate-400 hover:text-white border-slate-800 hover:border-slate-700"
                }`}
                title="Search by image upload"
              >
                <Upload className="w-3.5 h-3.5" />
                <span>Search by Image</span>
              </button>
            </div>
          </div>

          {/* Image Query Preview */}
          {imagePreview && (
            <div className="flex items-center space-x-3 p-3 rounded-2xl bg-slate-950 border border-purple-500/30">
              <img
                src={imagePreview}
                alt="Search query reference"
                className="w-12 h-12 rounded-xl object-cover border border-purple-500/40"
              />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-purple-200 truncate">{imageFile?.name}</p>
                <p className="text-[10px] text-slate-400">Image visual similarity search active</p>
              </div>
              <button
                type="button"
                onClick={handleClearImage}
                className="p-1 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}
        </form>
      </div>

      {/* Search Results Display */}
      {searchResponse && (
        <div className="space-y-6">
          <div className="flex items-center justify-between text-xs text-slate-400 px-1">
            <span>
              Found <strong className="text-white">{searchResponse.total_results}</strong> relevant items for &ldquo;{searchResponse.query}&rdquo;
            </span>
            <span className="font-mono">Latency: {searchResponse.latency_ms}ms</span>
          </div>

          {results.length === 0 ? (
            <div className="p-12 text-center rounded-3xl border border-dashed border-slate-800 text-slate-500 text-xs">
              No matching vectors found across your conversations. Try broadening your query terms or reindexing.
            </div>
          ) : (
            <div className="space-y-6">
              {/* Grouped: Text Chunks */}
              {textResults.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-2">
                    <FileText className="w-4 h-4 text-sky-400" />
                    <span>Text & Thought Excerpts ({textResults.length})</span>
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {textResults.map((item) => (
                      <div
                        key={item.id}
                        onClick={() => handleJumpToResult(item)}
                        className="group p-4 rounded-2xl bg-slate-900/60 hover:bg-slate-850 border border-slate-800 hover:border-sky-500/50 cursor-pointer transition-all shadow-md space-y-2.5"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono text-sky-400 text-[11px] font-semibold">
                            Score: {(item.score * 100).toFixed(1)}%
                          </span>
                          <span className="text-slate-500 group-hover:text-sky-300 flex items-center space-x-1">
                            <span>Open Chat</span>
                            <ExternalLink className="w-3 h-3" />
                          </span>
                        </div>
                        <p className="text-xs text-slate-200 line-clamp-3 leading-relaxed">
                          {item.snippet}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Grouped: Audio Transcript Segments */}
              {audioResults.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-2">
                    <Headphones className="w-4 h-4 text-indigo-400" />
                    <span>Audio & Spoken Segments ({audioResults.length})</span>
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {audioResults.map((item) => (
                      <div
                        key={item.id}
                        onClick={() => handleJumpToResult(item)}
                        className="group p-4 rounded-2xl bg-slate-900/60 hover:bg-slate-850 border border-slate-800 hover:border-indigo-500/50 cursor-pointer transition-all shadow-md space-y-2.5"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono text-indigo-400 text-[11px] font-semibold">
                            Score: {(item.score * 100).toFixed(1)}%
                          </span>
                          {item.start !== null && item.start !== undefined && (
                            <span className="font-mono text-[11px] text-slate-400 flex items-center space-x-1 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                              <Clock className="w-3 h-3 text-indigo-400" />
                              <span>{formatSecondsToTime(item.start)}</span>
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-200 line-clamp-3 leading-relaxed italic">
                          &ldquo;{item.snippet}&rdquo;
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Grouped: Visual Scenes */}
              {imageResults.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-2">
                    <ImageIcon className="w-4 h-4 text-purple-400" />
                    <span>Visual Scenes & Object Analyses ({imageResults.length})</span>
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {imageResults.map((item) => (
                      <div
                        key={item.id}
                        onClick={() => handleJumpToResult(item)}
                        className="group p-4 rounded-2xl bg-slate-900/60 hover:bg-slate-850 border border-slate-800 hover:border-purple-500/50 cursor-pointer transition-all shadow-md space-y-2.5"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono text-purple-400 text-[11px] font-semibold">
                            Score: {(item.score * 100).toFixed(1)}%
                          </span>
                          <span className="text-slate-500 group-hover:text-purple-300 flex items-center space-x-1">
                            <span>Inspect</span>
                            <ExternalLink className="w-3 h-3" />
                          </span>
                        </div>
                        <p className="text-xs text-slate-300 line-clamp-3 leading-relaxed">
                          {item.snippet}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
