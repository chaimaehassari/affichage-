/**
 * Non-régression : la rafale de GET /layouts/{id} et la cascade de 401.
 *
 * Historiquement DisplayConfig déclenchait un GET /layouts/{id} par modèle
 * (713 modèles en base, soit 713 requêtes). Ces tests verrouillent le
 * remplacement par UN appel groupé, avec cache et invalidation.
 *
 * Exécution :
 *   node --import ./tests/helpers/extensionLoader.mjs --test tests/
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { loadApiService, FakeBackend } from './helpers/apiHarness.mjs';

const SAMPLE = [
  {
    layout_id: 315,
    name: 'Double',
    is_active: true,
    active_zone_count: 2,
    zones: [
      { layout_zone_id: 1, zone_number: 1, position_x: 0, position_y: 0, width: 50, height: 100, is_active: true },
      { layout_zone_id: 2, zone_number: 2, position_x: 50, position_y: 0, width: 50, height: 100, is_active: true },
    ],
  },
  { layout_id: 1170, name: 'Simple', is_active: true, active_zone_count: 1, zones: [] },
];

/**
 * Charge services/layouts.js. Le jeton 'VALID' est déclaré valide par le
 * FakeBackend : ces tests portent sur la requête groupée, pas sur le refresh.
 */
async function loadLayoutsService() {
  const { store } = await loadApiService({ dyndisplay_token: 'VALID' });
  const url = new URL('../src/services/layouts.js', import.meta.url);
  const layoutsMod = await import(`${url.href}?t=${Date.now()}${Math.random()}`);
  return { layouts: layoutsMod, store };
}

/** FakeBackend pré-configuré pour accepter le jeton de session du test. */
function authenticatedBackend(layoutPayload = SAMPLE) {
  const backend = new FakeBackend();
  backend.validAccessTokens.add('VALID');
  backend.layoutPayload = layoutPayload;
  return backend;
}

test('les modèles + zones arrivent en UNE requête groupée', async () => {
  const { layouts } = await loadLayoutsService();
  const backend = authenticatedBackend();
  const restore = backend.install();

  try {
    const res = await layouts.getLayoutsWithZones();
    assert.deepEqual(res, SAMPLE);
    assert.equal(backend.layoutsListCalls, 1,
      'un seul appel HTTP doit suffire pour tous les modèles');
    assert.equal(backend.layoutDetailCalls, 0,
      'aucun GET /layouts/{id} ne doit être émis');
  } finally {
    restore();
  }
});

test('le cache évite de refaire l\'appel à chaque focus', async () => {
  const { layouts } = await loadLayoutsService();
  const backend = authenticatedBackend();
  const restore = backend.install();

  try {
    const first = await layouts.getLayoutsWithZones();
    const second = await layouts.getLayoutsWithZones();
    assert.deepEqual(first, SAMPLE);
    assert.deepEqual(second, SAMPLE);
    assert.equal(backend.layoutsListCalls, 1,
      'le deuxième appel doit venir du cache, pas du réseau');
  } finally {
    restore();
  }
});

test('deux appels simultanés partagent UNE seule requête', async () => {
  const { layouts } = await loadLayoutsService();
  const backend = authenticatedBackend();
  const restore = backend.install();

  try {
    const [a, b] = await Promise.all([
      layouts.getLayoutsWithZones(),
      layouts.getLayoutsWithZones(),
    ]);
    assert.deepEqual(a, SAMPLE);
    assert.deepEqual(b, SAMPLE);
    assert.equal(backend.layoutsListCalls, 1,
      'deux init() qui se chevauchent ne doivent pas doubler la requête');
  } finally {
    restore();
  }
});

test('une modification de modèle invalide le cache', async () => {
  const { layouts } = await loadLayoutsService();
  const backend = authenticatedBackend();
  const restore = backend.install();

  try {
    await layouts.getLayoutsWithZones();
    assert.equal(backend.layoutsListCalls, 1);

    // Sauvegarde des zones d'un modèle : le cache doit devenir inutilisable.
    await layouts.updateLayout(315, { is_active: true, zones: [] });
    assert.equal(backend.updateCalls, 1);

    const afterUpdate = await layouts.getLayoutsWithZones();
    assert.equal(backend.layoutsListCalls, 2,
      'après une écriture, le cache doit être rechargé');
    assert.deepEqual(afterUpdate, SAMPLE);
  } finally {
    restore();
  }
});

test('invalidateLayoutsCache() force explicitement le rechargement', async () => {
  const { layouts } = await loadLayoutsService();
  const backend = authenticatedBackend();
  const restore = backend.install();

  try {
    await layouts.getLayoutsWithZones();
    await layouts.getLayoutsWithZones();
    assert.equal(backend.layoutsListCalls, 1);

    layouts.invalidateLayoutsCache();
    await layouts.getLayoutsWithZones();
    assert.equal(backend.layoutsListCalls, 2);
  } finally {
    restore();
  }
});

test('le cache expire : un modèle créé entre-temps finit par réapparaître', async () => {
  const { layouts } = await loadLayoutsService();
  const backend = authenticatedBackend();
  const restore = backend.install();
  const realNow = Date.now;

  try {
    await layouts.getLayoutsWithZones();
    assert.equal(backend.layoutsListCalls, 1);

    // Un modèle est créé depuis un autre écran, puis l'utilisateur revient.
    const created = { layout_id: 2000, name: 'Nouveau', is_active: true, active_zone_count: 0, zones: [] };
    backend.layoutPayload = [...SAMPLE, created];

    // Tant que le cache est frais (focus, onglet redeployé) : aucun appel.
    const cached = await layouts.getLayoutsWithZones();
    assert.deepEqual(cached, SAMPLE, 'le cache évite bien la requête à chaque focus');
    assert.equal(backend.layoutsListCalls, 1);

    // Après la fenêtre de fraîcheur, le lot est rechargé et voit la création.
    Date.now = () => realNow() + 5 * 60 * 1000;
    const fresh = await layouts.getLayoutsWithZones();
    assert.equal(backend.layoutsListCalls, 2, 'le cache doit expirer');
    assert.ok(fresh.some((l) => l.layout_id === created.layout_id),
      'le modèle créé doit apparaître au rechargement');
  } finally {
    Date.now = realNow;
    restore();
  }
});

test('le détail unitaire reste disponible pour l\'éditeur de modèle', async () => {
  const { layouts } = await loadLayoutsService();
  const backend = authenticatedBackend();
  const restore = backend.install();

  try {
    const res = await layouts.getLayout(315);
    assert.ok(res.ok);
    assert.equal(backend.layoutDetailCalls, 1,
      'LayoutEditor a toujours besoin du détail unitaire');
  } finally {
    restore();
  }
});
