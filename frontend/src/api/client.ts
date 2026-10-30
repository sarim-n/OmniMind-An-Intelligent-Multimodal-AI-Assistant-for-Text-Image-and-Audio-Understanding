/**
 * Strongly typed HTTP API client with JWT in-memory + localStorage persistence,
 * automatic 401 handling, error normalization, and authenticated blob download.
 */

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000/api/v1";

export interface ApiErrorResponse {
  detail?: string | Array<{ loc: (string | number)[]; msg: string; type: string }>;
  message?: string;
  error?: string;
}

export class ApiError extends Error {
  public status: number;
  public details?: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

type UnauthorizedHandler = () => void;

class ApiClient {
  private token: string | null = null;
  private onUnauthorizedCallbacks: Set<UnauthorizedHandler> = new Set();

  constructor() {
    // Initialize token from localStorage
    try {
      this.token = localStorage.getItem("omnimind_token");
    } catch {
      this.token = null;
    }
  }

  public setToken(token: string | null): void {
    this.token = token;
    try {
      if (token) {
        localStorage.setItem("omnimind_token", token);
      } else {
        localStorage.removeItem("omnimind_token");
      }
    } catch {
      // localStorage might be unavailable in restricted environments
    }
  }

  public getToken(): string | null {
    if (!this.token) {
      try {
        this.token = localStorage.getItem("omnimind_token");
      } catch {
        this.token = null;
      }
    }
    return this.token;
  }

  public onUnauthorized(handler: UnauthorizedHandler): () => void {
    this.onUnauthorizedCallbacks.add(handler);
    return () => this.onUnauthorizedCallbacks.delete(handler);
  }

  private handle401(): void {
    this.setToken(null);
    for (const callback of this.onUnauthorizedCallbacks) {
      callback();
    }
    // Also dispatch custom event for window
    window.dispatchEvent(new CustomEvent("auth:unauthorized"));
  }

  public normalizeError(status: number, data: unknown): ApiError {
    let message = `Request failed with status ${status}`;
    if (data && typeof data === "object") {
      const err = data as ApiErrorResponse;
      if (typeof err.detail === "string") {
        message = err.detail;
      } else if (Array.isArray(err.detail)) {
        message = err.detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
      } else if (err.message) {
        message = err.message;
      } else if (err.error) {
        message = err.error;
      }
    }
    return new ApiError(message, status, data);
  }

  private buildUrl(path: string, params?: Record<string, unknown>): string {
    const cleanPath = path.startsWith("http")
      ? path
      : `${API_BASE_URL}/${path.replace(/^\//, "")}`;

    if (!params) return cleanPath;

    const url = new URL(cleanPath);
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
    return url.toString();
  }

  public async request<T = unknown>(
    path: string,
    options: RequestInit & { params?: Record<string, unknown> } = {}
  ): Promise<T> {
    const { params, headers = {}, ...rest } = options;
    const url = this.buildUrl(path, params);

    const requestHeaders: Record<string, string> = {
      Accept: "application/json",
      ...(headers as Record<string, string>),
    };

    const token = this.getToken();
    if (token && !requestHeaders["Authorization"]) {
      requestHeaders["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      ...rest,
      headers: requestHeaders,
    });

    if (response.status === 401) {
      this.handle401();
      throw new ApiError("Session expired or unauthorized", 401);
    }

    if (!response.ok) {
      let errorData: unknown;
      try {
        errorData = await response.json();
      } catch {
        errorData = await response.text();
      }
      throw this.normalizeError(response.status, errorData);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return (await response.json()) as T;
    }
    return (await response.text()) as unknown as T;
  }

  public async get<T>(path: string, params?: Record<string, unknown>, init?: RequestInit): Promise<T> {
    return this.request<T>(path, { ...init, method: "GET", params });
  }

  public async post<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    const isFormData = body instanceof FormData;
    const headers: Record<string, string> = {
      ...(init?.headers as Record<string, string>),
    };
    if (!isFormData && body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    return this.request<T>(path, {
      ...init,
      method: "POST",
      headers,
      body: isFormData ? (body as FormData) : body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  public async patch<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...init,
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers as Record<string, string>),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  public async put<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...init,
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers as Record<string, string>),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  public async delete<T>(path: string, init?: RequestInit): Promise<T> {
    return this.request<T>(path, { ...init, method: "DELETE" });
  }

  /**
   * Fetch authenticated binary blob (for annotated images, audio files, and PDFs).
   */
  public async fetchBlob(path: string, init?: RequestInit): Promise<Blob> {
    const url = this.buildUrl(path);
    const headers: Record<string, string> = {
      ...(init?.headers as Record<string, string>),
    };

    const token = this.getToken();
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      ...init,
      method: init?.method || "GET",
      headers,
    });

    if (response.status === 401) {
      this.handle401();
      throw new ApiError("Session expired or unauthorized", 401);
    }

    if (!response.ok) {
      throw new ApiError(`Failed to fetch media (status ${response.status})`, response.status);
    }

    return response.blob();
  }

  /**
   * Helper to fetch authenticated media as an ephemeral Object URL.
   * Remember to call URL.revokeObjectURL(url) when no longer needed.
   */
  public async fetchBlobUrl(path: string): Promise<string> {
    const blob = await this.fetchBlob(path);
    return URL.createObjectURL(blob);
  }
}

export const apiClient = new ApiClient();
