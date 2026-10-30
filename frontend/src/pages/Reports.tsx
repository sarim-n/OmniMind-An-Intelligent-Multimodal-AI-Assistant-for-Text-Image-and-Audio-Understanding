import React from 'react';
import { FileText, Download, Clock, Plus, CheckCircle2 } from 'lucide-react';

export const Reports: React.FC = () => {
  const sampleReports = [
    {
      id: 'rep-001',
      title: 'Multimodal Audio & Image Synthesis Report',
      date: '2026-10-30',
      size: '1.2 MB',
      status: 'Generated',
      type: 'PDF',
    },
    {
      id: 'rep-002',
      title: 'RT-DETR Object Detection & Bounding Box Summary',
      date: '2026-10-29',
      size: '840 KB',
      status: 'Generated',
      type: 'PDF',
    },
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">PDF Reports & Exports</h2>
          <p className="text-sm text-slate-400 mt-1">
            Generate and export automated multimodal inspection reports using ReportLab.
          </p>
        </div>

        <button
          onClick={() => alert('Report generation will be implemented in subsequent phases.')}
          className="flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2.5 rounded-xl font-medium text-sm transition shadow-lg shadow-indigo-600/30"
        >
          <Plus className="w-4 h-4" />
          <span>New Report</span>
        </button>
      </div>

      {/* Reports Table Card */}
      <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-800/80 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Recent Reports
          </span>
          <span className="text-xs text-slate-500 font-mono">Location: /storage/reports</span>
        </div>

        <div className="divide-y divide-slate-800/60">
          {sampleReports.map((report) => (
            <div
              key={report.id}
              className="px-6 py-4 flex items-center justify-between hover:bg-slate-900/40 transition"
            >
              <div className="flex items-center space-x-3.5">
                <div className="w-10 h-10 rounded-xl bg-purple-600/20 text-purple-400 flex items-center justify-center border border-purple-500/30">
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-white">{report.title}</h4>
                  <div className="flex items-center space-x-3 text-xs text-slate-400 mt-0.5">
                    <span className="flex items-center space-x-1">
                      <Clock className="w-3 h-3" />
                      <span>{report.date}</span>
                    </span>
                    <span>&bull;</span>
                    <span>{report.size}</span>
                    <span>&bull;</span>
                    <span className="flex items-center space-x-1 text-emerald-400">
                      <CheckCircle2 className="w-3 h-3" />
                      <span>{report.status}</span>
                    </span>
                  </div>
                </div>
              </div>

              <button
                className="flex items-center space-x-1.5 text-xs text-indigo-400 hover:text-indigo-300 font-medium px-3 py-1.5 rounded-lg border border-indigo-500/30 hover:bg-indigo-500/10 transition"
                onClick={() => alert(`Downloading ${report.title}`)}
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download</span>
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
