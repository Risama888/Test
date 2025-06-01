#!/bin/bash

# === KONFIGURASI ===
BOT_TOKEN="7795073622:AAFEHjnKKNAUv2SEwkhLpvblMqolLNjSP48"
CHAT_ID="6157064978"
PESAN="Halo, ini pesan otomatis dari script bash!"

# === URL API TELEGRAM ===
URL="https://api.telegram.org/bot$BOT_TOKEN/sendMessage"

# === LOOP TANPA HENTI ===
while true
do
    # Kirim pesan
    curl -s -X POST $URL -d chat_id=$CHAT_ID -d text="$PESAN"

    # Tampilkan log di terminal
    echo "$(date '+%Y-%m-%d %H:%M:%S') Pesan terkirim ke $CHAT_ID"

    # Tunggu 2 menit (120 detik)
    sleep 120
done
