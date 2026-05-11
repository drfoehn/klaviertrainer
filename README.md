# Klaviertrainer – Deployment Guide

## Voraussetzungen
- Python 3.10+
- Nginx (empfohlen als Reverse Proxy)
- Ein Linux-Server (Ubuntu/Debian/RHEL)

---

## Schnellstart (lokaler Test)

```bash
cd klaviertrainer/
chmod +x start.sh
./start.sh
# → http://localhost:5000
```

Beim ersten Start:
- `venv/` wird automatisch erstellt
- `klaviertrainer.db` (SQLite) wird angelegt
- `.secret_key` wird generiert (nicht löschen!)

---

## Server-Deployment (Ubuntu)

### 1. Dateien hochladen
```bash
scp -r klaviertrainer/ user@server:/opt/klaviertrainer
ssh user@server
cd /opt/klaviertrainer
chmod +x start.sh
```

### 2. Abhängigkeiten installieren
```bash
./start.sh   # einmal ausführen, dann Ctrl+C
```

### 3. Systemd Service einrichten
```bash
# Pfade in klaviertrainer.service anpassen (User, WorkingDirectory)
sudo cp klaviertrainer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable klaviertrainer
sudo systemctl start klaviertrainer
sudo systemctl status klaviertrainer
```

### 4. Nginx einrichten
```bash
# Domain in nginx.conf anpassen
sudo cp nginx.conf /etc/nginx/sites-available/klaviertrainer
sudo ln -s /etc/nginx/sites-available/klaviertrainer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5. HTTPS (Let's Encrypt)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d klavier.deinserver.at
```

---

## Dateistruktur

```
klaviertrainer/
├── app.py                  # Flask Backend
├── requirements.txt        # Python Dependencies
├── start.sh               # Start-Script
├── klaviertrainer.service  # Systemd Unit
├── nginx.conf              # Nginx Config
├── klaviertrainer.db       # SQLite (auto-erstellt)
├── .secret_key            # Session Secret (auto-erstellt, nicht committen!)
├── uploads/               # PDFs pro User
│   └── {user_id}/
│       └── abc123_notenblatt.pdf
└── templates/
    ├── login.html         # Login/Register Page
    └── index.html         # Haupt-App
```

---

## Datenbank-Schema

```sql
users      (id, username, pw_hash, pw_salt, created)
favorites  (id, user_id, title, has_pdf, pdf_name, added)
pdfs       (id, user_id, fav_id, filename, orig_name, size_bytes, uploaded)
```

Backup:
```bash
sqlite3 klaviertrainer.db ".backup backup_$(date +%Y%m%d).db"
```

---

## Umgebungsvariablen

| Variable      | Beschreibung                        | Default              |
|---------------|-------------------------------------|----------------------|
| `SECRET_KEY`  | Flask Session Secret (wichtig!)     | Zufällig generiert   |
| `PORT`        | Server Port                         | `5000`               |
| `FLASK_DEBUG` | Debug Mode (nur lokal!)             | `0`                  |

---

## Admin: User verwalten

```bash
# User auflisten
sqlite3 klaviertrainer.db "SELECT id, username, created FROM users;"

# User löschen (inkl. Favoriten und PDFs via CASCADE)
sqlite3 klaviertrainer.db "DELETE FROM users WHERE username='testuser';"

# Passwort reset: User löschen und neu registrieren lassen
```

---

## PDF-Limits

- Max. 30 MB pro Datei (in `app.py` änderbar: `MAX_PDF_MB`)
- Nginx muss `client_max_body_size` entsprechend gesetzt haben
- PDFs liegen in `uploads/{user_id}/` mit zufälligem Präfix
