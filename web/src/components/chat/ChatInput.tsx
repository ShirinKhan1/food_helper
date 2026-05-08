"use client";

import { useCallback, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import { MAX_MESSAGE_CHARS } from "@/lib/constants";

type Props = {
  disabled?: boolean;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  error?: string | null;
};

export function ChatInput({ disabled, value, onChange, onSubmit, error }: Props) {
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = useCallback(() => {
    const t = value.trim();
    if (!t) {
      setLocalError("Введите сообщение");
      return;
    }
    if (t.length > MAX_MESSAGE_CHARS) {
      setLocalError(`Сообщение слишком длинное. Максимум ${MAX_MESSAGE_CHARS} символов.`);
      return;
    }
    setLocalError(null);
    onSubmit();
  }, [onSubmit, value]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled) submit();
    }
  };

  const err = error ?? localError;

  return (
    <div className="border-t border-black/10 bg-background/95 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-white/10">
      {err ? <p className="mb-2 text-sm text-red-600">{err}</p> : null}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <Textarea
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            setLocalError(null);
          }}
          onKeyDown={onKeyDown}
          disabled={disabled}
          placeholder="Напишите запрос…"
          maxLength={MAX_MESSAGE_CHARS + 50}
        />
        <Button variant="primary" className="shrink-0 sm:w-32" disabled={disabled} onClick={submit}>
          Отправить
        </Button>
      </div>
      <p className="mt-1 text-xs text-neutral-500">Enter — отправить, Shift+Enter — новая строка</p>
    </div>
  );
}
