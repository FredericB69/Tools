#!/bin/bash

# Script de sauvegarde d'un dossier source vers un dossier de destination
# Usage: ./backup.sh [OPTIONS] <source> <destination>

# --- Fonction d'affichage de l'aide ---
usage() {
    echo "Usage: $0 [OPTIONS] <source> <destination>"
    echo "Options:"
    echo "  -c, --compress    Compresser la sauvegarde en .tar.gz"
    echo "  -v, --verbose     Mode verbeux (affiche les détails)"
    echo "  -h, --help        Affiche cette aide"
    exit 1
}

# --- Variables par défaut ---
COMPRESS=false
VERBOSE=false

# --- Analyse des arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--compress)
            COMPRESS=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
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
    echo "Erreur : Il faut spécifier un dossier source et un dossier de destination."
    usage
fi

SOURCE="$1"
DEST="$2"

# --- Vérification que le dossier source existe ---
if [[ ! -d "$SOURCE" ]]; then
    echo "Erreur : Le dossier source '$SOURCE' n'existe pas ou n'est pas un dossier."
    exit 1
fi

# --- Vérification que le dossier de destination existe, sinon le créer ---
if [[ ! -d "$DEST" ]]; then
    if $VERBOSE; then
        echo "Le dossier de destination '$DEST' n'existe pas. Création..."
    fi
    mkdir -p "$DEST" || {
        echo "Erreur : Impossible de créer le dossier de destination '$DEST'."
        exit 1
    }
fi

# --- Nom de la sauvegarde ---
BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"
BACKUP_PATH="$DEST/$BACKUP_NAME"

# --- Sauvegarde ---
if $COMPRESS; then
    if $VERBOSE; then
        echo "Compression et sauvegarde de '$SOURCE' vers '$BACKUP_PATH.tar.gz'..."
    fi
    tar -czf "$BACKUP_PATH.tar.gz" -C "$(dirname "$SOURCE")" "$(basename "$SOURCE")" || {
        echo "Erreur : La compression a échoué."
        exit 1
    }
    if $VERBOSE; then
        echo "Sauvegarde compressée terminée : $BACKUP_PATH.tar.gz"
    fi
else
    if $VERBOSE; then
        echo "Copie de '$SOURCE' vers '$BACKUP_PATH'..."
    fi
    cp -r "$SOURCE" "$BACKUP_PATH" || {
        echo "Erreur : La copie a échoué."
        exit 1
    }
    if $VERBOSE; then
        echo "Sauvegarde terminée : $BACKUP_PATH"
    fi
fi

echo "Sauvegarde effectuée avec succès."
exit 0
