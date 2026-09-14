# Licence T2F — Guide : run & test via l'interface

Application Android interne (Kotlin) qui **génère et vérifie** les codes de
licence T2F à partir de **Code client / Nombre de sites / Nombre de postes**.

> ⚠️ **Sécurité** : outil interne, **hors ligne**, **jamais sur le Play Store**.
> Installation par **sideload** uniquement sur les téléphones T2F.

---

## 1. Prérequis

| Besoin | Détail |
|---|---|
| JDK 17 | Temurin 17 déjà installé : `C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot` |
| Android SDK | `compileSdk 34`. Installé ici : `C:\Users\hp\AppData\Local\Android\Sdk` (ajouter à `local.properties` → `sdk.dir`) |
| Android Studio | Optionnel (interface graphique), sinon ligne de commande |
| Secret de licence | à mettre dans `local.properties` (voir §2) |

---

## 2. Configurer le secret de licence (avant tout build)

Le secret ne doit **jamais** être dans le code source.

```bash
# 1. Copier le gabarit (une seule fois)
copy local.properties.example local.properties
```

Puis éditer `local.properties` :

```properties
sdk.dir=C:\\Users\\hp\\AppData\\Local\\Android\\Sdk
license.secret=METTRE-ICI-LE-VRAI-SECRET
```

> Le secret doit être **identique** à `LICENSE_SECRET` du fichier
> `DYNDISPLAY\backend\.env` et à l'outil Python de référence.
> Si absent/placeholder, le build **échoue volontairement**.
> `local.properties` est exclu par `.gitignore` — ne jamais le committer.

---

## 3. Build de l'application

### 3.1 Avec Android Studio (recommandé)

1. Ouvrir Android Studio → **Open** → sélectionner le dossier `serialisation`.
2. Attendre la synchronisation Gradle.
3. **Run ▶** (`Shift+F10`) avec un téléphone connecté (USB + mode développeur) ou un émulateur.

### 3.2 En ligne de commande

```powershell
# PowerShell (depuis C:\Users\hp\Desktop\all\serialisation)
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"
$env:ANDROID_HOME = "C:\Users\hp\AppData\Local\Android\Sdk"

# Build de l'APK de debug
.\gradlew.bat :app:assembleDebug

# → APK produit : app\build\outputs\apk\debug\app-debug.apk
```

---

## 4. Installer sur un téléphone (sideload)

1. Copier `app-debug.apk` sur le téléphone (USB, Drive, WhatsApp…).
2. Sur le téléphone : ouvrir le fichier APK.
3. Autoriser l'installation « **Sources inconnues** » si demandée.
4. Ouvrir l'application **« Licence T2F »**.

> L'app n'a **aucun accès réseau** — tout se passe en local sur le téléphone.

---

## 5. Tester via l'interface de l'app

Écran unique, composé de deux zones :

```
Licence T2F
Générateur interne de codes de licence (confidentiel T2F)

[ Code client         ]      <- chiffres uniquement, 8 max
[ Nombre de sites     ]
[ Nombre de postes    ]

[ Générer ]
┌─────────────────────────────┐
│  ABCDE-FGHIJ-KLMNO-...      │   ← code généré
└─────────────────────────────┘
[ Copier le code ]

──────────  Vérifier / décoder une licence  ──────────

[ Code de licence à vérifier   ]

[ Vérifier ]
```

### 5.1 Générer un code (cas nominal)

| Étape | Action | Résultat attendu |
|---|---|---|
| 1 | Code client = `12345678` | chiffres uniquement (8 max) |
| 2 | Nombre de sites = `12` | entier ≥ 0 |
| 3 | Nombre de postes = `34` | entier ≥ 0 |
| 4 | Toucher **Générer** | un code apparaît, ex. `XXXXX-XXXXX-XXXXX-XXX` |
| 5 | Toucher **Copier le code** | toast « Code copié. » ; le code est dans le presse-papiers |

- Mêmes entrées → **toujours le même code** (déterminisme).
- Champs vides ou invalides → message d'erreur rouge sous le champ concerné
  (« Code client requis », « Nombre de sites invalide », …).

### 5.2 Vérifier / décoder

| Cas | Saisie | Résultat attendu |
|---|---|---|
| Code valide | coller un code généré à l'instant | fond **vert** : « Code valide. Client : … Sites : … Postes : … » avec les bonnes valeurs |
| Code altéré | modifier **1 seul caractère** du code valide | fond **rouge** : « Code invalide : la signature ne correspond pas… » |
| Code tronqué | couper la fin du code | fond **rouge** |
| Garbage | `NOT-A-CODE!!`, vide, `A1B2` | fond **rouge** |

> La vérification se fait **sans Appareil ni réseau** : elle recalcule la
> signature HMAC localement et compare en temps constant.

### 5.3 Recette rapide bout-en-bout

1. Saisir `12345678 / 12 / 34` → **Générer** → noter le code.
2. Copier, ré-entrer le même code dans la zone *Vérifier* → **vert**.
3. Changer une lettre → **rouge**. ✅

---

## 6. Test de bout en bout avec l'app web DYNDISPLAY

Objectif : le code généré sur Android doit être **accepté par la plateforme
web** (le même algorithme HMAC, même secret).

### Prérequis

- Backend : `http://localhost:8000` (voir §8 « relancer » ; seul le port doit
  être libre).
- Frontend : `http://localhost:5173` (facultatif, teste par API sinon).
- Compte admin : `admin / admin123`.

### Procédure

1. **Sur le téléphone** : générer un code pour un client existant, e.g.
   `12345678 / 15 / 40` → **Générer** → **Copier**.
2. **Dans le navigateur** : se connecter sur `http://localhost:5173`
   (`admin` / `admin123`).
3. Menu **Paramètres** → bouton **« Changer le nombre de licences »**.
4. Coller le code → cliquer **Valider**.

| Cas | Résultat attendu |
|---|---|
| Code non altéré | Les quotas « Sites » et « Postes » passent à 15 / 40 ✅ |
| Code altéré ou erroné | Refus (HTTP 400) avec message « Code de licence invalide… » |
| Code qui réduirait sous le nombre réel de sites/postes | Refus explicite (blocage métier, même si HMAC valide) |

> Vérification technique équivalente sans téléphone (PowerShell, dossier
> `DYNDISPLAY\backend`) :
> ```powershell
> .venv\Scripts\python.exe -c "from app.core.license_utils import generate_license; print(generate_license('12345678', 15, 40))"
> ```

---

## 7. Tests unitaires (hors interface)

```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"
$env:ANDROID_HOME = "C:\Users\hp\AppData\Local\Android\Sdk"

.\gradlew.bat :app:testDebugUnitTest
```

- **12 tests, 0 échec** attendu.
- Détail des résultats : `app\build\test-results\testDebugUnitTest\*.xml`.
- Le test clé `crossVector_matchesPythonReferenceTool` compare le code généré
  par Kotlin à un **vecteur de référence figé** produit par l'outil Python avec
  le secret réel — il garantit l'interopérabilité Android ↔ Web.

Côté web (même secret) :

```powershell
C:\Users\hp\Desktop\all\DYNDISPLAY\backend\.venv\Scripts\python.exe -m pytest tests/test_license_utils.py
```

---

## 8. Dépannage

| Problème | Cause / Solution |
|---|---|
| Build impossible, « license.secret absent de local.properties » | créer/remplir `local.properties` (voir §2) |
| Build impossible, « encore le placeholder » | remplacer `REMPLACER-PAR-LE-VRAI-SECRET` par la vraie valeur |
| `WinError 10013` sur port 8000 | un serveur occupe déjà :8000. Le tuer puis relancer : `Get-NetTCPConnection -LocalPort 8000 -State Listen` → `taskkill /F /T /PID <PID>` |
| L'app web rejette un code pourtant généré sur Android | secrets différents entre `local.properties` et `DYNDISPLAY\backend\.env` — mettre la même valeur des deux côtés |
| APK introuvable | rebuild : `.\gradlew.bat :app:assembleDebug`, chemin : `app\build\outputs\apk\debug\app-debug.apk` |
| Le Play Store propose l'app | ⛔ Elle ne doit **jamais** y être publiée (décompilation possible du secret) |

---

## Vérification finale rapide

1. `local.properties` contient le vrai secret ✅
2. `.\gradlew.bat :app:assembleDebug` → APK créé ✅
3. App installée sur le téléphone ✅
4. Générer `12345678 / 12 / 34` → valider dans l'app → **vert** ✅
5. Même code collé dans DYNDISPLAY Paramètres → **validé** ✅









Comment lancer ton projet

Il te faut 3 terminaux.

Terminal 1 — Backend

Dans :

C:\Users\hp\Desktop\all\DYNDISPLAY\backend

fais :

.venv\Scripts\activate

puis :

uvicorn app.main:app --reload --port 8000

Tu dois avoir quelque chose comme :

Uvicorn running on http://127.0.0.1:8000
Terminal 2 — Frontend

Dans :

C:\Users\hp\Desktop\all\DYNDISPLAY\frontend

fais :

npm run dev

Puis ouvre l'adresse donnée par Vite, généralement :

http://localhost:5173
Terminal 3 — Android

D'abord démarrer l'émulateur :

C:\Users\hp\AppData\Local\Android\Sdk\emulator\emulator.exe -avd licence_t2f

Ensuite installer l'APK :

C:\Users\hp\AppData\Local\Android\Sdk\platform-tools\adb.exe install -r C:\Users\hp\Desktop\all\serialisation\app\build\outputs\apk\debug\app-debug.apk

Puis ouvrir l'application :

C:\Users\hp\AppData\Local\Android\Sdk\platform-tools\adb.exe shell am start -n com.t2f.licensegen/.MainActivity