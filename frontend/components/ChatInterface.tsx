"use client";
import { useState, useRef, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { 
  Send, Loader2, MessageSquareCode, User, Bot, 
  Sparkles, Wrench, Factory, TrendingUp, Users, Landmark 
} from "lucide-react";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface Props {
  onSend: (message: string) => Promise<string>;
  placeholder?: string;
  agentType?: string;
  stateKey?: string;
}

const CHAT_AGENT_CONFIG: Record<
  string,
  { 
    colorLight: string; 
    colorDark: string; 
    textClass: string;
    icon: React.ComponentType<{ className?: string }> 
  }
> = {
  report: {
    colorLight: "bg-indigo-50 border-indigo-200 text-indigo-700",
    colorDark: "dark:bg-indigo-500/20 dark:border-indigo-500/30 dark:text-indigo-400",
    textClass: "text-indigo-600 dark:text-indigo-400",
    icon: Sparkles,
  },
  firm: {
    colorLight: "bg-sky-50 border-sky-200 text-sky-700",
    colorDark: "dark:bg-sky-500/20 dark:border-sky-500/30 dark:text-sky-400",
    textClass: "text-sky-600 dark:text-sky-400",
    icon: Wrench,
  },
  refiner: {
    colorLight: "bg-purple-50 border-purple-200 text-purple-700",
    colorDark: "dark:bg-purple-500/20 dark:border-purple-500/30 dark:text-purple-400",
    textClass: "text-purple-600 dark:text-purple-400",
    icon: Factory,
  },
  speculator: {
    colorLight: "bg-amber-50 border-amber-200 text-amber-700",
    colorDark: "dark:bg-amber-500/20 dark:border-amber-500/30 dark:text-amber-400",
    textClass: "text-amber-600 dark:text-amber-400",
    icon: TrendingUp,
  },
  consumer: {
    colorLight: "bg-emerald-50 border-emerald-200 text-emerald-700",
    colorDark: "dark:bg-emerald-500/20 dark:border-emerald-500/30 dark:text-emerald-400",
    textClass: "text-emerald-600 dark:text-emerald-400",
    icon: Users,
  },
  bank: {
    colorLight: "bg-rose-50 border-rose-200 text-rose-700",
    colorDark: "dark:bg-rose-500/20 dark:border-rose-500/30 dark:text-rose-400",
    textClass: "text-rose-600 dark:text-rose-400",
    icon: Landmark,
  },
};

export function ChatInterface({ onSend, placeholder = "Ask a question…", agentType, stateKey }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load chat state from sessionStorage on mount or stateKey changes
  useEffect(() => {
    if (stateKey) {
      try {
        const saved = sessionStorage.getItem(stateKey);
        setMessages(saved ? JSON.parse(saved) : []);
      } catch (e) {
        console.error("Error loading chat state", e);
        setMessages([]);
      }
    } else {
      setMessages([]);
    }
    setLoaded(true);
  }, [stateKey]);

  // Save chat state to sessionStorage when messages or stateKey changes
  useEffect(() => {
    if (!loaded || !stateKey) return;
    try {
      if (messages.length > 0) {
        sessionStorage.setItem(stateKey, JSON.stringify(messages));
      } else {
        sessionStorage.removeItem(stateKey);
      }
    } catch (e) {
      console.error("Error saving chat state", e);
    }
  }, [messages, stateKey, loaded]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const submit = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);
    try {
      const reply = await onSend(text);
      setMessages((m) => [...m, { role: "assistant", content: reply }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", content: `Error: ${String(err)}` }]);
    } finally {
      setLoading(false);
    }
  };

  const defaultThemeConfig = {
    colorLight: "bg-teal-50 border-teal-200 text-teal-700",
    colorDark: "dark:bg-teal-500/20 dark:border-teal-500/30 dark:text-teal-400",
    textClass: "text-teal-600 dark:text-teal-400",
    icon: Bot,
  };
  const activeAgentConfig = CHAT_AGENT_CONFIG[agentType?.toLowerCase() ?? ""] || defaultThemeConfig;

  return (
    <div className="flex flex-col h-full gap-3">
      <Card className="flex-1 flex flex-col min-h-0 border-border/80 shadow-md bg-card/50 backdrop-blur-sm">
        <CardContent className="p-0 flex-1 flex flex-col min-h-0">
          <ScrollArea className="flex-1 min-h-0 p-5">
            {!loaded && stateKey ? (
              <div className="flex flex-col items-center justify-center py-20 text-center select-none flex-1">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/60" />
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-center select-none">
                <div className={cn(
                  "p-4 border rounded-full mb-4 shadow-lg",
                  agentType === "report"
                    ? "bg-indigo-50 border-indigo-200 text-indigo-700 dark:bg-indigo-500/10 dark:border-indigo-500/20 dark:shadow-indigo-500/5 dark:text-indigo-400"
                    : "bg-teal-50 border-teal-200 text-teal-700 dark:bg-teal-500/10 dark:border-teal-500/20 dark:shadow-teal-500/5 dark:text-teal-400"
                )}>
                  <MessageSquareCode className="h-10 w-10 animate-pulse" />
                </div>
                <h3 className="text-sm font-semibold text-foreground">Start the conversation</h3>
                <p className="text-xs text-muted-foreground mt-1 max-w-[280px]">
                  Ask about market prices, demand, production capacity, or agent activities.
                </p>
              </div>
            ) : (
              <div className="space-y-5">
                {messages.map((m, i) => (
                  <div
                    key={i}
                    className={cn(
                      "flex items-start gap-3",
                      m.role === "user" ? "flex-row-reverse" : "flex-row"
                    )}
                  >
                    {/* Avatar block */}
                    {(() => {
                      if (m.role === "user") {
                        return (
                          <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center border shadow-md transition-all duration-300 bg-primary/10 border-primary/20 text-primary dark:bg-primary/20 dark:border-primary/40 dark:text-primary">
                            <User className="h-4 w-4" />
                          </div>
                        );
                      }
                      const Icon = activeAgentConfig.icon;
                      return (
                        <div className={cn(
                          "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center border shadow-md transition-all duration-300", 
                          activeAgentConfig.colorLight, 
                          activeAgentConfig.colorDark
                        )}>
                          <Icon className="h-4 w-4" />
                        </div>
                      );
                    })()}

                    {/* Bubble container */}
                    <div
                      className={cn(
                        "max-w-[78%] rounded-lg px-4 py-3 text-sm leading-relaxed shadow-sm border",
                        m.role === "user"
                          ? "bg-primary/10 border-primary/30 text-foreground whitespace-pre-wrap"
                          : "bg-muted/50 border-border/60 text-foreground"
                      )}
                    >
                      {m.role === "user" ? (
                        m.content
                      ) : (
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                            ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
                            ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
                            li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                            strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
                            code: ({ children }) => <code className="px-1.5 py-0.5 rounded bg-muted-foreground/10 font-mono text-xs">{children}</code>,
                            pre: ({ children }) => <pre className="p-3 rounded bg-secondary/30 border border-border/40 font-mono text-xs overflow-x-auto my-2">{children}</pre>,
                            h1: ({ children }) => <h1 className="text-base font-semibold mt-3 mb-1 text-foreground">{children}</h1>,
                            h2: ({ children }) => <h2 className="text-sm font-semibold mt-3 mb-1 text-foreground">{children}</h2>,
                            h3: ({ children }) => <h3 className="text-xs font-semibold mt-2 mb-1 text-foreground">{children}</h3>,
                            table: ({ children }) => (
                              <div className="overflow-x-auto my-3 border border-border/60 rounded-lg shadow-sm">
                                <table className="min-w-full divide-y divide-border/40 text-xs text-left">
                                  {children}
                                </table>
                              </div>
                            ),
                            thead: ({ children }) => (
                              <thead className="bg-muted/65 text-muted-foreground font-semibold uppercase tracking-wider text-[10px]">
                                {children}
                              </thead>
                            ),
                            tbody: ({ children }) => (
                              <tbody className="divide-y divide-border/20 bg-background/30">
                                {children}
                              </tbody>
                            ),
                            tr: ({ children }) => (
                              <tr className="hover:bg-secondary/15 transition-colors">
                                {children}
                              </tr>
                            ),
                            th: ({ children }) => (
                              <th className="px-3.5 py-2.5 font-semibold text-foreground/90 border-b border-border/40">
                                {children}
                              </th>
                            ),
                            td: ({ children }) => (
                              <td className="px-3.5 py-2.5 text-muted-foreground leading-normal">
                                {children}
                              </td>
                            ),
                          }}
                        >
                          {m.content}
                        </ReactMarkdown>
                      )}
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="flex items-start gap-3 justify-start">
                    <div className={cn(
                      "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center border shadow-md transition-all duration-300", 
                      activeAgentConfig.colorLight, 
                      activeAgentConfig.colorDark
                    )}>
                      <activeAgentConfig.icon className="h-4 w-4" />
                    </div>
                    <div className="bg-muted/50 border border-border/60 rounded-lg px-4 py-3 shadow-md flex items-center gap-2">
                      <Loader2 className={cn("h-4 w-4 animate-spin", activeAgentConfig.textClass)} />
                      <span className="text-xs text-muted-foreground animate-pulse">Thinking...</span>
                    </div>
                  </div>
                )}
                <div ref={bottomRef} />
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>

      <div className="flex gap-2 p-1 bg-muted/20 border border-border/60 rounded-lg focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all duration-200">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && submit()}
          placeholder={placeholder}
          className="flex-1 bg-transparent border-0 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-0"
        />
        <button
          onClick={submit}
          disabled={loading || !input.trim()}
          className="px-3 py-2 rounded-md bg-primary text-primary-foreground disabled:opacity-40 hover:bg-primary/90 transition-all duration-200 shadow-md active:scale-95 flex items-center justify-center"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}

