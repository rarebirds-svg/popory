// D1 일시적 스토리지 오류(타임아웃·DO 리셋·연결 끊김)를 지수 백오프로 재시도하는 헬퍼.

// D1 인프라 측 일시적 오류 패턴 — 같은 작업 재시도로 대부분 회복된다.
// SQL 오류(제약 위반·컬럼 없음 등)는 여기 매칭되지 않아 즉시 전파된다.
const TRANSIENT_D1 = /storage operation exceeded timeout|object to be reset|Storage caller|reset because its code was updated|Network connection lost/i;

export function isTransientD1Error(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : String(e);
  return TRANSIENT_D1.test(msg);
}

type RetryOpts = {
  attempts?: number;
  baseDelayMs?: number;
  sleep?: (ms: number) => Promise<void>;
};

const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

// 일시적 D1 오류일 때만 최대 attempts 번까지 백오프 재시도한다.
// batch()는 암묵적 트랜잭션이라 실패 시 전부 롤백되어 통째 재시도가 안전하다.
export async function withD1Retry<T>(op: () => Promise<T>, opts: RetryOpts = {}): Promise<T> {
  const attempts = opts.attempts ?? 3;
  const base = opts.baseDelayMs ?? 50;
  const sleep = opts.sleep ?? defaultSleep;
  let lastErr: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await op();
    } catch (e) {
      if (!isTransientD1Error(e)) throw e;
      lastErr = e;
      if (i < attempts - 1) await sleep(base * 2 ** i);
    }
  }
  throw lastErr;
}
