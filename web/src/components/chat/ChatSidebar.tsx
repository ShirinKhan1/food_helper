"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { deleteChat, updateChatTitle, type ChatListItemPayload } from "@/lib/api/chat";
import { formatChatDate } from "@/lib/utils/formatDate";

type Props = {
  items: ChatListItemPayload[];
  activeId: string | null;
  onCloseMobile?: () => void;
  onNewChat?: () => void;
};

export function ChatSidebar({ items, activeId, onCloseMobile, onNewChat }: Props) {
  const router = useRouter();
  const qc = useQueryClient();

  const openRename = async (id: string, current: string | null) => {
    const title = window.prompt("Новое название чата", current ?? "");
    if (title === null) return;
    const t = title.trim();
    if (!t || t.length > 100) {
      window.alert("Название от 1 до 100 символов.");
      return;
    }
    try {
      await updateChatTitle(id, t);
      await qc.invalidateQueries({ queryKey: ["chats"] });
      onCloseMobile?.();
    } catch {
      window.alert("Не удалось переименовать.");
    }
  };

  const confirmDelete = async (id: string) => {
    if (!window.confirm("Удалить этот чат?")) return;
    try {
      await deleteChat(id);
      await qc.invalidateQueries({ queryKey: ["chats"] });
      if (activeId === id) router.push("/");
      onCloseMobile?.();
    } catch {
      window.alert("Не удалось удалить.");
    }
  };

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-black/10 bg-neutral-50 dark:border-white/10 dark:bg-neutral-950">
      <div className="p-2">
        <Button
          variant="primary"
          className="w-full"
          onClick={() => {
            onNewChat?.();
            router.push("/");
            onCloseMobile?.();
          }}
        >
          Новый чат
        </Button>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-4">
        {items.length === 0 ? (
          <p className="px-2 text-sm text-neutral-500">История пуста. Начните новый диалог.</p>
        ) : (
          <ul className="space-y-1">
            {items.map((c) => {
              const active = c.conversation_id === activeId;
              return (
                <li key={c.conversation_id}>
                  <div
                    className={`group flex items-start gap-1 rounded-lg px-2 py-2 text-left text-sm ${
                      active ? "bg-emerald-100 dark:bg-emerald-900/40" : "hover:bg-black/5 dark:hover:bg-white/5"
                    }`}
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left font-medium text-neutral-900 dark:text-neutral-100"
                      onClick={() => {
                        router.push(`/chat/${c.conversation_id}`);
                        onCloseMobile?.();
                      }}
                    >
                      <span className="line-clamp-2">{c.title || "Без названия"}</span>
                      <span className="mt-0.5 block text-xs font-normal text-neutral-500">
                        {formatChatDate(c.updated_at)}
                      </span>
                    </button>
                    <div className="flex shrink-0 flex-col gap-0.5 opacity-100 sm:opacity-0 sm:group-hover:opacity-100">
                      <button
                        type="button"
                        className="rounded px-1 text-xs text-neutral-500 hover:bg-black/10 dark:hover:bg-white/10"
                        title="Переименовать"
                        onClick={() => void openRename(c.conversation_id, c.title)}
                      >
                        ✎
                      </button>
                      <button
                        type="button"
                        className="rounded px-1 text-xs text-red-600 hover:bg-red-50 dark:hover:bg-red-950/50"
                        title="Удалить"
                        onClick={() => void confirmDelete(c.conversation_id)}
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </nav>
    </aside>
  );
}
