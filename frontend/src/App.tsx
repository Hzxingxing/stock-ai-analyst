import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Activity, ArrowUpRight, BookOpen, Check, ChevronDown, ChevronRight,
  CircleHelp, Clock3, Database, FileText, Gauge, LoaderCircle, LogOut,
  Menu, MessageCircle, Plus, Search, Send, ShieldCheck, Sparkles,
  Square, Trash2, TrendingDown, TrendingUp, X,
} from "lucide-react";

import { api, ApiError } from "./api";
import type { Conversation, Instrument, MarketOverview, Memory, Message, ToolCall, User } from "./types";

type AuthMode = "login" | "register";
type RightTab = "watchlist" | "memory";

const toolLabels: Record<string, string> = {
  get_price_history: "查询历史行情",
  get_intraday_bars: "获取分时数据",
  get_recent_trades: "获取逐笔成交",
  get_market_overview: "读取市场广度",
};

function initials(email: string): string {
  return email.slice(0, 1).toLocaleUpperCase();
}

function formatAmount(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)} 万亿`;
  if (value >= 1e8) return `${(value / 1e8).toFixed(0)} 亿`;
  return value.toLocaleString("zh-CN");
}

function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(date);
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await api<User>(`/auth/${mode === "login" ? "login" : "register"}`, {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password }),
      });
      onAuthenticated(user);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "暂时无法登录，请稍后再试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-copy">
        <div className="brand-lockup brand-lockup-light">
          <div className="brand-mark"><Activity size={18} strokeWidth={2.1} /></div>
          <span>研序 <i>RESEARCH WORKSPACE</i></span>
        </div>
        <div className="auth-headline">
          <span className="eyebrow eyebrow-light">A SHARE · EVIDENCE FIRST</span>
          <h1>让每一次判断<br /><em>都有据可循。</em></h1>
          <p>持续对话、核验数据、记录假设。把投资研究，从零散的信息整理成一条清晰的证据链。</p>
        </div>
        <div className="auth-principles">
          <div><Database size={16} /><span>行情与研究事实分开存储</span></div>
          <div><ShieldCheck size={16} /><span>会话和研究记忆按用户隔离</span></div>
          <div><BookOpen size={16} /><span>工具调用可查，结论可回溯</span></div>
        </div>
        <span className="auth-footnote">本平台用于研究辅助。数据的完整性和时效性以所标注来源为准。</span>
      </section>
      <section className="auth-card-wrap">
        <div className="auth-card">
          <div className="auth-card-top">
            <span className="eyebrow">RESEARCH ACCOUNT</span>
            <span className="secure-pill"><ShieldCheck size={13} /> 安全连接</span>
          </div>
          <h2>{mode === "login" ? "欢迎回来" : "创建研究账户"}</h2>
          <p className="auth-subtitle">{mode === "login" ? "继续你的市场研究与讨论" : "开启独立、私密的研究空间"}</p>
          <form onSubmit={submit} className="auth-form">
            <label htmlFor="auth-email">邮箱地址</label>
            <input id="auth-email" type="email" autoComplete="email" required value={email}
              onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" />
            <div className="password-label">
              <label htmlFor="auth-password">密码</label>
              {mode === "register" && <small>至少 12 位</small>}
            </div>
            <input id="auth-password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={12} maxLength={256} required value={password}
              onChange={(event) => setPassword(event.target.value)} placeholder="输入至少 12 位密码" />
            {error && <div className="form-error" role="alert">{error}</div>}
            <button className="button button-primary auth-submit" disabled={busy} type="submit">
              {busy ? <LoaderCircle className="spin" size={17} /> : null}
              {mode === "login" ? "进入研究工作台" : "创建账户"}
              {!busy && <ArrowUpRight size={16} />}
            </button>
          </form>
          <div className="auth-switch">
            {mode === "login" ? "还没有账户？" : "已有账户？"}
            <button onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
              {mode === "login" ? "创建一个" : "返回登录"}
            </button>
          </div>
          <div className="auth-privacy"><ShieldCheck size={14} /> 你的会话、记忆与关注列表仅对你可见</div>
        </div>
        <div className="auth-version">研序 · 研究工作台 <span>版本 0.2</span></div>
      </section>
    </main>
  );
}

function ToolTrace({ calls }: { calls: ToolCall[] }) {
  if (!calls.length) return null;
  const complete = calls.filter((call) => call.status === "complete").length;
  return (
    <details className="trace-panel">
      <summary>
        <span className="trace-summary-icon"><Activity size={14} /></span>
        <span>研究过程</span>
        <span className="trace-count">{calls.length} 项工具调用</span>
        <span className="trace-status">{complete === calls.length ? "已完成" : "执行中"}</span>
        <ChevronDown className="trace-chevron" size={15} />
      </summary>
      <div className="trace-list">
        {calls.map((call, index) => (
          <article key={call.id} className={`trace-item trace-${call.status}`}>
            <div className="trace-step-index">{call.status === "running" ? <LoaderCircle className="spin" size={13} /> : String(index + 1).padStart(2, "0")}</div>
            <div className="trace-item-content">
              <div className="trace-item-heading">
                <strong>{toolLabels[call.name] || call.name}</strong>
                {call.duration_ms != null && <span>{call.duration_ms.toLocaleString()} ms</span>}
              </div>
              <div className="trace-output">
                {call.output_summary || (call.status === "running" ? "正在执行数据查询…" : call.error_summary || "工具已执行")}
              </div>
              <div className="trace-meta">
                {call.source && <span><Database size={12} /> {call.source}</span>}
                {call.data_as_of && <span><Clock3 size={12} /> 数据截至 {call.data_as_of}</span>}
                {call.cache_status && <span>{call.cache_status.includes("hit") ? "缓存命中" : "已刷新"}</span>}
                {call.retry_count ? <span>重试 {call.retry_count} 次</span> : null}
              </div>
              {call.input && Object.keys(call.input).length > 0 && (
                <details className="trace-arguments">
                  <summary>查看参数</summary>
                  <pre>{JSON.stringify(call.input, null, 2)}</pre>
                </details>
              )}
            </div>
            <span className={`trace-dot trace-dot-${call.status}`} aria-label={call.status} />
          </article>
        ))}
      </div>
      <div className="trace-disclosure">这里记录的是实际执行的工具和数据结果，不包含模型的隐式推理。</div>
    </details>
  );
}

function MessageItem({ message }: { message: Message }) {
  const isAssistant = message.role === "assistant";
  return (
    <article className={`message-row ${isAssistant ? "message-assistant" : "message-user"}`}>
      {isAssistant && <div className="assistant-avatar"><Activity size={16} /></div>}
      <div className="message-column">
        <div className="message-label">
          <span>{isAssistant ? "研序 · 研究助手" : "你"}</span>
          {isAssistant && <span className="message-confidence"><ShieldCheck size={12} /> 证据导向</span>}
        </div>
        <div className={isAssistant ? "assistant-body markdown-body" : "user-bubble"}>
          {isAssistant ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || ""}</ReactMarkdown> : message.content}
          {message.streaming && !message.content && <span className="typing-cursor" aria-label="正在生成" />}
          {message.streaming && message.content && <span className="typing-cursor" aria-hidden="true" />}
        </div>
        {isAssistant && <ToolTrace calls={message.tool_calls || []} />}
      </div>
      {!isAssistant && <div className="user-avatar">你</div>}
    </article>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [watchlist, setWatchlist] = useState<Instrument[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [rightTab, setRightTab] = useState<RightTab>("watchlist");
  const [input, setInput] = useState("");
  const [phase, setPhase] = useState("");
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [instrumentQuery, setInstrumentQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Instrument[]>([]);
  const [searching, setSearching] = useState(false);
  const [memoryDraft, setMemoryDraft] = useState("");
  const [memoryKind, setMemoryKind] = useState<Memory["kind"]>("hypothesis");
  const [memorySaving, setMemorySaving] = useState(false);
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [toast, setToast] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const activeLoad = useRef(0);
  const skipNextLoad = useRef(false);
  const abortController = useRef<AbortController | null>(null);

  const notify = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3000);
  }, []);

  useEffect(() => {
    api<User>("/auth/me").then(setUser).catch(() => setUser(null)).finally(() => setAuthReady(true));
  }, []);

  const refreshWorkspace = useCallback(async () => {
    try {
      const [threads, tracked, savedMemories] = await Promise.all([
        api<Conversation[]>("/conversations"),
        api<Instrument[]>("/watchlist"),
        api<Memory[]>("/memories"),
      ]);
      setConversations(threads);
      setWatchlist(tracked);
      setMemories(savedMemories);
      if (threads.length) setActiveId((current) => current || threads[0].id);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) setUser(null);
    }
  }, []);

  useEffect(() => {
    if (user) void refreshWorkspace();
  }, [user, refreshWorkspace]);

  useEffect(() => {
    if (!user || !activeId) {
      setMessages([]);
      return;
    }
    if (skipNextLoad.current) {
      skipNextLoad.current = false;
      return;
    }
    const loadId = ++activeLoad.current;
    setLoadingMessages(true);
    api<Message[]>(`/conversations/${activeId}/messages`)
      .then((result) => { if (loadId === activeLoad.current) setMessages(result); })
      .catch((reason) => { if (!(reason instanceof ApiError && reason.status === 404)) notify("无法读取这段研究记录"); })
      .finally(() => { if (loadId === activeLoad.current) setLoadingMessages(false); });
  }, [activeId, user, notify]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [messages, phase]);

  useEffect(() => {
    if (!instrumentQuery.trim() || !user) {
      setSearchResults([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      setSearching(true);
      try {
        const results = await api<Instrument[]>(`/instruments/search?query=${encodeURIComponent(instrumentQuery.trim())}`);
        setSearchResults(results);
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [instrumentQuery, user]);

  async function createConversation() {
    try {
      const conversation = await api<Conversation>("/conversations", {
        method: "POST", body: JSON.stringify({ title: "新研究" }),
      });
      skipNextLoad.current = true;
      activeLoad.current += 1;
      setActiveId(conversation.id);
      setMessages([]);
      setPhase("");
      setConversations((current) => [conversation, ...current]);
      setMobileNavOpen(false);
      setContextOpen(false);
      composerRef.current?.focus();
      return conversation;
    } catch {
      notify("暂时无法创建研究会话");
      return null;
    }
  }

  async function switchConversation(id: string) {
    abortController.current?.abort();
    setSending(false);
    setPhase("");
    activeLoad.current += 1;
    setActiveId(id);
    setMobileNavOpen(false);
    setContextOpen(false);
  }

  async function deleteConversation(event: ReactMouseEvent<HTMLButtonElement>, conversation: Conversation) {
    event.stopPropagation();
    try {
      await api<void>(`/conversations/${conversation.id}`, { method: "DELETE" });
      const next = conversations.filter((item) => item.id !== conversation.id);
      setConversations(next);
      if (activeId === conversation.id) {
        setActiveId(null);
        setMessages([]);
      }
    } catch {
      notify("无法删除这段研究记录");
    }
  }

  async function stopResearch() {
    abortController.current?.abort();
    abortController.current = null;
    setSending(false);
    setPhase("");
  }

  async function sendMessage(text: string) {
    const content = text.trim();
    if (!content || sending) return;
    setInput("");
    let conversationId = activeId;
    if (!conversationId) {
      const conversation = await createConversation();
      if (!conversation) return;
      conversationId = conversation.id;
    }
    const placeholderId = `local-${crypto.randomUUID()}`;
    let activeAssistantId = placeholderId;
    setMessages((current) => [
      ...current,
      { id: `user-${placeholderId}`, role: "user", content },
      { id: placeholderId, role: "assistant", content: "", streaming: true, tool_calls: [] },
    ]);
    setSending(true);
    setPhase("正在整理问题并核对数据");
    const controller = new AbortController();
    abortController.current = controller;
    try {
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ conversation_id: conversationId, content }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        const payload = await response.json().catch(() => null);
        throw new ApiError(payload?.detail || "研究请求暂时失败", response.status);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentMessageId = placeholderId;
      const applyEvent = (block: string) => {
        let eventName = "message";
        const dataLines: string[] = [];
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
        }
        if (!dataLines.length) return;
        const data = JSON.parse(dataLines.join("\n"));
        if (eventName === "conversation" && data.assistant_message_id) {
          currentMessageId = data.assistant_message_id;
          activeAssistantId = currentMessageId;
          setMessages((current) => current.map((message) => message.id === placeholderId
            ? { ...message, id: currentMessageId }
            : message));
        } else if (eventName === "status") {
          setPhase(data.label || "正在研究");
        } else if (eventName === "token") {
          setPhase("");
          setMessages((current) => current.map((message) => message.id === currentMessageId
            ? { ...message, content: message.content + data.text }
            : message));
        } else if (eventName === "tool") {
          if (data.status === "running") setPhase(`正在执行：${toolLabels[data.name] || data.name}`);
          setMessages((current) => current.map((message) => {
            if (message.id !== currentMessageId) return message;
            const calls = message.tool_calls || [];
            const index = calls.findIndex((call) => call.id === data.id);
            const nextCall = { ...(index >= 0 ? calls[index] : {}), ...data } as ToolCall;
            const nextCalls = [...calls];
            if (index >= 0) nextCalls[index] = nextCall;
            else nextCalls.push(nextCall);
            return { ...message, tool_calls: nextCalls };
          }));
        } else if (eventName === "done") {
          setPhase("");
          setMessages((current) => current.map((message) => message.id === currentMessageId
            ? { ...message, streaming: false }
            : message));
        } else if (eventName === "error") {
          setPhase("");
          setMessages((current) => current.map((message) => message.id === currentMessageId
            ? { ...message, content: message.content || data.message, streaming: false }
            : message));
        }
      };
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        buffer = buffer.replace(/\r\n/g, "\n");
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";
        for (const block of blocks) applyEvent(block);
      }
      if (buffer.trim()) applyEvent(buffer);
      setMessages((current) => current.map((message) => message.id === currentMessageId
        ? { ...message, streaming: false }
        : message));
      void refreshWorkspace();
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") {
        setMessages((current) => current.map((message) => message.id === activeAssistantId
          ? { ...message, streaming: false, content: message.content || "本轮研究已停止。" }
          : message));
      } else {
        const message = reason instanceof Error ? reason.message : "网络连接暂时中断";
        setMessages((current) => current.map((item) => item.id === placeholderId
          ? { ...item, streaming: false, content: item.content || message }
          : item));
      }
    } finally {
      abortController.current = null;
      setSending(false);
      setPhase("");
    }
  }

  function submitComposer(event: FormEvent) {
    event.preventDefault();
    void sendMessage(input);
  }

  function composerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void sendMessage(input);
    }
  }

  async function addInstrument(instrument: Instrument) {
    if (instrument.instrument_type !== "equity") {
      setInstrumentQuery("");
      return;
    }
    try {
      await api<Instrument>("/watchlist", {
        method: "POST", body: JSON.stringify({ symbol: instrument.provider_symbol }),
      });
      setWatchlist(await api<Instrument[]>("/watchlist"));
      setInstrumentQuery("");
      setSearchResults([]);
      notify(`${instrument.name} 已加入关注`);
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : "添加失败");
    }
  }

  async function removeInstrument(instrument: Instrument) {
    try {
      await api<void>(`/watchlist/${encodeURIComponent(instrument.code)}`, { method: "DELETE" });
      setWatchlist((current) => current.filter((item) => item.code !== instrument.code));
    } catch {
      notify("无法移除该关注股票");
    }
  }

  async function saveMemory(event: FormEvent) {
    event.preventDefault();
    if (!memoryDraft.trim()) return;
    setMemorySaving(true);
    try {
      await api<Memory>("/memories", {
        method: "POST",
        body: JSON.stringify({ kind: memoryKind, statement: memoryDraft.trim(), attribution: "user" }),
      });
      setMemories(await api<Memory[]>("/memories"));
      setMemoryDraft("");
      notify("研究记忆已保存");
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setMemorySaving(false);
    }
  }

  async function deleteMemory(memory: Memory) {
    try {
      await api<void>(`/memories/${memory.id}`, { method: "DELETE" });
      setMemories((current) => current.filter((item) => item.id !== memory.id));
    } catch {
      notify("无法删除这条研究记忆");
    }
  }

  async function loadOverview() {
    setOverviewLoading(true);
    try {
      setOverview(await api<MarketOverview>("/market/overview"));
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : "市场数据暂时不可用");
    } finally {
      setOverviewLoading(false);
    }
  }

  async function logout() {
    await api<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
    setUser(null);
    setConversations([]);
    setWatchlist([]);
    setMemories([]);
    setMessages([]);
    setActiveId(null);
  }

  if (!authReady) {
    return <div className="boot-screen"><div className="brand-mark"><Activity size={18} /></div><LoaderCircle className="spin" size={18} /></div>;
  }
  if (!user) return <AuthScreen onAuthenticated={setUser} />;

  const activeConversation = conversations.find((conversation) => conversation.id === activeId);
  const hasMessages = messages.length > 0;

  return (
    <div className={`workspace ${mobileNavOpen ? "nav-open" : ""}`}>
      {mobileNavOpen && <button className="nav-scrim" aria-label="关闭导航" onClick={() => setMobileNavOpen(false)} />}
      {contextOpen && <button className="context-scrim" aria-label="关闭研究上下文" onClick={() => setContextOpen(false)} />}
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark"><Activity size={18} strokeWidth={2.1} /></div>
          <span>研序 <i>RESEARCH</i></span>
        </div>
        <button className="button new-research" onClick={() => void createConversation()}>
          <Plus size={17} /> 新建研究 <kbd>⌘ K</kbd>
        </button>
        <div className="sidebar-section-title"><span>工作区</span></div>
        <nav className="side-nav" aria-label="主导航">
          <button className="side-nav-item active"><MessageCircle size={16} />研究对话<span className="nav-pill">AI</span></button>
          <button className="side-nav-item" onClick={() => { setRightTab("watchlist"); setContextOpen(true); }}><Activity size={16} />关注股票<span className="nav-count">{watchlist.length}</span></button>
          <button className="side-nav-item" onClick={() => { setRightTab("memory"); setContextOpen(true); }}><BookOpen size={16} />长期记忆<span className="nav-count">{memories.length}</span></button>
        </nav>
        <div className="history-heading">
          <span>最近研究</span><span className="history-count">{conversations.length}</span>
        </div>
        <div className="conversation-list">
          {conversations.length ? conversations.map((conversation) => (
            <div key={conversation.id} className={`conversation-row ${activeId === conversation.id ? "selected" : ""}`}>
              <button className="conversation-link" onClick={() => void switchConversation(conversation.id)} title={conversation.title}>
                <span className="conversation-glyph"><MessageCircle size={14} /></span>
                <span className="conversation-title">{conversation.title}</span>
                <span className="conversation-date">{dateLabel(conversation.updated_at)}</span>
              </button>
              <button className="conversation-delete" aria-label={`删除${conversation.title}`}
                onClick={(event) => void deleteConversation(event, conversation)}><Trash2 size={13} /></button>
            </div>
          )) : <div className="empty-history">你的研究对话会保存在这里</div>}
        </div>
        <div className="sidebar-bottom">
          <div className="workspace-status"><span className="status-indicator" />研究引擎已就绪</div>
          <button className="profile-button" onClick={() => void logout()} title="退出登录">
            <div className="profile-avatar">{initials(user.email)}</div>
            <span className="profile-details"><strong>{user.email.split("@")[0]}</strong><small>个人研究空间</small></span>
            <LogOut size={15} className="profile-logout" />
          </button>
        </div>
      </aside>

      <main className="chat-workspace">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="打开导航" onClick={() => setMobileNavOpen(true)}><Menu size={19} /></button>
          <div className="breadcrumbs"><span>研究工作区</span><ChevronRight size={14} /><strong>{activeConversation?.title || "新研究"}</strong></div>
          <div className="topbar-actions">
            <span className="market-status"><span className="status-indicator" />数据链路正常</span>
            <button className="icon-button mobile-context-button" aria-label="打开研究上下文" onClick={() => setContextOpen(true)}><BookOpen size={17} /></button>
            <button className="icon-button help-button" aria-label="研究规范说明" title="研究结论基于已标注来源的数据"><CircleHelp size={17} /></button>
            <button className="profile-avatar topbar-avatar" onClick={() => void logout()} title="退出登录">{initials(user.email)}</button>
          </div>
        </header>

        <div className={`conversation-stage ${hasMessages ? "has-messages" : "welcome-stage"}`} ref={scrollRef}>
          {loadingMessages ? <div className="loading-history"><LoaderCircle className="spin" size={17} /> 正在载入研究记录</div> : null}
          {!hasMessages && !loadingMessages ? (
            <div className="welcome-content">
              <div className="welcome-symbol"><Sparkles size={21} /></div>
              <span className="eyebrow">A SHARE RESEARCH ASSISTANT</span>
              <h1>从一个问题开始，<br /><em>逐步建立证据。</em></h1>
              <p>我可以协助梳理行情、市场结构与个股研究。涉及市场事实时，会先查询数据并记录来源。</p>
              <div className="suggestion-grid">
                <button onClick={() => void sendMessage("分析今天的市场广度与成交情况，并说明数据来源") }>
                  <span className="suggestion-icon"><Gauge size={16} /></span>
                  <strong>观察市场</strong>
                  <small>市场广度与成交变化</small><ArrowUpRight size={14} className="suggestion-arrow" />
                </button>
                <button onClick={() => void sendMessage("帮我研究贵州茅台近期日线与周线的结构") }>
                  <span className="suggestion-icon"><TrendingUp size={16} /></span>
                  <strong>研究个股</strong>
                  <small>趋势、量价与关键区间</small><ArrowUpRight size={14} className="suggestion-arrow" />
                </button>
                <button onClick={() => void sendMessage("请读取上证指数近三个月走势，归纳主要变化") }>
                  <span className="suggestion-icon"><Activity size={16} /></span>
                  <strong>查看指数</strong>
                  <small>上证指数与市场节奏</small><ArrowUpRight size={14} className="suggestion-arrow" />
                </button>
                <button onClick={() => { setRightTab("memory"); setContextOpen(true); }}>
                  <span className="suggestion-icon"><BookOpen size={16} /></span>
                  <strong>整理假设</strong>
                  <small>记录证据与失效条件</small><ArrowUpRight size={14} className="suggestion-arrow" />
                </button>
              </div>
              <div className="welcome-footnote"><ShieldCheck size={13} /> 行情事实、用户观点与模型推断会分别标注</div>
            </div>
          ) : (
            <div className="message-list">
              {messages.map((message) => <MessageItem key={message.id} message={message} />)}
              {phase && sending && <div className="research-phase"><span className="status-indicator" />{phase}</div>}
            </div>
          )}
        </div>

        <div className="composer-wrap">
          <form className="composer" onSubmit={submitComposer}>
            <textarea ref={composerRef} value={input} onChange={(event) => setInput(event.target.value)}
              onKeyDown={composerKeyDown} rows={1} maxLength={12000}
              placeholder="描述你想研究的问题，或提出一个需要核实的判断…" aria-label="输入研究问题" />
            <div className="composer-bottom">
              <div className="composer-tools">
                <span><ShieldCheck size={13} /> 数据结论附来源</span>
                <span className="composer-separator" />
                <span>Shift + Enter 换行</span>
              </div>
              {sending ? (
                <button className="send-button stop-button" type="button" onClick={() => void stopResearch()} aria-label="停止研究">
                  <Square size={14} fill="currentColor" /> 停止
                </button>
              ) : (
                <button className="send-button" type="submit" disabled={!input.trim()} aria-label="发送研究问题"><Send size={16} /></button>
              )}
            </div>
          </form>
          <p className="composer-disclaimer">AI 输出仅供研究参考。行情具有时效性，请以数据源标注时间为准。</p>
        </div>
      </main>

      <aside className={`context-panel ${contextOpen ? "context-open" : ""}`}>
        <div className="context-header">
          <div><span className="eyebrow">RESEARCH CONTEXT</span><h2>研究上下文</h2></div>
          <button className="icon-button context-close" aria-label="关闭上下文" onClick={() => setContextOpen(false)}><X size={16} /></button>
        </div>
        <div className="context-tabs" role="tablist" aria-label="研究上下文">
          <button role="tab" aria-selected={rightTab === "watchlist"} className={rightTab === "watchlist" ? "active" : ""}
            onClick={() => setRightTab("watchlist")}><Activity size={14} /> 关注</button>
          <button role="tab" aria-selected={rightTab === "memory"} className={rightTab === "memory" ? "active" : ""}
            onClick={() => setRightTab("memory")}><BookOpen size={14} /> 记忆 <span>{memories.length}</span></button>
        </div>

        {rightTab === "watchlist" ? (
          <div className="context-body">
            <div className="context-section-head">
              <div><strong>我的关注</strong><small>仅为你的研究采集长期行情</small></div>
              <span className="context-number">{watchlist.length.toString().padStart(2, "0")}</span>
            </div>
            <div className="instrument-search">
              <Search size={15} />
              <input value={instrumentQuery} onChange={(event) => setInstrumentQuery(event.target.value)}
                placeholder="输入名称或股票代码" aria-label="搜索股票" />
              {instrumentQuery && <button onClick={() => setInstrumentQuery("")} aria-label="清空搜索"><X size={13} /></button>}
              {instrumentQuery && (searching || searchResults.length > 0) && (
                <div className="search-results">
                  {searching && <div className="search-result-muted"><LoaderCircle size={14} className="spin" /> 正在查找</div>}
                  {!searching && searchResults.map((result) => (
                    <button key={result.code} onClick={() => void addInstrument(result)}>
                      <span><strong>{result.name}</strong><small>{result.provider_symbol} · {result.instrument_type === "index" ? "指数" : "A 股"}</small></span>
                      {result.instrument_type === "equity" ? <Plus size={15} /> : <span className="index-tag">系统指数</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="watchlist-items">
              {watchlist.length ? watchlist.map((instrument) => (
                <div className="watchlist-row" key={instrument.code}>
                  <div className="stock-monogram">{instrument.name.slice(0, 1)}</div>
                  <div className="watchlist-name"><strong>{instrument.name}</strong><small>{instrument.provider_symbol}</small></div>
                  <button className="remove-watch" aria-label={`取消关注${instrument.name}`} onClick={() => void removeInstrument(instrument)}><X size={14} /></button>
                </div>
              )) : <div className="empty-context"><div className="empty-context-icon"><Search size={16} /></div><strong>还没有关注股票</strong><span>搜索代码或名称，添加后即可研究个股。</span></div>}
            </div>
            <div className="context-divider" />
            <div className="context-section-head market-head">
              <div><strong>市场观察</strong><small>{overview?.trade_date || "尚未读取今日数据"}</small></div>
              <button className="text-button" onClick={() => void loadOverview()} disabled={overviewLoading}>
                {overviewLoading ? <LoaderCircle className="spin" size={13} /> : <ArrowUpRight size={13} />}
                更新
              </button>
            </div>
            {overview ? (
              <div className="market-card">
                <div className="market-advance"><span><TrendingUp size={13} /> 上涨</span><strong className="up-value">{overview.advances?.toLocaleString() ?? "—"}</strong></div>
                <div className="market-advance"><span><TrendingDown size={13} /> 下跌</span><strong className="down-value">{overview.declines?.toLocaleString() ?? "—"}</strong></div>
                <div className="market-amount"><span>两市成交额</span><strong>{formatAmount(overview.total_amount)}</strong></div>
                <small>来源：{overview.source}</small>
              </div>
            ) : (
              <button className="market-empty" onClick={() => void loadOverview()} disabled={overviewLoading}>
                {overviewLoading ? <LoaderCircle className="spin" size={15} /> : <Gauge size={15} />}
                <span>{overviewLoading ? "正在读取市场数据" : "读取今日市场概览"}</span><ChevronRight size={14} />
              </button>
            )}
            <div className="core-index-note"><span className="core-index-dot" /><span>上证、深证、创业板、科创 50 及参考指数由系统持续记录</span></div>
            <div className="source-note"><FileText size={13} /> 行情存于 MySQL；分时与逐笔使用短期缓存</div>
          </div>
        ) : (
          <div className="context-body memory-body">
            <div className="context-section-head">
              <div><strong>研究记忆</strong><small>偏好、假设、证据与待验证问题</small></div>
              <span className="context-number">{memories.length.toString().padStart(2, "0")}</span>
            </div>
            <form className="memory-form" onSubmit={saveMemory}>
              <label htmlFor="memory-kind">记忆类型</label>
              <select id="memory-kind" value={memoryKind} onChange={(event) => setMemoryKind(event.target.value as Memory["kind"])}>
                <option value="hypothesis">研究假设</option><option value="preference">研究偏好</option>
                <option value="evidence">证据记录</option><option value="open_question">待验证问题</option>
              </select>
              <label htmlFor="memory-statement">记忆内容</label>
              <textarea id="memory-statement" rows={4} maxLength={6000} value={memoryDraft}
                onChange={(event) => setMemoryDraft(event.target.value)} placeholder="写下假设、依据或失效条件…" />
              <button className="button button-dark memory-save" type="submit" disabled={!memoryDraft.trim() || memorySaving}>
                {memorySaving ? <LoaderCircle size={14} className="spin" /> : <Plus size={14} />} 保存到长期记忆
              </button>
            </form>
            <div className="memory-list-heading"><span>已保存的记忆</span><span>{memories.length}</span></div>
            <div className="memory-items">
              {memories.length ? memories.map((memory) => (
                <article className="memory-card" key={memory.id}>
                  <div className="memory-card-top"><span>{({ preference: "偏好", hypothesis: "假设", evidence: "证据", open_question: "待验证" } as const)[memory.kind]}</span>
                    <button aria-label="删除记忆" onClick={() => void deleteMemory(memory)}><Trash2 size={13} /></button></div>
                  <p>{memory.statement}</p>
                  <small>{memory.attribution === "user" ? "你的记录" : "模型推断"}{memory.updated_at ? ` · ${dateLabel(memory.updated_at)}` : ""}</small>
                </article>
              )) : <div className="empty-context memory-empty"><div className="empty-context-icon"><BookOpen size={16} /></div><strong>积累你的研究脉络</strong><span>保存假设和失效条件，AI 会在后续讨论中参考。</span></div>}
            </div>
            <div className="memory-privacy"><ShieldCheck size={14} /> 记忆可由你随时修改或删除</div>
          </div>
        )}
        <div className="context-footer"><span>研序 · 数据研究工作台</span><span>0.2.0</span></div>
      </aside>
      {toast && <div className="toast" role="status"><Check size={15} />{toast}</div>}
    </div>
  );
}
