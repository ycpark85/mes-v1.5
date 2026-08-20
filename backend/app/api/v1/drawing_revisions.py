from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Path as FPath,
    status,
    UploadFile,
    File,
    Form,
)
from uuid import uuid4
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.core.time import korea_now
from app.core.config import settings
from app.models.drawing import Drawing
from app.models.drawing_revision import DrawingRevision
from app.models.drawing_rivision_file import DrawingRevisionFile
from app.schemas.drawing_revision import (
    DrawingRevisionCreate,
    DrawingRevisionOut,
    DrawingRevisionListOut,
)
from app.schemas.drawing_revision_file import (
    DrawingRevisionFileOut,
    DrawingRevisionFileListOut,
)

router = APIRouter(prefix="/drawings", tags=["DrawingRevision"])

_filename_safe_re = re.compile(r"[^A-Za-z0-9_.()-]+")
ALLOWED_FILE_KINDS = {"DRAWING", "ORIGINAL", "PLATE"}


def _safe_filename(name: str) -> str:
    name = name.strip().replace(" ", "_")
    name = _filename_safe_re.sub("_", name)
    return name[:150] if len(name) > 150 else name


def _ext_of(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")

def _normalize_allowed_exts(values) -> set[str]:
    return {
        str(value).strip().lower().lstrip(".")
        for value in values
        if str(value).strip()
    }


def _safe_path_segment(value: str | None, fallback: str) -> str:
    name = (value or "").strip().replace(" ", "_")
    name = _filename_safe_re.sub("_", name)
    name = name.strip("._-")

    if not name or name in {".", ".."}:
        return fallback

    return name[:80]

def _ensure_valid_file_kind(file_kind: str) -> str:
    normalized = (file_kind or "").strip().upper()
    if normalized not in ALLOWED_FILE_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file_kind. allowed={sorted(ALLOWED_FILE_KINDS)}",
        )
    return normalized


def _ensure_drawing(db: Session, drawing_id: int) -> Drawing:
    drawing = db.query(Drawing).filter(Drawing.drawing_id == drawing_id).first()
    if not drawing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Drawing not found")
    return drawing


def _ensure_revision(db: Session, drawing_id: int, revision_id: int) -> DrawingRevision:
    rev = (
        db.query(DrawingRevision)
        .options(selectinload(DrawingRevision.files))
        .filter(
            DrawingRevision.revision_id == revision_id,
            DrawingRevision.drawing_id == drawing_id,
        )
        .first()
    )
    if not rev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DrawingRevision not found")
    return rev


def _make_store_dir(*, drawing_no: str, rev_no: str, file_kind: str) -> Path:
    root = Path(settings.DRAWING_STORAGE_ROOT)
    return (
        root
        / "drawings"
        / _safe_path_segment(drawing_no, "drawing")
        / _safe_path_segment(rev_no, "revision")
        / _safe_path_segment(file_kind, "file")
    )

def _save_upload_file(*, file: UploadFile, target_dir: Path) -> tuple[str, int | None, str | None]:
    ext = _ext_of(file.filename or "")
    allowed_exts = _normalize_allowed_exts(settings.DRAWING_ALLOWED_EXT)

    if not ext or ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension. allowed={sorted(allowed_exts)}",
        )

    root = Path(settings.DRAWING_STORAGE_ROOT).resolve()
    target_dir = target_dir.resolve()

    try:
        target_dir.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid storage path",
        )

    target_dir.mkdir(parents=True, exist_ok=True)

    ts = korea_now().strftime("%Y%m%d_%H%M%S")
    original = _safe_filename(file.filename or f"file.{ext}")
    final_name = f"{ts}_{uuid4().hex[:8]}_{original}"
    abs_path = target_dir / final_name

    max_bytes = settings.DRAWING_MAX_MB * 1024 * 1024
    written = 0

    with abs_path.open("wb") as f:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break

            written += len(chunk)

            if written > max_bytes:
                try:
                    abs_path.unlink(missing_ok=True)
                except Exception:
                    pass

                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large. max={settings.DRAWING_MAX_MB}MB",
                )

            f.write(chunk)

    if written <= 0:
        try:
            abs_path.unlink(missing_ok=True)
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file is not allowed",
        )

    rel_uri = str(abs_path.resolve().relative_to(root))
    return rel_uri.replace("\\", "/"), written, file.content_type


def _abs_path_from_uri(file_uri: str) -> Path:
    root = Path(settings.DRAWING_STORAGE_ROOT).resolve()
    abs_path = (root / file_uri).resolve()

    try:
        abs_path.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
        )

    return abs_path


def _remove_stored_files(file_uris: list[str]) -> None:
    """Best-effort cleanup for files that have no committed database row."""
    for file_uri in file_uris:
        try:
            _abs_path_from_uri(file_uri).unlink(missing_ok=True)
        except Exception:
            # Cleanup must not hide the original database or upload error.
            pass

# =========================================================
# 1) revision 생성 (파일 없이)
# =========================================================
@router.post(
    "/{drawing_id}/revisions",
    response_model=DrawingRevisionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_revision(
    drawing_id: int = FPath(..., ge=1),
    payload: DrawingRevisionCreate = ...,
    db: Session = Depends(get_db),
):
    drawing = _ensure_drawing(db, drawing_id)

    # legacy 호환용 file_uri는 빈 문자열 대신 placeholder 유지
    rev = DrawingRevision(
        drawing_id=drawing_id,
        rev_no=payload.rev_no.strip(),
        file_uri="",
    )

    try:
        db.add(rev)
        db.flush()

        if payload.set_as_current:
            drawing.current_revision_id = rev.revision_id

        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="rev_no already exists in this drawing",
        )

    db.refresh(rev)
    return rev


# =========================================================
# 2) legacy: 업로드 + revision 생성
#    유지하되 신규 구조도 같이 채움 (DRAWING 파일로 저장)
# =========================================================
@router.post(
    "/{drawing_id}/revisions/upload",
    response_model=DrawingRevisionOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_revision(
    drawing_id: int = FPath(..., ge=1),
    rev_no: str = Form(..., max_length=20),
    file: UploadFile = File(...),
    set_as_current: bool = Form(True),
    db: Session = Depends(get_db),
):
    drawing = _ensure_drawing(db, drawing_id)

    file_kind = "DRAWING"
    store_dir = _make_store_dir(
        drawing_no=drawing.drawing_no,
        rev_no=rev_no.strip(),
        file_kind=file_kind,
    )
    file_uri, file_size, content_type = _save_upload_file(file=file, target_dir=store_dir)

    rev = DrawingRevision(
        drawing_id=drawing_id,
        rev_no=rev_no.strip(),
        file_uri=file_uri,
    )

    try:
        db.add(rev)
        db.flush()

        file_row = DrawingRevisionFile(
            revision_id=rev.revision_id,
            file_kind=file_kind,
            file_uri=file_uri,
            original_filename=file.filename or Path(file_uri).name,
            content_type=content_type,
            file_size=file_size,
        )
        db.add(file_row)

        if set_as_current:
            drawing.current_revision_id = rev.revision_id

        db.commit()
    except IntegrityError:
        db.rollback()
        _remove_stored_files([file_uri])
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="rev_no already exists in this drawing",
        )
    except Exception:
        db.rollback()
        _remove_stored_files([file_uri])
        raise

    rev = _ensure_revision(db, drawing_id, rev.revision_id)
    return rev


@router.post(
    "/{drawing_id}/revisions/bundle",
    response_model=DrawingRevisionOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_revision_bundle(
    drawing_id: int = FPath(..., ge=1),
    rev_no: str = Form(..., max_length=20),
    set_as_current: bool = Form(True),
    drawing_file: UploadFile | None = File(None),
    original_file: UploadFile | None = File(None),
    plate_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """Create a revision and all selected files as one recoverable operation."""
    drawing = _ensure_drawing(db, drawing_id)
    normalized_rev_no = rev_no.strip()
    if not normalized_rev_no:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rev_no is required",
        )

    uploads = (
        ("DRAWING", drawing_file),
        ("ORIGINAL", original_file),
        ("PLATE", plate_file),
    )
    saved_files: list[tuple[str, str, int | None, str | None, str]] = []

    try:
        for file_kind, upload in uploads:
            if upload is None:
                continue

            store_dir = _make_store_dir(
                drawing_no=drawing.drawing_no,
                rev_no=normalized_rev_no,
                file_kind=file_kind,
            )
            file_uri, file_size, content_type = _save_upload_file(
                file=upload,
                target_dir=store_dir,
            )
            saved_files.append(
                (
                    file_kind,
                    file_uri,
                    file_size,
                    content_type,
                    upload.filename or Path(file_uri).name,
                )
            )

        drawing_uri = next(
            (file_uri for kind, file_uri, *_ in saved_files if kind == "DRAWING"),
            "",
        )
        revision = DrawingRevision(
            drawing_id=drawing_id,
            rev_no=normalized_rev_no,
            file_uri=drawing_uri,
        )
        db.add(revision)
        db.flush()

        for file_kind, file_uri, file_size, content_type, original_filename in saved_files:
            db.add(
                DrawingRevisionFile(
                    revision_id=revision.revision_id,
                    file_kind=file_kind,
                    file_uri=file_uri,
                    original_filename=original_filename,
                    content_type=content_type,
                    file_size=file_size,
                )
            )

        if set_as_current:
            drawing.current_revision_id = revision.revision_id

        db.commit()
    except IntegrityError:
        db.rollback()
        _remove_stored_files([file_uri for _, file_uri, *_ in saved_files])
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="rev_no already exists in this drawing",
        )
    except Exception:
        db.rollback()
        _remove_stored_files([file_uri for _, file_uri, *_ in saved_files])
        raise

    return _ensure_revision(db, drawing_id, revision.revision_id)


# =========================================================
# 3) revision 리스트 조회
# =========================================================
@router.get("/{drawing_id}/revisions", response_model=DrawingRevisionListOut)
def list_revisions(
    drawing_id: int = FPath(..., ge=1),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    q: str | None = Query(None),
    rev_no: str | None = Query(None),
    db: Session = Depends(get_db),
):
    _ensure_drawing(db, drawing_id)

    base = (
        db.query(DrawingRevision)
        .options(selectinload(DrawingRevision.files))
        .filter(DrawingRevision.drawing_id == drawing_id)
    )

    if rev_no:
        base = base.filter(DrawingRevision.rev_no == rev_no)

    if q:
        like = f"%{q}%"
        base = base.filter(
            (DrawingRevision.rev_no.ilike(like)) |
            (DrawingRevision.file_uri.ilike(like))
        )

    total = base.with_entities(func.count()).scalar() or 0
    items = (
        base.order_by(DrawingRevision.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {"items": items, "total": total, "page": page, "size": size}


# =========================================================
# 4) revision 파일 목록 조회
# =========================================================
@router.get(
    "/{drawing_id}/revisions/{revision_id}/files",
    response_model=DrawingRevisionFileListOut,
)
def list_revision_files(
    drawing_id: int = FPath(..., ge=1),
    revision_id: int = FPath(..., ge=1),
    db: Session = Depends(get_db),
):
    _ensure_drawing(db, drawing_id)
    _ensure_revision(db, drawing_id, revision_id)

    items = (
        db.query(DrawingRevisionFile)
        .filter(DrawingRevisionFile.revision_id == revision_id)
        .order_by(DrawingRevisionFile.created_at.asc(), DrawingRevisionFile.revision_file_id.asc())
        .all()
    )
    return {"items": items}


# =========================================================
# 5) revision 파일 업로드 (종류별 1개)
# =========================================================
@router.post(
    "/{drawing_id}/revisions/{revision_id}/files",
    response_model=DrawingRevisionFileOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_revision_file(
    drawing_id: int = FPath(..., ge=1),
    revision_id: int = FPath(..., ge=1),
    file_kind: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    drawing = _ensure_drawing(db, drawing_id)
    rev = _ensure_revision(db, drawing_id, revision_id)
    normalized_kind = _ensure_valid_file_kind(file_kind)

    existing = (
        db.query(DrawingRevisionFile)
        .filter(
            DrawingRevisionFile.revision_id == revision_id,
            DrawingRevisionFile.file_kind == normalized_kind,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{normalized_kind} file already exists",
        )

    store_dir = _make_store_dir(
        drawing_no=drawing.drawing_no,
        rev_no=rev.rev_no,
        file_kind=normalized_kind,
    )
    file_uri, file_size, content_type = _save_upload_file(file=file, target_dir=store_dir)

    obj = DrawingRevisionFile(
        revision_id=revision_id,
        file_kind=normalized_kind,
        file_uri=file_uri,
        original_filename=file.filename or Path(file_uri).name,
        content_type=content_type,
        file_size=file_size,
    )

    try:
        db.add(obj)

        # legacy 호환: DRAWING 파일이 들어오면 revision.file_uri도 동기화
        if normalized_kind == "DRAWING":
            rev.file_uri = file_uri

        db.commit()
    except IntegrityError:
        db.rollback()
        _remove_stored_files([file_uri])
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{normalized_kind} file already exists",
        )
    except Exception:
        db.rollback()
        _remove_stored_files([file_uri])
        raise

    db.refresh(obj)
    return obj


# =========================================================
# 6) revision 파일 교체
# =========================================================
@router.patch(
    "/{drawing_id}/revisions/{revision_id}/files/{file_kind}",
    response_model=DrawingRevisionFileOut,
)
def replace_revision_file_by_kind(
    drawing_id: int = FPath(..., ge=1),
    revision_id: int = FPath(..., ge=1),
    file_kind: str = FPath(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    drawing = _ensure_drawing(db, drawing_id)
    rev = _ensure_revision(db, drawing_id, revision_id)
    normalized_kind = _ensure_valid_file_kind(file_kind)

    obj = (
        db.query(DrawingRevisionFile)
        .filter(
            DrawingRevisionFile.revision_id == revision_id,
            DrawingRevisionFile.file_kind == normalized_kind,
        )
        .first()
    )
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision file not found")

    old_uri = obj.file_uri

    store_dir = _make_store_dir(
        drawing_no=drawing.drawing_no,
        rev_no=rev.rev_no,
        file_kind=normalized_kind,
    )
    new_uri, file_size, content_type = _save_upload_file(file=file, target_dir=store_dir)

    obj.file_uri = new_uri
    obj.original_filename = file.filename or Path(new_uri).name
    obj.content_type = content_type
    obj.file_size = file_size

    if normalized_kind == "DRAWING":
        rev.file_uri = new_uri

    try:
        db.commit()
    except Exception:
        db.rollback()
        _remove_stored_files([new_uri])
        raise

    db.refresh(obj)

    try:
        _abs_path_from_uri(old_uri).unlink(missing_ok=True)
    except Exception:
        pass

    return obj


# =========================================================
# 7) legacy: 기존 단일 파일 교체 API 유지
#    내부적으로 DRAWING 파일 교체로 연결
# =========================================================
@router.patch("/{drawing_id}/revisions/{revision_id}/file", response_model=DrawingRevisionOut)
def replace_revision_file_legacy(
    drawing_id: int = FPath(..., ge=1),
    revision_id: int = FPath(..., ge=1),
    file: UploadFile = File(...),
    set_as_current: bool = Form(False),
    db: Session = Depends(get_db),
):
    drawing = _ensure_drawing(db, drawing_id)
    rev = _ensure_revision(db, drawing_id, revision_id)

    obj = (
        db.query(DrawingRevisionFile)
        .filter(
            DrawingRevisionFile.revision_id == revision_id,
            DrawingRevisionFile.file_kind == "DRAWING",
        )
        .first()
    )

    store_dir = _make_store_dir(
        drawing_no=drawing.drawing_no,
        rev_no=rev.rev_no,
        file_kind="DRAWING",
    )
    new_uri, file_size, content_type = _save_upload_file(file=file, target_dir=store_dir)

    old_uri = rev.file_uri

    if obj:
        old_uri = obj.file_uri
        obj.file_uri = new_uri
        obj.original_filename = file.filename or Path(new_uri).name
        obj.content_type = content_type
        obj.file_size = file_size
    else:
        obj = DrawingRevisionFile(
            revision_id=revision_id,
            file_kind="DRAWING",
            file_uri=new_uri,
            original_filename=file.filename or Path(new_uri).name,
            content_type=content_type,
            file_size=file_size,
        )
        db.add(obj)

    rev.file_uri = new_uri

    if set_as_current:
        drawing.current_revision_id = rev.revision_id

    try:
        db.commit()
    except Exception:
        db.rollback()
        _remove_stored_files([new_uri])
        raise

    try:
        if old_uri:
            _abs_path_from_uri(old_uri).unlink(missing_ok=True)
    except Exception:
        pass

    rev = _ensure_revision(db, drawing_id, revision_id)
    return rev


# =========================================================
# 8) 최신 revision 수동 지정
# =========================================================
@router.post("/{drawing_id}/current-revision/{revision_id}", response_model=DrawingRevisionOut)
def set_current_revision(
    drawing_id: int = FPath(..., ge=1),
    revision_id: int = FPath(..., ge=1),
    db: Session = Depends(get_db),
):
    drawing = _ensure_drawing(db, drawing_id)
    rev = _ensure_revision(db, drawing_id, revision_id)

    drawing.current_revision_id = rev.revision_id
    db.commit()

    rev = _ensure_revision(db, drawing_id, revision_id)
    return rev


# =========================================================
# 9) 파일 다운로드/열기
# =========================================================
@router.get("/revision-files/{revision_file_id}/download")
def download_revision_file(
    revision_file_id: int = FPath(..., ge=1),
    db: Session = Depends(get_db),
):
    obj = (
        db.query(DrawingRevisionFile)
        .filter(DrawingRevisionFile.revision_file_id == revision_file_id)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision file not found")

    abs_path = _abs_path_from_uri(obj.file_uri)
    if not abs_path.exists() or not abs_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found")

    media_type = obj.content_type or "application/octet-stream"
    filename = obj.original_filename or abs_path.name
    db.close()

    return FileResponse(
        path=str(abs_path),
        media_type=media_type,
        filename=filename,
    )
