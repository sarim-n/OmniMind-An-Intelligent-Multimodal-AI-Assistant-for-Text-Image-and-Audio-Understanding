import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { apiClient } from "../api/client";

export interface User {
  id: string;
  email: string;
  created_at: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setTokenState] = useState<string | null>(() => apiClient.getToken());
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const fetchCurrentUser = useCallback(async () => {
    try {
      const profile = await apiClient.get<User>("/auth/me");
      setUser(profile);
    } catch {
      apiClient.setToken(null);
      setTokenState(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) {
      fetchCurrentUser();
    } else {
      setIsLoading(false);
    }

    const unsubscribe = apiClient.onUnauthorized(() => {
      setTokenState(null);
      setUser(null);
    });

    const handleUnauthorizedEvent = () => {
      setTokenState(null);
      setUser(null);
    };
    window.addEventListener("auth:unauthorized", handleUnauthorizedEvent);

    return () => {
      unsubscribe();
      window.removeEventListener("auth:unauthorized", handleUnauthorizedEvent);
    };
  }, [token, fetchCurrentUser]);

  const login = async (email: string, password: string): Promise<void> => {
    setIsLoading(true);
    try {
      // Login MUST send application/x-www-form-urlencoded with username=<email> and password
      const body = new URLSearchParams();
      body.append("username", email);
      body.append("password", password);

      const data = await apiClient.request<{ access_token: string; token_type: string }>("/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: body.toString(),
      });

      apiClient.setToken(data.access_token);
      setTokenState(data.access_token);

      const profile = await apiClient.get<User>("/auth/me");
      setUser(profile);
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (email: string, password: string): Promise<void> => {
    setIsLoading(true);
    try {
      await apiClient.post("/auth/register", { email, password });
      // Automatically log in after registration
      await login(email, password);
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    apiClient.setToken(null);
    setTokenState(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token && !!user,
        isLoading,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
