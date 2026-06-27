#!/usr/bin/env python3
""""
snap_flatpak_update.py — Mise à jour des paquets Snap et Flatpak sur Ubuntu 24.04
Lance directement avec : python3 snap_flatpak_update.py
Le script s'auto-relance en sudo pour Snap si nécessaire.
""""

import subprocess
import sys
import os
import logging
from datetime import datetime
from pathlib import Path


# ─── Auto-élévation sudo ──────────────────────────────────────────────────────

def auto_elevate() -> None:
    """Se relance en sudo si le processus n'est pas root."""
    if os.geteuid() == 0:
        return

    print("[*] Privilèges insuffisants — relance automatique avec sudo…")
    if subprocess.run(["which", "sudo"], capture_output=True).returncode != 0:
        print("[✘] sudo introuvable.", file=sys.stderr)
        sys.exit(1)

    try:
        result = subprocess.run(["sudo", sys.executable] + sys.argv)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n[!] Interruption — annulé.")
        sys.exit(130)


auto_elevate()


# ─── Logging ──────────────────────────────────────────────────────────────────

LOG_DIR = Path("/var/log/snap_flatpak_update")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE),
    ],
)
log = logging.getLogger(__name__)


# ─── Fonctions utilitaires ────────────────────────────────────────────────────

def separator(title: str) -> None:
    log.info("")
    log.info("=" * 60)
    log.info(f"  {title}")
    log.info("=" * 60)


def run(cmd: list[str], description: str, check: bool = True) -> subprocess.CompletedProcess:
    """Exécute une commande et loggue le résultat."""
    log.info(f"▶  {description}")
    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            log.info(result.stdout.strip())
        if result.stderr.strip():
            log.debug(result.stderr.strip())
        log.info(f"✔  {description} — OK")
        return result
    except subprocess.CalledProcessError as exc:
        log.error(f"✘  {description} — ÉCHEC (code {exc.returncode})")
        if exc.stderr.strip():
            log.error(exc.stderr.strip())
        raise


def is_available(tool: str) -> bool:
    """Vérifie si un outil est disponible dans le PATH."""
    return subprocess.run(
        ["which", tool], capture_output=True
    ).returncode == 0


# ─── SNAP ─────────────────────────────────────────────────────────────────────

def list_snap_packages() -> list[str]:
    """Retourne la liste des snaps installés (hors core/snapd)."""
    result = subprocess.run(
        ["snap", "list"],
        capture_output=True, text=True, check=True
    )
    packages = []
    for line in result.stdout.splitlines()[1:]:  # skip header
        parts = line.split()
        if parts:
            name = parts[0]
            if name not in ("core", "core18", "core20", "core22", "core24", "snapd"):
                packages.append(name)
    return packages


def snap_refresh_list() -> list[str]:
    """Retourne la liste des snaps ayant une mise à jour disponible."""
    result = subprocess.run(
        ["snap", "refresh", "--list"],
        capture_output=True, text=True
    )
    updates = []
    if result.returncode == 0:
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if parts:
                updates.append(parts[0])
    return updates


def update_snap() -> dict:
    """
    Met à jour tous les snaps installés.
    Retourne un résumé {updated: int, errors: int}.
    """
    stats = {"updated": 0, "errors": 0, "skipped": 0}

    if not is_available("snap"):
        log.warning("snap introuvable — section ignorée.")
        return stats

    # Snaps avec mise à jour disponible
    pending = snap_refresh_list()

    if not pending:
        log.info("✔  Tous les snaps sont déjà à jour.")
        stats["skipped"] = len(list_snap_packages())
        return stats

    log.info(f"{len(pending)} snap(s) à mettre à jour : {', '.join(pending)}")

    # Rafraîchissement global (snap gère lui-même l'ordre)
    try:
        run(["snap", "refresh"], "Mise à jour de tous les snaps (snap refresh)")
        stats["updated"] = len(pending)
    except subprocess.CalledProcessError:
        # En cas d'échec global, on tente snap par snap
        log.warning("Échec global — tentative paquet par paquet…")
        for pkg in pending:
            try:
                run(["snap", "refresh", pkg], f"Snap : mise à jour de {pkg}")
                stats["updated"] += 1
            except subprocess.CalledProcessError:
                log.error(f"✘  Échec mise à jour snap : {pkg}")
                stats["errors"] += 1

    return stats


# ─── FLATPAK ──────────────────────────────────────────────────────────────────

def get_flatpak_remotes() -> list[str]:
    """Retourne la liste des dépôts Flatpak configurés."""
    result = subprocess.run(
        ["flatpak", "remotes", "--columns=name"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def list_flatpak_updates() -> list[str]:
    """Retourne la liste des applications Flatpak ayant une mise à jour disponible."""
    result = subprocess.run(
        ["flatpak", "remote-ls", "--updates", "--columns=application"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def update_flatpak() -> dict:
    """
    Met à jour toutes les applications Flatpak (système + utilisateur).
    Retourne un résumé {updated: int, errors: int}.
    """
    stats = {"updated": 0, "errors": 0}

    if not is_available("flatpak"):
        log.warning("flatpak introuvable — section ignorée.")
        return stats

    remotes = get_flatpak_remotes()
    if remotes:
        log.info(f"Dépôts Flatpak détectés : {', '.join(remotes)}")
    else:
        log.warning("Aucun dépôt Flatpak configuré.")
        return stats

    pending = list_flatpak_updates()
    if not pending:
        log.info("✔  Toutes les applications Flatpak sont déjà à jour.")
        return stats

    log.info(f"{len(pending)} application(s) Flatpak à mettre à jour : {', '.join(pending)}")

    # Mise à jour système (--system)
    try:
        run(
            ["flatpak", "update", "--system", "-y", "--noninteractive"],
            "Flatpak — mise à jour système (--system)"
        )
        stats["updated"] += len(pending)
    except subprocess.CalledProcessError:
        stats["errors"] += 1

    # Mise à jour utilisateur (--user) — pour les apps installées sans root
    try:
        result = subprocess.run(
            ["flatpak", "update", "--user", "-y", "--noninteractive"],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            log.info(result.stdout.strip())
        log.info("✔  Flatpak — mise à jour utilisateur (--user) — OK")
    except Exception as exc:
        log.warning(f"Flatpak --user : {exc}")

    # Suppression des runtimes inutilisés
    try:
        run(
            ["flatpak", "uninstall", "--unused", "-y", "--noninteractive"],
            "Flatpak — suppression des runtimes inutilisés"
        )
    except subprocess.CalledProcessError:
        log.warning("Impossible de supprimer les runtimes inutilisés.")

    return stats


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def main() -> None:
    start_time = datetime.now()

    separator("MISE À JOUR SNAP + FLATPAK — Ubuntu 24.04")
    log.info(f"Début : {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Journal : {LOG_FILE}")

    # ── SNAP ──────────────────────────────────────────────────────────────
    separator("SNAP")
    snap_stats = update_snap()

    # ── FLATPAK ───────────────────────────────────────────────────────────
    separator("FLATPAK")
    flatpak_stats = update_flatpak()

    # ── Résumé ────────────────────────────────────────────────────────────
    separator("RÉSUMÉ")
    elapsed = datetime.now() - start_time

    log.info(f"Snap    — mis à jour : {snap_stats['updated']}  |  erreurs : {snap_stats['errors']}")
    log.info(f"Flatpak — mis à jour : {flatpak_stats['updated']}  |  erreurs : {flatpak_stats['errors']}")
    log.info(f"Durée totale : {elapsed.seconds}s")
    log.info(f"Journal complet : {LOG_FILE}")

    total_errors = snap_stats["errors"] + flatpak_stats["errors"]
    if total_errors:
        log.warning(f"{total_errors} erreur(s) — consultez le journal pour les détails.")
        sys.exit(1)
    else:
        log.info("✔  Toutes les mises à jour ont réussi.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("Interruption manuelle.")
        sys.exit(130)
