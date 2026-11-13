import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { Button, Chip, ErrorNote, Spinner } from "../../components/ui";
import { CONFIGS, DECISIONS, dateTime, decisionInfo, modelName, score, secondsShort } from "../../labels";
import type { Attempt, Guard } from "../../types";
import { Panel, PageHead, field, td, tdNum, th, useApi } from "./common";

interface LogItem {
  id: number;
  created_at: string;
  user: string | null;
  question: string;
  config: string;
  model: string;
  decision: string;
  faithfulness: number | null;
  first_faithfulness: number | null;
  attempts: number | null;
  total_ms: number;
}

interface LogDetail extends Omit<LogItem, "attempts" | "first_faithfulness"> {
  provider: string;
  cited_chunks: string[];
  details: {
    guard?: Guard & { input?: { signals?: Signals } };
    timings?: Record<string, number>;
    translated_query?: string | null;
    llm_calls?: string[];
  };
}

interface Signals {
  emergency_keywords?: string[];
  prompt_guard?: { original: number | null; english: number | null };
  classifier?: { label: string; reason: string };
}

const PAGE = 25;

export function Logs() {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [decision, setDecision] = useState("");
  const [who, setWho] = useState("all");
  const [offset, setOffset] = useState(0);
  const [openId, setOpenId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(q.trim());
      setOffset(0);
    }, 350);
    return () => clearTimeout(t);
  }, [q]);

  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset), who });
  if (query) params.set("q", query);
  if (decision) params.set("decision", decision);
  const { data, error, loading, reload } = useApi<{ total: number; items: LogItem[] }>(`/admin/logs?${params}`);

  // đổi trang / bộ lọc thì bỏ chọn, để không xoá nhầm dòng đang không nhìn thấy
  useEffect(() => setSelected(new Set()), [query, decision, who, offset]);

  const pageIds = data?.items.map((r) => r.id) ?? [];
  const allChecked = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  const toggle = (id: number) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  async function deleteLogs(ids: number[]) {
    const what = ids.length === 1 ? "câu hỏi này" : `${ids.length} câu hỏi đã chọn`;
    if (!window.confirm(`Xoá vĩnh viễn ${what}?\n\nCâu hỏi, câu trả lời và chi tiết Guardrails sẽ bị xoá khỏi thống kê và khỏi lịch sử của người hỏi. Không thể hoàn tác.`)) return;
    setDeleting(true);
    setNotice(null);
    try {
      const r = await api<{ logs: number; messages: number; conversations: number }>("/admin/logs/delete", { body: { ids } });
      setNotice({
        ok: true,
        text: `Đã xoá ${r.logs} câu hỏi` + (r.messages ? `, ${r.messages} câu trong lịch sử người dùng` : "") + (r.conversations ? `, ${r.conversations} cuộc hỏi đáp trống` : "") + ".",
      });
      setSelected(new Set());
      setOpenId(null);
      if (data && offset > 0 && ids.length >= data.items.length) setOffset(Math.max(0, offset - PAGE));
      else reload();
    } catch (e) {
      setNotice({ ok: false, text: (e as Error).message });
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <PageHead title="Hội thoại" sub="Mọi câu hỏi đều được ghi để theo dõi chất lượng; câu của khách ghi ẩn danh. Bấm một dòng để xem chi tiết Guardrails." />
      <Panel>
        <div className="flex flex-wrap gap-2">
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm trong câu hỏi…" aria-label="Tìm câu hỏi" className={`${field} min-w-[180px] flex-1`} />
          <select
            value={decision}
            onChange={(e) => {
              setDecision(e.target.value);
              setOffset(0);
            }}
            aria-label="Lọc quyết định"
            className={field}
          >
            <option value="">Mọi quyết định</option>
            {Object.entries(DECISIONS).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </select>
          <select
            value={who}
            onChange={(e) => {
              setWho(e.target.value);
              setOffset(0);
            }}
            aria-label="Lọc người hỏi"
            className={field}
          >
            <option value="all">Mọi người hỏi</option>
            <option value="user">Đã đăng nhập</option>
            <option value="guest">Khách</option>
          </select>
        </div>
        {selected.size > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger">
            <span>Đã chọn {selected.size} câu hỏi</span>
            <span className="flex gap-2">
              <Button variant="ghost" onClick={() => setSelected(new Set())}>
                Bỏ chọn
              </Button>
              <Button variant="danger" disabled={deleting} onClick={() => deleteLogs([...selected])}>
                {deleting ? "Đang xoá…" : `Xoá ${selected.size} câu đã chọn`}
              </Button>
            </span>
          </div>
        )}
        {notice && (notice.ok ? <p className="text-[13px] text-ok">{notice.text}</p> : <ErrorNote>{notice.text}</ErrorNote>)}
        {error && <ErrorNote>{error}</ErrorNote>}
        {loading && !data && <Spinner />}
        {data && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] border-collapse text-[13px]">
                <thead>
                  <tr>
                    <th className={`${th} w-8`}>
                      <input
                        type="checkbox"
                        aria-label="Chọn tất cả trong trang"
                        checked={allChecked}
                        onChange={() => setSelected(allChecked ? new Set() : new Set(pageIds))}
                        className="accent-pine"
                      />
                    </th>
                    <th className={th}>Thời gian</th>
                    <th className={th}>Người hỏi</th>
                    <th className={th}>Câu hỏi</th>
                    <th className={th}>Quyết định</th>
                    <th className={th}>Faithfulness</th>
                    <th className={th}>Lần sinh</th>
                    <th className={th}>Xử lý</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r) => {
                    const info = decisionInfo(r.decision);
                    return (
                      <tr key={r.id} onClick={() => setOpenId(r.id)} className={`cursor-pointer hover:bg-user ${selected.has(r.id) ? "bg-danger-soft" : ""}`}>
                        <td className={td} onClick={(e) => e.stopPropagation()}>
                          <input type="checkbox" aria-label={`Chọn câu hỏi ${r.id}`} checked={selected.has(r.id)} onChange={() => toggle(r.id)} className="accent-pine" />
                        </td>
                        <td className={tdNum}>{dateTime(r.created_at)}</td>
                        <td className={`${td} max-w-[140px] truncate`} title={r.user ?? "Khách"}>
                          {r.user ?? <span className="text-muted">Khách</span>}
                        </td>
                        <td className={td}>
                          <button type="button" className="text-left hover:underline" onClick={() => setOpenId(r.id)}>
                            {r.question}
                          </button>
                        </td>
                        <td className={td}>
                          <Chip tone={info.tone}>{info.label}</Chip>
                        </td>
                        <td className={tdNum}>
                          {r.first_faithfulness != null && r.faithfulness != null && r.first_faithfulness !== r.faithfulness
                            ? `${score(r.first_faithfulness)} → ${score(r.faithfulness)}`
                            : score(r.faithfulness)}
                        </td>
                        <td className={tdNum}>{r.attempts ?? "–"}</td>
                        <td className={tdNum}>{secondsShort(r.total_ms)}</td>
                      </tr>
                    );
                  })}
                  {!data.items.length && (
                    <tr>
                      <td colSpan={8} className={`${td} text-center text-muted`}>
                        Không có hội thoại nào khớp bộ lọc.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between gap-2 text-[13px] text-muted">
              <span>
                {data.total ? `${offset + 1}–${Math.min(offset + PAGE, data.total)} / ${data.total}` : "0"} hội thoại
              </span>
              <span className="flex gap-2">
                <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="rounded-lg border border-line px-3 py-1 disabled:opacity-40">
                  ← Trước
                </button>
                <button type="button" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)} className="rounded-lg border border-line px-3 py-1 disabled:opacity-40">
                  Sau →
                </button>
              </span>
            </div>
          </>
        )}
      </Panel>
      <LogDialog id={openId} onClose={() => setOpenId(null)} onDelete={(id) => deleteLogs([id])} deleting={deleting} />
    </>
  );
}

function LogDialog({ id, onClose, onDelete, deleting }: { id: number | null; onClose: () => void; onDelete: (id: number) => void; deleting: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const { data, error, loading } = useApi<LogDetail>(id ? `/admin/logs/${id}` : null);

  useEffect(() => {
    const dlg = ref.current;
    if (id && dlg && !dlg.open) dlg.showModal();
    if (!id && dlg?.open) dlg.close();
  }, [id]);

  const guard = data?.details.guard;
  const signals = guard?.input?.signals;
  const info = decisionInfo(data?.decision);

  return (
    <dialog ref={ref} onClose={onClose} aria-label="Chi tiết hội thoại" className="m-auto max-h-[90vh] w-[min(760px,calc(100%-32px))] rounded-[14px] bg-surface p-0 text-ink shadow-2xl">
      <div className="flex flex-col gap-4 p-6 max-sm:p-4">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold">{data?.question ?? "Chi tiết hội thoại"}</h2>
          <button type="button" onClick={onClose} aria-label="Đóng" className="text-xl leading-none text-muted">
            ×
          </button>
        </div>
        {error && <ErrorNote>{error}</ErrorNote>}
        {loading && <Spinner />}
        {data && !loading && (
          <>
            <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
              <Chip tone={info.tone}>{info.label}</Chip>
              <span>
                {dateTime(data.created_at)} · {data.user ?? "Khách"} · {CONFIGS[data.config] ?? data.config} · {modelName(data.provider, data.model)} · {secondsShort(data.total_ms)}
              </span>
            </div>
            {data.details.translated_query && (
              <p className="text-[13px]">
                <span className="text-muted">Bản dịch cho BM25: </span>
                <i>{data.details.translated_query}</i>
              </p>
            )}

            {guard && (
              <section className="flex flex-col gap-2 rounded-[10px] border border-line p-3.5">
                <h3 className="text-sm font-semibold">G1 · Kiểm tra đầu vào</h3>
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[13px]">
                  <dt className="text-muted">Bộ phân loại</dt>
                  <dd>
                    {signals?.classifier?.label ?? "–"}
                    {signals?.classifier?.reason && <span className="text-muted"> – {signals.classifier.reason}</span>}
                  </dd>
                  <dt className="text-muted">Prompt Guard</dt>
                  <dd className="font-mono text-xs">
                    gốc {score(signals?.prompt_guard?.original)} · tiếng Anh {score(signals?.prompt_guard?.english)}
                  </dd>
                  <dt className="text-muted">Từ khoá cấp cứu</dt>
                  <dd>{signals?.emergency_keywords?.length ? signals.emergency_keywords.join(", ") : "không có"}</dd>
                </dl>
                {guard.evidence && (
                  <>
                    <h3 className="mt-2 text-sm font-semibold">G2 · Bằng chứng</h3>
                    <p className="text-[13px]">
                      Cosine cao nhất <b className="font-mono">{score(guard.evidence.best_vector_score)}</b> (ngưỡng {score(guard.evidence.threshold)}) –{" "}
                      {guard.evidence.ok ? "đủ" : "không đủ"}
                    </p>
                  </>
                )}
                {!!guard.attempts?.length && (
                  <>
                    <h3 className="mt-2 text-sm font-semibold">G3 · Kiểm tra chéo từng lần sinh</h3>
                    {guard.attempts.map((a) => (
                      <AttemptView key={a.attempt} attempt={a} />
                    ))}
                  </>
                )}
              </section>
            )}

            {data.details.timings && (
              <p className="font-mono text-xs text-muted">
                {Object.entries(data.details.timings)
                  .map(([k, v]) => `${k.replace(/_ms/, "")} ${secondsShort(v)}`)
                  .join(" · ")}
              </p>
            )}
            {!!data.details.llm_calls?.length && <p className="font-mono text-xs break-all text-muted">LLM: {data.details.llm_calls.join(", ")}</p>}
            <div className="flex justify-end border-t border-line pt-3">
              <Button variant="danger" disabled={deleting} onClick={() => onDelete(data.id)}>
                {deleting ? "Đang xoá…" : "Xoá câu hỏi này"}
              </Button>
            </div>
          </>
        )}
      </div>
    </dialog>
  );
}

function AttemptView({ attempt }: { attempt: Attempt }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-lg bg-paper p-3 text-[13px]">
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
        <b className="text-ink">Lần {attempt.attempt}</b>
        {attempt.no_info && <Chip>LLM trả lời: tài liệu không có thông tin</Chip>}
        {attempt.infra_error && <Chip tone="warn">Lỗi dịch vụ kiểm tra chéo</Chip>}
        {attempt.faithfulness != null && <Chip tone={attempt.faithfulness >= 0.8 ? "ok" : "warn"}>Faithfulness {score(attempt.faithfulness)}</Chip>}
      </div>
      {attempt.claims?.map((c, i) => (
        <div key={i} className="flex gap-2">
          <span aria-label={c.supported ? "có nguồn" : "không có nguồn"} className={c.supported ? "text-ok" : "text-danger"}>
            {c.supported ? "✓" : "✗"}
          </span>
          <span className="min-w-0">
            {c.text}
            {c.reason && <span className="block text-xs text-muted">{c.reason}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}
