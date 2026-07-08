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

export async function getDir(token: string, path: string): Promise<DirEntry[]> {
  const url = `${API}/repos/${REPO}/contents/${encodeURIComponent(path).replace(/%2F/g, "/")}?ref=${BRANCH}`;
  const res = await fetch(url, { headers: COMMON_HEADERS(token) });
  if (!res.ok) throw new GitHubApiError(res.status, `getDir ${path} ${res.status}: ${await res.text()}`);
  return (await res.json()) as DirEntry[];
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
