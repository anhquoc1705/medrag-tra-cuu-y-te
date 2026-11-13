import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../../api";
import type { Tone } from "../../labels";

// Thành phần dùng chung cho các trang quản trị.

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!path) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    api<T>(path, { signal: ctrl.signal })
      .then(setData)
      .catch((e: Error) => e.name !== "AbortError" && setError(e.message))
      .finally(() => !ctrl.signal.aborted && setLoading(false));
    return () => ctrl.abort();
  }, [path, tick]);

  return { data, setData, error, loading, reload };
}

export function PageHead({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-xl font-semibold">{title}</h2>
        {sub && <p className="mt-1 text-[12.5px] text-muted">{sub}</p>}
      </div>
      {children}
    </div>
  );
}

export function Panel({ title, sub, children, className = "" }: { title?: string; sub?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`flex min-w-0 flex-col gap-3 rounded-[10px] border border-line bg-surface p-4 ${className}`}>
      {title && <h3 className="text-sm font-semibold">{title}</h3>}
      {sub && <p className="-mt-2 text-[12.5px] text-muted">{sub}</p>}
      {children}
    </section>
  );
}

export function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-[10px] border border-line bg-surface p-3.5">
      <span className="text-xs text-muted">{label}</span>
      <b className="text-[26px] tracking-tight tabular-nums">{value}</b>
      {note && <small className="text-xs text-muted">{note}</small>}
    </div>
  );
}

const FILL: Record<Tone, string> = { ok: "bg-ok", info: "bg-pine", warn: "bg-warn", bad: "bg-danger", plain: "bg-pine" };

export function BarRow({ label, value, max, tone = "info", title }: { label: string; value: number; max: number; tone?: Tone; title?: string }) {
  return (
    <div className="grid grid-cols-[150px_1fr_44px] items-center gap-2.5 text-[13px] max-sm:grid-cols-[110px_1fr_40px]" title={title}>
      <span className="truncate">{label}</span>
      <div className="h-2.5 overflow-hidden rounded-[5px] bg-user">
        <div className={`h-full rounded-[5px] ${FILL[tone]} motion-safe:transition-[width] motion-safe:duration-500`} style={{ width: `${max ? (value / max) * 100 : 0}%` }} />
      </div>
      <span className="text-right text-muted tabular-nums">{value}</span>
    </div>
  );
}

export const th = "border-b border-line px-2.5 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.06em] text-muted";
export const td = "border-b border-line px-2.5 py-2 text-left align-top";
export const tdNum = `${td} whitespace-nowrap font-mono text-xs tabular-nums`;
export const field = "rounded-lg border border-line bg-paper px-2.5 py-1.5 text-sm text-ink focus:border-pine focus:outline-none";
