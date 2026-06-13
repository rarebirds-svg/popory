// 컨텐츠 작업 1건의 R2 자산과 DB 행(소스 포함)을 함께 지우는 헬퍼.
import type { Env } from "../types";

export async function deleteContentJob(env: Env, jobId: string, draftR2Key: string | null): Promise<void> {
  // R2 자산 정리(베스트 에포트) — 영상·초안·캐러셀 슬라이드.
  const keys: string[] = [`content/video/${jobId}.mp4`];
  if (draftR2Key) keys.push(draftR2Key);
  const carousel = await env.R2.list({ prefix: `content/carousel/${jobId}/` });
  for (const obj of carousel.objects) keys.push(obj.key);
  await env.R2.delete(keys);
  // DB 행 정리 — D1은 FK CASCADE가 꺼져 있으므로 소스를 먼저, 작업 행을 나중에 지운다.
  await env.DB.batch([
    env.DB.prepare("DELETE FROM content_sources WHERE job_id=?").bind(jobId),
    env.DB.prepare("DELETE FROM content_jobs WHERE id=?").bind(jobId),
  ]);
}
