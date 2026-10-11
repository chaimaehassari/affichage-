#!/usr/bin/env python3
"""Refuse les clés privées hexadécimales de 64 caractères dans les fichiers suivis.

Deux détections :
  1. deny-list : empreinte SHA-256 d'une clé privée connue (la valeur en clair
     n'est PAS présente dans ce script) ;
  2. heuristique : affectation d'un jeton hex de 64 caractères à une variable
     dont le nom évoque une clé privée (private|secret|passphrase|priv_key...).

Les clés *publiques* (nom contenant « public ») ne sont pas signalées.

Usage :
  py -3 scripts/check_no_private_keys.py            # tous les fichiers suivis
  py -3 scripts/check_no_private_keys.py --staged   # index Git (pre-commit)
  py -3 scripts/check_no_private_keys.py f1 f2 ...  # fichiers explicites

Code retour : 0 si propre, 1 si au moins une correspondance.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys

# Empreintes SHA-256 (hex) de clés privées connues à ne jamais committer.
# Seule l'empreinte est stockée : la valeur en clair n'apparaît pas ici.
DENY_SHA256 = {
    "83c13ef53c34d923f3b896d77a13abebce53e15ff5e105f0a47b8bfce29ee0ff",
}

HEX64 = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")
PRIVATE_ASSIGN = re.compile(
    r"[A-Za-z0-9_]*(?:private|secret|passphrase|priv_?key)[A-Za-z0-9_]*"
    r"\s*[:=]\s*[\"']?([0-9A-Fa-f]{64})",
    re.IGNORECASE,
)


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=False
        ).stdout
    except OSError:
        return ""


def target_files(argv: list[str]) -> list[str]:
    explicit = [a for a in argv if not a.startswith("--")]
    if explicit:
        return explicit
    if "--staged" in argv:
        out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"])
    else:
        out = _git(["ls-files", "-z"])
    return [p for p in out.split("\0") if p]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.lower().encode("ascii", "ignore")).hexdigest()


def scan(files: list[str]) -> list[tuple[str, int, str, str]]:
    hits: list[tuple[str, int, str, str]] = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    for match in HEX64.finditer(line):
                        value = match.group(0)
                        if _sha256(value) in DENY_SHA256:
                            hits.append((path, lineno, value, "deny-list"))
                    for match in PRIVATE_ASSIGN.finditer(line):
                        hits.append((path, lineno, match.group(1), "affectation clé privée"))
        except (OSError, UnicodeError):
            continue
    return hits


def main(argv: list[str]) -> int:
    files = target_files(argv)
    hits = scan(files)
    if hits:
        print("ECHEC : clé privée / secret hex 64 détecté :", file=sys.stderr)
        for path, lineno, value, why in hits:
            print(f"  {path}:{lineno} [{why}] {value[:8]}…{value[-8:]}", file=sys.stderr)
        return 1
    print(f"OK : aucun secret hex 64 dans {len(files)} fichier(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
