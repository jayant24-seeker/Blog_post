import os
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse

import bleach
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from markupsafe import Markup
from sqlalchemy import ForeignKey, Integer, String, Text, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from forms import CommentForm, CreatePostForm, LoginForm, RegisterForm

load_dotenv()

database_url = os.getenv("DATABASE_URL", "sqlite:///posts.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)


class Base(DeclarativeBase):
    pass


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-me"),
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

db = SQLAlchemy(model_class=Base)
db.init_app(app)
Bootstrap5(app)
CKEditor(app)
CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."
gravatar = Gravatar(app, size=100, rating="g", default="retro", use_ssl=True)


ALLOWED_HTML_TAGS = {
    "p", "br", "strong", "em", "u", "s", "blockquote", "ol", "ul", "li",
    "h2", "h3", "h4", "a", "code", "pre",
}
ALLOWED_HTML_ATTRIBUTES = {"a": ["href", "title", "target", "rel"]}


def clean_html(value: str) -> str:
    return bleach.clean(
        value or "",
        tags=ALLOWED_HTML_TAGS,
        attributes=ALLOWED_HTML_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        strip=True,
    )


@app.template_filter("safe_html")
def safe_html(value):
    return Markup(clean_html(value))


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    posts: Mapped[list["BlogPost"]] = relationship(
        back_populates="author", cascade="all, delete-orphan"
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="comment_author", cascade="all, delete-orphan"
    )


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    author: Mapped[User] = relationship(back_populates="posts")
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    # Keep this as text so the original tutorial database remains readable.
    date: Mapped[str] = mapped_column(
        String(250), default=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(500), nullable=False)
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="parent_post", cascade="all, delete-orphan", order_by="Comment.id"
    )


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    comment_author: Mapped[User] = relationship(back_populates="comments")
    post_id: Mapped[int] = mapped_column(ForeignKey("blog_posts.id"), nullable=False)
    parent_post: Mapped[BlogPost] = relationship(back_populates="comments")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def owner_or_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(post_id, *args, **kwargs):
        post = db.get_or_404(BlogPost, post_id)
        if post.author_id != current_user.id and current_user.role != "admin":
            abort(403)
        return view(post, *args, **kwargs)

    return wrapped


def is_valid_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@app.template_filter("format_date")
def format_date(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%b %d, %Y")
    try:
        return datetime.fromisoformat(str(value)).strftime("%b %d, %Y")
    except ValueError:
        pass
    return value


@app.context_processor
def inject_helpers():
    return {
        "is_admin": current_user.is_authenticated and current_user.role == "admin",
        "current_year": datetime.now(timezone.utc).year,
    }


def migrate_existing_database():
    inspector = inspect(db.engine)
    if "users" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "role" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user' NOT NULL"))
    db.session.execute(text("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''"))
    first_user = db.session.scalar(db.select(User).order_by(User.id))
    admin_exists = db.session.scalar(db.select(User.id).where(User.role == "admin"))
    if first_user and not admin_exists:
        first_user.role = "admin"
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    if admin_email:
        configured_admin = db.session.scalar(db.select(User).where(User.email == admin_email))
        if configured_admin:
            configured_admin.role = "admin"
    db.session.commit()


with app.app_context():
    db.create_all()
    migrate_existing_database()


@app.route("/healthz")
def healthz():
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "ok"}, 200
    except Exception:
        db.session.rollback()
        return {"status": "error"}, 503


@app.route("/")
def get_all_posts():
    posts = db.session.scalars(db.select(BlogPost).order_by(BlogPost.date.desc())).all()
    return render_template("index.html", all_posts=posts)


@app.route("/dashboard")
@login_required
def dashboard():
    posts = db.session.scalars(
        db.select(BlogPost).where(BlogPost.author_id == current_user.id).order_by(BlogPost.date.desc())
    ).all()
    return render_template("dashboard.html", posts=posts)


@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if db.session.scalar(db.select(User).where(User.email == email)):
            flash("That email is already registered. Please log in.", "warning")
            return redirect(url_for("login"))
        user = User(
            email=email,
            name=form.name.data.strip(),
            password=generate_password_hash(form.password.data),
            role="admin" if email == os.getenv("ADMIN_EMAIL", "").strip().lower() else "user",
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Welcome! Your account is ready.", "success")
        return redirect(url_for("get_all_posts"))
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).where(User.email == form.email.data.strip().lower()))
        if not user or not check_password_hash(user.password, form.password.data):
            flash("Email or password is incorrect.", "danger")
            return redirect(url_for("login"))
        login_user(user)
        return redirect(request.args.get("next") or url_for("get_all_posts"))
    return render_template("login.html", form=form)


@app.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("get_all_posts"))


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("Please log in to comment.", "warning")
            return redirect(url_for("login", next=url_for("show_post", post_id=post.id)))
        comment = Comment(
            text=clean_html(comment_form.comment_text.data),
            comment_author=current_user,
            parent_post=post,
        )
        db.session.add(comment)
        db.session.commit()
        flash("Comment added.", "success")
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("post.html", post=post, form=comment_form)


@app.route("/new-post", methods=["GET", "POST"])
@login_required
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        if not is_valid_url(form.img_url.data):
            flash("Please use a valid image URL beginning with http or https.", "danger")
        else:
            post = BlogPost(
                title=form.title.data.strip(),
                subtitle=form.subtitle.data.strip(),
                body=clean_html(form.body.data),
                img_url=form.img_url.data.strip(),
                author=current_user,
            )
            db.session.add(post)
            db.session.commit()
            flash("Your post is live.", "success")
            return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=form, is_edit=False)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@owner_or_admin_required
def edit_post(post, post_id=None):
    form = CreatePostForm(obj=post)
    if form.validate_on_submit():
        if not is_valid_url(form.img_url.data):
            flash("Please use a valid image URL beginning with http or https.", "danger")
        else:
            post.title = form.title.data.strip()
            post.subtitle = form.subtitle.data.strip()
            post.img_url = form.img_url.data.strip()
            post.body = clean_html(form.body.data)
            db.session.commit()
            flash("Post updated.", "success")
            return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=form, is_edit=True, post=post)


@app.post("/delete/<int:post_id>")
@owner_or_admin_required
def delete_post(post, post_id=None):
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "success")
    return redirect(url_for("get_all_posts"))


@app.post("/comment/<int:comment_id>/delete")
@login_required
def delete_comment(comment_id):
    comment = db.get_or_404(Comment, comment_id)
    if comment.author_id != current_user.id and current_user.role != "admin":
        abort(403)
    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    flash("Comment deleted.", "success")
    return redirect(url_for("show_post", post_id=post_id))


@app.route("/admin")
@admin_required
def admin_dashboard():
    users = db.session.scalars(db.select(User).order_by(User.id)).all()
    posts = db.session.scalars(db.select(BlogPost).order_by(BlogPost.date.desc())).all()
    return render_template("admin.html", users=users, posts=posts)


@app.post("/admin/users/<int:user_id>/role")
@admin_required
def update_role(user_id):
    user = db.get_or_404(User, user_id)
    role = request.form.get("role", "user")
    if role not in {"user", "admin"}:
        abort(400)
    if user.id == current_user.id and role != "admin":
        flash("You cannot remove your own admin access.", "warning")
    else:
        user.role = role
        db.session.commit()
        flash("User role updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        if not request.form.get("name", "").strip() or not request.form.get("email", "").strip() or not request.form.get("message", "").strip():
            flash("Please complete all contact fields.", "danger")
        else:
            flash("Thanks, your message has been received.", "success")
            return redirect(url_for("contact"))
    return render_template("contact.html")


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="You do not have permission to do that."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="That page could not be found."), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
