"""Non-regression : construction du DSN PostgreSQL a partir de POSTGRES_*.

Bug couvert : le DSN etait monte par concatenation, sans echappement. Un mot
de passe contenant un caractere reserve d'URL rendait donc la connexion
impossible au moment reel :

    postgresql://u:Pwd#1@host:5432/db   ->  '#' ouvre le fragment, l'URL est
                                            coupee et le mot de passe perdu.

Ce n'etait pas hypothetique : le generateur de l'installateur produit des
mots de passe contenant '#' et '%', donc une installation neuve pouvait ne pas
arriver a se connecter a sa propre base alors que psql, avec le meme mot de
passe, fonctionnait. Le symptome (FATAL: authentification echouee pour
l'utilisateur X) ne designait aucun mot de passe errone et sendait chercher
au mauvais endroit.
"""
from __future__ import annotations

import os
from urllib.parse import quote

import pytest

from app.core.config import build_postgres_dsn


class _FakeSettings:
    def __init__(self, user: str, password: str, db: str = "dyndisplay") -> None:
        self.POSTGRES_USER = user
        self.POSTGRES_PASSWORD = password
        self.POSTGRES_DB = db
        self.POSTGRES_HOST = "localhost"
        self.POSTGRES_PORT = 5432


# Mots de passe produits par le generateur de l'installateur, ou par un
# operateur : chacun casse l'assemblage « postgresql://user:pass@h/db ».
RESERVES = ["Dyn#2026x", "Pwd%2x", "a#b%c", "Dyn@2026x", "Dyn/2026x", "p?d&e"]


@pytest.mark.parametrize("password", RESERVES)
def test_mot_de_passe_percent_encode(password: str) -> None:
    """Le mot de passe doit etre encode dans le DSN.

    On verifie la chaine produite, et non le resultat d'un parseur : c'est
    `psycopg.connect()` qui a tranche, et il est plus strict que
    `conninfo_to_dict` (qui, lui, laissait passer un '#').
    """
    dsn = build_postgres_dsn(_FakeSettings("dyndisplay", password))
    assert quote(password, safe="") in dsn, (
        f"le mot de passe {password!r} n'est pas encode dans {dsn!r} : "
        "l'application ne pourra pas se connecter."
    )
    assert password not in dsn, (
        f"le mot de passe {password!r} apparait en clair dans {dsn!r}."
    )


@pytest.mark.parametrize("password", ["motdepasse", "Dyn_2026-x", ""])
def test_mot_de_passe_simple_inchange(password: str) -> None:
    """Sans caractere reserve, le DSN doit rester lisible tel quel."""
    dsn = build_postgres_dsn(_FakeSettings("dyndisplay", password))
    assert f"postgresql://dyndisplay:{password}@localhost:5432/dyndisplay" == dsn


def test_identifiant_et_base_percent_encodes() -> None:
    dsn = build_postgres_dsn(_FakeSettings("dyn#display", "Dyn2026x", "dyn#base"))
    assert "dyn%23display" in dsn
    assert "dyn%23base" in dsn


def test_connexion_reelle_avec_mot_de_passe_reserve() -> None:
    """Preuve de bout en bout, uniquement si une base de test est fournie.

    C'est ce test qui a demontre le defaut : avec le DNS d'origine,
    `psycopg.connect` echouait sur un mot de passe contenant '#'/'%' alors
    que le meme mot de passe fonctionnait en ligne de commande.
    """
    url = os.environ.get("TEST_DSN_RESERVED_URL", "").strip()
    if not url:
        pytest.skip("TEST_DSN_RESERVED_URL non definie (pas de base de test)")

    import psycopg

    with psycopg.connect(url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)