"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";

type LoginResult = {
  role: "student" | "tutor" | "admin";
};

const landingPaths: Record<LoginResult["role"], string> = {
  student: "/aluno",
  tutor: "/tutor",
  admin: "/admin",
};

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await apiFetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        setError("Não foi possível entrar. Confira seus dados e tente novamente.");
        return;
      }
      const user = (await response.json()) as LoginResult;
      router.push(landingPaths[user.role]);
    } catch {
      setError("Não foi possível conectar. Tente novamente em instantes.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <section className="panel" aria-labelledby="login-title">
        <p className="display-title" id="login-title">
          Permaneço
        </p>
        <p className="lead">Um passo de cada vez. Entre para continuar sua jornada.</p>
        <form onSubmit={submit}>
          <label className="field-label" htmlFor="email">
            E-mail
          </label>
          <input
            autoComplete="username"
            className="text-input"
            id="email"
            name="email"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
          <label className="field-label" htmlFor="password">
            Senha
          </label>
          <input
            autoComplete="current-password"
            className="text-input"
            id="password"
            name="password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
          <button className="primary-button" disabled={submitting} type="submit">
            {submitting ? "Entrando..." : "Entrar"}
          </button>
          {error && (
            <p className="error-message" role="alert">
              {error}
            </p>
          )}
        </form>
      </section>
      <div className="ia-indicator" aria-label="Mentora de inteligência artificial">
        <span className="ia-dot" aria-hidden="true" />
        IA
      </div>
    </main>
  );
}
