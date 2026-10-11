/*
 * Stockage local de la licence, chiffre via le trousseau de l'OS.
 *
 * Windows : Electron `safeStorage` s'appuie sur DPAPI (chiffrement lie au
 * compte utilisateur). Le fichier sur disque ne contient alors qu'un blob
 * illisible en dehors de cette machine/compte, ce qui empeche la simple copie
 * du fichier de licence vers une autre box.
 *
 * Repli (safeStorage indisponible, ex. session Linux sans trousseau) : JSON en
 * clair, avec un marqueur `plain: true`. La securite repose alors uniquement
 * sur la signature : la licence reste verifiee a chaque demarrage.
 */
const fs = require('fs');
const path = require('path');

const STORE_VERSION = 1;

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function readLicense(filePath, safeStorage) {
  try {
    if (!fs.existsSync(filePath)) return null;
    const envelope = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    if (!envelope || envelope.v !== STORE_VERSION) return null;

    if (envelope.enc) {
      if (!safeStorage || !safeStorage.isEncryptionAvailable()) return null;
      const decrypted = safeStorage.decryptString(Buffer.from(envelope.enc, 'base64'));
      const parsed = JSON.parse(decrypted);
      return parsed && typeof parsed === 'object' ? parsed : null;
    }
    if (envelope.plain && envelope.data) {
      return envelope.data;
    }
    return null;
  } catch (err) {
    return null;
  }
}

function writeLicense(filePath, safeStorage, data) {
  ensureDir(path.dirname(filePath));
  let envelope;
  if (safeStorage && safeStorage.isEncryptionAvailable()) {
    const blob = safeStorage.encryptString(JSON.stringify(data));
    envelope = { v: STORE_VERSION, enc: blob.toString('base64') };
  } else {
    envelope = { v: STORE_VERSION, plain: true, data };
  }
  fs.writeFileSync(filePath, JSON.stringify(envelope), { encoding: 'utf8', mode: 0o600 });
  return true;
}

function clearLicense(filePath) {
  try {
    if (fs.existsSync(filePath)) fs.rmSync(filePath, { force: true });
    return true;
  } catch (err) {
    return false;
  }
}

module.exports = { STORE_VERSION, readLicense, writeLicense, clearLicense };
