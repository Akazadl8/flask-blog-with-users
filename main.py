import hashlib
import os
import smtplib
from datetime import date
from functools import wraps

import nh3
from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Integer, String, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import generate_password_hash, check_password_hash

from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("FLASK_SECRET_KEY", "change-me-in-production")
ckeditor = CKEditor(app)
Bootstrap5(app)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# CREATE DATABASE
class Base(DeclarativeBase):
    pass


app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI", "sqlite:///posts.db")
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(250), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)

    posts = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="comment_author")


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    author = relationship("User", back_populates="posts")

    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    # Deleting a post also deletes its comments
    comments = relationship("Comment", back_populates="parent_post", cascade="all, delete-orphan")


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    comment_author = relationship("User", back_populates="comments")

    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("blog_posts.id"))
    parent_post = relationship("BlogPost", back_populates="comments")

    text: Mapped[str] = mapped_column(Text, nullable=False)


with app.app_context():
    db.create_all()


@app.template_filter("gravatar")
def gravatar(email, size=100):
    """Profile picture for a commenter, from gravatar.com."""
    email_hash = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{email_hash}?s={size}&d=retro"


@app.context_processor
def inject_year():
    return {"current_year": date.today().year}


# Admin-only decorator: the first registered user (id 1) is the admin
def admin_only(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 1:
            abort(403)
        return func(*args, **kwargs)
    return wrapper


@login_manager.user_loader
def load_user(user_id):
    # Return None (not a 404) if the user no longer exists, so the visitor is simply logged out
    return db.session.get(User, int(user_id))


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = db.session.execute(db.select(User).where(User.email == email)).scalar()
        if user:
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for("login"))

        hashed_salted_pass = generate_password_hash(
            password=form.password.data,
            method="pbkdf2:sha256",
            salt_length=8
        )
        new_user = User(
            email=email,
            password=hashed_salted_pass,
            name=form.name.data.strip()
        )
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        return redirect(url_for("get_all_posts"))

    return render_template("register.html", form=form, current_user=current_user)


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        password = form.password.data

        user = db.session.execute(db.select(User).where(User.email == email)).scalar()

        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('login'))
        if not check_password_hash(user.password, password):
            flash("Password incorrect, please try again.")
            return redirect(url_for('login'))

        login_user(user)
        return redirect(url_for('get_all_posts'))

    return render_template("login.html", form=form, current_user=current_user)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    posts = db.session.execute(db.select(BlogPost).order_by(BlogPost.id.desc())).scalars().all()
    return render_template("index.html", all_posts=posts, current_user=current_user)


# Logged-in users can comment on posts
@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to log in or register to comment.")
            return redirect(url_for("login"))

        new_comment = Comment(
            # Comments come from any user, so strip out unsafe HTML (scripts etc.)
            text=nh3.clean(comment_form.comment.data),
            comment_author=current_user,
            parent_post=requested_post
        )
        db.session.add(new_comment)
        db.session.commit()
        return redirect(url_for("show_post", post_id=post_id))
    return render_template("post.html", post=requested_post,
                           current_user=current_user, form=comment_form)


# Only the admin can create, edit or delete posts
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, current_user=current_user)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, current_user=current_user)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html", current_user=current_user)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        data = request.form
        send_email(data.get("name", ""), data.get("email", ""), data.get("phone", ""), data.get("message", ""))
        return render_template("contact.html", msg_sent=True, current_user=current_user)
    return render_template("contact.html", msg_sent=False, current_user=current_user)


def send_email(name, email, phone, message):
    """Email the contact form to the site owner if mail settings are configured,
    otherwise just print it to the console."""
    email_message = f"Subject:New Blog Message\n\nName: {name}\nEmail: {email}\nPhone: {phone}\nMessage: {message}"
    sender = os.environ.get("MAIL_ADDRESS")
    password = os.environ.get("MAIL_APP_PASSWORD")
    if not sender or not password:
        print("Contact form message (set MAIL_ADDRESS and MAIL_APP_PASSWORD to email it):\n" + email_message)
        return
    try:
        with smtplib.SMTP(os.environ.get("MAIL_SMTP", "smtp.gmail.com"), 587) as connection:
            connection.starttls()
            connection.login(sender, password)
            connection.sendmail(sender, sender, email_message.encode("utf-8"))
    except (smtplib.SMTPException, OSError) as error:
        print(f"Could not send the contact email: {error}")


if __name__ == "__main__":
    app.run(debug=True, port=5002)
