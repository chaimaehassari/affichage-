/*
 * Service de licence cote box : relie empreinte machine, verification Ed25519
 * hors-ligne et stockage chiffre. Aucune dependance a Electron en dehors de
 * l'objet `safeStorage` injecte, ce qui rend la logique testable en isolation.
 */
const { currentComponentFingerprints, currentMachineCode, currentMachineCodeFull } = require('./machineFingerprint.js');
const { verifyLicense, ERRORS } = require('./ed25519License.js');
const { licenseGate, graceDays } = require('./licenseConfig.js');
const store = require('./licenseStore.js');
const graceStore = require('./graceStore.js');

const FINGERPRINT_CACHE_MS = 10 * 60 * 1000;

function createLicenseService({ licensePath, gracePath, safeStorage, machineComponentsOverride = null }) {
  let fingerprintCache = null;

  function machineComponents() {
    // Injection de test : reprodure exactement le comportement de production.
    if (machineComponentsOverride) return machineComponentsOverride;
    const now = Date.now();
    if (!fingerprintCache || now - fingerprintCache.at > FINGERPRINT_CACHE_MS) {
      fingerprintCache = { at: now, components: currentComponentFingerprints() };
    }
    return fingerprintCache.components;
  }

  function machineInfo() {
    return {
      short: currentMachineCode(),
      full: currentMachineCodeFull(),
    };
  }

  function verifyWithMachine(code, opts = {}) {
    return verifyLicense(code, { ...opts, machineComponents: machineComponents() });
  }

  function status() {
    const record = store.readLicense(licensePath, safeStorage);
    if (!record || !record.code) {
      return { activated: false, valid: false, errorCode: 'NO_LICENSE', error: null, summary: null };
    }
    const result = verifyWithMachine(record.code);
    record.lastVerify = {
      at: new Date().toISOString(),
      ok: result.valid,
      errorCode: result.errorCode,
      error: result.error,
    };
    store.writeLicense(licensePath, safeStorage, record);
    return {
      activated: true,
      valid: result.valid,
      errorCode: result.errorCode,
      error: result.error,
      summary: result.summary,
      activatedAt: record.activatedAt || null,
      lastVerify: record.lastVerify,
    };
  }

  /**
   * Décision du gate au démarrage :
   *   - licence valide            -> start ;
   *   - mode `block` (défaut)     -> block ;
   *   - mode `grace`              -> start pendant GRACE_DAYS jours après la
   *     première observation, puis block.
   * La première observation est enregistrée uniquement quand la boîte passe
   * par le mode grâce (elle n'est jamais créée en mode `block`).
   */
  function canStart() {
    const st = status();
    if (st.valid) {
      return { canStart: true, reason: 'licensed', graceDays: 0, graceRemainingDays: 0 };
    }
    const gate = licenseGate();
    const days = graceDays();
    if (gate !== 'grace' || days <= 0) {
      return { canStart: false, reason: 'blocked', graceDays: days, graceRemainingDays: 0 };
    }
    const now = Date.now();
    let rec = graceStore.readGrace(gracePath);
    if (!rec || typeof rec.seenAt !== 'number') {
      graceStore.touchGrace(gracePath, now);
      rec = graceStore.readGrace(gracePath);
    }
    const seenAt = rec && typeof rec.seenAt === 'number' ? rec.seenAt : now;
    const windowMs = days * 24 * 60 * 60 * 1000;
    const remainingMs = Math.max(0, windowMs - (now - seenAt));
    const remainingDays = Math.ceil(remainingMs / (24 * 60 * 60 * 1000));
    return {
      canStart: remainingMs > 0,
      reason: remainingMs > 0 ? 'grace' : 'grace-expired',
      graceDays: days,
      graceRemainingDays: remainingDays,
    };
  }

  function activate({ code, clientCode }) {
    const result = verifyWithMachine(code, {
      expectedClientCode: clientCode,
    });
    if (!result.valid) {
      return { ok: false, errorCode: result.errorCode, error: result.error, summary: null };
    }
    const record = {
      code: String(code).trim(),
      clientCode: result.summary.clientCode,
      activatedAt: new Date().toISOString(),
      lastVerify: { at: new Date().toISOString(), ok: true, errorCode: null, error: null },
    };
    store.writeLicense(licensePath, safeStorage, record);
    // Une licence valide efface la trace de grâce éventuelle.
    if (graceStore.readGrace(gracePath)) {
      try {
        const fs = require('fs');
        if (fs.existsSync(gracePath)) fs.rmSync(gracePath, { force: true });
      } catch (err) {
        // sans importance
      }
    }
    return { ok: true, errorCode: null, error: null, summary: result.summary, activatedAt: record.activatedAt };
  }

  function clear() {
    return store.clearLicense(licensePath);
  }

  return { ERRORS, machineInfo, status, activate, clear, canStart };
}

module.exports = { createLicenseService };
