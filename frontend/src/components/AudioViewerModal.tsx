import React, { useEffect, useRef, useState } from "react";
import {
  X,
  Play,
  Pause,
  Volume2,
  VolumeX,
  RotateCcw,
  Languages,
  Clock,
  Sparkles,
  FileText,
  Loader2,
  Headphones,
} from "lucide-react";
import { apiClient } from "../api/client";
import { formatSecondsToTime } from "../utils/citations";
import { InsightsPanel } from "./InsightsPanel";

export interface TranscriptSegment {
  id?: number | string;
  start: number;
  end: number;
  text: string;
}

export interface TranscriptData {
  attachment_id: string;
  text: string;
  language?: string;
  duration?: number;
  segments?: TranscriptSegment[];
}

interface AudioViewerModalProps {
  attachmentId: string;
  filename?: string;
  initialSeekSec?: number;
  onClose: () => void;
}

export const AudioViewerModal: React.FC<AudioViewerModalProps> = ({
  attachmentId,
  filename,
  initialSeekSec = 0,
  onClose,
}) => {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptData | null>(null);
  const [loadingAudio, setLoadingAudio] = useState(true);
  const [loadingTranscript, setLoadingTranscript] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(initialSeekSec);
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [activeTab, setActiveTab] = useState<"transcript" | "insights">("transcript");

  // Load audio file as authenticated blob URL
  useEffect(() => {
    let active = true;
    let blobUrl: string | null = null;
    setLoadingAudio(true);

    apiClient
      .fetchBlobUrl(`/audio/${attachmentId}/file`)
      .then((url) => {
        if (!active) {
          URL.revokeObjectURL(url);
          return;
        }
        blobUrl = url;
        setAudioUrl(url);
      })
      .catch((err) => {
        console.error("Failed to load audio blob:", err);
      })
      .finally(() => {
        if (active) setLoadingAudio(false);
      });

    // Load transcript
    setLoadingTranscript(true);
    apiClient
      .get<TranscriptData>(`/audio/${attachmentId}/transcript`)
      .then((data) => {
        if (active) {
          setTranscript(data);
          if (data.duration && !duration) setDuration(data.duration);
        }
      })
      .catch((err) => {
        console.warn("No transcript found yet:", err);
      })
      .finally(() => {
        if (active) setLoadingTranscript(false);
      });

    return () => {
      active = false;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [attachmentId, duration]);

  // Initial seek once audio metadata is loaded
  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration);
      if (initialSeekSec > 0) {
        audioRef.current.currentTime = initialSeekSec;
        setCurrentTime(initialSeekSec);
      }
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play();
      setIsPlaying(true);
    }
  };

  const handleSeek = (seconds: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = seconds;
      setCurrentTime(seconds);
    }
  };

  // Find active segment
  const activeSegmentIndex = transcript?.segments?.findIndex(
    (seg) => currentTime >= seg.start && currentTime <= seg.end
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Audio player and inspector"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
    >
      <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-4xl h-[88vh] flex flex-col overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <Headphones className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white">
                {filename || "Acoustic Player & Synced Transcript"}
              </h2>
              <div className="flex items-center space-x-2 text-xs text-slate-400 mt-0.5">
                <span className="font-mono">ID: {attachmentId}</span>
                {transcript?.language && (
                  <span className="inline-flex items-center space-x-1 px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 font-mono uppercase text-[10px] border border-indigo-500/30">
                    <Languages className="w-3 h-3" />
                    <span>{transcript.language}</span>
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            {/* View Tabs */}
            <div className="flex items-center bg-slate-800/80 rounded-xl p-1 border border-slate-700">
              <button
                onClick={() => setActiveTab("transcript")}
                className={`flex items-center space-x-1 px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  activeTab === "transcript"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                <FileText className="w-3.5 h-3.5" />
                <span>Transcript</span>
              </button>
              <button
                onClick={() => setActiveTab("insights")}
                className={`flex items-center space-x-1 px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  activeTab === "insights"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Insights</span>
              </button>
            </div>

            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-xl transition-colors"
              aria-label="Close audio player"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Persistent Audio Player Bar */}
        <div className="px-6 py-4 bg-slate-950/70 border-b border-slate-800/80 flex flex-col space-y-2">
          {audioUrl && (
            <audio
              ref={audioRef}
              src={audioUrl}
              onLoadedMetadata={handleLoadedMetadata}
              onTimeUpdate={handleTimeUpdate}
              onEnded={() => setIsPlaying(false)}
            />
          )}

          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <button
                onClick={togglePlay}
                disabled={loadingAudio || !audioUrl}
                className="w-10 h-10 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center shadow-lg shadow-indigo-600/20 disabled:opacity-50 transition-colors"
                aria-label={isPlaying ? "Pause audio" : "Play audio"}
              >
                {loadingAudio ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : isPlaying ? (
                  <Pause className="w-4 h-4" />
                ) : (
                  <Play className="w-4 h-4 ml-0.5" />
                )}
              </button>

              <button
                onClick={() => handleSeek(0)}
                className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
                title="Restart playback"
                aria-label="Restart playback"
              >
                <RotateCcw className="w-4 h-4" />
              </button>

              <div className="text-xs font-mono text-slate-300">
                <span>{formatSecondsToTime(currentTime)}</span>
                <span className="text-slate-600 mx-1">/</span>
                <span className="text-slate-400">{formatSecondsToTime(duration)}</span>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={() => {
                  if (audioRef.current) {
                    audioRef.current.muted = !isMuted;
                    setIsMuted(!isMuted);
                  }
                }}
                className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
              >
                {isMuted ? <VolumeX className="w-4 h-4 text-rose-400" /> : <Volume2 className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Scrubber Progress Bar */}
          <div className="flex items-center space-x-2">
            <input
              type="range"
              min={0}
              max={duration || 100}
              step={0.1}
              value={currentTime}
              onChange={(e) => handleSeek(Number(e.target.value))}
              className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
          </div>
        </div>

        {/* Tab Content Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === "transcript" ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Synchronized Utterance Transcript
                </span>
                <span className="text-xs text-slate-500">
                  Click any segment to jump playback
                </span>
              </div>

              {loadingTranscript ? (
                <div className="p-8 flex flex-col items-center justify-center space-y-2 text-slate-500 text-xs">
                  <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
                  <span>Loading transcript segments...</span>
                </div>
              ) : transcript?.segments && transcript.segments.length > 0 ? (
                <div className="space-y-2">
                  {transcript.segments.map((seg, idx) => {
                    const isActive = idx === activeSegmentIndex;
                    return (
                      <div
                        key={idx}
                        onClick={() => handleSeek(seg.start)}
                        className={`p-3.5 rounded-2xl border text-xs cursor-pointer transition-all duration-200 flex items-start space-x-3 ${
                          isActive
                            ? "bg-indigo-600/20 border-indigo-500/50 text-indigo-100 shadow-md shadow-indigo-950/40"
                            : "bg-slate-900/40 border-slate-800/80 text-slate-300 hover:bg-slate-800/40 hover:border-slate-700"
                        }`}
                      >
                        <button
                          type="button"
                          className="flex items-center space-x-1 font-mono text-[11px] text-slate-400 px-2 py-0.5 rounded bg-slate-800/80 border border-slate-700/60 shrink-0 mt-0.5"
                        >
                          <Clock className="w-3 h-3 text-slate-500" />
                          <span>{formatSecondsToTime(seg.start)}</span>
                        </button>
                        <p className="leading-relaxed flex-1">{seg.text}</p>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="p-8 text-center text-xs text-slate-500">
                  {transcript?.text || "No spoken segments found in this recording."}
                </div>
              )}
            </div>
          ) : (
            <InsightsPanel attachmentId={attachmentId} onSeekAudio={handleSeek} />
          )}
        </div>
      </div>
    </div>
  );
};
