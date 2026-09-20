# Rapport de session — Multi-tenant (SUPER ADMIN → ADMIN → CLIENT → UTILISATEURS)

Date : 18 septembre 2026 · Repo : `C:\Users\hp\Desktop\all` · Projet : DynDisplay (affichage dynamique — REDAL / T2F)

---

## 1. Objectif du lot traité

Implémenter la hiérarchie de gestion à 4 niveaux demandée au cahier des charges :

```
SUPER ADMIN  →  ADMIN  →  CLIENT  →  UTILISATEURS
```

avec :
- une entité **Client** dédiée (code, nom, quotas de licences),
- un rattachement Admin ↔ Clients,
- un **quota de licence par client** (remplace le quota global),
- des garde-fous de sécurité pour qu'un Admin ne voie/gère que SES clients.

---

## 2. Ce qui a été fait dans cette session

### 2.1 Base de données (migration 018 — appliquée)
Fichier `backend/migrations/018_add_clients_table.sql` appliqué sur la base DYNDISPLAY (port 5433).

- Création de la table `clients` :
  `id` (PK), `code_client` (UNIQUE), `nom_client`, `admin_id` (FK users, SET NULL), `license_sites`, `license_posts`, `created_at`.
- **Client par défaut** créé depuis `general_settings` :
  - code `3C48DBF1` · licence sites `433` · licence postes `588` · responsable = Super Admin (user 1).
  → vérifié en base : `1 ligne dans clients`, valeurs conformes (433 / 588).
- **`sites.client_id`** (FK NOT NULL) ajouté et backfillé : **420 sites** rattachés au client par défaut.
- **`users.client_id`** (FK nullable) ajouté : renseigné quand `user_code` = un `code_client`.

Vérification SQL après application :
```
id | code_client | nom_client        | license_sites | license_posts
 1 | 3C48DBF1    | Client par défaut|           433 | 588
sites : 420 / 420 affectés à un client
```

### 2.2 Backend — nouveaux endpoints (route `/api/v1`, tag « Admins, Clients »)
- `GET  /clients` — liste (Super Admin : tous ; Admin : uniquement ceux affectés) avec quotas, nb sites, nb utilisateurs.
- `GET  /clients/{code}` — détail : quotas, compteurs (sites, utilisateurs, comptes activés), liste des Admins affectés. **404** si inconnu, **403** hors périmètre Admin.
- `PUT  /clients/{code}/license` — mise à jour quotas **Super Admin uniquement** (403 sinon). Journalisée dans l'audit (`client_license_update`).
- `POST /admins/{id}/clients` — affecte un client à un Admin (**Super Admin uniquement**).
- `DELETE /admins/{id}/clients/{code}` — retire un client d'un Admin (**Super Admin uniquement**).
- Création/édition d'un site (`POST/PUT /sites`) : `client_id` dérivé automatiquement depuis `client_code` (fallback client par défaut).

### 2.3 Backend — quota de licence PAR CLIENT
- `auth_service._get_license_posts(client_code)` / `_count_activated_accounts(client_code)` :
  l'activation d'un compte (`POST /auth/activate-account`) consomme désormais un slot du **client** du compte
  (`clients.license_posts`, nombre de comptes déjà activés avec le même `user_code`),
  au lieu du quota global. Repli sur le quota global si le compte n'est rattaché à aucun client (rétro-compatible).

### 2.4 Backend — corrections induites
- `POST /users` / `PUT /users` : un même `user_code` peut être réutilisé **quand il correspond à un client existant**
  (plusieurs comptes du même client) ; sinon l'unicité reste exigée. `users.client_id` renseigné automatiquement.
- `ServiceUser.list_clients` réécrit sur la table `clients` (avant : agrégat de `users.user_code`).
- `get_client` : comptage des sites par `client_id` (FK), pas par la colonne texte — corrigeait un comptage à 0.

### 2.5 Frontend (React) — `npm run build` ✅
- **Page `/admins`** (`src/pages/Admins.jsx`, route remplaçant l'ancien redirect vers `/users`) :
  liste des Admins, badge « Super Admin », création/édition/suppression (modal `AdminFormModal.jsx`),
  affectation de clients par pastilles + / − (POST/DELETE `/admins/{id}/clients`).
  Réservée au Super Admin (redirect sinon).
- **Section « Clients (multi-tenant) »** dans `Settings.jsx` (sous « Comptes & appareils ») :
  tableau Code client / Nom / Admins / Sites (`site_count`/`license_sites`) / Postes-Comptes (`user_count`/`license_posts`) / Statut ;
  bouton « Appliquer licence » (modal `ClientLicenseModal.jsx`) **Super Admin uniquement**, admins en lecture seule.
- Helpers API ajoutés : `src/services/admins.js`.
- Route `/admins/*` → `/admins` corrigée dans `App.jsx`.

### 2.6 Android
- Le champ « **Code client** » existe déjà dans l'app Licences T2F (`strings.xml` : `hint_code`) → **rien à faire**, vérifié.

### 2.7 Tests de sécurité multi-tenant (nouveau lot v17)
Fichier `tests/test_v17_multitenant_security.py` — **7 passed, base nettoyée** :
1. un Admin ne voit que les clients qui lui sont affectés (liste + détail), 403 sur les autres, 404 sur un client inconnu ;
2. un Admin **ne peut pas modifier les licences** (403) ; le Super Admin oui ;
3. un Admin **ne peut pas gérer les Admins** (GET/POST `/admins`, affecter/retirer un client = 403) ;
4. affectation + retrait par le Super Admin = l'Admin voit/ne voit plus le client ;
5. un Admin ne s'affecte pas lui-même un client (403) ; un profil « Utilisateur » n'accède pas à `/clients` (403) ;
6. **quota par client à l'activation** : 2e compte bloqué (« Quota de postes atteint ») puis débloqué après hausse du quota ;
7. détail d'un client avec sites : le Super Admin et l'Admin affecté voient bien `site_count ≥ 1`.

### 2.8 Blocage historique v12 — RÉSOLU
Le test `test_v12_permissions.py::test_zone_scope_enforced` (échec 403/500 de longue date) a été diagnostiqué :
- avec le scoping multi-tenant, un utilisateur ne peut configurer les zones que sur des postes **de son propre client** ;
- l'ancien test ciblait un poste du client par défaut avec un utilisateur d'un autre client → 403 légitime ;
- le test est désormais corrigé pour créer le poste **dans le client de l'utilisateur** (l'intention « seules les zones autorisées »
  est conservée : zone non autorisée → 403, zone autorisée → 200). **v12 : 8 passed.**

### 2.9 Non-régressions corrigées
- `sites.client_id` NOT NULL cassait les insertions SQL directes des tests v7/v8 → `client_id` ajouté (client par défaut dynamique).
- Vue détail client renvoyait 500 (`KeyError`) → normalisation des clés du dict.

---

## 3. Fichiers touchés

**Backend**
- `backend/migrations/018_add_clients_table.sql` (nouveau)
- `backend/app/schemas/auth.py` (ClientItem étendu, ClientDetailResponse, ClientLicenseUpdateRequest, AdminClientAssignRequest)
- `backend/app/services/user_service.py` (list_clients sur la table clients, get_client, update_client_license,
  assign/remove admin_client, unicité user_code par client, client_id auto)
- `backend/app/services/auth_service.py` (quota de licence par client à l'activation)
- `backend/app/services/site_service.py` (dérivation client_id à la création/édition d'un site)
- `backend/app/api/routes/admins.py` (endpoints clients + licences + affectation admins)

**Frontend**
- `frontend/src/pages/Admins.jsx` (nouveau)
- `frontend/src/components/AdminFormModal.jsx`, `ClientLicenseModal.jsx` (nouveaux)
- `frontend/src/services/admins.js` (nouveau)
- `frontend/src/pages/Settings.jsx` (section Clients multi-tenant)
- `frontend/src/App.jsx` (route `/admins`)

**Tests**
- `tests/test_v17_multitenant_security.py` (nouveau — 7 tests)
- `tests/test_v12_permissions.py` (test_zone_scope_enforced corrigé)
- `tests/test_v7_sync.py`, `tests/test_v8_supervision_settings.py` (inserts SQL sites avec client_id)

**Documentation**
- `RAPPORT_GLOBAL.md` (§3.14 hiérarchie multi-tenant, §3.15 vérifications sécurité, §4 suite de tests complète)

---

## 4. Décisions de conception (résumé)

| Question | Décision |
|---|---|
| Table Client | `clients` avec PK `id` + `code_client` UNIQUE (le code reste l'identifiant métier) + quotas |
| Scoping opérationnel | Colonne `client_code` conservée (rétro-compatibilité) + **`sites.client_id`** FK NOT NULL comme lien fiable |
| Users ↔ Client | `users.client_id` nullable ; plusieurs comptes admis sous un même `code_client` (quota par client) |
| Admin ↔ Clients | N-N conservée (`admin_clients`) ; gestion par le Super Admin uniquement |
| Quotas licence | **Par client** à l'activation ; modification réservée au Super Admin |
| Rôle Admin | Modèle existant conservé (`is_superadmin`), pas de nouvelle table roles |

---

## 5. Vérifications

- **Frontend** : `npm run build` → succès (1859 modules, aucun message d'erreur).
- **Tests backend — suite complète au vert** :

| Série | Thème | Résultat |
|---|---|---|
| v1 | Auth | 18 passed |
| v2 | Users | 12 passed |
| v3 | Sites/Posts | 12 passed |
| v4 | Media | passed |
| v5 | Layouts | passed |
| v6 | Configuration | 9 passed |
| v7 | Synchronisation | passed (1 skip pré-existant) |
| v8 | Supervision & settings | passed |
| v9 | Zones multi-média | passed |
| v10 | Groupes | passed |
| v11 | Email | passed |
| v12 | Permissions / scoping zones | **8 passed** (blocage levé) |
| v13 | Activation client | passed |
| v14 | Scoping client sites/posts | 10 passed |
| v15 | Scoping média | 12 passed |
| v16 | Activation compte/appareil | 8 passed |
| v17 | **Sécurité multi-tenant** | **7 passed** |
| e2e / license_utils | Parcours complet | 3 passed / passed |

→ **Toute la suite est verte.**

---

## 6. Points de vigilance restants

- **Pas d'écran de création de nouveau Client** (la table existe et le client par défaut est en place) :
  la création d'un client passe actuellement en base ; un futur écran dédié pourra l'exposer.
- Le **secret `SUPREME_ADMIN_SECRET` (X7K9)** reste uniquement dans le `.env` du serveur — ne pas le committer.
- `test_v7` comporte 1 skip pré-existant (dépend d'un serveur SFTP réel sur le port 22).
- Les tests reposent sur un serveur live `127.0.0.1:8000` (uvicorn --reload) + base DYNDISPLAY (5433) démarrés.