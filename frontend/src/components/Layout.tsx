import React, { useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  MessageSquare,
  Search,
  FileText,
  Activity,
  LogIn,
  CheckCircle2,
  AlertCircle,
  Sparkles,
} from 'lucide-react';
import { checkHealth, API_BASE_URL, type HealthResponse } from '../api';

export const Layout: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    checkHealth()
      .then((data) => {
        setHealth(data);
        setError(null);
      })
      .catch((err) => {
        setError(err.message);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const navItems = [
    { to: '/chat', label: 'Chat', icon: MessageSquare },
    { to: '/search', label: 'Search', icon: Search },
    { to: '/reports', label: 'Reports', icon: FileText },
    { to: '/metrics', label: 'Metrics', icon: Activity },
    { to: '/login', label: 'Login', icon: LogIn },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Navbar */}
      <header className="sticky top-0 z-50 glass-panel border-b border-slate-800/80 px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-indigo-500/25">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
                Multimodal AI Assistant
              </h1>
              <p className="text-xs text-slate-400">Edge & Hybrid Vision-Language Monorepo</p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="hidden md:flex items-center space-x-1 bg-slate-900/60 p-1 rounded-xl border border-slate-800">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                      isActive
                        ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                    }`
                  }
                >
                  <Icon className="w-4 h-4" />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>

          {/* Backend Status Badge */}
          <div className="flex items-center space-x-3">
            <div
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-full text-xs font-medium border ${
                loading
                  ? 'bg-amber-950/40 border-amber-800/50 text-amber-300'
                  : health
                  ? 'bg-emerald-950/40 border-emerald-800/50 text-emerald-300'
                  : 'bg-rose-950/40 border-rose-800/50 text-rose-300'
              }`}
              title={`API URL: ${API_BASE_URL}`}
            >
              {loading ? (
                <>
                  <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                  <span>Connecting...</span>
                </>
              ) : health ? (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  <span>API OK ({health.profile})</span>
                  {health.mock_models && (
                    <span className="ml-1 px-1.5 py-0.2 bg-emerald-500/20 text-[10px] rounded text-emerald-200">
                      MOCK
                    </span>
                  )}
                </>
              ) : (
                <>
                  <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
                  <span>API Offline</span>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Viewport */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6">
        <Outlet context={{ health, error, loading }} />
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 px-6 py-4 text-center text-xs text-slate-500">
        Intelligent Multimodal AI Assistant &bull; Profile: {health?.profile || 'cpu'} &bull; API:{' '}
        <span className="font-mono text-slate-400">{API_BASE_URL}</span>
      </footer>
    </div>
  );
};
