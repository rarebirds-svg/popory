// 사용자가 쿠키 인증으로 컨텐츠 작업을 생성·조회·편집한다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?, 'member', 1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_sources");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM content_recommendations");
  await env.DB.exec("DELETE FROM style_profiles");
  await env.DB.exec("DELETE FROM content_categories");
});

describe("POST /api/content/jobs", () => {
  it("작업을 queued 로 만들고 manual source 를 적재", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "전세사기 예방", sources: [{ url: "https://law.go.kr/x", title: "근거" }] }),
    });
    expect(res.status).toBe(201);
    const { id } = await res.json<{ id: string }>();
    const job = await env.DB.prepare("SELECT status, owner_sub FROM content_jobs WHERE id=?").bind(id).first<{ status: string; owner_sub: string }>();
    expect(job?.status).toBe("queued");
    expect(job?.owner_sub).toBe("u1");
    const src = await env.DB.prepare("SELECT kind, url FROM content_sources WHERE job_id=?").bind(id).first<{ kind: string; url: string }>();
    expect(src?.kind).toBe("manual");
    expect(src?.url).toBe("https://law.go.kr/x");
  });

  it("미인증 요청 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }),
    });
    expect(res.status).toBe(401);
  });

  it("options 를 params_json 에 저장", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platform: "youtube", options: { length: "10", voice: "male", image_style: "watercolor" } }),
    });
    const { id } = await res.json<{ id: string }>();
    const row = await env.DB.prepare("SELECT params_json FROM content_jobs WHERE id=?").bind(id).first<{ params_json: string }>();
    expect(JSON.parse(row!.params_json)).toEqual({ length: "10", voice: "male", image_style: "watercolor" });
  });
});

describe("GET /api/content/jobs", () => {
  it("본인 작업만 반환", async () => {
    const a = await userCookie("u1", "u1@e.com");
    await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ topic: "내것" }) });
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch("https://example.com/api/content/jobs", { headers: { cookie: b } });
    const { jobs } = await res.json<{ jobs: unknown[] }>();
    expect(jobs.length).toBe(0);
  });
});

describe("GET /api/content/jobs 카테고리·검색·페이지네이션", () => {
  it("category_id로 필터하고 has_more 반환", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    for (let i = 0; i < 3; i++) {
      await env.DB.prepare(
        "INSERT INTO content_jobs (id,owner_sub,topic,platform,status,created_at,updated_at,category_id) VALUES (?,?,'주제','naver-blog','queued',?,?,?)",
      ).bind(`j${i}`, "u1", 100 + i, 100 + i, "c1").run();
    }
    const res = await SELF.fetch("https://example.com/api/content/jobs?category_id=c1&limit=2&offset=0", { headers: { cookie: ck } });
    const body = await res.json<{ jobs: { id: string }[]; has_more: boolean }>();
    expect(body.jobs.length).toBe(2);
    expect(body.has_more).toBe(true);
  });
});

describe("GET /api/content/jobs/:id", () => {
  it("남의 작업은 404", async () => {
    const a = await userCookie("u1", "u1@e.com");
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, { headers: { cookie: b } });
    expect(res.status).toBe(404);
  });
});

describe("PATCH /api/content/jobs/:id", () => {
  it("review 상태에서 초안 저장 + done 전이", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    await env.DB.prepare("UPDATE content_jobs SET status='review' WHERE id=?").bind(id).run();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, {
      method: "PATCH", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ draft: "# 수정본", status: "done" }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT status, draft_r2_key FROM content_jobs WHERE id=?").bind(id).first<{ status: string; draft_r2_key: string }>();
    expect(row?.status).toBe("done");
    expect(await (await env.R2.get(row!.draft_r2_key))?.text()).toBe("# 수정본");
  });

  it("queued 상태에서는 편집 불가 409", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, { method: "PATCH", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ draft: "x" }) });
    expect(res.status).toBe(409);
  });

  it("done 상태에서도 초안 재편집 허용", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    await env.DB.prepare("UPDATE content_jobs SET status='done' WHERE id=?").bind(id).run();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, {
      method: "PATCH", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ draft: "# 재편집" }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT draft_r2_key FROM content_jobs WHERE id=?").bind(id).first<{ draft_r2_key: string }>();
    expect(await (await env.R2.get(row!.draft_r2_key))?.text()).toBe("# 재편집");
  });
});

describe("POST /api/content/jobs/:id/retry", () => {
  it("failed 작업을 queued 로 재설정하고 error 를 비운다", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    await env.DB.prepare("UPDATE content_jobs SET status='failed', error='boom' WHERE id=?").bind(id).run();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/retry`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT status, error FROM content_jobs WHERE id=?").bind(id).first<{ status: string; error: string | null }>();
    expect(row?.status).toBe("queued");
    expect(row?.error).toBeNull();
  });

  it("failed 아닌 작업은 409", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/retry`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(409);
  });

  it("남의 작업 retry 는 404", async () => {
    const a = await userCookie("u1", "u1@e.com");
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    await env.DB.prepare("UPDATE content_jobs SET status='failed' WHERE id=?").bind(id).run();
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/retry`, { method: "POST", headers: { cookie: b } });
    expect(res.status).toBe(404);
  });
});

async function workerToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({
    privateJwk: k.privateJwk, kid: k.kid,
    claims: { sub: "service:content-worker", email: "worker@svc", area, aud: "popory-portal" },
    ttlSeconds: 600,
  });
}

async function serviceToken() {
  const k = await ensureActiveKey(env.DB);
  return signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "services-content", email: "svc@e.com", area: "content-recommend", aud: "popory-portal" } });
}

describe("POST /api/content/jobs/claim", () => {
  it("queued 작업을 running 으로 claim 하고 source·style 동봉", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO style_profiles (id, owner_sub, name, platform, sample_count, created_at) VALUES ('sp1','u1','톤','naver-blog',1,1)").run();
    await env.R2.put("content/style/sp1/samples.json", JSON.stringify(["예시 글"]));
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t", style_profile_id: "sp1", sources: [{ url: "https://a" }] }) });
    const { id } = await create.json<{ id: string }>();

    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(200);
    const body = await res.json<{ job: { id: string; status: string }; sources: unknown[]; style_samples: string[] }>();
    expect(body.job.id).toBe(id);
    expect(body.job.status).toBe("running");
    expect(body.sources.length).toBe(1);
    expect(body.style_samples).toEqual(["예시 글"]);
    const row = await env.DB.prepare("SELECT status FROM content_jobs WHERE id=?").bind(id).first<{ status: string }>();
    expect(row?.status).toBe("running");
  });

  it("queued 없으면 204", async () => {
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(204);
  });

  it("잘못된 area 의 서비스 JWT 는 403", async () => {
    const token = await workerToken("brief");
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(403);
  });

  it("서비스 JWT 없으면 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST" });
    expect(res.status).toBe(401);
  });

  it("리스 초과한 running 고아를 queued 로 회수해 다시 claim 한다", async () => {
    await userCookie();  // u1 사용자 보장
    const stale = Math.floor(Date.now() / 1000) - 100 * 60;  // 100분 전(리스 90분 초과)
    await env.DB.prepare(
      "INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at) VALUES ('orphan1','u1','t','youtube','running',?,?)",
    ).bind(stale, stale).run();
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(200);
    const body = await res.json<{ job: { id: string; status: string } }>();
    expect(body.job.id).toBe("orphan1");
    expect(body.job.status).toBe("running");  // 회수→queued→재claim
  });

  it("리스 내 running 은 회수하지 않는다", async () => {
    await userCookie();
    const recent = Math.floor(Date.now() / 1000) - 5 * 60;  // 5분 전(리스 내)
    await env.DB.prepare(
      "INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at) VALUES ('fresh1','u1','t','youtube','running',?,?)",
    ).bind(recent, recent).run();
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(204);  // 회수 안 됨, queued 없음
    const row = await env.DB.prepare("SELECT status FROM content_jobs WHERE id='fresh1'").first<{ status: string }>();
    expect(row?.status).toBe("running");
  });
});

describe("PATCH /api/content/jobs/:id/result", () => {
  it("초안·메타를 저장하고 review 로 전이", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    // claim 해서 running 상태로 만들기
    const token = await workerToken();
    await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/result`, {
      method: "PATCH", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ status: "review", draft: "# 생성된 글", meta: { seo: 82 } }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT status, draft_r2_key, meta_json FROM content_jobs WHERE id=?").bind(id).first<{ status: string; draft_r2_key: string; meta_json: string }>();
    expect(row?.status).toBe("review");
    expect(await (await env.R2.get(row!.draft_r2_key))?.text()).toBe("# 생성된 글");
    expect(JSON.parse(row!.meta_json).seo).toBe(82);
  });

  it("running 아닌 작업에 result 는 409", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    // 작업은 아직 queued (claim 안 함)
    const token = await workerToken();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/result`, {
      method: "PATCH", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ status: "review", draft: "x" }),
    });
    expect(res.status).toBe(409);
  });
});

describe("video PUT/GET", () => {
  it("워커가 PUT 으로 MP4 저장, 소유자가 GET 으로 받음", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t", platform: "youtube" }) });
    const { id } = await create.json<{ id: string }>();
    const token = await workerToken();
    const bytes = new Uint8Array([0, 1, 2, 3, 4]);
    const put = await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, {
      method: "PUT", headers: { authorization: `Bearer ${token}`, "content-type": "video/mp4" }, body: bytes,
    });
    expect(put.status).toBe(200);
    const get = await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, { headers: { cookie: ck } });
    expect(get.status).toBe(200);
    expect(new Uint8Array(await get.arrayBuffer())).toEqual(bytes);
  });

  it("워커 PUT 은 서비스 JWT 없으면 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/jobs/x/video", { method: "PUT", body: new Uint8Array([1]) });
    expect(res.status).toBe(401);
  });

  it("남의 영상 GET 은 404", async () => {
    const a = await userCookie("u1", "u1@e.com");
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ topic: "t", platform: "youtube" }) });
    const { id } = await create.json<{ id: string }>();
    const token = await workerToken();
    await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, { method: "PUT", headers: { authorization: `Bearer ${token}`, "content-type": "video/mp4" }, body: new Uint8Array([9]) });
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, { headers: { cookie: b } });
    expect(res.status).toBe(404);
  });

  it("서비스 JWT(content-worker)로 GET video 허용", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t", platform: "youtube" }) });
    const { id } = await create.json<{ id: string }>();
    const token = await workerToken();
    await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, { method: "PUT", headers: { authorization: `Bearer ${token}`, "content-type": "video/mp4" }, body: new Uint8Array([7, 8, 9]) });
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, { headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(200);
    expect(new Uint8Array(await res.arrayBuffer())).toEqual(new Uint8Array([7, 8, 9]));
  });
});

describe("POST /api/content/jobs — style_profile_id 소유권", () => {
  it("남의 스타일 프로필 참조는 404", async () => {
    // u2 가 프로필 생성
    await userCookie("u2", "u2@e.com");
    await env.DB.prepare("INSERT INTO style_profiles (id, owner_sub, name, platform, sample_count, created_at) VALUES ('spX','u2','톤','naver-blog',1,1)").run();
    // u1 이 그 프로필로 작업 시도
    const a = await userCookie("u1", "u1@e.com");
    const res = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { cookie: a, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", style_profile_id: "spX" }),
    });
    expect(res.status).toBe(404);
  });

  it("존재하지 않는 프로필 참조는 404", async () => {
    const a = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { cookie: a, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", style_profile_id: "nope" }),
    });
    expect(res.status).toBe(404);
  });
});

describe("PUT /api/content/jobs/:id/carousel (service)", () => {
  it("base64 이미지 배열을 R2에 저장하고 GET으로 확인", async () => {
    const ck = await userCookie();
    const svcToken = await workerToken();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      "INSERT INTO content_jobs (id,owner_sub,topic,platform,status,created_at,updated_at) VALUES (?,?,'t','instagram-image','running',?,?)"
    ).bind("jig1", "u1", now, now).run();
    const images = [btoa("fake-jpeg-1"), btoa("fake-jpeg-2")];
    const put = await SELF.fetch("https://example.com/api/content/jobs/jig1/carousel", {
      method: "PUT",
      headers: { authorization: `Bearer ${svcToken}`, "content-type": "application/json" },
      body: JSON.stringify({ images }),
    });
    expect(put.status).toBe(200);
    const { count } = await put.json<{ ok: boolean; count: number }>();
    expect(count).toBe(2);
    // GET 엔드포인트로 저장 확인
    const get0 = await SELF.fetch("https://example.com/api/content/jobs/jig1/carousel/0", {
      headers: { cookie: ck },
    });
    expect(get0.status).toBe(200);
    await get0.arrayBuffer();
    const get1 = await SELF.fetch("https://example.com/api/content/jobs/jig1/carousel/1", {
      headers: { cookie: ck },
    });
    expect(get1.status).toBe(200);
    await get1.arrayBuffer();
  });
});

describe("GET /api/content/jobs/:id/carousel/:n (user)", () => {
  it("슬라이드 이미지를 스트리밍한다", async () => {
    const ck = await userCookie();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      "INSERT INTO content_jobs (id,owner_sub,topic,platform,status,created_at,updated_at) VALUES (?,?,'t','instagram-image','review',?,?)"
    ).bind("jig2", "u1", now, now).run();
    await env.R2.put("content/carousel/jig2/0.jpg", new Uint8Array([0xff, 0xd8, 0x01]), {
      httpMetadata: { contentType: "image/jpeg" },
    });
    const res = await SELF.fetch("https://example.com/api/content/jobs/jig2/carousel/0", {
      headers: { cookie: ck },
    });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("image/jpeg");
    await res.arrayBuffer(); // body 스트림 소비
  });

  it("존재하지 않는 슬라이드는 404", async () => {
    const ck = await userCookie();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      "INSERT INTO content_jobs (id,owner_sub,topic,platform,status,created_at,updated_at) VALUES (?,?,'t','instagram-image','review',?,?)"
    ).bind("jig3", "u1", now, now).run();
    const res = await SELF.fetch("https://example.com/api/content/jobs/jig3/carousel/0", {
      headers: { cookie: ck },
    });
    expect(res.status).toBe(404);
  });
});

describe("POST /api/content/jobs/:id/regenerate", () => {
  async function makeJob(ck: string, platform = "youtube", status = "review", youtubeStatus: string | null = "done") {
    const r = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platform }),
    });
    const { id } = await r.json<{ id: string }>();
    await env.DB.prepare("UPDATE content_jobs SET status=?, youtube_status=? WHERE id=?").bind(status, youtubeStatus, id).run();
    return id;
  }

  it("review 영상 작업을 queued로 되돌리고 업로드 상태도 리셋", async () => {
    const ck = await userCookie();
    const id = await makeJob(ck, "youtube", "review", "done");
    await env.DB.prepare("UPDATE content_jobs SET youtube_video_id='vid_old' WHERE id=?").bind(id).run();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/regenerate`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const job = await env.DB.prepare("SELECT status, youtube_status, youtube_video_id FROM content_jobs WHERE id=?").bind(id).first<{ status: string; youtube_status: string | null; youtube_video_id: string | null }>();
    expect(job?.status).toBe("queued");
    expect(job?.youtube_status).toBeNull();      // 옛 업로드 상태가 새 영상에 남으면 안 됨
    expect(job?.youtube_video_id).toBeNull();
  });

  it("failed 영상 작업도 재생성 가능", async () => {
    const ck = await userCookie();
    const id = await makeJob(ck, "shorts", "failed", null);
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/regenerate`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const job = await env.DB.prepare("SELECT status FROM content_jobs WHERE id=?").bind(id).first<{ status: string }>();
    expect(job?.status).toBe("queued");
  });

  it("영상 플랫폼이 아니면 409", async () => {
    const ck = await userCookie();
    const id = await makeJob(ck, "naver-blog", "review", null);
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/regenerate`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(409);
  });

  it("queued 상태면 409", async () => {
    const ck = await userCookie();
    const id = await makeJob(ck, "youtube", "queued", null);
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/regenerate`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(409);
  });

  it("타인 작업은 404", async () => {
    const ck1 = await userCookie("u1", "u1@e.com");
    const id = await makeJob(ck1, "youtube", "review", null);
    const ck2 = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/regenerate`, { method: "POST", headers: { cookie: ck2 } });
    expect(res.status).toBe(404);
  });
});

describe("자막 저장·조회", () => {
  it("워커가 .srt를 저장하고 다시 읽는다", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platform: "youtube" }),
    });
    const { id } = await create.json<{ id: string }>();
    const token = await workerToken();
    const put = await SELF.fetch(`https://example.com/api/content/jobs/${id}/subtitle/en`, {
      method: "PUT", headers: { authorization: `Bearer ${token}` }, body: "1\n00:00:00,000 --> 00:00:01,000\nhi\n",
    });
    expect(put.status).toBe(200);
    const get = await SELF.fetch(`https://example.com/api/content/jobs/${id}/subtitle/en`, {
      headers: { authorization: `Bearer ${token}` },
    });
    expect(get.status).toBe(200);
    expect(await get.text()).toContain("00:00:00,000");
  });

  it("허용 안 된 언어는 400", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platform: "youtube" }),
    });
    const { id } = await create.json<{ id: string }>();
    const token = await workerToken();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/subtitle/fr`, {
      method: "PUT", headers: { authorization: `Bearer ${token}` }, body: "x",
    });
    expect(res.status).toBe(400);
  });
});

describe("DELETE /api/content/jobs/:id", () => {
  it("본인 작업과 소스를 함께 삭제한다", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", sources: [{ url: "https://x" }] }),
    });
    const { id } = await create.json<{ id: string }>();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const job = await env.DB.prepare("SELECT id FROM content_jobs WHERE id=?").bind(id).first();
    expect(job).toBeNull();
    const src = await env.DB.prepare("SELECT id FROM content_sources WHERE job_id=?").bind(id).first();
    expect(src).toBeNull();
  });

  it("타인 작업은 404", async () => {
    const ck1 = await userCookie("u1", "u1@e.com");
    const create = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { cookie: ck1, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }),
    });
    const { id } = await create.json<{ id: string }>();
    const ck2 = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, { method: "DELETE", headers: { cookie: ck2 } });
    expect(res.status).toBe(404);
    const job = await env.DB.prepare("SELECT id FROM content_jobs WHERE id=?").bind(id).first();
    expect(job).not.toBeNull();
  });

  it("미인증 요청 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/jobs/anything", { method: "DELETE" });
    expect(res.status).toBe(401);
  });
});

describe("POST /api/content/jobs/service-create", () => {
  it("서비스 토큰으로 잡 생성 + 추천 used 표시", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id, owner_sub, title, recommender, status, created_at, updated_at) VALUES ('rec1','u1','전세사기','시스템','pending',100,100)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/jobs/service-create", {
      method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", topic: "전세사기", platform: "youtube", recommendation_id: "rec1" }),
    });
    expect(res.status).toBe(201);
    const job = await env.DB.prepare("SELECT owner_sub, platform, status FROM content_jobs WHERE topic=?").bind("전세사기").first<{ owner_sub: string; platform: string; status: string }>();
    expect(job?.owner_sub).toBe("u1");
    expect(job?.platform).toBe("youtube");
    expect(job?.status).toBe("queued");
    const rec = await env.DB.prepare("SELECT status FROM content_recommendations WHERE id='rec1'").first<{ status: string }>();
    expect(rec?.status).toBe("used");
  });

  it("recommendation_id 없이도 생성", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/jobs/service-create", {
      method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", topic: "걷기운동", platform: "shorts" }),
    });
    expect(res.status).toBe(201);
  });

  it("서비스 토큰 없으면 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/jobs/service-create", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", topic: "t", platform: "youtube" }),
    });
    expect(res.status).toBe(401);
  });

  it("category_slug를 category_id로 해석해 저장", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub,email,role,created_at) VALUES ('u1','u1@e.com','member',1)").run();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/jobs/service-create", {
      method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", topic: "원씽", platform: "youtube", category_slug: "book-review" }),
    });
    expect(res.status).toBe(201);
    const job = await env.DB.prepare("SELECT category_id FROM content_jobs WHERE topic='원씽'").first<{ category_id: string }>();
    expect(job?.category_id).toBe("c1");
  });
});
