const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";
const LEGACY_KEY = "token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY) ?? localStorage.getItem(LEGACY_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh?: string | null): void {
  localStorage.setItem(ACCESS_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  localStorage.removeItem(LEGACY_KEY);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(LEGACY_KEY);
}
