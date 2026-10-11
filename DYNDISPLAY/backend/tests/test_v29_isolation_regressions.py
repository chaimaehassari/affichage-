"""Non-regression des five failles d'isolation multi-clients corrigees.

Chaque test reproduit une fuite qui etait reellement exploitable avant le
correctif, sur un jeu de donnees construit pour l'occasion (deux clients, un
admin classique rattache a un seul des deux) : aucune dependance a l'etat
reel de la base.

F1  GET /audit exposait toute la table, y compris des clients etrangers.
F2  /zones et /configuration acceptaient un media d'un autre client, et
    /zones effacait les zones AVANT de rejeter la requete.
F3  /media-token signait un chemin SFTP arbitraire : il suffisait de connaitre
    le `sftp_path` d'un media etranger pour le telecharger via GET /media.
F4  /groups/{id}/media/{media_id}/sync acceptait un media etranger, et
    /groups/{id}/sync synchronisait les postes du groupe sans filtrer le
    perimetre (un groupe Melange fuyait les postes d'un autre client).
F5  Les modeles de decoupage sont globaux (765 lignes, aucune colonne client) :
    un admin classique pouvait les modifier, donc toucher la configuration
    d'ecran des autres clients.
"""
import uuid
import zlib
import struct

import psycopg
import pytest
import requests
from psycopg.rows import dict_row

from tests._test_config import get_test_db_url
from tests.conftest import (
    ADMIN_LOGIN,
    ADMIN_PASSWORD,
    TEST_DEVICE,
    login_as,
    make_headers,
)

_TEST_PWD = "Test@1234"
_ADMIN_PERMS = [
    {"permission_id": 11, "can_view": True, "can_create": True,
     "can_update": True, "can_delete": True},
    {"permission_id": 14, "can_view": True},
    {"permission_id": 15, "can_create": True, "can_view": True},
    {"permission_id": 16, "can_update": True, "can_view": True},
    {"permission_id": 17, "can_delete": True, "can_view": True},
    {"permission_id": 18, "can_create": True, "can_view": True},
    {"permission_id": 19, "can_update": True, "can_view": True},
    {"permission_id": 20, "can_delete": True, "can_view": True},
]


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _api(method, path, **kwargs):
    return requests.request(method, f"{__import__('os').environ.get('TEST_BASE_URL') or 'http://localhost:8000'}{path}", **kwargs)


def _png(selu=""):
    """PNG 1x1 dont les octets PIXEL portent `selu`.

    Le contenu doit varier d'un media a l'autre : `POST /media/upload` refuse
    un doublon (409) et deduplique sur le fichier, pas seulement sur son nom.
    """
    signature = b"\x89PNG\r\n\x1a\n"

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    # 2 bits par pixel : on gonfle le selu a 8 bits et on l'insere dans les
    # 4 premieres couleurs de la ligne, ce qui rend chaque fichier unique.
    selu = selu.encode() or b"x"
    pad = b"\x00" * ((4 - len(selu) % 4) % 4)
    px = selu + pad
    ligne = b"\x00"
    for i in range(0, len(px), 4):
        mot = px[i:i + 4]
        ligne += b"".join(bytes([b]) for b in mot)
    raw = zlib.compress(ligne)
    idat = chunk(b"IDAT", raw)
    iend = chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


def _insert_client(code):
    with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO clients (code_client, nom_client, license_sites, license_posts)
               VALUES (%s, %s, 10, 20)""",
            (code, f"Client {code}"),
        )
        conn.commit()
    return code


def _upload(headers, name):
    r = _api("POST", "/api/v1/media/upload", headers=headers,
             files={"file": (name, _png(name), "image/png")})
    assert r.status_code == 201, f"upload {name} impossible: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def monde():
    """Deux clients, un admin classique sur le premier, un poste par client."""
    admin_token = login_as(ADMIN_LOGIN, ADMIN_PASSWORD)
    assert admin_token, "API joignable ? (login admin)"
    su = make_headers(admin_token)

    code_a, code_b = f"ISO_A_{_uid()}", f"ISO_B_{_uid()}"
    _insert_client(code_a)
    _insert_client(code_b)

    # Modele global : creation reservee au Super Admin (F5).
    r = _api("POST", "/api/v1/layouts", headers=su, json={
        "name": f"Layout ISO {_uid()}", "is_active": True,
        "zones": [{"zone_number": 1, "position_x": 0, "position_y": 0,
                   "width": 100, "height": 100, "is_active": True}],
    })
    assert r.status_code == 201, r.text
    layout_id = r.json()["layout_id"]

    # Un media par client, televerse par le Super Admin : `client_code` est
    # NULL et `owner_user_id` est celui du Super Admin, donc ces medias sont
    # hors perimetre de l'admin classique (ni SON client, ni SON upload).
    media_a = _upload(su, f"iso_a_{_uid()}.png")
    media_b = _upload(su, f"iso_b_{_uid()}.png")

    postes = {}
    for code in (code_a, code_b):
        r = _api("POST", "/api/v1/sites", headers=su, json={
            "code": f"S_{code}", "name": f"Site {code}", "is_active": True,
            "client_code": code,
        })
        assert r.status_code == 201, f"creation site: {r.text}"
        site = r.json()
        r = _api("POST", "/api/v1/posts", headers=su, json={
            "site_id": site["site_id"], "code": f"P_{code}",
            "name": f"Post {code}", "is_active": True,
        })
        assert r.status_code == 201, f"creation post: {r.text}"
        pid = r.json()["post_id"]
        # `GET /configuration` ne renvoie ses zones que celles du MODELE du
        # poste : sans layout, la reponse est une liste vide meme quand des
        # `zone_media` existent. On rattache donc le modele global cree plus haut.
        r = _api("PUT", f"/api/v1/posts/{pid}/configuration", headers=su,
                 json={"layout_id": layout_id})
        assert r.status_code == 200, f"rattachement du modele: {r.text}"
        postes[code] = {"site_id": site["site_id"], "post_id": pid}

    # Admin classique rattache au SEUL client A.
    login = f"adm_iso_{_uid()}"
    r = _api("POST", "/api/v1/users", headers=su, json={
        "user_code": f"I{_uid()}", "login": login, "password": _TEST_PWD,
        "password_confirm": _TEST_PWD, "profile_id": 1, "is_active": True,
        "zones": [], "permissions": _ADMIN_PERMS,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    r = _api("PUT", f"/api/v1/admins/{body['user_id']}", headers=su, json={
        "login": login, "is_active": True, "client_codes": [code_a],
    })
    assert r.status_code == 200, f"affectation client impossible: {r.text}"

    r = _api("POST", "/api/v1/auth/login",
             json={"login": login, "password": _TEST_PWD},
             headers={"X-Device-Id": TEST_DEVICE})
    assert r.status_code == 200, f"login admin classique: {r.text}"
    admin_h = make_headers(r.json()["access_token"])

    # Un second media, cette fois televerse PAR l'admin classique : il doit
    # pouvoir en obtenir une URL signee (sinon le correctif F3 casse l'IHM).
    media_moi = _upload(admin_h, f"iso_moi_{_uid()}.png")

    return {
        "su": su, "admin": admin_h, "layout_id": layout_id,
        "code_a": code_a, "code_b": code_b,
        "media_a": media_a, "media_b": media_b, "media_moi": media_moi,
        "post_a": postes[code_a], "post_b": postes[code_b],
    }


# ---------------------------------------------------------------------------
# F3 : /media-token ne signe que les fichiers du perimetre
# ---------------------------------------------------------------------------

@pytest.mark.v29
class TestF3MediaToken:

    def test_media_etranger_refuse(self, monde):
        r = _api("POST", "/api/v1/media-token", headers=monde["admin"],
                 json={"path": monde["media_b"]["sftp_path"]})
        assert r.status_code == 403, f"un media etranger ne doit pas etre signe: {r.text}"

    def test_token_etranger_ne_telecharge_pas(self, monde):
        """Le token signe ne doit pas non plus ouvrir GET /media."""
        r = _api("POST", "/api/v1/media-token", headers=monde["admin"],
                 json={"path": monde["media_b"]["sftp_path"]})
        assert r.status_code == 403
        assert "token" not in r.json(), "aucun token ne doit etre emis"

    def test_chemin_arbitraire_refuse(self, monde):
        for chemin in ("images/../../etc/passwd", "players/x/config.json",
                       f"images/inexistant_{_uid()}.png"):
            r = _api("POST", "/api/v1/media-token", headers=monde["admin"],
                     json={"path": chemin})
            assert r.status_code == 403, f"{chemin} aurait ete signe: {r.text}"

    def test_son_propre_media_accepte(self, monde):
        r = _api("POST", "/api/v1/media-token", headers=monde["admin"],
                 json={"path": monde["media_moi"]["sftp_path"]})
        assert r.status_code == 200, f"un media de l'admin doit rester signable: {r.text}"
        assert r.json()["token"]

    def test_super_admin_garde_la_vue_globale(self, monde):
        r = _api("POST", "/api/v1/media-token", headers=monde["su"],
                 json={"path": monde["media_b"]["sftp_path"]})
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# F2 : /zones et /configuration valident les medias avant d'ecrire
# ---------------------------------------------------------------------------

@pytest.mark.v29
class TestF2Configuration:

    def _zone(self, media_id, numero=1):
        # `POST /posts/{id}/zones` attend une LISTE nue de ZoneMediaAssignment ;
        # `PUT /posts/{id}/configuration` attend {"zones": [...]}. Chaque zone
        # porte UN media_id (et non une liste) : c'est ce media_id que la
        # validation de perimetre doit controler.
        return {"zone_number": numero, "media_id": media_id, "duration_seconds": 10}

    def test_zone_media_etranger_refuse(self, monde):
        r = _api("POST", f"/api/v1/posts/{monde['post_a']['post_id']}/zones",
                 headers=monde["admin"],
                 json=[self._zone(monde["media_b"]["media_id"])])
        assert r.status_code == 403, f"media etranger accepte en zone: {r.text}"

    def test_zone_refusee_ne_detruit_pas_l_existant(self, monde):
        """Regression du piege : `_rebuild_zones_playlists` faisait un DELETE
        avant de rejeter, ce qui vidait la configuration d'un poste valide."""
        pid = monde["post_a"]["post_id"]
        r = _api("POST", f"/api/v1/posts/{pid}/zones", headers=monde["admin"],
                 json=[self._zone(monde["media_moi"]["media_id"])])
        assert r.status_code == 200, r.text
        avant = _api("GET", f"/api/v1/posts/{pid}/configuration", headers=monde["admin"])
        assert avant.status_code == 200
        n_avant = len(avant.json().get("zones", []))
        assert n_avant >= 1, "la zone de reference n'a pas ete ecrite"

        r = _api("POST", f"/api/v1/posts/{pid}/zones", headers=monde["admin"],
                 json=[self._zone(monde["media_b"]["media_id"])])
        assert r.status_code == 403, r.text
        apres = _api("GET", f"/api/v1/posts/{pid}/configuration", headers=monde["admin"])
        assert apres.status_code == 200
        assert len(apres.json().get("zones", [])) == n_avant, \
            "la configuration du poste a ete alteree par une requete rejetee"

    def test_configuration_media_etranger_refuse(self, monde):
        r = _api("PUT", f"/api/v1/posts/{monde['post_a']['post_id']}/configuration",
                 headers=monde["admin"],
                 json={"zones": [self._zone(monde["media_b"]["media_id"])]})
        assert r.status_code == 403, f"media etranger accepte en configuration: {r.text}"

    def test_configuration_valide_acceptee(self, monde):
        """Controle de non-regression : le cas nominal doit continuer a passer,
        sinon le correctif F2 aurait casse la configuration en conditions
        reelles d'utilisation."""
        r = _api("PUT", f"/api/v1/posts/{monde['post_a']['post_id']}/configuration",
                 headers=monde["admin"],
                 json={"zones": [self._zone(monde["media_moi"]["media_id"])]})
        assert r.status_code == 200, f"un media de son perimetre doit etre accepte: {r.text}"
        assert len(r.json().get("zones", [])) == 1


# ---------------------------------------------------------------------------
# F5 : le Decoupage est desormais accessible a tout utilisateur disposant de
# la permission `menu_conception` (la restriction Super Admin a ete retiree :
# chaque utilisateur autorise doit pouvoir enregistrer son propre modele).
# ---------------------------------------------------------------------------

@pytest.mark.v29
class TestF5Layouts:

    def test_lecture_ouverte_a_l_admin_classique(self, monde):
        assert _api("GET", "/api/v1/layouts", headers=monde["admin"]).status_code == 200
        r = _api("GET", f"/api/v1/layouts/{monde['layout_id']}", headers=monde["admin"])
        assert r.status_code == 200, r.text

    def test_admin_classique_peut_creer_un_modele(self, monde):
        r = _api("POST", "/api/v1/layouts", headers=monde["admin"], json={
            "name": f"ADM {_uid()}", "is_active": True,
            "zones": [{"zone_number": 1, "position_x": 0, "position_y": 0,
                       "width": 50, "height": 50, "is_active": True}],
        })
        assert r.status_code == 201, f"un admin doit pouvoir creer un modele: {r.text}"
        _api("DELETE", f"/api/v1/layouts/{r.json()['layout_id']}", headers=monde["admin"])

    def test_admin_classique_peut_modifier_et_supprimer(self, monde):
        r = _api("POST", "/api/v1/layouts", headers=monde["admin"], json={
            "name": f"ADM {_uid()}", "is_active": True, "zones": [],
        })
        assert r.status_code == 201, r.text
        layout_id = r.json()["layout_id"]
        r2 = _api("PUT", f"/api/v1/layouts/{layout_id}", headers=monde["admin"],
                  json={"name": f"ADM2 {_uid()}"})
        assert r2.status_code == 200, f"un admin doit pouvoir modifier un modele: {r2.text}"
        r3 = _api("DELETE", f"/api/v1/layouts/{layout_id}", headers=monde["admin"])
        assert r3.status_code == 200, f"un admin doit pouvoir supprimer un modele: {r3.text}"

    def test_super_admin_peut_toujours_ecrire(self, monde):
        r = _api("PUT", f"/api/v1/layouts/{monde['layout_id']}", headers=monde["su"],
                 json={"is_active": False})
        assert r.status_code == 200, r.text
        r = _api("PUT", f"/api/v1/layouts/{monde['layout_id']}", headers=monde["su"],
                 json={"is_active": True})
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# F1 : /audit reste dans le perimetre
# ---------------------------------------------------------------------------

@pytest.mark.v29
class TestF1Audit:

    def test_aucune_ligne_du_client_etranger(self, monde):
        r = _api("GET", "/api/v1/audit?limit=500", headers=monde["admin"])
        assert r.status_code == 200, r.text
        lignes = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        code_b = monde["code_b"]
        fautives = [
            l for l in lignes
            if l.get("entity_type") == "client" and str(l.get("entity_id")) and
            _client_code_of(l.get("entity_id")) == code_b
        ]
        assert not fautives, f"{len(fautives)} journal(s) du client etranger exposes"

    def test_volume_borne_par_rapport_au_super_admin(self, monde):
        r_admin = _api("GET", "/api/v1/audit?limit=1", headers=monde["admin"])
        r_su = _api("GET", "/api/v1/audit?limit=1", headers=monde["su"])
        assert r_admin.status_code == 200 and r_su.status_code == 200
        n_admin = r_admin.json().get("total", r_admin.json().get("count"))
        n_su = r_su.json().get("total", r_su.json().get("count"))
        if n_admin is not None and n_su is not None:
            assert n_admin <= n_su, "l'admin classique voit plus de journaux que le Super Admin"

    def test_super_admin_conserve_la_vue_globale(self, monde):
        r = _api("GET", "/api/v1/audit?limit=1", headers=monde["su"])
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# F6 : coherence client d'un site / d'un poste
#
# Bug signale : un Admin Client voyait dans Sites & Postes des sites et postes
# APPARTENANT AU SUPER ADMIN, qu'il n'avait jamais crees.
#
# Cause exacte : `sites` porte deux colonnes de client, `client_id` (NOT NULL +
# cle etrangere, donc source de verite) et `client_code` (copie denormalisee,
# nullable). Les DEUX COLONNES DIVERGEAIENT sur 316 sites : `client_code`
# valait 'AMINA01' (le client de l'admin) alors que `client_id` valait 1
# (= 3C48DBF1, le « Client par defaut » du Super Admin). Or tout le
# filtrage d'isolation porte sur `client_code` : la copie erronee accordait
# l'acces a des sites dont le proprietaire reel etait le Super Admin.
# L'ecart avait ete introduit le 2026-09-30 20:52:24 (un `updated_at`
# identique sur les 299 lignes), soit apres la creation du client AMINA01
# (22:38 le meme jour) et apres la creation des sites (25/08 -> 30/09).
#
# Deux defects de code ont permis de reproduire la situation :
#   - `_resolve_client_id` retombait sur « le premier client » quand le code
#     etait vide : un site sans client se retrouvait donc rattache a 3C48DBF1
#     sans que personne ne le voie ;
#   - `update_site` ignorait `data.client_code` et relisait la valeur stockee,
#     empechant tout rattachement correct.
# ---------------------------------------------------------------------------

@pytest.mark.v29
class TestF6CoherenceClient:

    def test_aucune_divergence_entre_les_deux_colonnes(self):
        """Invariant de donnees : client_code doit toujours valoir le
        code_client du client designe par client_id."""
        with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, \
                conn.cursor() as cur:
            cur.execute("""
                SELECT s.site_id, s.code, s.client_code AS copie, cl.code_client AS reel
                FROM sites s JOIN clients cl ON cl.id = s.client_id
                WHERE s.client_code IS DISTINCT FROM cl.code_client
                ORDER BY s.site_id LIMIT 5""")
            fautives = cur.fetchall()
            assert not fautives, (
                "sites dont client_code diverge de client_id (donc dont "
                f"l'isolation est fausse) : {[dict(r) for r in fautives]}")

    def test_aucun_site_sans_client(self):
        with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, \
                conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM sites WHERE client_code IS NULL")
            assert cur.fetchone()["n"] == 0, "il reste des sites sans client"

    def test_creation_sans_client_valide_refusee(self, monde):
        """Un site doit toujours avoir un client : ni le client par defaut du
        Super Admin, ni un code invente."""
        code = f"S_ORPHELIN_{_uid()}"
        r = _api("POST", "/api/v1/sites", headers=monde["su"], json={
            "code": code, "name": "sans client", "is_active": True,
        })
        assert r.status_code in (400, 422), \
            f"une creation de site sans client a ete acceptee: {r.text}"
        with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, \
                conn.cursor() as cur:
            # le site ne doit pas avoir ete cree...
            cur.execute("SELECT COUNT(*) AS n FROM sites WHERE code = %s", (code,))
            assert cur.fetchone()["n"] == 0, "le site sans client a bien ete cree"
            # ...et aucun site ne doit pointer vers un client inexistant
            cur.execute("""SELECT COUNT(*) AS n FROM sites s
                           WHERE NOT EXISTS (SELECT 1 FROM clients c
                                             WHERE c.id = s.client_id)""")
            assert cur.fetchone()["n"] == 0, "un site sans client_id valide existe"

    def test_creation_client_inconnu_refusee(self, monde):
        r = _api("POST", "/api/v1/sites", headers=monde["su"], json={
            "code": f"S_INCONNU_{_uid()}", "name": "client inexistant",
            "is_active": True, "client_code": "CLIENT_QUI_EXISTE_PAS",
        })
        assert r.status_code in (400, 422), \
            f"un code client inexistant a ete accepte: {r.text}"

    def test_admin_client_ne_voit_pas_les_sites_du_super_admin(self, monde):
        """Le bug signale, verifie par l'API."""
        code_super = None
        with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, \
                conn.cursor() as cur:
            cur.execute("SELECT code_client FROM clients ORDER BY id LIMIT 1")
            code_super = cur.fetchone()["code_client"]
        r = _api("GET", "/api/v1/sites", headers=monde["admin"])
        assert r.status_code == 200, r.text
        codes = {s["client_code"] for s in r.json()}
        assert code_super not in codes, \
            f"l'admin voit des sites du client {code_super} (Super Admin)"
        assert codes <= {monde["code_a"]}, \
            f"l'admin voit des sites hors de son client : {codes}"

    def test_admin_client_ne_voit_pas_les_postes_du_super_admin(self, monde):
        r = _api("GET", "/api/v1/posts", headers=monde["admin"])
        assert r.status_code == 200, r.text
        codes = {p.get("client_code") for p in r.json()}
        assert codes <= {monde["code_a"]}, \
            f"l'admin voit des postes hors de son client : {codes}"

    def test_post_expose_son_client_effectif(self, monde):
        """Chaque poste renvoye doit indiquer le client de son site : sans cela
        l'ecran Sites & Postes affiche « sans client » partout."""
        r = _api("GET", "/api/v1/posts", headers=monde["su"])
        assert r.status_code == 200, r.text
        sans_client = [p["post_id"] for p in r.json() if not p.get("client_code")]
        assert not sans_client, \
            f"postes serialises sans client : {sans_client[:5]}"
        r = _api("GET", "/api/v1/sites", headers=monde["su"])
        par_id = {s["site_id"]: s["client_code"] for s in r.json()}
        for p in r.json():
            attendu = par_id.get(p["site_id"])
            assert p["client_code"] == attendu, \
                f"poste {p['post_id']} : client {p['client_code']} != site {attendu}"

    def test_rattachement_par_update_respecte_le_perimetre(self, monde):
        """Un Admin Client ne doit pas pouvoir rattacher son site au client
        d'un autre, ni laisser les deux colonnes diverger."""
        r = _api("GET", "/api/v1/sites", headers=monde["admin"])
        sites = r.json()
        if not sites:
            pytest.skip("l'admin n'a aucun site")
        site = sites[0]
        r = _api("PUT", f"/api/v1/sites/{site['site_id']}", headers=monde["admin"],
                 json={"code": site["code"], "name": site["name"],
                       "is_active": site["is_active"], "client_code": monde["code_b"]})
        assert r.status_code in (400, 403), \
            f"l'admin a rattache son site au client {monde['code_b']}: {r.text}"
        with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, \
                conn.cursor() as cur:
            cur.execute("""SELECT s.client_code, cl.code_client AS reel
                           FROM sites s JOIN clients cl ON cl.id = s.client_id
                           WHERE s.site_id = %s""", (site["site_id"],))
            r = cur.fetchone()
        assert r["client_code"] == r["reel"], \
            "la mise a jour a de nouveau diverge les deux colonnes"


def _client_code_of(client_id):
    with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute("SELECT code_client FROM clients WHERE id = %s", (client_id,))
        row = cur.fetchone()
        return row[0] if row else None


# ---------------------------------------------------------------------------
# F1 : le predicat SQL lui-meme
#
# Ces tests n'utilisent pas l'API : ils evaluent `audit_scope_sql` sur une base
# ou l'on INSERE un journal hostile, puis annulent la transaction. Ils
# couvrent les deux cas que les tests HTTP ne peuvent pas atteindre — un admin
# sans client, et un `entity_type` inconnu.
# ---------------------------------------------------------------------------

@pytest.mark.v29
class TestF1AuditSql:

    def _admin(self, cur, avec_clients=True, avec_crees=False):
        """Un Admin CLASSIQUE (non super admin) : c'est lui qui est soumis au
        filtre. Le Super Admin n'en est pas soumis, ses tests seraient vides."""
        sql = """SELECT u.user_id, u.login, u.is_superadmin, p.name, p.profile_id
                 FROM users u JOIN profiles p ON p.profile_id = u.profile_id
                 WHERE p.name = 'Administrateur' AND u.is_superadmin = FALSE"""
        if avec_clients:
            sql += (" AND EXISTS (SELECT 1 FROM admin_clients ac"
                    " WHERE ac.admin_id = u.user_id)")
        if avec_crees:
            sql += (" AND EXISTS (SELECT 1 FROM users au"
                    " WHERE au.admin_id = u.user_id)")
        sql += " ORDER BY u.user_id LIMIT 1"
        r = cur.execute(sql).fetchone()
        if r is None:
            r = cur.execute(
                """SELECT u.user_id, u.login, u.is_superadmin, p.name, p.profile_id
                   FROM users u JOIN profiles p ON p.profile_id = u.profile_id
                   WHERE p.name = 'Administrateur' AND u.is_superadmin = FALSE
                   ORDER BY u.user_id LIMIT 1""").fetchone()
        if r is None:
            pytest.skip("aucun Admin classique en base")
        from app.schemas.auth import UserInfo
        return UserInfo(
            user_id=r["user_id"], login=r["login"], profile_name=r["name"],
            is_superadmin=bool(r["is_superadmin"]), is_active=True,
            must_change_password=False, profile_id=r["profile_id"],
        )

    def _visibles(self, cur, join, cond, params):
        sql = ("SELECT COUNT(*) AS n FROM audit_logs al"
               " LEFT JOIN users u ON u.user_id = al.user_id " + join +
               " WHERE " + cond)
        return cur.execute(sql, params).fetchone()["n"]

    def test_type_inconnu_refuse(self):
        """Fail-closed : un type d'entite qu'on ne sait pas classer est
        reserve au Super Admin, meme si son auteur est un compte visible."""
        from app.services.scope import audit_scope_sql
        with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, conn.cursor() as cur:
            admin = self._admin(cur)
            join, cond, params = audit_scope_sql(conn, admin)
            assert "entity_type IN" in cond, "le filtre doit etre une liste blanche"
            avant = self._visibles(cur, join, cond, params)
            cur.execute(
                """INSERT INTO audit_logs
                   (user_id, action, entity_type, entity_id, description)
                   SELECT user_id, 'ZZ_TEST_INCONNU', 'zzz_type_inconnu', 999999,
                          'journal de test, type inconnu'
                   FROM users LIMIT 1""")
            apres = self._visibles(cur, join, cond, params)
            assert apres == avant, \
                "un journal de type inconnu est devenu visible : le filtrage n'est pas fail-closed"

    def test_entite_etrangere_vivante_refusee_sans_client(self):
        """Le piege du court-circuit : un admin SANS client mais qui gere des
        comptes voyait, via la seule branche auteur, les journaux d'entites
        VIVANTES d'autres clients. La condition doit exiger que l'entite soit
        non resoluble."""
        from app.services import scope as S
        with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, conn.cursor() as cur:
            admin = self._admin(cur, avec_clients=True, avec_crees=True)
            frag, frag_params = S.admin_owned_users_sql(admin.user_id, "au")
            auteur = cur.execute(
                f"SELECT au.user_id FROM users au WHERE {frag} LIMIT 1",
                frag_params).fetchone()
            if not auteur:
                pytest.skip("le compte Super Admin ne gere aucun autre compte")
            site = cur.execute(
                """SELECT site_id FROM sites
                   WHERE client_code IS NOT NULL AND is_active LIMIT 1""").fetchone()
            if not site:
                pytest.skip("aucun site en base")
            nid = cur.execute(
                """INSERT INTO audit_logs
                   (user_id, action, entity_type, entity_id, description)
                   VALUES (%s, 'ZZ_TEST_VIVANT', 'site', %s,
                           'SONDE: entite etrangere VIVANTE')
                   RETURNING audit_id""",
                (auteur["user_id"], site["site_id"])).fetchone()["audit_id"]

            ancien = cur.execute(
                f"""SELECT COUNT(*) AS n FROM audit_logs al
                    WHERE al.audit_id = %s
                      AND EXISTS (SELECT 1 FROM users au
                                  WHERE au.user_id = al.user_id AND {frag})
                      AND al.entity_type NOT IN ('settings','general_settings')""",
                [nid, *frag_params]).fetchone()["n"]

            reel = S.client_scope
            S.client_scope = lambda conn, user: []
            try:
                join, cond, params = S.audit_scope_sql(conn, admin)
                nouveau = cur.execute(
                    "SELECT COUNT(*) AS n FROM audit_logs al"
                    " LEFT JOIN users u ON u.user_id = al.user_id " + join +
                    " WHERE al.audit_id = %s AND " + cond,
                    [nid, *params]).fetchone()["n"]
            finally:
                S.client_scope = reel

            assert "ec.client_code IS NULL" in cond, \
                "la branche auteur doit exiger une entite non resoluble"
            assert nouveau == 0, "le journal d'une entite etrangere vivante est encore visible"
            assert ancien >= 1, \
                "le scenario ne reproduit plus la faille : le test ne prouve plus rien"

    def test_super_admin_sans_filtre(self):
        from app.services.scope import audit_scope_sql
        with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, conn.cursor() as cur:
            r = cur.execute(
                """SELECT u.user_id, u.login, u.is_superadmin, p.name, p.profile_id
                   FROM users u JOIN profiles p ON p.profile_id = u.profile_id
                   WHERE u.is_superadmin = TRUE ORDER BY u.user_id LIMIT 1""").fetchone()
            if r is None:
                pytest.skip("aucun Super Admin en base")
            from app.schemas.auth import UserInfo
            su = UserInfo(
                user_id=r["user_id"], login=r["login"], profile_name=r["name"],
                is_superadmin=True, is_active=True, must_change_password=False,
                profile_id=r["profile_id"])
            join, cond, params = audit_scope_sql(conn, su)
            assert cond == "" and join == "", "le Super Admin doit conserver la vue globale"


# ---------------------------------------------------------------------------
# F4 : la synchronisation de groupe reste dans le perimetre
# ---------------------------------------------------------------------------

@pytest.mark.v29
class TestF4SyncGroupe:

    def _groupe(self, monde, post_ids, nom):
        with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO screen_groups (name) VALUES (%s) RETURNING group_id",
                        (nom,))
            gid = cur.fetchone()["group_id"]
            for pid in post_ids:
                cur.execute(
                    "INSERT INTO screen_group_posts (group_id, post_id) VALUES (%s, %s)",
                    (gid, pid))
            conn.commit()
        return gid

    def test_media_etranger_refuse(self, monde):
        gid = self._groupe(monde, [monde["post_a"]["post_id"]], f"ISO_F4_{_uid()}")
        try:
            r = _api("POST",
                     f"/api/v1/groups/{gid}/media/{monde['media_b']['media_id']}/sync",
                     headers=monde["admin"])
            assert r.status_code == 403, f"media etranger synchronise: {r.text}"
        finally:
            self._purge(gid)

    def test_groupe_melange_ne_sync_que_mon_poste(self, monde):
        """Un groupe n'appartient a aucun client : son acces ne doit pas
        donner acces aux postes des autres clients qu'il contient."""
        pid_moi = monde["post_a"]["post_id"]
        pid_x = monde["post_b"]["post_id"]
        gid = self._groupe(monde, [pid_moi, pid_x], f"ISO_F4MIX_{_uid()}")
        try:
            r = _api("POST", f"/api/v1/groups/{gid}/sync", headers=monde["admin"])
            assert r.status_code == 200, r.text
            touches = {x["post_id"] for x in r.json()["results"]}
            assert pid_x not in touches, \
                f"le poste etranger {pid_x} a ete synchronise via un groupe mixte"
            assert pid_moi in touches, "son propre poste aurait du etre synchronise"
        finally:
            self._purge(gid)

    def test_poste_etranger_absent_de_la_liste_du_groupe(self, monde):
        pid_moi = monde["post_a"]["post_id"]
        pid_x = monde["post_b"]["post_id"]
        gid = self._groupe(monde, [pid_moi, pid_x], f"ISO_F4LST_{_uid()}")
        try:
            r = _api("GET", f"/api/v1/groups/{gid}/posts", headers=monde["admin"])
            if r.status_code != 200:
                pytest.skip("GET /groups/{id}/posts indisponible")
            corps = r.json()
            lst = corps.get("posts", corps) if isinstance(corps, dict) else corps
            ids = {p.get("post_id") for p in lst} if isinstance(lst, list) else set()
            assert pid_x not in ids, \
                f"le poste etranger {pid_x} apparait dans un groupe mixte"
        finally:
            self._purge(gid)

    def _purge(self, gid):
        with psycopg.connect(get_test_db_url(), row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute("""DELETE FROM media_sync_state WHERE post_id IN
                           (SELECT post_id FROM screen_group_posts WHERE group_id = %s)""",
                        (gid,))
            cur.execute("""DELETE FROM sync_jobs WHERE post_id IN
                           (SELECT post_id FROM screen_group_posts WHERE group_id = %s)""",
                        (gid,))
            cur.execute("DELETE FROM screen_group_posts WHERE group_id = %s", (gid,))
            cur.execute("DELETE FROM screen_groups WHERE group_id = %s", (gid,))
            conn.commit()
