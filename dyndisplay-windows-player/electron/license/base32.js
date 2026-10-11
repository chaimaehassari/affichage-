/*
 * Base32 RFC 4648 sans padding (alphabet A-Z2-7).
 *
 * Implementation volontairement identique a serialisation/.../Base32.kt :
 * le code de licence produit par l'app revendeur doit se decoder ici octet
 * pour octet. On tolere une saisie collee avec minuscules, espaces, tirets ou
 * tout autre separateur (comme l'app revendeur).
 */
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
const LOOKUP = (() => {
  const map = new Map();
  for (let i = 0; i < ALPHABET.length; i += 1) map.set(ALPHABET[i], i);
  return map;
})();

function encode(data) {
  const bytes = Buffer.isBuffer(data) ? data : Buffer.from(data);
  let out = '';
  let buffer = 0;
  let bitsLeft = 0;
  for (const byte of bytes) {
    buffer = ((buffer << 8) | byte) & 0xffffffff;
    bitsLeft += 8;
    while (bitsLeft >= 5) {
      out += ALPHABET[(buffer >>> (bitsLeft - 5)) & 0x1f];
      bitsLeft -= 5;
    }
  }
  if (bitsLeft > 0) {
    out += ALPHABET[(buffer << (5 - bitsLeft)) & 0x1f];
  }
  return out;
}

function decode(text) {
  const cleaned = String(text || '').toUpperCase().replace(/[^A-Z2-7]/g, '');
  const out = [];
  let buffer = 0;
  let bitsLeft = 0;
  for (const ch of cleaned) {
    const value = LOOKUP.get(ch);
    if (value === undefined) throw new Error('Caractere Base32 invalide.');
    buffer = ((buffer << 5) | value) & 0xffffffff;
    bitsLeft += 5;
    if (bitsLeft >= 8) {
      out.push((buffer >>> (bitsLeft - 8)) & 0xff);
      bitsLeft -= 8;
    }
  }
  // Bits de remplissage restants : ils doivent etre nuls (padding implicite).
  if (bitsLeft > 0) {
    const mask = (1 << (8 - bitsLeft)) - 1;
    if (((buffer << (8 - bitsLeft)) & 0xff) & mask) {
      throw new Error('Caracteres de remplissage Base32 invalides.');
    }
  }
  return Buffer.from(out);
}

module.exports = { encode, decode, ALPHABET };
