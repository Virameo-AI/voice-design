const KEY = "voice-generator.token";

export function loadToken(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveToken(token: string): void {
  if (token) localStorage.setItem(KEY, token);
  else localStorage.removeItem(KEY);
}
