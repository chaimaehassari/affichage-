# DYNDISPLAY

Plateforme de gestion de Digital Signage (affichage dynamique) : sites, écrans, médias, layouts, playlists et synchronisation SFTP.

Application **Web** : navigateur (Chrome, Edge, Firefox) → React/Vite → FastAPI → PostgreSQL → SFTP.

C'est une application exclusivement Web : aucun client Desktop n'existe ni n'est requis.

## Architecture

```
Navigateur
   │
   ▼
 React + Vite          (développement : http://localhost:5173)
   │
   ▼
 FastAPI (uvicorn)     (développement : http://localhost:8000)
   │
   ├──▶ PostgreSQL     (port 5433, base DYNDISPLAY)
   └──▶ SFTP / OpenSSH (stockage des médias + synchronisation players)
```

## Stack Technique

| Couche | Technologie |
|--------|-------------|
| Frontend | React 19, Vite 8, Tailwind CSS 4 |
| Backend | Python 3, FastAPI, Uvicorn |
| Base de données | PostgreSQL (psycopg 3 + pool) |
| Stockage fichiers | SFTP (paramiko) — `C:\DYNDISPLAY-SFTP\` |
| Authentification | JWT + Argon2, rôles, permissions, zones d'accès |
| Synchronisation | Jobs SFTP automatiques (scheduler intégré au backend) |

## Structure du projet

```
DYNDISPLAY/
├── backend/
│   ├── app/
│   │   ├── api/routes/     # Routeurs API (auth, users, sites, layouts, sync, supervision, settings, audit)
│   │   ├── core/           # Configuration, sécurité, fuseau horaire
│   │   ├── db/             # Connexion PostgreSQL (psycopg pool)
│   │   ├── schemas/        # Schémas Pydantic
│   │   ├── services/       # Logique métier (auth, users, sites, sync, supervision, mail…)
│   │   ├── sftp/           # Client SFTP
│   │   └── main.py         # Entrée FastAPI (sert l'API + le frontend compilé)
│   ├── migrations/         # Migrations SQL
│   ├── tests/              # Tests pytest
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/                # React (pages, composants, services, routes, contextes)
│   ├── package.json
│   ├── vite.config.js      # Proxy dev /api et /media → :8000
│   └── .env.example        # VITE_API_BASE_URL
├── package.json            # Scripts racine (dev, build, start)
├── .gitignore
└── README.md
```

## Prérequis

- Node.js >= 18
- Python 3.x (environnement virtuel recommandé : `backend/.venv`)
- PostgreSQL sur `127.0.0.1:5433` (base `DYNDISPLAY`) — **ne pas créer/supprimer la base**
- OpenSSH / SFTP sur le port 22 (racine `C:\DYNDISPLAY-SFTP\` : `images/`, `videos/`, `documents/`, `configs/`)

## Installation

### Backend (Python)

```bash
cd backend
python -m venv .venv
# Windows : .venv\Scripts\activate   |   Linux/Mac : source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # puis adapter les credentials (voir variables ci-dessous)
```

### Frontend (React)

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_BASE_URL=http://localhost:8000 en dev
```

## Lancement en mode Web

### Développement

Terminal 1 — backend (API + Swagger sur :8000) :

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 — frontend (sur :5173) :

```bash
cd frontend
npm run dev
```

Ou depuis la racine, tout en un :

```bash
npm install        # à la racine (concurrently)
npm run dev        # lance Vite (:5173) + backend (:8000)
```

Ouvrir **http://localhost:5173** dans le navigateur.

### Production

Le backend FastAPI sert aussi le frontend React compilé (SPA) :

```bash
cd frontend && npm run build     # produit frontend/dist
cd backend
```

Dans `backend/.env`, pointer `UI_DIST_PATH` vers le dossier compilé, par exemple :

```
UI_DIST_PATH=C:/Users/hp/Documents/DYNDISPLAY/frontend/dist
CORS_ORIGINS=https://votre-domaine.example
```

Puis :

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Application : http://serveur:8000
- Swagger : http://serveur:8000/docs

L'application étant servie par le backend lui-même, aucun CORS n'est nécessaire dans ce mode. `CORS_ORIGINS` n'est requis que si le frontend est hébergé sur une autre origine (CDN, etc.).

## Variables d'environnement

### Backend (`backend/.env`)

| Variable | Description | Défaut |
|---|---|---|
| `DATABASE_URL` | URL complète PostgreSQL (sinon construite depuis les variables) | vide |
| `POSTGRES_HOST` | Hôte PostgreSQL | `localhost` |
| `POSTGRES_PORT` | Port PostgreSQL | `5433` |
| `POSTGRES_DB` | Nom de la base | `DYNDISPLAY` |
| `POSTGRES_USER` | Utilisateur | |
| `POSTGRES_PASSWORD` | Mot de passe | |
| `SFTP_HOST` | Hôte SFTP | `localhost` |
| `SFTP_PORT` | Port SFTP | `22` |
| `SFTP_USERNAME` | Utilisateur SFTP | |
| `SFTP_PASSWORD` | Mot de passe SFTP | |
| `SFTP_ROOT_PATH` | Racine distante SFTP | |
| `JWT_SECRET_KEY` | Secret de signature JWT | |
| `JWT_ALGORITHM` | Algorithme JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Expiration token | `30` |
| `CORS_ORIGINS` | Origines autorisées (virgules) | `http://localhost:5173` |
| `UI_DIST_PATH` | Chemin du frontend compilé (SPA servie par FastAPI) | vide |
| `APP_TIMEZONE` | Fuseau horaire applicatif | vide (serveur) |

### Frontend (`frontend/.env`)

| Variable | Description | Défaut |
|---|---|---|
| `VITE_API_BASE_URL` | URL base de l'API backend. Vide = même origine | `http://localhost:8000` |

## API

- Swagger : http://localhost:8000/docs
- ReDoc : http://localhost:8000/redoc
- Health : http://localhost:8000/api/health

Principaux préfixes : `/api/v1/auth`, `/api/v1/users`, `/api/v1/sites`, `/api/v1/layouts`, `/api/v1/media/upload`, `/api/v1/sync`, `/api/v1/supervision`, `/api/v1/settings`, `/api/v1/audit`, `/media/{path}`.

## Sécurité

- Mots de passe hachés **Argon2**
- Authentification **JWT** (Bearer), gestion de sessions, rôles/profils et permissions
- **Filtrage côté serveur** : un utilisateur non administrateur n'a accès qu'aux menus, zones et actions autorisés (le backend refuse les actions interdites, 403)
- Ne jamais committer les `.env`

## Tests

```bash
cd backend
pytest                     # tous les tests (nécessite PostgreSQL + SFTP)
pytest tests/test_v1_auth.py
pytest tests/test_v4_media.py
pytest tests/test_v7_sync.py
```

## Ports

| Service | Port |
|---|---|
| Backend (FastAPI) | 8000 |
| Frontend (Vite dev) | 5173 |
| PostgreSQL | 5433 |
| SFTP | 22 |

## Licence

Proprietary - DYNDISPLAY