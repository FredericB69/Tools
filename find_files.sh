#!/bin/bash

# Vérifier si au moins un argument est fourni
if [ $# -eq 0 ]; then
    echo "Usage: $0 [-n nom] [-t type] [-d répertoire]"
    echo "Options :"
    echo "  -n  Nom ou partie du nom du fichier/dossier"
    echo "  -t  Type (f pour fichier, d pour dossier, etc.)"
    echo "  -d  Répertoire de départ (par défaut : répertoire courant)"
    exit 1
fi

# Initialiser les variables
nom=""
type="f"
repertoire="."

# Analyser les arguments
while getopts ":n:t:d:" opt; do
    case $opt in
        n) nom="$OPTARG" ;;
        t) type="$OPTARG" ;;
        d) repertoire="$OPTARG" ;;
        \?) echo "Option invalide : -$OPTARG" >&2; exit 1 ;;
        :) echo "Option -$OPTARG nécessite un argument." >&2; exit 1 ;;
    esac
done

# Vérifier que le nom est fourni
if [ -z "$nom" ]; then
    echo "Erreur : Le nom du fichier/dossier est obligatoire."
    exit 1
fi

# Vérifier que le répertoire existe
if [ ! -d "$repertoire" ]; then
    echo "Erreur : Le répertoire '$repertoire' n'existe pas."
    exit 1
fi

# Exécuter la commande find
echo "Recherche de '$nom' (type : $type) dans '$repertoire'..."
find "$repertoire" -type "$type" -name "*$nom*"

# Afficher un message si aucun résultat
if [ $? -ne 0 ]; then
    echo "Aucun résultat trouvé."
fi
