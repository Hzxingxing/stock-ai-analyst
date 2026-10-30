export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ToolCall {
  id: string;
  name: string;
  input?: Record<string, unknown>;
  output_summary?: string | null;
  evidence?: Record<string, unknown> | null;
  source?: string | null;
  data_as_of?: string | null;
  status: "running" | "complete" | "partial" | "error";
  cache_status?: string | null;
  duration_ms?: number | null;
  retry_count?: number;
  error_summary?: string | null;
  memory_proposal?: MemorySuggestion;
  created_at?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  metadata?: Record<string, unknown>;
  tool_calls?: ToolCall[];
  streaming?: boolean;
}

export interface Instrument {
  code: string;
  name: string;
  instrument_type: "equity" | "index";
  provider_symbol: string;
}

export interface Memory {
  id: string;
  kind: "preference" | "hypothesis" | "evidence" | "open_question";
  statement: string;
  attribution: "user" | "agent_inference";
  stance: "support" | "oppose" | "neutral" | null;
  supporting_evidence: Record<string, unknown>[];
  counter_evidence: Record<string, unknown>[];
  invalidation_conditions: string[];
  instrument_codes: string[];
  valid_until: string | null;
  status: "active" | "superseded" | "invalidated";
  supersedes_id: string | null;
  conversation_id: string | null;
  created_at?: string;
  updated_at?: string;
}

export type MemorySuggestion = Pick<
  Memory,
  | "kind"
  | "statement"
  | "attribution"
  | "stance"
  | "supporting_evidence"
  | "counter_evidence"
  | "invalidation_conditions"
> & Partial<Pick<Memory, "instrument_codes" | "valid_until">>;

export interface MarketOverview {
  trade_date: string;
  total_stocks: number | null;
  advances: number | null;
  declines: number | null;
  unchanged: number | null;
  limit_up: number | null;
  limit_down: number | null;
  limit_up_source?: string | null;
  limit_down_source?: string | null;
  trade_date_source?: string | null;
  total_amount: number | null;
  source: string;
  collected_at: string | null;
  warning?: string | null;
}
