// Kiểu dữ liệu khớp với kết quả backend (app/rag.py, app/auth.py, app/admin_api.py).

export type RagConfig = "llm_only" | "vector_rag" | "hybrid_rag" | "hybrid_rag_guard";
export type Provider = "groq" | "cloudflare" | "gemini";

export interface Source {
  n: number;
  chunk_id: string;
  document_id: string;
  title: string;
  issuing_organization: string;
  section_title: string | null;
  page_number: number | null;
  page_end: number | null;
  source_url: string | null;
  text: string;
  cited?: boolean;
}

export interface Claim {
  text: string;
  cited: number[];
  supported?: boolean;
  reason?: string;
}

export interface Attempt {
  attempt: number;
  answer?: string;
  no_info?: boolean;
  faithfulness?: number | null;
  claims?: Claim[];
  infra_error?: boolean;
}

export interface Guard {
  decision: string;
  input?: { label: string; action: string; message: string | null };
  evidence?: { ok: boolean; best_vector_score: number; threshold: number };
  attempts?: Attempt[];
  faithfulness?: number | null;
  threshold?: number;
}

export interface ChatResult {
  question: string;
  config: RagConfig;
  provider: string;
  model: string;
  answer: string;
  refused: boolean;
  emergency: boolean;
  emergency_notice: string | null;
  sources: Source[];
  cited: number[];
  disclaimer: string;
  guard: Guard | null;
  timings: { total_ms: number } & Record<string, number>;
  llm_calls?: string[];
  conversation_id?: number;
}

export interface User {
  id: number;
  email: string;
  name: string;
  role: "user" | "admin";
  has_password: boolean;
  has_google: boolean;
}

export interface Turn {
  id: string;
  question: string;
  result?: ChatResult;
  error?: string;
}
