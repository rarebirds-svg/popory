// D1 일시적 스토리지 오류 재시도 헬퍼 단위 테스트.
import { describe, it, expect } from "vitest";
import { withD1Retry, isTransientD1Error } from "./d1_retry";

const noSleep = async () => {};

describe("isTransientD1Error", () => {
  it("스토리지 타임아웃/리셋 메시지를 일시적 오류로 본다", () => {
    expect(isTransientD1Error(new Error("D1_ERROR: D1 DB storage operation exceeded timeout which caused object to be reset."))).toBe(true);
    expect(isTransientD1Error(new Error("Network connection lost."))).toBe(true);
  });
  it("일반 SQL 오류는 일시적 오류가 아니다", () => {
    expect(isTransientD1Error(new Error("D1_ERROR: no such column: foo"))).toBe(false);
    expect(isTransientD1Error(new Error("UNIQUE constraint failed"))).toBe(false);
  });
});

describe("withD1Retry", () => {
  it("일시적 오류 후 재시도해 성공값을 반환한다", async () => {
    let calls = 0;
    const op = async () => {
      calls++;
      if (calls < 3) throw new Error("D1 DB storage operation exceeded timeout which caused object to be reset.");
      return "ok";
    };
    const out = await withD1Retry(op, { sleep: noSleep });
    expect(out).toBe("ok");
    expect(calls).toBe(3);
  });

  it("일시적이지 않은 오류는 즉시 전파한다(재시도 안 함)", async () => {
    let calls = 0;
    const op = async () => {
      calls++;
      throw new Error("UNIQUE constraint failed");
    };
    await expect(withD1Retry(op, { sleep: noSleep })).rejects.toThrow("UNIQUE constraint failed");
    expect(calls).toBe(1);
  });

  it("끝까지 일시적 오류면 시도 횟수만큼 호출 후 마지막 오류를 던진다", async () => {
    let calls = 0;
    const op = async () => {
      calls++;
      throw new Error("storage operation exceeded timeout which caused object to be reset");
    };
    await expect(withD1Retry(op, { attempts: 3, sleep: noSleep })).rejects.toThrow("exceeded timeout");
    expect(calls).toBe(3);
  });
});
