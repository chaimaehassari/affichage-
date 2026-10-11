/*
 * Auto-test hors Electron de la vérification de licence Ed25519 v3.
 *
 * Il rejoue exactement le format produit par l'app revendeur
 * (Ed25519LicenseManager.kt) : construction du payload "TDL3" (sans quota ni
 * expiration), signature avec la clé privée revendeur, encodage Base32, puis
 * vérifie que le module de la box accepte les licences légitimes et refuse les
 * codes modifiés, étrangers à la box ou destinés à un autre client.
 *
 * La licence est PERMANENTE par construction : aucune notion d'expiration.
 *
 * Lancer : node test/licenseVerify.test.js
 */
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

const base32 = require('../electron/license/base32.js');
const { verifyLicense, peekMachineCode, ERRORS } = require('../electron/license/ed25519License.js');
const { createLicenseService } = require('../electron/license/licenseService.js');
const graceStore = require('../electron/license/graceStore.js');

// Paire de clés DÉDIÉE AUX TESTS, GÉNÉRÉE À L'EXÉCUTION : aucune clé privée
// n'est stockée dans ce dépôt. Elle ne sert qu'à signer les licences rejouées
// par cet auto-test ; la box, elle, embarque la clé PUBLIQUE de production.
// Ne JAMAIS introduire ici la clé privée revendeur réelle.
const TEST_KEYPAIR = crypto.generateKeyPairSync('ed25519');
const VENDOR_PRIVATE_KEY_HEX = TEST_KEYPAIR.privateKey
  .export({ format: 'der', type: 'pkcs8' })
  .subarray(-32)
  .toString('hex');
const VENDOR_PUBLIC_KEY_HEX = TEST_KEYPAIR.publicKey
  .export({ format: 'der', type: 'spki' })
  .subarray(-32)
  .toString('hex');

// Toutes les vérifications de cet auto-test utilisent la clé PUBLIQUE de test
// (surcharge supportée par licenseConfig), jamais celle embarquée en production.
process.env.DYNDISPLAY_LICENSE_PUBLIC_KEY = VENDOR_PUBLIC_KEY_HEX;

const PKCS8_ED25519_PREFIX = Buffer.from('302e020100300506032b657004220420', 'hex');
const MAGIC = Buffer.from('TDL3', 'ascii');
const PAYLOAD_LENGTH = 57;

function encodeField(value, width) {
  const ascii = Buffer.from(String(value).toUpperCase().replace(/[-\s]/g, ''), 'ascii');
  assert.ok(ascii.length <= width, `champ trop long: ${value}`);
  const out = Buffer.alloc(width);
  ascii.copy(out, width - ascii.length); // remplissage par zéros A GAUCHE (comme Kotlin)
  return out;
}

function machineComponentsFromFull(full) {
  const hex = full.replace(/[^0-9A-Fa-f]/g, '').toUpperCase();
  const raw = Buffer.from(hex, 'hex');
  return [raw.subarray(0, 4), raw.subarray(4, 8), raw.subarray(8, 12)];
}

function buildAndSign({ client, site, post, machineFull }) {
  const components = machineComponentsFromFull(machineFull);
  const payload = Buffer.alloc(PAYLOAD_LENGTH);
  MAGIC.copy(payload, 0);
  payload[4] = 3;
  encodeField(client, 8).copy(payload, 5);
  encodeField(site, 16).copy(payload, 13);
  encodeField(post, 16).copy(payload, 29);
  components[0].copy(payload, 45);
  components[1].copy(payload, 49);
  components[2].copy(payload, 53);

  const privateKey = crypto.createPrivateKey({
    key: Buffer.concat([PKCS8_ED25519_PREFIX, Buffer.from(VENDOR_PRIVATE_KEY_HEX, 'hex')]),
    format: 'der',
    type: 'pkcs8',
  });
  const signature = crypto.sign(null, payload, privateKey);
  return base32.encode(Buffer.concat([payload, signature]));
}

function check(name, fn) {
  try {
    fn();
    console.log(`  ok  - ${name}`);
    return true;
  } catch (err) {
    console.error(`FAIL  - ${name}\n        ${err.message}`);
    return false;
  }
}

const MACHINE_A = '11223344-55667788-99AABBCC';
const MACHINE_B = 'AABBCCDD-EEFF0011-22334455';

let allOk = true;

allOk &= check('licence valide acceptée, champs décodés', () => {
  const code = buildAndSign({ client: 'CLIENT01', site: 'SITE-ALPHA', post: 'POSTE-42', machineFull: MACHINE_A });
  const res = verifyLicense(code, { machineComponents: machineComponentsFromFull(MACHINE_A) });
  assert.strictEqual(res.valid, true, res.error || 'devrait être valide');
  assert.strictEqual(res.summary.clientCode, 'CLIENT01');
  // Le générateur normalise (majuscules, tirets/espaces retirés).
  assert.strictEqual(res.summary.siteCode, 'SITEALPHA');
  assert.strictEqual(res.summary.postCode, 'POSTE42');
  assert.strictEqual(res.summary.machineCodeFull, MACHINE_A);
  // Permanente par construction : aucun champ d'expiration dans le payload.
  assert.strictEqual('expiresAt' in res.summary, false);
  assert.strictEqual('sites' in res.summary, false);
  assert.strictEqual('postes' in res.summary, false);
});

allOk &= check('box étrangère refusée (1/3 empreintes)', () => {
  const code = buildAndSign({ client: 'CLIENT01', site: 'S', post: 'P', machineFull: MACHINE_A });
  const wrong = [
    machineComponentsFromFull(MACHINE_A)[0],
    machineComponentsFromFull(MACHINE_B)[1],
    machineComponentsFromFull(MACHINE_B)[2],
  ];
  const res = verifyLicense(code, { machineComponents: wrong });
  assert.strictEqual(res.valid, false);
  assert.strictEqual(res.errorCode, ERRORS.MACHINE_MISMATCH);
});

allOk &= check('tolérance 2/3 acceptée', () => {
  const code = buildAndSign({ client: 'CLIENT01', site: 'S', post: 'P', machineFull: MACHINE_A });
  const a = machineComponentsFromFull(MACHINE_A);
  const b = machineComponentsFromFull(MACHINE_B);
  const res = verifyLicense(code, { machineComponents: [a[0], a[1], b[2]] });
  assert.strictEqual(res.valid, true, res.error || 'devrait tolérer 2/3');
});

allOk &= check('code modifié refusé (signature) — client', () => {
  const code = buildAndSign({ client: 'CLIENT01', site: 'S', post: 'P', machineFull: MACHINE_A });
  const bytes = base32.decode(code);
  bytes[5] = bytes[5] ^ 0xff; // altère le champ client (offset 5)
  const tampered = base32.encode(bytes);
  const res = verifyLicense(tampered, { machineComponents: machineComponentsFromFull(MACHINE_A) });
  assert.strictEqual(res.valid, false);
  assert.strictEqual(res.errorCode, ERRORS.BAD_SIGNATURE);
});

allOk &= check('code modifié refusé (signature) — site', () => {
  const code = buildAndSign({ client: 'CLIENT01', site: 'SITE-ALPHA', post: 'P', machineFull: MACHINE_A });
  const bytes = base32.decode(code);
  bytes[13] = bytes[13] ^ 0xff; // altère le champ site (offset 13)
  const res = verifyLicense(base32.encode(bytes), { machineComponents: machineComponentsFromFull(MACHINE_A) });
  assert.strictEqual(res.valid, false);
  assert.strictEqual(res.errorCode, ERRORS.BAD_SIGNATURE);
});

allOk &= check('code modifié refusé (signature) — poste', () => {
  const code = buildAndSign({ client: 'CLIENT01', site: 'S', post: 'POSTE-42', machineFull: MACHINE_A });
  const bytes = base32.decode(code);
  bytes[29] = bytes[29] ^ 0xff; // altère le champ poste (offset 29)
  const res = verifyLicense(base32.encode(bytes), { machineComponents: machineComponentsFromFull(MACHINE_A) });
  assert.strictEqual(res.valid, false);
  assert.strictEqual(res.errorCode, ERRORS.BAD_SIGNATURE);
});

allOk &= check('code modifié refusé (signature) — numéro de box', () => {
  const code = buildAndSign({ client: 'CLIENT01', site: 'S', post: 'P', machineFull: MACHINE_A });
  const bytes = base32.decode(code);
  bytes[45] = bytes[45] ^ 0xff; // altère la 1re empreinte machine (offset 45)
  const res = verifyLicense(base32.encode(bytes), { machineComponents: machineComponentsFromFull(MACHINE_A) });
  assert.strictEqual(res.valid, false);
  assert.strictEqual(res.errorCode, ERRORS.BAD_SIGNATURE);
});

allOk &= check('mauvais client refusé', () => {
  const code = buildAndSign({ client: 'CLIENT01', site: 'S', post: 'P', machineFull: MACHINE_A });
  const res = verifyLicense(code, {
    machineComponents: machineComponentsFromFull(MACHINE_A),
    expectedClientCode: 'AUTRE',
  });
  assert.strictEqual(res.valid, false);
  assert.strictEqual(res.errorCode, ERRORS.CLIENT_MISMATCH);
});

allOk &= check('peekMachineCode reflète le code embarqué', () => {
  const code = buildAndSign({ client: 'CLIENT01', site: 'S', post: 'P', machineFull: MACHINE_A });
  assert.strictEqual(peekMachineCode(code), MACHINE_A);
});

allOk &= check('clé publique de test cohérente', () => {
  const privateKey = crypto.createPrivateKey({
    key: Buffer.concat([PKCS8_ED25519_PREFIX, Buffer.from(VENDOR_PRIVATE_KEY_HEX, 'hex')]),
    format: 'der', type: 'pkcs8',
  });
  const publicKey = crypto.createPublicKey(privateKey);
  const spki = publicKey.export({ format: 'der', type: 'spki' });
  const raw = spki.subarray(spki.length - 32).toString('hex');
  assert.strictEqual(raw, VENDOR_PUBLIC_KEY_HEX);
});

allOk &= check('code malformé refusé sans lever', () => {
  const bads = ['', '   ', 'AAAA', 'pas-du-base32!!!', 'TDL3', '0'];
  for (const bad of bads) {
    const res = verifyLicense(bad, { machineComponents: machineComponentsFromFull(MACHINE_A) });
    assert.strictEqual(res.valid, false, `code ${JSON.stringify(bad)} ne doit pas être valide`);
    assert.ok(
      ['EMPTY', 'BAD_BASE32', 'BAD_LENGTH', 'BAD_MAGIC', 'BAD_VERSION'].includes(res.errorCode),
      `code ${JSON.stringify(bad)} -> errorCode inattendu ${res.errorCode}`,
    );
  }
});

// ── Gate : période de grâce (déploiement) ───────────────────────────────────

function fakeSafeStorage() {
  return {
    isEncryptionAvailable: () => true,
    encryptString: (s) => Buffer.from('enc:' + String(s), 'utf8'),
    decryptString: (b) => Buffer.from(String(b).replace(/^enc:/, ''), 'utf8'),
  };
}

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'dyndisplay-grace-'));
}

function withEnv(env, fn) {
  const saved = {};
  for (const k of Object.keys(env)) {
    saved[k] = process.env[k];
    process.env[k] = env[k];
  }
  try {
    return fn();
  } finally {
    for (const k of Object.keys(env)) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  }
}

allOk &= check('gate : mode par défaut = block, aucun fichier de grâce créé', () => {
  const dir = tmpDir();
  const licensePath = path.join(dir, 'license.dat');
  const gracePath = path.join(dir, 'license-grace.json');
  const service = createLicenseService({ licensePath, gracePath, safeStorage: fakeSafeStorage() });
  const decision = service.canStart();
  assert.strictEqual(decision.canStart, false);
  assert.strictEqual(decision.reason, 'blocked');
  assert.strictEqual(fs.existsSync(gracePath), false);
});

allOk &= check('gate : grâce active tolère la box sans licence saisie', () => {
  const dir = tmpDir();
  const licensePath = path.join(dir, 'license.dat');
  const gracePath = path.join(dir, 'license-grace.json');
  const service = createLicenseService({ licensePath, gracePath, safeStorage: fakeSafeStorage() });
  const decision = withEnv(
    { DYNDISPLAY_LICENSE_GATE: 'grace', DYNDISPLAY_LICENSE_GRACE_DAYS: '6' },
    () => service.canStart(),
  );
  assert.strictEqual(decision.canStart, true);
  assert.strictEqual(decision.reason, 'grace');
  assert.strictEqual(decision.graceDays, 6);
  assert.strictEqual(decision.graceRemainingDays, 6);
  assert.ok(fs.existsSync(gracePath), 'la grâce doit être mémorisée');
});

allOk &= check('gate : grâce expirée bloque', () => {
  const dir = tmpDir();
  const licensePath = path.join(dir, 'license.dat');
  const gracePath = path.join(dir, 'license-grace.json');
  graceStore.touchGrace(gracePath, Date.now() - 8 * 24 * 3600 * 1000);
  const service = createLicenseService({ licensePath, gracePath, safeStorage: fakeSafeStorage() });
  const decision = withEnv(
    { DYNDISPLAY_LICENSE_GATE: 'grace', DYNDISPLAY_LICENSE_GRACE_DAYS: '6' },
    () => service.canStart(),
  );
  assert.strictEqual(decision.canStart, false);
  assert.strictEqual(decision.reason, 'grace-expired');
  assert.strictEqual(decision.graceRemainingDays, 0);
});

allOk &= check('gate : licence valide = start, jamais de grâce', () => {
  const dir = tmpDir();
  const licensePath = path.join(dir, 'license.dat');
  const gracePath = path.join(dir, 'license-grace.json');
  const code = buildAndSign({ client: 'CLIENT01', site: 'SITE-ALPHA', post: 'POSTE-42', machineFull: MACHINE_A });
  const service = createLicenseService({
    licensePath,
    gracePath,
    safeStorage: fakeSafeStorage(),
    machineComponentsOverride: machineComponentsFromFull(MACHINE_A),
  });
  withEnv(
    { DYNDISPLAY_LICENSE_GATE: 'grace', DYNDISPLAY_LICENSE_GRACE_DAYS: '6' },
    () => {
      const act = service.activate({ code, clientCode: 'CLIENT01' });
      assert.strictEqual(act.ok, true, act.error || 'activation devrait réussir');
    },
  );
  const decision = withEnv({ DYNDISPLAY_LICENSE_GATE: 'grace' }, () => service.canStart());
  assert.strictEqual(decision.canStart, true);
  assert.strictEqual(decision.reason, 'licensed');
  assert.ok(!fs.existsSync(gracePath), 'une licence valide efface la grâce');
});

if (!allOk) {
  console.error('\nDes tests ont échoué.');
  process.exit(1);
}
console.log('\nTous les tests de licence sont passés.');