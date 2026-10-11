<#
.SYNOPSIS
    Regenere integralement le dossier de deploiement DynDisplay-Serveur-Windows
    a partir du code de developpement.

.DESCRIPTION
    Ce script remplace les ~20 commandes copie/filtre/sbuild executees a la
    main lors de la creation initiale du dossier. A relancer a chaque
    modification du backend ou du frontend.

    IMPORTANT - ce qui est GENERE et ce qui est MAINTENU A LA MAIN :

      GENERE (ecrase a chaque execution) :
        backend/app/**            code Python, sans __pycache__ / .pyc
        backend/migrations/*.sql  schema de base + migrations
                                  029 est EXCLUE par defaut (-IncludeMigration029
                                  pour l'inclure) : cf. .PARAMETER IncludeMigration029
        backend/scripts/migrate.py
        backend/scripts/check_db.py
        backend/seed_admin.py
        backend/frontend/**       build de production du frontend (npm run build)
        backend/requirements.txt  verifie, puis regenere si incoherent

      MAINTENU A LA MAIN (jamais touche) :
        install.bat, start.bat, stop.bat, README.md, .env.example
        install-helpers/**

      GENERE SUR LA MACHINE CIBLE, JAMAIS COPIE :
        .env, .venv/, media_storage/, admin-credentials.txt

    Le script ne supprime donc JAMAIS le contenu du dossier de destination, et
    ne touche pas au .env d'une installation deja faite.

.PARAMETER SourceRoot
    Racine du depot (contient DYNDISPLAY\backend et DYNDISPLAY\frontend).
    Defaut : le parent du dossier contenant ce script.

.PARAMETER DestRoot
    Dossier de deploiement a regenerer.
    Defaut : <SourceRoot>\deploy\DynDisplay-Serveur-Windows

.PARAMETER SkipFrontendBuild
    Ne pas lancer `npm run build` : reutilise le dist deja present.
    Utile quand seul le backend a change.

.PARAMETER IncludeMigration029
    INCLUSION EXPLICITE de 029_remove_account_activation.sql dans le paquet.
    Par defaut : EXCLUE. La Phase A retire le mecanisme d'activation
    compte/appareil cote code, mais la migration destructrice 029 ne doit PAS
    partir dans le paquet livre : le serveur applique alors 027, 028 (et non
    029). Passer ce commutateur pour un paquet qui doit reellement retirer les
    colonnes.

.PARAMETER PythonExe
    interpreteur utilise pour verifier requirements.txt.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File build_deploiement.ps1

.EXAMPLE
    .\build_deploiement.ps1 -SkipFrontendBuild -Verbose

.EXAMPLE
    .\build_deploiement.ps1 -IncludeMigration029   # paquet AVEC 029 (rare)
#>
[CmdletBinding()]
param(
    [string] $SourceRoot,
    [string] $DestRoot,
    [switch] $SkipFrontendBuild,
    [switch] $IncludeMigration029,
    [string] $PythonExe = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $SourceRoot) {
    $SourceRoot = Split-Path -Parent $PSScriptRoot
}
if (-not $DestRoot) {
    $DestRoot = Join-Path $SourceRoot "deploy\DynDisplay-Serveur-Windows"
}

$SrcBackend = Join-Path $SourceRoot "DYNDISPLAY\backend"
$SrcFrontend = Join-Path $SourceRoot "DYNDISPLAY\frontend"

function Write-Step([string] $Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok([string] $Message) {
    Write-Host "    [OK] $Message" -ForegroundColor Green
}

function Write-Warn2([string] $Message) {
    Write-Host "    [!] $Message" -ForegroundColor Yellow
}

function Fail([string] $Message) {
    Write-Host ""
    Write-Host "    [ECHEC] $Message" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
Write-Step "Verification des sources"
# ---------------------------------------------------------------------------
foreach ($path in @($SrcBackend, $SrcFrontend)) {
    if (-not (Test-Path -LiteralPath $path)) {
        Fail "Source introuvable : $path"
    }
}
$appDir = Join-Path $SrcBackend "app"
$migrationsDir = Join-Path $SrcBackend "migrations"
if (-not (Test-Path -LiteralPath (Join-Path $appDir "main.py"))) {
    Fail "app\main.py introuvable dans $appDir"
}
Write-Ok "backend   : $SrcBackend"
Write-Ok "frontend  : $SrcFrontend"
Write-Ok "destination : $DestRoot"

# ---------------------------------------------------------------------------
Write-Step "1/6  Copie du code backend (app/)"
# ---------------------------------------------------------------------------
$dstApp = Join-Path $DestRoot "backend\app"

# Nettoyage complet de la destination pour eviter de laisser un fichier
# supprime du cote dev (le build doit etre reproductible, pas cumulatif).
if (Test-Path -LiteralPath $dstApp) {
    Remove-Item -Recurse -Force -LiteralPath $dstApp
}
New-Item -ItemType Directory -Force -Path $dstApp | Out-Null

$pyFiles = Get-ChildItem -Recurse -File -Filter *.py -LiteralPath $appDir |
    Where-Object { $_.FullName -notmatch '__pycache__' }
foreach ($file in $pyFiles) {
    $relative = $file.FullName.Substring($appDir.Length).TrimStart('\')
    $target = Join-Path $dstApp $relative
    $parent = Split-Path -Parent $target
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
}
Write-Ok "$($pyFiles.Count) fichiers .py copies (sans __pycache__)"

# ---------------------------------------------------------------------------
Write-Step "2/6  Copie des migrations"
# ---------------------------------------------------------------------------
$dstMigrations = Join-Path $DestRoot "backend\migrations"
if (Test-Path -LiteralPath $dstMigrations) {
    Remove-Item -Recurse -Force -LiteralPath $dstMigrations
}
New-Item -ItemType Directory -Force -Path $dstMigrations | Out-Null

$sqlFiles = Get-ChildItem -File -Filter *.sql -LiteralPath $migrationsDir | Sort-Object Name
if (-not $IncludeMigration029) {
    $excluded029 = $sqlFiles | Where-Object { $_.Name -like '029_*' }
    if ($excluded029) {
        $sqlFiles = $sqlFiles | Where-Object { $_.Name -notlike '029_*' }
        Write-Warn2 "029 exclue du paquet (Phase A, retrait activation) : $($excluded029.Name -join ', ')"
        Write-Warn2 "Pour l'inclure : build_deploiement.ps1 -IncludeMigration029"
    }
}
foreach ($file in $sqlFiles) {
    Copy-Item -LiteralPath $file.FullName -Destination $dstMigrations -Force
}
Write-Ok "$($sqlFiles.Count) migrations copiees : $($sqlFiles[0].Name) -> $($sqlFiles[-1].Name)"

$baseline = Join-Path $dstMigrations "000_baseline.sql"
if (-not (Test-Path -LiteralPath $baseline)) {
    Fail "000_baseline.sql absent : une base vierge ne peut pas etre creee."
}

# ---------------------------------------------------------------------------
Write-Step "3/6  Copie du runner de migrations et du bootstrap admin"
# ---------------------------------------------------------------------------
$dstScripts = Join-Path $DestRoot "backend\scripts"
New-Item -ItemType Directory -Force -Path $dstScripts | Out-Null
Copy-Item -LiteralPath (Join-Path $SrcBackend "scripts\migrate.py") `
          -Destination (Join-Path $dstScripts "migrate.py") -Force
Write-Ok "backend\scripts\migrate.py"

Copy-Item -LiteralPath (Join-Path $SrcBackend "seed_admin.py") `
          -Destination (Join-Path $DestRoot "backend\seed_admin.py") -Force
Write-Ok "backend\seed_admin.py"

# ---------------------------------------------------------------------------
Write-Step "4/6  Verification de requirements.txt (dependances runtime)"
# ---------------------------------------------------------------------------
# Plushi�res fois, une importation a disparu de requirements.txt et
# l'application n'a casse qu'AU MOMENT DU DEMARRAGE, sur la machine
# cliente. On verifie donc systematiquement, module par module.
$requirementsPath = Join-Path $DestRoot "backend\requirements.txt"
if (-not (Test-Path -LiteralPath $requirementsPath)) {
    Fail "backend\requirements.txt absent du dossier de deploiement."
}

# Module python importe -> nom de distribution a exiger.
$moduleToDist = @{
    'fastapi' = 'fastapi'
    'uvicorn' = 'uvicorn'
    'psycopg' = 'psycopg'
    'psycopg_pool' = 'psycopg-pool'
    'pydantic' = 'pydantic'
    'pydantic_settings' = 'pydantic-settings'
    'dotenv' = 'python-dotenv'
    'jwt' = 'pyjwt'
    'argon2' = 'argon2-cffi'
    'cryptography' = 'cryptography'
    'paramiko' = 'paramiko'
    'multipart' = 'python-multipart'
    # PyMuPDF : import DANS une fonction (app/api/routes/sites.py, lecture
    # du nombre de pages d'un PDF). Un import de ce type echappe aux
    # grep '^import' : si on l'ignore, l'import de PDF casse sur une
    # machine propre, tres loin de sa cause.
    'fitz' = 'pymupdf'
}

# Modules de la bibliotheque standard : jamais dans requirements.txt.
# Liste (et non hashtable) : PowerShell 5.1 refuse les virgules en fin de
# ligne dans un litteral de hachage, et l'appartenance se teste avec -contains.
$stdlib = @(
    'os','sys','re','json','io','time','base64','struct','hashlib'
    'hmac','secrets','string','random','uuid','datetime','date','timedelta'
    'pathlib','typing','collections','itertools','functools','math'
    'mimetypes','ipaddress','socket','threading','asyncio','shutil'
    'subprocess','tempfile','traceback','warnings','logging','getpass'
    'contextlib','textwrap','csv','statistics','enum','abc','copy'
    'unittest','urllib','zipfile','glob','platform','signal','errno'
    'codecs','locale','calendar','array','binascii','zlib','sqlite3'
    'email','http','html','xml','unicodedata','difflib','inspect'
    'numbers','decimal','fractions','operator','pickle','posixpath'
    'ntpath','nturl2path','genericpath','stat','fnmatch','selectors'
    'concurrent','queue','multiprocessing','ctypes','weakref','gc'
    'marshal','ast','token','tokenize','keyword','stringprep','pty'
    'ssl','quopri','uu','wsgiref','cgi','importlib','encodings'
    '__future__','dataclasses','ftplib','winreg','zoneinfo','types'
    'ipaddress','bisect','heapq','struct','textwrap','unicodedata'
    'shutil','socket','sqlite3','ssl','statistics','string'
    'builtins','abc','atexit','builtins','code','codeop','colorsys'
    'filecmp','fileinput','fnmatch','getopt','gettext','graphlib'
    'hashlib','heapq','hmac','keyword','linecache','locale','mimetypes'
    'netrc','nturl2path','pathlib','pprint','profile','pstats'
    'queue','reprlib','rlcompleter','runpy','sched','secrets','shelve'
    'shlex','site','smtplib','sndhdr','spwd','sqlite3','stat'
    'string','stringprep','symtable','sysconfig','tabnanny'
    'tarfile','telnetlib','tempfile','termios','test','timeit'
    'token','trace','tracemalloc','tty','turtle','unicodedata'
    'uu','uuid','venv','webbrowser','xdrlib','zipapp','zipimport'
)

# Modules de test / outils : exclus du build de production.
# Signalement (pas bloquant) s'ils traînent dans requirements.txt.
$excluded = @{
    'pytest' = 'test runner (pytest) - hors production'
    'httpx' = 'client HTTP de test (TestClient) - hors production'
    'requests' = 'requests - uniquement utilise par des scripts de dev'
}

$needed = New-Object 'System.Collections.Generic.SortedSet[string]'
$unknown = New-Object 'System.Collections.Generic.SortedSet[string]'

# Extraction des imports par AST, et NON par regex.
#
# Une regex `^\s*(from|import)\s+(\w+)` confond le SQL des chaines
# triple-quote (« FROM users u » dans une requete) avec des imports Python :
# sur ce backend elle signale 17 faux positifs (users, posts, sites, clients,
# layouts, licenses...). Inversement elle ne voit pas les imports locaux a une
# fonction, dont `import fitz` (app/api/routes/sites.py).
#
# ast.parse tranche les deux : il ignore le contenu des chaines et visite les
# imports imbriques.
$astScript = @'
import ast, os, sys

root = sys.argv[1]
modules = set()

for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d != "__pycache__"]
    for name in filenames:
        if not name.endswith(".py"):
            continue
        path = os.path.join(dirpath, name)
        try:
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
        except SyntaxError as exc:
            sys.stderr.write("SyntaxError %s: %s\n" % (path, exc))
            raise SystemExit(1)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                # level > 0 : import relatif (from . import x) -> ignorer.
                if node.level == 0 and node.module:
                    modules.add(node.module.split(".")[0])

for module in sorted(modules):
    print(module)
'@

$modules = $astScript | & $PythonExe - $appDir
if ($LASTEXITCODE -ne 0) {
    Fail "analyse AST des imports impossible (Python illisible ?)."
}
if (-not $modules) {
    Fail "aucun import trouve dans $appDir : l'audit est sans valeur, verifier $PythonExe."
}

foreach ($module in $modules) {
    if ($stdlib -contains $module) { continue }
    if ($module -like 'app*') { continue }
    if ($moduleToDist.ContainsKey($module)) {
        $null = $needed.Add($moduleToDist[$module])
    }
    else {
        # Ni standard, ni local a app/ : peut etre une dependance MANQUANTE.
        $null = $unknown.Add($module)
    }
}

$declared = @{}
foreach ($line in (Get-Content -LiteralPath $requirementsPath -Encoding UTF8)) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
    if ($trimmed -match '^([A-Za-z0-9_.-]+)') { $declared[$Matches[1].ToLower()] = $trimmed }
}

if ($unknown.Count -gt 0) {
    Write-Warn2 "Import(s) tiers non couverts par `$moduleToDist :"
    foreach ($module in $unknown) { Write-Host "          - $module" -ForegroundColor Yellow }
    Write-Warn2 "Ajoutez-les a `$moduleToDist avec le nom de distribution"
    Write-Warn2 "correspondant, OU declarez-les explicitement dans requirements.txt."
    Fail "Imports non identifies : le build ne peut pas garantir l'execution."
}
$missing = @()
foreach ($dist in $needed) {
    $key = $dist.ToLower()
    $found = $declared.ContainsKey($key) -or
             ($declared.Keys | Where-Object { $_ -eq $key -or $key.StartsWith($_) -or $_.StartsWith($key) } | Select-Object -First 1)
    if (-not $found) { $missing += $dist }
}

if ($missing.Count -gt 0) {
    Write-Warn2 "Dependances importees par app/ mais ABSENTES de requirements.txt :"
    foreach ($dist in $missing) { Write-Host "          - $dist" -ForegroundColor Yellow }
    Fail "Corrige backend\requirements.txt avant de livrer le dossier."
}
Write-Ok "les $($needed.Count) dependances runtime sont declarees : $($needed -join ', ')"

foreach ($key in $declared.Keys) {
    if ($excluded.ContainsKey($key)) {
        Write-Warn2 "'$key' est dans requirements.txt mais ne sert qu'au dev ($($excluded[$key]))"
    }
}

# ---------------------------------------------------------------------------
Write-Step "5/6  Build du frontend"
# ---------------------------------------------------------------------------
$dstFrontend = Join-Path $DestRoot "backend\frontend"
if ($SkipFrontendBuild) {
    if (-not (Test-Path -LiteralPath (Join-Path $dstFrontend "index.html"))) {
        Fail "-SkipFrontendBuild demande mais aucun build present dans backend\frontend."
    }
    Write-Ok "build frontend reutilise (-SkipFrontendBuild), pas de npm run build"
}
else {
    if (-not (Test-Path -LiteralPath (Join-Path $SrcFrontend "node_modules"))) {
        Fail "node_modules absent dans $SrcFrontend : lancez `npm install` d'abord."
    }
    Push-Location $SrcFrontend
    try {
        Write-Host "    npm run build ..." -ForegroundColor DarkGray
        # NE PAS ecrire `& npm run build 2>&1 | Out-Null` ici.
        # Sous PowerShell 5.1, la fusion `2>&1` transforme chaque ligne
        # d'erreur du processus natif en ErrorRecord ; combinee a
        # $ErrorActionPreference = "Stop" (ligne 61), la PREMIERE ligne de
        # stderr de vite arrete le deploiement. Or vite ecrit normalement ses
        # couleurs et ses avertissements sur stderr : le script echouait
        # alors meme que `npm run build` sortait avec le code 0 et que
        # dist\index.html etait correctement produit.
        # On laisse stderr s'afficher (l'utilisateur voit les avertissements de
        # vite) et on decide uniquement sur le code de sortie reel.
        $ErrorActionPreference = "Continue"
        try {
            & npm run build
            $npmCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = "Stop"
        }
        if ($npmCode -ne 0) { Fail "npm run build a echoue (code $npmCode)." }
    }
    finally {
        Pop-Location
    }

    $distDir = Join-Path $SrcFrontend "dist"
    if (-not (Test-Path -LiteralPath (Join-Path $distDir "index.html"))) {
        Fail "le build n'a pas produit dist\index.html."
    }
    if (Test-Path -LiteralPath $dstFrontend) {
        Remove-Item -Recurse -Force -LiteralPath $dstFrontend
    }
    New-Item -ItemType Directory -Force -Path $dstFrontend | Out-Null
    Copy-Item -Recurse -Force -Path (Join-Path $distDir "*") -Destination $dstFrontend
    Write-Ok "frontend compile copie dans backend\frontend"
}

# ---------------------------------------------------------------------------
Write-Step "6/6  Controle final du dossier"
# ---------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath (Join-Path $dstFrontend "index.html"))) {
    Fail "backend\frontend\index.html absent : le serveur ne pourra pas servir l'interface."
}

# Le controle porte uniquement sur les sous-arbres que ce script REGENERE
# (1/6, 2/6, 3/6, 5/6). Balayer tout $DestRoot rendait le deploiement
# IMPOSSIBLE des la deuxieme execution : `.env` et `.venv\` sont volontairement
# conserves sur une installation deja faite — cf. l'en-tete du script et le
# rappel final — et le controle les signalait comme pollution. En pratique le
# deploiement echouait donc systematiquement sur une installation existante,
# alors que ces fichiers sont precisement ceux qu'il faut garder.
# `.env` reste interdit DANS ces sous-arbres : le recopie ne deplace que des
# *.py, des *.sql et le dist, donc un `.env` qui y apparaitrait serait bien une
# fuite de l'arborescence de developpement.
$scannedDirs = @(
    (Join-Path $DestRoot "backend\app"),
    (Join-Path $DestRoot "backend\migrations"),
    (Join-Path $DestRoot "backend\scripts"),
    $dstFrontend
) | Where-Object { Test-Path -LiteralPath $_ }

# Purge prealable des caches Python rests dans les sous-dossiers regeneres.
# `backend\app` est recree a zero a l'etape 1/6, mais `backend\scripts` ne
# l'est pas : l'etape 3/6 y copie seulement deux fichiers. Un `migrate.py`
# execute sur place (ce qu'on fait apres chaque deploiement) y laisse donc un
# `__pycache__` qui faisait echouer le controle final, sans que ce soit la
# faute du code qui vient d'etre copie. Le serveur en laisse autant dans
# `backend\app` a chaque demarrage.
foreach ($dir in $scannedDirs) {
    Get-ChildItem -Recurse -Force -Directory -Filter '__pycache__' -LiteralPath $dir |
        ForEach-Object { Remove-Item -Recurse -Force -LiteralPath $_.FullName }
}

$polluting = foreach ($dir in $scannedDirs) {
    Get-ChildItem -Recurse -Force -LiteralPath $dir |
        Where-Object {
            $_.Name -in @('__pycache__', 'node_modules', '.pytest_cache', '.env') -or
            $_.Extension -in @('.pyc', '.log')
        }
}
if ($polluting) {
    Fail "Artefacts de developpement dans le dossier de deploiement : $(($polluting | Select-Object -First 5 -ExpandProperty FullName) -join ', ')"
}
Write-Ok "aucun artefact de developpement dans les sous-dossiers regeneres (__pycache__, node_modules, .env, logs)"

$size = (Get-ChildItem -Recurse -File -LiteralPath $DestRoot | Measure-Object -Property Length -Sum).Sum
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  DOSSIER REGENERE" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Chemin : $DestRoot"
Write-Host ("  Taille : {0:N1} Mo" -f ($size / 1MB))
Write-Host ""
Write-Host "  Rappel : .env, .venv\, media_storage\ et admin-credentials.txt"
Write-Host "  ne doivent PAS etre copies sur la machine cible."
Write-Host "============================================================"
