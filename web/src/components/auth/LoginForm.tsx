"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { login } from "@/lib/api/auth";
import { ApiRequestError } from "@/lib/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

const schema = z.object({
  email: z.string().min(1, "Введите email").email("Некорректный email"),
  password: z.string().min(1, "Введите пароль"),
});

type Form = z.infer<typeof schema>;

export function LoginForm() {
  const router = useRouter();
  const qc = useQueryClient();
  const [apiError, setApiError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  const onValid = async (data: Form) => {
    setApiError(null);
    try {
      const r = await login(data.email, data.password);
      qc.setQueryData(["me"], { user: r.user });
      await qc.invalidateQueries({ queryKey: ["me"] });
      router.push("/");
      router.refresh();
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 401) {
        setApiError("Неверный email или пароль.");
      } else {
        setApiError("Не удалось войти. Попробуйте позже.");
      }
    }
  };

  return (
    <form className="mx-auto flex max-w-md flex-col gap-4" onSubmit={handleSubmit(onValid)}>
      <h1 className="text-2xl font-semibold">Вход</h1>
      {apiError ? <p className="text-sm text-red-600">{apiError}</p> : null}
      <div>
        <label className="mb-1 block text-sm text-neutral-600 dark:text-neutral-300">Email</label>
        <Input type="email" autoComplete="email" {...register("email")} />
        {errors.email ? <p className="mt-1 text-xs text-red-600">{errors.email.message}</p> : null}
      </div>
      <div>
        <label className="mb-1 block text-sm text-neutral-600 dark:text-neutral-300">Пароль</label>
        <Input type="password" autoComplete="current-password" {...register("password")} />
        {errors.password ? <p className="mt-1 text-xs text-red-600">{errors.password.message}</p> : null}
      </div>
      <Button variant="primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Вход…" : "Войти"}
      </Button>
      <p className="text-sm text-neutral-600 dark:text-neutral-300">
        Нет аккаунта?{" "}
        <Link href="/register" className="text-emerald-700 underline dark:text-emerald-400">
          Зарегистрироваться
        </Link>
      </p>
    </form>
  );
}
