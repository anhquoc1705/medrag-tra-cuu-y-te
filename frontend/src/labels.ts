// Nhãn tiếng Việt cho quyết định Guardrails, cấu hình và mô hình – dùng chung cho trang hỏi đáp và quản trị.

export type Tone = "ok" | "info" | "warn" | "bad" | "plain";

export const DECISIONS: Record<string, { label: string; refusal: string; tone: Tone }> = {
  answered: { label: "Trả lời", refusal: "", tone: "ok" },
  emergency_info: { label: "Trả lời + cảnh báo cấp cứu", refusal: "", tone: "bad" },
  emergency: { label: "Cấp cứu", refusal: "Phát hiện dấu hiệu cấp cứu", tone: "bad" },
  personal_advice: { label: "Kê đơn / chẩn đoán", refusal: "Từ chối: yêu cầu kê đơn hoặc chẩn đoán cá nhân", tone: "warn" },
  out_of_scope: { label: "Ngoài phạm vi", refusal: "Ngoài phạm vi hỗ trợ", tone: "warn" },
  prompt_injection: { label: "Lách quy tắc", refusal: "Từ chối: yêu cầu vi phạm quy tắc an toàn", tone: "bad" },
  greeting: { label: "Chào hỏi", refusal: "", tone: "info" },
  no_evidence: { label: "Không đủ bằng chứng", refusal: "Không tìm thấy tài liệu đủ liên quan", tone: "plain" },
  no_info: { label: "Tài liệu không có thông tin", refusal: "Tài liệu không có thông tin để trả lời", tone: "plain" },
  low_faithfulness: { label: "Không đạt kiểm tra chéo", refusal: "Câu trả lời không vượt qua kiểm tra chéo", tone: "warn" },
  verify_error: { label: "Lỗi kiểm tra chéo", refusal: "Không kiểm chứng được câu trả lời (lỗi dịch vụ)", tone: "warn" },
};

export function decisionInfo(decision: string | null | undefined) {
  return DECISIONS[decision ?? ""] ?? { label: decision ?? "–", refusal: "Từ chối", tone: "plain" as Tone };
}

export const CONFIGS: Record<string, string> = {
  hybrid_rag_guard: "Hybrid RAG + Guardrails",
  hybrid_rag: "Hybrid RAG",
  vector_rag: "Vector RAG",
  llm_only: "LLM thuần",
};

export const PROVIDERS: Record<string, string> = {
  groq: "Qwen 3.8 27B · Groq",
  cloudflare: "Llama 3.3 70B · Cloudflare",
  gemini: "Gemini 3.8 Flash · Google",
};

export function modelName(provider: string, model: string): string {
  if (model.includes("qwen")) return "Qwen 3.8";
  if (model.includes("llama")) return "Llama 3.3 70B";
  if (model.includes("gemini")) return "Gemini 3.8 Flash";
  return `${provider}:${model}`;
}

const nf1 = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const seconds = (ms: number | null | undefined) => (ms == null ? "–" : `${nf1.format(ms / 1000)} giây`);
export const secondsShort = (ms: number | null | undefined) => (ms == null ? "–" : `${nf1.format(ms / 1000)} s`);
export const score = (x: number | null | undefined) => (x == null ? "–" : nf2.format(x));
export const percent = (part: number, total: number) => (total ? `${Math.round((part / total) * 100)}%` : "–");

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}
