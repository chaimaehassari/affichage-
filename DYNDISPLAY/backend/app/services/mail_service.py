import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.services.settings_service import SettingsService


def _smtp_settings(conn):
    svc = SettingsService(conn)
    alls = svc.get_all_settings()
    username = alls.get("smtp_user") or ""
    password_setting = svc._get("smtp_password") or ""
    return {
        "host": alls.get("smtp_host") or "",
        "port": alls.get("smtp_port") or 587,
        "user": username,
        "password": password_setting,
        "sender": alls.get("smtp_from") or username,
    }


def send_reset_email(conn, to_address: str, reset_link: str) -> None:
    cfg = _smtp_settings(conn)
    if not cfg["host"]:
        raise ValueError("SMTP non configuré. Veuillez renseigner le serveur SMTP dans les paramètres.")

    subject = "Réinitialisation de votre mot de passe DynDisplay"
    body = (
        "Bonjour,\n\n"
        "Vous avez demandé la réinitialisation de votre mot de passe DynDisplay.\n\n"
        "Cliquez sur le lien ci-dessous pour choisir un nouveau mot de passe "
        "(valable 30 minutes) :\n\n"
        f"{reset_link}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.\n\n"
        "Cordialement,\nDynDisplay"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = to_address
    msg.attach(MIMEText(body, "plain", "utf-8"))

    server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=30)
    try:
        server.ehlo()
        server.starttls()
        server.ehlo()
        if cfg["user"]:
            server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["sender"], [to_address], msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass
