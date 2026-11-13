import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setOnUnauthorized, tokenStore } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean; // đang kiểm tra token đã lưu
  signIn: (token: string, user: User) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(() => tokenStore.get() !== null);

  const signOut = useCallback(() => {
    tokenStore.set(null);
    setUser(null);
  }, []);

  const signIn = useCallback((token: string, next: User) => {
    tokenStore.set(token);
    setUser(next);
  }, []);

  useEffect(() => {
    setOnUnauthorized(signOut); // token hết hạn / tài khoản bị khoá → về chế độ khách
    if (tokenStore.get()) {
      api<User>("/auth/me")
        .then(setUser)
        .catch(() => signOut())
        .finally(() => setLoading(false));
    }
    return () => setOnUnauthorized(null);
  }, [signOut]);

  const value = useMemo(() => ({ user, loading, signIn, signOut }), [user, loading, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth phải nằm trong AuthProvider");
  return ctx;
}
