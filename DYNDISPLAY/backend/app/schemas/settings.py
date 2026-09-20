import re

from pydantic import BaseModel, field_validator


class SettingsOut(BaseModel):
    license_sites: int = 50
    license_posts: int = 200
    code_client: str = "DYNDISPLAY"
    sync_auto_enabled: bool = False
    sync_auto_mode: str = "txt"
    sync_auto_schedule: str = "realtime"
    sync_auto_time: str = "02:00"
    media_source: str = "shared"
    media_root_path: str = "./media_storage"
    sync_auto_profile_id: str = ""
    session_timeout_minutes: int = 30
    affluence_start_hour: int = 8
    affluence_end_hour: int = 17
    affluence_media_threshold_mb: int = 20
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_from: str = ""
    app_base_url: str = "http://localhost:5173"


class SettingsUpdate(BaseModel):
    license_sites: int | None = None
    license_posts: int | None = None
    code_client: str | None = None
    sync_auto_enabled: bool | None = None
    sync_auto_mode: str | None = None
    sync_auto_schedule: str | None = None
    sync_auto_time: str | None = None
    media_source: str | None = None
    media_root_path: str | None = None
    sync_auto_profile_id: str | None = None
    session_timeout_minutes: int | None = None
    affluence_start_hour: int | None = None
    affluence_end_hour: int | None = None
    affluence_media_threshold_mb: int | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    app_base_url: str | None = None


class ClientCodeVerify(BaseModel):
    code: str


class AccessPasswordVerify(BaseModel):
    password: str


class ChangeAccessPasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        if not v:
            raise ValueError("Le nouveau mot de passe est obligatoire.")
        if len(v) < 8:
            raise ValueError("Le mot de passe doit contenir entre 8 et 14 caractères.")
        if len(v) > 14:
            raise ValueError("Le mot de passe doit contenir entre 8 et 14 caractères.")
        if not re.search(r'[A-Za-z]', v):
            raise ValueError("Le mot de passe doit contenir au moins une lettre.")
        if not re.search(r'\d', v):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre.")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\;\'`~]', v):
            raise ValueError("Le mot de passe doit contenir au moins un caractère spécial.")
        return v


class RegenerateClientCodeRequest(BaseModel):
    pass


class LicenseUpdateRequest(BaseModel):
    code: str
    sites: int
    posts: int


class FtpProfileCreate(BaseModel):
    name: str
    server_address: str
    port: int = 21
    username: str | None = None
    password: str = ""
    security_mode: str = "NONE"
    transfer_mode: str = "BINARY"
    passive_mode: bool = True
    timeout: int = 30
    anonymous: bool = False
    ignore_cert_errors: bool = False


class FtpProfileUpdate(BaseModel):
    name: str | None = None
    server_address: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    security_mode: str | None = None
    transfer_mode: str | None = None
    passive_mode: bool | None = None
    timeout: int | None = None
    anonymous: bool | None = None
    ignore_cert_errors: bool | None = None


class FtpProfileOut(BaseModel):
    profile_id: int
    name: str
    server_address: str
    port: int
    username: str | None
    security_mode: str
    transfer_mode: str
    passive_mode: bool
    timeout: int
    is_active: bool
    anonymous: bool
    ignore_cert_errors: bool


class FtpTestRequest(BaseModel):
    profile_id: int


class FtpTestResult(BaseModel):
    success: bool
    message: str


class AccountDeviceOut(BaseModel):
    user_id: int
    login: str
    user_code: str | None = None
    profile_name: str
    is_superadmin: bool = False
    account_code: str | None = None
    requires_activation: bool = False
    authorized_device_id: str | None = None
    activated_at: str | None = None
    created_at: str | None = None


class AccountDeviceListResponse(BaseModel):
    accounts: list[AccountDeviceOut]
    total: int
    license_posts: int
    activated_accounts: int
    available_slots: int


class RevokeDeviceRequest(BaseModel):
    pass


class RevokeDeviceResponse(BaseModel):
    success: bool
    message: str
