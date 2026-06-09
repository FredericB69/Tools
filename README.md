# 📁 Dossier `scripting`

Ce dossier contient des scripts Bash et éventuellement d'autres langages (Python, Bash, etc.) pour automatiser des tâches courantes ou spécifiques.

---

## 📌 Description

Les scripts présents ici sont conçus pour :
- **Automatiser** des tâches répétitives (recherche de fichiers, sauvegardes, déploiements, etc.).
- **Faciliter** la gestion de fichiers, de dossiers ou de configurations.
- **Simplifier** l'interaction avec des outils en ligne de commande.

---

## 📂 Contenu
   Script | Langage | Description | Usage |
 |--------|---------|-------------|-------|
 | [`find_files.sh`](./find_files.sh) | Bash | Recherche des fichiers/dossiers par nom, type ou répertoire. | `./find_files.sh -n "nom" -t f -d /chemin` |
 | [`backup.sh`](./backup.sh) | Bash | Sauvegarde un dossier vers un emplacement distant. | `./backup.sh /source /destination` |
 | [`clean_logs.sh`](./clean_logs.sh) | Bash | Supprime les fichiers de logs anciens. | `./clean_logs.sh -d 30` |

*(Ajoutez ou modifiez cette table selon vos scripts.)*

---

## 🛠 Prérequis

- **Système d'exploitation** : Linux, macOS (ou Windows avec WSL/Git Bash).
- **Bash** : Version 4.0 ou supérieure (vérifiez avec `bash --version`).
- **Permissions** : Certains scripts nécessitent d'être exécutables (`chmod +x script.sh`).
- **Outils externes** : Certains scripts peuvent dépendre d'outils comme `find`, `rsync`, `awk`, etc. (généralement installés par défaut).

---

## 🚀 Installation

1. **Cloner le dépôt** (si ce n'est pas déjà fait) :
   ```bash
   git clone https://github.com/votre-utilisateur/votre-depot.git
   cd votre-depot/scripting
