#!/usr/bin/env python3
"""
rocky_update.py - Script de mise a jour automatisee pour Rocky Linux

Fonctionnalites :
  - Detection automatique de la version Rocky Linux (via /etc/os-release)
  - Elevation automatique en sudo si necessaire
  - dnf check-update / upgrade
  - Detection des paquets necessitant un redemarrage (dnf needs-restarting)
  - Logging horodate dans /var/log/rocky_update.log
  - Compatible cron (option --quiet)

Usage :
    sudo python3 rocky_update.py
    python3 rocky_update.py --quiet      # pour cron
    python3 rocky_update.py --no-reboot-check

Auteur : Heimdall
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime

LOG_FILE = "/var/log/rocky_update.log"


def log(message: str, quiet: bool = False) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    if not quiet:
        print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except PermissionError:
        pass  # pas de sudo -> on log juste en stdout


def check_root() -> None:
    """Relance le script avec sudo si on n'est pas root."""
    if os.geteuid() != 0:
        print("[*] Privileges root requis, relance avec sudo...")
        os.execvp("sudo", ["sudo", "python3"] + sys.argv)


def check_distro() -> str:
    """Verifie qu'on est bien sur Rocky Linux, renvoie la version."""
    try:
        with open("/etc/os-release") as f:
            content = f.read()
    except FileNotFoundError:
        print("[!] Impossible de lire /etc/os-release")
        sys.exit(1)

    if "rocky" not in content.lower():
        print("[!] Ce script est prevu pour Rocky Linux. Distribution non reconnue.")
        sys.exit(1)

    version = "inconnue"
    for line in content.splitlines():
        if line.startswith("VERSION_ID="):
            version = line.split("=", 1)[1].strip('"')
    return version


def run_cmd(cmd: list, quiet: bool = False) -> subprocess.CompletedProcess:
    log(f"Execution : {' '.join(cmd)}", quiet)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        log(result.stdout.strip(), quiet)
    if result.returncode != 0 and result.stderr.strip():
        log(f"ERREUR : {result.stderr.strip()}", quiet)
    return result


def needs_reboot(quiet: bool = False) -> bool:
    """Utilise dnf needs-restarting -r (code retour 1 = reboot necessaire)."""
    result = subprocess.run(
        ["dnf", "needs-restarting", "-r"], capture_output=True, text=True
    )
    if result.returncode == 1:
        log("Un redemarrage est necessaire (noyau ou lib critique mise a jour).", quiet)
        return True
    log("Aucun redemarrage necessaire.", quiet)
    return False


def main():
    parser = argparse.ArgumentParser(description="Mise a jour automatisee Rocky Linux")
    parser.add_argument("--quiet", action="store_true", help="Mode silencieux (cron)")
    parser.add_argument(
        "--no-reboot-check", action="store_true", help="Desactive la verification de redemarrage"
    )
    args = parser.parse_args()

    check_root()
    version = check_distro()
    log(f"=== Debut mise a jour Rocky Linux {version} ===", args.quiet)

    # 1. Verification des mises a jour disponibles
    check = run_cmd(["dnf", "check-update"], args.quiet)
    # dnf check-update renvoie 100 s'il y a des mises a jour, 0 si aucune
    if check.returncode == 0:
        log("Systeme deja a jour.", args.quiet)
    else:
        # 2. Mise a jour effective
        run_cmd(["dnf", "upgrade", "-y"], args.quiet)

        # 3. Nettoyage des paquets obsoletes
        run_cmd(["dnf", "autoremove", "-y"], args.quiet)

    # 4. Verification redemarrage
    if not args.no_reboot_check:
        needs_reboot(args.quiet)

    log("=== Fin mise a jour ===", args.quiet)


if __name__ == "__main__":
    main()
