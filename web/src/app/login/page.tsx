import { LoginForm } from "@/components/auth/LoginForm";
import Link from "next/link";

export default function LoginPage() {
  return (
    <div className="min-h-[100dvh] bg-background px-4 py-10 text-foreground">
      <div className="mb-8 text-center">
        <Link href="/" className="text-lg font-semibold text-emerald-800 dark:text-emerald-300">
          Food Helper
        </Link>
      </div>
      <LoginForm />
    </div>
  );
}
