# DynDisplay (GestoDynDisplay) — Rapport global

Application de gestion d'**affichage dynamique** (Digital Signage) pour **REDAL / T2F Manufacturing**.

Ce document fait le point sur l'architecture de l'application, ses fonctionnalités, et les problèmes
résolus au fil des itérations (bugs + écarts par rapport au cahier des charges).

---

## 1. Architecture

Monorepo `C:\Users\hp\Documents\DYNDISPLAY` :

| Dossier    | Techno                                                        | Rôle                              |
|------------|---------------------------------------------------------------|-----------------------------------|
| `backend/` | FastAPI + PostgreSQL (port 5433) + psychopg + SFTP (paramiko) | API REST + synchronisation        |
| `frontend/`| React 19 + Vite 8 + Tailwind 4 + React Router                 | Interface utilisateur (Single Page)|

- Backend démarré sur `127.0.0.1:8000` (auto-reload actif).
- Frontend : `localhost:5173` avec proxy Vite `/api` et `/media` → `8000`.
- Base de données : `postgresql://postgres:chaimae@127.0.0.1:5433/DYNDISPLAY`.
- Compte admin de référence : `admin` / `admin123`.

### Modèle de données (principales tables)
`sites`, `posts` (écrans), `media`, `zone_media`, `layouts` + `layout_zones`,
`post_configurations`, `schedules`, `screen_groups`, `users`, `profiles` (+ droits par menu),
`user_zone_access`, `ftp_profiles`, `general_settings`, `audit_logs`,
`password_reset_tokens`, `sync_jobs`, `sync_items`.

---

## 2. Fonctionnalités principales

### Authentification & sécurité
- Connexion par **nom d'utilisateur** + **mot de passe** (formulaire classique).
- Rôles/profils : **Administrateur**, **Supervisor**, **User** — le rôle est retourné par le
  backend après authentification (`profile_name`) et affiché dans l'en-tête (`user.login - user.profile_name`).
- **Expiration du mot de passe** : forçage du changement après **90 jours**.
- **Suspension de compte** : après **2 mois (60 jours)** d'inactivité, le compte est suspendu.
- **Verrouillage de session** : déconnexion automatique après une durée d'inactivité paramétrable
  (`session_timeout_minutes`).
- **Réinitialisation du mot de passe par e-mail** (lien valable 30 min + auto-login).
- **Traçabilité** : journal d'audit (`GET /api/v1/audit`, admin) + écran « Traçabilité ».

### Gestion des sites / écrans / groupes
- CRUD sites, postes (écrans), groupes d'écrans.
- Gestion des configurations d'affichage (modèle de layout, boucle, planning).
- Assignation de média par **zone** (1 à 8 zones par layout).

### Médiathèque
- Upload de médias (images / vidéos).
- **Deux colonnes** : « Images » (bleu) et « Vidéos » (orange).
- Affectation rapide (QuickAssign) ou par lot (BatchAssign) d'un média aux écrans.

### FTP / Synchronisation
- Profils FTP avec options : **accès anonyme**, **ignorer les erreurs de certificat**.
- Synchronisation SFTP vers les lecteurs, avec progression temps réel.
- Message de fin **exact : « Synchronisation terminée »**.
- **Report des gros médias en période d'affluence (08h–17h)** : les fichiers > 20 Mo sont
  marqués `DEFERRED` et non transférés pendant les heures de pointe.

### Paramètres & supervision
- Paramètres généraux, SMTP, verrouillage de session, licences, FTP.
- Supervision des écrans (en ligne / hors ligne).

---

## 3. Problèmes résolus (bugs & écarts vs cahier des charges)

### 3.1 Bug React : « Objects are not valid as a React child »
**Symptôme** (console) :
```
Uncaught Error: Objects are not valid as a React child
(found: object with keys {type, loc, msg, input, ctx})
```
**Cause** : en cas d'erreur 422 de validation Pydantic, le backend retourne
`{"detail": [ {type, loc, msg, input, ctx}, ... ]}`. `AuthContext.login` faisait
`setError(result.data?.detail)`, stockant **un tableau d'objets**, puis la page de login
rendait `{error}` → React ne sait pas afficher un objet comme enfant.

**Résolution** :
- Ajout d'un normalisateur `getErrorMessage(data)` dans `AuthContext.jsx` qui transforme
  `detail` (string, tableau d'erreurs ou objet) en chaîne lisible.
- `setError(...)` ne stocke plus que des chaînes.

### 3.2 Page de connexion : suppression du dropdown « Sélectionner un utilisateur »
**Demande** : formulaire de connexion classique (two fields) au lieu d'une liste d'utilisateurs.
**Résolution** (`frontend/src/pages/Login.jsx`) :
- Suppression du champ `<select>` et de l'appel `getLogins`.
- Remplacement par un champ texte **« Nom d'utilisateur »** (saisie libre).
- Conservation du champ mot de passe avec l'icône afficher/masquer (Eye / EyeOff).
- Design conservé (dark mode, jaune DynDisplay, boutons Annuler/Valider, dimensions/centrage).
- La valeur saisie est envoyée telle quelle au backend (logique d'authentification inchangée).

### 3.3 Médiathèque : deux colonnes images / vidéos
`MediaLibrary.jsx` : layout `grid md:grid-cols-2` avec logiciel `renderMediaSection`
pour les sections **Images** (bleu) et **Vidéos** (orange).

### 3.4 FTP : connexion anonyme + ignorer les erreurs de certificat
- `FtpProfileModal.jsx` : cases à cocher « anonyme » / « ignorer erreurs certificat », champ
  utilisateur désactivé en mode anonyme.
- Backend (`settings_service`, `schemas/settings`) : champs `is_anonymous` et
  `ignore_certificate_errors` pris en charge à l'insertion et au test de connexion.

### 3.5 Message de synchronisation exact
`SyncProgressModal.jsx` : statut COMPLETED affiché **« Synchronisation terminée »**.

### 3.6 Expiration du mot de passe (3 mois)
`auth_service.py` : si `last_password_change_at` est `NULL` → backfill à `now`
(le compte admin n'est pas bloqué inutilement) ; si > 90 jours → `must_change_password=True`.
Constantes : `MAX_ACTIVITY_IDLE_DAYS=60`, `PASSWORD_MAX_AGE_DAYS=90`.

### 3.7 Suspension du compte (2 mois d'inactivité)
`auth_service.py` : si `last_login_at OR created_at` a plus de 60 jours → `suspended_at=now`
et refus de connexion.

### 3.8 Réinitialisation du mot de passe par e-mail
`mail_service.py` (SMTP) + endpoints `forgot`/`reset` (`auth.py`) : token valable 30 min,
auto-login après reset, 400 sur jeton invalide/expiré. Frontend : `ResetPassword.jsx`,
lien « Mot de passe oublié ? » sur la page de connexion.

### 3.9 Verrouillage de session (paramétrable)
- Backend : setting `session_timeout_minutes` (ajouté aux schémas et à la récupération/mise à jour).
- Frontend : `Settings.jsx` (section SMTP + verrouillage), composant `SessionLock.jsx`
  monté dans `ProtectedRoute.jsx` (écoute des événements, déconnexion après `timeoutMinutes`).

### 3.10 Traçabilité (journal d'audit)
`GET /api/v1/audit` (admin only, filtres `entity_type`/`limit`/`offset`) + page `AuditLogs.jsx`
et entrée de menu « Traçabilité » pour les administrateurs.

### 3.11 Enforcement des zones autorisées à l'affectation de médias
Helper partagé `backend/app/services/zone_access.py` (`assert_zone_allowed`) appliqué :
- à l'affectation par lot (`batch_assign_media`, route → 403 si non autorisé),
- à l'affectation par zone de configuration (`update_configuration` / `update_zones`).
Un utilisateur non administrateur ne peut affecter un média que sur une zone qui lui est
autorisée (`user_zone_access` avec `is_allowed = TRUE`).

### 3.12 Report des gros médias en période d'affluence
`sync_service.run_sync` : pendant la plage d'affluence (par défaut **08h–17h**), les médias
**> seuil** (par défaut **20 Mo**) sont insérés dans `sync_items` avec le statut **`DEFERRED`**
au lieu d'être transférés ; seuls la config et les petits médias sont envoyés. Hors affluence,
comportement inchangé. **Heures et seuil désormais paramétrables** depuis l'écran
« Paramètres généraux » (section « Report des gros médias ») et stockés dans `general_settings`
(`affluence_start_hour`, `affluence_end_hour`, `affluence_media_threshold_mb`).

### 3.13 Module « Paramétrage » — mot de passe dédié, licences & affluence
Conformément au cahier des charges du module Paramétrage :
- **Mot de passe d'accès dédié** à l'écran Paramètres, distinct du mot de passe de connexion,
  **stocké haché** (`general_settings.settings_access_hash`). À la première utilisation (aucun
  mot de passe configuré) l'accès est ouvert ; l'Administrateur peut ensuite le définir.
  Endpoints : `POST /settings/verify-access` (401 si incorrect), `POST /settings/change-access-password`
  (**403 si non Administrateur**). Frontend : `SettingsAccessModal.jsx` remplace l'ancienne porte
  CODE78, et une section « Mot de passe d'accès » (Admin only) permet de le modifier.
- **Blocage de la réduction des licences** : `update_licenses` refuse de descendre sous le nombre
  réel de sites/postes actifs (message explicite, HTTP 400).
- **Affluence paramétrable** : voir 3.12.
- **Traçabilité** : les changements sensibles (mot de passe d'accès, licences) sont journalisés
  en arrière-plan via `log_action` (qui/quoi/quand).

---

## 4. Vérifications

- **Build frontend** : `npm run build` ✅ (Vite) après chaque lot.
- **Tests backend** (serveur live, SFTP non requis) :
  - v1 (auth) : 11 passed
  - v2 (users) : 12 passed
  - v3 (sites/posts — affectation par lot + zones) : 12 passed
  - v6 (configuration — zones) : 9 passed
  - v8 (supervision & settings) : 20 passed
  → **59 tests au total** ✅
- **Tests v7 (synchronisation)** : non exécutables sans un **serveur SFTP réel** sur le port 22
  (contrainte d'infrastructure, pas de code).

---

## 5. Points de vigilance / à faire

- Redémarrer le **serveur Vite** pour activer le proxy `/media` (le backend auto-reload est actif).
- L'heure d'affluence est l'heure locale du serveur ; le seuil « gros média » est de 20 Mo par défaut.
- Le champ SMTP `smtp_password` n'est jamais renvoyé par l'API (sécurité) : l'interface le gère
  en état local séparé.
- Compte admin : `last_password_change_at = NULL` + `must_change_password = False` → non forcé à
  changer (backfill fait automatiquement à `now`).
