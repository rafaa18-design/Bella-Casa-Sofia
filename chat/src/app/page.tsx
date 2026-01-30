"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// =============================================================================
// Design Tokens — Light & Dark (per Ask AI Design System)
// =============================================================================

interface ColorTokens {
  bg: string;
  bgElevated: string;
  bgSubtle: string;
  border: string;
  text: string;
  textSecondary: string;
  textTertiary: string;
  accent: string;
  accentHover: string;
  link: string;
  codeBg: string;
  codeInlineBg: string;
  tableBorder: string;
  thColor: string;
  tdColor: string;
  inputBg: string;
  pillHoverBg: string;
  error: string;
  errorBg: string;
  chipSuccess: string;
  chipSuccessText: string;
}

const lightColors: ColorTokens = {
  bg: "#faf9f7",
  bgElevated: "#ffffff",
  bgSubtle: "#f0eeeb",
  border: "#e8e6e3",
  text: "#1a1a1a",
  textSecondary: "#6b6b6b",
  textTertiary: "#999999",
  accent: "#2a2a2a",
  accentHover: "#3a3a3a",
  link: "#0066ff",
  codeBg: "#f5f5f5",
  codeInlineBg: "#e8e8e8",
  tableBorder: "#e0e0e0",
  thColor: "#1a1a1a",
  tdColor: "#4a4a4a",
  inputBg: "rgba(0,0,0,0.05)",
  pillHoverBg: "#fff",
  error: "#ef4444",
  errorBg: "rgba(239,68,68,0.08)",
  chipSuccess: "#dcfce7",
  chipSuccessText: "#16a34a",
};

const darkColors: ColorTokens = {
  bg: "#0f0f0f",
  bgElevated: "#1a1a1a",
  bgSubtle: "#262626",
  border: "#2a2a2a",
  text: "#e5e5e5",
  textSecondary: "#888888",
  textTertiary: "#555555",
  accent: "#3a3a3a",
  accentHover: "#4a4a4a",
  link: "#6b9fff",
  codeBg: "#1a1a1a",
  codeInlineBg: "#2a2a2a",
  tableBorder: "#2a2a2a",
  thColor: "#e5e5e5",
  tdColor: "#b0b0b0",
  inputBg: "rgba(255,255,255,0.05)",
  pillHoverBg: "#1f1f1f",
  error: "#ef4444",
  errorBg: "rgba(239,68,68,0.08)",
  chipSuccess: "#0f2e1f",
  chipSuccessText: "#4ade80",
};

function getColors(dark: boolean): ColorTokens {
  return dark ? darkColors : lightColors;
}

// =============================================================================
// Theme Hook
// =============================================================================

function useTheme() {
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return true;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const toggle = useCallback(() => setDark((d) => !d), []);

  return { dark, toggle };
}

// =============================================================================
// Types
// =============================================================================

interface ActionTaken {
  tool: string;
  success: boolean;
  error: string | null;
}

interface Metrics {
  latency_ms: number;
  tokens_used: number;
}

interface Message {
  id: string;
  role: "user" | "agent";
  content: string;
  actions?: ActionTaken[];
  metrics?: Metrics;
}

// =============================================================================
// Icons (inline SVG per spec)
// =============================================================================

function SparkleIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3z" />
      <path d="M19 15l.5 1.5 1.5.5-1.5.5-.5 1.5-.5-1.5-1.5-.5 1.5-.5.5-1.5z" opacity={0.6} />
    </svg>
  );
}

function PaperclipIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

function SendIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  );
}

function TrashIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z" />
    </svg>
  );
}

function LogoutIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
    </svg>
  );
}

function SunIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" />
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </svg>
  );
}

function MoonIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
    </svg>
  );
}

// =============================================================================
// Helpers
// =============================================================================

function uuid(): string {
  return crypto.randomUUID();
}

function formatLatency(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

// =============================================================================
// Markdown Components (dynamic per theme)
// =============================================================================

function useMdComponents(c: ColorTokens): Components {
  return useMemo<Components>(() => ({
    p: ({ children }) => (
      <p style={{ margin: "0 0 8px 0" }}>{children}</p>
    ),
    pre: ({ children }) => (
      <pre style={{
        background: c.codeBg,
        padding: 12,
        borderRadius: 8,
        overflow: "auto",
        margin: "8px 0",
        fontSize: 13,
      }}>{children}</pre>
    ),
    code: ({ children, className }) => {
      const isBlock = className?.includes("language-");
      if (isBlock) return <code style={{ fontSize: 13 }}>{children}</code>;
      return (
        <code style={{
          background: c.codeInlineBg,
          padding: "2px 6px",
          borderRadius: 4,
          fontSize: 13,
        }}>{children}</code>
      );
    },
    ul: ({ children }) => (
      <ul style={{ margin: "8px 0", paddingLeft: 20 }}>{children}</ul>
    ),
    ol: ({ children }) => (
      <ol style={{ margin: "8px 0", paddingLeft: 20 }}>{children}</ol>
    ),
    li: ({ children }) => (
      <li style={{ margin: "4px 0" }}>{children}</li>
    ),
    strong: ({ children }) => (
      <strong style={{ fontWeight: 600 }}>{children}</strong>
    ),
    a: ({ children, href }) => (
      <a href={href} target="_blank" rel="noopener noreferrer" style={{
        color: c.link,
        textDecoration: "underline",
      }}>{children}</a>
    ),
    table: ({ children }) => (
      <div style={{ overflowX: "auto", margin: "12px 0" }}>
        <table style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 13,
          border: `1px solid ${c.tableBorder}`,
          borderRadius: 6,
        }}>{children}</table>
      </div>
    ),
    thead: ({ children }) => (
      <thead style={{ background: c.codeBg }}>{children}</thead>
    ),
    tr: ({ children }) => (
      <tr style={{ borderBottom: `1px solid ${c.tableBorder}` }}>{children}</tr>
    ),
    th: ({ children }) => (
      <th style={{
        padding: "10px 12px",
        textAlign: "left" as const,
        fontWeight: 600,
        color: c.thColor,
        borderRight: `1px solid ${c.tableBorder}`,
      }}>{children}</th>
    ),
    td: ({ children }) => (
      <td style={{
        padding: "10px 12px",
        color: c.tdColor,
        borderRight: `1px solid ${c.tableBorder}`,
      }}>{children}</td>
    ),
  }), [c]);
}

// =============================================================================
// Loading Shimmer
// =============================================================================

const loadingMessages = [
  "Seu agente está pensando",
  "Analisando sua solicitação",
  "Preparando resposta",
  "Processando sua pergunta",
];

function LoadingShimmer({ c }: { c: ColorTokens }) {
  const [msgIndex, setMsgIndex] = useState(0);

  useEffect(() => {
    const t = setInterval(() => {
      setMsgIndex((i) => (i + 1) % loadingMessages.length);
    }, 2000);
    return () => clearInterval(t);
  }, []);

  return (
    <div style={{
      display: "flex",
      justifyContent: "flex-start",
      marginBottom: 16,
      padding: "12px 16px",
    }}>
      <span style={{
        fontSize: 14,
        fontStyle: "italic",
        background: `linear-gradient(90deg, ${c.textTertiary}, ${c.textSecondary}, ${c.textTertiary})`,
        backgroundSize: "200% 100%",
        WebkitBackgroundClip: "text",
        WebkitTextFillColor: "transparent",
        backgroundClip: "text",
        animation: "shimmer 2s ease-in-out infinite",
      }}>
        {loadingMessages[msgIndex]}…
      </span>
    </div>
  );
}

// =============================================================================
// Suggestion Pills
// =============================================================================

const suggestions = [
  "Olá!",
  "O que você pode fazer?",
  "Me ajude com algo",
];

function SuggestionPills({ c, onSelect }: { c: ColorTokens; onSelect: (text: string) => void }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <div style={{
      display: "flex",
      flexWrap: "wrap",
      gap: 8,
      justifyContent: "center",
      maxWidth: 320,
    }}>
      {suggestions.map((text, i) => (
        <button
          key={i}
          onClick={() => onSelect(text)}
          onMouseEnter={() => setHoveredIndex(i)}
          onMouseLeave={() => setHoveredIndex(null)}
          style={{
            padding: "10px 16px",
            fontSize: 13,
            color: c.text,
            background: hoveredIndex === i ? c.pillHoverBg : c.bgElevated,
            border: `1px solid ${hoveredIndex === i ? c.accent : c.border}`,
            borderRadius: 20,
            cursor: "pointer",
            transition: "all 0.15s",
            fontFamily: "inherit",
          }}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

// =============================================================================
// Chat Message
// =============================================================================

function ChatMessage({ msg, c, mdComponents }: { msg: Message; c: ColorTokens; mdComponents: Components }) {
  const isUser = msg.role === "user";

  return (
    <div style={{ animation: "msg-in 0.28s ease-out both" }}>
      {/* Bubble */}
      <div style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 16,
      }}>
        <div style={{
          maxWidth: isUser ? "88%" : "100%",
          width: isUser ? "auto" : "100%",
          padding: "12px 16px",
          borderRadius: isUser ? "18px 18px 4px 18px" : "8px",
          fontSize: 14,
          lineHeight: 1.6,
          background: isUser ? c.accent : "transparent",
          color: isUser ? "#ffffff" : c.text,
          wordBreak: "break-word" as const,
        }}>
          {isUser ? (
            <span style={{ whiteSpace: "pre-wrap" }}>{msg.content}</span>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {msg.content}
            </ReactMarkdown>
          )}
        </div>
      </div>

      {/* Tool chips + metrics */}
      {!isUser && (msg.actions?.length || msg.metrics) && (
        <div style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 6,
          padding: "0 16px",
          marginTop: -8,
          marginBottom: 16,
        }}>
          {msg.actions?.map((a, i) => (
            <span key={i} style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              padding: "3px 8px",
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 500,
              background: a.success ? c.chipSuccess : c.errorBg,
              color: a.success ? c.chipSuccessText : c.error,
            }}>
              <span style={{ opacity: 0.7 }}>{a.success ? "✓" : "✗"}</span>
              {a.tool}
            </span>
          ))}
          {msg.metrics && (
            <span style={{
              marginLeft: "auto",
              fontSize: 11,
              color: c.textTertiary,
              fontVariantNumeric: "tabular-nums",
            }}>
              {formatLatency(msg.metrics.latency_ms)} · {msg.metrics.tokens_used} tokens
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Login Screen
// =============================================================================

function LoginScreen({ c, dark, onToggleTheme, onLogin }: {
  c: ColorTokens;
  dark: boolean;
  onToggleTheme: () => void;
  onLogin: (token: string) => void;
}) {
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hovered, setHovered] = useState(false);
  const [themeBtnHover, setThemeBtnHover] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch(
        `${API}/auth/login?username=${encodeURIComponent(user)}&password=${encodeURIComponent(pass)}`,
        { method: "POST" }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Erro ${res.status}`);
      }
      const data = await res.json();
      onLogin(data.access_token);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro ao conectar");
    } finally {
      setLoading(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "12px 16px",
    fontSize: 14,
    color: c.text,
    background: c.inputBg,
    border: `1px solid ${c.border}`,
    borderRadius: 12,
    outline: "none",
    fontFamily: "inherit",
    transition: "border-color 0.15s",
  };

  return (
    <div style={{
      display: "flex",
      minHeight: "100dvh",
      alignItems: "center",
      justifyContent: "center",
      padding: 24,
      background: c.bg,
      transition: "background 0.3s",
    }}>
      {/* Theme toggle — top right */}
      <button
        onClick={onToggleTheme}
        onMouseEnter={() => setThemeBtnHover(true)}
        onMouseLeave={() => setThemeBtnHover(false)}
        style={{
          position: "fixed",
          top: 16,
          right: 16,
          width: 36,
          height: 36,
          borderRadius: 10,
          border: "none",
          background: themeBtnHover ? c.bgSubtle : "transparent",
          color: themeBtnHover ? c.text : c.textSecondary,
          cursor: "pointer",
          transition: "background 0.15s, color 0.15s",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
        title={dark ? "Modo claro" : "Modo escuro"}
      >
        {dark ? <SunIcon size={16} /> : <MoonIcon size={16} />}
      </button>

      <form
        onSubmit={handleSubmit}
        style={{
          width: "100%",
          maxWidth: 360,
          animation: "login-in 0.5s cubic-bezier(0.16,1,0.3,1) both",
        }}
      >
        <div style={{
          padding: 32,
          borderRadius: 16,
          border: `1px solid ${c.border}`,
          background: c.bgElevated,
          transition: "background 0.3s, border-color 0.3s",
        }}>
          {/* Avatar + Brand */}
          <div style={{ textAlign: "center", marginBottom: 32 }}>
            <div style={{
              width: 40,
              height: 40,
              borderRadius: "50%",
              background: "linear-gradient(180deg, #ffffff 0%, #4a4a4a 100%)",
              margin: "0 auto 12px",
            }} />
            <h1 style={{
              fontSize: 18,
              fontWeight: 500,
              color: c.text,
              letterSpacing: "-0.02em",
            }}>
              Agent Chat
            </h1>
            <p style={{
              fontSize: 14,
              color: c.textSecondary,
              marginTop: 4,
            }}>
              Interface de teste
            </p>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <input
              ref={inputRef}
              type="text"
              placeholder="Usuário"
              value={user}
              onChange={(e) => setUser(e.target.value)}
              required
              style={inputStyle}
              onFocus={(e) => e.target.style.borderColor = c.textTertiary}
              onBlur={(e) => e.target.style.borderColor = c.border}
            />
            <input
              type="password"
              placeholder="Senha"
              value={pass}
              onChange={(e) => setPass(e.target.value)}
              required
              style={inputStyle}
              onFocus={(e) => e.target.style.borderColor = c.textTertiary}
              onBlur={(e) => e.target.style.borderColor = c.border}
            />
          </div>

          {error && (
            <div style={{
              marginTop: 12,
              padding: "8px 12px",
              borderRadius: 8,
              background: c.errorBg,
              color: c.error,
              fontSize: 12,
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            style={{
              marginTop: 20,
              width: "100%",
              padding: "12px 16px",
              fontSize: 14,
              fontWeight: 500,
              fontFamily: "inherit",
              color: "#ffffff",
              background: hovered ? c.accentHover : c.accent,
              border: "none",
              borderRadius: 12,
              cursor: loading ? "default" : "pointer",
              opacity: loading ? 0.5 : 1,
              transition: "all 0.15s",
            }}
          >
            {loading ? "Conectando…" : "Entrar"}
          </button>
        </div>
      </form>
    </div>
  );
}

// =============================================================================
// Chat Screen
// =============================================================================

function ChatScreen({ token, dark, c, onToggleTheme, onLogout }: {
  token: string;
  dark: boolean;
  c: ColorTokens;
  onToggleTheme: () => void;
  onLogout: () => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const conversationId = useRef(uuid());
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [headerHover, setHeaderHover] = useState<string | null>(null);
  const mdComponents = useMdComponents(c);

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 200);
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages, loading]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: Message = { id: uuid(), role: "user", content: text.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    if (inputRef.current) {
      inputRef.current.style.height = "52px";
    }

    try {
      const res = await fetch(`${API}/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          input: [{ type: "text", content: text.trim() }],
          conversation_id: conversationId.current,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Erro ${res.status}`);
      }

      const data = await res.json();
      const fo = data.final_output || {};

      setMessages((prev) => [...prev, {
        id: uuid(),
        role: "agent",
        content: fo.message || "(sem resposta)",
        actions: fo.actions_taken,
        metrics: data.metrics,
      }]);
    } catch (err: unknown) {
      setMessages((prev) => [...prev, {
        id: uuid(),
        role: "agent",
        content: `**Erro:** ${err instanceof Error ? err.message : "Falha na comunicação"}`,
      }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [loading, token]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  function handleTextareaInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "52px";
    const newHeight = Math.min(Math.max(52, el.scrollHeight), 200);
    el.style.height = `${newHeight}px`;
  }

  function clearConversation() {
    setMessages([]);
    setInput("");
    conversationId.current = uuid();
  }

  const hasMessages = messages.length > 0;
  const canSend = input.trim().length > 0 && !loading;

  const headerBtn = (id: string): React.CSSProperties => ({
    width: 36,
    height: 36,
    borderRadius: 10,
    border: "none",
    background: headerHover === id ? c.bgSubtle : "transparent",
    color: headerHover === id ? c.text : c.textSecondary,
    cursor: "pointer",
    transition: "background 0.15s, color 0.15s",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  });

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      height: "100dvh",
      background: c.bg,
      fontFamily: "system-ui, -apple-system, sans-serif",
      transition: "background 0.3s",
    }}>
      {/* Header */}
      <div style={{
        borderBottom: `1px solid ${c.border}`,
        flexShrink: 0,
        padding: "16px 20px",
        transition: "border-color 0.3s",
      }}>
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          maxWidth: 640,
          margin: "0 auto",
        }}>
          {/* Left: avatar + name */}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 28,
              height: 28,
              borderRadius: "50%",
              background: "linear-gradient(180deg, #ffffff 0%, #4a4a4a 100%)",
              flexShrink: 0,
            }} />
            <span style={{
              fontSize: 14,
              fontWeight: 500,
              color: c.text,
            }}>
              Agent
            </span>
          </div>

          {/* Right: buttons */}
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            {hasMessages && (
              <button
                onClick={clearConversation}
                onMouseEnter={() => setHeaderHover("clear")}
                onMouseLeave={() => setHeaderHover(null)}
                style={headerBtn("clear")}
                title="Limpar conversa"
              >
                <TrashIcon size={16} />
              </button>
            )}
            <button
              onClick={onToggleTheme}
              onMouseEnter={() => setHeaderHover("theme")}
              onMouseLeave={() => setHeaderHover(null)}
              style={headerBtn("theme")}
              title={dark ? "Modo claro" : "Modo escuro"}
            >
              {dark ? <SunIcon size={16} /> : <MoonIcon size={16} />}
            </button>
            <button
              onClick={onLogout}
              onMouseEnter={() => setHeaderHover("logout")}
              onMouseLeave={() => setHeaderHover(null)}
              style={headerBtn("logout")}
              title="Sair"
            >
              <LogoutIcon size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Messages / Empty State */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "20px 20px",
        }}
      >
        <div style={{ maxWidth: 640, margin: "0 auto" }}>
          {!hasMessages && !loading && (
            <div style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "48px 24px",
              textAlign: "center",
              minHeight: "calc(100dvh - 220px)",
            }}>
              <SparkleIcon size={24} />
              <h2 style={{
                fontSize: 22,
                fontWeight: 500,
                color: c.text,
                marginTop: 16,
                marginBottom: 8,
                letterSpacing: "-0.02em",
              }}>
                Como posso ajudar?
              </h2>
              <p style={{
                fontSize: 14,
                color: c.textSecondary,
                marginBottom: 40,
                maxWidth: 260,
                lineHeight: 1.5,
              }}>
                Envie uma mensagem para começar a conversa
              </p>
              <SuggestionPills c={c} onSelect={(text) => sendMessage(text)} />
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessage key={msg.id} msg={msg} c={c} mdComponents={mdComponents} />
          ))}

          {loading && <LoadingShimmer c={c} />}
        </div>
      </div>

      {/* Input Area */}
      <div style={{
        padding: "16px 20px 20px",
        borderTop: `1px solid ${c.border}`,
        background: c.bg,
        flexShrink: 0,
        transition: "background 0.3s, border-color 0.3s",
      }}>
        <div style={{ maxWidth: 640, margin: "0 auto" }}>
          <div style={{ position: "relative" }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleTextareaInput}
              onKeyDown={handleKeyDown}
              placeholder="Pergunte algo..."
              disabled={loading}
              rows={1}
              style={{
                display: "block",
                width: "100%",
                margin: 0,
                padding: "16px 52px 16px 50px",
                fontSize: 14,
                lineHeight: 1.4,
                color: c.text,
                background: c.inputBg,
                border: "none",
                borderRadius: 24,
                outline: "none",
                resize: "none",
                fontFamily: "inherit",
                minHeight: 52,
                maxHeight: 200,
                boxSizing: "border-box",
                overflow: "auto",
              }}
            />
            <button
              type="button"
              style={{
                position: "absolute",
                left: 10,
                bottom: 10,
                width: 32,
                height: 32,
                borderRadius: "50%",
                border: "none",
                background: c.inputBg,
                color: c.text,
                cursor: "pointer",
                transition: "all 0.15s",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <PaperclipIcon size={16} />
            </button>
            <button
              onClick={(e) => {
                e.preventDefault();
                sendMessage(input);
              }}
              disabled={!canSend}
              style={{
                position: "absolute",
                right: 10,
                bottom: 10,
                width: 32,
                height: 32,
                borderRadius: "50%",
                border: "none",
                background: c.inputBg,
                color: c.text,
                opacity: canSend ? 1 : 0.3,
                cursor: canSend ? "pointer" : "default",
                transition: "all 0.15s",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <SendIcon size={16} />
            </button>
          </div>
          <p style={{
            marginTop: 12,
            fontSize: 11,
            color: c.textTertiary,
            textAlign: "center",
            letterSpacing: "0.01em",
          }}>
            IA pode cometer erros. Verifique as respostas.
          </p>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Root
// =============================================================================

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const { dark, toggle } = useTheme();
  const c = getColors(dark);

  // Sync html background for scroll overscroll areas
  useEffect(() => {
    document.documentElement.style.background = c.bg;
  }, [c.bg]);

  if (!token) {
    return <LoginScreen c={c} dark={dark} onToggleTheme={toggle} onLogin={setToken} />;
  }

  return <ChatScreen token={token} dark={dark} c={c} onToggleTheme={toggle} onLogout={() => setToken(null)} />;
}
