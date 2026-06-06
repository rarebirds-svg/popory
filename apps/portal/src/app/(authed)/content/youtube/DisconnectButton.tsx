"use client";
// YouTube 연결 해제 client — DELETE /api/content/youtube/connect.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function DisconnectButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function disconnect() {
    if (!confirm("YouTube 연결을 해제할까요?")) return;
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/content/youtube/connect`, { method: "DELETE", credentials: "include" });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      onClick={disconnect}
      disabled={busy}
      className="rounded-md border border-popory-border px-4 py-2 text-sm disabled:opacity-50"
    >
      {busy ? "해제 중…" : "연결 해제"}
    </button>
  );
}
