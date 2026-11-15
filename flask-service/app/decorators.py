from flask import jsonify, request
from functools import wraps
import jwt

from app.config import Config

# VALIDASI JWT BEARER TOKEN

def token_required(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        auth_header = request.headers.get("Authorization")

        if not auth_header:

            return jsonify({
                "status": False,
                "message": "Authorization header tidak ditemukan"
            }), 401

        if not auth_header.startswith("Bearer "):

            return jsonify({
                "status": False,
                "message": "Format Authorization harus Bearer Token"
            }), 401

        token = auth_header.split(" ", 1)[1]

        try:

            payload = jwt.decode(
                token,
                Config.JWT_SECRET_KEY,
                algorithms=["HS256"]
            )

            request.user = payload

        except jwt.ExpiredSignatureError:

            return jsonify({
                "status": False,
                "message": "Token sudah expired. Silakan login kembali."
            }), 401

        except jwt.InvalidTokenError:

            return jsonify({
                "status": False,
                "message": "Token tidak valid"
            }), 401

        return f(*args, **kwargs)

    return decorated
