from __future__ import annotations

import base64
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tests.windows_test_support import windows_powershell_environment


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT_ROOT = REPOSITORY_ROOT / "deploy" / "windows"


@unittest.skipUnless(os.name == "nt", "Windows deployment scripts require PowerShell")
class WindowsDeploymentScriptTests(unittest.TestCase):
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

    def test_all_deployment_scripts_parse_without_errors(self) -> None:
        source = f"""
        $failed = $false
        Get-ChildItem -LiteralPath '{DEPLOYMENT_ROOT}' -Filter '*.ps1' | ForEach-Object {{
            $tokens = $null
            $parseErrors = $null
            [void][System.Management.Automation.Language.Parser]::ParseFile(
                $_.FullName,
                [ref]$tokens,
                [ref]$parseErrors
            )
            if ($parseErrors.Count -gt 0) {{
                $failed = $true
                $parseErrors | ForEach-Object {{ Write-Error $_.Message }}
            }}
        }}
        if ($failed) {{ exit 1 }}
        """
        result = self._run_powershell(source)

        self.assertEqual(0, result.returncode, result.stderr)

    def test_example_config_loads_and_contains_no_secret_fields(self) -> None:
        common = DEPLOYMENT_ROOT / "MesDeployment.Common.ps1"
        config = DEPLOYMENT_ROOT / "mes-deployment.example.psd1"
        source = f"""
        . '{common}'
        $config = Import-MesDeploymentConfig -ConfigFile '{config}'
        if ($config.Keys | Where-Object {{ $_ -match '(?i)password|secret|databaseurl|token' }}) {{
            exit 1
        }}
        if ((Quote-MesTaskArgument 'C:\\MES Path\\file.ps1') -ne '"C:\\MES Path\\file.ps1"') {{
            exit 2
        }}
        """
        result = self._run_powershell(source)

        self.assertEqual(0, result.returncode, result.stderr)

    def test_native_stderr_with_zero_exit_code_is_not_a_failure(self) -> None:
        common = DEPLOYMENT_ROOT / "MesDeployment.Common.ps1"
        source = f"""
        $ErrorActionPreference = 'Stop'
        . '{common}'
        $code = Invoke-MesNativeCommand `
            -Executable $env:ComSpec `
            -Arguments @('/d', '/c', 'echo informational 1>&2 & exit /b 0') `
            -AllowedExitCodes @(0)
        if ($code -ne 0) {{ exit 1 }}
        """
        result = self._run_powershell(source)

        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
