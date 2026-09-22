"""Do not inherit PowerShell 7's bundled modules into Windows PowerShell 5.1."""
import os
from pathlib import Path


def windows_powershell_environment() -> dict[str, str]:
    env = os.environ.copy()
    if os.name == "nt":
        env["PSMODULEPATH"] = os.pathsep.join([
            str(Path(env["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/Modules"),
            str(Path(env["PROGRAMFILES"]) / "WindowsPowerShell/Modules"),
        ])
    return env
