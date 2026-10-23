import { describe, expect, it } from "vitest";

import { replaceLatestUserMessage } from "./chat-state";

describe("chat state", () => {
  it("replaces the latest optimistic user message with server content", () => {
    const messages = [
      { role: "user" as const, content: "Pergunta anterior" },
      { role: "assistant" as const, content: "Resposta" },
      { role: "user" as const, content: "CPF 529.982.247-25" },
      { role: "assistant" as const, content: "" },
    ];

    expect(replaceLatestUserMessage(messages, "CPF [CPF removido]")).toEqual([
      { role: "user", content: "Pergunta anterior" },
      { role: "assistant", content: "Resposta" },
      { role: "user", content: "CPF [CPF removido]" },
      { role: "assistant", content: "" },
    ]);
  });
});
