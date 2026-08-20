from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import UploadFile
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.api.v1.drawing_revisions import upload_revision_bundle
from app.core.config import settings
from app.db.base import Base
from app.models.drawing import Drawing
from app.models.drawing_revision import DrawingRevision
from app.models.drawing_rivision_file import DrawingRevisionFile


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, compiler, **kw):
    return "INTEGER"


class DrawingRevisionBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_storage_root = settings.DRAWING_STORAGE_ROOT
        self.original_allowed_ext = settings.DRAWING_ALLOWED_EXT
        settings.DRAWING_STORAGE_ROOT = self.temp_dir.name
        settings.DRAWING_ALLOWED_EXT = ["pdf", "ai"]

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                Base.metadata.tables["drawing"],
                Base.metadata.tables["drawing_revision"],
                Base.metadata.tables["drawing_revision_file"],
            ],
        )
        session_factory = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = session_factory()
        self.db.add(Drawing(drawing_id=1, drawing_no="DWG-001", is_active=True))
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        settings.DRAWING_STORAGE_ROOT = self.original_storage_root
        settings.DRAWING_ALLOWED_EXT = self.original_allowed_ext
        self.temp_dir.cleanup()

    @staticmethod
    def _upload(filename: str, content: bytes) -> UploadFile:
        return UploadFile(filename=filename, file=io.BytesIO(content))

    def test_bundle_commits_revision_and_all_files_together(self) -> None:
        revision = upload_revision_bundle(
            drawing_id=1,
            rev_no="A",
            set_as_current=True,
            drawing_file=self._upload("drawing.pdf", b"drawing"),
            original_file=self._upload("source.ai", b"source"),
            plate_file=None,
            db=self.db,
        )

        rows = (
            self.db.query(DrawingRevisionFile)
            .filter(DrawingRevisionFile.revision_id == revision.revision_id)
            .all()
        )
        drawing = self.db.query(Drawing).filter(Drawing.drawing_id == 1).one()

        self.assertEqual({"DRAWING", "ORIGINAL"}, {row.file_kind for row in rows})
        self.assertEqual(revision.revision_id, drawing.current_revision_id)
        self.assertTrue(all((Path(self.temp_dir.name) / row.file_uri).is_file() for row in rows))

    def test_bundle_removes_files_and_rolls_back_when_commit_fails(self) -> None:
        with patch.object(self.db, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                upload_revision_bundle(
                    drawing_id=1,
                    rev_no="B",
                    set_as_current=True,
                    drawing_file=self._upload("drawing.pdf", b"drawing"),
                    original_file=self._upload("source.ai", b"source"),
                    plate_file=None,
                    db=self.db,
                )

        self.assertEqual(0, self.db.query(DrawingRevision).count())
        stored_files = [path for path in Path(self.temp_dir.name).rglob("*") if path.is_file()]
        self.assertEqual([], stored_files)


if __name__ == "__main__":
    unittest.main()
