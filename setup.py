#!/usr/bin/env python3
"""
setup_local_ia.py

Installe et lance local_ia depuis un dépôt déjà présent sur la machine.

Le script NE clone PAS le dépôt.
Il doit être placé à la racine du projet local_ia, à côté de :
    main.py
    ollama_test.py

Support :
    - Linux (CachyOS / Arch Linux)
    - Windows

Usage :
    python setup_local_ia.py
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path


MODEL = "qwen2.5:1.5b"


def run(command, *, cwd=None, shell=False):
    """Exécute une commande et arrête le script en cas d'erreur."""
    display = command if isinstance(command, str) else " ".join(map(str, command))
    print(f"\n>>> {display}")

    subprocess.run(
        command,
        cwd=cwd,
        shell=shell,
        check=True,
    )


def find_project_dir():
    """
    Le script est normalement à la racine du projet.
    On utilise son dossier comme répertoire de travail.
    """
    project_dir = Path(__file__).resolve().parent

    if not (project_dir / "main.py").exists():
        print(
            f"Erreur : main.py est introuvable dans :\n{project_dir}\n\n"
            "Place setup_local_ia.py à la racine du projet local_ia.",
            file=sys.stderr,
        )
        sys.exit(1)

    return project_dir


def install_linux(project_dir):
    print("=== Installation pour Linux / CachyOS ===")

    # Dépendances système
    run([
        "sudo",
        "pacman",
        "-Syu",
        "--needed",
        "--noconfirm",
        "python",
        "python-pip",
        "python-virtualenv",
        "curl",
        "git",
        "base-devel",
    ])

    # Vérification/test Ollama fourni par le projet
    ollama_test = project_dir / "ollama_test.py"
    if ollama_test.exists():
        run([sys.executable, str(ollama_test)], cwd=project_dir)

    # Service Ollama
    if shutil.which("systemctl"):
        run(["sudo", "systemctl", "enable", "--now", "ollama"])

    # Vérification de la présence de la commande ollama
    if not shutil.which("ollama"):
        print(
            "\nErreur : la commande 'ollama' est introuvable.\n"
            "Installe Ollama sur ton système puis relance le script.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Téléchargement du modèle
    run(["ollama", "pull", MODEL])

    # Création du venv
    venv_dir = project_dir / ".venv"
    run([sys.executable, "-m", "venv", str(venv_dir)])

    venv_python = venv_dir / "bin" / "python"

    # Mise à jour de pip
    run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])

    # Rend main.py exécutable
    main_py = project_dir / "main.py"
    main_py.chmod(main_py.stat().st_mode | 0o111)

    # Lance le programme avec le venv
    run([str(venv_python), str(main_py)], cwd=project_dir)


def install_windows(project_dir):
    print("=== Installation pour Windows ===")

    # Autorisation des scripts PowerShell pour l'utilisateur courant
    run(
        "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser",
        shell=True,
    )

    # Installation des logiciels avec winget.
    # --accept-source-agreements / --accept-package-agreements
    # évitent les questions interactives lorsque winget les supporte.
    if not shutil.which("winget"):
        print(
            "\nErreur : winget est introuvable.\n"
            "Installe/active App Installer (winget), puis relance le script.",
            file=sys.stderr,
        )
        sys.exit(1)

    run([
        "winget",
        "install",
        "--id",
        "Python.Python.3",
        "-e",
        "--accept-source-agreements",
        "--accept-package-agreements",
    ])

    run([
        "winget",
        "install",
        "--id",
        "Ollama.Ollama",
        "-e",
        "--accept-source-agreements",
        "--accept-package-agreements",
    ])

    # Git n'est volontairement PAS installé :
    # le script n'utilise plus git clone et n'en a pas besoin.

    # Après l'installation de Python/Ollama par winget, les PATH peuvent
    # ne pas être actualisés dans le processus Python actuel.
    python_cmd = shutil.which("python") or sys.executable
    ollama_cmd = shutil.which("ollama") or "ollama"

    # Test Ollama fourni par le projet
    ollama_test = project_dir / "ollama_test.py"
    if ollama_test.exists():
        run([python_cmd, str(ollama_test)], cwd=project_dir)

    # Téléchargement du modèle
    run([ollama_cmd, "pull", MODEL])

    # Création du venv
    venv_dir = project_dir / ".venv"
    run([python_cmd, "-m", "venv", str(venv_dir)])

    venv_python = venv_dir / "Scripts" / "python.exe"

    # Mise à jour de pip
    run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])

    # Lance le programme avec le venv
    main_py = project_dir / "main.py"
    run([str(venv_python), str(main_py)], cwd=project_dir)


def main():
    project_dir = find_project_dir()

    print("========================================")
    print("       local_ia - Installation")
    print("========================================")
    print(f"Dossier : {project_dir}")
    print("Le dépôt existant sera utilisé.")
    print("Aucun git clone ne sera effectué.")

    system = platform.system()

    try:
        if system == "Linux":
            install_linux(project_dir)

        elif system == "Windows":
            install_windows(project_dir)

        else:
            print(
                f"\nSystème non supporté : {system}",
                file=sys.stderr,
            )
            sys.exit(1)

    except subprocess.CalledProcessError as exc:
        print(
            f"\nErreur : la commande a échoué avec le code {exc.returncode}.",
            file=sys.stderr,
        )
        sys.exit(exc.returncode)

    print("\n========================================")
    print("Installation terminée.")
    print("========================================")


if __name__ == "__main__":
    main()
