"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";

type SessionUser = { id: string; email: string; role: "student" | "tutor" | "admin" };
type Profile = { preferred_name: string; course: string; semester: number };
type TutorStudent = { user_id: string; preferred_name: string; course: string };

const labels = {
  student: "Seu espaço de estudos",
  tutor: "Acompanhamento de estudantes",
  admin: "Contas da plataforma",
};

export default function RoleLanding({ role }: { role: SessionUser["role"] }) {
  const router = useRouter();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [students, setStudents] = useState<TutorStudent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const response = await apiFetch("/api/auth/me");
        if (!response.ok) {
          router.replace("/");
          return;
        }
        const currentUser = (await response.json()) as SessionUser;
        if (!active) return;
        if (currentUser.role !== role) {
          router.replace(
            currentUser.role === "student"
              ? "/aluno"
              : currentUser.role === "tutor"
                ? "/tutor"
                : "/admin",
          );
          return;
        }
        setUser(currentUser);
        if (role === "student") {
          const profileResponse = await apiFetch("/api/me/profile");
          if (profileResponse.ok && active) setProfile((await profileResponse.json()) as Profile);
        }
        if (role === "tutor") {
          const listResponse = await apiFetch("/api/tutor/students");
          if (listResponse.ok && active) setStudents((await listResponse.json()) as TutorStudent[]);
        }
      } catch {
        if (active) setError("Não foi possível carregar seu espaço agora.");
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [role, router]);

  async function logout() {
    await apiFetch("/api/auth/logout", { method: "POST" });
    router.replace("/");
  }

  return (
    <main className="page-shell">
      <section className="panel" aria-labelledby="landing-title">
        <h1 className="display-title" id="landing-title">
          {labels[role]}
        </h1>
        {user ? (
          <>
            <p className="lead">Olá, {profile?.preferred_name ?? user.email}. Que bom ter você aqui.</p>
            <div className="account-card">
              <strong>Conta:</strong> {user.email}
              {profile && (
                <p>
                  {profile.course} · {profile.semester}º semestre
                </p>
              )}
            </div>
            {role === "tutor" && (
              <div className="account-card">
                <h2>Estudantes atribuídos</h2>
                {students.length ? (
                  <ul className="student-list">
                    {students.map((student) => (
                      <li key={student.user_id}>
                        {student.preferred_name} · {student.course}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>Nenhum estudante atribuído.</p>
                )}
              </div>
            )}
            <button className="primary-button" onClick={logout} type="button">
              Sair
            </button>
          </>
        ) : (
          <p className="lead">{error || "Carregando seu espaço..."}</p>
        )}
        <Link href="/" className="field-label">
          Voltar ao início
        </Link>
      </section>
      <div className="ia-indicator" aria-label="Mentora de inteligência artificial">
        <span className="ia-dot" aria-hidden="true" />
        IA
      </div>
    </main>
  );
}
