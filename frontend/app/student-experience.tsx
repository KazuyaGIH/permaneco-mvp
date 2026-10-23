"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";

import { apiFetch } from "@/lib/api";
import { replaceLatestUserMessage, type ChatMessage } from "@/lib/chat-state";
import { formatPlanValue, type FormattedPlanNode } from "@/lib/plan-format";
import { safeLink } from "@/lib/safe-links";

type Profile = { preferred_name: string; course: string; semester: number };
type ConsentState = {
  texts: Record<string, { version: string; text: string }>;
  accepted: Record<string, boolean>;
  age_confirmed: boolean;
  chat_allowed: boolean;
  minor_message: string | null;
};
type PlanData = {
  current: null | {
    version: number;
    plan: Record<string, unknown>;
    change_summary: string | null;
  };
  sources: { slug: string; title: string; source_url: string; kind: string }[];
};
type Proposal = { id: string; section: string; change: string };

const sections = ["estudos", "carreira", "financas"] as const;
const sectionLabels: Record<(typeof sections)[number], string> = {
  estudos: "Estudos",
  carreira: "Carreira",
  financas: "Finanças",
};
const studentTabs = [
  { id: "chat", label: "Conversa" },
  { id: "plan", label: "Meu Plano" },
  { id: "memories", label: "O que a Permaneço lembra" },
] as const;
type StudentTab = (typeof studentTabs)[number]["id"];

function PlanNodeView({ node }: { node: FormattedPlanNode }) {
  if (node.kind === "text") {
    return (
      <p>
        {node.label && <strong>{node.label}: </strong>}
        {node.text}
      </p>
    );
  }

  return (
    <section className={node.kind === "list" ? "plan-section" : "plan-group"}>
      {node.label && <h3>{node.label}</h3>}
      <ul>
        {node.items.map((item, index) => (
          <li key={`${item.kind}-${index}`}>
            <PlanNodeView node={item} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function PlanContent({ value }: { value: unknown }) {
  return (
    <div className="plan-content">
      <PlanNodeView node={formatPlanValue(value)} />
    </div>
  );
}

export default function StudentExperience() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [consents, setConsents] = useState<ConsentState | null>(null);
  const [memoryAccepted, setMemoryAccepted] = useState(false);
  const [voiceAccepted, setVoiceAccepted] = useState(false);
  const [ageConfirmed, setAgeConfirmed] = useState(false);
  const [riskAccepted, setRiskAccepted] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [plan, setPlan] = useState<PlanData | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [memories, setMemories] = useState<{ id: string; category: string; content: string }[]>([]);
  const [section, setSection] = useState<(typeof sections)[number]>("estudos");
  const [tab, setTab] = useState<StudentTab>("chat");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const chatTranscriptRef = useRef<HTMLDivElement | null>(null);

  const loadPlan = useCallback(async () => {
    const [planResponse, proposalResponse] = await Promise.all([
      apiFetch("/api/me/plan"),
      apiFetch("/api/me/plan/proposals"),
    ]);
    if (planResponse.ok) setPlan((await planResponse.json()) as PlanData);
    if (proposalResponse.ok) setProposals((await proposalResponse.json()) as Proposal[]);
  }, []);

  const loadMemories = useCallback(async () => {
    const response = await apiFetch("/api/me/memories");
    if (response.ok) setMemories((await response.json()) as typeof memories);
  }, []);

  useEffect(() => {
    let active = true;
    async function load() {
      const [profileResponse, consentResponse] = await Promise.all([
        apiFetch("/api/me/profile"),
        apiFetch("/api/me/consents"),
      ]);
      if (!active || !profileResponse.ok || !consentResponse.ok) return;
      const nextProfile = (await profileResponse.json()) as Profile;
      const nextConsents = (await consentResponse.json()) as ConsentState;
      setProfile(nextProfile);
      setConsents(nextConsents);
      setMemoryAccepted(nextConsents.accepted.memory);
      setVoiceAccepted(nextConsents.accepted.voice);
      setAgeConfirmed(nextConsents.age_confirmed);
      setRiskAccepted(nextConsents.accepted.risk_protocol);
      if (nextConsents.chat_allowed) {
        await Promise.all([loadPlan(), loadMemories()]);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [loadMemories, loadPlan]);

  useEffect(() => {
    const transcript = chatTranscriptRef.current;
    if (tab === "chat" && transcript) {
      transcript.scrollTop = transcript.scrollHeight;
    }
  }, [messages, tab]);

  async function saveConsents(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const response = await apiFetch("/api/me/consents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        age_confirmed: ageConfirmed,
        memory_accepted: memoryAccepted,
        voice_accepted: voiceAccepted,
        risk_protocol_accepted: riskAccepted,
      }),
    });
    if (response.ok) {
      const refreshed = await apiFetch("/api/me/consents");
      if (refreshed.ok) setConsents((await refreshed.json()) as ConsentState);
      setNotice("Preferências salvas.");
      await Promise.all([loadPlan(), loadMemories()]);
    } else {
      const error = (await response.json()) as { detail?: string };
      setNotice(error.detail ?? "Não foi possível salvar suas preferências.");
    }
    setBusy(false);
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.trim() || busy) return;
    const text = draft.trim();
    setDraft("");
    setMessages((current) => [...current, { role: "user", content: text }, { role: "assistant", content: "" }]);
    setBusy(true);
    try {
      let id = conversationId;
      if (!id) {
        const created = await apiFetch("/api/chat/conversations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind: "boas_vindas" }),
        });
        if (!created.ok) throw new Error("Não foi possível iniciar a conversa.");
        id = ((await created.json()) as { id: string }).id;
        setConversationId(id);
      }
      const response = await apiFetch(`/api/chat/conversations/${id}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!response.ok || !response.body) throw new Error("Não foi possível enviar sua mensagem.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistantText = "";
      const processEvent = (rawEvent: string) => {
        const lines = rawEvent.split("\n");
        const eventName = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
        const data = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
        if (eventName === "done" || eventName === "error") setNotice("");
        if (!eventName || !data) return;
        const payload = JSON.parse(data) as {
          content?: string;
          text?: string;
          message?: string;
          name?: string;
          replace?: boolean;
        };
        if (eventName === "delta" && payload.text) {
          assistantText = payload.replace ? payload.text : assistantText + payload.text;
          setMessages((current) => current.map((item, index) =>
            index === current.length - 1 ? { ...item, content: assistantText } : item,
          ));
        } else if (eventName === "error") {
          assistantText = payload.message ?? "Não foi possível responder agora.";
          setMessages((current) => current.map((item, index) =>
            index === current.length - 1 ? { ...item, content: assistantText } : item,
          ));
        } else if (eventName === "user_message" && typeof payload.content === "string") {
          const content = payload.content;
          setMessages((current) => replaceLatestUserMessage(current, content));
        } else if (eventName === "tool") {
          setNotice("A mentora está consultando seus próximos passos.");
        }
      };
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        events.forEach(processEvent);
      }
      if (buffer) processEvent(buffer);
      await loadPlan();
    } catch (error) {
      setNotice("");
      const message = error instanceof Error ? error.message : "Ocorreu um erro.";
      setMessages((current) => current.map((item, index) =>
        index === current.length - 1 ? { ...item, content: message } : item,
      ));
    } finally {
      setBusy(false);
    }
  }

  async function endConversation() {
    if (!conversationId) return;
    const response = await apiFetch(`/api/chat/conversations/${conversationId}/end`, { method: "POST" });
    setNotice(response.ok ? "Conversa encerrada. Seu resumo e plano estão sendo atualizados." : "Não foi possível encerrar agora.");
    setConversationId("");
    setMessages([]);
  }

  async function respondToProposal(id: string, action: "confirm" | "reject") {
    const response = await apiFetch(`/api/me/plan/proposals/${id}/${action}`, { method: "POST" });
    setNotice(response.ok ? "Sua resposta foi registrada." : "Não foi possível registrar sua resposta.");
    await loadPlan();
  }

  async function forgetMemory(id: string) {
    await apiFetch(`/api/me/memories/${id}`, { method: "DELETE" });
    await loadMemories();
  }

  function selectTab(nextTab: StudentTab) {
    setTab(nextTab);
    if (nextTab === "plan") void loadPlan();
    if (nextTab === "memories") void loadMemories();
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const selectedIndex = studentTabs.findIndex((item) => item.id === tab);
    let nextIndex = selectedIndex;
    if (event.key === "ArrowRight") nextIndex = (selectedIndex + 1) % studentTabs.length;
    if (event.key === "ArrowLeft") {
      nextIndex = (selectedIndex - 1 + studentTabs.length) % studentTabs.length;
    }
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = studentTabs.length - 1;
    if (nextIndex === selectedIndex) return;

    event.preventDefault();
    const nextTab = studentTabs[nextIndex];
    if (!nextTab) return;
    selectTab(nextTab.id);
    document.getElementById(`student-tab-${nextTab.id}`)?.focus();
  }

  return (
    <main className="page-shell">
      <section className="panel" aria-labelledby="student-title">
        <h1 className="display-title" id="student-title">Seu espaço de estudos</h1>
        {!profile || !consents ? (
          <p className="lead">Carregando…</p>
        ) : (
          <>
            <p className="lead">
              Olá, {profile.preferred_name}. {profile.course} · {profile.semester}º semestre.
            </p>
            {notice && <p role="status">{notice}</p>}
            {consents.minor_message ? (
              <p className="account-card">{consents.minor_message}</p>
            ) : !consents.chat_allowed ? (
              <form className="account-card" onSubmit={saveConsents}>
                <h2>Antes de começar</h2>
                <p>Suas mensagens ficam protegidas. A mentora usa IA e não substitui o apoio da instituição.</p>
                <div className="consent-options">
                  <label className="consent-option">
                    <input type="checkbox" checked={ageConfirmed} onChange={(event) => setAgeConfirmed(event.target.checked)} />
                    Tenho 18 anos ou mais.
                  </label>
                  <label className="consent-option">
                    <input type="checkbox" checked={memoryAccepted} onChange={(event) => setMemoryAccepted(event.target.checked)} />
                    Aceito memórias opcionais para retomar conversas.
                  </label>
                  <label className="consent-option">
                    <input type="checkbox" checked={voiceAccepted} onChange={(event) => setVoiceAccepted(event.target.checked)} />
                    Aceito o uso opcional de voz.
                  </label>
                </div>
                <p className="risk-protocol">{consents.texts.risk_protocol.text}</p>
                <label className="consent-option">
                  <input type="checkbox" checked={riskAccepted} onChange={(event) => setRiskAccepted(event.target.checked)} />
                  Li e entendi o protocolo de risco.
                </label>
                <button className="primary-button" type="submit" disabled={busy || !ageConfirmed || !riskAccepted}>Entendi e continuar</button>
              </form>
            ) : (
              <>
                <div className="student-tabs" role="tablist" aria-label="Área do estudante" onKeyDown={handleTabKeyDown}>
                  {studentTabs.map((item) => (
                    <button
                      key={item.id}
                      id={`student-tab-${item.id}`}
                      type="button"
                      role="tab"
                      aria-selected={tab === item.id}
                      aria-controls={`student-panel-${item.id}`}
                      tabIndex={tab === item.id ? 0 : -1}
                      className="student-tab"
                      onClick={() => selectTab(item.id)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
                <div
                  id="student-panel-chat"
                  role="tabpanel"
                  aria-labelledby="student-tab-chat"
                  tabIndex={0}
                  hidden={tab !== "chat"}
                  className="account-card tab-panel"
                >
                  <div ref={chatTranscriptRef} className="chat-transcript" aria-live="polite">
                    {messages.map((message, index) => (
                      <div
                        key={`${index}-${message.role}`}
                        className={`chat-bubble chat-bubble-${message.role}`}
                      >
                        <strong>{message.role === "user" ? "Você" : "Permaneço (IA)"}</strong>
                        <p>{message.content}</p>
                      </div>
                    ))}
                  </div>
                  <form onSubmit={sendMessage}>
                    <label className="field-label" htmlFor="chat-message">Sua mensagem</label>
                    <textarea id="chat-message" maxLength={2000} value={draft} onChange={(event) => setDraft(event.target.value)} disabled={busy} />
                    <button className="primary-button" type="submit" disabled={busy || !draft.trim()}>Enviar</button>
                    {conversationId && <button type="button" onClick={endConversation}>Encerrar conversa</button>}
                  </form>
                </div>
                <div
                  id="student-panel-plan"
                  role="tabpanel"
                  aria-labelledby="student-tab-plan"
                  tabIndex={0}
                  hidden={tab !== "plan"}
                  className="account-card tab-panel"
                >
                  <h2>Meu Plano</h2>
                  {sections.map((item) => (
                    <button
                      key={item}
                      type="button"
                      className={`section-tab${section === item ? " is-active" : ""}`}
                      onClick={() => setSection(item)}
                      aria-pressed={section === item}
                    >
                      {sectionLabels[item]}
                    </button>
                  ))}
                  {plan?.current?.plan?.[section] == null ? (
                    <p>Seu plano ainda está sendo preparado.</p>
                  ) : (
                    <PlanContent value={plan.current.plan[section]} />
                  )}
                  <p>Confirme informações acadêmicas e financeiras com a instituição.</p>
                  {plan?.sources.map((source) => {
                    const href = safeLink(source.source_url);
                    return href ? <p key={source.slug}><a href={href} rel="noreferrer">{source.title} — confirmar com a instituição</a></p> : null;
                  })}
                  {proposals.map((proposal) => (
                    <div key={proposal.id}>
                      <p>Proposta de {proposal.section}: {proposal.change}</p>
                      <button type="button" onClick={() => respondToProposal(proposal.id, "confirm")}>Confirmar</button>
                      <button type="button" onClick={() => respondToProposal(proposal.id, "reject")}>Rejeitar</button>
                    </div>
                  ))}
                </div>
                <div
                  id="student-panel-memories"
                  role="tabpanel"
                  aria-labelledby="student-tab-memories"
                  tabIndex={0}
                  hidden={tab !== "memories"}
                  className="account-card tab-panel"
                >
                  <h2>O que a Permaneço lembra de mim</h2>
                  {memories.map((memory) => (
                    <p key={memory.id}>{memory.content} <button type="button" onClick={() => forgetMemory(memory.id)}>Apagar</button></p>
                  ))}
                  {!memories.length && <p>Nenhuma memória ativa.</p>}
                </div>
              </>
            )}
          </>
        )}
      </section>
      <div className="ia-indicator" aria-label="Mentora de inteligência artificial">
        <span className="ia-dot" aria-hidden="true" /> IA
      </div>
    </main>
  );
}
