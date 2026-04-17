import { describe, expect, it } from "vitest";
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./auth";

describe("auth token storage", () => {
  it("returns null when no tokens are set", () => {
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it("stores both access and refresh tokens via setTokens", () => {
    setTokens("access-abc", "refresh-xyz");
    expect(getAccessToken()).toBe("access-abc");
    expect(getRefreshToken()).toBe("refresh-xyz");
  });

  it("updates access without touching refresh when refresh is omitted", () => {
    setTokens("access-1", "refresh-1");
    setTokens("access-2");
    expect(getAccessToken()).toBe("access-2");
    expect(getRefreshToken()).toBe("refresh-1");
  });

  it("falls back to legacy 'token' key when access_token missing (migration path)", () => {
    localStorage.setItem("token", "legacy-token");
    expect(getAccessToken()).toBe("legacy-token");
  });

  it("prefers access_token over legacy 'token' when both exist", () => {
    localStorage.setItem("token", "legacy-token");
    setTokens("new-access");
    expect(getAccessToken()).toBe("new-access");
  });

  it("setTokens clears the legacy 'token' key", () => {
    localStorage.setItem("token", "legacy-token");
    setTokens("new-access");
    expect(localStorage.getItem("token")).toBeNull();
  });

  it("clearTokens removes access, refresh, and legacy keys", () => {
    setTokens("a", "r");
    localStorage.setItem("token", "legacy");
    clearTokens();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(localStorage.getItem("token")).toBeNull();
  });
});
