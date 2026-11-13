import { useState } from "react";
import { ErrorNote, Spinner } from "../../components/ui";
import { decisionInfo, percent, score, secondsShort } from "../../labels";
import { BarRow, Panel, PageHead, Tile, field, useApi } from "./common";

interface Stats {
  days: number;
  questions: number;
  answered: number;
  guest_questions: number;
  users: number;
  faithfulness_avg: number | null;
  latency_avg_ms: number | null;
  latency_p95_ms: number | null;
  decisions: Record<string, number>;
  top_documents: { document_id: string; title: string; count: number }[];
}

export function Overview() {
  const [days, setDays] = useState(7);
  const { data, error, loading } = useApi<Stats>(`/admin/stats?days=${days}`);
  const maxDoc = Math.max(0, ...(data?.top_documents.map((d) => d.count) ?? []));

  return (
    <>
      <PageHead title="Tổng quan hoạt động" sub="Đọc từ bảng chat_logs – gồm cả câu hỏi của khách (ghi ẩn danh).">
        <label className="flex items-center gap-2 text-[13px] text-muted">
          Khoảng thời gian
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} className={field}>
            <option value={1}>Hôm nay</option>
            <option value={7}>7 ngày</option>
            <option value={30}>30 ngày</option>
            <option value={365}>1 năm</option>
          </select>
        </label>
      </PageHead>
      {error && <ErrorNote>{error}</ErrorNote>}
      {loading && !data && <Spinner />}
      {data && (
        <>
          <div className="grid grid-cols-4 gap-3 max-[900px]:grid-cols-2">
            <Tile label="Câu hỏi" value={String(data.questions)} note={`khách ${data.guest_questions} · ${data.users} tài khoản`} />
            <Tile label="Được trả lời" value={percent(data.answered, data.questions)} note={`${data.answered} câu`} />
            <Tile label="Faithfulness TB" value={score(data.faithfulness_avg)} note="trên các câu có kiểm tra chéo" />
            <Tile label="Độ trễ p95" value={secondsShort(data.latency_p95_ms)} note={`trung bình ${secondsShort(data.latency_avg_ms)} · mục tiêu ≤ 10 s`} />
          </div>
          <div className="grid grid-cols-2 gap-3 max-[900px]:grid-cols-1">
            <Panel title="Quyết định của Guardrails">
              {Object.keys(data.decisions).length ? (
                <div className="flex flex-col gap-2">
                  {Object.entries(data.decisions).map(([d, n]) => {
                    const info = decisionInfo(d);
                    return <BarRow key={d} label={info.label} value={n} max={data.questions} tone={info.tone} />;
                  })}
                </div>
              ) : (
                <p className="text-sm text-muted">Chưa có câu hỏi nào trong khoảng này.</p>
              )}
            </Panel>
            <Panel title="Tài liệu được trích dẫn nhiều nhất">
              {data.top_documents.length ? (
                <div className="flex flex-col gap-2">
                  {data.top_documents.map((d) => (
                    <BarRow key={d.document_id} label={d.title} title={`${d.document_id} – ${d.title}`} value={d.count} max={maxDoc} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted">Chưa có trích dẫn nào.</p>
              )}
            </Panel>
          </div>
        </>
      )}
    </>
  );
}
