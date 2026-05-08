export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block size-4 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent ${className}`}
      aria-hidden
    />
  );
}
