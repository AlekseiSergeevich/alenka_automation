import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authApi } from "@/api/auth";
import type { UserDto } from "@/api/types";
import { isAuthUiDisabled } from "@/lib/authUi";

const DEV_USER: UserDto = { username: "dev", role: "admin" };

interface AuthContextValue {
  user: UserDto | null;
  status: "loading" | "authenticated" | "unauthenticated";
  setUser: (user: UserDto | null) => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const bypass = isAuthUiDisabled();
  const [user, setUserState] = useState<UserDto | null>(() =>
    bypass ? DEV_USER : null,
  );
  const [status, setStatus] = useState<AuthContextValue["status"]>(() =>
    bypass ? "authenticated" : "loading",
  );

  const refresh = useCallback(async () => {
    if (isAuthUiDisabled()) {
      setUserState(DEV_USER);
      setStatus("authenticated");
      return;
    }
    try {
      const me = await authApi.fetchCurrentUser();
      setUserState(me);
      setStatus(me ? "authenticated" : "unauthenticated");
    } catch {
      setUserState(null);
      setStatus("unauthenticated");
    }
  }, []);

  const setUser = useCallback(
    (next: UserDto | null) => {
      setUserState(next);
      setStatus(next ? "authenticated" : "unauthenticated");
      if (!next) {
        queryClient.clear();
      }
    },
    [queryClient],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, setUser, refresh }),
    [user, status, setUser, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
