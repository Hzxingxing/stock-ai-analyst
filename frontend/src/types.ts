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
  source?: string | null;
  data_as_of?: string | null;
  status: "running" | "complete" | "error";
  cache_status?: string | null;
  duration_ms?: number | null;
  retry_count?: number;
  error_summary?: string | null;
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
  conversation_id: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface MarketOverview {
  trade_date: string;
  total_stocks: number | null;
  advances: number | null;
  declines: number | null;
  unchanged: number | null;
  limit_up: number | null;
  limit_down: number | null;
  total_amount: number | null;
  source: string;
  collected_at: string | null;
}
