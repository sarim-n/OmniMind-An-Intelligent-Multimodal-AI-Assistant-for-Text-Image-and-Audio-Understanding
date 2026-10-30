import React, { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Send, Image, Mic, Paperclip, Bot, User, Sparkles } from 'lucide-react';
import type { HealthResponse } from '../api';

export const Chat: React.FC = () => {
  const { health } = useOutletContext<{ health: HealthResponse | null }>();
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; text: string }>>([
    {
      role: 'assistant',
      text: 'Hello! I am your Multimodal AI Assistant. You can send text, attach images for vision analysis, or upload audio files for speech transcription.',
    },
  ]);
  const [input, setInput] = useState('');

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMsg = input.trim();
    setInput('');
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: userMsg },
      {
        role: 'assistant',
        text: `[Placeholder] Received "${userMsg}". Inference execution will be connected in subsequent phases. (Profile: ${health?.profile || 'cpu'})`,
      },
    ]);
  };

  return (
    <div className="max-w-4xl mx-auto flex flex-col h-[calc(100vh-10rem)]">
      {/* Profile info header */}
      <div className="glass-panel rounded-xl px-4 py-2.5 mb-4 flex items-center justify-between text-xs text-slate-400">
        <div className="flex items-center space-x-2">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
          <span>Multimodal Inference Engine:</span>
          <span className="font-mono text-indigo-300 font-semibold uppercase">
            {health?.profile || 'cpu'}
          </span>
        </div>
        <div className="font-mono text-slate-500">
          VLM: {health?.models?.vlm || 'SmolVLM'} &bull; LLM: {health?.models?.llm || 'Qwen2.5-1.5B'}
        </div>
      </div>

      {/* Messages viewport */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex items-start space-x-3 ${
              msg.role === 'user' ? 'justify-end' : 'justify-start'
            }`}
          >
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-400 shrink-0">
                <Bot className="w-4 h-4" />
              </div>
            )}
            <div
              className={`max-w-xl rounded-2xl px-4 py-3 text-sm ${
                msg.role === 'user'
                  ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-br-none shadow-md'
                  : 'glass-panel text-slate-200 rounded-bl-none'
              }`}
            >
              <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>
            </div>
            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-lg bg-purple-600/30 border border-purple-500/40 flex items-center justify-center text-purple-300 shrink-0">
                <User className="w-4 h-4" />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Chat Input Bar */}
      <form onSubmit={handleSend} className="mt-4">
        <div className="glass-panel rounded-2xl p-2 flex items-center space-x-2 border border-slate-800">
          <button
            type="button"
            className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded-xl transition"
            title="Attach Image"
          >
            <Image className="w-5 h-5" />
          </button>
          <button
            type="button"
            className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded-xl transition"
            title="Record Audio"
          >
            <Mic className="w-5 h-5" />
          </button>
          <button
            type="button"
            className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded-xl transition"
            title="Attach Document"
          >
            <Paperclip className="w-5 h-5" />
          </button>

          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a multimodal prompt or question..."
            className="flex-1 bg-transparent border-none text-sm text-white placeholder-slate-500 focus:outline-none px-2"
          />

          <button
            type="submit"
            className="bg-indigo-600 hover:bg-indigo-500 text-white p-2.5 rounded-xl transition shadow-lg shadow-indigo-600/30"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </form>
    </div>
  );
};
