import { RegisterForm } from "@/components/auth/RegisterForm";
import Link from "next/link";

export default function RegisterPage() {
  return (
    <div className="min-h-[100dvh] bg-background px-4 py-10 text-foreground">
      <div className="mb-8 text-center">
        <Link href="/" className="text-lg font-semibold text-emerald-800 dark:text-emerald-300">
          Food Helper
        </Link>
      </div>
      <RegisterForm />
    </div>
  );
}
