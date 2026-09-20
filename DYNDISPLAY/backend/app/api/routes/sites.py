import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from psycopg import Connection

from app.core.config import get_settings
from app.db.database import get_db
from app.dependencies.auth import require_permission
from app.schemas.site import (
    BatchAssignMediaRequest,
    BatchAssignResponse,
    GroupCompositionOut,
    GroupConfigApply,
    GroupConfigApplyResult,
    GroupCreate,
    GroupMembershipUpdate,
    GroupOut,
    GroupPostRequest,
    GroupUpdate,
    MediaOut,
    MessageResponse,
    PostCreate,
    PostOut,
    PostUpdate,
    SiteCreate,
    SiteOut,
    SiteUpdate,
)
from app.services.site_service import GroupService, MediaService, PostService, SiteService
from app.services.scope import client_scope, group_scope, assert_group_access, is_admin
from app.sftp.client import SFTPClient

router = APIRouter(prefix="/api/v1", tags=["Sites, Posts, Groups"])


def _site_out(site) -> SiteOut:
    return SiteOut(
        site_id=site["site_id"],
        code=site["code"],
        name=site["name"],
        address=site["address"],
        description=site["description"],
        is_active=site["is_active"],
        client_code=site.get("client_code"),
        post_count=site.get("post_count") or 0,
        created_at=site["created_at"].isoformat() if site["created_at"] else None,
        updated_at=site["updated_at"].isoformat() if site["updated_at"] else None,
    )


def _post_out(post) -> PostOut:
    return PostOut(
        post_id=post["post_id"],
        site_id=post["site_id"],
        site_name=post.get("site_name") or "",
        code=post["code"],
        name=post["name"],
        player_type=post["player_type"],
        ip_address=post["ip_address"],
        is_active=post["is_active"],
        is_online=post["is_online"],
        is_up_to_date=post["is_up_to_date"],
        last_sync_at=post["last_sync_at"].isoformat() if post["last_sync_at"] else None,
        created_at=post["created_at"].isoformat() if post["created_at"] else None,
        updated_at=post["updated_at"].isoformat() if post["updated_at"] else None,
    )


def _group_out(group, db: Connection, scope=None) -> GroupOut:
    if scope is not None and scope != "":
        from app.services.scope import scope_sql
        sql = """
            SELECT COUNT(*) AS cnt
            FROM screen_group_posts gp
            JOIN posts p ON p.post_id = gp.post_id
            JOIN sites s ON s.site_id = p.site_id
            WHERE gp.group_id = %s
        """
        params = [group["group_id"]]
        frag, args = scope_sql(scope, "s.client_code")
        if frag:
            sql += frag
        params.extend(args)
        post_count = db.execute(sql, params).fetchone()["cnt"] or 0
    else:
        post_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM screen_group_posts WHERE group_id = %s",
            (group["group_id"],),
        ).fetchone()["cnt"] or 0
    return GroupOut(
        group_id=group["group_id"],
        name=group["name"],
        description=group["description"],
        is_active=group["is_active"],
        post_count=post_count,
        created_at=group["created_at"].isoformat() if group["created_at"] else None,
        updated_at=group["updated_at"].isoformat() if group["updated_at"] else None,
    )


def _media_out(media) -> MediaOut:
    return MediaOut(
        media_id=media["media_id"],
        name=media["name"],
        original_filename=media["original_filename"],
        media_type=media["media_type"],
        mime_type=media["mime_type"],
        file_extension=media["file_extension"],
        file_size=media["file_size"],
        sftp_path=media["sftp_path"],
        page_count=media.get("page_count"),
        is_active=media["is_active"],
        client_code=media.get("client_code"),
        created_at=media["created_at"].isoformat() if media["created_at"] else None,
    )


# --- Sites ---

@router.get("/sites", response_model=list[SiteOut])
def list_sites(
    search: str | None = Query(None),
    current_user=Depends(require_permission("list_sites_posts")),
    db: Connection = Depends(get_db),
):
    service = SiteService(db)
    return [_site_out(s) for s in service.list_sites(search, client_scope(db, current_user))]


@router.post("/sites", response_model=SiteOut, status_code=201)
def create_site(
    data: SiteCreate,
    current_user=Depends(require_permission("create_site")),
    db: Connection = Depends(get_db),
):
    service = SiteService(db)
    try:
        site = service.create_site(data, admin_user_id=current_user.user_id,
                                   scope=client_scope(db, current_user))
        return _site_out(site)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sites/{site_id}", response_model=SiteOut)
def get_site(
    site_id: int,
    current_user=Depends(require_permission("list_sites_posts")),
    db: Connection = Depends(get_db),
):
    service = SiteService(db)
    site = service.get_site(site_id, client_scope(db, current_user))
    if not site:
        raise HTTPException(status_code=404, detail="Site introuvable.")
    return _site_out(site)


@router.put("/sites/{site_id}", response_model=SiteOut)
def update_site(
    site_id: int,
    data: SiteUpdate,
    current_user=Depends(require_permission("update_site")),
    db: Connection = Depends(get_db),
):
    service = SiteService(db)
    try:
        site = service.update_site(site_id, data, admin_user_id=current_user.user_id,
                                   scope=client_scope(db, current_user))
        return _site_out(site)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/sites/{site_id}", response_model=MessageResponse)
def delete_site(
    site_id: int,
    current_user=Depends(require_permission("delete_site")),
    db: Connection = Depends(get_db),
):
    service = SiteService(db)
    try:
        service.delete_site(site_id, admin_user_id=current_user.user_id,
                            scope=client_scope(db, current_user))
        return MessageResponse(message="Site supprimé avec succès.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Posts ---

@router.get("/posts", response_model=list[PostOut])
def list_posts(
    site_id: int | None = Query(None),
    search: str | None = Query(None),
    current_user=Depends(require_permission("list_sites_posts")),
    db: Connection = Depends(get_db),
):
    service = PostService(db)
    return [_post_out(p) for p in service.list_posts(site_id, search, client_scope(db, current_user))]


@router.post("/posts", response_model=PostOut, status_code=201)
def create_post(
    data: PostCreate,
    current_user=Depends(require_permission("create_post")),
    db: Connection = Depends(get_db),
):
    service = PostService(db)
    try:
        post = service.create_post(data, admin_user_id=current_user.user_id,
                                   scope=client_scope(db, current_user))
        return _post_out(post)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/posts/{post_id}", response_model=PostOut)
def get_post(
    post_id: int,
    current_user=Depends(require_permission("list_sites_posts")),
    db: Connection = Depends(get_db),
):
    service = PostService(db)
    post = service.get_post(post_id, client_scope(db, current_user))
    if not post:
        raise HTTPException(status_code=404, detail="Poste introuvable.")
    return _post_out(post)


@router.put("/posts/{post_id}", response_model=PostOut)
def update_post(
    post_id: int,
    data: PostUpdate,
    current_user=Depends(require_permission("update_post")),
    db: Connection = Depends(get_db),
):
    service = PostService(db)
    try:
        post = service.update_post(post_id, data, admin_user_id=current_user.user_id,
                                   scope=client_scope(db, current_user))
        return _post_out(post)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/posts/{post_id}", response_model=MessageResponse)
def delete_post(
    post_id: int,
    current_user=Depends(require_permission("delete_post")),
    db: Connection = Depends(get_db),
):
    service = PostService(db)
    try:
        service.delete_post(post_id, admin_user_id=current_user.user_id,
                            scope=client_scope(db, current_user))
        return MessageResponse(message="Poste supprimé avec succès.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Batch Assign Media ---

@router.post("/posts/batch-assign-media", response_model=BatchAssignResponse)
def batch_assign_media(
    data: BatchAssignMediaRequest,
    current_user=Depends(require_permission("update_post")),
    db: Connection = Depends(get_db),
):
    service = PostService(db)
    try:
        result = service.batch_assign_media(data, admin_user_id=current_user.user_id,
                                            scope=client_scope(db, current_user))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return BatchAssignResponse(**result)


# --- Groups ---

@router.get("/groups", response_model=list[GroupOut])
def list_groups(
    current_user=Depends(require_permission("list_sites_posts")),
    db: Connection = Depends(get_db),
):
    service = GroupService(db)
    allowed = group_scope(db, current_user)
    return [_group_out(g, db, client_scope(db, current_user)) for g in service.list_groups(allowed_group_ids=allowed)]


@router.post("/groups", response_model=GroupOut, status_code=201)
def create_group(
    data: GroupCreate,
    current_user=Depends(require_permission("create_site")),
    db: Connection = Depends(get_db),
):
    service = GroupService(db)
    try:
        group = service.create_group(
            data,
            admin_user_id=current_user.user_id,
            assign_to_user=None if is_admin(current_user) else current_user.user_id,
        )
        return GroupOut(
            group_id=group["group_id"],
            name=group["name"],
            description=group["description"],
            is_active=group["is_active"],
            post_count=0,
            created_at=group["created_at"].isoformat() if group["created_at"] else None,
            updated_at=group["updated_at"].isoformat() if group["updated_at"] else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/groups/{group_id}", response_model=GroupOut)
def get_group(
    group_id: int,
    current_user=Depends(require_permission("list_sites_posts")),
    db: Connection = Depends(get_db),
):
    service = GroupService(db)
    try:
        assert_group_access(db, current_user, group_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    group = service.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable.")
    return _group_out(group, db, client_scope(db, current_user))


@router.put("/groups/{group_id}", response_model=GroupOut)
def update_group(
    group_id: int,
    data: GroupUpdate,
    current_user=Depends(require_permission("update_site")),
    db: Connection = Depends(get_db),
):
    service = GroupService(db)
    try:
        assert_group_access(db, current_user, group_id)
        group = service.update_group(group_id, data, admin_user_id=current_user.user_id)
        return _group_out(group, db, client_scope(db, current_user))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/groups/{group_id}", response_model=MessageResponse)
def delete_group(
    group_id: int,
    current_user=Depends(require_permission("delete_site")),
    db: Connection = Depends(get_db),
):
    service = GroupService(db)
    try:
        assert_group_access(db, current_user, group_id)
        service.delete_group(group_id, admin_user_id=current_user.user_id)
        return MessageResponse(message="Groupe supprimé avec succès.")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Group Posts ---

@router.get("/groups/{group_id}/posts")
def get_group_posts(
    group_id: int,
    current_user=Depends(require_permission("list_sites_posts")),
    db: Connection = Depends(get_db),
):
    service = GroupService(db)
    try:
        assert_group_access(db, current_user, group_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    group = service.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable.")
    return service.get_group_posts(group_id, client_scope(db, current_user))


@router.post("/groups/{group_id}/posts", response_model=MessageResponse)
def add_posts_to_group(
    group_id: int,
    data: GroupPostRequest,
    current_user=Depends(require_permission("update_post")),
    db: Connection = Depends(get_db),
):
    service = GroupService(db)
    try:
        assert_group_access(db, current_user, group_id)
        service.add_posts_to_group(group_id, data.post_ids, admin_user_id=current_user.user_id,
                                   scope=client_scope(db, current_user))
        return MessageResponse(message="Postes ajoutés au groupe.")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/groups/{group_id}/posts", response_model=MessageResponse)
def remove_posts_from_group(
    group_id: int,
    data: GroupPostRequest,
    current_user=Depends(require_permission("update_post")),
    db: Connection = Depends(get_db),
):
    service = GroupService(db)
    try:
        assert_group_access(db, current_user, group_id)
        service.remove_posts_from_group(group_id, data.post_ids, admin_user_id=current_user.user_id,
                                        scope=client_scope(db, current_user))
        return MessageResponse(message="Postes retirés du groupe.")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Group Composition (sites -> posts) ---

@router.get("/groups/{group_id}/composition", response_model=GroupCompositionOut)
def get_group_composition(
    group_id: int,
    current_user=Depends(require_permission("list_sites_posts")),
    db: Connection = Depends(get_db),
):
    service = GroupService(db)
    try:
        assert_group_access(db, current_user, group_id)
        result = service.get_group_composition(group_id, client_scope(db, current_user))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Groupe introuvable.")
    return result


@router.put("/groups/{group_id}/membership", response_model=GroupCompositionOut)
def set_group_membership(
    group_id: int,
    data: GroupMembershipUpdate,
    current_user=Depends(require_permission("update_post")),
    db: Connection = Depends(get_db),
):
    service = GroupService(db)
    try:
        assert_group_access(db, current_user, group_id)
        return service.set_group_membership(
            group_id, data.post_ids, admin_user_id=current_user.user_id,
            scope=client_scope(db, current_user),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Apply configuration to a whole group ---

@router.post("/groups/{group_id}/apply-configuration", response_model=GroupConfigApplyResult)
def apply_group_configuration(
    group_id: int,
    data: GroupConfigApply,
    current_user=Depends(require_permission("update_post")),
    db: Connection = Depends(get_db),
):
    service = GroupService(db)
    try:
        assert_group_access(db, current_user, group_id)
        return service.apply_configuration_to_group(
            group_id, data, admin_user_id=current_user.user_id,
            scope=client_scope(db, current_user),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Media ---

@router.get("/media", response_model=list[MediaOut])
def list_media(
    media_type: str | None = Query(None),
    current_user=Depends(require_permission("menu_media")),
    db: Connection = Depends(get_db),
):
    service = MediaService(db)
    return [_media_out(m) for m in service.list_media(media_type, client_scope(db, current_user))]


@router.get("/media/{media_id}", response_model=MediaOut)
def get_media(
    media_id: int,
    current_user=Depends(require_permission("menu_media")),
    db: Connection = Depends(get_db),
):
    service = MediaService(db)
    media = service.get_media(media_id, client_scope(db, current_user))
    if not media:
        raise HTTPException(status_code=404, detail="Média introuvable.")
    return _media_out(media)


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".mp4", ".avi", ".mkv", ".mov", ".webm", ".pdf"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


@router.post("/media/upload", response_model=MediaOut, status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    current_user=Depends(require_permission("menu_media")),
    db: Connection = Depends(get_db),
):
    settings = get_settings()
    ext = Path(file.filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Extension non autorisée : {ext}. Extensions autorisées : {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux. Taille maximale : 500 Mo.")

    checksum = hashlib.sha256(content).hexdigest()

    existing = db.execute(
        """
        SELECT media_id FROM media
        WHERE checksum = %s AND client_code IS NOT DISTINCT FROM %s
        """,
        (checksum, client_scope(db, current_user)),
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Ce fichier existe déjà dans la médiathèque.")

    is_video = ext in {".mp4", ".avi", ".mkv", ".mov", ".webm"}
    is_pdf = ext == ".pdf"
    media_type = "VIDEO" if is_video else ("PDF" if is_pdf else "IMAGE")
    timestamp = int(time.time())
    safe_name = file.filename.replace(" ", "_")
    stored_name = f"{timestamp}_{safe_name}"
    page_count = None

    root = settings.SFTP_ROOT_PATH.rstrip("/")

    if is_pdf:
        media_dir = "pdfs"
        stored_remote = f"{media_dir}/{stored_name}"
        remote_path = f"{root}/{stored_remote}"

        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            page_count = len(doc)
            for page_num in range(page_count):
                page = doc[page_num]
                pix = page.get_pixmap(dpi=150)
                page_png = pix.tobytes("png")
                page_name = f"{media_dir}/{timestamp}_page_{page_num + 1}.png"
                page_path = f"{root}/{page_name}"
                with SFTPClient() as sftp:
                    sftp.upload_bytes(page_png, page_path)
            doc.close()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erreur lors de la conversion du PDF : {e}")

        try:
            with SFTPClient() as sftp:
                sftp.upload_bytes(content, remote_path)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Erreur de stockage SFTP : {e}")
    else:
        media_dir = "videos" if is_video else "images"
        stored_remote = f"{media_dir}/{stored_name}"
        remote_path = f"{root}/{stored_remote}"

        try:
            with SFTPClient() as sftp:
                sftp.upload_bytes(content, remote_path)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Erreur de stockage SFTP : {e}")

    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
        ".mp4": "video/mp4", ".avi": "video/x-msvideo", ".mkv": "video/x-matroska",
        ".mov": "video/quicktime", ".webm": "video/webm",
        ".pdf": "application/pdf",
    }

    row = db.execute(
        """
        INSERT INTO media (name, original_filename, media_type, mime_type, file_extension,
                           file_size, sftp_path, checksum, is_active, page_count, client_code)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s)
        RETURNING *
        """,
        (
            file.filename,
            file.filename,
            media_type,
            mime_map.get(ext, "application/octet-stream"),
            ext.lstrip("."),
            len(content),
            stored_remote,
            checksum,
            page_count if is_pdf else None,
            client_scope(db, current_user),
        ),
    ).fetchone()

    return _media_out(row)


@router.delete("/media/{media_id}", response_model=MessageResponse)
def delete_media(
    media_id: int,
    current_user=Depends(require_permission("menu_media")),
    db: Connection = Depends(get_db),
):
    service = MediaService(db)
    try:
        service.delete_media(media_id, admin_user_id=current_user.user_id,
                             scope=client_scope(db, current_user))
        return MessageResponse(message="Média supprimé avec succès.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))