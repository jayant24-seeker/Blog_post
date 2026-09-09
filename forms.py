from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField
from wtforms.validators import DataRequired, Email, Length
from flask_ckeditor import CKEditorField


# WTForm for creating a blog post
class CreatePostForm(FlaskForm):
    title = StringField("Blog Post Title", validators=[DataRequired(), Length(max=250)])
    subtitle = StringField("Subtitle", validators=[DataRequired(), Length(max=250)])
    img_url = StringField("Blog Image URL", validators=[DataRequired(), Length(max=500)])
    body = CKEditorField("Blog Content", validators=[DataRequired(), Length(max=100000)])
    submit = SubmitField("Submit Post")


# Create a form to register new users
class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    name = StringField("Name", validators=[DataRequired(), Length(max=100)])
    submit = SubmitField("Sign Me Up!")


# Create a form to login existing users
class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Let Me In!")


# Create a form to add comments
class CommentForm(FlaskForm):
    comment_text = CKEditorField("Comment", validators=[DataRequired(), Length(max=5000)])
    submit = SubmitField("Submit Comment")
