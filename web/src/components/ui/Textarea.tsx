import type { TextareaHTMLAttributes } from "react";

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { className = "", ...rest } = props;
  return (
    <textarea
      className={`min-h-[88px] w-full resize-y rounded-xl border border-black/10 bg-white px-3 py-2 text-sm text-neutral-900 outline-none ring-emerald-500/30 focus:ring-2 dark:border-white/10 dark:bg-neutral-900 dark:text-neutral-100 ${className}`}
      {...rest}
    />
  );
}
