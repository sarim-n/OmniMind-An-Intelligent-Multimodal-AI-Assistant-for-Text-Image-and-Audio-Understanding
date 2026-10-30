import React from 'react';
import { useOutletContext } from 'react-router-dom';
import { Activity, Cpu, HardDrive, Zap, Server } from 'lucide-react';
import type { HealthResponse } from '../api';

export const Metrics: React.FC = () => {
  const { health } = useOutletContext<{ health: HealthResponse | null }>();

  const stats = [
    { label: 'Active Profile', value: health?.profile?.toUpperCase() || 'CPU', icon: Cpu, color: 'text-indigo-400' },
    { label: 'Mock Inference', value: health?.mock_models ? 'ENABLED' : 'DISABLED', icon: Zap, color: 'text-amber-400' },
    { label: 'Backend Version', value: health?.version || 'v0.1.0', icon: Server, color: 'text-emerald-400' },
    { label: 'Telemetry Table', value: 'metrics (SQLAlchemy)', icon: HardDrive, color: 'text-purple-400' },
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">System & Inference Metrics</h2>
        <p className="text-sm text-slate-400 mt-1">
          Hardware telemetry, memory tracking, and inference latency statistics recorded by backend workers.
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, i) => {
          const Icon = stat.icon;
          return (
            <div key={i} className="glass-panel rounded-2xl p-4 border border-slate-800">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">{stat.label}</span>
                <Icon className={`w-4 h-4 ${stat.color}`} />
              </div>
              <div className="mt-2 text-xl font-bold text-white font-mono">{stat.value}</div>
            </div>
          );
        })}
      </div>

      {/* Active Model Configuration Matrix */}
      <div className="glass-panel rounded-2xl border border-slate-800 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Activity className="w-5 h-5 text-indigo-400" />
            <h3 className="text-base font-semibold text-white">Active Profile Model Matrix</h3>
          </div>
          <span className="text-xs font-mono text-slate-500">Source: app.core.config.settings</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-xs uppercase font-semibold text-slate-400">
                <th className="py-3 px-4">Task</th>
                <th className="py-3 px-4">Configured Model ID</th>
                <th className="py-3 px-4">License Type</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
              {health?.models ? (
                Object.entries(health.models).map(([task, modelId]) => (
                  <tr key={task} className="hover:bg-slate-900/40">
                    <td className="py-3 px-4 font-sans font-medium text-slate-300 uppercase">{task}</td>
                    <td className="py-3 px-4 text-indigo-300">{modelId}</td>
                    <td className="py-3 px-4 text-emerald-400">Apache-2.0 / MIT</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3} className="py-6 text-center text-slate-500 font-sans">
                    Connect backend to load active model metrics
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
