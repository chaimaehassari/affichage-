# DYNDISPLAY - Etat du Projet

## Date : 25 Août 2026

---

## 1. Description

**DYNDISPLAY** est une plateforme de gestion de **Digital Signage** (affichage dynamique). Elle permet de gerer des sites, ecrans, contenus media, synchronisation SFTP et planning d'affichage.

---

## 2. Stack Technique

### Backend
| Technologie | Version |
|---|---|
| Python | 3.x |
| FastAPI | >= 0.115.0 |
| Uvicorn | >= 0.34.0 |
| SQLAlchemy | >= 2.0.36 |
| PostgreSQL (psycopg) | >= 3.2.3 |
| Alembic | >= 1.14.0 |
| Pydantic | >= 2.10.3 |
| Paramiko (SFTP) | >= 3.5.0 |
| PyJWT | >= 2.10.1 |
| Argon2 (passwords) | >= 23.1.0 |

### Frontend
| Technologie | Version |
|---|---|
| React | 19.2.8 |
| React Router DOM | 7.18.2 |
| Tailwind CSS | 4.3.3 |
| Vite | 8.2.2 |
| Lucide React | 1.34.0 |

### Infra
| Technologie | Description |
|---|---|
| Docker Compose | Orchestration backend + frontend |
| PostgreSQL | Base de donnees (port 5433) |
| SFTP | Transfert de media vers les players |

---

## 3. Structure du Projet

```
DYNDISPLAY/
├── backend/
│   ├── app/
│   │   ├── api/routes/       (auth.py, users.py)
│   │   ├── core/             (config.py, security.py)
│   │   ├── db/               (database.py)
│   │   ├── dependencies/     (auth.py)
│   │   ├── models/           (auth.py)
│   │   ├── schemas/          (auth.py)
│   │   ├── services/         (auth_service.py, user_service.py, audit_service.py)
│   │   ├── sftp/             (client.py)
│   │   └── main.py
│   ├── alembic/
│   ├── seed_admin.py
│   ├── seed_data.py
│   ├── seed_v2.py
│   ├── migrate_permissions.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       (Header.jsx, Sidebar.jsx, common/)
│   │   ├── contexts/         (AuthContext.jsx)
│   │   ├── hooks/
│   │   ├── layouts/
│   │   ├── pages/            (Login.jsx, Dashboard.jsx, UserList.jsx, UserForm.jsx)
│   │   ├── routes/           (ProtectedRoute.jsx)
│   │   ├── services/         (api.js, auth.js)
│   │   ├── types/
│   │   └── utils/
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml
└── docs/
```

---

## 4. Base de Donnees - Tables

| Table | Colonnes | Description |
|---|---|---|
| `profiles` | 4 | Profils utilisateurs (Administrateur, Utilisateur, Superieur) |
| `users` | 14 | Comptes utilisateurs |
| `password_history` | 4 | Historique mots de passe |
| `password_reset_tokens` | 6 | Tokens de reinitialisation |
| `permissions` | 5 | Permissions systeme |
| `user_permissions` | 7 | Permissions par utilisateur (CRUD) |
| `user_zone_access` | 4 | Acces aux zones par utilisateur |
| `sites` | 8 | Sites/geolocalisation |
| `screen_groups` | 6 | Groupes d'ecrans |
| `posts` | 13 | Players/ecrans connectes |
| `screen_group_posts` | 3 | Association groupes-ecrans |
| `layouts` | 6 | Dispositions d'affichage |
| `layout_zones` | 8 | Zones dans un layout |
| `post_configurations` | 8 | Configurations par player |
| `zone_media` | 8 | Media par zone |
| `media` | 12 | Fichiers media |
| `schedules` | 11 | Plannings d'affichage |
| `sync_jobs` | 10 | Taches de synchronisation SFTP |
| `sync_items` | 7 | Elements d'une sync |
| `audit_logs` | 8 | Journal d'audit |
| `ftp_profiles` | 16 | Profils de connexion FTP/SFTP |
| `general_settings` | 5 | Parametres generaux |

---

## 5. API Endpoints (Routes)

| Methode | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/login` | Connexion |
| GET | `/api/v1/auth/me` | Profil utilisateur courant |
| POST | `/api/v1/auth/logout` | Deconnexion |
| GET | `/` | Health check API |
| GET | `/api/health` | Status API |

---

## 6. Utilisateurs en Base

### Profils

| Profil | Description | Utilisateurs |
|---|---|---|
| Administrateur | Tous les droits | 2 |
| Superieur | Supervision | 2 |
| Utilisateur | Standard | 3 |

### Comptes

| Login | Profil | Actif | Derniere Connexion |
|---|---|---|---|
| chaimae | Administrateur | Oui | 25/08/2026 |
| admin | Administrateur | Oui | 25/08/2026 |
| supervisor1 | Superieur | Oui | - |
| operator1 | Utilisateur | Oui | - |
| operator2 | Utilisateur | Oui | - |
| viewer1 | Superieur | Oui | - |
| inactive1 | Utilisateur | Oui | - |

---

## 7. Etat d'Avancement

### Fonctionnalites Implementees
- [x] Authentification (login/logout) avec JWT
- [x] Gestion des utilisateurs (CRUD)
- [x] Systeme de profils et permissions
- [x] Verrouillage apres tentatives echouees
- [x] Pages : Login, Dashboard, UserList, UserForm
- [x] Route protegee (ProtectedRoute)
- [x] AuthContext (React)
- [x] Sidebar + Header
- [x] Configuration SFTP
- [x] Modele de donnees complet (21 tables)

### En Cours / A Venir
- [ ] Routes API : Sites, Posts, Layouts, Media, Schedules
- [ ] Pages Frontend : Sites, Ecrans, Layouts, Media, Synchronisation
- [ ] Gestion SFTP (transfert media vers players)
- [ ] Plannings d'affichage
- [ ] Dashboard avec statistiques
- [ ] Alembic migrations (aucune version pour l'instant)
- [ ] Tests unitaires
- [ ] Audit logging complet
- [ ] Dockerisation fonctionnelle

---

## 8. Services

### Backend
| Service | Fichier | Role |
|---|---|---|
| AuthService | `services/auth_service.py` | Authentification, verification mots de passe |
| UserService | `services/user_service.py` | Gestion CRUD utilisateurs |
| AuditService | `services/audit_service.py` | Journalisation des actions |
| SFTPClient | `sftp/client.py` | Transfert fichiers via SFTP |

### Frontend
| Service | Fichier | Role |
|---|---|---|
| api.js | `services/api.js` | Client HTTP (axios/fetch) |
| auth.js | `services/auth.js` | Appels API authentification |

---

## 9. Notes Techniques

- Mots de passe hashes avec **Argon2**
- Tokens JWT avec **PyJWT** (expire 60 min)
- SFTP via **Paramiko**
- Backend sur **port 8000**, Frontend sur **port 5173**
- Proxy Vite redirige `/api` vers `localhost:8000`
- CORS active pour `http://localhost:5173`
