import React, { useState, useRef, useEffect } from "react";
import {
  Send,
  Square,
  Image as ImageIcon,
  Mic,
  Paperclip,
  X,
  Languages,
  Play,
  Pause,
  AlertCircle,
} from "lucide-react";
import { useToast } from "../context/ToastContext";
import { formatSecondsToTime } from "../utils/citations";

const MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB
const MAX_AUDIO_SIZE_BYTES = 50 * 1024 * 1024; // 50 MB
const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const ALLOWED_AUDIO_TYPES = [
  "audio/wav",
  "audio/x-wav",
  "audio/mpeg",
  "audio/mp3",
  "audio/m4a",
  "audio/x-m4a",
  "audio/ogg",
  "audio/webm",
  "audio/flac",
];

export interface AttachedImage {
  id: string;
  file: File;
  previewUrl: string;
}

export interface AttachedAudio {
  file: File | Blob;
  name: string;
  previewUrl: string;
  durationSec?: number;
}

interface ComposerProps {
  onSend: (data: {
    content: string;
    language?: string;
    images: File[];
    audio?: File | Blob;
  }) => void;
  onAbort?: () => void;
  isStreaming: boolean;
}

const LANGUAGES = [
  { code: "", label: "Auto-detect" },
  { code: "en", label: "English" },
  { code: "hi", label: "Hindi (हिंदी)" },
  { code: "ta", label: "Tamil (தமிழ்)" },
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "ja", label: "Japanese" },
  { code: "zh", label: "Chinese" },
];

export const Composer: React.FC<ComposerProps> = ({ onSend, onAbort, isStreaming }) => {
  const { toast } = useToast();
  const [content, setContent] = useState("");
  const [language, setLanguage] = useState("");
  const [images, setImages] = useState<AttachedImage[]>([]);
  const [audio, setAudio] = useState<AttachedAudio | null>(null);

  // Mic recording states
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [micError, setMicError] = useState<string | null>(null);

  // Preview audio state
  const [isPlayingAudioPreview, setIsPlayingAudioPreview] = useState(false);
  const audioPreviewRef = useRef<HTMLAudioElement | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const audioInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [content]);

  // Clean up preview URLs on unmount
  useEffect(() => {
    return () => {
      images.forEach((img) => URL.revokeObjectURL(img.previewUrl));
      if (audio?.previewUrl) URL.revokeObjectURL(audio.previewUrl);
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    };
  }, [images, audio]);

  const validateAndAddImages = (files: FileList | File[]) => {
    const validImages: AttachedImage[] = [];
    for (const file of Array.from(files)) {
      if (!ALLOWED_IMAGE_TYPES.includes(file.type.toLowerCase())) {
        toast.error(`Invalid image type: ${file.name}. Allowed: JPG, PNG, WebP, GIF.`);
        continue;
      }
      if (file.size > MAX_IMAGE_SIZE_BYTES) {
        toast.error(`Image too large (${Math.round(file.size / (1024 * 1024))}MB). Max limit is 20MB.`);
        continue;
      }
      validImages.push({
        id: Math.random().toString(36).substring(2, 9),
        file,
        previewUrl: URL.createObjectURL(file),
      });
    }
    setImages((prev) => [...prev, ...validImages]);
  };

  const validateAndSetAudio = (file: File) => {
    if (
      !ALLOWED_AUDIO_TYPES.includes(file.type.toLowerCase()) &&
      !file.name.match(/\.(wav|mp3|m4a|ogg|webm|flac)$/i)
    ) {
      toast.error(`Unsupported audio format: ${file.name}. Allowed: WAV, MP3, M4A, OGG, WebM, FLAC.`);
      return;
    }
    if (file.size > MAX_AUDIO_SIZE_BYTES) {
      toast.error(`Audio file too large. Max limit is 50MB.`);
      return;
    }

    if (audio?.previewUrl) URL.revokeObjectURL(audio.previewUrl);

    setAudio({
      file,
      name: file.name,
      previewUrl: URL.createObjectURL(file),
    });
  };

  const handleStartRecording = async () => {
    setMicError(null);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setMicError("Microphone access is not supported in this browser.");
      toast.error("Microphone recording not supported");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const recorder = new MediaRecorder(stream);

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        if (audioBlob.size > 0) {
          const previewUrl = URL.createObjectURL(audioBlob);
          setAudio({
            file: audioBlob,
            name: `voice_recording_${new Date().toLocaleTimeString().replace(/:/g, "-")}.webm`,
            previewUrl,
            durationSec: recordingSeconds,
          });
        }
      };

      recorder.start(250);
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
      setRecordingSeconds(0);

      timerIntervalRef.current = window.setInterval(() => {
        setRecordingSeconds((s) => s + 1);
      }, 1000);
    } catch (err: unknown) {
      const errorMsg =
        err instanceof Error && err.name === "NotAllowedError"
          ? "Microphone access was denied. Please allow microphone permissions."
          : "Could not access microphone.";
      setMicError(errorMsg);
      toast.error(errorMsg);
    }
  };

  const handleStopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
    }
  };

  const handleCancelRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
      setIsRecording(false);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
      setRecordingSeconds(0);
    }
  };

  const handleRemoveImage = (id: string) => {
    setImages((prev) => {
      const target = prev.find((i) => i.id === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((i) => i.id !== id);
    });
  };

  const handleRemoveAudio = () => {
    if (audio?.previewUrl) URL.revokeObjectURL(audio.previewUrl);
    setAudio(null);
    setIsPlayingAudioPreview(false);
  };

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (isStreaming) return;

    const trimmed = content.trim();
    if (!trimmed && images.length === 0 && !audio) {
      return;
    }

    onSend({
      content: trimmed,
      language: language || undefined,
      images: images.map((i) => i.file),
      audio: audio ? audio.file : undefined,
    });

    // Reset input state
    setContent("");
    images.forEach((img) => URL.revokeObjectURL(img.previewUrl));
    setImages([]);
    if (audio?.previewUrl) URL.revokeObjectURL(audio.previewUrl);
    setAudio(null);
    setIsPlayingAudioPreview(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndAddImages(e.dataTransfer.files);
    }
  };

  return (
    <div
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
      className="p-3 sm:p-4 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-2xl backdrop-blur-md transition-all"
    >
      {/* Mic Permission Warning */}
      {micError && (
        <div className="mb-3 p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{micError}</span>
          </div>
          <button onClick={() => setMicError(null)} className="text-rose-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Previews Bar: Images & Audio */}
      {(images.length > 0 || audio) && (
        <div className="flex flex-wrap gap-2.5 mb-3 pb-3 border-b border-slate-800/80">
          {/* Image Previews */}
          {images.map((img) => (
            <div
              key={img.id}
              className="relative group w-16 h-16 rounded-xl overflow-hidden border border-slate-700 bg-slate-950 shadow-md"
            >
              <img
                src={img.previewUrl}
                alt="Upload preview"
                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
              />
              <button
                type="button"
                onClick={() => handleRemoveImage(img.id)}
                className="absolute top-1 right-1 p-1 rounded-full bg-slate-950/80 hover:bg-rose-600 text-slate-300 hover:text-white transition-colors"
                title="Remove image"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}

          {/* Audio Preview Card */}
          {audio && (
            <div className="flex items-center space-x-2 px-3 py-2 rounded-xl bg-slate-800/80 border border-slate-700 text-xs text-slate-200">
              <audio
                ref={audioPreviewRef}
                src={audio.previewUrl}
                onEnded={() => setIsPlayingAudioPreview(false)}
              />
              <button
                type="button"
                onClick={() => {
                  if (!audioPreviewRef.current) return;
                  if (isPlayingAudioPreview) {
                    audioPreviewRef.current.pause();
                    setIsPlayingAudioPreview(false);
                  } else {
                    audioPreviewRef.current.play();
                    setIsPlayingAudioPreview(true);
                  }
                }}
                className="p-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
              >
                {isPlayingAudioPreview ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 ml-0.5" />}
              </button>
              <span className="font-medium max-w-[140px] truncate">{audio.name}</span>
              <button
                type="button"
                onClick={handleRemoveAudio}
                className="text-slate-400 hover:text-rose-400 p-1 transition-colors"
                title="Remove audio"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Recording in progress overlay */}
      {isRecording ? (
        <div className="flex items-center justify-between p-3 rounded-2xl bg-rose-950/20 border border-rose-500/30 text-rose-300 mb-2 animate-pulse">
          <div className="flex items-center space-x-2.5">
            <span className="w-3 h-3 rounded-full bg-rose-500 animate-ping" />
            <span className="text-xs font-semibold uppercase tracking-wider">Recording Speech...</span>
            <span className="font-mono text-xs px-2 py-0.5 rounded bg-rose-500/20 text-white font-bold">
              {formatSecondsToTime(recordingSeconds)}
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={handleCancelRecording}
              className="px-2.5 py-1 text-xs text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleStopRecording}
              className="px-3 py-1 bg-rose-600 hover:bg-rose-500 text-white text-xs font-medium rounded-xl transition-colors shadow-lg shadow-rose-600/20"
            >
              Done & Attach
            </button>
          </div>
        </div>
      ) : (
        /* Text Input Area */
        <div className="relative">
          <textarea
            ref={textareaRef}
            rows={1}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything, attach visual evidence, or record speech... (Enter to send, Shift+Enter for newline)"
            className="w-full bg-transparent text-sm text-slate-100 placeholder-slate-500 resize-none focus:outline-none pr-4 max-h-44 leading-relaxed"
          />
        </div>
      )}

      {/* Footer Controls & Buttons */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800/80 mt-2">
        <div className="flex items-center space-x-1">
          {/* Hidden file inputs */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files) validateAndAddImages(e.target.files);
              e.target.value = "";
            }}
          />
          <input
            ref={audioInputRef}
            type="file"
            accept="audio/*"
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.[0]) validateAndSetAudio(e.target.files[0]);
              e.target.value = "";
            }}
          />

          {/* Add Image Button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="p-2 text-slate-400 hover:text-indigo-400 hover:bg-slate-800 rounded-xl transition-colors"
            title="Attach images (drag & drop supported)"
            aria-label="Attach images"
          >
            <ImageIcon className="w-4 h-4" />
          </button>

          {/* Add Audio Button */}
          <button
            type="button"
            onClick={() => audioInputRef.current?.click()}
            className="p-2 text-slate-400 hover:text-indigo-400 hover:bg-slate-800 rounded-xl transition-colors"
            title="Upload audio file (WAV, MP3, M4A)"
            aria-label="Upload audio"
          >
            <Paperclip className="w-4 h-4" />
          </button>

          {/* Record Microphone Button */}
          <button
            type="button"
            onClick={isRecording ? handleStopRecording : handleStartRecording}
            className={`p-2 rounded-xl transition-colors ${
              isRecording
                ? "bg-rose-600 text-white"
                : "text-slate-400 hover:text-rose-400 hover:bg-slate-800"
            }`}
            title="Record speech from microphone"
            aria-label="Record speech from microphone"
          >
            <Mic className="w-4 h-4" />
          </button>

          {/* Language Selector Dropdown */}
          <div className="flex items-center space-x-1 pl-2 ml-1 border-l border-slate-800 text-xs text-slate-400">
            <Languages className="w-3.5 h-3.5 text-slate-500" />
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="bg-transparent text-xs text-slate-300 focus:outline-none cursor-pointer py-1"
              aria-label="Language selector"
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code} className="bg-slate-900 text-slate-200">
                  {lang.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Send / Abort Buttons */}
        <div className="flex items-center space-x-2">
          {isStreaming ? (
            <button
              type="button"
              onClick={onAbort}
              className="flex items-center space-x-1.5 px-3.5 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-xl transition-colors shadow-lg shadow-rose-600/20"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
              <span>Stop</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={() => handleSubmit()}
              disabled={!content.trim() && images.length === 0 && !audio}
              className="flex items-center space-x-1.5 px-4 py-1.5 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white text-xs font-semibold rounded-xl shadow-lg shadow-indigo-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              <span>Send</span>
              <Send className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
