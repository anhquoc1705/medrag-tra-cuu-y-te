import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Tone } from "../labels";

const TONES: Record<Tone, string> = {
  ok: "bg-ok-soft text-ok",
  info: "bg-pine-soft text-pine",
  warn: "bg-warn-soft text-warn",
  bad: "bg-danger-soft text-danger",
  plain: "bg-user text-muted",
};

export function Chip({ tone = "plain", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>{children}</span>;
}

type Variant = "primary" | "outline" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "border-pine bg-pine text-surface hover:opacity-90",
  danger: "border-danger bg-danger text-surface hover:opacity-90",
  outline: "border-line bg-surface hover:bg-user",
  ghost: "border-transparent text-muted hover:bg-user",
};

export function Button({ variant = "outline", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      {...props}
      className={`rounded-lg border px-3 py-1.5 text-[13px] font-semibold disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
    />
  );
}

export function Avatar({ name, guest = false }: { name: string; guest?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`grid size-10 flex-none place-items-center rounded-full bg-user text-[15px] font-semibold ${guest ? "text-muted" : "text-ink"}`}
    >
      {guest ? "?" : name.trim().charAt(0).toUpperCase() || "?"}
    </span>
  );
}

export function LogoutButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} aria-label="Đăng xuất" title="Đăng xuất" className="grid size-9 flex-none place-items-center rounded-lg text-muted hover:bg-user hover:text-ink">
      <svg viewBox="0 0 24 24" aria-hidden="true" className="size-5 fill-none stroke-current" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
        <path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M15 8l4 4-4 4M19 12H9" />
      </svg>
    </button>
  );
}

export function ChatIcon({ className = "size-[18px]" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={`flex-none fill-none stroke-current ${className}`} strokeWidth={1.8} strokeLinejoin="round">
      <path d="M4 5h16v11H9l-5 4z" />
    </svg>
  );
}

export function Logo({ className = "size-8" }: { className?: string }) {
  // cùng hình với public/favicon.svg; màu theo --pine để đổi theo chế độ sáng/tối
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={`flex-none ${className}`}>
      <rect width="32" height="32" rx="8" className="fill-pine" />
      <path d="M13 7h6v6h6v6h-6v6h-6v-6H7v-6h6z" className="fill-surface" />
    </svg>
  );
}

export function Brand({ subtitle, className = "" }: { subtitle: string; className?: string }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <Logo className="size-11" />
      <div className="flex min-w-0 flex-col gap-0.5 text-left">
        <b className="text-[19px] leading-tight tracking-tight text-pine">Tra cứu y tế</b>
        <span className="truncate text-xs text-muted">{subtitle}</span>
      </div>
    </div>
  );
}

export function Spinner({ label = "Đang tải…" }: { label?: string }) {
  return (
    <p className="typing p-6 text-center text-sm text-muted" role="status">
      {label}
    </p>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger">
      {children}
    </p>
  );
}
