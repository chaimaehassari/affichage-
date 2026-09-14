from pydantic import BaseModel, field_validator


class MessageResponse(BaseModel):
    message: str


# --- Sites ---

class SiteCreate(BaseModel):
    code: str
    name: str
    address: str | None = None
    description: str | None = None
    is_active: bool = True
    client_code: str | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, v):
        if not v or not v.strip():
            raise ValueError("Le code est obligatoire.")
        return v.strip()


class SiteUpdate(BaseModel):
    code: str
    name: str
    address: str | None = None
    description: str | None = None
    is_active: bool = True
    client_code: str | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, v):
        if not v or not v.strip():
            raise ValueError("Le code est obligatoire.")
        return v.strip()


class SiteOut(BaseModel):
    site_id: int
    code: str
    name: str
    address: str | None = None
    description: str | None = None
    is_active: bool
    client_code: str | None = None
    post_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


# --- Posts ---

class PostCreate(BaseModel):
    site_id: int
    code: str
    name: str
    player_type: str | None = None
    ip_address: str | None = None
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def validate_code(cls, v):
        if not v or not v.strip():
            raise ValueError("Le code est obligatoire.")
        return v.strip()


class PostUpdate(BaseModel):
    site_id: int
    code: str
    name: str
    player_type: str | None = None
    ip_address: str | None = None
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def validate_code(cls, v):
        if not v or not v.strip():
            raise ValueError("Le code est obligatoire.")
        return v.strip()


class PostOut(BaseModel):
    post_id: int
    site_id: int
    site_name: str = ""
    code: str
    name: str
    player_type: str | None = None
    ip_address: str | None = None
    is_active: bool
    is_online: bool
    is_up_to_date: bool
    last_sync_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# --- Screen Groups ---

class GroupCreate(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Le nom est obligatoire.")
        return v.strip()


class GroupUpdate(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Le nom est obligatoire.")
        return v.strip()


class GroupOut(BaseModel):
    group_id: int
    name: str
    description: str | None = None
    is_active: bool
    post_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class GroupPostRequest(BaseModel):
    post_ids: list[int]


class GroupMembershipUpdate(BaseModel):
    """Remplaçe l'ensemble des postes d'un groupe de façon idempotente.

    Les postes non listés sont retirés, ceux listés sont ajoutés.
    Utilisé pour composer un groupe par site sur l'interface.
    """
    post_ids: list[int]


class GroupCompositionPost(BaseModel):
    post_id: int
    code: str
    name: str
    in_group: bool = False


class GroupCompositionSite(BaseModel):
    site_id: int
    code: str
    name: str
    posts: list[GroupCompositionPost] = []


class GroupCompositionOut(BaseModel):
    group_id: int
    name: str
    description: str | None = None
    is_active: bool
    post_count: int = 0
    sites: list[GroupCompositionSite] = []


class GroupConfigApply(BaseModel):
    """Configuration à appliquer à tous les postes d'un groupe."""
    layout_id: int | None = None
    loop_enabled: bool = True
    schedule_enabled: bool = False
    display_enabled: bool = True
    zones: list[dict] = []
    sync: bool = True


class GroupConfigApplyResult(BaseModel):
    group_id: int
    success_count: int
    failed_post_ids: list[int]
    synced_post_ids: list[int]


class GroupPostDetail(BaseModel):
    post_id: int
    code: str
    name: str
    site_id: int
    site_name: str | None = None


# --- Batch Assign ---

class BatchAssignMediaRequest(BaseModel):
    post_ids: list[int]
    media_id: int
    zone_number: int = 1


class BatchAssignResponse(BaseModel):
    success_count: int
    failed_ids: list[int]


# --- Media ---

class MediaOut(BaseModel):
    media_id: int
    name: str
    original_filename: str | None = None
    media_type: str | None = None
    mime_type: str | None = None
    file_extension: str | None = None
    file_size: int | None = None
    sftp_path: str | None = None
    page_count: int | None = None
    is_active: bool
    client_code: str | None = None
    created_at: str | None = None
