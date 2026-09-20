# DYNDISPLAY - Guide Complet (Web)

## Architecture

```
DYNDISPLAY/
├── backend/               # Python FastAPI (source)
├── frontend/              # React + Vite (source)
├── package.json           # Racine : scripts dev/build/start (concurrently)
└── node_modules/          # Dépendances racine (concurrently)
```

L'application s'ouvre dans un navigateur via une URL — aucun client Desktop requis.

**Stack :**
| Couche | Technologie |
|--------|------------|
| Frontend | React 19 + Vite 8 + Tailwind CSS 4 |
| Backend | Python 3 + FastAPI + Uvicorn |
| Base | PostgreSQL (port 5433, base `DYNDISPLAY`) |
| Stockage media | SFTP/SSH (`C:\DYNDISPLAY-SFTP\`) |
| Auth | JWT + Argon2 (rôles, permissions, zones d'accès) |
| Sync | Jobs SFTP automatiques (scheduler intégré au backend) |

## Prérequis

- **Node.js** >= 18
- **Python** 3.x avec `.venv` dans `backend/.venv`
- **PostgreSQL** sur `127.0.0.1:5433` (base `DYNDISPLAY`)
- **OpenSSH** (SFTP sur port 22)

---

## Installation

### 1. Backend (Python)

```bash
cd backend

# Virtualenv
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# Dépendances
pip install -r requirements.txt

# Config
cp .env.example .env          # puis éditer les credentials
```

**Fichier `backend/.env`** (référence) :

```
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_DB=DYNDISPLAY
POSTGRES_USER=postgres
POSTGRES_PASSWORD=changeme   <-- remplacer par votre vrai mot de passe (.env jamais committé)

SFTP_HOST=127.0.0.1
SFTP_PORT=22
SFTP_USERNAME=changeme
SFTP_PASSWORD=changeme
SFTP_ROOT_PATH=/C:/DYNDISPLAY-SFTP

JWT_SECRET_KEY=<openssl rand -hex 32>   <-- obligatoire pour démarrer, ne jamais committer
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
CORS_ORIGINS=http://localhost:5173
MEDIA_ROOT=./media_storage
APP_TIMEZONE=Atlantic/Casablanca
UI_DIST_PATH=
```

### 2. Frontend (React / Vite)

```bash
cd frontend

# Install
npm install

# Fichier frontend/.env
# VITE_API_BASE_URL=http://localhost:8000  (dev)
# Vide = même origine (le backend sert l'API et le frontend compilé)
```

---

## Lancement en développement

### Backend seul

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API : http://localhost:8000
- Swagger : http://localhost:8000/docs
- Health : http://localhost:8000/api/health

### Frontend seul (navigateur)

```bash
cd frontend
npm run dev
```

- App : http://localhost:5173
- Vite proxye `/api` et `/media` vers `http://localhost:8000`

### Frontend + Backend ensemble (dev, depuis la racine)

```bash
npm install          # installe concurrently (racine)
npm run dev          # lance Vite (:5173) + backend (:8000)
```

Ouvrir **http://localhost:5173** dans Chrome/Edge/Firefox.

---

## Lancement en production

FastAPI sert l'API **et** le frontend React compilé (SPA).

### 1. Builder le frontend

```bash
cd frontend
npm run build                 # produit frontend/dist
```

### 2. Configurer le backend

Dans `backend/.env` :

```
UI_DIST_PATH=C:/chemin/absolu/vers/frontend/dist
CORS_ORIGINS=https://votre-domaine.example   # facultatif si même origine
```

### 3. Démarrer

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Application : http://serveur:8000
- Docs API : http://serveur:8000/docs

Le catch-all SPA de FastAPI (`main.py`) sert les assets du frontend compilé et retombe
sur `index.html` pour les routes React.

---

## Tests Backend

```bash
cd backend
.venv\Scripts\activate
pytest                           # tous les tests
pytest tests/test_v1_auth.py     # authentification
pytest tests/test_v4_media.py    # médiathèque / upload
pytest tests/test_v7_sync.py     # synchronisation
pytest tests/test_v8_supervision_settings.py  # supervision + paramètres
```

**Comptes de test :**
| Login | Mot de passe | Profil |
|-------|-------------|--------|
| admin | généré par `seed_admin.py` (affiché une seule fois ; `SEED_ADMIN_PASSWORD` pour le dev/tests) | Administrateur |
| supervisor1, operator1, operator2, viewer1 | générés par `seed_data.py` (aléatoires, affichés une seule fois) | voir seed_data.py |

**Ports :**
| Service | Port |
|---------|------|
| Backend (FastAPI) | 8000 |
| Frontend (Vite dev) | 5173 |
| PostgreSQL | 5433 |
| SFTP | 22 |

---

## Variables d'environnement

### Backend (`backend/.env`)

| Variable | Description | Défaut |
|----------|------------|--------|
| `DATABASE_URL` | URL PostgreSQL complète (sinon construite) | vide |
| `POSTGRES_HOST` | Hôte PostgreSQL | `localhost` |
| `POSTGRES_PORT` | Port PostgreSQL | `5433` |
| `POSTGRES_DB` | Nom base | `DYNDISPLAY` |
| `POSTGRES_USER` | Utilisateur | — |
| `POSTGRES_PASSWORD` | Mot de passe | — |
| `SFTP_HOST` | Hôte SFTP | `localhost` |
| `SFTP_PORT` | Port SFTP | `22` |
| `SFTP_ROOT_PATH` | Racine SFTP | — |
| `JWT_SECRET_KEY` | Secret JWT | — |
| `JWT_ALGORITHM` | Algorithme JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Expiration token | `30` |
| `CORS_ORIGINS` | Origines CORS (virgules) | `http://localhost:5173` |
| `MEDIA_ROOT` | Racine locale (réserve) | `./media_storage` |
| `APP_TIMEZONE` | Fuseau horaire app | `Atlantic/Casablanca` |
| `UI_DIST_PATH` | Frontend compilé servi par FastAPI | `""` (vide) |

### Frontend (`frontend/.env`)

| Variable | Description | Défaut |
|----------|------------|--------|
| `VITE_API_BASE_URL` | URL base de l'API backend | `http://localhost:8000` |

---

## Résolution de problèmes

### Port 8000 déjà utilisé

```bash
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select OwningProcess
Stop-Process -Id <PID> -Force
```

### Le navigateur n'arrive pas à joindre l'API

- Vérifier le backend : http://127.0.0.1:8000/api/health
- En dev, le frontend doit tourner sur http://localhost:5173 et le `CORS_ORIGINS`
  du backend doit contenir cette origine.
- Si `VITE_API_BASE_URL` est laissé vide, s'assurer que le proxy Vite (`/api`, `/media`)
  ou le servi par FastAPI est bien en place.

### Base CORS en production

- Frontend et backend sur la même origine → aucun réglage CORS nécessaire.
- Frontend sur une autre origine → ajouter l'origine dans `CORS_ORIGINS` (séparée par des virgules).