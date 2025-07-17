from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import os
# ---------------------------------------------------------------------------
# DB 초기화 -----------------------------------------------------------------
# ---------------------------------------------------------------------------

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# 환경변수 또는 기본값 사용
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///typing_app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-secret-key")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=7)

db = SQLAlchemy(app)
with app.app_context():
    db.create_all()      # 테이블이 없으면 생성, 있으면 아무 일도 안 함

jwt = JWTManager(app)

# ---------------------------------------------------------------------------
# 모델 정의 -----------------------------------------------------------------
# ---------------------------------------------------------------------------


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    hashed_password = db.Column(db.String(128), nullable=False)
    username = db.Column(db.String(50), nullable=False)
    level = db.Column(db.Integer, default=1)
    experience = db.Column(db.Integer, default=0)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pwd):
        self.hashed_password = generate_password_hash(pwd)

    def check_password(self, pwd):
        return check_password_hash(self.hashed_password, pwd)

class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Sentence(db.Model):
    __tablename__ = "sentences"
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    text = db.Column(db.Text, nullable=False)
    difficulty = db.Column(db.Integer)
    is_approved = db.Column(db.Boolean, default=True)
    uploader_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TypingRecord(db.Model):
    __tablename__ = "typing_records"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    sentence_id = db.Column(db.Integer, db.ForeignKey("sentences.id"))
    wpm = db.Column(db.Float)
    accuracy = db.Column(db.Float)
    total_keys = db.Column(db.Integer)
    mistake_count = db.Column(db.Integer)
    played_at = db.Column(db.DateTime, default=datetime.utcnow)
# ---------------------------------------------------------------------------
# CLI: 초기 DB ----------------------------------------------------------------
# ---------------------------------------------------------------------------

@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized ✅")

# ---------------------------------------------------------------------------
# 기본 라우터 ---------------------------------------------------------------
# ---------------------------------------------------------------------------

@app.route("/")
def health():
    return jsonify({"msg": "Typing API running"})


# ---------------------------------------------------------------------------
# 인증 (회원가입 / 로그인) ----------------------------------------------------
# ---------------------------------------------------------------------------

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    email = data.get("email")
    username = data.get("username")
    password = data.get("password")

    if not all([email, username, password]):
        return jsonify({"msg": "모든 필드를 입력하세요."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "이미 존재하는 이메일."}), 400

    user = User(email=email, username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({"msg": "회원가입 완료"}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"msg": "이메일 또는 비밀번호 오류"}), 401

    token = create_access_token(identity=user.id)
    return jsonify({
        "access_token": token,
        "username": user.username,
        "is_admin": user.is_admin
    }), 200

# ---------------------------------------------------------------------------
# 계정 관리 (프로필) ----------------------------------------------------------
# ---------------------------------------------------------------------------

@app.route("/api/me", methods=["GET"])
@jwt_required()
def me():
    user = User.query.get(get_jwt_identity())
    # 최고 기록 계산 (on‑the‑fly)
    best_record = (
        TypingRecord.query.filter_by(user_id=user.id)
        .order_by(TypingRecord.wpm.desc())
        .first()
    )
    best_wpm = best_record.wpm if best_record else None
    best_accuracy = best_record.accuracy if best_record else None

    return jsonify({
        "email": user.email,
        "username": user.username,
        "level": user.level,
        "experience": user.experience,
        "best_wpm": best_wpm,
        "best_accuracy": best_accuracy,
    })


@app.route("/api/me", methods=["PATCH"])
@jwt_required()
def update_me():
    user = User.query.get(get_jwt_identity())
    data = request.get_json()
    new_username = data.get("username")
    new_password = data.get("password")
    updated = False

    if new_username:
        user.username = new_username
        updated = True
    if new_password:
        user.set_password(new_password)
        updated = True

    if updated:
        db.session.commit()
        return jsonify({"msg": "정보 수정 완료"})
    return jsonify({"msg": "수정할 필드 없음"}), 400

# ---------------------------------------------------------------------------
# 카테고리 ---------------------------------------------------------------
# ---------------------------------------------------------------------------

@app.route("/api/categories", methods=["GET"])
@jwt_required()
def get_categories():
    return jsonify([{"id": c.id, "name": c.name} for c in Category.query.all()])


@app.route("/api/categories", methods=["POST"])
@jwt_required()
def add_category():
    name = request.get_json().get("name")
    if not name:
        return jsonify({"msg": "카테고리 이름 필요"}), 400
    if Category.query.filter_by(name=name).first():
        return jsonify({"msg": "이미 존재"}), 400
    db.session.add(Category(name=name))
    db.session.commit()
    return jsonify({"msg": "카테고리 추가"}), 201


@app.route("/api/categories/<int:cid>", methods=["DELETE"])
@jwt_required()
def delete_category(cid):
    user = User.query.get(get_jwt_identity())
    if not user.is_admin:
        return jsonify({"msg": "관리자만 가능"}), 403
    cat = Category.query.get(cid)
    if not cat:
        return jsonify({"msg": "없음"}), 404
    db.session.delete(cat)
    db.session.commit()
    return jsonify({"msg": "삭제 완료"})

# ---------------------------------------------------------------------------
# 문장 (Sentence) ------------------------------------------------------------
# ---------------------------------------------------------------------------

@app.route("/api/sentences", methods=["GET"])
@jwt_required()
def sentences():
    category_id = request.args.get("category_id")
    q = Sentence.query.filter_by(is_approved=True)
    if category_id:
        q = q.filter_by(category_id=category_id)
    data = [
        {
            "id": s.id,
            "text": s.text,
            "category_id": s.category_id,
            "difficulty": s.difficulty,
        }
        for s in q.all()
    ]
    return jsonify(data)


@app.route("/api/sentences", methods=["POST"])
@jwt_required()
def upload_sentence():
    data = request.get_json()
    category_id, text, difficulty = data.get("category_id"), data.get("text"), data.get("difficulty")
    if not all([category_id, text]):
        return jsonify({"msg": "카테고리·본문 필요"}), 400
    if not Category.query.get(category_id):
        return jsonify({"msg": "잘못된 카테고리"}), 400
    sentence = Sentence(
        category_id=category_id,
        text=text,
        difficulty=difficulty,
        uploader_id=get_jwt_identity(),
        is_approved=True,
    )
    db.session.add(sentence)
    db.session.commit()
    return jsonify({"msg": "문장 업로드"}), 201


@app.route("/api/sentences/<int:sid>", methods=["DELETE"])
@jwt_required()
def delete_sentence(sid):
    user = User.query.get(get_jwt_identity())
    sentence = Sentence.query.get(sid)
    if not sentence:
        return jsonify({"msg": "문장 없음"}), 404
    # 권한 check: 업로더 or 어드민
    if sentence.uploader_id != user.id and not user.is_admin:
        return jsonify({"msg": "권한 없음"}), 403
    db.session.delete(sentence)
    db.session.commit()
    return jsonify({"msg": "문장 삭제"})

# ---------------------------------------------------------------------------
# 연습 기록 -----------------------------------------------------------------
# ---------------------------------------------------------------------------

@app.route("/api/records", methods=["POST"])
@jwt_required()
def save_record():
    data = request.get_json()
    sentence_id, wpm, accuracy = data.get("sentence_id"), data.get("wpm"), data.get("accuracy")
    total_keys = data.get("total_keys")
    mistake_count = data.get("mistake_count")
    if None in [sentence_id, wpm, accuracy]:
        return jsonify({"msg": "필수값 누락"}), 400

    rec = TypingRecord(
        user_id=get_jwt_identity(), sentence_id=sentence_id, wpm=wpm,
        accuracy=accuracy, total_keys=total_keys, mistake_count=mistake_count
    )
    db.session.add(rec)

    # 경험치 & 레벨 계산
    user = User.query.get(get_jwt_identity())
    gained = int(wpm * (accuracy / 100) * 2)
    user.experience += gained
    while user.experience >= user.level * 100:
        user.experience -= user.level * 100
        user.level += 1
    db.session.commit()

    return jsonify({"msg": "저장", "gained_exp": gained, "level": user.level})


@app.route("/api/records", methods=["GET"])
@jwt_required()
def my_records():
    uid = get_jwt_identity()
    recs = (
        TypingRecord.query.filter_by(user_id=uid)
        .order_by(TypingRecord.played_at.desc())
        .all()
    )
    return jsonify([
        {
            "id": r.id,
            "sentence_id": r.sentence_id,
            "wpm": r.wpm,
            "accuracy": r.accuracy,
            "total_keys": r.total_keys,
            "mistake_count": r.mistake_count,
            "played_at": r.played_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for r in recs
    ])

# ---------------------------------------------------------------------------
# 글로벌 랭킹 ---------------------------------------------------------------
# ---------------------------------------------------------------------------

@app.route("/api/highscores", methods=["GET"])
@jwt_required()
def highscores():
    limit = int(request.args.get("limit", 20))
    # 최고 WPM 기준 상위 기록 (한 유저당 하나만) — 서브쿼리 사용
    sub = (
        db.session.query(
            TypingRecord.user_id, db.func.max(TypingRecord.wpm).label("max_wpm")
        )
        .group_by(TypingRecord.user_id)
        .subquery()
    )
    q = (
        db.session.query(User.username, sub.c.max_wpm)
        .join(sub, sub.c.user_id == User.id)
        .order_by(sub.c.max_wpm.desc())
        .limit(limit)
    )
    return jsonify([
        {"username": row.username, "best_wpm": row.max_wpm}
        for row in q.all()
    ])
@app.route('/init-db')
def init_db_route():
    db.create_all()
    return "DB initialized!"

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
