"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { User, getApiBaseUrl } from "../components/types";

interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  register: (email: string, password: string, fullName: string) => Promise<{ success: boolean; error?: string }>;
  loginWithGoogle: (credential: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
  authFetch: (url: string, options?: RequestInit) => Promise<Response>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const API = getApiBaseUrl();

  // Restore session from localStorage on mount
  useEffect(() => {
    async function initAuth() {
      try {
        const storedToken = localStorage.getItem("agent_pilot_token");
        const storedRefresh = localStorage.getItem("agent_pilot_refresh");
        const storedUser = localStorage.getItem("agent_pilot_user");

        if (storedUser) {
          try {
            setUser(JSON.parse(storedUser));
          } catch {
            /* ignore */
          }
        }

        if (storedToken) {
          setAccessToken(storedToken);
          const meRes = await fetch(`${API}/api/auth/me`, {
            headers: { Authorization: `Bearer ${storedToken}` },
          });

          if (meRes.ok) {
            const userData = await meRes.json();
            setUser(userData);
            localStorage.setItem("agent_pilot_user", JSON.stringify(userData));
          } else if (storedRefresh) {
            // Attempt token refresh
            const refreshed = await attemptRefresh(storedRefresh);
            if (!refreshed) {
              clearAuth();
            }
          } else {
            clearAuth();
          }
        }
      } catch (err) {
        console.error("Auth initialization error:", err);
      } finally {
        setIsLoading(false);
      }
    }
    initAuth();
  }, []);

  const attemptRefresh = async (refreshToken: string): Promise<boolean> => {
    try {
      const res = await fetch(`${API}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (res.ok) {
        const data = await res.json();
        setAccessToken(data.access_token);
        localStorage.setItem("agent_pilot_token", data.access_token);
        if (data.refresh_token) {
          localStorage.setItem("agent_pilot_refresh", data.refresh_token);
        }

        const meRes = await fetch(`${API}/api/auth/me`, {
          headers: { Authorization: `Bearer ${data.access_token}` },
        });
        if (meRes.ok) {
          const userData = await meRes.json();
          setUser(userData);
          localStorage.setItem("agent_pilot_user", JSON.stringify(userData));
          return true;
        }
      }
    } catch (err) {
      console.error("Token refresh failed:", err);
    }
    return false;
  };

  const clearAuth = () => {
    setUser(null);
    setAccessToken(null);
    localStorage.removeItem("agent_pilot_token");
    localStorage.removeItem("agent_pilot_refresh");
    localStorage.removeItem("agent_pilot_user");
  };

  const login = async (email: string, password: string): Promise<{ success: boolean; error?: string }> => {
    try {
      const res = await fetch(`${API}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();
      if (!res.ok) {
        return { success: false, error: data.detail || "Invalid credentials." };
      }

      setAccessToken(data.access_token);
      localStorage.setItem("agent_pilot_token", data.access_token);
      if (data.refresh_token) {
        localStorage.setItem("agent_pilot_refresh", data.refresh_token);
      }

      setUser(data.user);
      localStorage.setItem("agent_pilot_user", JSON.stringify(data.user));
      return { success: true };
    } catch (err) {
      return { success: false, error: "Network error connecting to authentication server." };
    }
  };

  const register = async (email: string, password: string, fullName: string): Promise<{ success: boolean; error?: string }> => {
    try {
      const res = await fetch(`${API}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, full_name: fullName }),
      });

      const data = await res.json();
      if (!res.ok) {
        return { success: false, error: data.detail || "Registration failed." };
      }

      setAccessToken(data.access_token);
      localStorage.setItem("agent_pilot_token", data.access_token);
      if (data.refresh_token) {
        localStorage.setItem("agent_pilot_refresh", data.refresh_token);
      }

      setUser(data.user);
      localStorage.setItem("agent_pilot_user", JSON.stringify(data.user));
      return { success: true };
    } catch (err) {
      return { success: false, error: "Network error registering user account." };
    }
  };

  const loginWithGoogle = async (credential: string): Promise<{ success: boolean; error?: string }> => {
    try {
      const res = await fetch(`${API}/api/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credential }),
      });
      const data = await res.json();
      if (!res.ok) {
        return { success: false, error: data.detail || "Google sign-in failed." };
      }
      setAccessToken(data.access_token);
      localStorage.setItem("agent_pilot_token", data.access_token);
      if (data.refresh_token) {
        localStorage.setItem("agent_pilot_refresh", data.refresh_token);
      }

      let userData = data.user;
      if (credential) {
        try {
          const parts = credential.split(".");
          if (parts.length > 1) {
            const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
            if (payload?.picture && (!userData?.avatar_url || userData.avatar_url !== payload.picture)) {
              userData = { ...userData, avatar_url: payload.picture };
            }
          }
        } catch {
          // ignore JWT decode fallback
        }
      }

      setUser(userData);
      localStorage.setItem("agent_pilot_user", JSON.stringify(userData));
      return { success: true };
    } catch {
      return { success: false, error: "Network error during Google sign-in." };
    }
  };

  const logout = async (): Promise<void> => {
    const token = accessToken || localStorage.getItem("agent_pilot_token");
    if (token) {
      try {
        await fetch(`${API}/api/auth/logout`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch (err) {
        /* best-effort */
      }
    }
    clearAuth();
  };

  // Authenticated fetch wrapper that automatically attaches Authorization: Bearer <token>
  const authFetch = useCallback(
    async (url: string, options: RequestInit = {}): Promise<Response> => {
      const headers = new Headers(options.headers || {});
      const currentToken = accessToken || localStorage.getItem("agent_pilot_token");

      if (currentToken) {
        headers.set("Authorization", `Bearer ${currentToken}`);
      }

      // When body is FormData, let the browser auto-generate the
      // multipart/form-data Content-Type with the correct boundary.
      if (options.body instanceof FormData) {
        headers.delete("Content-Type");
      }

      let response = await fetch(url, { ...options, headers });

      // If token expired (401), attempt refresh and retry once
      if (response.status === 401) {
        const storedRefresh = localStorage.getItem("agent_pilot_refresh");
        if (storedRefresh) {
          const refreshed = await attemptRefresh(storedRefresh);
          if (refreshed) {
            const newToken = localStorage.getItem("agent_pilot_token");
            if (newToken) {
              headers.set("Authorization", `Bearer ${newToken}`);
              response = await fetch(url, { ...options, headers });
            }
          } else {
            clearAuth();
          }
        }
      }

      return response;
    },
    [accessToken]
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        loginWithGoogle,
        logout,
        authFetch,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
