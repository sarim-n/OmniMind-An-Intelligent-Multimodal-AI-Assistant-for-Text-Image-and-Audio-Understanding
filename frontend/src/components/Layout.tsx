import React, { useState } from "react";
import { Outlet, Navigate, useLocation } from "react-router-dom";
import { Menu, Sparkles } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { MockBanner } from "./MockBanner";
import { useAuth } from "../context/AuthContext";

export const Layout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  // If loading auth state, show minimalist loading splash
  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center space-y-4">
        <div className="h-12 w-12 rounded-2xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-indigo-500/25 animate-pulse">
          <Sparkles className="w-6 h-6 text-white" />
        </div>
        <p className="text-xs font-mono text-slate-400">Initializing OmniMind Session...</p>
      </div>
    );
  }

  // Public auth pages (login / register) don't require sidebar
  const isAuthPage = location.pathname === "/login" || location.pathname === "/register";

  if (!isAuthenticated && !isAuthPage) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (isAuthPage) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
        <MockBanner />
        <main className="flex-1 flex items-center justify-center p-4">
          <Outlet />
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans antialiased overflow-hidden">
      {/* Informational Mock Models Banner */}
      <MockBanner />

      <div className="flex-1 flex overflow-hidden">
        {/* Responsive Collapsible Sidebar */}
        <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-slate-900/30">
          {/* Mobile Top Navbar with Hamburger */}
          <header className="md:hidden flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="Open sidebar"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="flex items-center space-x-2">
              <div className="h-7 w-7 rounded-lg bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center">
                <Sparkles className="w-3.5 h-3.5 text-white" />
              </div>
              <span className="text-sm font-bold text-white">OmniMind</span>
            </div>
            <div className="w-6" /> {/* Placeholder for symmetry */}
          </header>

          <main className="flex-1 overflow-y-auto">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
};
