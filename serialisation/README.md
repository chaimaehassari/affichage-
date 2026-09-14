# Licence T2F — Générateur Android

Application Android native (Kotlin), **hors ligne** (aucun appel réseau), usage
interne T2F : génère et vérifie les codes de licence à partir de
**Code client / Nombre de sites / Nombre de postes**.

## ⚠️ Compromis de sécurité (lire avant déploiement)

- **Ne JAMAIS publier cette app sur le Play Store.**
- Installation **uniquement par sideload** sur les téléphones internes T2F,
  sous contrôle.
- Un APK peut être décompilé (`apktool`, `jadx`, …) et le secret extrait par
  quelqu'un de déterminé. C'est un choix assumé car l'outil est local et
  hors-ligne — mais le secret perd sa valeur de confiance s'il fuit.
- Aucun logique sensible ne doit être ajoutée ici ; le but est la génération
  de codes de licence, uniquement.

## Algorithme (à conserver identique bit à bit)

```
payload   = "CODE_CLIENT:NOMBRE_SITES:NOMBRE_POSTES"   (UTF-8)
signature = HMAC-SHA256(LICENSE_SECRET, payload) → 8 premiers octets
combined  = payload_bytes + signature_bytes (8 octets)
code      = Base32(combined) (RFC 4648, sans padding), formaté en blocs de 5
            caractères séparés par des tirets, ex. "ABCDE-FGHIJ-KLMNO"
```

Validation : retirer les tirets → Base32 decode → séparer `combined[:-8]` /
`combined[-8:]` → recalculer HMAC (8 premiers octets) → comparaison en temps
constant (`MessageDigest.isEqual`) → si OK, extraire le payload (`split(":")`).

> Ne pas changer : l'ordre des champs, la taille de signature (8 octets), le
> format Base32 ni les tirets. Les codes doivent rester compatibles avec
> l'outil Python de référence et le backend FastAPI.

## Remplacer le `LICENSE_SECRET` (point 5 du cahier des charges)

Le secret **n'est plus en dur dans le code source suivi par Git**. Il vit à un
seul endroit local : le fichier [`local.properties`](local.properties)
(**exclu de Git** via `.gitignore`).

1. Copier [`local.properties.example`](local.properties.example) vers
   `local.properties` :
   ```bash
   cp local.properties.example local.properties
   ```
2. Y renseigner la vraie valeur (longue, ≥ 16 octets d'entropie, hexadécimal
   recommandé — ex. `openssl rand -hex 32`) dans la clé `license.secret`.
   Le secret est injecté au build via `buildConfigField` dans
   `app/build.gradle.kts` et lu par `LicenseConfig.kt` → `BuildConfig.LICENSE_SECRET`.
   Ne JAMAIS commit `local.properties`.
3. Mettre la **même valeur** dans :
   - `backend/.env` (`LICENSE_SECRET`) côté DYNDISPLAY,
   - l'outil de référence Python.
4. Recompiler l'APK, générer un code de test, le vérifier côté backend.
   Le test `ReferenceVectorTest.crossVector_matchesPythonReferenceTool`
   échouera si le secret du build ne correspond pas à celui qui a produit
   le vecteur de référence (interopérabilité Kotlin ↔ Python prouvée et figée).

> Si `license.secret` est absent ou placeholder dans `local.properties`, le
> build échoue volontairement (message explicite).

## Build

```bash
# Android Studio : Open -> dossier "serialisation" -> Run.
# Ou en CLI (avec un JDK 17 et Android SDK) :
./gradlew :app:assembleDebug
./gradlew :app:testDebugUnitTest          # exécute la suite JUnit
```

`minSdk = 21` (Android 5.0) — couvre large pour la flotte terrain existante.

## Structure

```
app/src/main/java/com/t2f/licensegen/
  MainActivity.kt        # UI : saisie, génération, copie, vérification
  LicenseConfig.kt       # Secret lu depuis BuildConfig (injecté depuis local.properties)
  LicenseManager.kt      # generate() / validate() (HMAC + Base32 + tirets)
  Base32.kt              # RFC 4648 sans padding

local.properties.example  # gabarit (NE contient PAS la vraie valeur du secret)
local.properties          # secret réel — NON committé (.gitignore)

app/src/test/java/com/t2f/licensegen/
  LicenseManagerTest.kt  # round-trip, falsification, déterminisme, Base32
  ReferenceVectorTest.kt # vecteur de référence croisé Python ↔ Kotlin (secret réel)
```

## Tests couverts

- Génération puis validation immédiate → succès.
- Modification d'un seul caractère du code → rejet.
- Mêmes entrées → même code (déterminisme).
- Vecteur construit « à la main » selon la spec = code produit (référence).