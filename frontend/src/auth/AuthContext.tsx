import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getMe, login as loginRequest } from "../api/auth";
import { ApiError, getAccessToken, onUnauthorized, setTokens } from "../api/client";
import { queryClient } from "../queryClient";
import type { Me, TokenPair } from "../api/types";

interface AuthContextValue {
  user: Me | null;
  loading: boolean;
  // Signed in, but the server couldn't be reached to load the account (offline, restarting).
  unreachable: boolean;
  retry: () => void;
  login: (email: string, password: string) => Promise<void>;
  // Start a session from tokens already issued (e.g. after a password reset).
  signIn: (tokens: TokenPair) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [unreachable, setUnreachable] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    onUnauthorized(() => {
      queryClient.clear();
      setUser(null);
    });
    return () => onUnauthorized(null);
  }, []);

  // Load the signed-in account. A rejected session (401) is handled by the API
  // client (refresh, else sign out); anything else — offline, server restarting —
  // keeps the session and retries, so a blip on a slow connection doesn't sign people out.
  useEffect(() => {
    if (!getAccessToken()) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const delays = [1000, 2000, 4000];
    async function load() {
      setLoading(true);
      setUnreachable(false);
      for (let i = 0; ; i++) {
        try {
          const me = await getMe();
          if (!cancelled) setUser(me);
          break;
        } catch (e) {
          if (cancelled) return;
          if (e instanceof ApiError && e.status === 401) {
            setTokens(null);
            break;
          }
          if (i >= delays.length) {
            setUnreachable(true);
            break;
          }
          await new Promise((resolve) => setTimeout(resolve, delays[i]));
        }
      }
      if (!cancelled) setLoading(false);
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  async function login(email: string, password: string) {
    setTokens(await loginRequest(email, password));
    const me = await getMe();
    setUser(me);
  }

  async function signIn(tokens: TokenPair) {
    queryClient.clear();
    setTokens(tokens);
    setUser(await getMe());
  }

  function logout() {
    setTokens(null);
    // Don't let the next person on this browser see the last user's data.
    queryClient.clear();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, unreachable, retry: () => setAttempt((a) => a + 1), login, signIn, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
