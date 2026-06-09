#!/bin/bash

# Script de nettoyage des fichiers de logs anciens
# Usage: ./clean_logs.sh [OPTIONS] <dossier> <âge_en_jours>

# --- Fonction d'affichage de l'aide ---
usage() {
    echo "Usage: $0 [OPTIONS] <dossier> <âge_en_jours>"
    echo "Options:"
    echo "  -d, --dry-run     Mode simulation (affiche les fichiers à supprimer sans les supprimer)"
    echo "  -v, --verbose     Mode verbeux (affiche les détails)"
    echo "  -p, --pattern     Filtre les fichiers par motif (ex: '*.log')"
    echo "  -h, --help        Affiche cette aide"
    exit 1
}

# --- Variables par défaut ---
DRY_RUN=false
VERBOSE=false
PATTERN="*"

# --- Analyse des arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -p|--pattern)
            PATTERN="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            break
            ;;
    esac
done

# --- Vérification du nombre d'arguments ---
if [[ $# -ne 2 ]]; then
    echo "Erreur : Il faut spécifier un dossier et un âge en jours."
    usage
fi

LOG_DIR="$1"
MAX_AGE="$2"

# --- Vérification que le dossier existe ---
if [[ ! -d "$LOG_DIR" ]]; then
    echo "Erreur : Le dossier '$LOG_DIR' n'existe pas ou n'est pas un dossier."
    exit 1
fi

# --- Vérification que l'âge est un nombre ---
if ! [[ "$MAX_AGE" =~ ^[0-9]+$ ]]; then
    echo "Erreur : L'âge doit être un nombre entier (en jours)."
    exit 1
fi

# --- Vérification que l'utilisateur a les droits ---
if [[ ! -w "$LOG_DIR" ]]; then
    echo "Erreur : Vous n'avez pas les droits en écriture sur '$LOG_DIR'."
    exit 1
fi

# --- Recherche des fichiers ---
if $VERBOSE; then
    echo "Recherche des fichiers de logs dans '$LOG_DIR' plus vieux que $MAX_AGE jours..."
    echo "Motif : $PATTERN"
fi

FILES_TO_DELETE=$(find "$LOG_DIR" -type f -name "$PATTERN" -mtime +$MAX_AGE 2>/dev/null)

if [[ -z "$FILES_TO_DELETE" ]]; then
    if $VERBOSE; then
        echo "Aucun fichier à supprimer."
    fi
    exit 0
fi

# --- Affichage des fichiers à supprimer ---
echo "Les fichiers suivants seront supprimés :"
echo "$FILES_TO_DELETE"
echo ""

# --- Mode simulation ---
if $DRY_RUN; then
    echo "[DRY RUN] Aucun fichier ne sera supprimé."
    exit 0
fi

# --- Confirmation interactive ---
read -p "Voulez-vous vraiment supprimer ces $(echo "$FILES_TO_DELETE" | wc -l) fichier(s) ? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Suppression annulée."
    exit 0
fi

# --- Suppression effective ---
if $VERBOSE; then
    echo "Suppression des fichiers..."
fi

echo "$FILES_TO_DELETE" | while read -r file; do
    if $VERBOSE; then
        echo "Suppression de : $file"
    fi
    rm -f "$file" || {
        echo "Erreur : Impossible de supprimer '$file'."
        exit 1
    }
done

if $VERBOSE; then
    echo "Nettoyage terminé."
else
    echo "Nettoyage des logs terminé : $(echo "$FILES_TO_DELETE" | wc -l) fichier(s) supprimé(s)."
fi

exit 0
