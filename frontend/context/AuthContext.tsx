"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { apiFetch, fetchCsrfToken } from "@/lib/api";

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  workspace_id?: string | null;
  workspace_role?: string | null;
}

export interface Profile {
  id: string;
  display_name: string | null;
  created_at?: string;
}

export interface Workspace {
  id: string;
  name: string;
  role: string;
  created_at?: string;
}

export type WorkspaceRole = "admin" | "editor" | "viewer" | "owner";

interface AuthContextType {
  user: User | null;
  session: any | null;
  profile: Profile | null;
  workspace: Workspace | null;
  workspaces: Workspace[];
  role: WorkspaceRole | null;
  isLoading: boolean;
  isConfigured: boolean;
  error: string | null;
  signInWithEmail: (email: string, password: string) => Promise<{ error: string | null }>;
  signUpWithEmail: (
    email: string,
    password: string,
    displayName?: string
  ) => Promise<{ error: string | null; userConfirmed: boolean }>;
  signOut: () => Promise<void>;
  getAccessToken: () => Promise<string | null>;
  refreshWorkspace: () => Promise<void>;
  switchWorkspace: (workspaceId: string) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [role, setRole] = useState<WorkspaceRole | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load current authenticated user and workspaces from FastAPI backend
  const checkSession = useCallback(async () => {
    try {
      // Ensure CSRF token cookie is present
      await fetchCsrfToken();

      const res = await apiFetch("/api/auth/me", { method: "GET" });
      if (res.ok) {
        const data = await res.json();
        const authedUser: User = data.user;
        setUser(authedUser);
        setProfile({
          id: authedUser.id,
          display_name: authedUser.display_name || authedUser.email.split("@")[0],
        });
        setWorkspaces(data.workspaces || []);
        if (data.active_workspace) {
          setWorkspace(data.active_workspace);
          setRole((data.active_workspace.role as WorkspaceRole) || "viewer");
        } else if (data.workspaces && data.workspaces.length > 0) {
          setWorkspace(data.workspaces[0]);
          setRole((data.workspaces[0].role as WorkspaceRole) || "viewer");
        }
      } else {
        setUser(null);
        setProfile(null);
        setWorkspace(null);
        setWorkspaces([]);
        setRole(null);
      }
    } catch {
      setUser(null);
      setProfile(null);
      setWorkspace(null);
      setWorkspaces([]);
      setRole(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const initializeAuth = async () => {
      if (active) {
        await checkSession();
      }
    };
    initializeAuth();
    return () => {
      active = false;
    };
  }, [checkSession]);

  const signInWithEmail = async (email: string, password: string) => {
    setError(null);
    try {
      const res = await apiFetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        const msg = errData.detail || "Invalid email or password.";
        setError(msg);
        return { error: msg };
      }

      await checkSession();
      return { error: null };
    } catch (err: any) {
      const msg = err?.message || "Failed to connect to authentication server.";
      setError(msg);
      return { error: msg };
    }
  };

  const signUpWithEmail = async (email: string, password: string, displayName?: string) => {
    setError(null);
    try {
      const res = await apiFetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
          display_name: displayName || undefined,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        const msg = errData.detail || "Registration failed. Please check your details.";
        setError(msg);
        return { error: msg, userConfirmed: false };
      }

      await checkSession();
      return { error: null, userConfirmed: true };
    } catch (err: any) {
      const msg = err?.message || "Failed to connect to registration server.";
      setError(msg);
      return { error: msg, userConfirmed: false };
    }
  };

  const signOut = async () => {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch {
      // Non-fatal
    } finally {
      setUser(null);
      setProfile(null);
      setWorkspace(null);
      setWorkspaces([]);
      setRole(null);
    }
  };

  const getAccessToken = async (): Promise<string | null> => {
    // Session token is stored in HTTP-only cookie for maximum security
    return null;
  };

  const refreshWorkspace = async () => {
    await checkSession();
  };

  const switchWorkspace = (workspaceId: string) => {
    const target = workspaces.find((w) => w.id === workspaceId);
    if (target) {
      setWorkspace(target);
      setRole((target.role as WorkspaceRole) || "viewer");
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session: user ? { user } : null,
        profile,
        workspace,
        workspaces,
        role,
        isLoading,
        isConfigured: true,
        error,
        signInWithEmail,
        signUpWithEmail,
        signOut,
        getAccessToken,
        refreshWorkspace,
        switchWorkspace,
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
