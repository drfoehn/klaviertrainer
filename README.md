# Klaviertrainer

A web-based piano training and music education app with chord recognition, sheet music management, note reading exercises, and MIDI support.

## Versions

### `klaviertrainer-public.html` — Standalone Version
A self-contained single HTML file that runs **natively in any browser without any installation or server**. Just open the file directly. This version does **not** include sheet music storage or user login — it's a pure client-side tool for music theory and ear training.

### Full Server Version (`app.py`)
A Flask-based multi-user app with login, per-user sheet music storage (PDF upload), admin panel, and production deployment support.

---

## Features

- **Chord Library & Recognition** — Interactive chord database with visual keyboard; real-time MIDI chord detection
- **Practice Mode** — Guided chord exercises with MIDI input
- **Sheet Music Viewer** — PDF upload, zoom, pagination, and personal favorites (server version only)
- **Note Reading Trainer** — Staff notation exercises with adjustable difficulty and clef selection (treble, bass, both)
- **Circle of Fifths** — Interactive Quintenzirkel for music theory
- **Sheet Search** — Integrated search via Google/IMSLP
- **MIDI Support** — Full Web MIDI API integration for hardware instruments
- **Multi-language** — German and English UI
- **Admin Panel** — User management: create, delete, password reset, admin toggle (server version only)

---

## Quick Start (Server Version)

```bash
cd klaviertrainer/
chmod +x start.sh
./start.sh
# → http://localhost:5000
```

On first run:
- `venv/` is created automatically
- `klaviertrainer.db` (SQLite) is initialized
- `.secret_key` is generated (do not delete or commit!)

---

## Server Deployment (Ubuntu/Debian)

### 1. Upload files
```bash
scp -r klaviertrainer/ user@server:/opt/klaviertrainer
ssh user@server
cd /opt/klaviertrainer
chmod +x start.sh
```

### 2. Install dependencies
```bash
./start.sh   # run once, then Ctrl+C
```

### 3. Set up systemd service
```bash
# Adjust paths in klaviertrainer.service (User, WorkingDirectory)
sudo cp klaviertrainer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable klaviertrainer
sudo systemctl start klaviertrainer
sudo systemctl status klaviertrainer
```

### 4. Set up Nginx
```bash
# Set your domain in nginx.conf
sudo cp nginx.conf /etc/nginx/sites-available/klaviertrainer
sudo ln -s /etc/nginx/sites-available/klaviertrainer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5. HTTPS (Let's Encrypt)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.example.com
```

---

## File Structure

```
klaviertrainer/
├── app.py                      # Flask backend
├── requirements.txt            # Python dependencies
├── start.sh                    # Setup & launch script
├── klaviertrainer-public.html  # Standalone version (no server needed)
├── klaviertrainer.service      # Systemd unit file
├── nginx.conf                  # Nginx reverse proxy config
└── templates/
    ├── login.html              # Login page
    ├── index.html              # Main app (full version)
    └── admin.html              # Admin panel
```

> `klaviertrainer.db`, `.secret_key`, and `uploads/` are auto-generated at runtime and not included in the repository.

---

## Database Schema

```sql
users      (id, username, pw_hash, pw_salt, is_admin, created)
favorites  (id, user_id, title, has_pdf, pdf_name, added)
pdfs       (id, user_id, fav_id, filename, orig_name, size_bytes, uploaded)
```

Backup:
```bash
sqlite3 klaviertrainer.db ".backup backup_$(date +%Y%m%d).db"
```

---

## Environment Variables

| Variable      | Description                        | Default           |
|---------------|------------------------------------|-------------------|
| `SECRET_KEY`  | Flask session secret (important!)  | Auto-generated    |
| `PORT`        | Server port                        | `5000`            |
| `FLASK_DEBUG` | Debug mode (local only!)           | `0`               |

---

## Admin: Manage Users

The admin panel is available at `/admin` when logged in as an admin. To create the first admin via CLI:

```bash
python app.py create-admin <username> <password>
```

---

## PDF Limits

- Max. 30 MB per file (configurable via `MAX_PDF_MB` in `app.py`)
- Nginx must have `client_max_body_size` set accordingly
- PDFs are stored in `uploads/{user_id}/` with a random prefix
