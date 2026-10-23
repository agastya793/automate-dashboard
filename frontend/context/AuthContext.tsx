"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { User, Session } from "@supabase/supabase-js";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

export interface Profile {
  id: string;
  display_name: string | null;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  created_by: string;
}

export type WorkspaceRole = "owner" | "editor" | "viewer";

interface AuthContextType {
  user: User | null;
  session: Session | null;
  profile: Profile | null;
  workspace: Workspace | null;
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
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [role, setRole] = useState<WorkspaceRole | null>(null);
  const configured = isSupabaseConfigured();
  const [isLoading, setIsLoading] = useState(() => isSupabaseConfigured());
  const [error, setError] = useState<string | null>(null);

  // Load workspace & profile for current user
  const loadUserData = useCallback(async (activeUser: User) => {
    const supabase = createClient();
    if (!supabase) return;

    try {
      // 1. Fetch profile
      const { data: profileData } = await supabase
        .from("profiles")
        .select("id, display_name, created_at")
        .eq("id", activeUser.id)
        .maybeSingle();

      if (profileData) {
        setProfile(profileData as Profile);
      } else {
        // Fallback profile if row hasn't synced yet
        const defaultName =
          activeUser.user_metadata?.full_name ||
          activeUser.user_metadata?.display_name ||
          activeUser.email?.split("@")[0] ||
          "User";
        setProfile({
          id: activeUser.id,
          display_name: defaultName,
          created_at: new Date().toISOString(),
        });
      }

      // 2. Fetch primary workspace membership
      const { data: memberData } = await supabase
        .from("workspace_members")
        .select("role, workspace_id, workspaces (id, name, created_by)")
        .eq("user_id", activeUser.id)
        .limit(1)
        .maybeSingle();

      if (memberData && memberData.workspaces) {
        setWorkspace(memberData.workspaces as unknown as Workspace);
        setRole(memberData.role as WorkspaceRole);
      } else {
        // If trigger didn't fire or workspace not found, attempt client-side creation
        const wsName = `${profileData?.display_name || "My"} Workspace`;
        const { data: newWs } = await supabase
          .from("workspaces")
          .insert({ name: wsName, created_by: activeUser.id })
          .select("id, name, created_by")
          .maybeSingle();

        if (newWs) {
          await supabase.from("workspace_members").insert({
            workspace_id: newWs.id,
            user_id: activeUser.id,
            role: "owner",
          });
          setWorkspace(newWs as Workspace);
          setRole("owner");
        }
      }
    } catch (err: any) {
      console.warn("Failed to load user workspace data:", err?.message || err);
    }
  }, []);

  // Listen to auth state changes
  useEffect(() => {
    if (!configured) {
      return;
    }

    const supabase = createClient();
    if (!supabase) {
      return;
    }

    // Initial session
    supabase.auth.getSession().then(({ data: { session: currentSession } }) => {
      setSession(currentSession);
      setUser(currentSession?.user ?? null);
      if (currentSession?.user) {
        loadUserData(currentSession.user).finally(() => setIsLoading(false));
      } else {
        setIsLoading(false);
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, newSession) => {
      setSession(newSession);
      setUser(newSession?.user ?? null);
      if (newSession?.user) {
        await loadUserData(newSession.user);
      } else {
        setProfile(null);
        setWorkspace(null);
        setRole(null);
      }
      setIsLoading(false);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [configured, loadUserData]);

  const signInWithEmail = async (email: string, password: string) => {
    setError(null);
    const supabase = createClient();
    if (!supabase) {
      return { error: "Supabase project credentials are not configured in environment variables." };
    }

    const { data, error: authError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (authError) {
      setError(authError.message);
      return { error: authError.message };
    }

    if (data.user) {
      await loadUserData(data.user);
    }

    return { error: null };
  };

  const signUpWithEmail = async (email: string, password: string, displayName?: string) => {
    setError(null);
    const supabase = createClient();
    if (!supabase) {
      return {
        error: "Supabase project credentials are not configured in environment variables.",
        userConfirmed: false,
      };
    }

    const { data, error: authError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: displayName,
          display_name: displayName,
        },
      },
    });

    if (authError) {
      setError(authError.message);
      return { error: authError.message, userConfirmed: false };
    }

    const userConfirmed = Boolean(data.session);
    if (data.user && data.session) {
      await loadUserData(data.user);
    }

    return { error: null, userConfirmed };
  };

  const signOut = async () => {
    const supabase = createClient();
    if (supabase) {
      await supabase.auth.signOut();
    }
    setUser(null);
    setSession(null);
    setProfile(null);
    setWorkspace(null);
    setRole(null);
  };

  const getAccessToken = async (): Promise<string | null> => {
    if (!configured) return null;
    const supabase = createClient();
    if (!supabase) return null;

    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  };

  const refreshWorkspace = async () => {
    if (user) {
      await loadUserData(user);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        profile,
        workspace,
        role,
        isLoading,
        isConfigured: configured,
        error,
        signInWithEmail,
        signUpWithEmail,
        signOut,
        getAccessToken,
        refreshWorkspace,
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
