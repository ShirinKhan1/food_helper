import type { ClarificationPayload } from "@/lib/api/chat";
import { Button } from "@/components/ui/Button";

type Props = {
  clarification: ClarificationPayload;
  disabled?: boolean;
  onPick: (text: string) => void;
};

export function ClarificationBlock({ clarification, disabled, onPick }: Props) {
  const opts = clarification.options?.filter(Boolean) ?? [];
  return (
    <div className="mt-3 rounded-lg border border-amber-200/80 bg-amber-50/80 p-3 text-sm dark:border-amber-900/50 dark:bg-amber-950/40">
      <p className="font-medium text-amber-950 dark:text-amber-100">{clarification.question}</p>
      {opts.length ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {opts.map((o) => (
            <Button key={o} variant="primary" disabled={disabled} onClick={() => onPick(o)}>
              {o}
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
