// KST 날짜·시각 표기 단일 구현. admin 화면 전체가 이 포맷터만 쓴다.

// yyyy.mm.dd hh:mm:ss (KST·24시간) 고정 폭. ko-KR 기본형은 "2026. 8. 26. 오후 3:08:40"
// 처럼 자리수·오전오후 때문에 폭이 흔들려 표 안에서 줄바꿈되고 열이 어긋난다.
// en-GB + h23 은 2자리 0채움과 24시간을 보장한다(ko-KR 은 h12 로 되돌린다).
const KST_PARTS = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Seoul",
  year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit",
  hourCycle: "h23",
});

export function formatKst(ts: number | null | undefined): string {
  if (!ts) return "—";
  const parts = KST_PARTS.formatToParts(new Date(ts * 1000));
  const at = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${at("year")}.${at("month")}.${at("day")} ${at("hour")}:${at("minute")}:${at("second")}`;
}

export function formatKstIso(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ko-KR", {
      timeZone: "Asia/Seoul",
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
