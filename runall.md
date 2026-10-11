# RUNALL — Lancer toutes les apps du repo

Guide de lancement unique pour les 5 projets de `C:\Users\hp\Desktop\all`.
Tout est en **PowerShell**, sauf les `.bat` / `gradlew.bat` (cmd).

| # | App | Dossier | Commande | Port |
|---|-----|---------|----------|------|
| 1 | Backend API (FastAPI) | `DYNDISPLAY\backend` | `python -m uvicorn app.main:app` | 8000 |
| 2 | Frontend Web (Vite) | `DYNDISPLAY\frontend` | `npm run dev` | 5173 |
| 3 | Player Windows (Electron) | `dyndisplay-windows-player` | `npm run dev` | 5174 |
| 4 | Player Android (Kotlin) | `dyndisplay-android-player` | `gradlew.bat :app:installDebug` | émulateur |
| 5 | Générateur de licence (Kotlin) | `serialisation` | `gradlew.bat :app:installDebug` | émulateur |

> Apps 1 + 2 = l'application **Web DynDisplay** (le `npm run dev` racine les lance ensemble).
> Apps 3/4/5 sont **indépendantes** du backend : elles ne se lancent pas "en même temps" par nécessité, mais pour tester la supervision (heartbeat) il faut le backend **allumé**.

---

## 0. Prérequis

- **Node.js ≥ 18** (≥ 20 pour le player Windows) → `node -v`
- **Python 3.14** dans `DYNDISPLAY\backend\.venv` (venv déjà créée) → `.\.venv\Scripts\python.exe --version`
- **PostgreSQL** sur `localhost:5433`, base `DYNDISPLAY` (ne pas la recréer)
- **OpenSSH / SFTP** sur le port 22, racine `C:\DYNDISPLAY-SFTP\`
- **JDK 17** + **Android SDK** (pour apps 4 et 5)

Vérifier que les services infra tournent :

```powershell
Get-NetTCPConnection -State Listen -LocalPort 5433,22 | Select-Object LocalPort,OwningProcess
```

Si PostgreSQL n'est pas démarré → services Windows (`services.msc`) ou
`net start postgresql-x64`. Si SFTI ne répond pas, le service `sshd` doit tourner.

Variables déjà configurées dans `DYNDISPLAY\backend\.env` et `DYNDISPLAY\frontend\.env`
(ne rien modifier pour un run local).

---

## 1. Backend API (FastAPI) — port 8000

Terminal dédié :

```powershell
cd C:\Users\hp\Desktop\all\DYNDISPLAY\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Vérif :

- API / Swagger : http://localhost:8000/docs
- Health : http://localhost:8000/api/health

### Migrations (avant le 1er lancement, ou après ajout d'un `migrations\0NN_*.sql`)

```powershell
cd C:\Users\hp\Desktop\all\DYNDISPLAY\backend
.\.venv\Scripts\python.exe scripts\migrate.py status   # audit
.\.venv\Scripts\python.exe scripts\migrate.py apply    # applique les migrations en attente
```

### Seed / compte admin (une fois, si la base est vide)

```powershell
.\.venv\Scripts\python.exe seed_admin.py
```

### Tests backend

```powershell
cd C:\Users\hp\Desktop\all\DYNDISPLAY\backend
.\.venv\Scripts\python.exe -m pytest              # tout
.\.venv\Scripts\python.exe -m pytest -m v7         # par lot (v1..v28, e2e)
```

> Les tests TAPent un serveur live sur `127.0.0.1:8000` **et** la base 5433 : le
> backend doit tourner pendant `pytest`.

---

## 2. Frontend Web (Vite) — port 5173

Terminal dédié :

```powershell
cd C:\Users\hp\Desktop\all\DYNDISPLAY\frontend
npm install      # une seule fois
npm run dev
```

Ouvrir **http://localhost:5173**.
Vite proxifie `/api` et `/media/` vers `http://localhost:8000` → le backend doit être lancé.

### Les deux d'un coup (racine `DYNDISPLAY`)

```powershell
cd C:\Users\hp\Desktop\all\DYNDISPLAY
npm install      # une seule fois (installe concurrently)
npm run dev      # = Vite :5173 + backend :8000 dans le même terminal
```

> Utilise `python` (venv active) — si le backend ne démarre pas, activer d'abord
> `DYNDISPLAY\backend\.venv\Scripts\Activate.ps1` ou utiliser la commande 1 ci-dessus.

### Build frontend (production)

```powershell
cd C:\Users\hp\Desktop\all\DYNDISPLAY\frontend
npm run build    # produit frontend\dist
```

---

## 3. Player Windows (Electron) — port 5174

Terminal dédié :

```powershell
cd C:\Users\hp\Desktop\all\dyndisplay-windows-player
npm install      # une seule fois
npm run dev
```

`npm run dev` = Vite sur 5174 + Electron en kiosque plein écran (DevTools ouverts).

- URL dev : http://localhost:5174 (ne pas utiliser le navigateur : le pont SFTP
  n'existe que dans Electron)
- 1er lancement → écran « Configuration initiale » : **code site**, **code poste**,
  IP serveur, SFTP user/pass, code client, port API 8000.

Packager :

```powershell
npm run dist      # installeur NSIS + portable dans release\
npm run dist:dir  # dossier non packagé (debug du build)
```

---

## 4. Player Android (Kotlin, API 21+)

### 4.1 Démarrer l'émulateur (1er terminal)

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -avd t2f_test
```

Attendre l'écran d'accueil du launcher (ne pas tenter l'APK avant le boot terminé).

### 4.2 Installer + lancer (2e terminal)

```powershell
cd C:\Users\hp\Desktop\all\dyndisplay-android-player
.\gradlew.bat :app:installDebug
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" shell am start -n com.t2fm.gestodyndisplay/.MainActivity
```

Package : `com.t2fm.gestodyndisplay` — APK : `app\build\outputs\apk\debug\app-debug.apk`.

Journaux : `adb logcat -s GestoDyn`

### 4.3 Tests player sans backend (serveur factice)

Utile pour valider le heartbeat sans allumer FastAPI :

```powershell
cd C:\Users\hp\Desktop\all\dyndisplay-android-player\test-env
.\lancer_fake_api.bat
```

Depuis l'émulateur, le port 8000 de l'hôte = `10.0.2.2:8000`.
Le serveur factice affiche `Heartbeat poste <N> -> 200 OK` toutes les 60 s, et
répond 404 si `post_id=999` (test « poste introuvable »).

---

## 5. Générateur de licence `serialisation` (hors ligne)

```powershell
cd C:\Users\hp\Desktop\all\serialisation
.\gradlew.bat :app:installDebug
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" shell am start -n com.t2f.licensegen/.MainActivity
```

Package : `com.t2f.licensegen`. Build seul : `.\gradlew.bat :app:assembleDebug`.
Tests JUnit : `.\gradlew.bat :app:testDebugUnitTest`.

> Prérequis build : `license.secret` renseigné dans `serialisation\local.properties`,
> **identique** à `LICENSE_SECRET` dans `DYNDISPLAY\backend\.env` (sinon le build échoue
> volontairement). Ne jamais committer ce fichier.

---

## 6. Séquence « tout lancer » (le plus simple)

5 terminaux, dans cet ordre :

```powershell
# T1 — infra déjà démarrée (Postgres 5433 + SFTP 22), sinon services.msc
# T2 — backend
cd C:\Users\hp\Desktop\all\DYNDISPLAY\backend
.\.venv\Scripts\python.exe scripts\migrate.py apply
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# T3 — frontend web
cd C:\Users\hp\Desktop\all\DYNDISPLAY\frontend
npm run dev                      # http://localhost:5173

# T4 — player Windows
cd C:\Users\hp\Desktop\all\dyndisplay-windows-player
npm run dev                      # http://localhost:5174 + Electron

# T5 — player Android
& "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -avd t2f_test
cd C:\Users\hp\Desktop\all\dyndisplay-android-player
.\gradlew.bat :app:installDebug
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" shell am start -n com.t2fm.gestodyndisplay/.MainActivity
```

Puis, dans un 6e terminal si besoin :

```powershell
cd C:\Users\hp\Desktop\all\serialisation
.\gradlew.bat :app:installDebug
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" shell am start -n com.t2f.licensegen/.MainActivity
```

---

## 7. Arrêter tout

- `Ctrl+C` dans chaque terminal (le `--reload` d'uvicorn et `concurrently` se coupent proprement).
- Fermer la fenêtre Electron.
- Émulateur : `adb emu kill`

Vérifier qu'il ne reste aucun process sur les ports :

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000,5173,5174,5433,22
```

Forcer le nettoyage si un port reste occupé :

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000,5173,5174 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

---

## 8. Troubleshooting

| Symptôme | Cause / solution |
|---|---|
| `5173` / `5174` déjà utilisé | autre Vite lancé → `Get-NetTCPConnection -State Listen -LocalPort 5173,5174` puis `Stop-Process` |
| Frontend: pages vides / 404 API | backend pas lancé sur 8000, ou `VITE_API_BASE_URL` vide au lieu de `http://localhost:8000` |
| `Errno connecting to 127.0.0.1:5433` | PostgreSQL arrêté |
| Sync backend échoue | SFTP port 22 arrêté, ou `SFTP_ROOT_PATH` inaccessible |
| `python` non reconnu dans `DYNDISPLAY` | utiliser `.\.venv\Scripts\python.exe` (ou activer le venv) |
| Electron: « Pont Electron non disponible » | ne pas ouvrir 5174 dans un navigateur, passer par `npm run dev` |
| Android: APK ne démarre pas | émulateur pas encore booté, ou `adb install -r` à relancer |
| Android: build échoue sur le secret | `license.secret` manquant dans `serialisation\local.properties` |

---

## 9. Ports (résumé)

| Service | Port |
|---|---|
| Backend FastAPI | 8000 |
| Frontend Vite (web) | 5173 |
| Player Windows (Vite + Electron) | 5174 |
| PostgreSQL | 5433 |
| SFTP / OpenSSH | 22 |
| Android émulateur → hôte | 10.0.2.2:<port hôte> |
