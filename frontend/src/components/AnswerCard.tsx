import type { ComponentProps, ReactNode } from "react";
import Markdown from "react-markdown";
import { decisionInfo, modelName, seconds, score } from "../labels";
import type { ChatResult, Source } from "../types";
import { Chip } from "./ui";

// Một câu trả lời: cảnh báo cấp cứu / từ chối / nội dung có trích dẫn [n] bấm được + thông tin kiểm tra chéo + nguồn.

const CITATION = /\[(\d{1,2})\]/g;

export function sourceLabel(src: Source): string {
  const page = src.page_number ? ` · tr. ${src.page_number}` : "";
  return `${src.issuing_organization} – ${src.title}${page}`;
}

export function EmergencyAlert({ text }: { text?: string | null }) {
  return (
    <div role="alert" className="flex flex-col gap-1.5 rounded-[10px] border-[1.5px] border-danger bg-danger-soft px-4 py-3.5 text-danger">
      <strong className="text-base">Có thể là tình trạng cấp cứu</strong>
      <span>
        {text?.replace(/^⚠️\s*/, "") ??
          "Hãy gọi ngay cấp cứu hoặc đến cơ sở y tế gần nhất. Không tự xử trí tại nhà và không chờ xem triệu chứng có tự hết không."}
      </span>
      <a href="tel:115" className="w-fit font-mono text-[22px] font-medium tracking-wider underline-offset-4 hover:underline">
        115
      </a>
    </div>
  );
}

interface Props {
  result: ChatResult;
  activeSource: number | null;
  onCite: (n: number) => void;
  showModel?: boolean;
}

export function AnswerCard({ result, activeSource, onCite, showModel = false }: Props) {
  const decision = result.guard?.decision ?? (result.refused ? "no_info" : "answered");
  const info = decisionInfo(decision);
  const time = seconds(result.timings?.total_ms);
  const sources = new Map(result.sources.map((s) => [s.n, s]));

  if (result.refused && result.emergency) {
    return (
      <article className="flex flex-col gap-2.5">
        <EmergencyAlert text={result.answer} />
        <Meta>
          <Chip tone="bad">Phát hiện dấu hiệu cấp cứu</Chip>
          <span>{time}</span>
        </Meta>
      </article>
    );
  }

  if (result.refused || decision === "greeting") {
    return (
      <article className="flex flex-col gap-2.5">
        <div className="rounded-[10px] border border-line bg-surface px-3.5 py-3">{result.answer}</div>
        <Meta>
          {info.refusal && <Chip tone={info.tone}>{info.refusal}</Chip>}
          <span>{time}</span>
        </Meta>
      </article>
    );
  }

  const attempts = result.guard?.attempts ?? [];
  const last = [...attempts].reverse().find((a) => a.claims);
  const claims = last?.claims ?? [];
  const supported = claims.filter((c) => c.supported).length;
  const cited = result.sources.filter((s) => result.cited.includes(s.n));
  const markdown = result.answer.replace(CITATION, (m, n) => (sources.has(Number(n)) ? `[${n}](#cite-${n})` : m));

  const components: ComponentProps<typeof Markdown>["components"] = {
    a({ href, children }) {
      const match = href?.match(/^#cite-(\d+)$/);
      if (!match) {
        return (
          <a href={href} target="_blank" rel="noreferrer" className="text-pine underline">
            {children}
          </a>
        );
      }
      const n = Number(match[1]);
      return (
        <button
          type="button"
          onClick={() => onCite(n)}
          aria-pressed={activeSource === n}
          aria-label={`Xem nguồn ${n}`}
          className="ml-0.5 rounded border border-pine bg-pine-soft px-1 align-[1px] font-mono text-[11.5px] text-pine hover:bg-pine hover:text-surface aria-pressed:bg-pine aria-pressed:text-surface"
        >
          {n}
        </button>
      );
    },
  };

  return (
    <article className="flex min-w-0 flex-col gap-2.5">
      {result.emergency_notice && <EmergencyAlert text={result.emergency_notice} />}
      <div className="answer">
        <Markdown components={components}>{markdown}</Markdown>
      </div>
      <Meta>
        {claims.length > 0 && (
          <Chip tone={supported === claims.length ? "ok" : "warn"}>
            Kiểm tra chéo: {supported}/{claims.length} ý có nguồn
          </Chip>
        )}
        {result.guard?.faithfulness != null && <Chip tone="info">Faithfulness {score(result.guard.faithfulness)}</Chip>}
        {attempts.length > 1 && <Chip>Đã sinh lại {attempts.length - 1} lần</Chip>}
        <span>
          {showModel ? `${modelName(result.provider, result.model)} · ` : ""}
          {time}
        </span>
      </Meta>
      {cited.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {cited.map((s) => (
            <button
              key={s.n}
              type="button"
              onClick={() => onCite(s.n)}
              title={sourceLabel(s)}
              className="max-w-full truncate rounded-lg border border-line bg-surface px-2.5 py-1.5 text-left text-[12.5px] hover:bg-user"
            >
              <b className="mr-1 font-mono font-medium text-pine">[{s.n}]</b>
              {sourceLabel(s)}
            </button>
          ))}
        </div>
      )}
      <p className="border-t border-dashed border-line pt-2 text-xs text-muted">{result.disclaimer}</p>
    </article>
  );
}

function Meta({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">{children}</div>;
}
