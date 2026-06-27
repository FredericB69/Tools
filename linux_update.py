#!/usr/bin/env python3
""""
linux_update.py — Mise à jour complète Debian/Ubuntu + base antivirale ClamAV
Compatible : Debian 12/13, Ubuntu 22.04/24.04 et dérivés APT.
Lance directement avec : python3 linux_update.py
Le script s'auto-relance en sudo si nécessaire.
""""

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
    """
    if os.geteuid() == 0:
        return

    print("[*] Privilèges insuffisants — relance automatique avec sudo…")

    if subprocess.run(["which", "sudo"], capture_output=True).returncode != 0:
        print("[✘] sudo introuvable. Installez-le ou lancez le script en root.")
        sys.exit(1)

    cmd = ["sudo", sys.executable] + sys.argv
    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n[!] Interruption — annulé.")
        sys.exit(130)


# Élévation en tout premier, avant toute initialisation root
auto_elevate()


# ─── Détection de la distribution ────────────────────────────────────────────

def detect_distro() -> dict:
    """
    Lit /etc/os-release et retourne un dict avec :
      - name    : nom lisible (ex. "Ubuntu", "Debian GNU/Linux")
      - version : numéro de version (ex. "24.04", "13")
      - id      : identifiant bas niveau (ex. "ubuntu", "debian")
      - family  : "debian" pour tout dérivé APT reconnu
    Lève une RuntimeError si la distro n'est pas basée sur APT.
    """
    info = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    info[k] = v.strip('"')
    except FileNotFoundError:
        raise RuntimeError("/etc/os-release introuvable — système non supporté.")

    distro_id = info.get("ID", "").lower()
    id_like   = info.get("ID_LIKE", "").lower()

    apt_family = {"debian", "ubuntu", "linuxmint", "pop", "elementary", "kali", "raspbian"}
    if distro_id not in apt_family and not any(d in id_like for d in apt_family):
        raise RuntimeError(
            f"Distribution '{distro_id}' non supportée. Ce script nécessite APT (Debian/Ubuntu)."
        )

    return {
        "name":    info.get("NAME",       distro_id),
        "version": info.get("VERSION_ID", "inconnue"),
        "id":      distro_id,
        "family":  "debian",
    }


DISTRO = detect_distro()


# ─── Configuration du logging ─────────────────────────────────────────────────

LOG_DIR  = "/var/log"
LOG_FILE = os.path.join(LOG_DIR, f"linux_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

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
    run(["apt-get", "update", "-y"], "Rafraîchissement des sources APT")


def apt_upgrade() -> None:
    run(
        ["apt-get", "upgrade", "-y", "--with-new-pkgs"],
        "Mise à jour des paquets (upgrade)",
    )


def apt_full_upgrade() -> None:
    """
    Ubuntu recommande 'full-upgrade' ; Debian utilise 'dist-upgrade'.
    Les deux sont équivalents, on adapte selon la distro détectée.
    """
    if DISTRO["id"] == "ubuntu":
        cmd  = ["apt-get", "full-upgrade", "-y"]
        desc = "Mise à jour complète (full-upgrade — Ubuntu)"
    else:
        cmd  = ["apt-get", "dist-upgrade", "-y"]
        desc = "Mise à jour de la distribution (dist-upgrade — Debian)"
    run(cmd, desc)


def apt_autoremove() -> None:
    run(
        ["apt-get", "autoremove", "-y", "--purge"],
        "Suppression des paquets inutilisés (autoremove)",
    )


def apt_autoclean() -> None:
    run(["apt-get", "autoclean", "-y"], "Nettoyage du cache APT (autoclean)")


# ─── ClamAV ───────────────────────────────────────────────────────────────────

def ensure_clamav_installed() -> None:
    result = subprocess.run(["dpkg", "-s", "clamav"], capture_output=True, text=True)
    if result.returncode != 0:
        log.info("ClamAV non détecté — installation en cours…")
        run(
            ["apt-get", "install", "-y", "clamav", "clamav-daemon"],
            "Installation de ClamAV",
        )
    else:
        log.info("✔  ClamAV déjà installé.")


def stop_clamav_daemon() -> None:
    try:
        run(["systemctl", "stop", "clamav-freshclam"], "Arrêt du démon clamav-freshclam")
    except subprocess.CalledProcessError:
        log.warning("clamav-freshclam n'était pas actif — on continue.")


def update_clamav_db() -> None:
    run(["freshclam"], "Mise à jour de la base antivirale ClamAV (freshclam)")


def start_clamav_daemon() -> None:
    try:
        run(["systemctl", "start", "clamav-freshclam"], "Redémarrage du démon clamav-freshclam")
    except subprocess.CalledProcessError:
        log.warning("Impossible de redémarrer clamav-freshclam (service absent ou désactivé).")


def show_clamav_version() -> None:
    try:
        result = subprocess.run(
            ["clamscan", "--version"], capture_output=True, text=True, check=True
        )
        log.info(f"Version ClamAV : {result.stdout.strip()}")
    except subprocess.CalledProcessError:
        log.warning("Impossible de récupérer la version ClamAV.")


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def main() -> None:
    start_time = datetime.now()

    log.info(f"Distribution détectée : {DISTRO['name']} {DISTRO['version']}")
    log.info(f"Démarrage de la mise à jour — {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Journal : {LOG_FILE}")

    # ── 1. Mise à jour système ─────────────────────────────────────────────
    separator(f"MISE À JOUR {DISTRO['name'].upper()} {DISTRO['version']}")
    apt_update()
    apt_upgrade()
    apt_full_upgrade()
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
