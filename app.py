from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash

# 내부 모듈에서 models 불러오기
from models import db, User, Category, Sentence, TypingRecord

# Flask 앱 생성
app = Flask(__name__)
CORS(app)

# 환경설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///typing_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'your-secret-key'  # 실제 배포 시 환경변수로 관리
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

# 확장 모듈 초기화
db.init_app(app)
jwt = JWTManager(app)

# DB 초기화 라우터 (개발용)
@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized.")

# 기본 라우터 (서버 테스트용)
@app.route('/')
def home():
    return jsonify({"message": "Typing App API Running."})

# 회원가입 API
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    username = data.get('username')
    password = data.get('password')

    if not email or not username or not password:
        return jsonify({"msg": "모든 필드를 입력해주세요."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "이미 존재하는 이메일입니다."}), 400

    user = User(email=email, username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"msg": "회원가입 성공"}), 201

# 로그인 API
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        access_token = create_access_token(identity=user.id)
        return jsonify({"access_token": access_token, "username": user.username}), 200
    else:
        return jsonify({"msg": "이메일 또는 비밀번호가 올바르지 않습니다."}), 401

# 카테고리 목록 조회
@app.route('/api/categories', methods=['GET'])
@jwt_required()
def get_categories():
    categories = Category.query.all()
    result = [{"id": c.id, "name": c.name} for c in categories]
    return jsonify(result), 200

# 새 카테고리 추가 (모든 사용자 가능)
@app.route('/api/categories', methods=['POST'])
@jwt_required()
def add_category():
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({"msg": "카테고리 이름을 입력해주세요."}), 400

    if Category.query.filter_by(name=name).first():
        return jsonify({"msg": "이미 존재하는 카테고리입니다."}), 400

    category = Category(name=name)
    db.session.add(category)
    db.session.commit()
    return jsonify({"msg": "카테고리 추가 성공"}), 201

# 카테고리 삭제 (본인+관리자만 가능, 단순화: 관리자만 삭제 가능)
@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
@jwt_required()
def delete_category(category_id):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user.is_admin:
        return jsonify({"msg": "관리자만 삭제할 수 있습니다."}), 403

    category = Category.query.get(category_id)
    if not category:
        return jsonify({"msg": "카테고리를 찾을 수 없습니다."}), 404

    db.session.delete(category)
    db.session.commit()
    return jsonify({"msg": "카테고리 삭제 성공"}), 200

# 선택한 카테고리의 문장 제공
@app.route('/api/sentences', methods=['GET'])
@jwt_required()
def get_sentences():
    category_id = request.args.get('category_id')
    query = Sentence.query.filter_by(is_approved=True)
    if category_id:
        query = query.filter_by(category_id=category_id)

    sentences = query.all()
    result = [{
        "id": s.id,
        "text": s.text,
        "category_id": s.category_id,
        "difficulty": s.difficulty
    } for s in sentences]
    return jsonify(result), 200

# 새 문장 업로드 (모든 사용자 가능)
@app.route('/api/sentences', methods=['POST'])
@jwt_required()
def upload_sentence():
    data = request.get_json()
    category_id = data.get('category_id')
    text = data.get('text')
    difficulty = data.get('difficulty')
    user_id = get_jwt_identity()

    if not category_id or not text:
        return jsonify({"msg": "카테고리와 문장 내용을 입력해주세요."}), 400

    category = Category.query.get(category_id)
    if not category:
        return jsonify({"msg": "유효하지 않은 카테고리입니다."}), 400

    sentence = Sentence(
        category_id=category_id,
        text=text,
        difficulty=difficulty,
        uploader_id=user_id,
        is_approved=True
    )
    db.session.add(sentence)
    db.session.commit()

    return jsonify({"msg": "문장 업로드 성공"}), 201

# 연습 기록 저장 API
@app.route('/api/records', methods=['POST'])
@jwt_required()
def save_record():
    data = request.get_json()
    user_id = get_jwt_identity()
    sentence_id = data.get('sentence_id')
    wpm = data.get('wpm')
    accuracy = data.get('accuracy')
    total_keys = data.get('total_keys')
    mistake_count = data.get('mistake_count')

    if not sentence_id or wpm is None or accuracy is None:
        return jsonify({"msg": "필수 기록 데이터가 누락되었습니다."}), 400

    record = TypingRecord(
        user_id=user_id,
        sentence_id=sentence_id,
        wpm=wpm,
        accuracy=accuracy,
        total_keys=total_keys,
        mistake_count=mistake_count
    )
    db.session.add(record)
    db.session.commit()

    # 경험치 계산 및 레벨 업데이트
    user = User.query.get(user_id)
    gained_exp = int(wpm * (accuracy / 100) * 2)
    user.experience += gained_exp
    while user.experience >= user.level * 100:
        user.experience -= user.level * 100
        user.level += 1
    db.session.commit()

    return jsonify({"msg": "기록 저장 및 경험치 업데이트 성공", "gained_exp": gained_exp, "level": user.level}), 201

# 연습 기록 조회 API
@app.route('/api/records', methods=['GET'])
@jwt_required()
def get_records():
    user_id = get_jwt_identity()
    records = TypingRecord.query.filter_by(user_id=user_id).order_by(TypingRecord.played_at.desc()).all()

    result = [{
        "id": r.id,
        "sentence_id": r.sentence_id,
        "wpm": r.wpm,
        "accuracy": r.accuracy,
        "total_keys": r.total_keys,
        "mistake_count": r.mistake_count,
        "played_at": r.played_at.strftime("%Y-%m-%d %H:%M:%S")
    } for r in records]

    return jsonify(result), 200

# Flask 실행 (개발용)
if __name__ == '__main__':
    app.run(debug=True)
