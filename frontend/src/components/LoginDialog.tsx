import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import type { User } from "../types";
import { GoogleButton } from "./GoogleButton";
import { ErrorNote } from "./ui";

// Hộp "Đăng nhập hoặc đăng ký": Google, hoặc email → (mật khẩu nếu đã có tài khoản | họ tên + mật khẩu nếu email mới).

type Step = "start" | "password" | "register";
type Session = { token: string; user: User };

let googleClientId: Promise<string | null> | null = null;
const getGoogleClientId = () =>
  (googleClientId ??= api<{ google_client_id: string | null }>("/auth/config")
    .then((r) => r.google_client_id)
    .catch(() => {
      googleClientId = null;
      return null;
    }));

const input =
  "w-full rounded-full border border-line bg-paper px-[18px] py-3 text-[15px] text-ink placeholder:text-muted focus:border-pine focus:outline-none";
const pillDark = "w-full rounded-full border border-ink bg-ink px-[18px] py-3 text-[15px] font-semibold text-surface hover:opacity-90 disabled:opacity-60";

export function LoginDialog({ open, onClose, title = "Đăng nhập hoặc đăng ký" }: { open: boolean; onClose: () => void; title?: string }) {
  const { signIn } = useAuth();
  const ref = useRef<HTMLDialogElement>(null);
  const [step, setStep] = useState<Step>("start");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [clientId, setClientId] = useState<string | null>(null);

  useEffect(() => {
    const dlg = ref.current;
    if (!dlg) return;
    if (open && !dlg.open) {
      setStep("start");
      setPassword("");
      setError(null);
      dlg.showModal();
      getGoogleClientId().then(setClientId);
    } else if (!open && dlg.open) dlg.close();
  }, [open]);

  const finish = useCallback(
    (s: Session) => {
      signIn(s.token, s.user);
      onClose();
    },
    [signIn, onClose],
  );

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const submitEmail = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const r = await api<{ exists: boolean; has_password: boolean }>("/auth/check-email", { body: { email } });
      if (r.exists && !r.has_password) throw new Error("Email này đã đăng ký bằng Google – hãy bấm “Tiếp tục với Google”.");
      setStep(r.exists ? "password" : "register");
    });
  };

  const submitPassword = (e: FormEvent) => {
    e.preventDefault();
    run(async () =>
      finish(
        step === "register"
          ? await api<Session>("/auth/register", { body: { email, name, password } })
          : await api<Session>("/auth/login", { body: { email, password } }),
      ),
    );
  };

  const onGoogle = useCallback(
    (credential: string) => {
      setBusy(true);
      setError(null);
      api<Session>("/auth/google", { body: { credential } })
        .then(finish)
        .catch((e: Error) => setError(e.message))
        .finally(() => setBusy(false));
    },
    [finish],
  );

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby="login-title"
      className="m-auto w-[min(440px,calc(100%-32px))] rounded-[18px] bg-surface p-0 text-ink shadow-2xl"
    >
      <div className="relative flex flex-col gap-3 px-9 pb-8 pt-8 max-sm:px-5">
        <button type="button" onClick={onClose} aria-label="Đóng" className="absolute right-3.5 top-3.5 text-xl leading-none text-muted">
          ×
        </button>

        {step === "start" ? (
          <form onSubmit={submitEmail} className="flex flex-col gap-3">
            <h2 id="login-title" className="text-center text-2xl font-semibold tracking-tight">
              {title}
            </h2>
            <p className="mb-2 text-center text-sm text-balance text-muted">Lưu lại các cuộc hỏi đáp và xem lại trên mọi thiết bị.</p>
            {clientId && (
              <>
                <GoogleButton clientId={clientId} onCredential={onGoogle} onError={setError} />
                <div className="my-1 flex items-center gap-3 text-xs tracking-widest text-muted before:flex-1 before:border-t before:border-line after:flex-1 after:border-t after:border-line">
                  HOẶC
                </div>
              </>
            )}
            <input
              type="email"
              required
              autoComplete="email"
              aria-label="Địa chỉ email"
              placeholder="Địa chỉ email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={input}
            />
            {error && <ErrorNote>{error}</ErrorNote>}
            <button type="submit" disabled={busy} className={pillDark}>
              {busy ? "Đang kiểm tra…" : "Tiếp tục"}
            </button>
          </form>
        ) : (
          <form onSubmit={submitPassword} className="flex flex-col gap-3">
            <button type="button" onClick={() => setStep("start")} className="self-start text-[13px] text-muted">
              ← Quay lại
            </button>
            <h2 id="login-title" className="text-center text-2xl font-semibold tracking-tight">
              {step === "register" ? "Tạo tài khoản" : "Nhập mật khẩu"}
            </h2>
            <p className="-mt-1 mb-1 break-all text-center text-sm">{email}</p>
            {step === "register" && (
              <input
                required
                autoComplete="name"
                aria-label="Họ tên"
                placeholder="Họ tên"
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
                className={input}
              />
            )}
            <input
              type="password"
              required
              minLength={step === "register" ? 8 : 1}
              autoComplete={step === "register" ? "new-password" : "current-password"}
              aria-label="Mật khẩu"
              placeholder={step === "register" ? "Mật khẩu (ít nhất 8 ký tự)" : "Mật khẩu"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={input}
              autoFocus
            />
            {error && <ErrorNote>{error}</ErrorNote>}
            <button type="submit" disabled={busy} className={pillDark}>
              {busy ? "Đang xử lý…" : step === "register" ? "Tạo tài khoản" : "Đăng nhập"}
            </button>
          </form>
        )}
      </div>
    </dialog>
  );
}
