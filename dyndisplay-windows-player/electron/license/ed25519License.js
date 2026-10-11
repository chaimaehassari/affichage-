/*
 * Verification d'un code de serialisation Ed25519 v3, hors-ligne.
 *
 * FORMAT (bit a bit identique a Ed25519LicenseManager.kt de l'app revendeur) :
 *   payload 57 octets
 *     0..4    magic   "TDL3"
 *     4       version 0x03
 *     5..13   client  code client, 8 octets  (remplissage par zeros A GAUCHE)
 *     13..29  site    code site,   16 octets (idem)
 *     29..45  poste   code poste,  16 octets (idem)
 *     45..57  materiel 3 empreintes de 4 octets
 *   signature Ed25519 64 octets sur le payload
 *   total 121 octets, encode Base32 (sans padding)
 *
 * Aucun quota ni expiration : le code identifie UNIQUEMENT la box (client,
 * site, poste, numero de box). Il est PERMANENT par construction : il
 * n'existe aucun champ d'expiration dans le payload, donc rien ne peut
 * expirer.
 *
 * La verification couvre : format, signature (cle publique embarque),
 * appartenance de la box (>= MATCH_THRESHOLD empreintes) et code client
 * attendu. Aucun acces reseau : tout est local.
 */
const crypto = require('crypto');
const base32 = require('./base32.js');
const { MATCH_THRESHOLD, splitMachineCodeFull } = require('./machineFingerprint.js');
const { licensePublicKeyHex } = require('./licenseConfig.js');

const MAGIC = Buffer.from('TDL3', 'ascii');
const FORMAT_VERSION = 3;
const PAYLOAD_LENGTH = 57;
const SIGNATURE_LENGTH = 64;
const CODE_LENGTH = PAYLOAD_LENGTH + SIGNATURE_LENGTH;

const CLIENT_OFFSET = 5;
const CLIENT_WIDTH = 8;
const SITE_OFFSET = 13;
const SITE_WIDTH = 16;
const POST_OFFSET = 29;
const POST_WIDTH = 16;
const MACHINE_OFFSET = 45;

// Prefixe DER SPKI pour une cle publique Ed25519 brute de 32 octets :
//   SEQUENCE { SEQUENCE { OID 1.3.101.112 }, BIT STRING (32 octets) }
const SPKI_ED25519_PREFIX = Buffer.from('302a300506032b6570032100', 'hex');

const ERRORS = {
  EMPTY: 'EMPTY',
  BAD_BASE32: 'BAD_BASE32',
  BAD_LENGTH: 'BAD_LENGTH',
  BAD_MAGIC: 'BAD_MAGIC',
  BAD_VERSION: 'BAD_VERSION',
  BAD_SIGNATURE: 'BAD_SIGNATURE',
  MACHINE_MISMATCH: 'MACHINE_MISMATCH',
  CLIENT_MISMATCH: 'CLIENT_MISMATCH',
  BAD_PUBLIC_KEY: 'BAD_PUBLIC_KEY',
};

// Champ texte : on retire les zeros de remplissage (a gauche) puis on lit le
// reste. Identique a readField() cote Kotlin.
function readField(payload, offset, width) {
  const slice = payload.subarray(offset, offset + width);
  let start = 0;
  while (start < slice.length && slice[start] === 0) start += 1;
  if (start >= slice.length) return '';
  return slice.subarray(start).toString('ascii');
}

function publicKeyObject() {
  const hex = licensePublicKeyHex();
  if (hex.length !== 64) {
    throw new Error(`Cle publique Ed25519 invalide (${hex.length} car., attendu 64).`);
  }
  const raw = Buffer.from(hex, 'hex');
  const der = Buffer.concat([SPKI_ED25519_PREFIX, raw]);
  return crypto.createPublicKey({ key: der, format: 'der', type: 'spki' });
}

function parsePayload(payload) {
  return {
    version: payload[4],
    clientCode: readField(payload, CLIENT_OFFSET, CLIENT_WIDTH),
    siteCode: readField(payload, SITE_OFFSET, SITE_WIDTH),
    postCode: readField(payload, POST_OFFSET, POST_WIDTH),
    machineComponents: [
      payload.subarray(MACHINE_OFFSET, MACHINE_OFFSET + 4),
      payload.subarray(MACHINE_OFFSET + 4, MACHINE_OFFSET + 8),
      payload.subarray(MACHINE_OFFSET + 8, MACHINE_OFFSET + 12),
    ],
  };
}

function machineCodeFullFromComponents(components) {
  return Buffer.concat(components).toString('hex').toUpperCase().match(/.{1,8}/g).join('-');
}

function countMatchingComponents(licensed, current) {
  let matches = 0;
  for (let i = 0; i < 3; i += 1) {
    if (Buffer.compare(licensed[i], current[i]) === 0) matches += 1;
  }
  return matches;
}

/**
 * Verifie un code de serialisation.
 *
 * @param {string} rawCode  code Base32 saisi par l'operateur
 * @param {object} [opts]
 * @param {Buffer[]} [opts.machineComponents] empreintes de la box (defaut : rien a comparer)
 * @param {string}   [opts.expectedClientCode] code client exige (sinon ignore)
 * @returns {{valid: boolean, errorCode: string|null, error: string|null, summary: object|null}}
 */
function verifyLicense(rawCode, opts = {}) {
  const fail = (errorCode, error) => ({ valid: false, errorCode, error, summary: null });

  const raw = String(rawCode || '').trim();
  if (!raw) return fail(ERRORS.EMPTY, 'Aucun code de serialisation saisi.');

  let bytes;
  try {
    bytes = base32.decode(raw);
  } catch (err) {
    return fail(ERRORS.BAD_BASE32, `Code illisible : ${err.message}`);
  }
  if (bytes.length !== CODE_LENGTH) {
    return fail(
      ERRORS.BAD_LENGTH,
      `Code de ${bytes.length} octets une fois decode, attendu ${CODE_LENGTH}. Code tronque ou mal colle ?`,
    );
  }

  const payload = bytes.subarray(0, PAYLOAD_LENGTH);
  const signature = bytes.subarray(PAYLOAD_LENGTH, CODE_LENGTH);

  if (!payload.subarray(0, MAGIC.length).equals(MAGIC)) {
    return fail(ERRORS.BAD_MAGIC, "Ce code n'est pas au format attendu (magic TDL3).");
  }

  let publicKey;
  try {
    publicKey = publicKeyObject();
  } catch (err) {
    return fail(ERRORS.BAD_PUBLIC_KEY, err.message);
  }

  let signatureOk = false;
  try {
    signatureOk = crypto.verify(null, payload, publicKey, signature);
  } catch (err) {
    signatureOk = false;
  }
  if (!signatureOk) {
    return fail(ERRORS.BAD_SIGNATURE, 'Signature invalide : code modifie ou non emis par le revendeur.');
  }

  const parsed = parsePayload(payload);
  if (parsed.version !== FORMAT_VERSION) {
    return fail(ERRORS.BAD_VERSION, `Version de code ${parsed.version} inconnue.`);
  }

  if (opts.machineComponents) {
    const matches = countMatchingComponents(parsed.machineComponents, opts.machineComponents);
    if (matches < MATCH_THRESHOLD) {
      return fail(
        ERRORS.MACHINE_MISMATCH,
        `Ce code a ete emis pour une autre box (${matches}/3 empreintes correspondantes, ${MATCH_THRESHOLD} requises).`,
      );
    }
  }

  if (opts.expectedClientCode) {
    const expected = String(opts.expectedClientCode).trim().toUpperCase();
    if (expected && parsed.clientCode.toUpperCase() !== expected) {
      return fail(
        ERRORS.CLIENT_MISMATCH,
        `Le code client saisi (« ${expected} ») ne correspond pas a celui de la licence (« ${parsed.clientCode} »).`,
      );
    }
  }

  return {
    valid: true,
    errorCode: null,
    error: null,
    summary: {
      version: parsed.version,
      clientCode: parsed.clientCode,
      siteCode: parsed.siteCode,
      postCode: parsed.postCode,
      machineComponents: parsed.machineComponents,
      machineCodeFull: machineCodeFullFromComponents(parsed.machineComponents),
    },
  };
}

// Utilitaire de test/diagnostic : reconstruit le code machine complet a partir
// d'un code de licence (sans verifier la signature). Jamais pour un controle.
function peekMachineCode(rawCode) {
  const bytes = base32.decode(rawCode);
  if (bytes.length !== CODE_LENGTH) throw new Error('Longueur de code invalide.');
  return machineCodeFullFromComponents(parsePayload(bytes.subarray(0, PAYLOAD_LENGTH)).machineComponents);
}

module.exports = {
  ERRORS,
  CODE_LENGTH,
  PAYLOAD_LENGTH,
  SIGNATURE_LENGTH,
  verifyLicense,
  peekMachineCode,
  splitMachineCodeFull,
};