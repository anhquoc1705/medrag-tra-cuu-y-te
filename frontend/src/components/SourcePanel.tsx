import type { Source } from "../types";

// Ngăn tài liệu nguồn: mở khi bấm số trích dẫn – thông tin văn bản + đoạn gốc mà LLM đã dùng.

export function SourcePanel({ source, onClose }: { source: Source; onClose: () => void }) {
  const pages = source.page_number
    ? source.page_end && source.page_end !== source.page_number
      ? `${source.page_number}–${source.page_end}`
      : String(source.page_number)
    : "–";
  return (
    // Màn hình hẹp: cửa sổ trượt từ dưới lên, chiếm tối đa 75% chiều cao (lớp nền mờ do ChatPage vẽ).
    <aside
      aria-label="Tài liệu nguồn"
      className="flex min-h-0 min-w-0 flex-col border-l border-line bg-surface max-[900px]:fixed max-[900px]:inset-x-0 max-[900px]:bottom-0 max-[900px]:z-40 max-[900px]:max-h-[75%] max-[900px]:rounded-t-2xl max-[900px]:border-l-0 max-[900px]:shadow-2xl"
    >
      <header className="flex items-start justify-between gap-2 border-b border-line px-[18px] py-4">
        <div className="min-w-0">
          <small className="block text-[11px] uppercase tracking-[0.08em] text-muted">Nguồn [{source.n}]</small>
          <h2 className="mt-0.5 text-[15px] font-semibold text-balance break-words">{source.title}</h2>
        </div>
        <button type="button" onClick={onClose} aria-label="Đóng" className="text-xl leading-none text-muted">
          ×
        </button>
      </header>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-line px-[18px] py-3.5 text-[13px]">
        <dt className="text-muted">Cơ quan</dt>
        <dd className="min-w-0 break-words">{source.issuing_organization}</dd>
        <dt className="text-muted">Mã tài liệu</dt>
        <dd className="min-w-0 break-all font-mono text-xs">{source.document_id}</dd>
        {source.section_title && (
          <>
            <dt className="text-muted">Mục</dt>
            <dd className="min-w-0 break-words">{source.section_title}</dd>
          </>
        )}
        <dt className="text-muted">Trang</dt>
        <dd>{pages}</dd>
        {source.source_url && (
          <>
            <dt className="text-muted">Bản gốc</dt>
            <dd className="min-w-0">
              <a href={source.source_url} target="_blank" rel="noreferrer" className="break-all text-pine underline underline-offset-2">
                Mở tài liệu ↗
              </a>
            </dd>
          </>
        )}
      </dl>
      <div className="min-h-0 overflow-auto whitespace-pre-line px-[18px] py-4 font-serif text-[14.5px] leading-[1.7]">{source.text}</div>
    </aside>
  );
}
