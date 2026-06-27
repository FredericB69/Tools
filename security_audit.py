#!/usr/bin/env python3
""""
security_audit.py — Audit de sécurité local + réseau
Compatible : Debian/Ubuntu/Proxmox

Usage :
  python3 security_audit.py                             # audit local
  python3 security_audit.py --target 192.168.1.10       # audit réseau
  python3 security_audit.py --target 192.168.1.10 --ports 22,80,443,8006

Rapports générés dans /var/log/security_audit/ :
  <date>_<cible>.log   — rapport texte lisible
  <date>_<cible>.json  — rapport structuré exploitable (jq, scripts, SIEM…)
""""

import argparse
import json
import logging
import os
import pwd
import grp
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# ─── Auto-élévation sudo ──────────────────────────────────────────────────────

def auto_elevate() -> None:
    if os.geteuid() == 0:
        return
    print("[*] Relance automatique avec sudo…")
    if subprocess.run(["which", "sudo"], capture_output=True).returncode != 0:
        print("[✘] sudo introuvable.", file=sys.stderr)
        sys.exit(1)
    try:
        result = subprocess.run(["sudo", sys.executable] + sys.argv)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n[!] Annulé.")
        sys.exit(130)


auto_elevate()


# ─── Répertoire de sortie ─────────────────────────────────────────────────────

LOG_DIR = Path("/var/log/security_audit")
LOG_DIR.mkdir(parents=True, exist_ok=True)

_TS   = datetime.now().strftime("%Y%m%d_%H%M%S")
_SLUG = "localhost"   # sera mis à jour dans main() si --target fourni

def _build_log_path(slug: str) -> Path:
    return LOG_DIR / f"{_TS}_{slug}.log"

def _build_json_path(slug: str) -> Path:
    return LOG_DIR / f"{_TS}_{slug}.json"


# ─── Logging console + fichier .log ───────────────────────────────────────────

def setup_logging(slug: str) -> Path:
    """
    Configure le logging vers stdout ET vers un fichier .log horodaté.
    Retourne le chemin du fichier log.
    """
    log_file = _build_log_path(slug)
    fmt = "%(asctime)s [%(levelname)s] %(message)s"

    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    return log_file


# Initialisation provisoire (console uniquement) avant parse_args
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ─── Utilitaires ─────────────────────────────────────────────────────────────

def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """Exécute une commande, retourne (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"Commande introuvable : {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "Timeout"


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def separator(title: str) -> None:
    log.info("")
    log.info("─" * 60)
    log.info(f"  {title}")
    log.info("─" * 60)


# ─── CONTRÔLES LOCAUX ────────────────────────────────────────────────────────

def audit_system_info() -> dict:
    """Informations générales sur le système."""
    separator("Informations système")
    info = {}

    _, hostname, _ = run_cmd(["hostname", "-f"])
    _, kernel, _   = run_cmd(["uname", "-r"])
    _, arch, _     = run_cmd(["uname", "-m"])
    _, uptime, _   = run_cmd(["uptime", "-p"])

    # Distribution
    distro = "inconnue"
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    distro = line.split("=", 1)[1].strip().strip('"')
                    break
    except FileNotFoundError:
        pass

    info = {
        "hostname": hostname,
        "distro":   distro,
        "kernel":   kernel,
        "arch":     arch,
        "uptime":   uptime,
        "date":     datetime.now().isoformat(),
    }

    for k, v in info.items():
        log.info(f"  {k:12} : {v}")

    return info


def audit_users() -> dict:
    """
    Analyse des comptes utilisateurs :
    - Comptes avec UID 0 (root cachés)
    - Comptes sudo
    - Comptes avec shell interactif
    - Comptes sans mot de passe
    """
    separator("Utilisateurs & privileges")
    result = {
        "uid0_accounts":        [],
        "sudo_members":         [],
        "interactive_accounts": [],
        "no_password_accounts": [],
        "findings":             [],
    }

    # UID 0
    for p in pwd.getpwall():
        if p.pw_uid == 0:
            result["uid0_accounts"].append(p.pw_name)

    if len(result["uid0_accounts"]) > 1:
        result["findings"].append({
            "severity": "HIGH",
            "detail": f"Plusieurs comptes UID 0 : {result['uid0_accounts']}"
        })
        log.warning(f"[HIGH] Comptes UID 0 : {result['uid0_accounts']}")
    else:
        log.info(f"  UID 0 : {result['uid0_accounts']}")

    # Membres sudo / wheel
    for group_name in ("sudo", "wheel", "adm"):
        try:
            g = grp.getgrnam(group_name)
            result["sudo_members"].extend(g.gr_mem)
        except KeyError:
            pass
    result["sudo_members"] = list(set(result["sudo_members"]))
    log.info(f"  Membres sudo/wheel/adm : {result['sudo_members']}")

    # Comptes avec shell interactif (hors nologin/false)
    no_shell = {"/usr/sbin/nologin", "/sbin/nologin", "/bin/false", "/usr/bin/false"}
    for p in pwd.getpwall():
        if p.pw_shell not in no_shell and p.pw_uid >= 1000:
            result["interactive_accounts"].append(p.pw_name)
    log.info(f"  Comptes interactifs (UID≥1000) : {result['interactive_accounts']}")

    # Comptes sans mot de passe (champ vide dans /etc/shadow)
    try:
        with open("/etc/shadow") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) >= 2 and parts[1] == "":
                    result["no_password_accounts"].append(parts[0])
                    result["findings"].append({
                        "severity": "CRITICAL",
                        "detail": f"Compte sans mot de passe : {parts[0]}"
                    })
                    log.warning(f"[CRITICAL] Compte sans mot de passe : {parts[0]}")
    except PermissionError:
        log.warning("  /etc/shadow illisible (permissions insuffisantes)")

    return result


def audit_services() -> dict:
    """Services systemd actifs et timers."""
    separator("Services systemd actifs")
    result = {"active_services": [], "timers": [], "findings": []}

    # Services actifs
    rc, out, _ = run_cmd([
        "systemctl", "list-units", "--type=service", "--state=running",
        "--no-pager", "--no-legend"
    ])
    if rc == 0:
        for line in out.splitlines():
            parts = line.split()
            if parts:
                svc = parts[0]
                result["active_services"].append(svc)
                log.info(f"  [actif] {svc}")

    # Timers
    rc, out, _ = run_cmd([
        "systemctl", "list-timers", "--no-pager", "--no-legend"
    ])
    if rc == 0:
        for line in out.splitlines():
            parts = line.split()
            if parts and parts[0] not in ("NEXT", ""):
                result["timers"].append(" ".join(parts))

    log.info(f"  Timers actifs : {len(result['timers'])}")

    # Services suspects (exemples courants en CTF/pentest)
    suspicious = {"telnet.service", "rsh.service", "rlogin.service",
                  "tftp.service", "ftp.service", "rexec.service"}
    found_suspicious = suspicious & set(result["active_services"])
    if found_suspicious:
        for svc in found_suspicious:
            result["findings"].append({
                "severity": "HIGH",
                "detail": f"Service dangereux actif : {svc}"
            })
            log.warning(f"[HIGH] Service dangereux actif : {svc}")

    return result


def audit_open_ports_local() -> dict:
    """Ports en écoute sur la machine locale via ss."""
    separator("Ports ouverts (local)")
    result = {"listening_ports": [], "findings": []}

    rc, out, _ = run_cmd(["ss", "-tlunp"])
    if rc != 0:
        rc, out, _ = run_cmd(["netstat", "-tlunp"])

    risky_ports = {21, 23, 69, 111, 512, 513, 514, 2049}

    for line in out.splitlines():
        if "LISTEN" in line or ("udp" in line.lower() and "0.0.0.0" in line):
            parts = line.split()
            entry = {"raw": line.strip()}
            # Extraction port
            for part in parts:
                if ":" in part:
                    try:
                        port = int(part.rsplit(":", 1)[-1])
                        entry["port"] = port
                        if port in risky_ports:
                            result["findings"].append({
                                "severity": "MEDIUM",
                                "detail": f"Port à risque en écoute : {port}"
                            })
                            log.warning(f"[MEDIUM] Port à risque en écoute : {port}")
                        break
                    except ValueError:
                        pass
            result["listening_ports"].append(entry)
            log.info(f"  {line.strip()}")

    return result


def audit_suid_sgid() -> dict:
    """Fichiers SUID, SGID et world-writable dans les répertoires système."""
    separator("Fichiers SUID / SGID / World-Writable")
    result = {"suid": [], "sgid": [], "world_writable": [], "findings": []}

    search_paths = ["/usr", "/bin", "/sbin", "/tmp", "/var", "/home", "/opt"]

    # SUID
    rc, out, _ = run_cmd(
        ["find"] + search_paths + ["-perm", "-4000", "-type", "f", "-not", "-path", "*/proc/*"]
    )
    if rc == 0:
        for f in out.splitlines():
            result["suid"].append(f)
            log.info(f"  [SUID] {f}")
            # SUID hors /usr/bin standard → suspicious
            if not f.startswith(("/usr/bin/", "/usr/sbin/", "/bin/", "/sbin/")):
                result["findings"].append({
                    "severity": "HIGH",
                    "detail": f"SUID inhabituel : {f}"
                })
                log.warning(f"[HIGH] SUID inhabituel : {f}")

    # SGID
    rc, out, _ = run_cmd(
        ["find"] + search_paths + ["-perm", "-2000", "-type", "f", "-not", "-path", "*/proc/*"]
    )
    if rc == 0:
        for f in out.splitlines():
            result["sgid"].append(f)
            log.info(f"  [SGID] {f}")

    # World-writable (hors /tmp et /dev)
    rc, out, _ = run_cmd(
        ["find"] + search_paths +
        ["-perm", "-0002", "-not", "-path", "*/tmp/*",
         "-not", "-path", "*/dev/*", "-not", "-path", "*/proc/*",
         "-type", "f"]
    )
    if rc == 0:
        for f in out.splitlines():
            result["world_writable"].append(f)
            result["findings"].append({
                "severity": "MEDIUM",
                "detail": f"Fichier world-writable : {f}"
            })
            log.warning(f"[MEDIUM] World-writable : {f}")

    log.info(f"  SUID : {len(result['suid'])}  |  SGID : {len(result['sgid'])}  |  WW : {len(result['world_writable'])}")
    return result


def audit_sudo_config() -> dict:
    """Analyse de la configuration sudoers."""
    separator("Configuration sudo")
    result = {"sudoers_entries": [], "nopasswd_entries": [], "findings": []}

    rc, out, _ = run_cmd(["sudo", "-l", "-n"])
    if rc in (0, 1):
        for line in out.splitlines():
            result["sudoers_entries"].append(line.strip())
            if "NOPASSWD" in line:
                result["nopasswd_entries"].append(line.strip())
                result["findings"].append({
                    "severity": "HIGH",
                    "detail": f"Règle NOPASSWD détectée : {line.strip()}"
                })
                log.warning(f"[HIGH] NOPASSWD : {line.strip()}")
            else:
                log.info(f"  {line.strip()}")

    return result


def audit_cron_jobs() -> dict:
    """Tâches cron système et utilisateurs."""
    separator("Tâches cron")
    result = {"system_crons": [], "user_crons": [], "findings": []}

    cron_dirs = [
        "/etc/crontab",
        "/etc/cron.d",
        "/etc/cron.daily",
        "/etc/cron.weekly",
        "/etc/cron.monthly",
        "/var/spool/cron/crontabs",
    ]

    for path in cron_dirs:
        p = Path(path)
        if p.is_file():
            try:
                content = p.read_text()
                result["system_crons"].append({"file": str(p), "content": content})
                log.info(f"  [fichier] {p}")
                # Détection de chemins world-writable dans les crons
                for line in content.splitlines():
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.split()
                    for part in parts:
                        if part.startswith("/"):
                            fp = Path(part)
                            if fp.exists() and oct(fp.stat().st_mode)[-1] in ("2", "3", "6", "7"):
                                result["findings"].append({
                                    "severity": "HIGH",
                                    "detail": f"Script cron world-writable : {part}"
                                })
                                log.warning(f"[HIGH] Script cron world-writable : {part}")
            except PermissionError:
                log.warning(f"  {p} : permission refusée")
        elif p.is_dir():
            for f in p.iterdir():
                result["system_crons"].append({"file": str(f)})
                log.info(f"  [dir]    {f}")

    return result


# ─── CONTRÔLES RÉSEAU (cible distante) ───────────────────────────────────────

DEFAULT_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143,
    443, 445, 993, 995, 1723, 3306, 3389, 5900, 8006, 8080, 8443
]

BANNER_PORTS = {22, 21, 23, 25, 80, 8080, 8443, 8006}


def grab_banner(ip: str, port: int, timeout: float = 3.0) -> str | None:
    """Tente de récupérer la bannière d'un service."""
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.settimeout(timeout)
            try:
                banner = s.recv(1024).decode(errors="replace").strip()
                return banner[:200] if banner else None
            except socket.timeout:
                return None
    except (ConnectionRefusedError, OSError):
        return None


def audit_network_target(target: str, ports: list[int]) -> dict:
    """Scan de ports et bannières sur une cible réseau."""
    separator(f"Scan réseau : {target}")
    result = {
        "target":     target,
        "open_ports": [],
        "findings":   [],
    }

    # Résolution DNS
    try:
        ip = socket.gethostbyname(target)
        result["resolved_ip"] = ip
        log.info(f"  Cible résolue : {target} → {ip}")
    except socket.gaierror:
        result["findings"].append({"severity": "INFO", "detail": f"Résolution DNS échouée pour {target}"})
        log.error(f"  Résolution DNS échouée pour {target}")
        return result

    log.info(f"  Scan de {len(ports)} ports…")

    risky = {21, 23, 69, 111, 512, 513, 514, 2049, 3389, 5900}

    for port in sorted(ports):
        try:
            with socket.create_connection((ip, port), timeout=2):
                entry: dict = {"port": port, "state": "open"}

                # Résolution service connu
                try:
                    entry["service"] = socket.getservbyport(port)
                except OSError:
                    entry["service"] = "unknown"

                # Grab de bannière
                if port in BANNER_PORTS:
                    banner = grab_banner(ip, port)
                    if banner:
                        entry["banner"] = banner
                        log.info(f"  [OPEN] {port:5d}/{entry['service']:12s}  banner: {banner[:60]}")
                    else:
                        log.info(f"  [OPEN] {port:5d}/{entry['service']}")
                else:
                    log.info(f"  [OPEN] {port:5d}/{entry['service']}")

                if port in risky:
                    result["findings"].append({
                        "severity": "HIGH",
                        "detail": f"Port à risque ouvert : {port}/{entry['service']}"
                    })
                    log.warning(f"[HIGH] Port à risque : {port}/{entry['service']}")

                result["open_ports"].append(entry)

        except (ConnectionRefusedError, OSError):
            pass  # Port fermé ou filtré — normal

    log.info(f"  Ports ouverts : {len(result['open_ports'])} / {len(ports)}")
    return result


# ─── Sauvegarde des rapports ──────────────────────────────────────────────────

def save_json_report(report: dict, slug: str) -> Path:
    """Sauvegarde le rapport structuré en JSON."""
    json_file = _build_json_path(slug)
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return json_file


def save_text_report(report: dict, slug: str) -> Path:
    """
    Génère un rapport texte lisible (Markdown-like) à partir du dict rapport.
    Complémentaire au fichier .log qui contient la trace d'exécution brute.
    """
    txt_file = LOG_DIR / f"{_TS}_{slug}_report.txt"
    lines = []

    def h1(t):  lines.append(f"\n{'='*60}\n  {t}\n{'='*60}")
    def h2(t):  lines.append(f"\n  ── {t}")
    def row(k, v): lines.append(f"  {k:<30} {v}")

    h1("RAPPORT D'AUDIT DE SÉCURITÉ")
    meta = report.get("meta", {})
    row("Cible",   meta.get("target", "—"))
    row("Date",    meta.get("date",   "—"))
    row("Outil",   meta.get("auditor","—"))

    # Système
    si = report.get("system_info", {})
    if si:
        h1("INFORMATIONS SYSTÈME")
        for k, v in si.items():
            row(k, v)

    # Utilisateurs
    u = report.get("users", {})
    if u:
        h1("UTILISATEURS")
        row("Comptes UID 0",        ", ".join(u.get("uid0_accounts", [])) or "—")
        row("Membres sudo/wheel",   ", ".join(u.get("sudo_members",  [])) or "—")
        row("Comptes interactifs",  ", ".join(u.get("interactive_accounts", [])) or "—")
        row("Sans mot de passe",    ", ".join(u.get("no_password_accounts",[])) or "aucun")

    # Services
    svc = report.get("services", {})
    if svc:
        h1("SERVICES ACTIFS")
        for s in svc.get("active_services", []):
            lines.append(f"  [+] {s}")
        h2(f"Timers ({len(svc.get('timers',[]))})")
        for t in svc.get("timers", []):
            lines.append(f"      {t}")

    # Ports locaux
    op = report.get("open_ports", {})
    if op:
        h1("PORTS EN ÉCOUTE (LOCAL)")
        for p in op.get("listening_ports", []):
            lines.append(f"  {p.get('raw','')}")

    # SUID/SGID
    ss = report.get("suid_sgid", {})
    if ss:
        h1("FICHIERS SUID / SGID / WORLD-WRITABLE")
        h2(f"SUID ({len(ss.get('suid',[]))})")
        for f in ss.get("suid", []):   lines.append(f"  [SUID] {f}")
        h2(f"SGID ({len(ss.get('sgid',[]))})")
        for f in ss.get("sgid", []):   lines.append(f"  [SGID] {f}")
        h2(f"World-writable ({len(ss.get('world_writable',[]))})")
        for f in ss.get("world_writable", []): lines.append(f"  [WW]   {f}")

    # Sudo
    sc = report.get("sudo_config", {})
    if sc:
        h1("CONFIGURATION SUDO")
        for entry in sc.get("sudoers_entries", []):
            lines.append(f"  {entry}")
        if sc.get("nopasswd_entries"):
            h2("Règles NOPASSWD détectées")
            for entry in sc["nopasswd_entries"]:
                lines.append(f"  [!] {entry}")

    # Cron
    cron = report.get("cron_jobs", {})
    if cron:
        h1("TÂCHES CRON")
        for c in cron.get("system_crons", []):
            lines.append(f"  {c.get('file','')}")

    # Scan réseau
    ns = report.get("network_scan", {})
    if ns:
        h1(f"SCAN RÉSEAU : {ns.get('target','')}")
        row("IP résolue", ns.get("resolved_ip", "—"))
        h2(f"Ports ouverts ({len(ns.get('open_ports',[]))})")
        for p in ns.get("open_ports", []):
            banner = f"  → {p['banner'][:80]}" if p.get("banner") else ""
            lines.append(f"  [{p['port']:5d}] {p.get('service','?'):15s}{banner}")

    # Résumé findings
    summ = report.get("summary", {})
    if summ:
        h1("RÉSUMÉ DES FINDINGS")
        row("CRITICAL", summ.get("critical", 0))
        row("HIGH",     summ.get("high",     0))
        row("MEDIUM",   summ.get("medium",   0))
        row("LOW",      summ.get("low",      0))
        row("Total",    summ.get("total_findings", 0))
        row("Durée",    f"{summ.get('duration_s', 0)}s")
        lines.append("")
        for f in summ.get("findings", []):
            lines.append(f"  [{f.get('severity','?'):8s}] [{f.get('section','?')}] {f.get('detail','')}")

    lines.append(f"\n{'='*60}\n  Fin du rapport — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}\n")

    with open(txt_file, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    return txt_file


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit de sécurité local + réseau — génère un rapport LOG + JSON"
    )
    parser.add_argument(
        "--target", "-t",
        metavar="IP/HOST",
        help="Cible réseau à scanner (optionnel, ex: 192.168.1.10)"
    )
    parser.add_argument(
        "--ports", "-p",
        metavar="PORTS",
        help="Ports à scanner (virgule, ex: 22,80,443). Défaut : liste standard"
    )
    return parser.parse_args()


def collect_all_findings(report: dict) -> list[dict]:
    """Agrège tous les findings de toutes les sections."""
    findings = []
    for section, data in report.items():
        if isinstance(data, dict) and "findings" in data:
            for f in data["findings"]:
                f["section"] = section
                findings.append(f)
    return sorted(findings, key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}.get(x.get("severity", "INFO"), 4))


def main() -> None:
    args   = parse_args()
    target = args.target or "localhost"
    slug   = target.replace(".", "_").replace(":", "_")
    start  = datetime.now()

    # ── Reconfiguration du logging avec fichier .log ───────────────────────
    # On réinitialise les handlers pour ajouter le FileHandler maintenant
    # qu'on connaît le slug (cible)
    root_logger = logging.getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
    log_file = setup_logging(slug)

    ports = DEFAULT_PORTS
    if args.ports:
        try:
            ports = [int(p.strip()) for p in args.ports.split(",")]
        except ValueError:
            log.error("Format de ports invalide. Exemple : --ports 22,80,443")
            sys.exit(1)

    log.info("=" * 60)
    log.info("  SECURITY AUDIT — démarrage")
    log.info(f"  Cible   : {target}")
    log.info(f"  Début   : {start.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"  Log     : {log_file}")
    log.info("=" * 60)

    report: dict = {"meta": {"target": target, "date": start.isoformat(), "auditor": "security_audit.py"}}

    # ── Contrôles locaux ──────────────────────────────────────────────────
    report["system_info"] = audit_system_info()
    report["users"]       = audit_users()
    report["services"]    = audit_services()
    report["open_ports"]  = audit_open_ports_local()
    report["suid_sgid"]   = audit_suid_sgid()
    report["sudo_config"] = audit_sudo_config()
    report["cron_jobs"]   = audit_cron_jobs()

    # ── Contrôle réseau (si cible fournie) ───────────────────────────────
    if args.target:
        report["network_scan"] = audit_network_target(args.target, ports)

    # ── Agrégation des findings ───────────────────────────────────────────
    all_findings = collect_all_findings(report)
    report["summary"] = {
        "total_findings": len(all_findings),
        "critical":       sum(1 for f in all_findings if f.get("severity") == "CRITICAL"),
        "high":           sum(1 for f in all_findings if f.get("severity") == "HIGH"),
        "medium":         sum(1 for f in all_findings if f.get("severity") == "MEDIUM"),
        "low":            sum(1 for f in all_findings if f.get("severity") == "LOW"),
        "findings":       all_findings,
        "duration_s":     (datetime.now() - start).seconds,
    }

    # ── Sauvegarde JSON + rapport texte ───────────────────────────────────
    json_file = save_json_report(report, slug)
    txt_file  = save_text_report(report, slug)

    separator("RÉSUMÉ")
    log.info(f"  CRITICAL : {report['summary']['critical']}")
    log.info(f"  HIGH     : {report['summary']['high']}")
    log.info(f"  MEDIUM   : {report['summary']['medium']}")
    log.info(f"  Durée    : {report['summary']['duration_s']}s")
    log.info("")
    log.info(f"  Fichiers générés dans {LOG_DIR} :")
    log.info(f"  [LOG]    {log_file.name}    ← trace d'exécution")
    log.info(f"  [TXT]    {txt_file.name}    ← rapport lisible")
    log.info(f"  [JSON]   {json_file.name}   ← rapport structuré (jq, SIEM…)")
    log.info("")

    for f in all_findings:
        log.info(f"  [{f['severity']:8s}] [{f['section']}] {f['detail']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("Interruption manuelle.")
        sys.exit(130)
