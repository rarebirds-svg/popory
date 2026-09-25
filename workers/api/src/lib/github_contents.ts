// GitHub Contents API REST 래퍼 (rarebirds-svg/popory 단일 repo 대상).
const API = "https://api.github.com";
const REPO = "rarebirds-svg/popory";
const BRANCH = "main";
const COMMON_HEADERS = (token: string) => ({
  Authorization: `Bearer ${token}`,
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
  "User-Agent": "popory-portal-admin",
});

export interface DirEntry {
  type: "file" | "dir" | "submodule" | "symlink";
  name: string;
  path: string;
  sha: string;
}

export interface FileResponse {
  content: string; // base64
  sha: string;
  path: string;
}

export class GitHubApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "GitHubApiError";
  }
}

// Fine-grained PAT 는 만료일이 있고, 만료되면 모든 호출이 401 "Bad credentials" 가 된다
// (2026-09-25: 90일 PAT 만료로 관리자 카테고리 화면·공개 브리핑 카테고리 목록이 멈췄다).
// GitHub 는 응답마다 이 헤더로 만료 시각을 알려 준다 — 미리 경고하는 데 쓴다.
// 형식: "2026-12-24 00:00:00 UTC" 또는 "2026-12-24 09:00:00 +0900". 만료 없는 토큰은 헤더가 없다.
export function parseTokenExpiration(raw: string | null): number | null {
  if (!raw) return null;
  const m = raw.trim().match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})\s*(UTC|Z|[+-]\d{2}:?\d{2})?$/);
  if (!m) return null;
  let tz = m[3] ?? "Z";
  if (tz === "UTC") tz = "Z";
  else if (/^[+-]\d{4}$/.test(tz)) tz = `${tz.slice(0, 3)}:${tz.slice(3)}`;
  const ms = Date.parse(`${m[1]}T${m[2]}${tz}`);
  return Number.isNaN(ms) ? null : Math.floor(ms / 1000);
}

export async function getDirWithTokenExpiry(
  token: string,
  path: string,
): Promise<{ entries: DirEntry[]; tokenExpiresAt: number | null }> {
  const url = `${API}/repos/${REPO}/contents/${encodeURIComponent(path).replace(/%2F/g, "/")}?ref=${BRANCH}`;
  const res = await fetch(url, { headers: COMMON_HEADERS(token) });
  if (!res.ok) throw new GitHubApiError(res.status, `getDir ${path} ${res.status}: ${await res.text()}`);
  return {
    entries: (await res.json()) as DirEntry[],
    tokenExpiresAt: parseTokenExpiration(res.headers.get("github-authentication-token-expiration")),
  };
}

export async function getDir(token: string, path: string): Promise<DirEntry[]> {
  return (await getDirWithTokenExpiry(token, path)).entries;
}

export async function getFile(token: string, path: string): Promise<FileResponse> {
  const url = `${API}/repos/${REPO}/contents/${encodeURIComponent(path).replace(/%2F/g, "/")}?ref=${BRANCH}`;
  const res = await fetch(url, { headers: COMMON_HEADERS(token) });
  if (!res.ok) throw new GitHubApiError(res.status, `getFile ${path} ${res.status}: ${await res.text()}`);
  const data = (await res.json()) as { content: string; sha: string; path: string };
  return data;
}

export interface PutFileInput {
  path: string;
  message: string;
  contentText: string;
  sha?: string;          // optional. 없으면 새 파일 create
  actorEmail: string;
}

export async function putFile(token: string, input: PutFileInput): Promise<{ sha: string }> {
  const url = `${API}/repos/${REPO}/contents/${encodeURIComponent(input.path).replace(/%2F/g, "/")}`;
  // Web Crypto / btoa 없는 환경 대비. TextEncoder + 수동 base64
  const contentB64 = base64FromUtf8(input.contentText);
  const bodyObj: Record<string, unknown> = {
    message: input.message,
    content: contentB64,
    branch: BRANCH,
    committer: { name: "popory-portal-admin", email: "noreply@popory.local" },
    author: { name: "popory-portal-admin", email: "noreply@popory.local" },
  };
  if (input.sha) bodyObj.sha = input.sha;
  const body = JSON.stringify(bodyObj);
  const res = await fetch(url, {
    method: "PUT",
    headers: { ...COMMON_HEADERS(token), "Content-Type": "application/json" },
    body,
  });
  if (!res.ok) throw new GitHubApiError(res.status, `putFile ${input.path} ${res.status}: ${await res.text()}`);
  const data = (await res.json()) as { content: { sha: string } };
  return { sha: data.content.sha };
}

export interface DeleteFileInput {
  path: string;
  message: string;
  sha: string; // 삭제 대상 파일의 현재 blob sha (필수)
}

export async function deleteFile(token: string, input: DeleteFileInput): Promise<void> {
  const url = `${API}/repos/${REPO}/contents/${encodeURIComponent(input.path).replace(/%2F/g, "/")}`;
  const body = JSON.stringify({
    message: input.message,
    sha: input.sha,
    branch: BRANCH,
    committer: { name: "popory-portal-admin", email: "noreply@popory.local" },
    author: { name: "popory-portal-admin", email: "noreply@popory.local" },
  });
  const res = await fetch(url, {
    method: "DELETE",
    headers: { ...COMMON_HEADERS(token), "Content-Type": "application/json" },
    body,
  });
  if (!res.ok) throw new GitHubApiError(res.status, `deleteFile ${input.path} ${res.status}: ${await res.text()}`);
}

function base64FromUtf8(s: string): string {
  // Cloudflare Workers는 Uint8Array를 직접 btoa 인자로 받지 못한다 → ascii 변환 후 btoa
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}
