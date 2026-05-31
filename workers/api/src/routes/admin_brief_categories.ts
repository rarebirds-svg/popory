// admin이 services/brief/categories/{slug}/SKILL.md를 GitHub로 read/edit하는 라우트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAdmin, type AppVars } from "../middleware/session";
import { parseSkillMd, serializeSkillMd, validateFields, type SkillFields } from "../lib/skill_md";
import { getDir, getFile, putFile, GitHubApiError } from "../lib/github_contents";

const CATEGORIES_PATH = "services/brief/categories";

function decodeBase64Utf8(b64: string): string {
  const bin = atob(b64.replace(/\n/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

export function mountAdminBriefCategories(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  // GET 목록 — categories/ 디렉토리 + 각 SKILL.md frontmatter 요약
  app.get("/api/admin/brief-categories", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const token = c.env.BRIEF_CATEGORIES_GITHUB_TOKEN;
    try {
      const entries = await getDir(token, CATEGORIES_PATH);
      const dirs = entries.filter((e) => e.type === "dir");
      const items = await Promise.all(
        dirs.map(async (d) => {
          const file = await getFile(token, `${CATEGORIES_PATH}/${d.name}/SKILL.md`);
          const text = decodeBase64Utf8(file.content);
          const parsed = parseSkillMd(text);
          return {
            slug: d.name,
            name: parsed.fields?.name ?? d.name,
            delivery_mode: parsed.fields?.delivery_mode ?? "bundled",
            enabled: parsed.fields?.enabled ?? false,
            sha: file.sha,
          };
        }),
      );
      return c.json({ items });
    } catch (e) {
      if (e instanceof GitHubApiError) return c.text(`github: ${e.message}`, 502);
      throw e;
    }
  });

  // GET 단건 — fields + body + sha
  app.get("/api/admin/brief-categories/:slug", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const slug = c.req.param("slug");
    const token = c.env.BRIEF_CATEGORIES_GITHUB_TOKEN;
    try {
      const file = await getFile(token, `${CATEGORIES_PATH}/${slug}/SKILL.md`);
      const text = decodeBase64Utf8(file.content);
      const parsed = parseSkillMd(text);
      if (!parsed.fields) return c.text(`parse error: ${parsed.errors.join(", ")}`, 500);
      return c.json({ fields: parsed.fields, body: parsed.body, sha: file.sha });
    } catch (e) {
      if (e instanceof GitHubApiError) return c.text(`github: ${e.message}`, e.status === 404 ? 404 : 502);
      throw e;
    }
  });

  // PUT 단건 — validate → serialize → GitHub PUT (sha 기반 optimistic locking)
  app.put("/api/admin/brief-categories/:slug", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const slug = c.req.param("slug");
    const user = c.get("user")!;
    const token = c.env.BRIEF_CATEGORIES_GITHUB_TOKEN;
    const payload = await c.req.json<{ fields: SkillFields; body: string; sha: string }>();
    if (payload.fields.slug !== slug) return c.text("slug mismatch", 400);
    const errs = validateFields(payload.fields);
    if (errs.length > 0) return c.json({ errors: errs }, 422);
    const text = serializeSkillMd({ fields: payload.fields, body: payload.body });
    const path = `${CATEGORIES_PATH}/${slug}/SKILL.md`;
    try {
      const result = await putFile(token, {
        path,
        message: `chore(brief): update categories/${slug}/SKILL.md via portal admin (by ${user.email})`,
        contentText: text,
        sha: payload.sha,
        actorEmail: user.email,
      });
      return c.json({ sha: result.sha });
    } catch (e) {
      if (e instanceof GitHubApiError) {
        if (e.status === 409) {
          // sha mismatch — 최신 본문 다시 가져와 클라이언트에 전달
          try {
            const fresh = await getFile(token, path);
            const freshText = decodeBase64Utf8(fresh.content);
            const freshParsed = parseSkillMd(freshText);
            return c.json({ error: "sha mismatch", latest: { fields: freshParsed.fields, body: freshParsed.body, sha: fresh.sha } }, 409);
          } catch {
            return c.text("sha mismatch — failed to fetch latest", 409);
          }
        }
        return c.text(`github: ${e.message}`, 502);
      }
      throw e;
    }
  });

  // POST 단건 — 신규 slug 생성 (sha 없이 putFile = create)
  app.post("/api/admin/brief-categories", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const user = c.get("user")!;
    const token = c.env.BRIEF_CATEGORIES_GITHUB_TOKEN;
    const payload = await c.req.json<{ fields: SkillFields; body: string }>();
    const errs = validateFields(payload.fields);
    if (errs.length > 0) return c.json({ errors: errs }, 422);
    const slug = payload.fields.slug;
    const path = `${CATEGORIES_PATH}/${slug}/SKILL.md`;
    // 중복 검사. getFile 200 = 이미 존재
    try {
      await getFile(token, path);
      return c.json({ errors: ["slug already exists"] }, 422);
    } catch (e) {
      if (!(e instanceof GitHubApiError) || e.status !== 404) {
        if (e instanceof GitHubApiError) return c.text(`github: ${e.message}`, 502);
        throw e;
      }
      // 404 → 진행
    }
    const text = serializeSkillMd({ fields: payload.fields, body: payload.body });
    try {
      const result = await putFile(token, {
        path,
        message: `chore(brief): create categories/${slug}/SKILL.md via portal admin (by ${user.email})`,
        contentText: text,
        actorEmail: user.email,
      });
      return c.json({ sha: result.sha });
    } catch (e) {
      if (e instanceof GitHubApiError) return c.text(`github: ${e.message}`, 502);
      throw e;
    }
  });
}
