/**
 * Non-régression : le renouvellement PROACTIF du jeton d'accès.
 *
 * Contexte : le front n'attendait plus le 401 pour renouveler. Résultat,
 * chaque ouverture d'onglet avec un access token de plus de ~30 min
 * produisait un 401 visible dans la console du navigateur et dans les
 * journaux du serveur, même quand la session se rétablissait aussitôt
 * (le couple 401 puis /auth/refresh 200 était devenu le cas nominal).
 *
 * Garanties vérifiées ici :
 *  1. un jeton expiré est renouvelé AVANT l'envoi : zéro 401 émis ;
 *  2. un renouvellement proactif qui échoue ne retente PAS le même refresh
 *     en réaction au 401 qui suit (une seule tentative, une seule déconnexion) ;
 *  3. un jeton encore valide ne déclenche aucun refresh prématuré ;
 *  4. un refus métier avec un jeton expiré ne déconnecte toujours pas.
 *
 * Exécution : npm test (dossier frontend)
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { loadApiService, FakeBackend } from './helpers/apiHarness.mjs';

const b64url = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url');
const jwtWithExp = (expSeconds) =>
  `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url({ sub: '1', exp: expSeconds })}.sig`;

const expiredJwt = () => jwtWithExp(Math.floor(Date.now() / 1000) - 60);
const validJwt = () => jwtWithExp(Math.floor(Date.now() / 1000) + 3600);

const EXPIRED = () => ({
  dyndisplay_token: expiredJwt(),
  dyndisplay_refresh_token: 'REFRESH1',
});

test('un jeton expiré est renouvelé avant l\'envoi : aucun 401 sur le chemin', async () => {
  const { service, store } = await loadApiService(EXPIRED());
  const backend = new FakeBackend();
  const restore = backend.install();

  try {
    const result = await service.request('/api/v1/layouts/1');

    assert.ok(result.ok, `la requête doit aboutir, statut ${result.status}`);
    assert.equal(backend.unauthorizedCount, 0,
      'le serveur ne doit jamais voir de jeton expiré : 0 x 401 attendu');
    assert.equal(backend.refreshCalls, 1, 'un seul renouvellement attendu');
    assert.equal(store.dyndisplay_token, backend.currentAccessToken,
      'le jeton renouvelé doit être écrit en session');
  } finally {
    restore();
  }
});

test('N requêtes avec un jeton expiré partagent un seul renouvellement proactif', async () => {
  const { service, store } = await loadApiService(EXPIRED());
  const backend = new FakeBackend();
  const restore = backend.install();

  try {
    const results = await Promise.all(
      Array.from({ length: 20 }, (_, i) => service.request(`/api/v1/layouts/${i}`)),
    );

    assert.ok(results.every((r) => r.ok), 'toutes les requêtes doivent aboutir');
    assert.equal(backend.refreshCalls, 1,
      `le verrou de refresh doit limiter à un appel, obtenu ${backend.refreshCalls}`);
    assert.equal(backend.unauthorizedCount, 0, 'aucun 401 ne doit être émis');
    assert.equal(store.dyndisplay_token, backend.currentAccessToken);
  } finally {
    restore();
  }
});

test('un renouvellement proactif qui échoue ne retente pas le refresh (1 seule déconnexion)', async () => {
  const { service, mod, store } = await loadApiService(EXPIRED());
  const backend = new FakeBackend();
  backend.refreshStatus = 401;
  const restore = backend.install();

  try {
    const events = [];
    const unsubscribe = mod.subscribeUnauthorized(() => events.push(1));

    const result = await service.request('/api/v1/layouts/1');
    unsubscribe();

    assert.equal(result.status, 401);
    assert.equal(backend.refreshCalls, 1,
      `une seule tentative de refresh attendue, obtenu ${backend.refreshCalls}`);
    assert.equal(events.length, 1, 'un seul événement de déconnexion');
    assert.equal(store.dyndisplay_token, undefined, 'le jeton doit être effacé');
    assert.equal(store.dyndisplay_refresh_token, undefined);
  } finally {
    restore();
  }
});

test('un jeton encore valide n\'entraîne aucun refresh prématuré', async () => {
  const token = validJwt();
  const { service, store } = await loadApiService({
    dyndisplay_token: token,
    dyndisplay_refresh_token: 'REFRESH1',
  });
  const backend = new FakeBackend();
  backend.validAccessTokens.add(token);
  const restore = backend.install();

  try {
    const result = await service.request('/api/v1/layouts/1');

    assert.ok(result.ok, `la requête doit aboutir, statut ${result.status}`);
    assert.equal(backend.refreshCalls, 0,
      'un jeton valide ne doit pas provoquer de renouvellement');
    assert.equal(backend.unauthorizedCount, 0);
    assert.equal(store.dyndisplay_token, token, 'le jeton doit rester en session');
  } finally {
    restore();
  }
});

test('un refus métier conserve la session même avec un jeton expiré', async () => {
  const { service, mod, store } = await loadApiService(EXPIRED());
  const tokenAvant = store.dyndisplay_token;
  const backend = new FakeBackend();
  const restore = backend.install();

  try {
    const events = [];
    const unsubscribe = mod.subscribeUnauthorized(() => events.push(1));
    const result = await service.request('/api/v1/settings/verify-access');
    unsubscribe();

    assert.equal(result.status, 401);
    assert.deepEqual(events, [], 'un mauvais mot de passe ne doit pas déconnecter');
    assert.equal(backend.refreshCalls, 0, 'aucun refresh sur un refus métier');
    assert.equal(store.dyndisplay_token, tokenAvant,
      'le jeton (expiré ou non) doit rester en session');
  } finally {
    restore();
  }
});
