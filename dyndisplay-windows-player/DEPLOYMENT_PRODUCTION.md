# Déploiement box — DynDisplay Player (Windows)

Procédure et recommandations pour installer le player sur une **box réelle**
(mini-PC / VM kiosque), valider le démarrage automatique et mesurer le temps
d'affichage après une coupure de courant.

## 1. Binaire à déployer

Produit par `npm run dist` (la commande **complète**, pas `--dir`) :

| Fichier | Type | Taille |
|---|---|---|
| `release\DynDisplay-Player-1.0.0.exe` | Installeur **NSIS** (assistant, changeable) | ~94 Mo |
| `release\DynDisplay-Player-1.0.0-portable.exe` | Exécutable portable | ~94 Mo |

Installer avec l'installeur NSIS : raccourcis bureau + menu Démarrer créés
(option `createDesktopShortcut` / `createStartMenuShortcut`), et à la fin de
l'installation l'application se lance (`runAfterFinish: true`) → premier écran =
« Configuration initiale ».

## 2. Comportement auto-start actuel (à connaître absolument)

Le player gère son auto-start dans `electron/main.js` via
`app.setLoginItemSettings({ openAtLogin, openAsHidden })` (IPC `app:set-autostart`,
menu caché `Ctrl+Alt+Maj+P`).

Sur Windows, `setLoginItemSettings` écrit une entrée
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` :

- l'entrée se déclenche **à l'OUVERTURE DE SESSION** de l'utilisateur installé,
- **PAS au démarrage système** (boot).

Conséquence pour un redémarrage réel (simulation coupure de courant) :

> Si la box affiche l'écran de connexion Windows (pas d'auto-login) →
> **aucune session n'est ouverte → l'entrée Run ne se déclenche jamais → le
> player ne démarre pas.** C'est un FAIL attendu, pas un bug du player.

## 3. Recommandation : stratégie kiosque pour une box réelle

### 3.1 Option retenue : auto-login Windows d'un compte kiosque DÉDIÉ (recommandé)

Un player affichage dynamique est un appareil dédié : il doit ressembler à un
téléviseur. L'accès physique complet sans mot de passe est **le** compromis
assumé par la majorité des déploiements signage, MAIS il doit être encadré :

1. **Créer un compte Windows local dédié** (ex. `kiosk`), dans le groupe
   « Utilisateurs » **pas** « Administrateurs ».
2. **Activer l'auto-login** de ce compte (voir 3.3) — faisable sans stocker
   le mot de passe en clair registre via `netplwiz`.
3. Déverrouiller l'accès au menu caché seulement pour la maintenance
   (prévoir un compte admin distinct, grab d'accès physique limité).
4. Durcissements complémentaires recommandés pour passer de « acceptable » à
   « défendable » :
   - Désactiver/complexifier l'accès : session Utilisateur indépendante, verrou
     règlé, `Ctrl+Alt+Suppr` sans actions sensibles, bloquer la fermeture de
     l'app (le kiosque du player le gère déjà en partie).
   - **Assigned Access / Kiosk Mode** (Windows 10/11 Pro/Enterprise) : un seul
     compte « application kiosque » confinement à l'app — bonne ceinture-bretelles
     si la box est accessible au public.
   - BIOS : « Power On After Power Loss » = ON (coupure secteur → boot auto).
   - Windows Update maintenance fenêtre hors heures d'ouverture.
   - Pare-feu : autoriser ICMP (nécessaire au ping serveur, cf. STEP0_ANALYSE §ping).

### 3.2 Pourquoi pas « simplement » une tâche planifiée au démarrage système ?

Une tâche planifiée avec déclencheur **« au démarrage »** (`/sc onstart`) déclenche
en session 0 (non interactive) si elle est configurée « exécuter que l'utilisateur
soit connecté ou non » : **Electron ne peut pas afficher de kiosque en session 0**
→ l'app se lance « dans le vide », invisible.

Une tâche avec exécution « uniquement si connecté » revient au même besoin : il
**faut** une session ouverte → il faut l'auto-login. Conclusion : **l'auto-login
d'un compte kiosque est incontournable** pour tout player qui doit démarrer seul
après une coupure de courant. L'alternative équivalente (même dépendance) est la
tâche `/sc onlogon`.

### 3.3 Activer l'auto-login Windows (procédure)

Méthode sans mot de passe clair enregistré (recommandée) — `netplwiz` :

1. `Win+R` → `netplwiz`
2. Sélectionner le compte kiosque ; décocher
   « **Les utilisateurs doivent entrer un nom d'utilisateur et un mot de passe** »
3. Saisir 2× le mot de passe (stocké en secret LSA, pas en clair registre)
4. Redémarrer pour valider.

Ou (équivalent registre, à éviter en clair sauf purpose internalisé) :

```powershell
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /t REG_SZ /d 1 /f
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultUserName /t REG_SZ /d kiosk /f
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultDomainName /t REG_SZ /d $env:COMPUTERNAME /f
# /!\ DefaultPassword = mot de passe EN CLAIR dans le registre — préférer netplwiz.
```

### 3.4 Après l'auto-login, faire démarrer le player

Le player s'ajoute lui-même à `HKCU\...\Run` via son menu caché
(`Ctrl+Alt+Maj+P` → « auto-start Windows »). Depuis le compte kiosque, après
l'installation : cocher l'auto-start, puis vérifier la présence de l'entrée :

```powershell
Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" | fl
```

## 4. Protocole de test final (à exécuter sur la box, une fois en place)

1. Installer `DynDisplay-Player-1.0.0.exe` (machine vierge de préférence, sinon
   la machine de test la moins outillée — noter la limite).
2. Écran « Configuration initiale » → poste de test déjà existant
   (ex. poste / site 134·1146, ou en créer un) → « Tester la connexion » → ok,
   « Démarrer ».
3. Affichage kiosque : contenu attendu dans les zones.
4. **Redémarrage réel** du PC (pas une simple fermeture fenêtre) : simule une
   coupure secteur.
5. Mesurer : `t_content = heure(affichage 1er contenu) − heure(alimentation)`.
6. Après reboot, sans intervention :
   - [ ] la box s'est auto-loggée (sans mot de passe) ?
   - [ ] le player s'est relancé en kiosque ?
   - [ ] la config + médias présents en cache affichent rapidement
         (éviter de dépendre du réseau pour le 1er affichage).
7. Si le player ne démarre pas : contrôler dans l'ordre —
   a. l'entrée `HKCU\...\Run` existe-t-elle **dans le profil kiosque** ?
   b. l'auto-login a-t-il bien abouti (session ouverte, pas d'écran de connexion) ?
   c. `eventvwr` → journal Application : erreur de lancement ?

## 5. Limites constatées (salle de dev)

- Machine de dev actuelle : **aucun auto-login** configuré
  (`AutoAdminLogon` absent) et **aucune entrée Run** player → un reboot ici ne
  relancerait pas le player sans connexion manuelle. Ce n'est pas le poste de test.
- Le test d'installation sur machine propre + reboot réel doit être fait sur le
  poste de test (134/1146) ou une VM : hors de portée depuis le poste de dev.