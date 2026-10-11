/*
 * État de la période de grâce d'une box sans licence valide.
 *
 * En mode `grace`, une box déjà installée (donc sans fichier de licence) peut
 * continuer de fonctionner pendant GRACE_DAYS jours après sa première
 * observation, le temps que les équipes installent la licence. Passé ce
 * délai, elle est définitivement bloquée sur l'écran d'activation.
 *
 * Le mode par défaut est `block` (aucune grâce) : le gate n'affaiblit jamais
 * une installation qui n'a PAS été explicitement mise en grâce.
 */
const fs = require('fs');
const path = require('path');

const GRACE_VERSION = 1;

function readGrace(filePath) {
  try {
    if (!fs.existsSync(filePath)) return null;
    const parsed = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    if (!parsed || parsed.v !== GRACE_VERSION || typeof parsed.seenAt !== 'number') return null;
    return parsed;
  } catch (err) {
    return null;
  }
}

function touchGrace(filePath, now = Date.now()) {
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(
      filePath,
      JSON.stringify({ v: GRACE_VERSION, seenAt: now, seenAtIso: new Date(now).toISOString() }),
      { encoding: 'utf8', mode: 0o600 },
    );
    return true;
  } catch (err) {
    return false;
  }
}

module.exports = { GRACE_VERSION, readGrace, touchGrace };