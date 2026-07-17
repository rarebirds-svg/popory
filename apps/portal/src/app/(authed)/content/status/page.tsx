// 구 경로 /content/status → /admin/status 리다이렉트 (북마크 보존).
import { redirect } from "next/navigation";

export const runtime = "edge";

export default function ContentStatusRedirect() {
  redirect("/admin/status");
}
