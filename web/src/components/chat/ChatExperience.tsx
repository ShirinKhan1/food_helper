"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getMe, logout } from "@/lib/api/auth";
import { ApiRequestError } from "@/lib/api/client";
import {
  getChat,
  getChats,
  sendChatMessage,
  type ChatMessagePayload,
  type ChatResponsePayload,
} from "@/lib/api/chat";
import { ChatInput } from "@/components/chat/ChatInput";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { ClarificationBlock } from "@/components/chat/ClarificationBlock";
import { NutritionBlock, SourcesBlock, SubstitutionsBlock } from "@/components/chat/ContentBlocks";
import { RecipeCard } from "@/components/chat/RecipeCard";
import { RecipeDetailModal } from "@/components/chat/RecipeDetailModal";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useUiStore } from "@/stores/uiStore";

export type ChatUiMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: ChatResponsePayload;
  status?: "pending" | "success" | "error";
};

const EXAMPLES = [
  "Легкий ужин с курицей без грибов",
  "Завтрак без молока до 300 ккал",
  "Чем заменить сахар в выпечке?",
  "Что приготовить из творога и банана?",
];

type Props = {
  conversationIdFromUrl?: string | null;
};

export function ChatExperience({ conversationIdFromUrl = null }: Props) {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: meData, isLoading: meLoading } = useQuery({ queryKey: ["me"], queryFn: getMe });
  const user = meData?.user ?? null;
  const authed = !!user;

  const { data: chatsData } = useQuery({
    queryKey: ["chats"],
    queryFn: getChats,
    enabled: authed,
  });
  const chats = chatsData?.items ?? [];

  const [messages, setMessages] = useState<ChatUiMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const recipeModalId = useUiStore((s) => s.recipeModalId);
  const setRecipeModalId = useUiStore((s) => s.setRecipeModalId);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const loadedChatRef = useRef<string | null>(null);

  useEffect(() => {
    loadedChatRef.current = null;
  }, [conversationIdFromUrl]);

  useEffect(() => {
    if (!conversationIdFromUrl) return;
    if (meLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    if (loadedChatRef.current === conversationIdFromUrl) return;
    let cancelled = false;
    (async () => {
      try {
        const d = await getChat(conversationIdFromUrl);
        if (cancelled) return;
        setConversationId(d.conversation_id);
        setMessages(
          d.messages.map((m: ChatMessagePayload) => ({
            id: `hist-${m.id}`,
            role: m.role,
            content: m.content,
            status: "success" as const,
          })),
        );
        loadedChatRef.current = conversationIdFromUrl;
      } catch {
        if (!cancelled) router.replace("/");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationIdFromUrl, user, meLoading, router]);

  const hasThread = messages.length > 0;
  const activeChatId = conversationIdFromUrl ?? conversationId;

  const sendWithText = useCallback(
    async (rawText: string) => {
      const text = rawText.trim();
      if (!text) {
        setInputError("Введите сообщение");
        return;
      }
      setInputError(null);
      setSending(true);
      const userMsg: ChatUiMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
        status: "success",
      };
      const pendingId = crypto.randomUUID();
      const pendingAssistant: ChatUiMessage = {
        id: pendingId,
        role: "assistant",
        content: "",
        status: "pending",
      };
      setMessages((prev) => [...prev, userMsg, pendingAssistant]);
      if (!conversationIdFromUrl) setDraft("");
      try {
        const res = await sendChatMessage({
          conversation_id: conversationId,
          message: text,
          options: { top_k: 5 },
        });
        setConversationId(res.conversation_id);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === pendingId
              ? {
                  ...m,
                  content: res.answer,
                  response: res,
                  status: "success",
                }
              : m,
          ),
        );
        setDraft("");
        if (authed) await qc.invalidateQueries({ queryKey: ["chats"] });
      } catch (e) {
        const msg =
          e instanceof ApiRequestError
            ? e.status >= 500
              ? (() => {
                  const d = e.message?.trim();
                  if (d && d !== "Request failed") return d;
                  return "Сервис временно недоступен (ошибка сервера). Проверьте логи API и что БД/Ollama доступны.";
                })()
              : "Не получилось получить ответ. Попробуйте еще раз."
            : "Не удалось связаться с API. Запустите backend на :8000 или задайте NEXT_PUBLIC_API_BASE_URL / API_PROXY_TARGET (см. README).";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === pendingId
              ? {
                  ...m,
                  content: msg,
                  status: "error",
                }
              : m,
          ),
        );
      } finally {
        setSending(false);
      }
    },
    [authed, conversationId, conversationIdFromUrl, qc],
  );

  const onSubmit = () => void sendWithText(draft);

  const resetChat = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setDraft("");
    loadedChatRef.current = null;
  }, []);

  const header = useMemo(
    () => (
      <header className="flex items-center justify-between gap-2 border-b border-black/10 px-3 py-2 dark:border-white/10">
        <div className="flex items-center gap-2">
          {authed ? (
            <button
              type="button"
              className="rounded-lg p-2 text-neutral-700 hover:bg-black/5 sm:hidden dark:text-neutral-200 dark:hover:bg-white/10"
              aria-label="История"
              onClick={() => setSidebarOpen(true)}
            >
              ☰
            </button>
          ) : null}
          <Link href="/" className="text-lg font-semibold text-emerald-800 dark:text-emerald-300">
            Food Helper
          </Link>
        </div>
        <div className="flex items-center gap-2">
          {authed ? (
            <>
              <span className="hidden max-w-[10rem] truncate text-xs text-neutral-500 sm:inline">{user.email}</span>
              <Button
                variant="ghost"
                className="!px-2 text-sm"
                onClick={() => {
                  void logout().then(() => {
                    qc.setQueryData(["me"], { user: null });
                    qc.removeQueries({ queryKey: ["chats"] });
                    router.push("/");
                    router.refresh();
                  });
                }}
              >
                Выйти
              </Button>
            </>
          ) : (
            <>
              <Link href="/login">
                <Button variant="ghost" className="!px-2 text-sm">
                  Войти
                </Button>
              </Link>
              <Link href="/register">
                <Button variant="primary" className="!px-2 text-sm">
                  Зарегистрироваться
                </Button>
              </Link>
            </>
          )}
        </div>
      </header>
    ),
    [authed, qc, router, user],
  );

  const mainClass = "flex min-h-0 flex-1 flex-col";

  return (
    <div className="flex h-[100dvh] flex-col bg-background text-foreground">
      {header}
      <div className="relative flex min-h-0 flex-1">
        {authed ? (
          <>
            <div className="hidden h-full sm:block">
              <ChatSidebar items={chats} activeId={activeChatId} onNewChat={resetChat} />
            </div>
            {sidebarOpen ? (
              <div className="fixed inset-0 z-40 flex sm:hidden">
                <button type="button" className="absolute inset-0 bg-black/40" aria-label="Закрыть" onClick={() => setSidebarOpen(false)} />
                <div className="relative z-50 h-full shadow-xl">
                  <ChatSidebar
                    items={chats}
                    activeId={activeChatId}
                    onCloseMobile={() => setSidebarOpen(false)}
                    onNewChat={resetChat}
                  />
                </div>
              </div>
            ) : null}
          </>
        ) : null}
        <div className={mainClass}>
          <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
            {!hasThread ? (
              <div className="mx-auto flex max-w-2xl flex-col items-center gap-6 pt-8 text-center">
                <div>
                  <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-50">Что приготовить сегодня?</h1>
                  <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">
                    Напишите, какие продукты есть дома, что нельзя есть или какую цель хотите учесть.
                  </p>
                </div>
                <div className="grid w-full gap-2 sm:grid-cols-2">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex}
                      type="button"
                      className="rounded-xl border border-black/10 bg-white px-3 py-2 text-left text-sm text-neutral-800 hover:border-emerald-500/40 dark:border-white/10 dark:bg-neutral-900 dark:text-neutral-100"
                      onClick={() => {
                        setDraft(ex);
                      }}
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mx-auto flex max-w-3xl flex-col gap-4 pb-8">
                {messages.map((m) => (
                  <MessageBubble
                    key={m.id}
                    message={m}
                    sending={sending}
                    onRecipeDetails={setRecipeModalId}
                    onClarificationPick={(t) => void sendWithText(t)}
                  />
                ))}
              </div>
            )}
          </div>
          <ChatInput
            disabled={sending}
            value={draft}
            onChange={setDraft}
            onSubmit={onSubmit}
            error={inputError}
          />
        </div>
      </div>
      <RecipeDetailModal recipeId={recipeModalId} onClose={() => setRecipeModalId(null)} />
    </div>
  );
}

function MessageBubble({
  message,
  sending,
  onRecipeDetails,
  onClarificationPick,
}: {
  message: ChatUiMessage;
  sending: boolean;
  onRecipeDetails: (id: number) => void;
  onClarificationPick: (t: string) => void;
}) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[90%] rounded-2xl px-4 py-2 text-sm ${
          isUser
            ? "bg-emerald-700 text-white"
            : message.status === "error"
              ? "bg-red-50 text-red-900 dark:bg-red-950/50 dark:text-red-100"
              : "bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-50"
        }`}
      >
        {message.status === "pending" ? (
          <div className="flex items-center gap-2 text-neutral-600 dark:text-neutral-300">
            <Spinner />
            Food Helper подбирает рецепты…
          </div>
        ) : (
          <p className="whitespace-pre-wrap">{message.content}</p>
        )}
        {!isUser && message.response && message.status === "success" ? (
          <div className="mt-3 space-y-3 border-t border-black/10 pt-3 dark:border-white/10">
            {message.response.recipes?.length ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {message.response.recipes.map((r) => (
                  <RecipeCard key={r.recipe_id} recipe={r} onDetails={onRecipeDetails} />
                ))}
              </div>
            ) : null}
            {message.response.selected_recipe ? (
              <Button variant="ghost" className="!px-0 text-emerald-800 dark:text-emerald-300" onClick={() => onRecipeDetails(message.response!.selected_recipe!.recipe_id)}>
                Выбранный рецепт: {message.response.selected_recipe.title} — подробнее
              </Button>
            ) : null}
            {message.response.nutrition ? <NutritionBlock nutrition={message.response.nutrition} /> : null}
            {message.response.substitutions?.length ? (
              <SubstitutionsBlock items={message.response.substitutions} />
            ) : null}
            {message.response.sources?.length ? <SourcesBlock sources={message.response.sources} /> : null}
            {message.response.requires_clarification && message.response.clarification ? (
              <ClarificationBlock
                clarification={message.response.clarification}
                disabled={sending}
                onPick={onClarificationPick}
              />
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
