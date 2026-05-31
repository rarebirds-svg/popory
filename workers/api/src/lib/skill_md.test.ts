// SKILL.md parse/serialize/validate 단위 테스트.
import { describe, it, expect } from "vitest";
import {
  parseSkillMd,
  serializeSkillMd,
  validateFields,
  type SkillFields,
} from "./skill_md";

const SAMPLE = `---
slug: realestate
name: 부동산
delivery_mode: standalone
subject_template: "[{name} 이슈 브리핑] {date}"
sender_name: "{name} 이슈 브리핑"
enabled: true
description: "국토부·한국부동산원·기재부 정책·시장·판례"
---

본문 system prompt 첫 줄.
`;

describe("parseSkillMd", () => {
  it("frontmatter 6필드 + body 분리", () => {
    const r = parseSkillMd(SAMPLE);
    expect(r.errors).toEqual([]);
    expect(r.fields).toEqual({
      slug: "realestate",
      name: "부동산",
      delivery_mode: "standalone",
      subject_template: "[{name} 이슈 브리핑] {date}",
      sender_name: "{name} 이슈 브리핑",
      enabled: true,
      description: "국토부·한국부동산원·기재부 정책·시장·판례",
    });
    expect(r.body).toBe("본문 system prompt 첫 줄.\n");
  });

  it("frontmatter 없으면 error", () => {
    const r = parseSkillMd("no frontmatter\n");
    expect(r.errors).toContain("frontmatter not found");
  });

  it("필수 필드 누락 error", () => {
    const txt = `---\nslug: foo\nname: Foo\n---\nbody\n`;
    const r = parseSkillMd(txt);
    expect(r.errors.some((e) => e.includes("missing field"))).toBe(true);
  });
});

describe("parseSkillMd body 안의 --- 구분선 보존", () => {
  it("body에 ---가 여러 번 등장해도 잘리지 않음 (round-trip 무손실)", () => {
    const txt = `---
slug: foo
name: Foo
delivery_mode: bundled
subject_template: "x"
sender_name: "x"
enabled: true
description: "desc"
---

본문 시작.

---

본문 가운데 구분선 이후 줄.

---

본문 마지막 구분선 이후 줄.
`;
    const r = parseSkillMd(txt);
    expect(r.errors).toEqual([]);
    expect(r.body).toContain("본문 가운데 구분선 이후 줄.");
    expect(r.body).toContain("본문 마지막 구분선 이후 줄.");
    const re = serializeSkillMd({ fields: r.fields!, body: r.body });
    expect(re).toBe(txt);
  });
});

describe("serializeSkillMd", () => {
  it("parse → serialize round-trip", () => {
    const r = parseSkillMd(SAMPLE);
    const re = serializeSkillMd({ fields: r.fields!, body: r.body });
    expect(re).toBe(SAMPLE);
  });

  it("template value 안의 따옴표 escape", () => {
    const out = serializeSkillMd({
      fields: {
        slug: "x",
        name: "X",
        delivery_mode: "bundled",
        subject_template: 'A "B" C',
        sender_name: "S",
        enabled: false,
        description: "desc",
      },
      body: "body\n",
    });
    expect(out).toContain('subject_template: "A \\"B\\" C"');
    expect(out).toContain("enabled: false");
  });

  it("sender_name 안의 따옴표·역슬래시 escape round-trip", () => {
    const fields = {
      slug: "x",
      name: "X",
      delivery_mode: "bundled" as const,
      subject_template: "x",
      sender_name: 'a "b" \\\\c',
      enabled: true,
      description: "desc",
    };
    const out = serializeSkillMd({ fields, body: "body\n" });
    const back = parseSkillMd(out);
    expect(back.errors).toEqual([]);
    expect(back.fields).toEqual(fields);
  });
});

describe("validateFields", () => {
  const base: SkillFields = {
    slug: "realestate",
    name: "부동산",
    delivery_mode: "standalone",
    subject_template: "[{name}] {date}",
    sender_name: "{name}",
    enabled: true,
    description: "국토부 정책·시장 동향",
  };

  it("정상 → 빈 error 배열", () => {
    expect(validateFields(base)).toEqual([]);
  });

  it("slug regex 위반", () => {
    expect(validateFields({ ...base, slug: "Bad_Slug" })).toContainEqual(
      expect.stringContaining("slug"),
    );
  });

  it("delivery_mode 화이트리스트 위반", () => {
    expect(validateFields({ ...base, delivery_mode: "weekly" as never })).toContainEqual(
      expect.stringContaining("delivery_mode"),
    );
  });

  it("name 빈 문자열 위반", () => {
    expect(validateFields({ ...base, name: "" })).toContainEqual(
      expect.stringContaining("name"),
    );
  });

  it("subject_template 빈 문자열 위반", () => {
    expect(validateFields({ ...base, subject_template: "" })).toContainEqual(
      expect.stringContaining("subject_template"),
    );
  });

  it("sender_name 빈 문자열 위반", () => {
    expect(validateFields({ ...base, sender_name: "" })).toContainEqual(
      expect.stringContaining("sender_name"),
    );
  });

  it("예약어 slug (new) 거부", () => {
    expect(validateFields({ ...base, slug: "new" })).toContainEqual(
      expect.stringContaining("예약어"),
    );
  });

  it("description 빈 문자열 위반", () => {
    expect(validateFields({ ...base, description: "" })).toContainEqual(
      expect.stringContaining("description"),
    );
  });
});
