#!/bin/bash

# --- CONFIGURAZIONE ---
# Inserisci qui il percorso del file (es: src/main.js)
TARGET_FILE=gateway/prompts/harper/plan_system.md
# Quanti mesi vuoi andare indietro?
SINCE="6 months ago"
# Cartella di destinazione
OUTPUT_DIR=$PWD/extract_history
# ----------------------

if [ ! -f "$TARGET_FILE" ]; then
    echo "Errore: Il file '$TARGET_FILE' non esiste nel percorso specificato."
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "Inizio recupero versioni per: $TARGET_FILE"
echo "------------------------------------------"

# Recuperiamo Hash, Data e Oggetto (per gestire rinomine con --follow)
git log --since="$SINCE" --follow --pretty=format:"%h|%as" -- "$TARGET_FILE" | while IFS='|' read -r hash date; do
    
    # Nome del file di output: DATA_HASH_NOMEORIGINALE
    FILENAME="${date}_${hash}_$(basename "$TARGET_FILE")"
    
    # Estraiamo il contenuto del file in quel commit specifico
    # Usiamo git show $hash -- "$TARGET_FILE" per maggiore sicurezza
    git show "$hash:$TARGET_FILE" > "$OUTPUT_DIR/$FILENAME" 2>/dev/null
    
    if [ $? -eq 0 ]; then
        echo "✅ Recuperato: $FILENAME"
    else
        echo "⚠️  Impossibile recuperare la versione al commit $hash (forse il file aveva un altro nome)"
    fi
done

echo "------------------------------------------"
echo "Completato! Trovi tutte le versioni in: $OUTPUT_DIR"
