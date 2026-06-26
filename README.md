# 📁 Dossier `scripting`

Ce dossier contient des scripts Python pour automatiser des tâches d'administration système sur Ubuntu/Debian et Proxmox.

---

## 📌 Description

Les scripts présents ici sont conçus pour :
- **Automatiser** les mises à jour système (APT, Snap, Flatpak, ClamAV, Proxmox).
- **Auditer** la sécurité locale et réseau.
- **Détecter** les fichiers et paquets obsolètes.

---

## 📂 Contenu

| Script | Description | Usage |
|--------|-------------|-------|
| [`linux_update.py`](./linux_update.py) | Mise à jour APT + ClamAV (Debian 13 / Ubuntu 24.04) | `sudo python3 linux_update.py` |
| [`proxmox_update.py`](./proxmox_update.py) | Mise à jour Proxmox PVE 8.x avec reboot conditionnel | `sudo python3 proxmox_update.py` |
| [`snap_flatpak_update.py`](./snap_flatpak_update.py) | Mise à jour Snap + Flatpak (Ubuntu 24.04) | `sudo python3 snap_flatpak_update.py` |
| [`security_audit.py`](./security_audit.py) | Audit de sécurité local et réseau (LOG + TXT + JSON) | `sudo python3 security_audit.py` |
| [`obsolete_finder.py`](./obsolete_finder.py) | Détection paquets orphelins, vieux logs, configs résiduelles | `sudo python3 obsolete_finder.py` |

---

## 🛠 Prérequis

- **Système d'exploitation** : Ubuntu 24.04 / Debian 13 / Proxmox PVE 8.x
- **Python** : Version 3.10 ou supérieure (vérifiez avec `python3 --version`)
- **Permissions** : Tous les scripts nécessitent les droits root (`sudo`)
- **Outils externes** : `apt`, `dpkg`, `snap`, `flatpak`, `clamscan` (selon le script utilisé)

---

## 📝 Logs

Les scripts génèrent des logs horodatés dans `/var/log/` :

| Script | Fichier de log |
|--------|---------------|
| `linux_update.py` | `/var/log/linux_update.log` |
| `proxmox_update.py` | `/var/log/proxmox_update.log` |
| `snap_flatpak_update.py` | `/var/log/snap_flatpak_update.log` |
| `security_audit.py` | `/var/log/security_audit.log` |
| `obsolete_finder.py` | `/var/log/obsolete_finder.log` |

---

## ⚠️ Avertissement

Ces scripts sont fournis à titre éducatif et personnel. Testez-les dans un environnement non critique avant tout déploiement en production.
