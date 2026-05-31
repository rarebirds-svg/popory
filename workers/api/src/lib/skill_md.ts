// SKILL.md frontmatter·body 파싱·직렬화·검증 순수 함수.
export interface SkillFields {
  slug: string;
  name: string;
  delivery_mode: "standalone" | "bundled";
  subject_template: string;
  sender_name: string;
  enabled: boolean;
}

export interface ParseResult {
  fields: SkillFields | null;
  body: string;
  errors: string[];
}

const REQUIRED = ["slug", "name", "delivery_mode", "subject_template", "sender_name", "enabled"] as const;
const SLUG_RE = /^[a-z][a-z0-9-]{1,30}$/;
const RESERVED_SLUGS = new Set(["new"]); // /admin/brief-categories/new 정적 라우트 충돌 회피
const VALID_MODES = new Set(["standalone", "bundled"]);

export function parseSkillMd(text: string): ParseResult {
  const errors: string[] = [];
  if (!text.startsWith("---\n")) {
    return { fields: null, body: "", errors: ["frontmatter not found"] };
  }
  // split("---\n", 3)을 쓰면 body 안의 추가 "---" 구분선부터가 잘려나가므로 indexOf로 정확히 끊는다.
  const closeIdx = text.indexOf("\n---\n", 4);
  if (closeIdx === -1) {
    return { fields: null, body: "", errors: ["frontmatter not closed"] };
  }
  const fmText = text.slice(4, closeIdx + 1);
  const body = text.slice(closeIdx + 5).replace(/^\n/, "");
  const raw: Record<string, unknown> = {};
  for (const line of fmText.split("\n")) {
    const m = /^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$/.exec(line);
    if (!m) continue;
    const [, key, valueRaw] = m;
    raw[key!] = parseYamlScalar(valueRaw!);
  }
  for (const k of REQUIRED) {
    if (!(k in raw)) errors.push(`missing field: ${k}`);
  }
  if (errors.length > 0) return { fields: null, body, errors };
  const fields: SkillFields = {
    slug: String(raw.slug),
    name: String(raw.name),
    delivery_mode: String(raw.delivery_mode) as SkillFields["delivery_mode"],
    subject_template: String(raw.subject_template),
    sender_name: String(raw.sender_name),
    enabled: raw.enabled === true || raw.enabled === "true",
  };
  return { fields, body, errors: [] };
}

function parseYamlScalar(s: string): unknown {
  const trimmed = s.trim();
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  if (/^".*"$/.test(trimmed)) {
    // \X → X 한 패스. backslash·quote escape 모두 안전 처리.
    return trimmed.slice(1, -1).replace(/\\(.)/g, (_, ch) => ch);
  }
  return trimmed;
}

export function serializeSkillMd(input: { fields: SkillFields; body: string }): string {
  const { fields, body } = input;
  const esc = (s: string) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  const fm = [
    `slug: ${fields.slug}`,
    `name: ${fields.name}`,
    `delivery_mode: ${fields.delivery_mode}`,
    `subject_template: "${esc(fields.subject_template)}"`,
    `sender_name: "${esc(fields.sender_name)}"`,
    `enabled: ${fields.enabled ? "true" : "false"}`,
  ].join("\n");
  const bodyOut = body.startsWith("\n") ? body : "\n" + body;
  return `---\n${fm}\n---\n${bodyOut}`;
}

export function validateFields(f: SkillFields): string[] {
  const errs: string[] = [];
  if (!SLUG_RE.test(f.slug)) errs.push(`slug 규칙 위반 (^[a-z][a-z0-9-]{1,30}$)`);
  if (RESERVED_SLUGS.has(f.slug)) errs.push(`slug "${f.slug}"는 예약어 (사용 불가)`);
  if (!VALID_MODES.has(f.delivery_mode)) errs.push(`delivery_mode 화이트리스트 위반 (standalone|bundled)`);
  if (!f.name.trim()) errs.push("name 비어있음");
  if (!f.subject_template.trim()) errs.push("subject_template 비어있음");
  if (!f.sender_name.trim()) errs.push("sender_name 비어있음");
  return errs;
}
