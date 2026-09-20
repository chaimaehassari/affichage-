# Test manuel — DynDisplay Player Windows

Guide de test local entre ce PC (serveur + player sur la même machine).

> Prérequis déjà en place sur ce poste :
> - Backend DynDisplay **en cours d'exécution** sur `http://localhost:8000` (uvicorn).
> - Serveur SFTP (OpenSSH, port **22**) actif, racine `C:\DYNDISPLAY-SFTP`.
> - Poste de test **`1`** (« poste casa », site « Casablanca », `post_id=7`) avec une
>   config publiée : `players/1/config.json` + médias dans `players/1/media/`.
>   Son `ip_address` est réglé sur `192.168.11.108` (IP Wi-Fi de ce PC).

## 1. Lancer l'application

**Packagé (recommandé)** — depuis `dyndisplay-windows-player\` :

```powershell
.\release\win-unpacked\DynDisplay Player.exe
```

ou en dev : `npm run dev` (Vite sur **5174** + Electron).

> ⚠️ L'application est **single-instance** : si un écran « Configuration initiale »
> ou kiosque est déjà ouvert, ferme-le d'abord (`Ctrl+Alt+Maj+P` → « Quitter ») avant
> de relancer, sinon l'exe se ferme immédiatement.

## 2. Remplir le formulaire « Configuration initiale »

| Champ | Valeur à saisir |
|---|---|
| **Code site** | `3` (référence libre, ex. casablanca, S1…) |
| **Code poste** | `1` ← DÉTERMINANT : lit `players/1/` sur le SFTP |
| **Adresse IP du serveur** | `127.0.0.1` |
| **Port FTP/SFTP** | `22` (SFTP, pas 21) |
| **Utilisateur FTP** | `chaimae` |
| **Mot de passe FTP** | valeur `SFTP_PASSWORD=` du fichier `DYNDISPLAY\backend\.env` |
| **Code client** | laisser vide (ou le code tenant serveur) |
| **Port API HTTP** | `8000` |
| **Poll (s)** | `60` |
| **Synchro quotidienne** | `02:00` |

Puis clique sur **« Tester la connexion »** : une vraie connexion SFTP est faite —
succès attendu. Ensuite **« Démarrer »**.

## 3. Après « Démarrer » — affichage attendu

Le player : synchronisation immédiate → télécharge `players/1/config.json` + médias
(delta) → lance l'affichage kiosque plein écran.

Contenu attendu (4 zones indépendantes) :

| Zone | Contenu | Durée |
|---|---|---|
| 1 (haut, 100%×50%) | image 1 puis image 2 | 5 s puis 8 s |
| 2 (bas, 100%×50%) | image | 12 s |
| 3 (zone interne) | image | ~10 s (défaut) |
| 4 | **vidéo** `Enregistrement_..._132749.mp4` | durée native, lue en entier |

Personnalisation : bouton télécommande OK, config en boucle (`loop_enabled=true`).

## 4. Vérifications côté serveur

```powershell
# Heartbeat : le player l'envoie toutes les 60 s, la console doit voir le poste en ligne
Invoke-RestMethod -Uri "http://localhost:8000/api/health"            # {"status":"ok"}
# Dernier contenu publié (sur le SFTP local) :
Get-Content "C:\DYNDISPLAY-SFTP\players\1\config.json" -Raw
# Poste en base (IP + dernière synchro) : post_id = 7
```

Raccourci menu caché en kiosque : **`Ctrl+Alt+Maj+P`** (re-tester, resynchroniser,
auto-start Windows, quitter).

## 5. Créer SON PROPRÉ site / poste (repro But)

1. Console web (`http://localhost:8000` → frontend dev `http://localhost:5173`) →
   « Sites & Postes » → créer un **site** puis un **poste** (ex. code `P1`, type
   Windows, IP = `192.168.11.108`).
2. Ouvrir **DisplayConfig** pour ce poste, affecter un **layout** et ajouter des
   **médias** aux zones, sauvegarder → le backend régénère
   `players/P1/config.json` + médias lors de la synchro suivante (auto ou bouton
   « Synchroniser »).
3. Dans le player (formulaire) mettre **Code poste = `P1`** et refaire le test.

## 6. Critères de réussite

- [ ] « Tester la connexion » → succès SFTP
- [ ] Après Démarrer, les 4 zones s'affichent (3 images + 1 vidéo)
- [ ] Les images bouclent (5 s / 8 s / 12 s), la vidéo se lit en entier
- [ ] `heartbeat` reçu (dans les logs API : `POST /api/v1/posts/heartbeat 200`)
- [ ] Couper le WiFi/le serveur → le player continue d'afficher le contenu en cache
- [ ] Redémarrer le PC → le player repart en kiosque (si auto-start activé dans le menu caché)

> ⚠️ SÉCURITÉ : ce document contient des infos de connexion locales. Ne pas le
> committer tel quel.