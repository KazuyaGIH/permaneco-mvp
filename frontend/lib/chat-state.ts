export type ChatMessage = { role: "user" | "assistant"; content: string };

export function restoreConversationMessages(
  messages: Array<{ role: string; content: string }>,
): ChatMessage[] {
  const restored: ChatMessage[] = [];
  for (const { role, content } of messages) {
    if (role === "user" || role === "assistant") restored.push({ role, content });
  }
  return restored;
}

export function replaceLatestUserMessage(
  messages: ChatMessage[],
  content: string,
): ChatMessage[] {
  let latestUserIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "user") {
      latestUserIndex = index;
      break;
    }
  }

  if (latestUserIndex === -1) return messages;
  return messages.map((message, index) =>
    index === latestUserIndex ? { ...message, content } : message,
  );
}
