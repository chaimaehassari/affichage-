from psycopg import Connection
import psycopg
from datetime import datetime, timezone


class SettingsService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def _get(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT setting_value FROM general_settings WHERE setting_key = %s",
            (key,),
        ).fetchone()
        return row["setting_value"] if row else None

    def _set(self, key: str, value: str, description: str = "") -> None:
        row = self.conn.execute(
            "SELECT setting_id FROM general_settings WHERE setting_key = %s",
            (key,),
        ).fetchone()
        if row:
            if description:
                self.conn.execute(
                    "UPDATE general_settings SET setting_value = %s, description = %s WHERE setting_id = %s",
                    (value, description, row["setting_id"]),
                )
            else:
                self.conn.execute(
                    "UPDATE general_settings SET setting_value = %s WHERE setting_id = %s",
                    (value, row["setting_id"]),
                )
        else:
            self.conn.execute(
                "INSERT INTO general_settings (setting_key, setting_value, description) VALUES (%s, %s, %s)",
                (key, value, description),
            )

    def get_all_settings(self) -> dict:
        return {
            "license_sites": int(self._get("license_sites") or 50),
            "license_posts": int(self._get("license_posts") or 200),
            "code_client": self._get("code_client") or "DYNDISPLAY",
            "sync_auto_enabled": self._get("sync_auto_enabled") == "true",
            "sync_auto_mode": self._get("sync_auto_mode") or "txt",
            "sync_auto_schedule": self._get("sync_auto_schedule") or "realtime",
            "sync_auto_time": self._get("sync_auto_time") or "02:00",
            "media_source": self._get("media_source") or "shared",
            "media_root_path": self._get("media_root_path") or "./media_storage",
            "sync_auto_profile_id": self._get("sync_auto_profile_id") or "",
            "session_timeout_minutes": int(self._get("session_timeout_minutes") or 30),
            "affluence_start_hour": int(self._get("affluence_start_hour") or 8),
            "affluence_end_hour": int(self._get("affluence_end_hour") or 17),
            "affluence_media_threshold_mb": int(self._get("affluence_media_threshold_mb") or 20),
            "smtp_host": self._get("smtp_host") or "",
            "smtp_port": int(self._get("smtp_port") or 587),
            "smtp_user": self._get("smtp_user") or "",
            "smtp_from": self._get("smtp_from") or "",
            "app_base_url": self._get("app_base_url") or "http://localhost:5173",
        }

    def update_settings(self, data: dict) -> dict:
        mapping = {
            "code_client": ("code_client", "Code d'accès client"),
            "sync_auto_enabled": ("sync_auto_enabled", "Synchronisation automatique"),
            "sync_auto_mode": ("sync_auto_mode", "Mode de synchro auto"),
            "sync_auto_schedule": ("sync_auto_schedule", "Horaire synchro"),
            "sync_auto_time": ("sync_auto_time", "Heure de declenchement"),
            "media_source": ("media_source", "Source des medias"),
            "media_root_path": ("media_root_path", "Chemin dossier medias"),
            "sync_auto_profile_id": ("sync_auto_profile_id", "Profil FTP synchro auto"),
            "session_timeout_minutes": ("session_timeout_minutes", "Verrouillage session (minutes)"),
            "affluence_start_hour": ("affluence_start_hour", "Heure début affluence"),
            "affluence_end_hour": ("affluence_end_hour", "Heure fin affluence"),
            "affluence_media_threshold_mb": ("affluence_media_threshold_mb", "Seuil média volumineux (Mo)"),
            "smtp_host": ("smtp_host", "Serveur SMTP"),
            "smtp_port": ("smtp_port", "Port SMTP"),
            "smtp_user": ("smtp_user", "Utilisateur SMTP"),
            "smtp_password": ("smtp_password", "Mot de passe SMTP"),
            "smtp_from": ("smtp_from", "Expéditeur SMTP"),
            "app_base_url": ("app_base_url", "URL de base de l'application"),
        }
        for field, (key, desc) in mapping.items():
            val = data.get(field)
            if val is not None:
                self._set(key, str(val).lower() if isinstance(val, bool) else str(val), desc)
        return self.get_all_settings()

    def verify_client_code(self, code: str) -> bool:
        stored = self._get("code_client")
        return stored is not None and code == stored

    def get_session_timeout_minutes(self) -> int:
        """Durée d'inactivité (minutes) avant verrouillage de session."""
        value = self._get("session_timeout_minutes")
        try:
            return max(0, int(value)) if value else 0
        except (TypeError, ValueError):
            return 0

    def count_used_licenses(self) -> dict:
        site_count = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM sites WHERE is_active = TRUE"
        ).fetchone()["cnt"]
        post_count = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM posts WHERE is_active = TRUE"
        ).fetchone()["cnt"]
        return {"used_sites": site_count, "used_posts": post_count}


class FtpProfileService:
    def __init__(self, conn: Connection):
        self.conn = conn

    def list_profiles(self) -> list[dict]:
        profiles = self.conn.execute(
            "SELECT * FROM ftp_profiles WHERE is_active = TRUE"
        ).fetchall()
        return [self._to_dict(p) for p in profiles]

    def create_profile(self, data: dict) -> dict:
        try:
            row = self.conn.execute(
                """
                INSERT INTO ftp_profiles (name, server_address, port, username, password_hash,
                                          security_mode, transfer_mode, passive_connection,
                                          connection_timeout, is_anonymous, ignore_certificate_errors,
                                          is_active, is_default)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, FALSE)
                RETURNING *
                """,
                (
                    data["name"],
                    data["server_address"],
                    data.get("port", 21),
                    data.get("username"),
                    data.get("password") or None,
                    data.get("security_mode", "NONE"),
                    data.get("transfer_mode", "BINARY"),
                    data.get("passive_mode", True),
                    data.get("timeout", 30),
                    data.get("anonymous", False),
                    data.get("ignore_cert_errors", False),
                ),
            ).fetchone()
        except psycopg.errors.UniqueViolation:
            raise ValueError("Un profil FTP portant ce nom existe déjà.")
        return self._to_dict(row)

    def update_profile(self, profile_id: int, data: dict) -> dict:
        profile = self.conn.execute(
            "SELECT * FROM ftp_profiles WHERE ftp_profile_id = %s",
            (profile_id,),
        ).fetchone()
        if not profile:
            raise ValueError("Profil FTP introuvable.")

        field_map = {
            "name": "name",
            "server_address": "server_address",
            "port": "port",
            "username": "username",
            "security_mode": "security_mode",
            "transfer_mode": "transfer_mode",
            "passive_mode": "passive_connection",
            "timeout": "connection_timeout",
            "anonymous": "is_anonymous",
            "ignore_cert_errors": "ignore_certificate_errors",
        }
        updates = []
        params = []
        for api_key, col in field_map.items():
            val = data.get(api_key)
            if val is not None:
                updates.append(f"{col} = %s")
                params.append(val)
        if data.get("password") is not None:
            updates.append("password_hash = %s")
            params.append(data["password"])
        if updates:
            params.append(profile_id)
            self.conn.execute(
                f"UPDATE ftp_profiles SET {', '.join(updates)} WHERE ftp_profile_id = %s",
                params,
            )
        row = self.conn.execute(
            "SELECT * FROM ftp_profiles WHERE ftp_profile_id = %s",
            (profile_id,),
        ).fetchone()
        return self._to_dict(row)

    def delete_profile(self, profile_id: int) -> None:
        profile = self.conn.execute(
            "SELECT * FROM ftp_profiles WHERE ftp_profile_id = %s",
            (profile_id,),
        ).fetchone()
        if not profile:
            raise ValueError("Profil FTP introuvable.")
        self.conn.execute(
            "UPDATE ftp_profiles SET is_active = FALSE WHERE ftp_profile_id = %s",
            (profile_id,),
        )

    def test_connection(self, profile_id: int) -> dict:
        profile = self.conn.execute(
            "SELECT * FROM ftp_profiles WHERE ftp_profile_id = %s",
            (profile_id,),
        ).fetchone()
        if not profile:
            return {"success": False, "message": "Profil FTP introuvable."}
        password = profile["password_hash"] or ""
        timeout = profile["connection_timeout"] or 30
        anonymous = profile["is_anonymous"]
        try:
            if profile["security_mode"] in ("SFTP", "FTPES", "FTPS"):
                import paramiko
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(
                    hostname=profile["server_address"],
                    port=profile["port"] or 22,
                    username=profile["username"] or "",
                    password=password,
                    timeout=timeout,
                )
                client.close()
                return {"success": True, "message": "Connexion SFTP réussie."}
            else:
                from ftplib import FTP
                ftp = FTP()
                ftp.connect(profile["server_address"], profile["port"] or 21, timeout=timeout)
                if anonymous:
                    ftp.login()
                else:
                    ftp.login(profile["username"] or "", password)
                ftp.quit()
                return {"success": True, "message": "Connexion FTP réussie."}
        except Exception as e:
            return {"success": False, "message": f"Échec : {str(e)}"}

    def _to_dict(self, p: dict) -> dict:
        return {
            "profile_id": p["ftp_profile_id"],
            "name": p["name"],
            "server_address": p["server_address"],
            "port": p["port"] or 21,
            "username": p["username"] or "",
            "security_mode": p["security_mode"],
            "transfer_mode": p["transfer_mode"],
            "passive_mode": p["passive_connection"],
            "timeout": p["connection_timeout"] or 30,
            "is_active": p["is_active"],
            "anonymous": p["is_anonymous"],
            "ignore_cert_errors": p["ignore_certificate_errors"],
        }