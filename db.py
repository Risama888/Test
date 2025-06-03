import sqlite3

# Nama file database
db_filename = 'signals.db'

# Fungsi untuk membuat database dan tabel
def setup_database():
    conn = sqlite3.connect(db_filename)
    c = conn.cursor()

    # Membuat tabel jika belum ada
    c.execute('''
    CREATE TABLE IF NOT EXISTS sent_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_text TEXT UNIQUE,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()
    print("Database dan tabel berhasil dibuat atau sudah ada.")

# Panggil fungsi setup
if __name__ == "__main__":
    setup_database()
