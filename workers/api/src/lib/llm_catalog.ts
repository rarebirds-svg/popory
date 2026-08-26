// LLM 기능·모델 카탈로그. 어드민 UI 와 각 서비스 워커가 같은 목록을 본다.
//
// 워커는 파이썬이라 이 파일을 직접 못 읽는다. 그래서 카탈로그는 여기 한 곳에 두고
// API 가 양쪽에 내려준다 — 목록이 갈라지면 어드민에서 고른 값이 워커에서 안 먹는다.
//
// 기능은 service 로 묶는다. 서비스마다 자기 area 토큰으로 자기 기능만 읽어가므로
// (content-worker → content, brief → brief), 새 서비스를 붙일 때 여기에 한 줄만 늘린다.

export const DEFAULT_MODEL = "claude-sonnet-5";

export type ServiceKey = "content" | "brief";

// 어드민 화면에서 기능을 묶어 보여줄 순서·이름.
export const SERVICES: { key: ServiceKey; label: string; description: string }[] = [
  { key: "content", label: "컨텐츠 생성", description: "포포리 책방 블로그·영상·인스타" },
  { key: "brief", label: "뉴스 브리핑", description: "카테고리·커스텀 주제 일일 이슈" },
];

export type FeatureKey =
  | "blog" | "video_script" | "shorts_script" | "carousel"
  | "youtube_post" | "reply" | "translate" | "recommend" | "image_review"
  | "brief_issue";

// defaultModel 을 준 기능은 그 값이 기본값이다(안 주면 DEFAULT_MODEL). 기능마다
// 적정 모델이 다르고, 어드민에서 "기본값"으로 되돌릴 때 돌아갈 자리도 여기다.
export const FEATURES: {
  key: FeatureKey; service: ServiceKey; label: string; description: string; defaultModel?: string;
}[] = [
  { key: "blog", service: "content", label: "블로그 본문", description: "네이버 블로그 HTML 생성" },
  { key: "video_script", service: "content", label: "유튜브 롱폼 대본", description: "장면·내레이션·이미지 프롬프트" },
  { key: "shorts_script", service: "content", label: "쇼츠 대본", description: "세로 영상 장면 구성" },
  { key: "carousel", service: "content", label: "인스타 캐러셀", description: "슬라이드 카피·이미지 프롬프트" },
  { key: "youtube_post", service: "content", label: "유튜브 커뮤니티 글", description: "채널 커뮤니티 포스트" },
  { key: "reply", service: "content", label: "댓글 답글 초안", description: "시청자 댓글 답글" },
  { key: "translate", service: "content", label: "자막 번역", description: "EN·ZH·JA SRT 번역" },
  { key: "recommend", service: "content", label: "주간 도서 추천", description: "다음 주 다룰 책 후보" },
  { key: "image_review", service: "content", label: "이미지 이상 검수", description: "얼굴·인체 기형 판정(비전). 장당 1회라 호출이 가장 많다" },
  // 브리핑은 도입 때부터 Sonnet 4.6 으로 돌아왔다. 어드민 설정이 붙었다고 모델이
  // 저절로 바뀌면 안 되니 기본값을 그대로 유지한다.
  { key: "brief_issue", service: "brief", label: "이슈 생성", defaultModel: "claude-sonnet-4-6", description: "WebSearch 로 이슈를 모아 브리핑 본문 작성. 카테고리·커스텀 주제 공통" },
];

export function featuresOf(service: ServiceKey) {
  return FEATURES.filter((f) => f.service === service);
}

// 해당 기능의 기본 모델. 설정 행이 없을 때 쓰이고, 이 값으로 저장하면 행을 지운다.
export function defaultModelOf(feature: string): string {
  return FEATURES.find((f) => f.key === feature)?.defaultModel ?? DEFAULT_MODEL;
}

// tier 는 UI 정렬·설명용이다. 실제 호출은 claude CLI 의 --model 에 id 를 그대로 넘긴다.
export const MODELS: { id: string; label: string; note: string }[] = [
  { id: "claude-opus-5", label: "Opus 5", note: "가장 강한 추론. 호출당 비용·시간이 가장 크다" },
  { id: "claude-opus-4-8", label: "Opus 4.8", note: "Opus 계열 직전 세대" },
  { id: "claude-opus-4-7", label: "Opus 4.7", note: "Opus 계열" },
  { id: "claude-opus-4-6", label: "Opus 4.6", note: "Opus 계열 구세대" },
  { id: "claude-sonnet-5", label: "Sonnet 5", note: "현재 기본값. Sonnet 최신" },
  { id: "claude-sonnet-4-6", label: "Sonnet 4.6", note: "직전 기본값. 품질·속도 균형" },
  { id: "claude-haiku-4-5", label: "Haiku 4.5", note: "가장 빠르고 가볍다. 이진 판정(검수)에 적합" },
];

export const MODEL_IDS = new Set(MODELS.map((m) => m.id));
export const FEATURE_KEYS = new Set(FEATURES.map((f) => f.key));
