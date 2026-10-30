import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiClient, ApiError } from "../api/client";

describe("API Client & 401 Interception", () => {
  beforeEach(() => {
    localStorage.clear();
    apiClient.setToken(null);
    vi.restoreAllMocks();
  });

  it("persists token in memory and localStorage", () => {
    expect(apiClient.getToken()).toBeNull();

    apiClient.setToken("test_jwt_token_123");
    expect(apiClient.getToken()).toBe("test_jwt_token_123");
    expect(localStorage.getItem("omnimind_token")).toBe("test_jwt_token_123");

    apiClient.setToken(null);
    expect(apiClient.getToken()).toBeNull();
    expect(localStorage.getItem("omnimind_token")).toBeNull();
  });

  it("intercepts 401 response, clears token, and triggers onUnauthorized handlers", async () => {
    apiClient.setToken("expired_or_invalid_token");
    const onUnauthorizedSpy = vi.fn();
    const unsubscribe = apiClient.onUnauthorized(onUnauthorizedSpy);

    const windowEventSpy = vi.fn();
    window.addEventListener("auth:unauthorized", windowEventSpy);

    // Mock 401 response from fetch
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 401,
        ok: false,
        json: async () => ({ detail: "Token expired" }),
      })
    );

    await expect(apiClient.get("/conversations")).rejects.toThrow(ApiError);

    expect(apiClient.getToken()).toBeNull();
    expect(onUnauthorizedSpy).toHaveBeenCalledTimes(1);
    expect(windowEventSpy).toHaveBeenCalledTimes(1);

    unsubscribe();
    window.removeEventListener("auth:unauthorized", windowEventSpy);
  });

  it("normalizes FastAPI validation and detail error objects into clean messages", () => {
    // String detail
    const err1 = apiClient.normalizeError(400, { detail: "Email already exists" });
    expect(err1.message).toBe("Email already exists");
    expect(err1.status).toBe(400);

    // Array of pydantic errors
    const err2 = apiClient.normalizeError(422, {
      detail: [
        { loc: ["body", "password"], msg: "Password too short", type: "value_error" },
        { loc: ["body", "email"], msg: "Invalid email", type: "value_error" },
      ],
    });
    expect(err2.message).toContain("Password too short");
    expect(err2.message).toContain("Invalid email");

    // Generic error fallback
    const err3 = apiClient.normalizeError(500, "Internal Server Error");
    expect(err3.message).toBe("Request failed with status 500");
  });
});
