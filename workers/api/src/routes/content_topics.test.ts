// 주제 그룹 생성·조회·작업 시작(start) API 테스트.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?,'member',1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_sources");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM content_topics");
  await env.DB.exec("DELETE FROM content_recommendations");
});

describe("POST /api/content/topics", () => {
  it("주제와 플랫폼별 idle 작업을 생성한다", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        topic: "전세사기 예방",
        platforms: [
          { platform: "naver-blog" },
          { platform: "youtube", options: { length: "5", voice: "female-calm", image_style: "photo" } },
        ],
      }),
    });
    expect(res.status).toBe(201);
    const { topic_id, job_ids } = await res.json<{ topic_id: string; job_ids: string[] }>();
    expect(job_ids).toHaveLength(2);
    const topic = await env.DB.prepare("SELECT topic FROM content_topics WHERE id=?").bind(topic_id).first<{ topic: string }>();
    expect(topic?.topic).toBe("전세사기 예방");
    const jobs = await env.DB.prepare("SELECT platform, status FROM content_jobs WHERE topic_id=? ORDER BY created_at").bind(topic_id).all<{ platform: string; status: string }>();
    expect(jobs.results.map((j) => j.platform)).toEqual(["naver-blog", "youtube"]);
    expect(jobs.results.every((j) => j.status === "idle")).toBe(true);
  });

  it("같은 제목의 pending 추천을 registered로 전환한다", async () => {
    const ck = await userCookie();
    await SELF.fetch("https://example.com/api/content/recommendations", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title: "원씽" }),
    });
    await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "원씽", platforms: [{ platform: "naver-blog" }] }),
    });
    const row = await env.DB.prepare("SELECT status FROM content_recommendations WHERE title=?").bind("원씽").first<{ status: string }>();
    expect(row?.status).toBe("registered");
  });

  it("저자가 붙은 제목으로 주제를 만들면 동명(제목만) 추천도 registered로 전환한다", async () => {
    const ck = await userCookie();
    // 추천은 제목만 저장됨
    await SELF.fetch("https://example.com/api/content/recommendations", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title: "원씽", author: "게리 켈러" }),
    });
    // 등록 버튼이 보내는 형식: "제목 - 저자"
    await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "원씽 - 게리 켈러", platforms: [{ platform: "naver-blog" }] }),
    });
    const row = await env.DB.prepare("SELECT status FROM content_recommendations WHERE title=?").bind("원씽").first<{ status: string }>();
    expect(row?.status).toBe("registered");
  });

  it("미인증 요청 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platforms: [{ platform: "naver-blog" }] }),
    });
    expect(res.status).toBe(401);
  });

  it("platforms 빈 배열은 400", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platforms: [] }),
    });
    expect(res.status).toBe(400);
  });
});

describe("GET /api/content/topics", () => {
  it("내 주제 목록을 작업 상태와 함께 반환한다", async () => {
    const ck = await userCookie();
    await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t1", platforms: [{ platform: "naver-blog" }] }),
    });
    const res = await SELF.fetch("https://example.com/api/content/topics", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const { topics } = await res.json<{ topics: unknown[] }>();
    expect(topics).toHaveLength(1);
  });
});

describe("GET /api/content/topics/:id", () => {
  it("주제와 하위 작업 전체를 반환한다", async () => {
    const ck = await userCookie();
    const cr = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t1", platforms: [{ platform: "naver-blog" }, { platform: "youtube" }] }),
    });
    const { topic_id } = await cr.json<{ topic_id: string; job_ids: string[] }>();
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topic_id}`, { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const body = await res.json<{ id: string; topic: string; jobs: unknown[] }>();
    expect(body.topic).toBe("t1");
    expect(body.jobs).toHaveLength(2);
  });

  it("하위 작업에 업로드 상태(youtube/instagram)를 포함한다", async () => {
    const ck = await userCookie();
    const cr = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t1", platforms: [{ platform: "youtube" }] }),
    });
    const { topic_id, job_ids } = await cr.json<{ topic_id: string; job_ids: string[] }>();
    await env.DB.prepare("UPDATE content_jobs SET status='review', youtube_status='done', youtube_video_id='vid1' WHERE id=?").bind(job_ids[0]).run();
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topic_id}`, { headers: { cookie: ck } });
    const body = await res.json<{ jobs: { youtube_status: string | null; youtube_video_id: string | null; instagram_status: string | null }[] }>();
    expect(body.jobs[0].youtube_status).toBe("done");
    expect(body.jobs[0].youtube_video_id).toBe("vid1");
    expect(body.jobs[0]).toHaveProperty("instagram_status");
  });

  it("타인 주제는 404", async () => {
    const ck1 = await userCookie("u1", "u1@e.com");
    const cr = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck1, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t1", platforms: [{ platform: "naver-blog" }] }),
    });
    const { topic_id } = await cr.json<{ topic_id: string; job_ids: string[] }>();
    const ck2 = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topic_id}`, { headers: { cookie: ck2 } });
    expect(res.status).toBe(404);
  });
});

describe("POST /api/content/jobs/:id/start", () => {
  it("idle 작업을 queued로 전환한다", async () => {
    const ck = await userCookie();
    const cr = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platforms: [{ platform: "naver-blog" }] }),
    });
    const { job_ids } = await cr.json<{ topic_id: string; job_ids: string[] }>();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${job_ids[0]}/start`, {
      method: "POST", headers: { cookie: ck },
    });
    expect(res.status).toBe(200);
    const job = await env.DB.prepare("SELECT status FROM content_jobs WHERE id=?").bind(job_ids[0]).first<{ status: string }>();
    expect(job?.status).toBe("queued");
  });

  it("이미 queued 이상이면 409", async () => {
    const ck = await userCookie();
    const cr = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platforms: [{ platform: "naver-blog" }] }),
    });
    const { job_ids } = await cr.json<{ topic_id: string; job_ids: string[] }>();
    await SELF.fetch(`https://example.com/api/content/jobs/${job_ids[0]}/start`, {
      method: "POST", headers: { cookie: ck },
    });
    const res2 = await SELF.fetch(`https://example.com/api/content/jobs/${job_ids[0]}/start`, {
      method: "POST", headers: { cookie: ck },
    });
    expect(res2.status).toBe(409);
  });
});

describe("POST /api/content/topics/:id/jobs", () => {
  async function makeTopic(ck: string, platforms: object[]) {
    const r = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "추가테스트주제", platforms }),
    });
    return (await r.json<{ topic_id: string }>()).topic_id;
  }

  it("없는 플랫폼을 idle 작업으로 추가한다", async () => {
    const ck = await userCookie();
    const topicId = await makeTopic(ck, [{ platform: "naver-blog" }]);
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topicId}/jobs`, {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ platforms: [{ platform: "youtube", options: { length: "5", voice: "male", image_style: "photo" } }] }),
    });
    expect(res.status).toBe(201);
    const out = await res.json<{ added_job_ids: string[]; skipped_platforms: string[] }>();
    expect(out.added_job_ids).toHaveLength(1);
    expect(out.skipped_platforms).toEqual([]);
    const job = await env.DB.prepare("SELECT platform, status, topic_id, params_json FROM content_jobs WHERE id=?").bind(out.added_job_ids[0]).first<{ platform: string; status: string; topic_id: string; params_json: string }>();
    expect(job?.platform).toBe("youtube");
    expect(job?.status).toBe("idle");
    expect(job?.topic_id).toBe(topicId);
    expect(JSON.parse(job!.params_json).length).toBe("5");
  });

  it("이미 있는 플랫폼은 skip한다", async () => {
    const ck = await userCookie();
    const topicId = await makeTopic(ck, [{ platform: "naver-blog" }]);
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topicId}/jobs`, {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ platforms: [{ platform: "naver-blog" }, { platform: "shorts" }] }),
    });
    const out = await res.json<{ added_job_ids: string[]; skipped_platforms: string[] }>();
    expect(out.added_job_ids).toHaveLength(1); // shorts만 추가
    expect(out.skipped_platforms).toEqual(["naver-blog"]);
    const { results } = await env.DB.prepare("SELECT platform FROM content_jobs WHERE topic_id=? ORDER BY platform").bind(topicId).all<{ platform: string }>();
    expect(results.map((r) => r.platform).sort()).toEqual(["naver-blog", "shorts"]);
  });

  it("타인 주제에 추가하면 404", async () => {
    const ck1 = await userCookie("u1", "u1@e.com");
    const topicId = await makeTopic(ck1, [{ platform: "naver-blog" }]);
    const ck2 = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topicId}/jobs`, {
      method: "POST", headers: { cookie: ck2, "content-type": "application/json" },
      body: JSON.stringify({ platforms: [{ platform: "youtube" }] }),
    });
    expect(res.status).toBe(404);
  });

  it("빈 platforms는 400", async () => {
    const ck = await userCookie();
    const topicId = await makeTopic(ck, [{ platform: "naver-blog" }]);
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topicId}/jobs`, {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ platforms: [] }),
    });
    expect(res.status).toBe(400);
  });

  it("존재하지 않는 style_profile_id는 404", async () => {
    const ck = await userCookie();
    const topicId = await makeTopic(ck, [{ platform: "naver-blog" }]);
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topicId}/jobs`, {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ platforms: [{ platform: "youtube" }], style_profile_id: "nope" }),
    });
    expect(res.status).toBe(404);
  });

  it("같은 요청 내 중복 플랫폼은 1개만 추가한다", async () => {
    const ck = await userCookie();
    const topicId = await makeTopic(ck, [{ platform: "naver-blog" }]);
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topicId}/jobs`, {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ platforms: [{ platform: "youtube" }, { platform: "youtube" }] }),
    });
    const out = await res.json<{ added_job_ids: string[]; skipped_platforms: string[] }>();
    expect(out.added_job_ids).toHaveLength(1);
    expect(out.skipped_platforms).toContain("youtube");
    const { results } = await env.DB.prepare("SELECT platform FROM content_jobs WHERE topic_id=? AND platform='youtube'").bind(topicId).all();
    expect(results).toHaveLength(1);
  });
});

describe("DELETE /api/content/topics/:id", () => {
  it("주제와 하위 작업을 모두 삭제한다", async () => {
    const ck = await userCookie();
    const cr = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "지울주제", platforms: [{ platform: "naver-blog" }, { platform: "youtube" }] }),
    });
    const { topic_id } = await cr.json<{ topic_id: string }>();
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topic_id}`, { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const topic = await env.DB.prepare("SELECT id FROM content_topics WHERE id=?").bind(topic_id).first();
    expect(topic).toBeNull();
    const { results } = await env.DB.prepare("SELECT id FROM content_jobs WHERE topic_id=?").bind(topic_id).all();
    expect(results).toHaveLength(0);
  });

  it("타인 주제는 404이고 삭제되지 않는다", async () => {
    const ck1 = await userCookie("u1", "u1@e.com");
    const cr = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck1, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platforms: [{ platform: "naver-blog" }] }),
    });
    const { topic_id } = await cr.json<{ topic_id: string }>();
    const ck2 = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topic_id}`, { method: "DELETE", headers: { cookie: ck2 } });
    expect(res.status).toBe(404);
    const topic = await env.DB.prepare("SELECT id FROM content_topics WHERE id=?").bind(topic_id).first();
    expect(topic).not.toBeNull();
  });
});
