// 민감값(예: YouTube refresh token) 보관용 AES-GCM 대칭 암복호.
function b64encode(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}
function b64decode(s: string): Uint8Array {
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}
async function importKey(keyB64: string): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", b64decode(keyB64), { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}
export async function encrypt(plaintext: string, keyB64: string): Promise<string> {
  const key = await importKey(keyB64);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(plaintext));
  const out = new Uint8Array(iv.length + ct.byteLength);
  out.set(iv, 0);
  out.set(new Uint8Array(ct), iv.length);
  return b64encode(out.buffer);
}
export async function decrypt(token: string, keyB64: string): Promise<string> {
  const key = await importKey(keyB64);
  const data = b64decode(token);
  const iv = data.slice(0, 12);
  const ct = data.slice(12);
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ct);
  return new TextDecoder().decode(pt);
}
