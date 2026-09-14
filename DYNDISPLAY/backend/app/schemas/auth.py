from pydantic import BaseModel, field_validator
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    v = v.strip().lower()
    if not EMAIL_RE.match(v):
        raise ValueError("Adresse e-mail invalide.")
    return v


class PermissionInfo(BaseModel):
    permission_id: int
    code: str
    name: str
    can_view: bool
    can_create: bool
    can_update: bool
    can_delete: bool


class UserInfo(BaseModel):
    user_id: int
    login: str
    email: str | None = None
    is_active: bool
    must_change_password: bool
    profile_name: str
    profile_id: int
    permissions: list[PermissionInfo] = []
    zones: list[int] = []
    user_code: str | None = None
    is_activated: bool = True
    sites_limit: int | None = None
    posts_limit: int | None = None
    activated_at: str | None = None


class ActivationRequest(BaseModel):
    code: str


class LoginRequest(BaseModel):
    login: str
    password: str
    client_code: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class MessageResponse(BaseModel):
    message: str


# --- V2: User CRUD ---


class UserListItem(BaseModel):
    user_id: int
    user_code: str | None = None
    login: str
    email: str | None = None
    password_masked: str = ""
    profile_id: int
    profile_name: str
    is_active: bool
    is_activated: bool = True
    sites_limit: int | None = None
    posts_limit: int | None = None
    created_at: str | None = None


class UserListResponse(BaseModel):
    users: list[UserListItem]
    total: int


class UserCreateRequest(BaseModel):
    user_code: str | None = None
    login: str
    email: str | None = None
    password: str
    password_confirm: str
    profile_id: int
    is_active: bool = True
    requires_activation: bool = False
    zones: list[int] = []
    permissions: list[dict] = []

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        return _validate_email(v)

    @field_validator("login")
    @classmethod
    def validate_login(cls, v):
        if not v or not v.strip():
            raise ValueError("Le login est obligatoire.")
        if len(v.strip()) < 2:
            raise ValueError("Le login doit contenir au moins 2 caractères.")
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v, info):
        if not v:
            raise ValueError("Le mot de passe est obligatoire.")
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

    @field_validator("password_confirm")
    @classmethod
    def validate_confirm(cls, v, info):
        data = info.data
        if "password" in data and v != data["password"]:
            raise ValueError("Les mots de passe ne correspondent pas.")
        return v


class UserUpdateRequest(BaseModel):
    user_code: str | None = None
    login: str
    email: str | None = None
    profile_id: int
    is_active: bool = True
    requires_activation: bool = False
    zones: list[int] = []
    permissions: list[dict] = []
    new_password: str | None = None
    password_confirm: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        return _validate_email(v)

    @field_validator("login")
    @classmethod
    def validate_login(cls, v):
        if not v or not v.strip():
            raise ValueError("Le login est obligatoire.")
        return v.strip()

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if v is None or v == "":
            return None
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

    @field_validator("password_confirm")
    @classmethod
    def validate_confirm(cls, v, info):
        data = info.data
        if data.get("new_password") and v != data["new_password"]:
            raise ValueError("Les mots de passe ne correspondent pas.")
        return v


class PasswordResetRequest(BaseModel):
    new_password: str
    password_confirm: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if not v:
            raise ValueError("Le mot de passe est obligatoire.")
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

    @field_validator("password_confirm")
    @classmethod
    def validate_confirm(cls, v, info):
        data = info.data
        if "new_password" in data and v != data["new_password"]:
            raise ValueError("Les mots de passe ne correspondent pas.")
        return v


class ProfileInfo(BaseModel):
    profile_id: int
    name: str
    description: str | None = None
    is_active: bool


class PermissionListItem(BaseModel):
    permission_id: int
    code: str
    name: str
    description: str | None = None
    is_active: bool


class ZoneAccessItem(BaseModel):
    zone_number: int
    is_allowed: bool


class UserDetailResponse(BaseModel):
    user_id: int
    user_code: str | None = None
    login: str
    email: str | None = None
    profile_id: int
    profile_name: str
    is_active: bool
    must_change_password: bool
    is_activated: bool = True
    sites_limit: int | None = None
    posts_limit: int | None = None
    activated_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    last_login_at: str | None = None
    zones: list[ZoneAccessItem] = []
    permissions: list[PermissionInfo] = []


class ForgotPasswordRequest(BaseModel):
    login: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    password_confirm: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if not v:
            raise ValueError("Le mot de passe est obligatoire.")
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

    @field_validator("password_confirm")
    @classmethod
    def validate_confirm(cls, v, info):
        data = info.data
        if "new_password" in data and v != data["new_password"]:
            raise ValueError("Les mots de passe ne correspondent pas.")
        return v
