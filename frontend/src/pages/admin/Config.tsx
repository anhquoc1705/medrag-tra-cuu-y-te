import { useEffect, useState, type ReactNode } from "react";
import { api } from "../../api";
import { AnswerCard } from "../../components/AnswerCard";
import { SourcePanel } from "../../components/SourcePanel";
import { Button, ErrorNote, Spinner } from "../../components/ui";
import { CONFIGS, PROVIDERS, dateTime } from "../../labels";
import type { ChatResult, Provider, RagConfig } from "../../types";
import { Panel, PageHead, field, useApi } from "./common";

interface Values {
  chat_config: RagConfig;
  llm_provider: Provider;
  llm_model: string;
  guard_verifier_provider: Provider;
  search_top_k: number;
  translate_query: boolean;
  llm_fallback: boolean;
  guard_faithfulness_threshold: number;
  guard_max_retries: number;
  guard_min_evidence: number;
  guard_prompt_guard_threshold: number;
}
interface Info {
  values: Values;
  defaults: Values;
  updated_at: string | null;
  updated_by: string | null;
}

export function Config() {
  const { data, setData, error, loading } = useApi<Info>("/admin/settings");
  const [form, setForm] = useState<Values | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (data) setForm(data.values);
  }, [data]);

  const set = <K extends keyof Values>(key: K, value: Values[K]) => {
    setForm((f) => (f ? { ...f, [key]: value } : f));
    setMessage(null);
  };
  const dirty = !!form && !!data && JSON.stringify(form) !== JSON.stringify(data.values);

  async function save(path: string, body?: Values) {
    setSaving(true);
    setMessage(null);
    try {
      const info = await api<Info>(path, body ? { method: "PUT", body } : { method: "POST" });
      setData(info);
      setMessage({ ok: true, text: "Đã lưu – áp dụng từ câu hỏi tiếp theo." });
    } catch (e) {
      setMessage({ ok: false, text: (e as Error).message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHead title="Cấu hình hệ thống" sub="Áp dụng cho mọi người dùng từ câu hỏi tiếp theo. Người dùng thường không thấy các lựa chọn này." />
      {error && <ErrorNote>{error}</ErrorNote>}
      {loading && !form && <Spinner />}
      {form && data && (
        <>
          <Panel title="Luồng trả lời">
            <div className="grid grid-cols-2 gap-x-[18px] gap-y-3.5 max-[900px]:grid-cols-1">
              <Field label="Cấu hình" help="Chỉ cấu hình có Guardrails mới cảnh báo cấp cứu và kiểm tra chéo.">
                <select value={form.chat_config} onChange={(e) => set("chat_config", e.target.value as RagConfig)} className={field}>
                  {Object.entries(CONFIGS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                      {k === "hybrid_rag_guard" ? " (đề xuất)" : ""}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Mô hình trả lời" help="Mô hình sinh câu trả lời có trích dẫn.">
                <select
                  value={form.llm_provider}
                  onChange={(e) => {
                    set("llm_provider", e.target.value as Provider);
                    set("llm_model", ""); // dùng mô hình mặc định của nhà cung cấp mới
                  }}
                  className={field}
                >
                  {Object.entries(PROVIDERS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Mô hình kiểm tra chéo" help="Phải khác mô hình trả lời để không “tự chấm bài”.">
                <select value={form.guard_verifier_provider} onChange={(e) => set("guard_verifier_provider", e.target.value as Provider)} className={field}>
                  {Object.entries(PROVIDERS).map(([k, v]) => (
                    <option key={k} value={k} disabled={k === form.llm_provider}>
                      {v}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Số đoạn tài liệu (top-k)">
                <input type="number" min={1} max={10} value={form.search_top_k} onChange={(e) => set("search_top_k", Number(e.target.value))} className={field} />
              </Field>
              <Check checked={form.translate_query} onChange={(v) => set("translate_query", v)}>
                Dịch câu hỏi sang tiếng Anh để tìm BM25 trong tài liệu WHO / MedlinePlus
              </Check>
              <Check checked={form.llm_fallback} onChange={(v) => set("llm_fallback", v)}>
                Tự chuyển sang mô hình dự phòng khi hết hạn mức (Qwen Groq → Qwen Cloudflare)
              </Check>
            </div>
          </Panel>

          <Panel title="Ngưỡng Guardrails">
            <div className="grid grid-cols-2 gap-x-[18px] gap-y-3.5 max-[900px]:grid-cols-1">
              <Field label="Ngưỡng Faithfulness" help="Dưới ngưỡng thì sinh lại, hết lượt thì trả “Không đủ dữ liệu an toàn để tư vấn”.">
                <input type="number" min={0} max={1} step={0.05} value={form.guard_faithfulness_threshold} onChange={(e) => set("guard_faithfulness_threshold", Number(e.target.value))} className={field} />
              </Field>
              <Field label="Số lần sinh lại tối đa">
                <input type="number" min={0} max={5} value={form.guard_max_retries} onChange={(e) => set("guard_max_retries", Number(e.target.value))} className={field} />
              </Field>
              <Field label="Ngưỡng bằng chứng (cosine)" help="Đoạn gần nhất dưới ngưỡng thì từ chối, không gọi LLM.">
                <input type="number" min={0} max={1} step={0.05} value={form.guard_min_evidence} onChange={(e) => set("guard_min_evidence", Number(e.target.value))} className={field} />
              </Field>
              <Field label="Ngưỡng Prompt Guard" help="Điểm lách quy tắc từ ngưỡng này trở lên thì chặn.">
                <input type="number" min={0} max={1} step={0.05} value={form.guard_prompt_guard_threshold} onChange={(e) => set("guard_prompt_guard_threshold", Number(e.target.value))} className={field} />
              </Field>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
              <p className="text-xs text-muted">
                {data.updated_at ? `Lần đổi gần nhất: ${dateTime(data.updated_at)} · ${data.updated_by}` : "Đang dùng giá trị mặc định trong .env"}
              </p>
              <span className="flex gap-2">
                <Button variant="ghost" disabled={saving} onClick={() => window.confirm("Khôi phục toàn bộ về giá trị mặc định trong .env?") && save("/admin/settings/reset")}>
                  Khôi phục mặc định
                </Button>
                <Button variant="ghost" disabled={saving || !dirty} onClick={() => setForm(data.values)}>
                  Huỷ thay đổi
                </Button>
                <Button variant="primary" disabled={saving || !dirty} onClick={() => save("/admin/settings", form)}>
                  {saving ? "Đang lưu…" : "Lưu cấu hình"}
                </Button>
              </span>
            </div>
            {message && (message.ok ? <p className="text-[13px] text-ok">{message.text}</p> : <ErrorNote>{message.text}</ErrorNote>)}
          </Panel>
        </>
      )}
      <Compare />
    </>
  );
}

function Field({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-[13px] font-medium">
      {label}
      {children}
      {help && <small className="text-xs font-normal text-muted">{help}</small>}
    </label>
  );
}

function Check({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="flex items-start gap-2 text-[13px]">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-[3px] accent-pine" />
      {children}
    </label>
  );
}

// Thử nghiệm so sánh: cùng một câu hỏi, 2 cấu hình cạnh nhau (dùng khi demo, không đổi cấu hình của người dùng).
function Compare() {
  const [question, setQuestion] = useState("Bố tôi đang đau ngực dữ dội, vã mồ hôi, phải làm sao?");
  const [a, setA] = useState<RagConfig>("hybrid_rag");
  const [b, setB] = useState<RagConfig>("hybrid_rag_guard");
  const [provider, setProvider] = useState<Provider | "">("");
  const [results, setResults] = useState<ChatResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<{ col: number; n: number } | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    setResults(null);
    setSource(null);
    try {
      setResults(await api<ChatResult[]>("/admin/compare", { body: { question, configs: [a, b], provider: provider || null } }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const openSource = source && results?.[source.col]?.sources.find((s) => s.n === source.n);

  return (
    <Panel title="Thử nghiệm so sánh" sub="Hỏi một câu với 2 cấu hình cạnh nhau – dùng khi demo, không ảnh hưởng người dùng. Mỗi lần chạy tốn hạn mức LLM như 2 câu hỏi.">
      <div className="flex flex-wrap gap-2">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} aria-label="Câu hỏi thử" maxLength={1000} className={`${field} min-w-[220px] flex-1`} />
        <select value={a} onChange={(e) => setA(e.target.value as RagConfig)} aria-label="Cấu hình A" className={field}>
          {Object.entries(CONFIGS).map(([k, v]) => (
            <option key={k} value={k}>
              A: {v}
            </option>
          ))}
        </select>
        <select value={b} onChange={(e) => setB(e.target.value as RagConfig)} aria-label="Cấu hình B" className={field}>
          {Object.entries(CONFIGS).map(([k, v]) => (
            <option key={k} value={k}>
              B: {v}
            </option>
          ))}
        </select>
        <select value={provider} onChange={(e) => setProvider(e.target.value as Provider | "")} aria-label="Mô hình" className={field}>
          <option value="">Mô hình đang cấu hình</option>
          {Object.entries(PROVIDERS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <Button variant="primary" disabled={busy || !question.trim()} onClick={run}>
          {busy ? "Đang chạy…" : "Chạy"}
        </Button>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      {busy && <Spinner label="Đang chạy lần lượt 2 cấu hình…" />}
      {results && (
        <div className="grid grid-cols-2 gap-3 max-[900px]:grid-cols-1">
          {results.map((r, i) => (
            <div key={i} className="flex min-w-0 flex-col gap-2 rounded-lg border border-line p-3 text-[13.5px]">
              <h4 className="text-[13px] font-semibold">
                {i === 0 ? "A" : "B"} · {CONFIGS[r.config]}
              </h4>
              <AnswerCard result={r} showModel activeSource={source?.col === i ? source.n : null} onCite={(n) => setSource({ col: i, n })} />
            </div>
          ))}
        </div>
      )}
      {openSource && (
        <div className="max-h-[420px] overflow-hidden rounded-lg border border-line [&>aside]:border-l-0">
          <SourcePanel source={openSource} onClose={() => setSource(null)} />
        </div>
      )}
    </Panel>
  );
}
