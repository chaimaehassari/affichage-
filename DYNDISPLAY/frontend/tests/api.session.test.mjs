/**
 * Partie 2 — stabilisation de la navbar face aux 401.
 *
 * Garanties vérifiées au niveau du service réseau (source unique de la
 * déconnexion) :
 *  - une RAFALE de 401 MÉTIER ne vide JAMAIS la session (le menu ne clignote
 *    pas, l'utilisateur n'est pas renvoyé au login) ;
 *  - une rafale de 401 de SESSION (rafraîchissement en échec) n'émet qu'UN
 *    seul événement de déconnexion (donc une seule redirection vers /login).
 *
 * Exécution : node --import ./tests/helpers/extensionLoader.mjs --test tests/
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { loadApiService, FakeBackend } from './helpers/apiHarness.mjs';

test('une rafale de 401 MÉTIER ne vide jamais la session', async () => {
  const { service, mod, store } = await loadApiService({
    dyndisplay_token: 'OLD',
    dyndisplay_refresh_token: 'REFRESH1',
  });
  const backend = new FakeBackend();
  const restore = backend.install();

  try {
    const events = [];
    const unsubscribe = mod.subscribeUnauthorized(() => events.push(1));

    // /settings/verify-access est un refus métier : mot de passe d'accès faux.
    const results = await Promise.all(
      Array.from({ length: 20 }, () => service.request('/api/v1/settings/verify-access')),
    );
    unsubscribe();

    assert.ok(results.every((r) => r.status === 401));
    assert.deepEqual(events, [], 'un 401 métier ne doit pas déconnecter');
    assert.equal(store.dyndisplay_token, 'OLD', 'le jeton de session doit rester');
    assert.equal(backend.refreshCalls, 0, 'aucun refresh sur un refus métier');
  } finally {
    restore();
  }
});

test('une rafale de 401 de SESSION n\'émet qu\'une seule déconnexion', async () => {
  const { service, mod, store } = await loadApiService({
    dyndisplay_token: 'OLD',
    dyndisplay_refresh_token: 'DEAD',
  });
  const backend = new FakeBackend();
  backend.refreshStatus = 401;
  const restore = backend.install();

  try {
    const events = [];
    const unsubscribe = mod.subscribeUnauthorized(() => events.push(1));

    await Promise.all(
      Array.from({ length: 25 }, (_, i) => service.request(`/api/v1/layouts/${i}`)),
    );
    unsubscribe();

    assert.equal(events.length, 1, `un seul événement attendu, reçu ${events.length}`);
    assert.equal(store.dyndisplay_token, undefined, 'la session réelle est bien close');
  } finally {
    restore();
  }
});
