# DynDisplay Player Windows — Analyse Étape 0

Document d'architecture issu de l'inspection du code **réel** de `DYNDISPLAY/`
(backend FastAPI + frontend React). Ce document conditionne toute
l'implémentation du player. Chaque point liste le code observé et la
conséquence exacte pour `dyndisplay-windows-player/`.

> Base de référence vérifiée à jour au moment de la création du projet.
> Aucune modification du backend n'est requise pour ce lot.

---

## 1. Payload exact de `POST /api/v1/posts/heartbeat`

**Fichiers inspectés**
- `backend/app/api/routes/supervision.py:23-32`
- `backend/app/schemas/supervision.py:23-24`
- `backend/app/services/supervision_service.py:123-138`

**Fait observé**

La route `send_heartbeat` n'a **aucune dépendance d'authentification**
(pas de `require_permission`, pas de `require_activated`) — un appel
volontairement non authentifié, confirmant l'audit mentionné dans la
demande.

Le schema Pydantic est exhaustif :

```python
class HeartbeatRequest(BaseModel):
    post_id: int
```

Et le service :

```python
def send_heartbeat(self, post_id: int) -> bool:
    # ... met is_online = TRUE, last_heartbeat_at = now
```

**Contrat exact pour le player**

```
POST http://<serveur>:8000/api/v1/posts/heartbeat
Content-Type: application/json

{"post_id": 42}
```

- Succès : `200` → `{"message": "Heartbeat reçu."}`
- Échec : `404` → `{"detail": "Poste introuvable."}` (si le `post_id`
  n'existe pas en base)

**Conséquence d'implémentation**

Le player doit connaître son **`post_id` (identifiant entier de la table
`posts`)**, pas seulement son code « P1 ». Ce `post_id` est fourni par le
serveur dans **`config.json`** (`"post_id": <int>`, cf. §3). Le heartbeat
ne peut donc démarrer qu'**après la première synchronisation** réussie, qui
livre `config.json` localement. Toutes les 60 s (marge de sécurité vs le
seuil offline serveur de 90 s, cf. `HEARTBEAT_OFFLINE_THRESHOLD_SECONDS`)
le player envoie `{"post_id": <id>}`. Pas d'autre champ, pas de header.

---

## 2. Mécanisme exact du ping `POST /posts/{id}/ping`

**Fichiers inspectés**
- `backend/app/api/routes/supervision.py:35-47`
- `backend/app/services/supervision_service.py:140-195`

**Fait observé — point important, diffère de l'énoncé initial**

Le « ping » du serveur vers une box **n'est PAS bidirectionnel applicatif**
et **n'utilise aucun des deux mécanismes supposés** :
- La box n'a **pas besoin d'exposer un endpoint HTTP local** ;
- La box ne doit **pas interroger une « commande en attente »** au prochain
  heartbeat.

La route est un simple **ping ICMP réel** : le serveur exécute la commande
système `ping` vers l'adresse IP enregistrée du poste (`posts.ip_address`)
et retourne joignabilité + RTT.

```python
def ping_post(self, post_id: int) -> dict:
    # lit post["ip_address"] | None
    params = ["ping", "-n", "1", "-w", "5000", host]   # Windows
    result = subprocess.run(params, ...)
    # parse "temps=2ms" / "time=1ms" → {"reachable", "rtt_ms"}
```

De plus cette route est **authentifiée** (`require_permission("menu_config")`
+ `require_activated` + contrôle de scope) : c'est un outil d'admin côté
interface web, pas un canal de commande vers le player.

**Conséquence d'implémentation**

Aucun code actif n'est nécessaire côté player pour répondre au ping. Le
module `src/sync/pingHandler.js` ne fait donc **que documenter** ce
mécanisme (il est conservé dans la structure demandée, en tant que no-op
explicite). Les deux seules exigences réelles pour qu'un poste Windows
soit « pingable » depuis le serveur :

1. Le champ `ip_address` du poste doit être renseigné côté serveur
   (Dashboard / Sites & Postes) — action **backend/admin**, hors périmètre
   player ;
2. La box Windows doit **répondre aux requêtes ICMP echo** (autoriser le
   trafic entrant `ICMPv4 echo request` après le profil *Domaine* /
   *Privé* du Pare-feu Windows). Le player n'effectue aucune action réseau
   pour le ping, il doit juste laisser ICMP passer.

⚠️ **À valider ensemble** : si l'équipe attendait un « ping applicatif »
(pousser une commande vers la box), ce mécanisme n'existe pas dans ce
backend. Seul l'ICMP serveur → box existe. Si une commande applicative est
souhaitée plus tard, elle devra être ajoutée côté backend (nouveau canal de
commande à poller au heartbeat), car rien ne l'expose aujourd'hui.

---

## 3. Format exact de `config.json` (zones, media_playlist, durées)

**Fichiers inspectés**
- `backend/app/services/sync_service.py` : `generate_config` (l.134-218) et
  `_group_zones_playlists` (l.220-252) → c'est **le fichier réellement
  écrit sur le SFTP** ; `run_sync` (l.290-466) → c'est **le schéma
  d'arborescence SFTP**.
- `backend/app/api/routes/sites.py:518-622` → comment les médias sont
  stockés (PDF pages, images, vidéos) et ce que vaut `sftp_path`.
- `backend/app/services/configuration_service.py:95-148` → variante de
  l'API web (elle ajoute `url`/`pdf_pages`, absente du fichier FTP).

**3a. Arborescence SFTP écrite par le serveur (run_sync)**

```python
root = settings.SFTP_ROOT_PATH.rstrip("/")
player_dir = f"{root}/players/{post_code}"        # post_code = "code" du POSTE (ex. "P1")
media_dir  = f"{player_dir}/media"
```

Le serveur écrit **`players/<code_poste>/config.json`** (avec `code` = le
code du poste, p.ex. `players/P1/config.json`, **pas** un code client) puis
copie chaque média sous **`players/<code_poste>/media/<sftp_path>`**
(p.ex. `players/P1/media/images/1690000000_logo.png`).

> ⚠️ **Correction vs l'énoncé** : l'arborescence est par **code de poste**
> (`players/P1/`), pas par `code_client`. Le player construit donc son
> chemin de lecture à partir du **« code poste »** saisi à l'écran de
> config, et **n'utilise pas** le code client pour localiser les fichiers.
> Le code client est un concept de licence/tenant côté serveur, absent de
> l'arborescence de synchronisation.

**3b. Schéma exact de `config.json` (sortie de `generate_config`)**

```json
{
  "post_id": 1,
  "code": "P1",
  "name": "Écran accueil",
  "layout": {
    "layout_id": 3,
    "zones": [
      {
        "zone_number": 1,
        "position_x": 0.0,
        "position_y": 0.0,
        "width": 50.0,
        "height": 100.0,
        "is_active": true
      }
    ]
  },
  "zones": [
    {
      "zone_number": 1,
      "media_playlist": [
        {
          "media_id": 12,
          "name": "logo.png",
          "media_type": "IMAGE",
          "filename": "images/1690000000_logo.png",
          "duration_seconds": 10,
          "display_order": 1
        },
        {
          "media_id": 7,
          "name": "pub.mp4",
          "media_type": "VIDEO",
          "filename": "videos/1690000001_pub.mp4",
          "duration_seconds": null,
          "display_order": 2
        },
        {
          "media_id": 3,
          "name": "menu.pdf",
          "media_type": "PDF",
          "filename": "pdfs/1690000002_menu.pdf",
          "duration_seconds": 12,
          "display_order": 3
        }
      ],
      "media": {
        "media_id": 12,
        "name": "logo.png",
        "media_type": "IMAGE",
        "filename": "images/1690000000_logo.png",
        "duration_seconds": 10,
        "display_order": 1
      }
    }
  ],
  "loop_enabled": true,
  "schedule_enabled": false,
  "display_enabled": true,
  "schedules": [
    {
      "name": "Planning accueil",
      "start_date": null,
      "end_date": null,
      "start_time": "08:00:00",
      "end_time": "19:00:00",
      "days_of_week": ["1", "2", "3", "4", "5"],
      "is_active": true
    }
  ]
}
```

Propriétés clés observées dans le code (à respecter strictement) :

| Champ | Type | Notes |
|---|---|---|
| `post_id` | int | **Utilisé pour le heartbeat** (§1). |
| `zones[].zone_number` | int | Index de la zone (1..n). |
| `zones[].media_playlist[]` | array | **Vraie playlist** : c'est elle qu'il faut lire (pas `media`, champs de secours = 1er élément pour compat web). |
| `.media_id` | int | Id du média. |
| `.media_type` | enum | `IMAGE` / `VIDEO` / `PDF`. |
| `.filename` | str | `sftp_path` relatif de la racine SFTP (`images/x.png`, `videos/x.mp4`, `pdfs/x.pdf`) → à télécharger depuis `players/<code>/media/<filename>`. |
| `.duration_seconds` | int/null | Non-null seulement pour IMAGE et PDF (borné 3–60 s côté web). `null` pour VIDEO (**durée native**). |
| `.display_order` | int | Ordre dans la playlist (le serveur trie déjà par `ORDER BY display_order`). |
| `layout.zones[]` | array | Coordonnées **en %** (`position_x`/`y`, `width`/`height`), zone éventuellement `is_active=false`. |
| `loop_enabled` | bool | `true` → boucle infinie ; `false` → s'arrêter sur le dernier média. |
| `schedule_enabled` / `schedules` | bool / array | Hors périmètre de rendu de ce lot (comme la préview web qui les ignore). |
| `display_enabled` | bool | `false` → rendu à l'écran noir (affichage désactivé). |

**3c. `url` et `pdf_pages` — absents de `config.json` FTP**

- La **prévisualisation web** (route API `get_configuration`) génère
  `url: "/media/<sftp_path>"` et (pour les PDF) `pdf_pages:
  ["/media/pdfs/<ts>_page_1.png", ...]` (configuration_service.py:124-137).
  C'est ce qu'utilise `PostPreview.jsx`.
- Le **`config.json` réellement synchronisé** (sync_service `generate_config`)
  **ne contient ni `url`, ni `pdf_pages`**. Il contient uniquement
  `filename` et `page_count` n'est **pas** exporté non plus.

**Conséquences d'implémentation (PDF)**

1. Le player construit ses URLs de média à partir de `filename` (source
   locale : cache `%APPDATA%/dyndisplay-player/cache/media/<filename>`), et
   **non** depuis `url` (qui pointe vers l'API web avec authentification).
2. Pour les PDF, les images des pages ne sont **pas copiées** vers
   `players/<code>/media/` par `run_sync` (seul le `.pdf` l'est). Le player
   doit donc **rendre localement le PDF page par page** (pdf.js) pour
   reproduire le comportement visuel de `PdfZone` (1 page = 1 écran,
   ~10 s/page, rotation automatique). C'est une **adaptation** : sémantique
   (page = image, 10 s, rotation) identique, mais pages générées côté box.

---

## Points laissés ouverts (à valider ensemble)

1. **`sync_auto_time` n'existe pas dans `config.json`.** La fréquence de
   synchronisation automatique demandée est en réalité un **réglage global
   serveur** (`general_settings.sync_auto_time`, défaut `"02:00"` —
   `settings_service.py:49`), **propagé à aucun client**. Le player fait
   donc : synchro immédiate au démarrage + **poll périodique** du
   `config.json` distant (défaut 60 s) qui détecte toute synchro serveur
   (immédiate ou **programmée** via `sync_jobs.scheduled_at`) dès sa
   finalisation, + synchro quotidienne à une heure locale configurable
   (`syncTime`, défaut `02:00`). Documentation complète dans le README.
2. **Port du service du serveur.** L'API FastAPI écoute en **http:8000**
   (uvicorn, cf. GUIDE.md) et les réglages SFTP par défaut sont **SFTP
   (port 22)**. L'écran de config garde la libellé « Port FTP » demandé ;
   par défaut il est pré-rempli à **22** (SFTP, cohérent avec le backend
   paramiko) alors que l'énoncé suggérait 21. Un champ additionnel
   « Port API HTTP » (défaut 8000) a été ajouté pour le heartbeat.
3. **Ping : pas d'action applicative du player** (cf. §2) — méchanisme ICMP
   serveur → IP du poste. Relèvement à prévoir si un ping applicatif
   (commande poussée) est requis plus tard.