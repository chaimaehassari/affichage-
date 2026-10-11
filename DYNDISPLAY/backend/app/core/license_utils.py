from __future__ import annotations

import re

# Règle du code client — DOIT rester identique à celle de l'app Android
# « Licence T2F » (LicenseManager.normalizeClientCode) : 1 à 8 caractères,
# lettres A-Z et chiffres 0-9, normalisés en majuscules.
# Le code est signé tel quel dans la licence : un code hors règle produirait
# un code que l'app refuse de générer.
CLIENT_CODE_MAX_LENGTH = 8
CLIENT_CODE_PATTERN = re.compile(r"^[A-Z0-9]+$")


def normalize_client_code(value: str | None) -> str | None:
    """Normalise (trim + majuscules) et valide un code client.

    Retourne None si le code est vide, dépasse CLIENT_CODE_MAX_LENGTH
    caractères ou contient autre chose que des lettres / chiffres.
    """
    code = (value or "").strip().upper()
    if not code or len(code) > CLIENT_CODE_MAX_LENGTH:
        return None
    return code if CLIENT_CODE_PATTERN.fullmatch(code) else None