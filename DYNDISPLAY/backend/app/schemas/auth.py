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
    groups: list[int] = []
    user_code: str | None = None
    is_activated: bool = True
    is_superadmin: bool = False
    sites_limit: int | None = None
    posts_limit: int | None = None
    activated_at: str | None = None
    requires_activation: bool = False
    account_code: str | None = None
    authorized_device_id: str | None = None


class ActivationRequest(BaseModel):
    code: str


class ActivateAccountRequest(BaseModel):
    login: str
    activation_code: str

    @field_validator("login")
    @classmethod
    def validate_login(cls, v):
        if not v or not v.strip():
            raise ValueError("Le login est obligatoire.")
        return v.strip()

    @field_validator("activation_code")
    @classmethod
    def validate_code(cls, v):
        if not v or not v.strip():
            raise ValueError("Le code d'activation est obligatoire.")
        return v.strip().upper()


class LoginRequest(BaseModel):
    login: str
    password: str
    client_code: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class ActivateAccountResponse(BaseModel):
    success: bool
    message: str


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
    is_superadmin: bool = False
    sites_limit: int | None = None
    posts_limit: int | None = None
    created_at: str | None = None
    client_name: str | None = None
    admin_id: int | None = None
    admin_login: str | None = None
    admin_code: str | None = None
    account_code: str | None = None
    requires_activation: bool = False
    authorized_device_id: str | None = None


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
    admin_id: int | None = None
    is_active: bool = True
    requires_activation: bool = False
    zones: list[int] = []
    groups: list[int] = []
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


class UserCreatedResponse(BaseModel):
    message: str
    success: bool = True
    user_id: int
    login: str
    user_code: str | None = None
    account_code: str | None = None
    requires_activation: bool = True


class UserUpdateRequest(BaseModel):
    user_code: str | None = None
    login: str
    email: str | None = None
    profile_id: int
    admin_id: int | None = None
    is_active: bool = True
    requires_activation: bool = False
    zones: list[int] = []
    groups: list[int] = []
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
        return v.strip()


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
    is_superadmin: bool = False
    sites_limit: int | None = None
    posts_limit: int | None = None
    activated_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    last_login_at: str | None = None
    zones: list[ZoneAccessItem] = []
    groups: list[int] = []
    permissions: list[PermissionInfo] = []
    account_code: str | None = None
    requires_activation: bool = False
    authorized_device_id: str | None = None
    admin_id: int | None = None


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


# --- V3: Hiérarchie de gestion (Super Admin / Admin / Clients) ---


class AdminClientItem(BaseModel):
    client_code: str


class AdminListItem(BaseModel):
    user_id: int
    user_code: str | None = None
    login: str
    email: str | None = None
    profile_id: int
    profile_name: str
    is_active: bool
    is_superadmin: bool = False
    client_codes: list[str] = []
    created_at: str | None = None


class AdminListResponse(BaseModel):
    admins: list[AdminListItem]
    total: int


class AdminCreateRequest(BaseModel):
    user_code: str | None = None
    login: str
    email: str | None = None
    password: str
    password_confirm: str
    is_active: bool = True
    client_codes: list[str] = []

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

    @field_validator("user_code")
    @classmethod
    def code_admin(cls, v):
        if v is not None:
            v = v.strip() or None
        return v


class AdminUpdateRequest(BaseModel):
    user_code: str | None = None
    login: str
    email: str | None = None
    is_active: bool = True
    client_codes: list[str] = []

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

    @field_validator("user_code")
    @classmethod
    def code_admin(cls, v):
        if v is not None:
            v = v.strip() or None
        return v


class ClientItem(BaseModel):
    client_id: int | None = None
    client_code: str
    client_name: str | None = None
    license_sites: int = 0
    license_posts: int = 0
    user_count: int = 0
    site_count: int = 0
    admin_login: str | None = None
    admin_code: str | None = None
    created_at: str | None = None


class ClientListResponse(BaseModel):
    clients: list[ClientItem]
    total: int


class ClientDetailResponse(ClientItem):
    activated_count: int = 0
    admins: list[dict] = []


class ClientLicenseUpdateRequest(BaseModel):
    license_sites: int
    license_posts: int

    @field_validator("license_sites", "license_posts")
    @classmethod
    def non_negative(cls, v):
        if v < 0:
            raise ValueError("Les licences doivent être positives ou nulles.")
        return v


class AdminClientAssignRequest(BaseModel):
    client_code: str

    @field_validator("client_code")
    @classmethod
    def normalize_code(cls, v):
        c = (v or "").strip().upper()
        if not c:
            raise ValueError("Le code client est obligatoire.")
        return c
