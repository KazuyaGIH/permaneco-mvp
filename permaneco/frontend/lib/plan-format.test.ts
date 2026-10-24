import { describe, expect, it } from "vitest";

import { formatDayLabel, formatPlanValue, planKeyLabel } from "./plan-format";

describe("plan formatter", () => {
  it.each(["terca-feira", "terça-feira"])("formats the weekday %s in pt-BR", (day) => {
    expect(formatDayLabel(day)).toBe("Terça-feira");
  });

  it("formats weekly blocks as readable list items", () => {
    const plan = formatPlanValue(
      [{ day: "terca-feira", start: "20:00", end: "21:00", activity: "Leitura" }],
      "weekly_blocks",
    );

    expect(plan.kind).toBe("list");
    if (plan.kind !== "list") return;
    expect(plan.items).toEqual([
      { kind: "text", text: "Terça-feira, 20:00–21:00 — Leitura" },
    ]);
  });

  it("formats arrays as labelled lists", () => {
    const plan = formatPlanValue(["Organizar materiais", "Revisar a aula"], "priorities");

    expect(plan).toEqual({
      kind: "list",
      label: "Prioridades",
      items: [
        { kind: "text", text: "Organizar materiais" },
        { kind: "text", text: "Revisar a aula" },
      ],
    });
  });

  it("humanizes unknown schema keys by replacing underscores", () => {
    expect(planKeyLabel("future_plan_field")).toBe("future plan field");
  });
});
