/*
 * Parametres de licence cote box.
 *
 * SEULE la cle PUBLIQUE est embarquee : la box verifie hors-ligne une licence
 * signee par le revendeur. La cle privee n'existe que dans l'APK de l'app de
 * serialisation et ne doit JAMAIS etre distribuee ici.
 *
 * La cle par defaut correspond a `vendor.license.ed25519.publicKey` de
 * serialisation/local.properties, elle-meme egale a LICENSE_PUBLIC_KEY du
 * backend. Surchargeable via DYNDISPLAY_LICENSE_PUBLIC_KEY (utile en test).
 */
const DEFAULT_PUBLIC_KEY_HEX =
  'f066f9a591d994cf35e026634eeb2ca25eec08f5552f784b605e391ae7a759e6';

function licensePublicKeyHex() {
  const raw = process.env.DYNDISPLAY_LICENSE_PUBLIC_KEY || DEFAULT_PUBLIC_KEY_HEX;
  return String(raw).trim().replace(/[^0-9A-Fa-f]/g, '').toUpperCase();
}

/**
 * Mode du gate de licence : `block` (défaut, aucune grâce) ou `grace`.
 * Surchargeable par DYNDISPLAY_LICENSE_GATE. Le défaut est volontairement
 * strict : activer la grâce est une décision explicite de déploiement.
 */
function licenseGate() {
  const raw = String(process.env.DYNDISPLAY_LICENSE_GATE || 'block').trim().toLowerCase();
  return raw === 'grace' ? 'grace' : 'block';
}

/** Durée de grâce en jours (0 = aucune). DYNDISPLAY_LICENSE_GRACE_DAYS. */
function graceDays() {
  const raw = parseInt(process.env.DYNDISPLAY_LICENSE_GRACE_DAYS || '0', 10);
  return Number.isFinite(raw) ? Math.max(0, raw) : 0;
}

module.exports = { DEFAULT_PUBLIC_KEY_HEX, licensePublicKeyHex, licenseGate, graceDays };
