from flask import jsonify, request
from datetime import datetime, timedelta, timezone
import jwt

from app.config import Config

def login():
    data = request.get_json()

    if not data:
        return jsonify({
            "status": False,
            "message": "Request body tidak ditemukan"
        }), 400

    username = data.get("username")
    password = data.get("password")

    # TEST LOGIN SEMENTARA

    if username != "admin" or password != "123456":
        return jsonify({
            "status": False,
            "message": "Username atau password salah"
        }), 401

    now = datetime.now(timezone.utc)

    payload = {
        "username": username,
        "iat": now,
        "exp": now + timedelta(
            minutes=Config.JWT_EXPIRE_MINUTES
        )
    }

    token = jwt.encode(
        payload,
        Config.JWT_SECRET_KEY,
        algorithm="HS256"
    )

    return jsonify({
        "status": True,
        "message": "Login berhasil",
        "token": token,
        "token_type": "Bearer",
        "expires_in": Config.JWT_EXPIRE_MINUTES * 60
    })