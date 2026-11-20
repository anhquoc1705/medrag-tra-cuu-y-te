// Gọi backend FastAPI. Token đăng nhập lưu ở localStorage (bọc try/catch: trình duyệt chặn bộ nhớ vẫn dùng được ở chế độ khách).

import { Capacitor } from "@capacitor/core";

// 127.0.0.1 thay vì localhost: trên Windows "localhost" thử IPv6 (::1) trước, backend chỉ nghe IPv4 → chậm thêm mỗi yêu cầu (GĐ 7)
const DEFAULT_BASE = (import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const TOKEN_KEY = "medrag.token";
const SERVER_KEY = "medrag.server";

// App Android (Capacitor): địa chỉ backend đổi được ngay trong app, không cần build lại – địa chỉ đám mây / ngrok
// có thể đổi sau khi đã cài app lên điện thoại. Bản web vẫn chỉ dùng VITE_API_URL.
export const isNativeApp = Capacitor.isNativePlatform();

export const serverStore = {
  get(): string {
    if (!isNativeApp) return DEFAULT_BASE;
    try {
      return localStorage.getItem(SERVER_KEY) || DEFAULT_BASE;
    } catch {
      return DEFAULT_BASE;
    }
  },
  /** Lưu địa chỉ mới (chuỗi rỗng = về mặc định lúc build). Trả về địa chỉ đã chuẩn hoá, hoặc lỗi nếu sai định dạng. */
  set(raw: string): string {
    let url = raw.trim().replace(/\/+$/, "");
    if (url && !/^https?:\/\//i.test(url)) url = "https://" + url;
    if (url) new URL(url); // ném lỗi nếu không phải địa chỉ hợp lệ
    try {
      if (url) localStorage.setItem(SERVER_KEY, url);
      else localStorage.removeItem(SERVER_KEY);
    } catch {
      /* bỏ qua */
    }
    return url || DEFAULT_BASE;
  },
};

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string | null) {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* bỏ qua */
    }
  },
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let onUnauthorized: (() => void) | null = null;
export function setOnUnauthorized(fn: (() => void) | null) {
  onUnauthorized = fn;
}

function detailMessage(data: unknown): string | null {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "Dữ liệu gửi lên không hợp lệ: " + detail.map((d) => d?.msg).filter(Boolean).join("; ");
  return null;
}

export async function api<T>(path: string, options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const token = tokenStore.get();
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  const base = serverStore.get();
  // ngrok bản miễn phí chèn trang cảnh báo trước yêu cầu từ trình duyệt → gửi kèm header này để bỏ qua
  if (base.includes("ngrok")) headers["ngrok-skip-browser-warning"] = "1";
  let res: Response;
  try {
    res = await fetch(base + path, {
      method: options.method ?? (options.body !== undefined ? "POST" : "GET"),
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(
      0,
      isNativeApp
        ? `Không kết nối được máy chủ (${base}). Mở menu ☰ → “Máy chủ” để kiểm tra địa chỉ.`
        : "Không kết nối được máy chủ. Hãy kiểm tra backend đang chạy.",
    );
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized?.();
    throw new ApiError(res.status, detailMessage(data) ?? `Lỗi máy chủ (${res.status})`);
  }
  return data as T;
}
