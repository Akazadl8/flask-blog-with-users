# 📝 Flask Blog with Users

A full blog website built with Flask. People can register and log in, read posts and leave comments. The first registered user becomes the admin, who can write, edit and delete posts with a rich-text editor.

## Features

- User registration and login with hashed passwords (Flask-Login + Werkzeug)
- Admin-only create / edit / delete for posts
- Comments with profile pictures (Gravatar), cleaned of unsafe HTML
- Rich-text editing with CKEditor
- SQLite database with SQLAlchemy (users, posts and comments linked together)
- Contact form (optionally emails you)

## Built with

Python, Flask, SQLAlchemy, Flask-Login, Flask-WTF, Bootstrap 5

## How to run

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python main.py
```

Then open **http://127.0.0.1:5002** in your browser.

### Optional settings

| Variable | What it does |
|---|---|
| `FLASK_SECRET_KEY` | Secret key for sessions (set this for any real deployment) |
| `MAIL_ADDRESS` / `MAIL_APP_PASSWORD` | Lets the contact form email you (otherwise messages print in the terminal) |

> The **first account you register is the admin**.
