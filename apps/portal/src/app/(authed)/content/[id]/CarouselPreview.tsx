"use client";
// 인스타그램 캐러셀 슬라이드 이미지 뷰어 — 좌우 버튼으로 슬라이드 이동.
import { useState } from "react";
import { API_BASE } from "@/lib/env";

interface Props {
  jobId: string;
  slideCount: number;
  caption: string;
}

export function CarouselPreview({ jobId, slideCount, caption }: Props) {
  const [current, setCurrent] = useState(0);

  return (
    <div className="space-y-4">
      <div className="relative w-full max-w-sm mx-auto aspect-square rounded-lg overflow-hidden border border-popory-border bg-popory-card">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`${API_BASE}/api/content/jobs/${jobId}/carousel/${current}`}
          alt={`슬라이드 ${current + 1}`}
          className="w-full h-full object-cover"
        />
        <div className="absolute bottom-2 left-0 right-0 flex justify-center gap-1">
          {Array.from({ length: slideCount }, (_, i) => (
            <button
              key={i}
              onClick={() => setCurrent(i)}
              className={`h-1.5 w-1.5 rounded-full transition-colors ${
                i === current ? "bg-white" : "bg-white/40"
              }`}
            />
          ))}
        </div>
        {current > 0 && (
          <button
            onClick={() => setCurrent((c) => c - 1)}
            className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-1 text-white text-xs"
          >
            ‹
          </button>
        )}
        {current < slideCount - 1 && (
          <button
            onClick={() => setCurrent((c) => c + 1)}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-1 text-white text-xs"
          >
            ›
          </button>
        )}
      </div>
      <p className="text-xs text-popory-muted">{current + 1} / {slideCount}</p>
      {caption && (
        <details>
          <summary className="cursor-pointer text-xs text-popory-accent">캡션 보기</summary>
          <pre className="mt-2 whitespace-pre-wrap rounded-md border border-popory-border bg-popory-card p-3 text-xs text-popory-fg">{caption}</pre>
        </details>
      )}
    </div>
  );
}
