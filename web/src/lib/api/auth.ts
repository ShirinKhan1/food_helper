import { apiFetchJson } from "./client";

export type UserPublic = {
  id: string;
  email: string;
  created_at: string;
};

export async function register(email: string, password: string): Promise<{ user: UserPublic }> {
  return apiFetchJson("/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<{ user: UserPublic }> {
  return apiFetchJson("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function logout(): Promise<{ ok: boolean }> {
  return apiFetchJson("/v1/auth/logout", { method: "POST" });
}

export async function getMe(): Promise<{ user: UserPublic | null }> {
  return apiFetchJson("/v1/auth/me");
}
