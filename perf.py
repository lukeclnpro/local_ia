#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Collecte et affichage des performances système (CPU, RAM, GPU).

Affiché après chaque réponse de l'IA dans ia_agent.py.
"""

import shutil
import subprocess

import ui

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


# ============================================================
# COLLECTE
# ============================================================

def get_cpu_ram():
    """Retourne les métriques CPU/RAM, ou None si psutil est absent."""

    if not _HAS_PSUTIL:
        return None

    try:
        cpu_percent = psutil.cpu_percent(interval=0.3)
        memory = psutil.virtual_memory()
    except Exception:
        return None

    return {
        "cpu_percent": cpu_percent,
        "ram_percent": memory.percent,
        "ram_used_gb": memory.used / (1024 ** 3),
        "ram_total_gb": memory.total / (1024 ** 3),
    }


def get_gpu():
    """
    Tente de récupérer l'utilisation GPU via nvidia-smi.

    Retourne une liste de dictionnaires (un par carte détectée),
    ou None si aucun GPU NVIDIA n'est disponible.
    """

    nvidia_smi = shutil.which("nvidia-smi")

    if nvidia_smi is None:
        return None

    try:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=utilization.gpu,memory.used,memory.total,name",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0 or not result.stdout.strip():
        return None

    gpus = []

    for line in result.stdout.strip().splitlines():

        parts = [part.strip() for part in line.split(",")]

        if len(parts) < 4:
            continue

        try:
            gpus.append({
                "usage_percent": float(parts[0]),
                "mem_used_mb": float(parts[1]),
                "mem_total_mb": float(parts[2]),
                "name": parts[3],
            })
        except ValueError:
            continue

    return gpus or None


def get_snapshot():
    """Retourne un instantané complet des performances système."""

    return {
        "psutil_available": _HAS_PSUTIL,
        "cpu_ram": get_cpu_ram(),
        "gpu": get_gpu(),
    }


# ============================================================
# AFFICHAGE
# ============================================================

def _bar(percent, width=18):
    percent = max(0.0, min(100.0, percent or 0.0))
    filled = int(round(width * percent / 100))
    return "█" * filled + "░" * (width - filled)


def _bar_color(percent):
    if percent >= 85:
        return ui.C.BRIGHT_RED
    if percent >= 60:
        return ui.C.BRIGHT_YELLOW
    return ui.C.BRIGHT_GREEN


def render(snapshot=None):
    """
    Construit un bloc coloré prêt à afficher avec les performances
    CPU / RAM / GPU. À appeler après chaque réponse de l'IA.
    """

    if snapshot is None:
        snapshot = get_snapshot()

    lines = []

    lines.append(ui.colorize("┌─ Performances système " + "─" * 12, ui.C.PERF_LABEL))

    if not snapshot["psutil_available"]:
        lines.append(
            ui.colorize(
                "│ CPU/RAM indisponibles — installez le module : pip install psutil",
                ui.C.WARN,
            )
        )
    else:
        cpu_ram = snapshot["cpu_ram"]

        if cpu_ram is None:
            lines.append(ui.colorize("│ CPU/RAM : lecture impossible", ui.C.WARN))
        else:
            cpu_percent = cpu_ram["cpu_percent"]
            ram_percent = cpu_ram["ram_percent"]

            cpu_line = (
                ui.colorize("│ CPU  ", ui.C.PERF_LABEL)
                + ui.colorize(_bar(cpu_percent), _bar_color(cpu_percent))
                + ui.colorize(f" {cpu_percent:5.1f} %", ui.C.WHITE)
            )
            lines.append(cpu_line)

            ram_line = (
                ui.colorize("│ RAM  ", ui.C.PERF_LABEL)
                + ui.colorize(_bar(ram_percent), _bar_color(ram_percent))
                + ui.colorize(
                    f" {ram_percent:5.1f} %  "
                    f"({cpu_ram['ram_used_gb']:.1f} / {cpu_ram['ram_total_gb']:.1f} Go)",
                    ui.C.WHITE,
                )
            )
            lines.append(ram_line)

    gpu = snapshot["gpu"]

    if not gpu:
        lines.append(
            ui.colorize(
                "│ GPU  non détecté (nvidia-smi introuvable ou absent)",
                ui.C.DIM + ui.C.WHITE,
            )
        )
    else:
        for card in gpu:
            usage = card["usage_percent"]
            gpu_line = (
                ui.colorize("│ GPU  ", ui.C.PERF_LABEL)
                + ui.colorize(_bar(usage), _bar_color(usage))
                + ui.colorize(
                    f" {usage:5.1f} %  "
                    f"VRAM {card['mem_used_mb']:.0f}/{card['mem_total_mb']:.0f} Mo"
                    f"  ({card['name']})",
                    ui.C.WHITE,
                )
            )
            lines.append(gpu_line)

    lines.append(ui.colorize("└" + "─" * 36, ui.C.PERF_LABEL))

    return "\n".join(lines)


def print_perf():
    """Calcule puis affiche directement le bloc de performances."""
    print(render())
