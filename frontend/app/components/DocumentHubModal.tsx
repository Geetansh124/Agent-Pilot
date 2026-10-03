"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  X,
  Upload,
  Cloud,
  FileText,
  Trash2,
  Download,
  Paperclip,
  CheckCircle2,
  Loader2,
  Search,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { StoredDocument, getApiBaseUrl } from "./types";

interface DocumentHubModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeThreadId: string;
  activeDocumentId?: string;
  onDocumentAttached: (doc: StoredDocument) => void;
}

export default function DocumentHubModal({
  isOpen,
  onClose,
  activeThreadId,
  activeDocumentId,
  onDocumentAttached,
}: DocumentHubModalProps) {
  const { authFetch, isAuthenticated } = useAuth();
  const API = getApiBaseUrl();
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploadStage, setUploadStage] = useState<number>(0); // 0=idle, 1=uploading, 2=syncing, 3=indexing
  const [pendingFile, setPendingFile] = useState<{ name: string; size: number } | null>(null);
  const [attachingId, setAttachingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploading = uploadStage > 0 || pendingFile !== null;

  const UPLOAD_STAGES: Record<number, string> = {
    1: "Uploading payload to server…",
    2: "Syncing with cloud storage…",
    3: "Indexing vector embeddings for RAG…",
  };

  useEffect(() => {
    if (isOpen) {
      loadDocuments();
    }
  }, [isOpen]);

  const loadDocuments = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API}/api/documents`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || []);
      } else {
        setDocuments([]);
      }
    } catch (err) {
      console.warn("Fetch documents error:", err);
      setDocuments([]);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    setPendingFile({ name: file.name, size: file.size });
    setUploadStage(1);
    setError(null);
    const formData = new FormData();
    formData.append("file", file);
    if (activeThreadId) {
      formData.append("thread_id", activeThreadId);
    }

    const stageTimer2 = setTimeout(() => setUploadStage(2), 1500);
    const stageTimer3 = setTimeout(() => setUploadStage(3), 4000);

    try {
      const res = await authFetch(`${API}/api/documents/upload`, {
        method: "POST",
        body: formData,
      });

      clearTimeout(stageTimer2);
      clearTimeout(stageTimer3);

      if (res.ok) {
        const newDoc = await res.json();
        await loadDocuments();
        if (activeThreadId) {
          onDocumentAttached(newDoc);
        }
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || `Upload failed (HTTP ${res.status}). Please retry.`);
      }
    } catch (err) {
      clearTimeout(stageTimer2);
      clearTimeout(stageTimer3);
      console.error("Document upload error:", err);
      setError("Backend server is currently unreachable. If hosted on a free cloud tier, it may be waking up. Please retry in a few moments.");
    } finally {
      setPendingFile(null);
      setUploadStage(0);
    }
  };

  const handleAttach = async (doc: StoredDocument) => {
    if (!activeThreadId) return;
    setAttachingId(doc.id);
    setError(null);

    try {
      const res = await authFetch(`${API}/api/threads/${activeThreadId}/documents/${doc.id}/attach`, {
        method: "POST",
      });

      if (res.ok) {
        const attachData = await res.json().catch(() => ({}));
        const resolvedDoc: StoredDocument = {
          ...doc,
          chunks_count: attachData.chunks_count || doc.chunks_count || 0,
          chunks: attachData.chunks || attachData.chunks_count || doc.chunks || 0,
        };
        onDocumentAttached(resolvedDoc);
        onClose();
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || "Failed to attach document to thread.");
      }
    } catch (err) {
      console.warn("Document attach error:", err);
      setError("Network error attaching document. If the backend server is waking up, please retry in a few moments.");
    } finally {
      setAttachingId(null);
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm("Are you sure you want to permanently delete this document?")) return;
    setDeletingId(docId);
    try {
      const res = await authFetch(`${API}/api/documents/${docId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setDocuments((prev) => prev.filter((d) => d.id !== docId));
      }
    } catch (err) {
      setError("Failed to delete document.");
    } finally {
      setDeletingId(null);
    }
  };

  const formatFileSize = (bytes?: number): string => {
    if (!bytes) return "0 KB";
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (!isOpen) return null;

  const filteredDocs = documents.filter((doc) =>
    doc.filename.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-zinc-950/95 shadow-2xl backdrop-blur-2xl ring-1 ring-white/5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/[0.08] px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/10 p-2 text-indigo-400">
              <Cloud size={20} />
            </div>
            <div>
              <h2 className="text-base font-semibold tracking-tight text-white">
                Document Cloud Hub
              </h2>
              <p className="text-xs text-zinc-400">
                Manage persistent multi-tenant documents and attach them to any active chat thread.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.08] transition"
            title="Close hub"
          >
            <X size={18} />
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-6 py-3 border-b border-white/[0.06] bg-white/[0.01]">
          <div className="relative w-full sm:w-72">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search uploaded documents..."
              className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] py-1.5 pl-9 pr-3 text-xs text-zinc-200 placeholder:text-zinc-500 outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/40 transition"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-indigo-500 active:scale-95 transition disabled:opacity-50 cursor-pointer w-full sm:w-auto"
            >
              {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
              <span>{uploading ? (UPLOAD_STAGES[uploadStage] || "Processing…") : "Upload Document"}</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.doc,.txt,.md,.markdown,.csv,.json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileUpload(file);
                e.target.value = "";
              }}
            />
          </div>
        </div>

        {/* Upload Progress Stages */}
        {uploading && (
          <div className="mx-6 mt-3 rounded-xl border border-indigo-500/20 bg-indigo-500/[0.06] px-4 py-3">
            <div className="flex items-center gap-4">
              {[1, 2, 3].map((stage) => {
                const isActive = uploadStage === stage;
                const isComplete = uploadStage > stage;
                return (
                  <div key={stage} className="flex items-center gap-2 text-xs">
                    <div
                      className={`h-2 w-2 rounded-full transition-all duration-300 ${
                        isComplete
                          ? "bg-emerald-400 shadow-sm shadow-emerald-400/50"
                          : isActive
                            ? "bg-indigo-400 animate-pulse shadow-sm shadow-indigo-400/50"
                            : "bg-zinc-600"
                      }`}
                    />
                    <span
                      className={`transition-colors ${
                        isComplete ? "text-emerald-400" : isActive ? "text-indigo-300 font-medium" : "text-zinc-500"
                      }`}
                    >
                      {UPLOAD_STAGES[stage]}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Error notification */}
        {error && (
          <div className="mx-6 mt-3 rounded-xl border border-red-500/30 bg-red-500/10 px-3.5 py-2 text-xs text-red-300">
            {error}
          </div>
        )}

        {/* Document List Table */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 text-zinc-500 gap-2">
              <Loader2 size={24} className="animate-spin text-indigo-400" />
              <p className="text-xs">Loading documents catalog…</p>
            </div>
          ) : filteredDocs.length === 0 && !pendingFile ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4 mb-3">
                <FileText size={32} className="text-zinc-500" />
              </div>
              <h3 className="text-sm font-medium text-zinc-300">No documents found</h3>
              <p className="mt-1 text-xs text-zinc-500 max-w-sm">
                Upload your PDFs, Word docs, Markdown or CSV files to persist them in secure cloud storage and query them with grounded AI citations.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {pendingFile && (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-indigo-500/40 bg-indigo-500/[0.08] p-3 shadow-lg shadow-indigo-500/10">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/20 p-2 text-indigo-400 shrink-0">
                      <Loader2 size={16} className="animate-spin text-indigo-400" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="truncate text-xs font-semibold text-white">{pendingFile.name}</p>
                        <span className="flex items-center gap-1 rounded bg-indigo-500/30 px-2 py-0.5 text-[10px] font-medium text-indigo-200 border border-indigo-500/40">
                          <Loader2 size={10} className="animate-spin" />
                          Saving to Cloud…
                        </span>
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
                        <span>{formatFileSize(pendingFile.size)}</span>
                        <span>•</span>
                        <span className="text-indigo-300 font-mono text-[10px]">
                          {UPLOAD_STAGES[uploadStage] || "Processing…"}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                    <span className="text-xs text-zinc-400 italic">Syncing…</span>
                  </div>
                </div>
              )}

              {filteredDocs.map((doc) => {
                const isAttached = doc.id === activeDocumentId || (doc.doc_id && doc.doc_id === activeDocumentId);
                const isAttaching = attachingId === doc.id;
                const isDeleting = deletingId === doc.id;

                return (
                  <div
                    key={doc.id}
                    className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border p-3 transition ${
                      isAttached
                        ? "border-indigo-500/40 bg-indigo-500/[0.08] shadow-sm"
                        : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04] hover:border-white/10"
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="rounded-lg border border-white/10 bg-white/[0.04] p-2 text-zinc-300 shrink-0">
                        <FileText size={16} className="text-indigo-400" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-xs font-medium text-zinc-200">
                            {doc.filename}
                          </p>
                          {isAttached && (
                            <span className="flex items-center gap-1 rounded bg-indigo-500/20 px-1.5 py-0.5 text-[10px] font-medium text-indigo-300 border border-indigo-500/30">
                              <CheckCircle2 size={10} />
                              Active in Chat
                            </span>
                          )}
                        </div>
                        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                          <span>{formatFileSize(doc.size_bytes)}</span>
                          <span>•</span>
                          <span>{doc.chunks_count || doc.chunks || 0} chunks</span>
                          <span>•</span>
                          <span className="text-emerald-400/90 font-mono text-[10px]">
                            🟢 Synced to Cloud
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                      {doc.drive_web_link && (
                        <a
                          href={doc.drive_web_link}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-lg p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.06] transition"
                          title="View Document"
                        >
                          <ExternalLink size={13} />
                        </a>
                      )}

                      <button
                        onClick={() => handleAttach(doc)}
                        disabled={isAttached || isAttaching}
                        className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition cursor-pointer ${
                          isAttached
                            ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 cursor-default"
                            : "bg-white/[0.06] text-zinc-200 hover:bg-indigo-600 hover:text-white border border-white/[0.08]"
                        }`}
                      >
                        {isAttaching ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Paperclip size={12} />
                        )}
                        <span>{isAttached ? "Attached" : "Attach"}</span>
                      </button>

                      <button
                        onClick={() => handleDelete(doc.id)}
                        disabled={isDeleting}
                        className="rounded-lg p-1.5 text-zinc-500 hover:text-red-400 hover:bg-white/[0.06] transition cursor-pointer"
                        title="Delete document"
                      >
                        {isDeleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-white/[0.08] px-6 py-3 bg-zinc-950/80 text-[11px] text-zinc-500">
          <div className="flex items-center gap-1.5">
            <ShieldCheck size={13} className="text-emerald-400" />
            <span>Encrypted cloud storage (Google Drive + Vector RAG)</span>
          </div>
          <span>
            {pendingFile
              ? `${documents.length + 1} documents (${documents.length} ready, 1 saving)`
              : `${documents.length} document${documents.length === 1 ? "" : "s"} total`}
          </span>
        </div>
      </div>
    </div>
  );
}
