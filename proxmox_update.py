#!/usr/bin/env python3
""""
proxmox_update.py — Mise à jour automatique Proxmox VE 8.x (Debian Bookworm)
- Met à jour les dépôts et paquets PVE
- Détecte si un nouveau kernel a été installé et redémarre si nécessaire
- Journal horodaté dans /var/log/proxmox_update/
- Conçu pour être planifié via cron (exécution non interactive).

Utilisation manuelle : python3 proxmox_update.py
Cron exemple (chaque dimanche à 03h00) :
  0 3 * * 0 /usr/bin/python3 /opt/scripts/proxmox_update.py
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

    # En mode cron, on ne peut pas demander de mot de passe — on échoue proprement
    if not sys.stdin.isatty():
        print("[✘] Exécution non interactive sans root. Ajoutez l'utilisateur au sudoers "
              "ou planifiez la cron sous root.", file=sys.stderr)
        sys.exit(1)

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

LOG_DIR = Path("/var/log/proxmox_update")
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


# ─── Vérification Proxmox VE ──────────────────────────────────────────────────

def check_proxmox() -> str:
    """
    Vérifie que le système est bien un nœud Proxmox VE 8.x.
    Retourne la version PVE sous forme de chaîne.
    """
    result = subprocess.run(
        ["pveversion"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            "pveversion introuvable — ce script nécessite Proxmox VE."
        )
    version_line = result.stdout.strip()
    if not version_line.startswith("pve-manager/8"):
        log.warning(f"Version détectée : {version_line} — ce script cible PVE 8.x.")
    else:
        log.info(f"Proxmox VE détecté : {version_line}")
    return version_line


# ─── Kernel courant ───────────────────────────────────────────────────────────

def get_running_kernel() -> str:
    """Retourne le kernel actuellement en cours d'exécution."""
    result = subprocess.run(["uname", "-r"], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def get_latest_installed_kernel() -> str | None:
    """
    Retourne le kernel PVE le plus récent installé via dpkg,
    ou None si aucun paquet pve-kernel n'est trouvé.
    """
    result = subprocess.run(
        ["dpkg", "--list", "pve-kernel-*"],
        capture_output=True, text=True
    )
    kernels = []
    for line in result.stdout.splitlines():
        # Lignes dpkg installées commencent par "ii"
        if line.startswith("ii"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith("pve-kernel-"):
                kernels.append(parts[1])

    if not kernels:
        return None

    # Tri lexicographique descendant — suffisant pour les versions PVE
    kernels.sort(reverse=True)
    # Extrait la version depuis le nom du paquet (ex. pve-kernel-6.8.12-4-pve)
    latest_pkg = kernels[0]
    kernel_ver = latest_pkg.replace("pve-kernel-", "")
    return kernel_ver


# ─── Fonctions utilitaires ────────────────────────────────────────────────────

def run(cmd: list[str], description: str) -> subprocess.CompletedProcess:
    """Exécute une commande et loggue le résultat."""
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
        "Mise à jour des paquets PVE (upgrade)",
    )


def apt_dist_upgrade() -> None:
    run(
        ["apt-get", "dist-upgrade", "-y"],
        "Mise à jour complète de la distribution (dist-upgrade)",
    )


def apt_autoremove() -> None:
    run(
        ["apt-get", "autoremove", "-y", "--purge"],
        "Suppression des paquets inutilisés",
    )


def apt_autoclean() -> None:
    run(["apt-get", "autoclean", "-y"], "Nettoyage du cache APT")


# ─── Gestion du redémarrage ───────────────────────────────────────────────────

def handle_reboot(kernel_before: str) -> None:
    """
    Compare le kernel avant/après mise à jour.
    Redémarre si un nouveau kernel PVE a été installé.
    Attend 60 secondes pour laisser le temps aux VMs/CTs de se préparer.
    """
    kernel_after = get_latest_installed_kernel()

    log.info(f"Kernel en cours d'exécution : {kernel_before}")
    log.info(f"Kernel PVE le plus récent installé : {kernel_after or 'indéterminé'}")

    needs_reboot = False

    # Cas 1 : nouveau kernel détecté via dpkg
    if kernel_after and kernel_after != kernel_before:
        log.info("→ Nouveau kernel détecté — redémarrage nécessaire.")
        needs_reboot = True

    # Cas 2 : fichier sentinelle laissé par needrestart ou update-notifier
    elif Path("/var/run/reboot-required").exists():
        log.info("→ Fichier /var/run/reboot-required présent — redémarrage nécessaire.")
        needs_reboot = True

    if needs_reboot:
        log.info("Redémarrage du nœud Proxmox dans 60 secondes…")
        log.info(f"Journal complet : {LOG_FILE}")
        # shutdown -r +1 planifie un reboot dans 1 minute
        subprocess.run(["shutdown", "-r", "+1",
                        "Redémarrage automatique post-mise-à-jour Proxmox"])
    else:
        log.info("✔  Aucun nouveau kernel — redémarrage non nécessaire.")


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def main() -> None:
    start_time = datetime.now()

    separator("PROXMOX VE 8.x — MISE À JOUR AUTOMATIQUE")
    log.info(f"Début : {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Journal : {LOG_FILE}")

    # Vérification de l'environnement
    pve_version   = check_proxmox()
    kernel_before = get_running_kernel()

    # ── Mise à jour ───────────────────────────────────────────────────────
    separator("MISE À JOUR APT / PVE")
    apt_update()
    apt_upgrade()
    apt_dist_upgrade()
    apt_autoremove()
    apt_autoclean()

    # ── Redémarrage conditionnel ──────────────────────────────────────────
    separator("VÉRIFICATION KERNEL / REDÉMARRAGE")
    handle_reboot(kernel_before)

    # ── Résumé ────────────────────────────────────────────────────────────
    separator("RÉSUMÉ")
    elapsed = datetime.now() - start_time
    log.info(f"PVE : {pve_version}")
    log.info(f"Durée totale : {elapsed.seconds}s")
    log.info(f"Journal : {LOG_FILE}")
    log.info("Mise à jour terminée avec succès.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        log.error("Une étape a échoué — consultez le journal pour les détails.")
        sys.exit(1)
    except RuntimeError as exc:
        log.error(str(exc))
        sys.exit(2)
    except KeyboardInterrupt:
        log.warning("Interruption manuelle.")
        sys.exit(130)
