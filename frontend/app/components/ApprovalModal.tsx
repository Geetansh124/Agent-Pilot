"use client";

import React, { useState } from "react";
import { AlertTriangle, Check, X, ShieldAlert } from "lucide-react";

export interface PendingApproval {
  request_id: string;
  tool_name: string;
  arguments: Record<string, any>;
  thread_id: string;
  reason?: string;
}

interface ApprovalModalProps {
  isOpen: boolean;
  approval: PendingApproval | null;
  onDecision: (requestId: string, decision: "allowed-once" | "rejected" | "cancelled") => Promise<void>;
  onClose: () => void;
}

export default function ApprovalModal({
  isOpen,
  approval,
  onDecision,
  onClose,
}: ApprovalModalProps) {
  const [submitting, setSubmitting] = useState(false);

  if (!isOpen || !approval) return null;

  const handleAction = async (decision: "allowed-once" | "rejected" | "cancelled") => {
    try {
      setSubmitting(true);
      await onDecision(approval.request_id, decision);
      onClose();
    } catch (err) {
      console.error("Failed to submit approval decision:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-md rounded-2xl border border-amber-500/30 bg-slate-900/95 p-6 shadow-2xl">
        <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-100">Tool Authorization Required</h3>
            <p className="text-xs text-slate-400">Human-in-the-Loop Security Gate</p>
          </div>
        </div>

        <div className="my-4 space-y-3">
          <div className="rounded-lg bg-slate-800/60 p-3">
            <span className="text-xs font-medium text-slate-400">Requested Tool:</span>
            <div className="font-mono text-sm font-semibold text-amber-300">{approval.tool_name}</div>
          </div>

          <div className="rounded-lg bg-slate-800/60 p-3">
            <span className="text-xs font-medium text-slate-400">Arguments:</span>
            <pre className="mt-1 max-h-36 overflow-auto rounded bg-slate-950 p-2 font-mono text-xs text-slate-300">
              {JSON.stringify(approval.arguments, null, 2)}
            </pre>
          </div>

          {approval.reason && (
            <p className="text-xs text-slate-400">
              <span className="font-medium text-slate-300">Reason:</span> {approval.reason}
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
          <button
            type="button"
            disabled={submitting}
            onClick={() => handleAction("cancelled")}
            className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            <X className="h-4 w-4" /> Cancel
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => handleAction("rejected")}
            className="flex items-center gap-1.5 rounded-lg bg-rose-500/10 px-3 py-2 text-xs font-medium text-rose-400 hover:bg-rose-500/20"
          >
            <AlertTriangle className="h-4 w-4" /> Deny
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => handleAction("allowed-once")}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-500/20 px-4 py-2 text-xs font-medium text-emerald-400 hover:bg-emerald-500/30 shadow-lg shadow-emerald-500/10"
          >
            <Check className="h-4 w-4" /> Allow Once
          </button>
        </div>
      </div>
    </div>
  );
}

