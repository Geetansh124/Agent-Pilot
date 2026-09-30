"use client";

import React, { useState } from "react";
import { X, Eye, EyeOff, Loader2, Lock, Mail, User as UserIcon, ShieldCheck } from "lucide-react";
import { useAuth } from "../context/AuthContext";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialMode?: "signin" | "register";
}

export default function AuthModal({ isOpen, onClose, initialMode = "signin" }: AuthModalProps) {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"signin" | "register">(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const validateForm = (): boolean => {
    setError(null);
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email.trim() || !emailRegex.test(email.trim())) {
      setError("Please provide a valid email address.");
      return false;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return false;
    }
    if (mode === "register" && !fullName.trim()) {
      setError("Full name is required to create an account.");
      return false;
    }
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    setLoading(true);
    setError(null);

    try {
      if (mode === "signin") {
        const res = await login(email.trim(), password);
        if (res.success) {
          onClose();
        } else {
          setError(res.error || "Failed to sign in.");
        }
      } else {
        const res = await register(email.trim(), password, fullName.trim());
        if (res.success) {
          onClose();
        } else {
          setError(res.error || "Failed to create account.");
        }
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-md overflow-hidden rounded-2xl border border-white/10 bg-zinc-950/90 p-6 shadow-2xl backdrop-blur-2xl ring-1 ring-white/5 sm:p-8"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-xl p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.08] transition"
          title="Close modal"
        >
          <X size={18} />
        </button>

        {/* Modal Brand Header */}
        <div className="flex flex-col items-center text-center">
          <div className="relative mb-3 flex items-center justify-center">
            <img
              src="/logo.jpg"
              alt="Agent-Pilot Logo"
              className="h-12 w-12 rounded-xl border border-white/15 object-cover shadow-lg ring-1 ring-white/10"
            />
          </div>
          <h2 className="text-xl font-bold tracking-tight text-white">Agent-Pilot</h2>
          <p className="mt-1 text-xs text-zinc-400">
            {mode === "signin"
              ? "Sign in to access your persistent cloud documents"
              : "Create an autonomous workspace account"}
          </p>
        </div>

        {/* Mode Switcher Tabs */}
        <div className="mt-6 flex rounded-xl border border-white/[0.08] bg-white/[0.03] p-1">
          <button
            type="button"
            onClick={() => {
              setMode("signin");
              setError(null);
            }}
            className={`flex-1 rounded-lg py-1.5 text-xs font-medium transition ${
              mode === "signin"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("register");
              setError(null);
            }}
            className={`flex-1 rounded-lg py-1.5 text-xs font-medium transition ${
              mode === "register"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Create Account
          </button>
        </div>

        {/* Error message banner */}
        {error && (
          <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-3.5 py-2.5 text-xs text-red-300">
            {error}
          </div>
        )}

        {/* Auth Form */}
        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          {mode === "register" && (
            <div>
              <label className="block text-[11px] font-medium text-zinc-300 mb-1.5">
                Full Name
              </label>
              <div className="relative">
                <UserIcon size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Alex Vance"
                  required={mode === "register"}
                  className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] py-2 pl-9 pr-3 text-xs text-zinc-100 placeholder:text-zinc-600 outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/40 transition"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-[11px] font-medium text-zinc-300 mb-1.5">
              Email Address
            </label>
            <div className="relative">
              <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
                required
                className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] py-2 pl-9 pr-3 text-xs text-zinc-100 placeholder:text-zinc-600 outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/40 transition"
              />
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-zinc-300 mb-1.5">
              Password
            </label>
            <div className="relative">
              <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                required
                minLength={8}
                className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] py-2 pl-9 pr-10 text-xs text-zinc-100 placeholder:text-zinc-600 outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/40 transition"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition"
              >
                {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <p className="mt-1 text-[10px] text-zinc-500">Minimum 8 characters.</p>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 py-2.5 text-xs font-semibold text-white shadow-md shadow-indigo-600/20 hover:bg-indigo-500 active:scale-[0.99] transition disabled:opacity-50 cursor-pointer"
          >
            {loading && <Loader2 size={14} className="animate-spin" />}
            <span>{mode === "signin" ? "Sign In to Workspace" : "Create Account & Workspace"}</span>
          </button>
        </form>

        {/* Security Footer Guarantee */}
        <div className="mt-6 flex items-center justify-center gap-1.5 text-[11px] text-zinc-500 border-t border-white/[0.06] pt-4">
          <ShieldCheck size={13} className="text-emerald-400" />
          <span>Multi-tenant encrypted · Persistent cloud sync</span>
        </div>
      </div>
    </div>
  );
}
