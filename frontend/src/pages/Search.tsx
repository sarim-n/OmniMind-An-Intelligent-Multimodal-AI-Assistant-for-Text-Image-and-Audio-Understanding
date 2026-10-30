import React, { useState } from 'react';
import { Search as SearchIcon, Filter, Database } from 'lucide-react';

export const Search: React.FC = () => {
  const [query, setQuery] = useState('');
  const [similarityThreshold, setSimilarityThreshold] = useState(0.7);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">Multimodal Vector Search</h2>
        <p className="text-sm text-slate-400 mt-1">
          Perform cross-modal semantic similarity queries over text embeddings (BGE) and image embeddings (SigLIP) indexed in ChromaDB.
        </p>
      </div>

      {/* Search Input Bar */}
      <div className="glass-panel rounded-2xl p-4 border border-slate-800 space-y-4">
        <div className="relative">
          <SearchIcon className="w-5 h-5 text-slate-400 absolute left-4 top-3.5" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search across documents, audio transcripts, and image descriptions..."
            className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl py-3 pl-12 pr-4 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          />
        </div>

        {/* Filter controls */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-slate-800/80 text-xs text-slate-400">
          <div className="flex items-center space-x-4">
            <span className="flex items-center space-x-1.5 font-medium text-slate-300">
              <Filter className="w-3.5 h-3.5 text-indigo-400" />
              <span>Modality:</span>
            </span>
            <label className="flex items-center space-x-1.5 cursor-pointer">
              <input type="checkbox" defaultChecked className="rounded bg-slate-800 border-slate-700 text-indigo-600 focus:ring-0" />
              <span>Text</span>
            </label>
            <label className="flex items-center space-x-1.5 cursor-pointer">
              <input type="checkbox" defaultChecked className="rounded bg-slate-800 border-slate-700 text-indigo-600 focus:ring-0" />
              <span>Images</span>
            </label>
            <label className="flex items-center space-x-1.5 cursor-pointer">
              <input type="checkbox" defaultChecked className="rounded bg-slate-800 border-slate-700 text-indigo-600 focus:ring-0" />
              <span>Audio</span>
            </label>
          </div>

          <div className="flex items-center space-x-3">
            <span>Threshold: {similarityThreshold.toFixed(2)}</span>
            <input
              type="range"
              min="0.1"
              max="0.99"
              step="0.05"
              value={similarityThreshold}
              onChange={(e) => setSimilarityThreshold(parseFloat(e.target.value))}
              className="w-28 accent-indigo-500 cursor-pointer"
            />
          </div>
        </div>
      </div>

      {/* Placeholder Results View */}
      <div className="glass-panel rounded-2xl p-8 border border-slate-800 text-center space-y-3">
        <div className="w-12 h-12 bg-indigo-600/20 text-indigo-400 rounded-xl flex items-center justify-center mx-auto border border-indigo-500/30">
          <Database className="w-6 h-6" />
        </div>
        <h3 className="text-base font-semibold text-white">ChromaDB Index Ready for Queries</h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto">
          Semantic search results across text and SigLIP image embeddings will be populated once documents and images are ingested in the storage pipeline.
        </p>
      </div>
    </div>
  );
};
