import os
import re
from datetime import datetime
from collections import Counter

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, send_from_directory, jsonify, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from passlib.hash import pbkdf2_sha256
from flask_migrate import Migrate
from PyPDF2 import PdfReader
import docx
from docx import Document
import stripe
import openai

# --- CONFIG ---
openai.api_key = os.getenv("OPENAI_API_KEY")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
API_KEY = os.getenv("API_KEY")

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'changeme-in-prod')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'database.db')

app.config.update({
    'UPLOAD_FOLDER': UPLOAD_FOLDER,
    'SQLALCHEMY_DATABASE_URI': f"sqlite:///{DB_PATH}",
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
})
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# --- MODELS ---
class User(db.Model, UserMixin):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    role     = db.Column(db.String(20), nullable=False)
    area     = db.Column(db.String(100), nullable=True)
    credits  = db.Column(db.Integer, default=0)
    email    = db.Column(db.String(120), nullable=True)
    address  = db.Column(db.String(200), nullable=True)
    phone    = db.Column(db.String(40), nullable=True)
    resumes  = db.relationship('Resume', backref='user', lazy=True)

class Resume(db.Model):
    id                     = db.Column(db.Integer, primary_key=True)
    filename               = db.Column(db.String(260), nullable=False)
    upload_time            = db.Column(db.DateTime, default=datetime.utcnow)
    user_id                = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    summary                = db.Column(db.Text, nullable=True)
    generated_cover_letter = db.Column(db.Text, nullable=True)
    tags                   = db.relationship('ResumeTag', backref='resume', lazy=True, cascade="all, delete-orphan")

class ResumeTag(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    tag       = db.Column(db.String(100), nullable=False)
    resume_id = db.Column(db.Integer, db.ForeignKey('resume.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

ALLOWED_EXTENSIONS = {'pdf', 'docx'}
STOPWORDS = {'the','and','for','with','that','this','from','your','have','will','project','manager','experience'}

def require_api_key():
    key = request.headers.get("Authorization", "")
    if key != f"Bearer {API_KEY}":
        abort(401, "Invalid API key")

# ... [other helpers unchanged: allowed_file, extract_text, parse_and_save_tags, generate_cv_summary] ...

def generate_cover_letter_text(cv_text: str, job_desc: str, tone: str) -> str:
    prompt = (
        f"You are an expert career coach. "
        f"Write a {tone} cover letter for a candidate whose CV is below, applying for this job:\n\n"
        f"=== CV ===\n{cv_text[:3000]}\n\n"
        f"=== Job Description ===\n{job_desc[:2000]}\n\n"
        "The letter should be 3–4 paragraphs, highlight key skills, match tone, and end with a strong closing."
    )
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        max_tokens=500
    )
    return resp.choices[0].message.content.strip()

# --- ROUTES ---
@app.route('/')
@login_required
def home():
    # unchanged…

@app.route('/api/slack_search', methods=['POST'])
def api_slack_search():
    require_api_key()
    data = request.get_json() or {}
    area   = data.get("area","").lower()
    skills = [s.lower() for s in data.get("skills",[])]
    users = User.query.filter(User.area.ilike(f"%{area}%")) if area else User.query
    results = []
    for u in users.all():
        for cv in u.resumes:
            tags = [t.tag for t in cv.tags]
            if all(skill in tags for skill in skills):
                results.append({
                    "user": {"id":u.id,"name":u.name,"area":u.area},
                    "resume": {"id":cv.id,"upload_time":cv.upload_time.isoformat(),"tags":tags}
                })
    return jsonify(results=results)

@app.route('/api/cv/<int:cv_id>/download_link', methods=['GET'])
def api_cv_download(cv_id):
    require_api_key()
    # local file download
    url = url_for('download_resume', resume_id=cv_id, _external=True)
    return jsonify(download_url=url)

@app.route('/contractor/cover_letter/<int:resume_id>', methods=['GET','POST'])
@login_required
def generate_cover_letter(resume_id):
    # unchanged…

@app.route('/download_cover_letter/<int:resume_id>')
@login_required
def download_cover_letter(resume_id):
    # unchanged…

# ... [other existing routes...]

# Failsafe: ensure tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
