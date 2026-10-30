import React, { useState } from "react";
import { NavLink, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  MessageSquare,
  Search,
  FileText,
  Activity,
  Trash2,
  Edit2,
  Check,
  X,
  Sun,
  Moon,
  LogOut,
  Sparkles,
  AlertTriangle,
} from "lucide-react";
import { apiClient } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useToast } from "../context/ToastContext";
import { ConversationListSkeleton } from "./Skeleton";

export interface ConversationItem {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

interface ConversationListResponse {
  items: ConversationItem[];
  total: number;
}

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const activeConversationId = searchParams.get("conversation_id");

  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { toast } = useToast();

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Fetch conversations
  const { data, isLoading } = useQuery<ConversationListResponse>({
    queryKey: ["conversations"],
    queryFn: () => apiClient.get<ConversationListResponse>("/conversations", { page_size: 50 }),
  });

  // Create conversation
  const createMutation = useMutation({
    mutationFn: () => apiClient.post<ConversationItem>("/conversations", { title: "New Conversation" }),
    onSuccess: (newConv) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      navigate(`/chat?conversation_id=${newConv.id}`);
      onClose();
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to create conversation";
      toast.error(msg);
    },
  });

  // Rename conversation
  const renameMutation = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      apiClient.patch<ConversationItem>(`/conversations/${id}`, { title }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      setEditingId(null);
      toast.success("Conversation renamed");
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to rename";
      toast.error(msg);
    },
  });

  // Delete conversation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/conversations/${id}`),
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      setDeletingId(null);
      toast.success("Conversation deleted");
      if (activeConversationId === deletedId) {
        navigate("/chat");
      }
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to delete conversation";
      toast.error(msg);
    },
  });

  const handleStartRename = (conv: ConversationItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(conv.id);
    setEditTitle(conv.title);
  };

  const handleSaveRename = (id: string, e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!editTitle.trim()) return;
    renameMutation.mutate({ id, title: editTitle.trim() });
  };

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm z-40 md:hidden animate-in fade-in"
        />
      )}

      {/* Delete confirmation modal */}
      {deletingId && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in"
        >
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 max-w-sm w-full shadow-2xl space-y-4">
            <div className="w-10 h-10 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">Delete Conversation?</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                This will permanently delete this conversation, disk attachments, and memory vectors. This action cannot be undone.
              </p>
            </div>
            <div className="flex items-center justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setDeletingId(null)}
                className="px-3 py-1.5 rounded-xl text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => deleteMutation.mutate(deletingId)}
                className="px-4 py-1.5 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white transition-colors shadow-lg shadow-rose-600/20"
              >
                Delete Permanently
              </button>
            </div>
          </div>
        </div>
      )}

      <aside
        className={`fixed md:static inset-y-0 left-0 z-40 w-72 flex flex-col bg-slate-950/95 dark:bg-slate-950/95 border-r border-slate-800/80 transition-transform duration-300 ease-in-out md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Top Branding & New Chat */}
        <div className="p-4 border-b border-slate-800/80 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center shadow-md shadow-indigo-500/25">
                <Sparkles className="w-4 h-4 text-white" />
              </div>
              <div>
                <h1 className="text-sm font-bold text-white tracking-tight">OmniMind</h1>
                <p className="text-[10px] text-slate-400 font-mono">Multimodal Assistant</p>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white rounded-lg md:hidden"
              aria-label="Close sidebar"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <button
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending}
            className="w-full flex items-center justify-center space-x-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition-all disabled:opacity-50"
          >
            <Plus className="w-4 h-4" />
            <span>New Conversation</span>
          </button>
        </div>

        {/* Conversations History List */}
        <div className="flex-1 overflow-y-auto px-2 py-3 space-y-1">
          <div className="px-3 pb-1 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            Conversations
          </div>

          {isLoading ? (
            <ConversationListSkeleton />
          ) : data?.items && data.items.length > 0 ? (
            data.items.map((conv) => {
              const isActive = activeConversationId === conv.id;
              const isEditing = editingId === conv.id;

              return (
                <div
                  key={conv.id}
                  onClick={() => {
                    if (!isEditing) {
                      navigate(`/chat?conversation_id=${conv.id}`);
                      onClose();
                    }
                  }}
                  className={`group relative flex items-center justify-between px-3 py-2 rounded-xl text-xs cursor-pointer transition-colors ${
                    isActive
                      ? "bg-indigo-600/20 text-indigo-200 border border-indigo-500/30"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent"
                  }`}
                >
                  <div className="flex items-center space-x-2.5 min-w-0 flex-1">
                    <MessageSquare className={`w-3.5 h-3.5 shrink-0 ${isActive ? "text-indigo-400" : "text-slate-500"}`} />
                    {isEditing ? (
                      <form
                        onSubmit={(e) => handleSaveRename(conv.id, e)}
                        onClick={(e) => e.stopPropagation()}
                        className="flex items-center space-x-1 flex-1"
                      >
                        <input
                          type="text"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          autoFocus
                          className="w-full bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                        />
                        <button
                          type="submit"
                          className="p-1 text-emerald-400 hover:text-emerald-300"
                          title="Save title"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="p-1 text-slate-400 hover:text-slate-300"
                          title="Cancel"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </form>
                    ) : (
                      <span className="truncate font-medium">{conv.title}</span>
                    )}
                  </div>

                  {!isEditing && (
                    <div className="hidden group-hover:flex items-center space-x-1 pl-1">
                      <button
                        onClick={(e) => handleStartRename(conv, e)}
                        className="p-1 hover:text-white text-slate-500 hover:bg-slate-800 rounded transition-colors"
                        title="Rename conversation"
                      >
                        <Edit2 className="w-3 h-3" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeletingId(conv.id);
                        }}
                        className="p-1 hover:text-rose-400 text-slate-500 hover:bg-slate-800 rounded transition-colors"
                        title="Delete conversation"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <div className="p-4 text-center text-xs text-slate-600">
              No conversations yet. Click "New Conversation" above.
            </div>
          )}
        </div>

        {/* Global Navigation Links */}
        <div className="p-2 border-t border-slate-800/80 space-y-1">
          <NavLink
            to="/search"
            onClick={onClose}
            className={({ isActive }) =>
              `flex items-center space-x-2.5 px-3 py-2 rounded-xl text-xs font-medium transition-colors ${
                isActive
                  ? "bg-slate-800/80 text-white"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
              }`
            }
          >
            <Search className="w-4 h-4 text-sky-400" />
            <span>Knowledge Vault</span>
          </NavLink>

          <NavLink
            to="/reports"
            onClick={onClose}
            className={({ isActive }) =>
              `flex items-center space-x-2.5 px-3 py-2 rounded-xl text-xs font-medium transition-colors ${
                isActive
                  ? "bg-slate-800/80 text-white"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
              }`
            }
          >
            <FileText className="w-4 h-4 text-amber-400" />
            <span>Structured Reports</span>
          </NavLink>

          <NavLink
            to="/metrics"
            onClick={onClose}
            className={({ isActive }) =>
              `flex items-center space-x-2.5 px-3 py-2 rounded-xl text-xs font-medium transition-colors ${
                isActive
                  ? "bg-slate-800/80 text-white"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
              }`
            }
          >
            <Activity className="w-4 h-4 text-emerald-400" />
            <span>Telemetry & Metrics</span>
          </NavLink>
        </div>

        {/* Footer: User Profile, Theme & Logout */}
        <div className="p-3 border-t border-slate-800/80 bg-slate-950/40 flex items-center justify-between">
          <div className="min-w-0 pr-2">
            <p className="text-xs font-semibold text-slate-200 truncate">{user?.email || "User"}</p>
            <p className="text-[10px] text-slate-500 font-mono">Authenticated</p>
          </div>

          <div className="flex items-center space-x-1">
            <button
              onClick={toggleTheme}
              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            >
              {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            <button
              onClick={logout}
              className="p-1.5 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-800 transition-colors"
              title="Sign out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
};
