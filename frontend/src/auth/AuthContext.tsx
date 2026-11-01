import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getMe, login as loginRequest } from "../api/auth";
import { getAccessToken, onUnauthorized, setTokens } from "../api/client";
import { queryClient } from "../queryClient";
import type { Me, TokenPair } from "../api/types";

interface AuthContextValue {
  user: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  // Start a session from tokens already issued (e.g. after a password reset).
  signIn: (tokens: TokenPair) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    onUnauthorized(() => {
      queryClient.clear();
      setUser(null);
    });
    return () => onUnauthorized(null);
  }, []);

  useEffect(() => {
    if (!getAccessToken()) {
      setLoading(false);
      return;
    }
    getMe()
      .then(setUser)
      .catch(() => setTokens(null))
      .finally(() => setLoading(false));
  }, []);

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
    <AuthContext.Provider value={{ user, loading, login, signIn, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
