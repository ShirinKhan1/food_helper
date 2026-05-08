import type { InputHTMLAttributes } from "react";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  const { className = "", ...rest } = props;
  return (
    <input
      className={`w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm text-neutral-900 outline-none ring-emerald-500/30 focus:ring-2 dark:border-white/10 dark:bg-neutral-900 dark:text-neutral-100 ${className}`}
      {...rest}
    />
  );
}
