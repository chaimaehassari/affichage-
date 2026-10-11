// Règles de visibilité des entrées de la navbar (logique PURE, testable hors
// React). Extraite de NavBar.jsx pour être couverte par les tests Node.
//
// Contrat :
//  - un item `superAdminOnly` n'est visible que pour un Super Admin ;
//  - un item sans permission est toujours visible ;
//  - sinon la permission réelle décide (`hasPermission`), et non le seul nom du
//    profil : un Admin client voit tout son périmètre, jamais les écrans
//    plateforme.
export function isNavItemVisible(item, { isSuperAdmin = false, hasPermission } = {}) {
  if (!item) return false;
  if (item.superAdminOnly) return !!isSuperAdmin;
  if (!item.permission) return true;
  return !!(hasPermission && hasPermission(item.permission));
}

// Entrée plateforme : réservée au Super Admin, jamais visible pour un Admin
// client (masquage de confort — l'API renvoie de toute façon 403).
export const PLATFORM_NAV_ITEMS = [
  { id: 'admins', label: 'Administrateurs', route: '/admins', superAdminOnly: true },
];
