/**
 * Non-régression : la cascade de 401 sur les rafales de /layouts/{id}.
 *
 * Garanties vérifiées ici :
 *  1. le renouvellement est unique et verrouillé (1 appel pour N 401) ;
 *  2. la requête est rejouée une seule fois après un renouvellement réussi ;
 *  3. le jeton n'est effacé qu'après un échec DÉFINITIF, et une seule fois ;
 *  4. un refus métier (401 sans rapport avec la session) ne déconnecte pas.
 *
 * Exécution : node --test tests/
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { loadApiService, FakeBackend } from './helpers/apiHarness.mjs';

const EXPIRED = () => ({
  dyndisplay_token: 'OLD',
  dyndisplay_refresh_token: 'REFRESH1',
});

test('N requêtes en échec simultanées ne déclenchent qu\'UN seul refresh', async () => {
  const { service, store } = await loadApiService(EXPIRED());
  const backend = new FakeBackend();
  const restore = backend.install();

  try {
    const results = await Promise.all(
      Array.from({ length: 40 }, (_, i) => service.request(`/api/v1/layouts/${i}`)),
    );

    assert.equal(backend.refreshCalls, 1,
      `un seul appel à /auth/refresh attendu, obtenu ${backend.refreshCalls}`);
    assert.ok(results.every((r) => r.ok),
      `toutes les requêtes doivent aboutir, statuts: ${results.map((r) => r.status).join(',')}`);
    assert.equal(store.dyndisplay_token, backend.currentAccessToken,
      'le jeton renouvelé doit être écrit en session');
  } finally {
    restore();
  }
});

test('le verrou est libéré : un second batch déclenche un nouveau refresh', async () => {
  const { service } = await loadApiService(EXPIRED());
  const backend = new FakeBackend();
  const restore = backend.install();

  try {
    const first = await Promise.all([
      service.request('/api/v1/layouts/1'),
      service.request('/api/v1/layouts/2'),
    ]);
    assert.equal(backend.refreshCalls, 1);
    assert.ok(first.every((r) => r.ok));

    // Le jeton obtenu au tour précédent a expiré : le verrou doit être libre
    // et un second refresh doit avoir lieu au lieu de bloquer les requêtes.
    backend.expireCurrentAccessToken();
    const second = await Promise.all([
      service.request('/api/v1/layouts/3'),
      service.request('/api/v1/layouts/4'),
    ]);
    assert.equal(backend.refreshCalls, 2,
      'le verrou ne doit pas rester bloqué après un refresh terminé');
    assert.ok(second.every((r) => r.ok),
      `le second lot doit aboutir, statuts: ${second.map((r) => r.status).join(',')}`);
  } finally {
    restore();
  }
});

test('un batch en échec définitif n\'émet qu\'un seul événement de déconnexion', async () => {
  const { service, mod, store } = await loadApiService(EXPIRED());
  const backend = new FakeBackend();
  backend.refreshStatus = 401;
  const restore = backend.install();

  try {
    const events = [];
    const unsubscribe = mod.subscribeUnauthorized(() => events.push(1));

    const results = await Promise.all(
      Array.from({ length: 15 }, (_, i) => service.request(`/api/v1/layouts/${i}`)),
    );
    unsubscribe();

    assert.ok(results.every((r) => r.status === 401));
    assert.equal(events.length, 1,
      `un seul événement attendu, reçu ${events.length}`);
    assert.equal(store.dyndisplay_token, undefined, 'le jeton doit être effacé');
    assert.equal(store.dyndisplay_refresh_token, undefined,
      'le refresh token doit être effacé avec le jeton d\'accès');
  } finally {
    restore();
  }
});

test('le rejeu après refresh ne boucle pas si le serveur refuse à nouveau', async () => {
  const { service, mod, store } = await loadApiService(EXPIRED());
  const backend = new FakeBackend();
  // Même un jeton « neuf » est refusé : le rejeu ne doit pas repartir en boucle.
  backend.alwaysRejectLayouts = true;
  const restore = backend.install();

  try {
    const events = [];
    const unsubscribe = mod.subscribeUnauthorized(() => events.push(1));
    const result = await service.request('/api/v1/layouts/1');
    unsubscribe();

    assert.equal(result.status, 401);
    assert.equal(backend.refreshCalls, 1, 'un seul essai de refresh');
    assert.equal(backend.layoutDetailCalls, 2, 'appel initial + un seul rejeu');
    // Un jeton frais refusé est un refus définitif : sans cela la session
    // resterait en localStorage avec un token que le serveur rejette, et
    // l'utilisateur resterait sur une page morte jusqu'au rechargement.
    assert.equal(events.length, 1, 'un jeton neuf refusé doit déconnecter');
    assert.equal(store.dyndisplay_token, undefined);
    assert.equal(store.dyndisplay_refresh_token, undefined);
  } finally {
    restore();
  }
});

test('un refus métier conserve la session et ne déclenche aucun refresh', async () => {
  const { service, mod, store } = await loadApiService(EXPIRED());
  const backend = new FakeBackend();
  const restore = backend.install();

  try {
    const events = [];
    const unsubscribe = mod.subscribeUnauthorized(() => events.push(1));
    const result = await service.request('/api/v1/settings/verify-access');
    unsubscribe();

    assert.equal(result.status, 401);
    assert.deepEqual(events, [], 'un mauvais mot de passe ne doit pas déconnecter');
    assert.equal(store.dyndisplay_token, 'OLD', 'le jeton valide doit rester en session');
    assert.equal(backend.refreshCalls, 0, 'aucun refresh sur un refus métier');
  } finally {
    restore();
  }
});

test('sans refresh token, un 401 déconnecte proprement', async () => {
  const { service, mod, store } = await loadApiService({ dyndisplay_token: 'OLD' });
  const backend = new FakeBackend();
  const restore = backend.install();

  try {
    const events = [];
    const unsubscribe = mod.subscribeUnauthorized(() => events.push(1));
    const result = await service.request('/api/v1/layouts/1');
    unsubscribe();

    assert.equal(result.status, 401);
    assert.equal(backend.refreshCalls, 0, 'rien à renouveler sans refresh token');
    assert.equal(events.length, 1);
    assert.equal(store.dyndisplay_token, undefined);
  } finally {
    restore();
  }
});

test('une reconnexion réarme la session après une déconnexion', async () => {
  const { service, store } = await loadApiService({
    dyndisplay_token: 'OLD',
    dyndisplay_refresh_token: 'DEAD',
  });
  const backend = new FakeBackend();
  backend.refreshStatus = 401;
  const restore = backend.install();

  try {
    await service.request('/api/v1/layouts/1');
    assert.equal(store.dyndisplay_token, undefined);

    // Simule le login : l'utilisateur se reconnecte après une déconnexion.
    backend.refreshStatus = 200;
    backend.validAccessTokens.add('AFTER_LOGIN');
    service.setToken('AFTER_LOGIN');
    service.setRefreshToken('REFRESH_AFTER_LOGIN');

    const result = await service.request('/api/v1/layouts/1');
    assert.ok(result.ok, 'la session réarmée doit de nouveau fonctionner');
  } finally {
    restore();
  }
});
