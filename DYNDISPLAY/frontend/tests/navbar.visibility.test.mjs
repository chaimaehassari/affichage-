/**
 * Partie 2 — visibilité des entrées de la navbar.
 *
 * Vérifie la règle « Admin client = tout son périmètre, jamais la plateforme » :
 *  - l'entrée plateforme /admins est invisible pour un Admin client ;
 *  - elle reste visible pour un Super Admin ;
 *  - les autres entrées dépendent de la permission réelle (jamais du seul nom
 *    du profil) ;
 *  - tant que le profil n'est pas chargé, aucun item n'est affiché (NavBar rend
 *    alors un squelette stable) — et surtout pas un item plateforme.
 *
 * Exécution : node --import ./tests/helpers/extensionLoader.mjs --test tests/
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { isNavItemVisible, PLATFORM_NAV_ITEMS } from '../src/utils/navbarItems.js';

const grantAll = () => true;
const denyAll = () => false;

test('un Admin client ne voit jamais l\'entrée plateforme /admins', () => {
  const ctx = { isSuperAdmin: false, hasPermission: grantAll };
  for (const item of PLATFORM_NAV_ITEMS) {
    assert.equal(isNavItemVisible(item, ctx), false, `${item.id} ne doit pas être visible`);
  }
});

test('un Super Admin voit l\'entrée plateforme /admins', () => {
  const ctx = { isSuperAdmin: true, hasPermission: denyAll };
  const admins = PLATFORM_NAV_ITEMS.find((i) => i.id === 'admins');
  assert.ok(admins, 'entrée /admins absente de la navbar');
  assert.equal(admins.route, '/admins');
  assert.equal(isNavItemVisible(admins, ctx), true, 'un Super Admin doit voir /admins');
});

test('un Admin client voit toutes les entrées de son périmètre', () => {
  const ctx = { isSuperAdmin: false, hasPermission: grantAll };
  const items = [
    { id: 'users', permission: 'user_list' },
    { id: 'media', permission: 'menu_media' },
    { id: 'layouts', permission: 'menu_conception' },
    { id: 'config', permission: 'menu_config' },
    { id: 'sync', permission: 'menu_sync' },
  ];
  for (const it of items) {
    assert.equal(isNavItemVisible(it, ctx), true, `entrée ${it.id} masquée à tort`);
  }
});

test('une entrée est masquée quand la permission réelle manque', () => {
  const ctx = { isSuperAdmin: false, hasPermission: (c) => c === 'menu_media' };
  assert.equal(isNavItemVisible({ id: 'media', permission: 'menu_media' }, ctx), true);
  assert.equal(isNavItemVisible({ id: 'layouts', permission: 'menu_conception' }, ctx), false);
});

test('une entrée sans permission est toujours visible', () => {
  assert.equal(
    isNavItemVisible({ id: 'home' }, { isSuperAdmin: false, hasPermission: denyAll }),
    true,
  );
});

test('pendant le chargement du profil, aucun item n\'est affiché (squelette)', () => {
  const loadingCtx = { isSuperAdmin: false, hasPermission: denyAll };
  assert.equal(isNavItemVisible({ id: 'users', permission: 'user_list' }, loadingCtx), false);
  assert.equal(isNavItemVisible(PLATFORM_NAV_ITEMS[0], loadingCtx), false);
});
