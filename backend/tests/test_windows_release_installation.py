from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from tests.windows_test_support import windows_powershell_environment


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT_ROOT = REPOSITORY_ROOT / "deploy" / "windows"
COMMIT = "b" * 40


@unittest.skipUnless(os.name == "nt", "Windows release installation requires PowerShell")
class WindowsReleaseInstallationTests(unittest.TestCase):
    def _run_powershell(self, source: str) -> subprocess.CompletedProcess[str]:
        executable = shutil.which("powershell.exe") or shutil.which("powershell")
        if executable is None:
            self.skipTest("Windows PowerShell is not available")
        encoded = base64.b64encode(source.encode("utf-16-le")).decode("ascii")
        return subprocess.run(
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=windows_powershell_environment(),
        )

    def _write_package(self, root: Path) -> tuple[Path, Path, Path]:
        files = {
            "backend/app/main.py": b"app = object()\n",
            "backend/migrations/env.py": b"# migration env\n",
            "deploy/windows/Test-MesDeployment.ps1": b"# preflight\n",
            "clients/internal/Mes.Wpf.exe": b"internal\n",
            "clients/vendor/Mes.Vendor.Wpf.exe": b"vendor\n",
        }
        manifest = {
            "format_version": 1,
            "release_type": "mes-v2-windows",
            "git": {"commit": COMMIT},
            "database": {"alembic_head": "abc"},
            "validation": {"overall_status": "OK"},
            "files": [
                {
                    "path": relative,
                    "size": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
                for relative, raw in sorted(files.items())
            ],
        }
        manifest_raw = (json.dumps(manifest, indent=2) + "\n").encode()
        package = root / "mes-v2-test.zip"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for relative, raw in files.items():
                archive.writestr(relative, raw)
            archive.writestr("release-manifest.json", manifest_raw)
        manifest_path = root / "mes-v2-test.manifest.json"
        manifest_path.write_bytes(manifest_raw)
        checksum = root / "mes-v2-test.sha256"
        checksum.write_text(
            f"{hashlib.sha256(package.read_bytes()).hexdigest()}  {package.name}\n",
            encoding="ascii",
        )
        return package, manifest_path, checksum

    def test_verified_package_install_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            package, manifest, checksum = self._write_package(root)
            release_root = root / "server"
            installer = DEPLOYMENT_ROOT / "Install-MesRelease.ps1"
            source = f"""
            & '{installer}' `
                -PackagePath '{package}' `
                -ManifestPath '{manifest}' `
                -ChecksumPath '{checksum}' `
                -ReleaseRoot '{release_root}'
            & '{installer}' `
                -PackagePath '{package}' `
                -ManifestPath '{manifest}' `
                -ChecksumPath '{checksum}' `
                -ReleaseRoot '{release_root}'
            if (-not (Test-Path -LiteralPath '{release_root / "releases" / COMMIT / "backend" / "app" / "main.py"}')) {{ exit 3 }}
            """

            result = self._run_powershell(source)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("ALREADY_STAGED", result.stdout)

    def test_tampered_package_is_rejected_before_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            package, manifest, checksum = self._write_package(root)
            package.write_bytes(package.read_bytes() + b"tampered")
            release_root = root / "server"
            installer = DEPLOYMENT_ROOT / "Install-MesRelease.ps1"
            source = f"""
            try {{
                & '{installer}' `
                    -PackagePath '{package}' `
                    -ManifestPath '{manifest}' `
                    -ChecksumPath '{checksum}' `
                    -ReleaseRoot '{release_root}'
                exit 1
            }}
            catch {{
                if ($_.Exception.Message -notlike '*SHA-256*') {{ exit 2 }}
                if (Test-Path -LiteralPath '{release_root}') {{ exit 3 }}
            }}
            """

            result = self._run_powershell(source)

            self.assertEqual(0, result.returncode, result.stderr)

    def test_failed_junction_switch_restores_previous_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "server"
            previous = root / "releases" / ("0" * 40)
            target = root / "releases" / COMMIT
            common = DEPLOYMENT_ROOT / "MesRelease.Installation.Common.ps1"
            source = f"""
            . '{common}'
            New-Item -ItemType Directory -Path '{previous}' -Force | Out-Null
            New-Item -ItemType Directory -Path '{target}' -Force | Out-Null
            New-Item -ItemType Junction -Path '{root / "current"}' -Target '{previous}' | Out-Null
            $switched = Set-MesReleaseJunction `
                -ReleaseRoot '{root}' `
                -TargetReleasePath '{target}'
            if ($switched -ne [IO.Path]::GetFullPath('{target}').TrimEnd('\')) {{ exit 5 }}
            $rolledBack = Set-MesReleaseJunction `
                -ReleaseRoot '{root}' `
                -TargetReleasePath '{previous}'
            if ($rolledBack -ne [IO.Path]::GetFullPath('{previous}').TrimEnd('\')) {{ exit 6 }}
            try {{
                $null = Set-MesReleaseJunction `
                    -ReleaseRoot '{root}' `
                    -TargetReleasePath '{target}' `
                    -InjectFailureAfterCurrentMove
                exit 1
            }}
            catch {{
                if ($_.Exception.Message -notlike 'Injected release-switch failure*') {{ exit 2 }}
            }}
            $restored = Get-MesReleaseJunctionTarget -CurrentPath '{root / "current"}'
            if ($restored -ne [IO.Path]::GetFullPath('{previous}').TrimEnd('\')) {{ exit 3 }}
            if (@(Get-ChildItem -LiteralPath '{root}' -Force | Where-Object {{ $_.Name -like '.current-*' }}).Count -ne 0) {{ exit 4 }}
            """

            result = self._run_powershell(source)

            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
