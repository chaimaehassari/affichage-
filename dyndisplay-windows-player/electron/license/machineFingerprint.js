/*
 * Empreinte machine de la box Windows.
 *
 * Portage Node de DYNDISPLAY/backend/app/core/machine_fingerprint.py : les
 * trois composants DOIVENT donner exactement le meme code machine que le
 * backend, car l'app de serialisation signe a partir de ce code et la box le
 * reverifie localement.
 *
 * Trois composants, du plus stable au plus instable :
 *   1. MachineGuid Windows (registre HKLM),
 *   2. numero de serie du disque systeme,
 *   3. adresse MAC de la premiere interface reseau physique.
 *
 * Chaque composant est normalise (majuscules, separateurs retires) puis reduit
 * a ses 4 premiers octets de SHA-256. La licence embarque ces trois empreintes
 * separement : UN composant sur trois peut changer sans invalider la licence
 * (MATCH_THRESHOLD = 2).
 */
const crypto = require('crypto');
const os = require('os');
const { execFileSync } = require('child_process');

const FINGERPRINT_BYTES = 4;
const MATCH_THRESHOLD = 2;
const MACHINE_CODE_FULL_CHARS = 24;

// --- Normalisation -----------------------------------------------------------

function normalizeComponent(value) {
  if (!value) return 'UNKNOWN';
  const cleaned = String(value).replace(/[^0-9A-Za-z]+/g, '').toUpperCase();
  return cleaned || 'UNKNOWN';
}

function fingerprintComponent(value) {
  return crypto
    .createHash('sha256')
    .update(normalizeComponent(value), 'utf8')
    .digest()
    .subarray(0, FINGERPRINT_BYTES);
}

function normalizeHex(value) {
  return String(value || '').replace(/[^0-9A-Fa-f]/g, '').toUpperCase();
}

// --- Code machine ------------------------------------------------------------

// Format court 7F3A-92BC-4E10 (2 premiers octets de chaque empreinte).
function machineCodeFromComponents(hostId, diskSerial, mac) {
  const parts = [
    fingerprintComponent(hostId),
    fingerprintComponent(diskSerial),
    fingerprintComponent(mac),
  ];
  const raw = Buffer.concat(parts.map((p) => p.subarray(0, 2)));
  return raw.toString('hex').toUpperCase().match(/.{1,4}/g).join('-');
}

// Format COMPLET 1F3A9C2E-4B07D5A1-9E62 (les 3 empreintes entieres). C'est
// celui que la box affiche au revendeur : le format court est lossy (2 octets
// sur 4) et ne permettrait pas de reconstruire le payload signe.
function machineCodeFullFromComponents(hostId, diskSerial, mac) {
  const parts = [
    fingerprintComponent(hostId),
    fingerprintComponent(diskSerial),
    fingerprintComponent(mac),
  ];
  return Buffer.concat(parts).toString('hex').toUpperCase().match(/.{1,8}/g).join('-');
}

// Code machine complet -> les trois empreintes de 4 octets.
function splitMachineCodeFull(code) {
  const cleaned = normalizeHex(code);
  if (cleaned.length !== MACHINE_CODE_FULL_CHARS) {
    throw new Error(
      `Un code machine complet compte exactement ${MACHINE_CODE_FULL_CHARS} caracteres hexadecimaux (recu : ${cleaned.length}).`,
    );
  }
  const raw = Buffer.from(cleaned, 'hex');
  return [raw.subarray(0, 4), raw.subarray(4, 8), raw.subarray(8, 12)];
}

// Nombre de composants identiques entre deux triplets d'empreintes (0..3).
function componentsMatch(licensed, current) {
  let matches = 0;
  for (let i = 0; i < 3; i += 1) {
    if (Buffer.compare(licensed[i], current[i]) === 0) matches += 1;
  }
  return matches;
}

// --- Collecte reelle ---------------------------------------------------------

function run(argv) {
  try {
    return (
      execFileSync(argv[0], argv.slice(1), {
        encoding: 'utf8',
        timeout: 10000,
        windowsHide: true,
      }) || ''
    );
  } catch (err) {
    return '';
  }
}

function hostIdWindows() {
  // Lecture directe du registre : valeur stable utilisee par l'OS.
  const out = run(['reg', 'query', 'HKLM\\SOFTWARE\\Microsoft\\Cryptography', '/v', 'MachineGuid']);
  const match = out.match(/MachineGuid\s+REG_SZ\s+([0-9A-Fa-f-]+)/);
  if (match) return match[1];
  const ps = run([
    'powershell',
    '-NoProfile',
    '-NonInteractive',
    '-Command',
    "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography').MachineGuid",
  ]);
  return ps.trim();
}

function diskSerialWindows() {
  const out = run([
    'powershell',
    '-NoProfile',
    '-NonInteractive',
    '-Command',
    'Get-CimInstance -ClassName Win32_DiskDrive | Select-Object -First 1 -ExpandProperty SerialNumber',
  ]);
  for (const line of out.split(/\r?\n/)) {
    const candidate = line.trim();
    if (candidate) return candidate;
  }
  return '';
}

// MAC physique : on ecarte les adaptateurs virtuels (VMware, Hyper-V, vEthernet,
// VPN...) pour se rapprocher de `uuid.getnode()` cote Python/backend, puis on
// privilegie une interface dont l'octet d'administration locale est a 0.
const VIRTUAL_ADAPTER = /vmware|virtual|vether|vethernet|hyper-?v|loopback|docker|wsl|tap|tun|vpn|pseudo|bluetooth|tailscale|zerotier|hamachi|npcap|wan miniport|teredo|isatap|microsoft wi-?fi direct/i;

function isValidMac(hex) {
  return hex.length === 12 && hex !== '000000000000';
}
function isLocallyAdministered(hex) {
  return (parseInt(hex.slice(0, 2), 16) & 0x02) !== 0;
}
function isMulticast(hex) {
  return (parseInt(hex.slice(0, 2), 16) & 0x01) !== 0;
}
function formatMac(hex) {
  return hex.match(/.{2}/g).join(':');
}

function macAddress() {
  const interfaces = os.networkInterfaces();
  const candidates = [];
  for (const name of Object.keys(interfaces)) {
    for (const iface of interfaces[name] || []) {
      if (iface.internal) continue;
      const hex = normalizeHex(iface.mac);
      if (!isValidMac(hex) || isMulticast(hex)) continue;
      candidates.push({
        hex,
        virtual: VIRTUAL_ADAPTER.test(name),
        localAdmin: isLocallyAdministered(hex),
      });
    }
  }

  const pick =
    candidates.find((c) => !c.virtual && !c.localAdmin) ||
    candidates.find((c) => !c.virtual) ||
    candidates.find((c) => !c.localAdmin) ||
    candidates[0];
  if (pick) return formatMac(pick.hex);

  // Dernier recours : ipconfig (au cas ou os.networkInterfaces serait vide).
  const out = run(['ipconfig', '/all']);
  for (const match of out.matchAll(
    /Physical Address[^\n]*:\s*([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})/g,
  )) {
    const hex = normalizeHex(match[1]);
    if (isValidMac(hex)) return formatMac(hex);
  }
  return '';
}

function collectMachineFingerprint() {
  return {
    hostId: hostIdWindows(),
    diskSerial: diskSerialWindows(),
    mac: macAddress(),
  };
}

function currentComponentFingerprints() {
  const fp = collectMachineFingerprint();
  return [
    fingerprintComponent(fp.hostId),
    fingerprintComponent(fp.diskSerial),
    fingerprintComponent(fp.mac),
  ];
}

function currentMachineCodeFull() {
  const fp = collectMachineFingerprint();
  return machineCodeFullFromComponents(fp.hostId, fp.diskSerial, fp.mac);
}

function currentMachineCode() {
  const fp = collectMachineFingerprint();
  return machineCodeFromComponents(fp.hostId, fp.diskSerial, fp.mac);
}

module.exports = {
  FINGERPRINT_BYTES,
  MATCH_THRESHOLD,
  MACHINE_CODE_FULL_CHARS,
  normalizeComponent,
  fingerprintComponent,
  normalizeHex,
  machineCodeFromComponents,
  machineCodeFullFromComponents,
  splitMachineCodeFull,
  componentsMatch,
  collectMachineFingerprint,
  currentComponentFingerprints,
  currentMachineCode,
  currentMachineCodeFull,
};
