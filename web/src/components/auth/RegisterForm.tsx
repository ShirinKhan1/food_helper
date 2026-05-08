"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { register as registerUser } from "@/lib/api/auth";
import { ApiRequestError } from "@/lib/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

const schema = z
  .object({
    email: z.string().min(1, "Введите email").email("Некорректный email"),
    password: z.string().min(8, "Минимум 8 символов"),
    password2: z.string().min(1, "Повторите пароль"),
  })
  .refine((d) => d.password === d.password2, { message: "Пароли не совпадают", path: ["password2"] });

type Form = z.infer<typeof schema>;

export function RegisterForm() {
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
      const r = await registerUser(data.email, data.password);
      qc.setQueryData(["me"], { user: r.user });
      await qc.invalidateQueries({ queryKey: ["me"] });
      router.push("/");
      router.refresh();
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 409) {
        setApiError("Этот email уже зарегистрирован.");
      } else {
        setApiError("Не удалось зарегистрироваться. Попробуйте позже.");
      }
    }
  };

  return (
    <form className="mx-auto flex max-w-md flex-col gap-4" onSubmit={handleSubmit(onValid)}>
      <h1 className="text-2xl font-semibold">Регистрация</h1>
      {apiError ? <p className="text-sm text-red-600">{apiError}</p> : null}
      <div>
        <label className="mb-1 block text-sm text-neutral-600 dark:text-neutral-300">Email</label>
        <Input type="email" autoComplete="email" {...register("email")} />
        {errors.email ? <p className="mt-1 text-xs text-red-600">{errors.email.message}</p> : null}
      </div>
      <div>
        <label className="mb-1 block text-sm text-neutral-600 dark:text-neutral-300">Пароль</label>
        <Input type="password" autoComplete="new-password" {...register("password")} />
        {errors.password ? <p className="mt-1 text-xs text-red-600">{errors.password.message}</p> : null}
      </div>
      <div>
        <label className="mb-1 block text-sm text-neutral-600 dark:text-neutral-300">Повтор пароля</label>
        <Input type="password" autoComplete="new-password" {...register("password2")} />
        {errors.password2 ? <p className="mt-1 text-xs text-red-600">{errors.password2.message}</p> : null}
      </div>
      <Button variant="primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Регистрация…" : "Зарегистрироваться"}
      </Button>
      <p className="text-sm text-neutral-600 dark:text-neutral-300">
        Уже есть аккаунт?{" "}
        <Link href="/login" className="text-emerald-700 underline dark:text-emerald-400">
          Войти
        </Link>
      </p>
    </form>
  );
}
