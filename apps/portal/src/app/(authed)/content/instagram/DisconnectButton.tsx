"use client";
// Instagram 연결 해제 버튼.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function DisconnectButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function disconnect() {
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/content/instagram/connect`, { method: "DELETE", credentials: "include" });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }
  return (
    <button onClick={disconnect} disabled={busy}
      className="rounded-md border border-red-300 px-3 py-1.5 text-xs text-red-700 disabled:opacity-50">
      {busy ? "해제 중…" : "연결 해제"}
    </button>
  );
}
