#!/usr/bin/env python3
"""
Installation/lancement de local_ia pour CachyOS/Linux ou Windows.

Usage:
    python setup_local_ia.py

Le script exécute les commandes dans l'ordre et s'arrête si une commande échoue.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


REPO_URL = "https://github.com/lukeclnpro/local_ia.git"
PROJECT_DIR = Path("local_ia")


def run(command, *, cwd=None, shell=False):
    print(f"\n>>> {command if isinstance(command, str) else ' '.join(command)}")
    subprocess.run(command, cwd=cwd, shell=shell, check=True)


def command_exists(name):
    return shutil.which(name) is not None


def main():
    system = platform.system()

    if system == "Linux":
        # Clonage
        if not PROJECT_DIR.exists():
            run(["git", "clone", REPO_URL])
        else:
            print(f"{PROJECT_DIR} existe déjà, clonage ignoré.")

        # Dépendances système
        run([
            "sudo", "pacman", "-Syu", "--needed", "--noconfirm",
            "python", "python-pip", "python-virtualenv",
            "curl", "git", "base-devel"
        ])

        # Test Ollama (comme demandé)
        run(["python", "ollama_test.py"], cwd=PROJECT_DIR)

        # Service Ollama
        run(["sudo", "systemctl", "enable", "--now", "ollama"])

        # Modèle
        run(["ollama", "pull", "qwen2.5:1.5b"])

        # Environnement virtuel
        run(["python3", "-m", "venv", ".venv"], cwd=PROJECT_DIR)

        # Activation fish + pip + lancement
        # Une activation dans un sous-processus ne persiste pas après sa fin.
        # On utilise donc directement les exécutables du venv.
        venv_python = PROJECT_DIR / ".venv" / "bin" / "python"
        main_py = PROJECT_DIR / "main.py"

        run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])

        main_py.chmod(main_py.stat().st_mode | 0o111)
        run([str(main_py)], cwd=PROJECT_DIR)

    elif system == "Windows":
        # PowerShell est utilisé explicitement pour Set-ExecutionPolicy.
        if not PROJECT_DIR.exists():
            run(["git", "clone", REPO_URL])
        else:
            print(f"{PROJECT_DIR} existe déjà, clonage ignoré.")

        run(
            "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser",
            shell=True,
        )

        # Test Ollama (comme demandé)
        run(["python", "ollama_test.py"], cwd=PROJECT_DIR)

        # Installation des outils via winget
        run([
            "winget", "install", "Python.Python.3",
            "Git.Git", "Ollama.Ollama"
        ])

        run(["ollama", "pull", "qwen2.5:1.5b"])

        # Environnement virtuel
        run(["python", "-m", "venv", ".venv"], cwd=PROJECT_DIR)

        # Pas besoin d'activer le venv dans un subprocess :
        # on utilise directement son Python.
        venv_python = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
        main_py = PROJECT_DIR / "main.py"

        run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
        run([str(venv_python), str(main_py)], cwd=PROJECT_DIR)

    else:
        print(f"Système non supporté : {system}", file=sys.stderr)
        sys.exit(1)

    print("\nInstallation terminée.")


if __name__ == "__main__":
    main()
