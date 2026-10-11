import CryptoJS from 'crypto-js';

/** AES-CBC encrypt to Base64, compatible with Java AES/CBC/PKCS5Padding. */
function aesCbcEncryptBase64(plainText: string, key: string, iv: string): string {
  const keyBytes = CryptoJS.enc.Utf8.parse(key);
  const ivBytes = CryptoJS.enc.Utf8.parse(iv);

  if (![16, 24, 32].includes(key.length)) {
    throw new Error('VITE_PUBLIC_CATALYST_AES_KEY must be 16/24/32 bytes');
  }
  if (iv.length !== 16) {
    throw new Error('VITE_PUBLIC_CATALYST_AES_IV must be 16 bytes');
  }

  const encrypted = CryptoJS.AES.encrypt(plainText, keyBytes, {
    iv: ivBytes,
    mode: CryptoJS.mode.CBC,
    padding: CryptoJS.pad.Pkcs7
  });

  // Raw ciphertext Base64 (no OpenSSL salt header) — matches Java Base64(cipher.doFinal(...))
  return encrypted.ciphertext.toString(CryptoJS.enc.Base64);
}

/** Build X-Public-Token: AES(token:timestampMs). Works on HTTP (no WebCrypto secure-context). */
export async function buildPublicCatalystToken(): Promise<string> {
  const token = import.meta.env.VITE_PUBLIC_CATALYST_TOKEN;
  const key = import.meta.env.VITE_PUBLIC_CATALYST_AES_KEY;
  const iv = import.meta.env.VITE_PUBLIC_CATALYST_AES_IV;

  if (!token || !key || !iv) {
    throw new Error('Missing VITE_PUBLIC_CATALYST_TOKEN / AES_KEY / AES_IV');
  }

  return aesCbcEncryptBase64(`${token}:${Date.now()}`, key, iv);
}
