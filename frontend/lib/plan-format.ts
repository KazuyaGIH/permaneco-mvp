export type FormattedPlanNode =
  | { kind: "text"; label?: string; text: string }
  | { kind: "list"; label?: string; items: FormattedPlanNode[] }
  | { kind: "object"; label?: string; items: FormattedPlanNode[] };

const planLabels: Record<string, string> = {
  estudos: "Estudos",
  carreira: "Carreira",
  financas: "Finanças",
  change_summary: "Resumo das mudanças",
  weekly_blocks: "Blocos de estudo da semana",
  day: "Dia",
  start: "Início",
  end: "Término",
  activity: "Atividade",
  priorities: "Prioridades",
  exam_strategy: "Estratégia para as provas",
  paths: "Caminhos profissionais",
  title: "Área de atuação",
  steps: "Etapas",
  knowledge_ids: "Materiais de referência",
  monthly_income: "Renda mensal",
  fixed_expenses: "Despesas fixas",
  tuition: "Mensalidade",
  balance: "Saldo mensal",
  actions: "Ações",
  auxilios: "Auxílios",
  knowledge_id: "Material de referência",
};

const weekdayLabels: Record<string, string> = {
  domingo: "Domingo",
  "segunda-feira": "Segunda-feira",
  "terca-feira": "Terça-feira",
  "quarta-feira": "Quarta-feira",
  "quinta-feira": "Quinta-feira",
  "sexta-feira": "Sexta-feira",
  "sabado-feira": "Sábado",
  segunda: "Segunda-feira",
  terca: "Terça-feira",
  quarta: "Quarta-feira",
  quinta: "Quinta-feira",
  sexta: "Sexta-feira",
  sabado: "Sábado",
  "domingo-feira": "Domingo",
};

const moneyKeys = new Set(["monthly_income", "fixed_expenses", "tuition", "balance"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function planKeyLabel(key: string): string {
  return planLabels[key] ?? key.replaceAll("_", " ");
}

export function formatDayLabel(value: string): string {
  const normalized = value
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR");
  const label = weekdayLabels[normalized];
  if (label) return label;
  return value.trim()
    ? value.trim().charAt(0).toLocaleUpperCase("pt-BR") + value.trim().slice(1)
    : "Dia não informado";
}

function formatScalar(value: unknown, key?: string): string {
  if (value === null || value === undefined) return "Não informado";
  if (key === "day" && typeof value === "string") return formatDayLabel(value);
  if (typeof value === "number" && moneyKeys.has(key ?? "")) {
    return new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency: "BRL",
    }).format(value);
  }
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  return String(value);
}

function formatWeeklyBlock(value: unknown): FormattedPlanNode {
  if (!isRecord(value)) return { kind: "text", text: formatScalar(value) };

  const day = typeof value.day === "string" ? formatDayLabel(value.day) : "";
  const start = value.start === null || value.start === undefined ? "" : String(value.start);
  const end = value.end === null || value.end === undefined ? "" : String(value.end);
  const time = [start, end].filter(Boolean).join("–");
  const schedule = [day, time].filter(Boolean).join(", ");
  const activity = value.activity === null || value.activity === undefined
    ? ""
    : String(value.activity);

  return {
    kind: "text",
    text: [schedule, activity].filter(Boolean).join(" — ") || "Bloco de estudo",
  };
}

function arrayItemLabel(key: string | undefined, index: number): string {
  if (key === "paths") return `Caminho ${index + 1}`;
  if (key === "auxilios") return `Auxílio ${index + 1}`;
  return `Item ${index + 1}`;
}

function formatArrayItem(
  value: unknown,
  index: number,
  parentKey: string | undefined,
): FormattedPlanNode {
  if (parentKey === "weekly_blocks") return formatWeeklyBlock(value);
  if (isRecord(value)) {
    return formatObject(value, arrayItemLabel(parentKey, index));
  }
  return formatPlanValue(value);
}

function formatObject(
  value: Record<string, unknown>,
  label?: string,
): FormattedPlanNode {
  return {
    kind: "object",
    label,
    items: Object.entries(value).map(([key, child]) => formatPlanValue(child, key)),
  };
}

export function formatPlanValue(value: unknown, key?: string): FormattedPlanNode {
  const label = key ? planKeyLabel(key) : undefined;
  if (Array.isArray(value)) {
    return {
      kind: "list",
      label,
      items: value.map((item, index) => formatArrayItem(item, index, key)),
    };
  }
  if (isRecord(value)) return formatObject(value, label);
  return { kind: "text", label, text: formatScalar(value, key) };
}
