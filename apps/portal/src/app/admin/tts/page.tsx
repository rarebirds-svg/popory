// admin · TTS 설정 조회(읽기 전용). 유튜브 동영상·쇼츠 내레이션의 속도·쉼·발음 처리를 한눈에 본다.
// 값은 포털 상수가 아니라 **워커가 보고한 유효값**이다 — 맥미니 env 로 덮어쓴 값까지 맞아야 해서 복제하지 않는다.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { Badge } from "../_components/Badge";
import { EmptyState } from "../_components/EmptyState";
import { Table } from "../_components/Table";
import { formatKst } from "../_lib/format";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface Tunable { current: number; env: string | null; default?: string; overridden: boolean }
interface TtsConfig {
  generated_at: string;
  engine: { provider: string; language: string; encoding: string; api_key_set: boolean };
  voices: { key: string; name: string; family: string }[];
  defaults: { longform: { length: string; voice: string; image_style: string }; shorts: { length: string; voice: string; image_style: string } };
  lengths: { longform: { minutes: string; scenes: number }[]; shorts: { seconds: string; scenes: number }[] };
  speed: { speaking_rate: Tunable; note: string };
  pauses: { comma_break_ms: Tunable; sentence_gap_s: Tunable; chapter_gap_s: Tunable; question_gap_s: Tunable; crossfade_s: Tunable };
  voice_fx: { deepen_semitones: Tunable; enabled: boolean };
  normalization: { label: string; input: string; spoken: string }[];
  name_fixes: { wrong: string; right: string }[];
  pronunciation_dictionary: { exists: boolean; entries?: { term: string; reading: string; ignore_case: boolean; note?: string }[] };
}
interface Res { config: TtsConfig | null; tts_reported_at: number | null; tts_age_sec: number | null; worker_reported_at: number | null }

async function fetchTts(): Promise<Res> {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/tts`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`admin tts ${res.status}`);
  return res.json();
}

function ago(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 90) return `${sec}초 전`;
  if (sec < 5400) return `${Math.round(sec / 60)}분 전`;
  return `${Math.round(sec / 3600)}시간 전`;
}

const CODE = "font-mono text-xs";
// 포털이 워커를 온라인으로 보는 기준(content_status.ts 의 STALE_SEC)과 같다.
const WORKER_STALE_SEC = 120;

// 하트비트가 한 번이라도 온 적 있다고 "살아 있다" 고 단정하면 안 된다 — 신선도로 가른다.
function emptyReason(workerReportedAt: number | null) {
  if (workerReportedAt == null) {
    return "워커가 한 번도 하트비트를 보내지 않았습니다 — 맥미니 워커가 떠 있는지 확인하세요.";
  }
  const age = Math.floor(Date.now() / 1000) - workerReportedAt;
  if (age >= WORKER_STALE_SEC) {
    return `워커 하트비트가 ${ago(age)}부터 끊겼습니다 — 워커가 멈췄거나 재시작 중입니다.`;
  }
  return (
    <>
      워커는 살아 있지만 설정을 아직 보내지 않았습니다. 맥미니에서 <strong>새 코드로 재시작되지 않았을</strong> 가능성이 가장 큽니다.
      <code className={`${CODE} block mt-2`}>cd ~/projects/popory &amp;&amp; git pull &amp;&amp; launchctl kickstart -k gui/$(id -u)/com.popory.content-worker</code>
      재시작 뒤에도 비어 있으면 <code className={CODE}>services/content/logs/</code> 의 <code className={CODE}>heartbeat_failed</code> /{" "}
      <code className={CODE}>tts_config_failed</code> 줄을 확인하세요.
    </>
  );
}

export default async function TtsPage() {
  const { config: c, tts_reported_at, tts_age_sec, worker_reported_at } = await fetchTts();

  return (
    <main>
      <h1 className="text-xl font-semibold">TTS 설정</h1>
      <p className="mt-2 text-sm text-popory-muted">
        유튜브 <strong>동영상·쇼츠</strong> 내레이션을 만들 때 적용되는 말속도, 쉼, 발음 처리입니다. 읽기 전용이며
        맥미니 워커가 <strong>실제로 쓰고 있는 값</strong>을 보고한 것입니다 — 바꾸려면 워커 환경변수를 고치고 재시작하세요.
      </p>

      {!c ? (
        <EmptyState>
          워커가 아직 TTS 설정을 보고하지 않았습니다. {emptyReason(worker_reported_at)}
        </EmptyState>
      ) : (
        <>
          <p className="mt-2 text-xs text-popory-muted">
            마지막 보고 {formatKst(tts_reported_at)} ({ago(tts_age_sec)}) · 워커는 약 1시간마다 다시 보고합니다.
          </p>

          <section className="mt-6">
            <h2 className="text-base font-semibold">엔진</h2>
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
              <dt className="text-popory-muted">서비스</dt><dd>{c.engine.provider}</dd>
              <dt className="text-popory-muted">언어 · 형식</dt><dd>{c.engine.language} · {c.engine.encoding}</dd>
              <dt className="text-popory-muted">API 키</dt>
              <dd>{c.engine.api_key_set
                ? <Badge intent="success">설정됨</Badge>
                : <Badge intent="danger">없음 — 합성 실패 시 macOS say 폴백</Badge>}</dd>
            </dl>
          </section>

          <section className="mt-8">
            <h2 className="text-base font-semibold">속도 · 쉼 · 음색</h2>
            <p className="mt-1 text-xs text-popory-muted">
              <Badge intent="warn">변경됨</Badge> 은 환경변수로 기본값에서 바꾼 항목입니다.
              환경변수가 없는 항목은 코드 상수라 수정하려면 배포가 필요합니다.
            </p>
            <Table head={["항목", "현재값", "기본값", "조정", "설명"]}>
              <TunableRow label="말속도" t={c.speed.speaking_rate} unit="배" note={c.speed.note} />
              <TunableRow label="쉼표 뒤 호흡" t={c.pauses.comma_break_ms} unit="ms"
                note="쉼표마다 SSML <break> 로 넣는 무음. 한 글자 나열 항목(밥, 꽃…)에는 넣지 않는다. 0 이면 끔." />
              <TunableRow label="문장 사이 쉼" t={c.pauses.sentence_gap_s} unit="초" note="문장별 TTS 클립 사이 무음. 자막 타이밍이 이 값을 그대로 따른다." />
              <TunableRow label="질문 뒤 쉼" t={c.pauses.question_gap_s} unit="초" note="물음표로 끝난 문장 뒤. 시청자가 생각할 틈을 준다." />
              <TunableRow label="챕터 경계 쉼" t={c.pauses.chapter_gap_s} unit="초" note="헤드라인이 바뀌는 장면 경계. 문장 사이 쉼의 2배." />
              <TunableRow label="장면 전환(크로스페이드)" t={c.pauses.crossfade_s} unit="초" note="장면 사이 영상 전이 길이. 자막 오프셋과 공유한다." />
              <TunableRow label="저음화(피치다운)" t={c.voice_fx.deepen_semitones} unit="반음"
                note={c.voice_fx.enabled ? "켜짐 — 머드 컷 + 프레즌스 부스트로 명료도 복원." : "꺼짐(0)."} />
            </Table>
          </section>

          <section className="mt-8">
            <h2 className="text-base font-semibold">목소리</h2>
            <Table head={["선택지", "음성", "계열", "기본값"]}>
              {c.voices.map((v) => (
                <tr key={v.key} className="border-b border-popory-border">
                  <td className="py-2 pr-4"><code className={CODE}>{v.key}</code></td>
                  <td className="py-2 pr-4"><code className={CODE}>{v.name}</code></td>
                  <td className="py-2 pr-4">{v.family}</td>
                  <td className="py-2 pr-4 space-x-1">
                    {c.defaults.longform.voice === v.key && <Badge intent="neutral">동영상</Badge>}
                    {c.defaults.shorts.voice === v.key && <Badge intent="neutral">쇼츠</Badge>}
                  </td>
                </tr>
              ))}
            </Table>
            <p className="mt-2 text-xs text-popory-muted">
              말속도는 계열과 짝이 맞아야 합니다 — Neural2 는 1.0, Chirp3-HD 는 1.06 이 귀 튜닝값입니다.
              현재 기본 음성 계열: <strong>{c.voices.find((v) => v.key === c.defaults.longform.voice)?.family ?? "—"}</strong>.
            </p>
          </section>

          <section className="mt-8">
            <h2 className="text-base font-semibold">길이별 장면 수</h2>
            <p className="mt-1 text-sm text-popory-muted">
              동영상: {c.lengths.longform.map((l) => `${l.minutes}분 ${l.scenes}장면`).join(" · ")}
              <br />
              쇼츠: {c.lengths.shorts.map((l) => `${l.seconds}초 ${l.scenes}장면`).join(" · ")}
            </p>
          </section>

          <section className="mt-8">
            <h2 className="text-base font-semibold">발음 처리</h2>
            <p className="mt-1 text-sm text-popory-muted">
              합성 직전에 텍스트를 이렇게 바꿉니다. 아래 <strong>결과는 예시 문장을 실제 처리 함수에 돌린 출력</strong>이라
              현재 코드와 항상 일치합니다.
            </p>
            <Table head={["규칙", "입력", "TTS 에 들어가는 텍스트"]}>
              {c.normalization.map((r) => (
                <tr key={r.label} className="border-b border-popory-border align-top">
                  <td className="py-2 pr-4 whitespace-nowrap">{r.label}</td>
                  <td className="py-2 pr-4 text-popory-muted">{r.input}</td>
                  <td className="py-2 pr-4">{r.spoken}</td>
                </tr>
              ))}
            </Table>
          </section>

          <section className="mt-8">
            <h2 className="text-base font-semibold">발음 사전</h2>
            {c.pronunciation_dictionary.exists && c.pronunciation_dictionary.entries ? (
              <>
                <p className="mt-1 text-sm text-popory-muted">
                  합성 직전에 영문 약어·고유명사를 한글 독음으로 바꿉니다. <strong>자막에는 원문이 그대로</strong> 남고 음성만 바뀝니다.
                  영문자에 붙은 경우(<code className={CODE}>ACEO</code>)는 건드리지 않고, 한글 조사가 붙은 경우(<code className={CODE}>CEO가</code>)는 바꿉니다.
                  대소문자를 구분하지만 표시된 항목은 구분하지 않습니다. 대본에서 실제 뜻을 확인한 항목만 넣습니다.
                </p>
                <Table head={["표기", "읽는 소리", "비고"]}>
                  {c.pronunciation_dictionary.entries.map((e) => (
                    <tr key={e.term} className="border-b border-popory-border">
                      <td className="py-2 pr-4"><code className={CODE}>{e.term}</code></td>
                      <td className="py-2 pr-4">{e.reading}</td>
                      <td className="py-2 pr-4 text-xs text-popory-muted">{e.note ?? ""}</td>
                    </tr>
                  ))}
                </Table>
                <p className="mt-2 text-xs text-popory-muted">
                  사전에 없는 영문 약어는 그대로 TTS 에 넘어갑니다. 잘못 읽는 단어를 발견하면 알려 주세요 — 뜻을 확인한 뒤 추가합니다.
                </p>
              </>
            ) : (
              <p className="mt-1 text-sm text-popory-muted">
                <Badge intent="warn">없음</Badge>{" "}
                단어별 발음 사전이 아직 없습니다. 위 규칙 표와 아래 인명 교정이 현재 발음을 다루는 전부입니다.
              </p>
            )}
          </section>

          <section className="mt-8">
            <h2 className="text-base font-semibold">외국 인명 표기 교정</h2>
            <p className="mt-1 text-sm text-popory-muted">
              LLM 이 쓴 대본·제목·태그에서 국내 출판 표기와 다른 이름을 바꿉니다. 대본에서 바뀌므로 <strong>내레이션 발음도 따라갑니다</strong>.
              책 표지·서점 상세페이지로 확인한 표기만 넣습니다.
            </p>
            <Table head={["틀린 표기", "출판 표기"]}>
              {c.name_fixes.map((f) => (
                <tr key={f.wrong} className="border-b border-popory-border">
                  <td className="py-2 pr-4 text-popory-muted">{f.wrong}</td>
                  <td className="py-2 pr-4">{f.right}</td>
                </tr>
              ))}
            </Table>
          </section>
        </>
      )}
    </main>
  );
}

// JSON 은 1.0 을 1 로 돌려줘 "현재 1 / 기본 1.0" 처럼 어긋나 보인다 — 기본값의 소수 자릿수에 맞춰 표기한다.
function fmt(n: number, def: string | undefined): string {
  if (def === undefined) return String(n);          // 기본값 정보가 없으면(코드 상수) 반올림하지 않는다
  return n.toFixed(def.split(".")[1]?.length ?? 0);
}

function TunableRow({ label, t, unit, note }: { label: string; t: Tunable; unit: string; note: string }) {
  return (
    <tr className="border-b border-popory-border align-top">
      <td className="py-2 pr-4 whitespace-nowrap">{label}</td>
      <td className="py-2 pr-4 whitespace-nowrap">
        <strong>{fmt(t.current, t.default)}</strong> {unit}{" "}
        {t.overridden && <Badge intent="warn">변경됨</Badge>}
      </td>
      <td className="py-2 pr-4 whitespace-nowrap text-popory-muted">{t.default ?? fmt(t.current, undefined)} {unit}</td>
      <td className="py-2 pr-4">
        {t.env ? <code className={CODE}>{t.env}</code> : <span className="text-xs text-popory-muted">코드 상수</span>}
      </td>
      <td className="py-2 pr-4 text-popory-muted">{note}</td>
    </tr>
  );
}
