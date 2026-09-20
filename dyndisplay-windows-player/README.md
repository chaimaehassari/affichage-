# DynDisplay Player (Windows)

Lecteur d'affichage **Electron** pour box / mini-PC Windows, en kiosque plein
écran. Canal d'affichage Windows supplémentaire du système DynDisplay — il lit
**exactement la même source** que le player Android existant : les fichiers
que le backend publie sur le serveur SFTP (voir `STEP0_ANALYSE.md` pour le
contrat réseau vérifié dans le code).

Aucune modification du backend DynDisplay n'est requise pour ce projet.

---

## 1. Architecture en bref

```
dyndisplay-windows-player/
  electron/
    main.js            # kiosque, cycle de vie, watchdog, auto-start, IPC SFTP/HTTP/cache
    preload.js         # pont sécurisé (contextBridge) -> window.dyndisplay
  src/
    App.jsx            # rendu des zones — adapté de PostPreview.jsx (ZoneSlideshow/PdfZone)
    screens/SetupScreen.jsx   # config initiale + paramètres cachés
    sync/
      ftpClient.js     # SFTP : players/<code_poste>/config.json + médias
      heartbeat.js     # POST /api/v1/posts/heartbeat toutes les 60 s
      pingHandler.js   # ping serveur = ICMP côté serveur (no-op documenté)
    cache/mediaCache.js    # cache %APPDATA%/dyndisplay-player/cache/media
    config/localConfig.js  # config locale %APPDATA%/dyndisplay-player/config.json
    pdf/pdfRender.js       # rendu local des PDF (pdf.js), page par page
  STEP0_ANALYSE.md      # les 3 points de l'étape 0 documentés (heartbeat/ping/config.json)
```

Données locales :

| Élément | Emplacement |
|---|---|
| Config locale (paramètres de connexion) | `%APPDATA%/dyndisplay-player/config.json` |
| `config.json` synchronisé (dernier contenu connu) | `%APPDATA%/dyndisplay-player/cache/last-config.json` |
| Médias téléchargés | `%APPDATA%/dyndisplay-player/cache/media/<sftp_path>` |

Le player est **résilient en offline** : il continue d'afficher le dernier
contenu connu (config + médias en cache) si le serveur ou le réseau tombe
temporairement.

---

## 2. Lancement en développement

Prérequis : Node.js ≥ 20.

```bash
npm install
npm run dev
```

`npm run dev` démarre :
1. Vite (frontend React) sur `http://localhost:5174` ;
2. Electron qui charge cette URL (fenêtre kiosque, DevTools ouverts en mode dev).

> En dev, les raccourcis clavier (Ctrl+R, F5…) restent bloqués comme en
> production pour tester le comportement kiosque.

---

## 3. Build de l'installeur Windows

```bash
npm run dist
```

Produit dans `release/` :
- `DynDisplay-Player-<version>.exe` — **installeur NSIS** (mode silencieux
  possible en ligne de commande) ;
- `DynDisplay-Player-<version>-portable.exe` — **exécutable portable**.

Variantes utiles :
- `npm run dist:dir` → dossier non packagé (débogage du build) ;
- `npm run pack` → installeur Windows uniquement.

Auto-start : l'application propose d'**Activer l'auto-start Windows**
(paramètres cachés). Elle utilise le mécanisme `app.setLoginItemSettings`
(équivalent HKCU `Run`), donc la box **repart seule après une coupure de
courant**, sans intervention humaine.

---

## 4. Configuration d'une nouvelle box (procédure)

1. **Installer** `DynDisplay-Player-<version>.exe` sur la box Windows
   (ou copier le portable exe).
2. **Premier lancement** : l'écran « Configuration initiale » s'affiche.
3. Renseigner :
   - **Code site** — libre (référence uniquement).
   - **Code poste** — libre. C'est ce code qui détermine le dossier
     `players/<code>/` lu sur le SFTP.
   - **Adresse IP du serveur** — l'hôte SFTP (+ l'API HTTP qui sert le
     heartbeat sur le port 8000).
   - **Port FTP/SFTP** — défaut **22** (le backend DynDisplay utilise
     SFTP/paramiko ; le port 21 ne convient qu'à un serveur FTP classique).
   - **Utilisateur / mot de passe FTP** — identifiants SFTP du serveur.
   - **Code client** — code tenant serveur (information).
   - **Port API HTTP** — défaut `8000` (heartbeat).
   - Options avancées : **Poll (s)** (détection de changement, défaut 60 s),
     **Synchro quotidienne** (défaut `02:00`, alignée sur le réglage global
     `sync_auto_time` du serveur).
4. **Tester la connexion** : effectue une vraie connexion SFTP et affiche
   succès/échec avant de continuer.
5. **Démarrer le player** : synchro immédiate → téléchargement de
   `players/P1/config.json` + des médias (delta : uniquement les fichiers
   nouveaux/modifiés) → affichage kiosque plein écran.

> Sur le site DynDisplay (console web), le poste doit être **créé** avec le
> même code (P1) et son **`ip_address` renseignée** pour que le ping ICMP
> serveur le trouve. Le rendu reprendra automatiquement la config assignée.

### Paramètres cachés — accès

Une fois en kiosque, la **seule** manière d'ouvrir l'écran de paramètres est
le raccourci clavier : **`Ctrl + Alt + Maj + P`**. Il permet de :
- modifier la connexion / les codes, tester à nouveau, re-synchroniser ;
- activer/désactiver l'auto-start Windows ;
- basculer l'affichage des badges/couleurs de la prévisualisation ;
- quitter l'application.

---

## 5. Comportement d'affichage (identique à la prévisualisation web)

- **Zones indépendantes** : chaque zone possède sa propre playlist
  (`media_playlist`, ordonnée par `display_order`) et joue en parallèle des
  autres zones. Position/taille en **pourcentage** depuis `layout.zones`.
- **Images** : durée d'affichage `duration_seconds` (3–60 s côté web), puis
  média suivant.
- **Vidéos** : lues **en entier** (durée native ; le champ `duration_seconds`
  n'est pas appliqué — limite connue côté web), puis média suivant.
- **PDF** : rendu **local** page par page (pdf.js) — 1 page = 1 écran,
  ~10 s/page, rotation automatique de la dernière à la première page,
  même sémantique que `PdfZone` de `PostPreview.jsx`. Les pages PNG ne sont
  pas fournies par le serveur au player (`config.json` FTP n'a pas
  `pdf_pages`), d'où le rendu local.
- **Boucle** (`loop_enabled`) : si vrai, la playlist recommence à l'infini ;
  sinon elle s'arrête sur le **dernier média** affiché.
- **`display_enabled` à false** : écran noir « Affichage désactivé ».

## 6. Supervision

| Brique | Détail |
|---|---|
| Heartbeat | `POST http://<serveur>:8000/api/v1/posts/heartbeat`, body `{"post_id": <int>}`, toutes les **60 s**. Non authentifié. Le `post_id` vient de `config.json`. Seuil offline serveur = 90 s → marge de sécurité conservée. |
| Ping | `POST /posts/{id}/ping` = **ping ICMP** exécuté par le serveur vers l'IP du poste. Le player n'expose **aucun endpoint** et ne poll **aucune commande** : rien à implémenter côté application. Le poste Windows doit seulement accepter l'**ICMP v4 echo** (pare-feu). |

## 7. Sécurité / licence

Ce player est un **client passif** : aucune gestion de licence embarquée. Le
contrôle (`serialisation/`) est fait côté serveur par compte utilisateur +
quota `license_posts`. Le player est isolé par code de poste via
`players/<code>/`. Aucune logique de licence ne vit ici.

## 8. Points écartés / à valider

Voir `STEP0_ANALYSE.md` — en résumé :
1. `sync_auto_time` n'existe **pas** dans `config.json` (c'est un réglage
   global serveur). Le player détecte donc les changements par **poll** (60 s)
   + synchro quotidienne locale. Si la console doit piloter l'heure de synchro
   par poste, il faudra l'ajouter au backend plus tard.
2. Port SFTP par défaut **22** (SFTP), contrairement au « 21 » de
   l'énoncé — cohérent avec le backend (paramiko). Le champ reste éditable.
3. Le « ping » spec ne correspond pas à un canal applicatif (voir §6).