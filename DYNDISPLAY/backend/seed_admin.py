"""Seed an initial admin user into the database.

Le mot de passe du compte admin n'est JAMAIS en dur : il est lu, dans cet
ordre, depuis

  1. ``SEED_ADMIN_PASSWORD_FILE`` - chemin d'un fichier texte contenant le
     mot de passe. C'est le mode utilise par ``install.bat`` : un mot de passe
     saisi par un humain contient souvent des caracteres (``&``, ``|``, ``%``,
     ``!``, espaces) qui cassent l'affectation de variable dans un script
     .bat/cmd.exe. Passer par un fichier evite tout quoting.
  2. ``SEED_ADMIN_PASSWORD`` - variable d'environnement (dev / tests).
  3. sinon : genere aleatoirement et affiche UNE SEULE FOIS, a la creation.

Dans les trois cas le mot de passe n'est ecrit NI dans le code NI dans un
fichier du depot : c'est l'installateur qui decide de le transmettre.
"""
import secrets
import sys
import os
import string
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_deploy_env() -> None:
    """Charge le .env du dossier de DEPLOIEMENT s'il n'est pas dans le CWD.

    Dans le dossier livre, le .env est a la racine (a cote de install.bat) et
    seed_admin.py est appele depuis backend/ : sans ce chargement,
    pydantic-settings ne trouve pas le fichier et le seed echoue sur
    "JWT_SECRET_KEY n'est pas defini" alors que tout est configure.

    Recherche : ./.env (dev), puis <dossier du projet>/.env (deploiement).
    N'ecrase jamais une variable deja definie. Sans effet si rien n'est trouve.
    """
    for candidate in (os.path.join(os.getcwd(), ".env"),
                      os.path.join(os.path.dirname(_HERE), ".env")):
        if os.path.isfile(candidate):
            try:
                from dotenv import load_dotenv

                load_dotenv(candidate, override=False)
            except ImportError:
                pass
            return


_load_deploy_env()

from app.core.security import hash_password, verify_password
from app.db.database import close_db, get_connection


# Quotas du client plateforme cree/produit au premier demarrage. Un quota
# 0/0 (valeur du client 'DEFAULT' de la migration 018) rendrait l'interface
# inutilisable : aucun site ni poste ne pourrait etre cree.
PLATFORM_SITES = 100
PLATFORM_POSTS = 1000


def _sans_accents(valeur: str | None) -> str:
    """Compare des libelles sans se soucier des accents.

    La migration 018 ecrit 'Client par defaut' avec un accent ; recopier ce
    libelle en dur dans le seed rendrait la detection fragile (accent perdu a
    la lecture du .sql, ou lors d'un copier-coller). On compare donc sur la
    forme sans diacritiques.
    """
    texte = unicodedata.normalize("NFKD", valeur or "")
    return "".join(c for c in texte if not unicodedata.combining(c)).strip().lower()


def _bootstrap_password() -> tuple[str, str]:
    """Mot de passe du Super Admin : fichier, sinon env, sinon aleatoire.

    Retourne ``(mot_de_passe, origine)`` avec origine dans
    ``{"file", "env", "random"}``. L'origine sert a n'afficher le mot de
    passe QUE s'il a ete genere sur place : sinon c'est l'installateur qui
    l'affiche deja (et le superviseur qui l'a saisi).
    """
    path = os.environ.get("SEED_ADMIN_PASSWORD_FILE", "").strip()
    if path:
        if not os.path.isfile(path):
            raise SystemExit(
                f"SEED_ADMIN_PASSWORD_FILE pointe sur un fichier inexistant : {path}"
            )
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        password = lines[0].strip() if lines else ""
        if not password:
            raise SystemExit(f"Le fichier de mot de passe est vide : {path}")
        return password, "file"

    from_env = os.environ.get("SEED_ADMIN_PASSWORD", "").strip()
    if from_env:
        return from_env, "env"

    return secrets.token_urlsafe(18), "random"


def seed() -> str:
    """Cree le compte Super Admin si besoin.

    Renvoie "created" si le compte vient d'etre cree avec le mot de passe
    fourni, "exists" si le compte existait deja (mot de passe NON modifie).

    Ce retournee n'est pas un detail : install-helpers/create_admin.py s'en
    sert pour ne pas inscrire dans admin-credentials.txt un mot de passe qui
    n'a jamais ete applique. See create_admin.py.
    """
    password, origin = _bootstrap_password()
    try:
        return _seed_with_password(password, origin)
    finally:
        # Ferme le pool avant la finalisation de l'interpreteur : sinon
        # ConnectionPool.__del__ tente de joiner ses threads apres
        # l'arret du module threading et affiche un traceback sur stderr
        # pendant que l'installateur affiche "COMPTE SUPER ADMIN CREE".
        close_db()


def _seed_with_password(password, origin):
    resultat = "exists"
    with get_connection() as conn:
        try:
            # Create admin profile if it doesn't exist
            admin_profile = conn.execute(
                "SELECT * FROM profiles WHERE name = 'Administrateur'"
            ).fetchone()
            if not admin_profile:
                admin_profile = conn.execute(
                    """
                    INSERT INTO profiles (name, description, is_active)
                    VALUES ('Administrateur', 'Profil administrateur avec tous les droits', TRUE)
                    RETURNING profile_id
                    """
                ).fetchone()
                print(f"Created profile: Administrateur (id={admin_profile['profile_id']})")
            else:
                print(f"Profile Administrateur already exists (id={admin_profile['profile_id']})")

            # Create regular user profile if it doesn't exist
            user_profile = conn.execute(
                "SELECT * FROM profiles WHERE name = 'Utilisateur'"
            ).fetchone()
            if not user_profile:
                user_profile = conn.execute(
                    """
                    INSERT INTO profiles (name, description, is_active)
                    VALUES ('Utilisateur', 'Profil utilisateur standard', TRUE)
                    RETURNING profile_id
                    """
                ).fetchone()
                print(f"Created profile: Utilisateur (id={user_profile['profile_id']})")
            else:
                print(f"Profile Utilisateur already exists (id={user_profile['profile_id']})")

            # Create supervisor profile if it doesn't exist (consultation only)
            supervisor_profile = conn.execute(
                "SELECT * FROM profiles WHERE name = 'Superviseur'"
            ).fetchone()
            if not supervisor_profile:
                supervisor_profile = conn.execute(
                    """
                    INSERT INTO profiles (name, description, is_active)
                    VALUES ('Superviseur', 'Profil de supervision (consultation uniquement)', TRUE)
                    RETURNING profile_id
                    """
                ).fetchone()
                print(f"Created profile: Superviseur (id={supervisor_profile['profile_id']})")
            else:
                print(f"Profile Superviseur already exists (id={supervisor_profile['profile_id']})")

            # Create admin user if it doesn't exist
            admin_user = conn.execute(
                "SELECT * FROM users WHERE login = 'admin'"
            ).fetchone()
            if not admin_user:
                # users.client_id est NOT NULL : sans client prealable, aucune
                # connexion n'est possible sur une base vierge (deadlock de
                # bootstrap). On cree donc le client plateforme si besoin.
                bootstrap_client = conn.execute(
                    "SELECT * FROM clients ORDER BY id LIMIT 1"
                ).fetchone()
                if not bootstrap_client:
                    code = "".join(
                        secrets.choice(string.ascii_uppercase + string.digits)
                        for _ in range(8)
                    )
                    bootstrap_client = conn.execute(
                        """
                        INSERT INTO clients (code_client, nom_client, license_sites, license_posts)
                        VALUES (%s, %s, %s, %s)
                        RETURNING *
                        """,
                        (code, "Plateforme", PLATFORM_SITES, PLATFORM_POSTS),
                    ).fetchone()
                    print(
                        f"Created bootstrap client: {code} "
                        f"(id={bootstrap_client['id']}, "
                        f"quota {PLATFORM_SITES}/{PLATFORM_POSTS})"
                    )
                else:
                    # La migration 018 cree, sur une base vierge, un client
                    # 'DEFAULT' / 'Client par defaut' avec un quota 0/0 tant
                    # qu'aucun code_client n'est configure. Heriter de ce client
                    # rendrait le serveur installe INUTILISABLE (0 site, 0
                    # poste). On le promeut donc en client plateforme.
                    #
                    # Condition volontairement ETROITE : uniquement le client
                    # cree automatiquement par 018, jamais coche. Un client
                    #Configure a la main (meme nom, meme code, mais avec un
                    # quota non nul) n'est pas touche, donc relancer le seed
                    # sur une base en production ne modifie rien.
                    if (
                        (bootstrap_client["code_client"] or "").strip().upper() == "DEFAULT"
                        and _sans_accents(bootstrap_client["nom_client"])
                        == _sans_accents("Client par defaut")
                        and not bootstrap_client["license_sites"]
                        and not bootstrap_client["license_posts"]
                    ):
                        bootstrap_client = conn.execute(
                            """
                            UPDATE clients
                            SET nom_client = 'Plateforme',
                                license_sites = %s,
                                license_posts = %s
                            WHERE id = %s
                            RETURNING *
                            """,
                            (PLATFORM_SITES, PLATFORM_POSTS, bootstrap_client["id"]),
                        ).fetchone()
                        print(
                            f"Promoted auto-created default client to "
                            f"'{bootstrap_client['nom_client']}' "
                            f"(id={bootstrap_client['id']}, "
                            f"quota {PLATFORM_SITES}/{PLATFORM_POSTS})"
                        )
                    else:
                        print(
                            f"Reusing existing client: "
                            f"{bootstrap_client['code_client']} "
                            f"(id={bootstrap_client['id']})"
                        )
                admin_user = conn.execute(
                    """
                    INSERT INTO users (profile_id, login, password_hash, is_active, must_change_password, is_superadmin, requires_activation, client_id)
                    VALUES (%s, 'admin', %s, TRUE, TRUE, TRUE, FALSE, %s)
                    RETURNING user_id
                    """,
                    (admin_profile["profile_id"], hash_password(password),
                     bootstrap_client["id"]),
                ).fetchone()
                print(f"Created admin user: admin (id={admin_user['user_id']})")
                resultat = "created"
                if origin == "random":
                    # Seul cas ou le mot de passe n'a pas deja ete affiche
                    # par l'installateur : on doit donc le montrer ICI, une
                    # seule fois, car il n'est stocke que sous forme de hash.
                    print(f"  MOT DE PASSE : {password}")
                    print("  <-- a conserver EN UN SEUL exemplaire")
                else:
                    print("  mot de passe : fourni par l'installateur (non modifie)")
                print("  (ouverture de session : admin / mot de passe ci-dessus)")
                print(
                    "  must_change_password = TRUE : l'interface IMPOSE le changement\n"
                    "  du mot de passe avant tout acces (Parametres > mon compte)."
                )
            else:
                # S'assurer que le compte admin par défaut est le Super Admin
                conn.execute(
                    "UPDATE users SET is_superadmin = TRUE, requires_activation = FALSE WHERE user_id = %s",
                    (admin_user["user_id"],),
                )
                print(f"Admin user already exists (id={admin_user['user_id']}) ; mot de passe non modifié")

            conn.commit()
            print("\nSeed completed successfully.")
            return resultat
        except Exception as e:
            conn.rollback()
            print(f"Error: {e}")
            raise


# Code de sortie utilise par create_admin.py pour distinguer « cree » de
# « deja existant ». 3 est reserve a ce cas : ce n'est pas une erreur.
CODE_COMPTE_EXISTANT = 3


if __name__ == "__main__":
    sys.exit(0 if seed() == "created" else CODE_COMPTE_EXISTANT)