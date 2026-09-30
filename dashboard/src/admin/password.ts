// No look-alike characters (0/O, 1/l/I), so a password read aloud or copied by hand works
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';

/** A random temporary password (crypto.getRandomValues, no modulo bias). */
export function generatePassword(length = 12): string {
  const limit = Math.floor(2 ** 32 / ALPHABET.length) * ALPHABET.length;
  const buf = new Uint32Array(1);
  let out = '';
  while (out.length < length) {
    crypto.getRandomValues(buf);
    if (buf[0] < limit) out += ALPHABET[buf[0] % ALPHABET.length];
  }
  return out;
}
