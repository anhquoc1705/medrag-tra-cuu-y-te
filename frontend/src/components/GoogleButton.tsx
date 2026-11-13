import { useEffect, useRef } from "react";

// Nút "Tiếp tục với Google" của Google Identity Services: Google trả về ID token (credential),
// backend kiểm tra token bằng google-auth (POST /auth/google). Không cần thư viện npm.

interface GoogleId {
  initialize(options: { client_id: string; callback: (r: { credential: string }) => void; ux_mode?: string }): void;
  renderButton(el: HTMLElement, options: Record<string, unknown>): void;
}
declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

let loader: Promise<void> | null = null;
function loadScript(): Promise<void> {
  loader ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => {
      loader = null;
      reject(new Error("Không tải được nút đăng nhập Google"));
    };
    document.head.appendChild(s);
  });
  return loader;
}

export function GoogleButton({ clientId, onCredential, onError }: { clientId: string; onCredential: (credential: string) => void; onError: (msg: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const callback = useRef(onCredential);
  callback.current = onCredential;

  useEffect(() => {
    let alive = true;
    loadScript()
      .then(() => {
        const el = ref.current;
        if (!alive || !el || !window.google) return;
        window.google.accounts.id.initialize({ client_id: clientId, callback: (r) => callback.current(r.credential) });
        window.google.accounts.id.renderButton(el, {
          theme: "outline",
          size: "large",
          shape: "pill",
          text: "continue_with",
          locale: "vi",
          width: Math.min(el.clientWidth || 360, 400),
        });
      })
      .catch((e: Error) => alive && onError(e.message));
    return () => {
      alive = false;
    };
  }, [clientId, onError]);

  return <div ref={ref} className="flex min-h-11 w-full justify-center" />;
}
