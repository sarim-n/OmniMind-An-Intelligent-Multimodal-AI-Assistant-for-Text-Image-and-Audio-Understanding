import React, { useEffect, useState, useRef, useTransition } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot,
  User,
  FileText,
  Download,
  Headphones,
  Image as ImageIcon,
  Loader2,
  ExternalLink,
} from "lucide-react";
import { apiClient } from "../api/client";
import { streamSSE } from "../api/sse";
import { Composer } from "../components/Composer";
import { ImageViewerModal } from "../components/ImageViewerModal";
import { AudioViewerModal } from "../components/AudioViewerModal";
import { MessageSkeleton } from "../components/Skeleton";
import { useToast } from "../context/ToastContext";
import {
  parseMessageCitations,
  type Citation,
  type MessageSegment,
} from "../utils/citations";

interface MessageItem {
  id: string;
  role: "user" | "assistant";
  content: string;
  language?: string | null;
  created_at: string;
  attachments?: Array<{
    id: string;
    filename: string;
    file_type: "image" | "audio" | "document";
  }>;
  statusChips?: string[];
  reportCard?: {
    id: string;
    title: string;
    pdf_url?: string;
    summary?: string;
  };
}

interface MessageListResponse {
  items: MessageItem[];
  total: number;
}

export const Chat: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const conversationId = searchParams.get("conversation_id");
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [, startTransition] = useTransition();

  const [streamingMessage, setStreamingMessage] = useState<MessageItem | null>(null);
  const [statusChip, setStatusChip] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Modals state for inline citations & attachments
  const [selectedImage, setSelectedImage] = useState<{ id: string; filename?: string } | null>(null);
  const [selectedAudio, setSelectedAudio] = useState<{
    id: string;
    filename?: string;
    seekSec?: number;
  } | null>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // If no conversation_id in URL, find or create one
  useEffect(() => {
    if (!conversationId) {
      apiClient
        .get<{ items: Array<{ id: string }> }>("/conversations", { page_size: 1 })
        .then((res) => {
          if (res.items && res.items.length > 0) {
            setSearchParams({ conversation_id: res.items[0]!.id }, { replace: true });
          } else {
            apiClient
              .post<{ id: string }>("/conversations", { title: "New Conversation" })
              .then((newConv) => {
                queryClient.invalidateQueries({ queryKey: ["conversations"] });
                setSearchParams({ conversation_id: newConv.id }, { replace: true });
              })
              .catch((err) => console.error("Could not create conversation:", err));
          }
        })
        .catch((err) => console.error("Could not fetch conversations:", err));
    }
  }, [conversationId, setSearchParams, queryClient]);

  // Load message history
  const { data: messagesData, isLoading: isLoadingMessages } = useQuery<MessageListResponse>({
    queryKey: ["messages", conversationId],
    queryFn: () =>
      apiClient.get<MessageListResponse>(`/conversations/${conversationId}/messages`, {
        page_size: 100,
      }),
    enabled: Boolean(conversationId),
  });

  const messages = messagesData?.items || [];

  // Auto-scroll
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingMessage, statusChip]);

  // Check URL params for deep links (e.g. from search: ?attachment_id=...&t=...)
  useEffect(() => {
    const attId = searchParams.get("attachment_id");
    const t = searchParams.get("t");
    const modality = searchParams.get("modality");

    if (attId) {
      if (modality === "image") {
        setSelectedImage({ id: attId });
      } else if (modality === "audio" || t) {
        setSelectedAudio({ id: attId, seekSec: t ? Number(t) : 0 });
      }
    }
  }, [searchParams]);

  // Handle SSE streaming message send
  const handleSendMessage = async (payload: {
    content: string;
    language?: string;
    images: File[];
    audio?: File | Blob;
  }) => {
    if (!conversationId || isStreaming) return;

    // Optimistically create user message in UI
    const tempUserMsgId = `user_${Date.now()}`;
    const userMsg: MessageItem = {
      id: tempUserMsgId,
      role: "user",
      content: payload.content || "(Sent attachment)",
      language: payload.language,
      created_at: new Date().toISOString(),
    };

    queryClient.setQueryData<MessageListResponse>(["messages", conversationId], (old) => {
      if (!old) return { items: [userMsg], total: 1 };
      return { ...old, items: [...old.items, userMsg], total: old.total + 1 };
    });

    // Prepare assistant streaming placeholder
    const tempAssistantMsgId = `assistant_${Date.now()}`;
    const initialAssistantMsg: MessageItem = {
      id: tempAssistantMsgId,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
      statusChips: [],
    };

    setStreamingMessage(initialAssistantMsg);
    setIsStreaming(true);
    setStatusChip("Initiating multimodal orchestrator...");

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Build FormData
    const formData = new FormData();
    if (payload.content) formData.append("content", payload.content);
    if (payload.language) formData.append("language", payload.language);
    payload.images.forEach((img) => formData.append("images", img));
    if (payload.audio) {
      formData.append(
        "audio",
        payload.audio,
        (payload.audio as File).name || "recorded_audio.webm"
      );
    }

    try {
      await streamSSE({
        url: `${apiClient["buildUrl"]?.(`/conversations/${conversationId}/messages?stream=true`) || `/api/v1/conversations/${conversationId}/messages?stream=true`}`,
        headers: {
          Authorization: `Bearer ${apiClient.getToken()}`,
        },
        body: formData,
        signal: controller.signal,
        onEvent: (event) => {
          const type = event.event;
          const data = event.data;

          if (type === "status") {
            const msg = data?.message || data?.stage || "Processing...";
            setStatusChip(msg);
          } else if (type === "token") {
            setStatusChip(null);
            const tokenStr = data?.text || data?.token || "";
            startTransition(() => {
              setStreamingMessage((prev) => {
                if (!prev) return prev;
                return { ...prev, content: prev.content + tokenStr };
              });
            });
          } else if (type === "transcript") {
            setStatusChip(`Audio transcribed (${data?.language || "detected"})`);
          } else if (type === "image_analysis") {
            setStatusChip("Visual analysis extracted");
          } else if (type === "report") {
            setStreamingMessage((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                reportCard: {
                  id: data?.id || "",
                  title: data?.title || "Multimodal Executive Report",
                  pdf_url: data?.pdf_url,
                  summary: data?.summary,
                },
              };
            });
          } else if (type === "done") {
            setStatusChip(null);
          } else if (type === "error") {
            const errStr = data?.message || data?.error || "Streaming error encountered";
            toast.error(errStr);
            setStatusChip(null);
          }
        },
        onDone: () => {
          setIsStreaming(false);
          setStatusChip(null);
          setStreamingMessage(null);
          queryClient.invalidateQueries({ queryKey: ["messages", conversationId] });
          queryClient.invalidateQueries({ queryKey: ["conversations"] });
        },
        onError: (err) => {
          setIsStreaming(false);
          setStatusChip(null);
          if (controller.signal.aborted) {
            toast.info("Message generation cancelled");
          } else {
            toast.error(err.message || "Message streaming failed");
          }
          queryClient.invalidateQueries({ queryKey: ["messages", conversationId] });
        },
      });
    } catch {
      setIsStreaming(false);
      setStatusChip(null);
    }
  };

  const handleAbort = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
      setStatusChip(null);
    }
  };

  const handleDownloadReportPdf = async (reportId?: string) => {
    try {
      toast.info("Preparing PDF report download...");
      const path = reportId
        ? `/reports/${reportId}/pdf`
        : `/conversations/${conversationId}/report/pdf`;
      const blob = await apiClient.fetchBlob(path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `OmniMind_Report_${reportId || conversationId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("Report PDF downloaded");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to download report PDF";
      toast.error(msg);
    }
  };

  const handleCitationClick = (citation: Citation) => {
    if (citation.type === "image") {
      // Find matching attachment ID or target
      setSelectedImage({
        id: citation.target,
        filename: citation.target,
      });
    } else if (citation.type === "audio") {
      setSelectedAudio({
        id: citation.target,
        filename: citation.target,
        seekSec: citation.timestampSec,
      });
    }
  };

  // Render text with clickable inline citations
  const renderMessageContentWithCitations = (rawText: string) => {
    const segments: MessageSegment[] = parseMessageCitations(rawText);

    return segments.map((seg, idx) => {
      if (seg.type === "text") {
        return (
          <ReactMarkdown
            key={idx}
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <span className="inline leading-relaxed">{children} </span>,
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="text-indigo-400 hover:text-indigo-300 underline font-medium"
                >
                  {children}
                </a>
              ),
              code: ({ className, children }) => {
                const isInline = !className;
                return isInline ? (
                  <code className="bg-slate-800/80 px-1.5 py-0.5 rounded text-[11px] font-mono text-purple-300 border border-slate-700/60">
                    {children}
                  </code>
                ) : (
                  <pre className="bg-slate-950 p-3 rounded-xl overflow-x-auto my-2 text-xs font-mono text-slate-200 border border-slate-800">
                    <code>{children}</code>
                  </pre>
                );
              },
            }}
          >
            {seg.content}
          </ReactMarkdown>
        );
      }

      // Inline citation chip
      const cit = seg.citation;
      return (
        <button
          key={idx}
          onClick={() => handleCitationClick(cit)}
          type="button"
          className="inline-flex items-center space-x-1.5 mx-1 px-2.5 py-0.5 rounded-lg text-[11px] font-medium transition-all shadow-sm cursor-pointer select-none border align-middle bg-indigo-500/15 hover:bg-indigo-500/25 text-indigo-300 border-indigo-500/30"
          title={
            cit.type === "audio"
              ? `Jump audio playback to ${cit.timestampFormatted}`
              : `Open visual attachment ${cit.target}`
          }
        >
          {cit.type === "audio" ? (
            <>
              <Headphones className="w-3 h-3 text-indigo-400" />
              <span className="font-mono text-indigo-200">{cit.target}</span>
              <span className="font-mono text-indigo-400 font-bold">[{cit.timestampFormatted}]</span>
            </>
          ) : (
            <>
              <ImageIcon className="w-3 h-3 text-purple-400" />
              <span className="font-mono text-purple-200">{cit.target}</span>
            </>
          )}
          <ExternalLink className="w-2.5 h-2.5 opacity-60" />
        </button>
      );
    });
  };

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)] md:h-screen max-w-5xl mx-auto p-3 sm:p-6 space-y-4">
      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto space-y-5 pr-2">
        {isLoadingMessages ? (
          <MessageSkeleton />
        ) : messages.length === 0 && !streamingMessage ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 text-slate-500 space-y-4">
            <div className="w-14 h-14 rounded-3xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shadow-xl shadow-indigo-500/10">
              <Bot className="w-7 h-7" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-slate-200">Multimodal Intelligence Assistant</h3>
              <p className="text-xs text-slate-400 max-w-sm mt-1">
                Ask analytical questions across text, images, and audio. Type a prompt, attach images, or speak into the microphone.
              </p>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex items-start space-x-3 ${
                msg.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              {msg.role === "assistant" && (
                <div className="w-8 h-8 rounded-xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400 shrink-0 shadow-md">
                  <Bot className="w-4 h-4" />
                </div>
              )}

              <div
                className={`max-w-2xl rounded-2xl p-4 text-xs leading-relaxed shadow-lg ${
                  msg.role === "user"
                    ? "bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-tr-sm"
                    : "bg-slate-900/90 text-slate-200 border border-slate-800 rounded-tl-sm backdrop-blur-sm"
                }`}
              >
                {/* Content */}
                <div className="prose prose-invert prose-xs max-w-none">
                  {renderMessageContentWithCitations(msg.content)}
                </div>

                {/* Stored Report Card if present */}
                {msg.reportCard && (
                  <div className="mt-3 p-3.5 rounded-xl bg-slate-950/70 border border-indigo-500/30 flex items-center justify-between">
                    <div className="flex items-center space-x-2.5">
                      <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                        <FileText className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="text-xs font-semibold text-white">{msg.reportCard.title}</h4>
                        <p className="text-[10px] text-slate-400">Compiled Intelligence Synthesis</p>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDownloadReportPdf(msg.reportCard?.id)}
                      className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-[11px] font-semibold transition-colors"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>PDF</span>
                    </button>
                  </div>
                )}
              </div>

              {msg.role === "user" && (
                <div className="w-8 h-8 rounded-xl bg-purple-600/30 border border-purple-500/40 flex items-center justify-center text-purple-300 shrink-0">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))
        )}

        {/* Live Streaming Message */}
        {streamingMessage && (
          <div className="flex items-start space-x-3 justify-start animate-in fade-in">
            <div className="w-8 h-8 rounded-xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400 shrink-0 shadow-md">
              <Bot className="w-4 h-4" />
            </div>

            <div className="max-w-2xl rounded-2xl rounded-tl-sm p-4 text-xs leading-relaxed bg-slate-900/90 text-slate-200 border border-slate-800 shadow-xl backdrop-blur-sm">
              {/* Dynamic Status Chip */}
              {statusChip && (
                <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-[11px] font-medium mb-3 animate-pulse">
                  <Loader2 className="w-3 h-3 animate-spin text-indigo-400" />
                  <span>{statusChip}</span>
                </div>
              )}

              {/* Accumulated streaming text */}
              <div className="prose prose-invert prose-xs max-w-none">
                {renderMessageContentWithCitations(streamingMessage.content)}
                {isStreaming && (
                  <span className="inline-block w-1.5 h-3.5 bg-indigo-400 ml-1 animate-pulse align-middle" />
                )}
              </div>

              {/* Streaming Report Card */}
              {streamingMessage.reportCard && (
                <div className="mt-3 p-3.5 rounded-xl bg-slate-950/70 border border-indigo-500/30 flex items-center justify-between">
                  <div className="flex items-center space-x-2.5">
                    <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                      <FileText className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="text-xs font-semibold text-white">
                        {streamingMessage.reportCard.title}
                      </h4>
                      <p className="text-[10px] text-slate-400">Executive Synthesis Ready</p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDownloadReportPdf(streamingMessage.reportCard?.id)}
                    className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-[11px] font-semibold transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>PDF</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Multimodal Composer */}
      <Composer
        onSend={handleSendMessage}
        onAbort={handleAbort}
        isStreaming={isStreaming}
      />

      {/* Modals for citations & attachments */}
      {selectedImage && (
        <ImageViewerModal
          attachmentId={selectedImage.id}
          filename={selectedImage.filename}
          onClose={() => setSelectedImage(null)}
        />
      )}

      {selectedAudio && (
        <AudioViewerModal
          attachmentId={selectedAudio.id}
          filename={selectedAudio.filename}
          initialSeekSec={selectedAudio.seekSec}
          onClose={() => setSelectedAudio(null)}
        />
      )}
    </div>
  );
};
