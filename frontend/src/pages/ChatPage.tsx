import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { api, isNativeApp, serverStore } from "../api";
import { useAuth } from "../auth";
import { AnswerCard } from "../components/AnswerCard";
import { LoginDialog } from "../components/LoginDialog";
import { SourcePanel } from "../components/SourcePanel";
import { Avatar, Brand, Button, ChatIcon, ErrorNote, LogoutButton, Spinner } from "../components/ui";
import type { ChatResult, Turn } from "../types";

// Trang hỏi đáp.
// - Khách: các cuộc trò chuyện chỉ giữ trong sessionStorage của tab – đóng tab / thoát là mất, không gửi lên máy chủ để lưu.
// - Đã đăng nhập: danh sách và nội dung lấy từ /conversations (máy chủ lưu khi gọi /chat).

interface Conv {
  id: string; // khoá phía giao diện
  title: string;
  serverId?: number; // id trên máy chủ (chỉ khi đã đăng nhập)
}

const GUEST_KEY = "medrag.guest";
const EXAMPLES = [
  "Người tăng huyết áp nên ăn bao nhiêu muối mỗi ngày?",
  "Mục tiêu HbA1c ở người đái tháo đường típ 2 là bao nhiêu?",
  "Hen phế quản có những triệu chứng nào?",
  "Làm thế nào để phòng ngừa viêm gan B?",
];
const newId = () => Math.random().toString(36).slice(2, 10);

function loadGuest(): { convs: Conv[]; turns: Record<string, Turn[]> } {
  try {
    const raw = sessionStorage.getItem(GUEST_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* bộ nhớ bị chặn → bắt đầu trống */
  }
  return { convs: [], turns: {} };
}
function saveGuest(data: { convs: Conv[]; turns: Record<string, Turn[]> } | null) {
  try {
    if (data) sessionStorage.setItem(GUEST_KEY, JSON.stringify(data));
    else sessionStorage.removeItem(GUEST_KEY);
  } catch {
    /* bỏ qua */
  }
}

// Nhãn trạng thái lưu ở thanh trên cùng: đã đăng nhập (✓ xanh) / khách (! cam).
function SavePill({ saved }: { saved: boolean }) {
  return (
    <span className="flex flex-none items-center gap-2 rounded-full border border-line bg-surface py-1.5 pl-2 pr-3.5 text-[13.5px] shadow-sm">
      <svg viewBox="0 0 20 20" aria-hidden="true" className={`size-5 ${saved ? "text-pine" : "text-warn"}`}>
        <circle cx="10" cy="10" r="9" className="fill-current" />
        {saved ? (
          <path d="M6 10.2l2.6 2.6L14 7.4" className="fill-none stroke-surface" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        ) : (
          <path d="M10 5.5v5.5M10 13.8v.2" className="fill-none stroke-surface" strokeWidth={2} strokeLinecap="round" />
        )}
      </svg>
      {saved ? "Đã lưu vào lịch sử" : "Chế độ khách · không lưu"}
    </span>
  );
}

export function ChatPage() {
  const { user, loading, signOut } = useAuth();
  const [convs, setConvs] = useState<Conv[]>([]);
  const [turns, setTurns] = useState<Record<string, Turn[]>>({});
  const [activeId, setActiveId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [source, setSource] = useState<{ turnId: string; n: number } | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [loadingConv, setLoadingConv] = useState(false);
  const [draft, setDraft] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const [menuOpen, setMenuOpen] = useState(false); // menu trượt trên màn hình hẹp
  const narrow = window.matchMedia("(max-width: 900px)").matches; // gợi ý ngắn trong ô nhập để không bị xuống dòng
  const threadEnd = useRef<HTMLDivElement>(null);

  // Danh sách bệnh hệ thống hỗ trợ – lấy từ backend (data/catalog/topics.csv), không viết cứng ở giao diện.
  useEffect(() => {
    api<{ topics: string[] }>("/topics")
      .then((r) => setTopics(r.topics))
      .catch(() => setTopics([]));
  }, []);

  // Đổi trạng thái đăng nhập → nạp lại danh sách tương ứng.
  useEffect(() => {
    if (loading) return;
    setActiveId(null);
    setSource(null);
    if (!user) {
      const guest = loadGuest();
      setConvs(guest.convs);
      setTurns(guest.turns);
      return;
    }
    saveGuest(null); // đăng nhập rồi thì bỏ các cuộc tạm của khách
    setConvs([]);
    setTurns({});
    setListError(null);
    api<{ id: number; title: string }[]>("/conversations")
      .then((rows) => setConvs(rows.map((r) => ({ id: `s${r.id}`, title: r.title, serverId: r.id }))))
      .catch((e: Error) => setListError(e.message));
  }, [user, loading]);

  // Khách: lưu tạm vào sessionStorage (chỉ các lượt đã có kết quả).
  useEffect(() => {
    if (loading || user) return;
    const done = Object.fromEntries(Object.entries(turns).map(([k, v]) => [k, v.filter((t) => t.result)]));
    saveGuest({ convs: convs.filter((c) => done[c.id]?.length), turns: done });
  }, [convs, turns, user, loading]);

  // App Android – nút Back: đóng lần lượt ngăn nguồn → menu → hộp đăng nhập; không còn gì để đóng thì thoát app.
  const backState = useRef({ source, menuOpen, loginOpen });
  backState.current = { source, menuOpen, loginOpen };
  useEffect(() => {
    const previous = window.medragBack;
    window.medragBack = () => {
      const s = backState.current;
      if (s.source) setSource(null);
      else if (s.menuOpen) setMenuOpen(false);
      else if (s.loginOpen) setLoginOpen(false);
      else return false;
      return true;
    };
    return () => {
      window.medragBack = previous;
    };
  }, []);

  const activeTurns = useMemo(() => (activeId ? turns[activeId] ?? [] : []), [activeId, turns]);
  const activeConv = convs.find((c) => c.id === activeId);

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeTurns.length, pending]);

  const openConv = useCallback(
    (conv: Conv) => {
      setActiveId(conv.id);
      setSource(null);
      if (!user || !conv.serverId || turns[conv.id]) return;
      setLoadingConv(true);
      api<{ messages: { id: number; question: string; result: ChatResult }[] }>(`/conversations/${conv.serverId}`)
        .then((r) => setTurns((t) => ({ ...t, [conv.id]: r.messages.map((m) => ({ id: `m${m.id}`, question: m.question, result: m.result })) })))
        .catch((e: Error) => setTurns((t) => ({ ...t, [conv.id]: [{ id: newId(), question: conv.title, error: e.message }] })))
        .finally(() => setLoadingConv(false));
    },
    [user, turns],
  );

  async function deleteConv(conv: Conv) {
    if (!window.confirm(`Xoá cuộc hỏi đáp “${conv.title}”?`)) return;
    try {
      if (user && conv.serverId) await api(`/conversations/${conv.serverId}`, { method: "DELETE" });
      setConvs((cs) => cs.filter((c) => c.id !== conv.id));
      if (activeId === conv.id) setActiveId(null);
    } catch (e) {
      window.alert((e as Error).message);
    }
  }

  async function send(question: string) {
    question = question.trim();
    if (!question || pending) return;
    let conv = activeConv;
    if (!conv) {
      conv = { id: newId(), title: question.slice(0, 200) };
      const created = conv;
      setConvs((cs) => [created, ...cs]);
      setActiveId(created.id);
    }
    const convId = conv.id;
    const turnId = newId();
    const update = (patch: Partial<Turn>) =>
      setTurns((t) => ({ ...t, [convId]: (t[convId] ?? []).map((x) => (x.id === turnId ? { ...x, ...patch } : x)) }));
    setTurns((t) => ({ ...t, [convId]: [...(t[convId] ?? []), { id: turnId, question }] }));
    setDraft("");
    setPending(true);
    try {
      const result = await api<ChatResult>("/chat", { body: { question, conversation_id: conv.serverId ?? null } });
      update({ result });
      setConvs((cs) => {
        const current = cs.find((c) => c.id === convId);
        if (!current) return cs;
        const moved = { ...current, serverId: current.serverId ?? result.conversation_id };
        return [moved, ...cs.filter((c) => c.id !== convId)];
      });
    } catch (e) {
      update({ error: (e as Error).message });
    } finally {
      setPending(false);
    }
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send(draft);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(draft);
    }
  };

  const openSource = source && activeTurns.find((t) => t.id === source.turnId)?.result?.sources.find((s) => s.n === source.n);

  // App Android: đổi địa chỉ backend ngay trong app (vd. sau khi đưa lên đám mây), không cần build lại.
  function changeServer() {
    const value = window.prompt("Địa chỉ máy chủ (backend), ví dụ https://ten-may-chu.duckdns.org\nĐể trống = dùng địa chỉ mặc định.", serverStore.get());
    if (value === null) return;
    try {
      serverStore.set(value);
      window.location.reload();
    } catch {
      window.alert("Địa chỉ không hợp lệ.");
    }
  }

  return (
    // Màn hình hẹp (điện thoại, app Android): thanh trái thành menu trượt (nút ☰), ngăn nguồn thành cửa sổ trượt từ dưới lên.
    <div className={`grid h-full max-[900px]:grid-cols-1 ${openSource ? "grid-cols-[264px_minmax(0,1fr)_360px]" : "grid-cols-[264px_minmax(0,1fr)]"}`}>
      {(menuOpen || openSource) && (
        <div
          aria-hidden="true"
          onClick={() => {
            setMenuOpen(false);
            setSource(null);
          }}
          className="fixed inset-0 z-30 bg-black/40 min-[901px]:hidden"
        />
      )}
      {/* thanh trái */}
      <nav
        aria-label="Điều hướng"
        className={`flex min-h-0 min-w-0 flex-col gap-5 border-r border-line bg-surface px-4 pt-6 max-[900px]:fixed max-[900px]:inset-y-0 max-[900px]:left-0 max-[900px]:z-40 max-[900px]:w-[min(300px,85vw)] max-[900px]:shadow-2xl max-[900px]:transition-[translate,visibility] ${menuOpen ? "" : "max-[900px]:invisible max-[900px]:-translate-x-full"}`}
      >
        <Brand subtitle="Trợ lý thông tin y tế" />
        <button
          type="button"
          onClick={() => {
            setActiveId(null);
            setSource(null);
            setMenuOpen(false);
          }}
          className="flex items-center justify-center gap-2 rounded-xl border border-pine/30 bg-pine-soft px-3 py-3 text-[15px] font-semibold text-pine hover:border-pine"
        >
          <span aria-hidden="true" className="text-xl leading-none">
            +
          </span>
          Cuộc hỏi đáp mới
        </button>

        <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-auto">
          <h3 className="mb-1 ml-1 text-xs font-semibold uppercase tracking-[0.08em] text-muted">{user ? "Lịch sử" : "Cuộc trò chuyện"}</h3>
          {listError && <ErrorNote>{listError}</ErrorNote>}
          {convs.map((c) => (
            <div
              key={c.id}
              className={`group flex items-center rounded-lg border ${c.id === activeId ? "border-line bg-paper" : "border-transparent hover:bg-paper"}`}
            >
              <button
                type="button"
                title={c.title}
                aria-current={c.id === activeId}
                onClick={() => {
                  openConv(c);
                  setMenuOpen(false);
                }}
                className="flex min-w-0 flex-1 items-center gap-2.5 px-2.5 py-2 text-left text-[14px]"
              >
                <ChatIcon className="size-[18px] text-muted" />
                <span className="truncate">{c.title}</span>
              </button>
              <button
                type="button"
                aria-label={`Xoá “${c.title}”`}
                onClick={() => deleteConv(c)}
                className="px-2 text-muted opacity-0 hover:text-danger focus-visible:opacity-100 group-hover:opacity-100 max-[900px]:px-3 max-[900px]:text-lg max-[900px]:opacity-100"
              >
                ×
              </button>
            </div>
          ))}
          {!convs.length && !listError && <p className="px-1 text-[13px] text-muted">Chưa có cuộc hỏi đáp nào.</p>}
        </div>

        {user?.role === "admin" && (
          <Link
            to="/admin"
            className="flex items-center justify-between gap-2 rounded-lg border border-pine bg-pine-soft px-3 py-2 text-[13.5px] font-semibold text-pine hover:bg-pine hover:text-surface"
          >
            <span className="flex items-center gap-2">
              <svg viewBox="0 0 20 20" aria-hidden="true" className="size-4 fill-current">
                <path d="M3 3h6v6H3zM11 3h6v4h-6zM11 9h6v8h-6zM3 11h6v6H3z" />
              </svg>
              Trang quản trị
            </span>
            <span aria-hidden="true">→</span>
          </Link>
        )}
        {isNativeApp && (
          <button type="button" onClick={changeServer} className="-mb-2 min-w-0 text-left text-[12.5px] text-muted">
            Máy chủ: <span className="break-all font-mono">{serverStore.get().replace(/^https?:\/\//, "")}</span> · <u>Đổi</u>
          </button>
        )}
        <div className="-mx-4 flex min-w-0 items-center gap-3 border-t border-line px-4 py-4">
          {user ? (
            <>
              <Avatar name={user.name} />
              <div className="flex min-w-0 flex-1 flex-col gap-0.5 leading-tight">
                <b className="truncate text-[14px] font-semibold">{user.name}</b>
                <span className="truncate text-xs text-muted">{user.email}</span>
              </div>
              <LogoutButton onClick={signOut} />
            </>
          ) : (
            <>
              <Avatar name="" guest />
              <div className="flex min-w-0 flex-1 flex-col gap-0.5 leading-tight">
                <b className="text-[14px] font-semibold">Khách</b>
                <span className="truncate text-xs text-muted">Chưa đăng nhập</span>
              </div>
              <Button variant="primary" onClick={() => setLoginOpen(true)} disabled={loading}>
                Đăng nhập
              </Button>
            </>
          )}
        </div>
      </nav>

      {/* khung hỏi đáp */}
      <main className="flex min-h-0 min-w-0 flex-col">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line bg-paper px-7 py-3.5 max-[900px]:px-4">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              aria-label="Mở menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}
              className="-ml-1.5 rounded-lg p-1.5 text-ink hover:bg-user min-[901px]:hidden"
            >
              <svg viewBox="0 0 20 20" aria-hidden="true" className="size-6 fill-none stroke-current" strokeWidth={1.8} strokeLinecap="round">
                <path d="M3.5 5.5h13M3.5 10h13M3.5 14.5h13" />
              </svg>
            </button>
            <h1 className="min-w-0 truncate text-lg font-semibold tracking-tight">{activeConv?.title ?? "Cuộc hỏi đáp mới"}</h1>
          </div>
          {!loading && <SavePill saved={!!user} />}
        </div>

        <div className="flex-1 overflow-auto px-6 py-6 max-[900px]:px-4">
          <div className="mx-auto flex max-w-[720px] flex-col gap-[22px]">
            {loadingConv && <Spinner />}
            {!activeTurns.length && !loadingConv && (
              <div className="flex flex-col gap-4 py-10">
                <h2 className="text-2xl font-semibold tracking-tight text-balance">Bạn muốn tìm hiểu điều gì về sức khoẻ?</h2>
                <p className="text-sm text-muted">Câu trả lời tổng hợp từ tài liệu của Bộ Y tế, WHO, MedlinePlus và Hội Tim mạch Việt Nam, kèm số trích dẫn để đối chiếu.</p>
                {topics.length > 0 && (
                  <details className="rounded-[10px] border border-line bg-surface px-3.5 py-2.5 text-sm">
                    <summary className="cursor-pointer font-medium">Hệ thống hỗ trợ {topics.length} bệnh ở người trưởng thành – xem danh sách</summary>
                    <ul className="mt-2 flex flex-wrap gap-1.5">
                      {topics.map((t) => (
                        <li key={t} className="rounded-full bg-user px-2.5 py-0.5 text-[13px]">
                          {t}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                <div className="grid gap-2 sm:grid-cols-2">
                  {EXAMPLES.map((q) => (
                    <button key={q} type="button" onClick={() => send(q)} disabled={pending} className="rounded-[10px] border border-line bg-surface px-3.5 py-3 text-left text-sm hover:bg-user">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {activeTurns.map((t) => (
              <div key={t.id} className="flex flex-col gap-[22px]">
                <div className="max-w-[80%] self-end whitespace-pre-wrap rounded-[14px_14px_4px_14px] bg-user px-3.5 py-2.5">{t.question}</div>
                {t.result ? (
                  <AnswerCard
                    result={t.result}
                    activeSource={source?.turnId === t.id ? source.n : null}
                    onCite={(n) => setSource({ turnId: t.id, n })}
                  />
                ) : t.error ? (
                  <div className="flex flex-col items-start gap-2">
                    <ErrorNote>{t.error}</ErrorNote>
                    <Button onClick={() => send(t.question)} disabled={pending}>
                      Thử lại
                    </Button>
                  </div>
                ) : (
                  <p className="typing text-sm text-muted" role="status">
                    Đang tra cứu tài liệu và kiểm tra chéo câu trả lời<span>.</span>
                    <span>.</span>
                    <span>.</span>
                  </p>
                )}
              </div>
            ))}
            <div ref={threadEnd} />
          </div>
        </div>

        <div className="border-t border-line bg-surface px-6 py-3.5 max-[900px]:px-4">
          <form onSubmit={onSubmit} className="mx-auto flex max-w-[720px] gap-2">
            <textarea
              aria-label="Câu hỏi"
              placeholder={narrow ? "Hỏi về một bệnh…" : "Hỏi về một bệnh, ví dụ: tiểu đường, huyết áp, hen, viêm gan…"}
              maxLength={1000}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              className="h-[46px] min-w-0 flex-1 resize-none rounded-[10px] border border-line bg-paper px-3 py-2.5 text-ink placeholder:text-muted focus:border-pine focus:outline-none"
            />
            <button type="submit" disabled={pending || !draft.trim()} className="rounded-[10px] bg-pine px-[18px] font-semibold text-surface disabled:opacity-50">
              Gửi
            </button>
          </form>
          <p className="mx-auto mt-1.5 max-w-[720px] text-[11.5px] text-muted">
            Câu trả lời dựa trên tài liệu của Bộ Y tế, WHO, MedlinePlus và Hội Tim mạch Việt Nam. Bấm số trong ô vuông để xem đoạn gốc.
          </p>
        </div>
      </main>

      {openSource && <SourcePanel source={openSource} onClose={() => setSource(null)} />}

      <LoginDialog open={loginOpen} onClose={() => setLoginOpen(false)} />
    </div>
  );
}
