# Jayant's Blog

A multi-user Flask blog where anyone can register, publish posts, edit or delete their own posts, and comment on other posts. Admins can manage all posts and user roles.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask --app main run --port 5001
```

The default local database is SQLite at `instance/posts.db`. The first existing user becomes an admin; set `ADMIN_EMAIL` to promote a specific account. For Render, set `DATABASE_URL` to a Render PostgreSQL connection string and set a long random `SECRET_KEY`.

## Render

Create a PostgreSQL database, create a web service from this repository, and use the included `render.yaml` or these commands:

- Build: `pip install -r requirements.txt`
- Start: `gunicorn main:app`

Required environment variables are `SECRET_KEY` and `DATABASE_URL`. `ADMIN_EMAIL` is optional and promotes that registered account to admin on startup.

## Reset a forgotten password

From the project directory, run:

```bash
python reset_password.py admin@email.com
```

The script prompts for a new password and stores only its secure hash.
