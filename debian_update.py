#!/usr/bin/env python3
"""
debian_update.py — Mise à jour complète Debian 13 + base antivirale ClamAV
Lance directement avec : python3 debian_update.py
Le script s'auto-relance en sudo si nécessaire.
"""

import subprocess
import sys
import logging
import os
from datetime import datetime


# ─── Auto-élévation sudo ──────────────────────────────────────────────────────

def auto_elevate() -> None:
    """
    Si le processus courant n'est pas root, se relance automatiquement
    via sudo en préservant tous les arguments originaux.
    Quitte le processus non-root après le transfert.
    """
    if os.geteuid() == 0:
        return  # déjà root, rien à faire

    print("[*] Privilèges insuffisants — relance automatique avec sudo…")

    # Vérifie que sudo est disponible
    if subprocess.run(["which", "sudo"], capture_output=True).returncode != 0:
        print("[✘] sudo introuvable. Installez-le ou lancez le script en root.")
        sys.exit(1)

    # Reconstruction de la commande complète avec sudo
    cmd = ["sudo", sys.executable] + sys.argv
    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n[!] Interruption — annulé.")
        sys.exit(130)


# Élévation en tout premier, avant toute initialisation qui nécessite root
auto_elevate()


# ─── Configuration du logging (nécessite /var/log → root requis) ──────────────

LOG_DIR = "/var/log"
LOG_FILE = os.path.join(LOG_DIR, f"debian_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

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

def run(cmd: list[str], description: str) -> subprocess.CompletedProcess:
    """Exécute une commande système et loggue le résultat."""
    log.info(f"▶  {description}")
    log.debug(f"   Commande : {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
        )
        if result.stdout.strip():
            log.info(result.stdout.strip())
        log.info(f"✔  {description} — OK")
        return result
    except subprocess.CalledProcessError as exc:
        log.error(f"✘  {description} — ÉCHEC (code {exc.returncode})")
        if exc.stderr.strip():
            log.error(exc.stderr.strip())
        raise


def separator(title: str) -> None:
    log.info("")
    log.info("=" * 60)
    log.info(f"  {title}")
    log.info("=" * 60)


# ─── Étapes de mise à jour ────────────────────────────────────────────────────

def apt_update() -> None:
    """Rafraîchit la liste des paquets disponibles."""
    run(["apt-get", "update", "-y"], "Rafraîchissement des sources APT")


def apt_upgrade() -> None:
    """Met à jour tous les paquets installés sans changer les dépendances."""
    run(
        ["apt-get", "upgrade", "-y", "--with-new-pkgs"],
        "Mise à jour des paquets (upgrade)",
    )


def apt_dist_upgrade() -> None:
    """Met à jour la distribution (gère les changements de dépendances)."""
    run(
        ["apt-get", "dist-upgrade", "-y"],
        "Mise à jour de la distribution (dist-upgrade)",
    )


def apt_autoremove() -> None:
    """Supprime les paquets obsolètes et inutilisés."""
    run(
        ["apt-get", "autoremove", "-y", "--purge"],
        "Suppression des paquets inutilisés (autoremove)",
    )


def apt_autoclean() -> None:
    """Vide le cache APT des paquets obsolètes."""
    run(["apt-get", "autoclean", "-y"], "Nettoyage du cache APT (autoclean)")


# ─── ClamAV ───────────────────────────────────────────────────────────────────

def ensure_clamav_installed() -> None:
    """Installe ClamAV s'il n'est pas déjà présent."""
    result = subprocess.run(
        ["dpkg", "-s", "clamav"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.info("ClamAV non détecté — installation en cours…")
        run(
            ["apt-get", "install", "-y", "clamav", "clamav-daemon"],
            "Installation de ClamAV",
        )
    else:
        log.info("✔  ClamAV déjà installé.")


def stop_clamav_daemon() -> None:
    """Arrête clamav-freshclam pour libérer le verrou sur la base."""
    try:
        run(["systemctl", "stop", "clamav-freshclam"], "Arrêt du démon clamav-freshclam")
    except subprocess.CalledProcessError:
        log.warning("clamav-freshclam n'était pas actif — on continue.")


def update_clamav_db() -> None:
    """Met à jour la base de signatures ClamAV via freshclam."""
    run(["freshclam"], "Mise à jour de la base antivirale ClamAV (freshclam)")


def start_clamav_daemon() -> None:
    """Redémarre clamav-freshclam après la mise à jour."""
    try:
        run(["systemctl", "start", "clamav-freshclam"], "Redémarrage du démon clamav-freshclam")
    except subprocess.CalledProcessError:
        log.warning("Impossible de redémarrer clamav-freshclam (service absent ou désactivé).")


def show_clamav_version() -> None:
    """Affiche la version de la base ClamAV après mise à jour."""
    try:
        result = subprocess.run(
            ["clamscan", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        log.info(f"Version ClamAV : {result.stdout.strip()}")
    except subprocess.CalledProcessError:
        log.warning("Impossible de récupérer la version ClamAV.")


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def main() -> None:
    start_time = datetime.now()

    log.info(f"Démarrage de la mise à jour — {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Journal : {LOG_FILE}")

    # ── 1. Mise à jour Debian ──────────────────────────────────────────────
    separator("MISE À JOUR DEBIAN 13")
    apt_update()
    apt_upgrade()
    apt_dist_upgrade()
    apt_autoremove()
    apt_autoclean()

    # ── 2. Mise à jour ClamAV ──────────────────────────────────────────────
    separator("MISE À JOUR BASE ANTIVIRALE CLAMAV")
    ensure_clamav_installed()
    stop_clamav_daemon()
    update_clamav_db()
    start_clamav_daemon()
    show_clamav_version()

    # ── 3. Résumé ──────────────────────────────────────────────────────────
    separator("RÉSUMÉ")
    elapsed = datetime.now() - start_time
    log.info(f"Mise à jour terminée avec succès en {elapsed.seconds}s.")
    log.info(f"Journal complet disponible dans : {LOG_FILE}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        log.error("Une étape a échoué — consultez le journal pour les détails.")
        sys.exit(1)
    except KeyboardInterrupt:
        log.warning("Interruption manuelle — mise à jour annulée.")
        sys.exit(130)
