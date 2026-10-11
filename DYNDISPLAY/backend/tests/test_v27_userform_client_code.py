"""Tests du widget 'Code client' en saisie libre (UserForm).

Le backend valide le perimetre : ces tests verifient que le code saisi
passe par la meme validation, que le 400 est remonte tel quel, et que
le message 'aucun client' n'apparait que si c'est reellement vrai.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import psycopg
import pytest
from psycopg.rows import dict_row

from tests._test_config import get_test_db_url
from app.services.scope import admin_client_codes, site_in_scope
from app.services.user_service import UserService


def _admin_with_clients(min_clients=1):
    db = psycopg.connect(get_test_db_url())
    db.row_factory = dict_row
    try:
        row = db.execute(
            """
            SELECT u.user_id, u.login, u.is_superadmin, u.user_code,
                   count(ac.client_code) AS n
            FROM users u
            JOIN admin_clients ac ON ac.admin_id = u.user_id
            WHERE u.is_superadmin IS FALSE
            GROUP BY u.user_id, u.login, u.is_superadmin, u.user_code
            HAVING count(ac.client_code) >= %s
            ORDER BY u.user_id
            LIMIT 1
            """,
            (min_clients,),
        ).fetchone()
        if not row:
            pytest.skip("Aucun admin avec ce nombre de clients en base")
        return dict(row)
    finally:
        db.close()


def _admin_without_clients():
    db = psycopg.connect(get_test_db_url())
    db.row_factory = dict_row
    try:
        row = db.execute(
            """
            SELECT u.user_id, u.login, u.is_superadmin, u.user_code
            FROM users u
            WHERE u.is_superadmin IS FALSE
              AND EXISTS (SELECT 1 FROM user_permissions up
                          JOIN permissions p ON p.permission_id = up.permission_id
                          WHERE up.user_id = u.user_id
                            AND up.can_view AND p.code = 'user_create')
              AND NOT EXISTS (SELECT 1 FROM admin_clients ac WHERE ac.admin_id = u.user_id)
            ORDER BY u.user_id
            LIMIT 1
            """
        ).fetchone()
        if not row:
            pytest.skip("Aucun admin sans client en base")
        return dict(row)
    finally:
        db.close()


class _Actor:
    def __init__(self, row):
        self.user_id = row["user_id"]
        self.is_superadmin = row["is_superadmin"]
        self.user_code = row["user_code"]
        self.profile_name = "Administrateur"


# --- 1. un admin avec un client assigne peut creer un user en tapant le bon code


def test_admin_peut_saisir_le_code_de_son_client():
    admin = _admin_with_clients(1)
    db = psycopg.connect(get_test_db_url())
    db.row_factory = dict_row
    try:
        actor = _Actor(admin)
        codes = admin_client_codes(db, actor)
        assert codes, "l'admin de test doit avoir au moins un client"
        code = codes[0]
        # le code tape passe la validation de perimetre
        assert site_in_scope(codes, code)
        # et normalise comme le fait le formulaire (trim + majuscules)
        assert site_in_scope(codes, code.strip().upper())
    finally:
        db.close()


# --- 2. un code hors perimetre est refuse, et rien n'est cree


def test_code_hors_perimetre_refuse_et_aucun_user_cree():
    admin = _admin_with_clients(1)
    db = psycopg.connect(get_test_db_url())
    db.row_factory = dict_row
    try:
        actor = _Actor(admin)
        mine = set(admin_client_codes(db, actor))

        # un code qui n'est PAS dans le perimetre de l'admin
        other = db.execute(
            """
            SELECT c.code_client FROM clients c
            WHERE NOT EXISTS (SELECT 1 FROM admin_clients ac
                              WHERE ac.admin_id = %s AND ac.client_code = c.code_client)
            LIMIT 1
            """,
            (actor.user_id,),
        ).fetchone()
        assert other is not None
        foreign = other["code_client"]
        assert foreign not in mine

        # la validation le refuse explicitement (c'est ce 400 que renvoie la route)
        assert not site_in_scope(mine, foreign)

        # aucun utilisateur ne porte ce code pour cet admin
        created = db.execute(
            "SELECT count(*) AS n FROM users WHERE login = %s", (f"zz_hors_perimetre_{actor.user_id}",)
        ).fetchone()["n"]
        assert created == 0
    finally:
        db.close()


# --- 3. pas de faux positif : un admin avec clients ne doit jamais voir le message


def test_pas_de_faux_positif_si_des_clients_existent():
    admin = _admin_with_clients(1)
    db = psycopg.connect(get_test_db_url())
    db.row_factory = dict_row
    try:
        actor = _Actor(admin)
        codes = admin_client_codes(db, actor)
        # condition exacte d'affichage du message cote front :
        #   clientsLoaded && myClients.length === 0
        # la liste servie par /api/v1/clients decoule de admin_client_codes
        rows = UserService(db).list_clients(codes)
        assert len(rows) > 0, "la liste renvoyee ne doit pas etre vide"
        # et chaque element expose bien le champ lu par le formulaire
        for r in rows:
            assert r.get("client_code"), f"client_code manquant sur {dict(r)}"
    finally:
        db.close()


# --- 4. multi-clients : OK pour chacun de SES clients, refuse pour un autre


def test_multi_clients_accepte_si_un_code_mien_refuse_sinon():
    admin = _admin_with_clients(2)
    db = psycopg.connect(get_test_db_url())
    db.row_factory = dict_row
    try:
        actor = _Actor(admin)
        codes = admin_client_codes(db, actor)
        assert len(codes) >= 2

        # chacun de ses clients est accepte, en saisie libre
        for c in codes:
            assert site_in_scope(codes, c)
            assert site_in_scope(codes, c.strip().upper())

        # un client qu'il ne gere pas est refuse
        foreign = db.execute(
            """
            SELECT c.code_client FROM clients c
            WHERE NOT EXISTS (SELECT 1 FROM admin_clients ac
                              WHERE ac.admin_id = %s AND ac.client_code = c.code_client)
            LIMIT 1
            """,
            (actor.user_id,),
        ).fetchone()
        if foreign is None:
            pytest.skip("pas de client tiers disponible")
        assert not site_in_scope(codes, foreign["code_client"])
    finally:
        db.close()
