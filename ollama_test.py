#!/usr/bin/env python3

import os
import platform
import shutil
import subprocess
import sys
import urllib.request


MODEL = "qwen2.5:1.5b"


# ============================================================
# OUTILS
# ============================================================

def run(command, check=False):
    print(f"> {' '.join(command)}")

    try:
        return subprocess.run(
            command,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
    except FileNotFoundError:
        return None


def command_exists(command):
    return shutil.which(command) is not None


def print_ok(message):
    print(f"[OK] {message}")


def print_info(message):
    print(f"[INFO] {message}")


def print_error(message):
    print(f"[ERREUR] {message}")


# ============================================================
# OLLAMA
# ============================================================

def find_ollama():
    """
    Cherche Ollama dans le PATH et dans les emplacements
    classiques de Windows/Linux.
    """

    path = shutil.which("ollama")

    if path:
        return path

    system = platform.system()

    possible_paths = []

    if system == "Windows":
        possible_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
            os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe"),
        ]

    elif system == "Linux":
        possible_paths = [
            "/usr/local/bin/ollama",
            "/usr/bin/ollama",
            os.path.expanduser("~/.local/bin/ollama"),
        ]

    for path in possible_paths:
        if os.path.isfile(path):
            return path

    return None


# ============================================================
# INSTALLATION WINDOWS
# ============================================================

def install_windows():

    print_info("Installation d'Ollama pour Windows...")

    url = "https://ollama.com/download/OllamaSetup.exe"

    installer = os.path.join(
        os.environ.get("TEMP", "."),
        "OllamaSetup.exe"
    )

    try:
        print_info("Téléchargement de l'installateur...")

        urllib.request.urlretrieve(
            url,
            installer
        )

        print_ok(f"Installateur téléchargé : {installer}")

        print_info("Lancement de l'installation...")

        subprocess.run(
            [installer],
            check=True
        )

    except Exception as e:
        print_error(f"Impossible d'installer Ollama : {e}")
        sys.exit(1)


# ============================================================
# INSTALLATION LINUX
# ============================================================

def install_linux():

    print_info("Installation d'Ollama pour Linux...")

    if not command_exists("curl"):
        print_info("curl n'est pas installé.")

        if command_exists("apt"):
            run([
                "sudo",
                "apt",
                "update"
            ], check=True)

            run([
                "sudo",
                "apt",
                "install",
                "-y",
                "curl"
            ], check=True)

        elif command_exists("dnf"):
            run([
                "sudo",
                "dnf",
                "install",
                "-y",
                "curl"
            ], check=True)

        elif command_exists("pacman"):
            run([
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "curl"
            ], check=True)

        else:
            print_error(
                "Impossible d'installer curl automatiquement."
            )
            sys.exit(1)

    print_info("Lancement de l'installateur officiel Ollama...")

    command = [
        "sh",
        "-c",
        "curl -fsSL https://ollama.com/install.sh | sh"
    ]

    result = run(command)

    if result is None or result.returncode != 0:
        print_error("Installation d'Ollama échouée.")
        sys.exit(1)

    print_ok("Ollama installé.")


# ============================================================
# INSTALLATION
# ============================================================

def install_ollama():

    system = platform.system()

    print_info(f"Système détecté : {system}")

    if system == "Windows":
        install_windows()

    elif system == "Linux":
        install_linux()

    else:
        print_error(
            f"Système non supporté : {system}"
        )
        print_info(
            "Systèmes supportés : Windows et Linux."
        )
        sys.exit(1)


# ============================================================
# SERVICE LINUX
# ============================================================

def start_linux_service():

    if not command_exists("systemctl"):
        return

    print_info("Vérification du service Ollama...")

    result = run([
        "systemctl",
        "is-active",
        "--quiet",
        "ollama"
    ])

    if result and result.returncode == 0:
        print_ok("Le service Ollama fonctionne.")
        return

    print_info("Démarrage du service Ollama...")

    result = run([
        "sudo",
        "systemctl",
        "enable",
        "--now",
        "ollama"
    ])

    if result and result.returncode == 0:
        print_ok("Service Ollama démarré.")
    else:
        print_info(
            "Le service systemd n'a pas pu être démarré."
        )


# ============================================================
# TEST OLLAMA
# ============================================================

def test_ollama(ollama):

    print_info("Test de communication avec Ollama...")

    try:
        result = subprocess.run(
            [
                ollama,
                "list"
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )

        if result.returncode == 0:
            print_ok("Ollama fonctionne.")
            return result.stdout

        print_error("Ollama ne répond pas correctement.")

    except Exception as e:
        print_error(str(e))

    return ""


# ============================================================
# MODELE
# ============================================================

def check_model(ollama, output):

    if MODEL in output:
        print_ok(f"Modèle déjà présent : {MODEL}")
        return

    print_info(
        f"Le modèle {MODEL} n'est pas installé."
    )

    answer = input(
        f"Télécharger {MODEL} maintenant ? [O/n] : "
    ).strip().lower()

    if answer not in ("", "o", "oui", "y", "yes"):
        print_info("Téléchargement ignoré.")
        return

    print_info(f"Téléchargement de {MODEL}...")

    result = run([
        ollama,
        "pull",
        MODEL
    ])

    if result and result.returncode == 0:
        print_ok(f"{MODEL} installé.")
    else:
        print_error(
            f"Impossible de télécharger {MODEL}."
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("        INSTALLATEUR OLLAMA WINDOWS / LINUX")
    print("=" * 60)
    print()

    system = platform.system()

    if system not in ("Windows", "Linux"):
        print_error(
            f"Système non supporté : {system}"
        )
        sys.exit(1)

    # --------------------------------------------------------
    # Vérification
    # --------------------------------------------------------

    ollama = find_ollama()

    if ollama:
        print_ok(
            f"Ollama est déjà installé : {ollama}"
        )

    else:
        print_info(
            "Ollama n'est pas installé."
        )

        install_ollama()

        # Rechercher à nouveau après installation
        ollama = find_ollama()

        if not ollama:
            print_error(
                "Ollama semble avoir été installé, "
                "mais l'exécutable est introuvable."
            )

            if system == "Windows":
                print_info(
                    "Redémarre éventuellement le terminal "
                    "pour actualiser le PATH."
                )

            sys.exit(1)

        print_ok(
            f"Ollama détecté : {ollama}"
        )

    # --------------------------------------------------------
    # Linux : service
    # --------------------------------------------------------

    if system == "Linux":
        start_linux_service()

    # --------------------------------------------------------
    # Test
    # --------------------------------------------------------

    output = test_ollama(ollama)

    if not output:
        print()
        print_error(
            "Ollama n'est pas disponible."
        )

        if system == "Windows":
            print_info(
                "Ouvre Ollama depuis le menu Démarrer "
                "puis relance ce script."
            )

        sys.exit(1)

    # --------------------------------------------------------
    # Modèle
    # --------------------------------------------------------

    check_model(
        ollama,
        output
    )

    # --------------------------------------------------------
    # Fin
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("Installation / vérification terminée.")
    print("=" * 60)
    print()
    print(f"Ollama : {ollama}")
    print(f"Modèle : {MODEL}")
    print()


if __name__ == "__main__":
    main()
