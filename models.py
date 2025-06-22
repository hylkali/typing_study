from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# User table
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    hashed_password = db.Column(db.String(128), nullable=False)
    username = db.Column(db.String(50), nullable=False)
    level = db.Column(db.Integer, default=1)
    experience = db.Column(db.Integer, default=0)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.hashed_password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.hashed_password, password)

# Category table
class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

# Sentence table
class Sentence(db.Model):
    __tablename__ = 'sentences'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    text = db.Column(db.Text, nullable=False)
    difficulty = db.Column(db.Integer)
    is_approved = db.Column(db.Boolean, default=True)
    uploader_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    category = db.relationship('Category', backref=db.backref('sentences', lazy=True))
    uploader = db.relationship('User', backref=db.backref('uploaded_sentences', lazy=True))

# Typing record table
class TypingRecord(db.Model):
    __tablename__ = 'typing_records'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    sentence_id = db.Column(db.Integer, db.ForeignKey('sentences.id'))
    wpm = db.Column(db.Float)
    accuracy = db.Column(db.Float)
    total_keys = db.Column(db.Integer)
    mistake_count = db.Column(db.Integer)
    played_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('typing_records', lazy=True))
    sentence = db.relationship('Sentence', backref=db.backref('records', lazy=True))
