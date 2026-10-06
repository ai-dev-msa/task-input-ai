from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from alokasi_agent import run
import json
import os
import requests



load_dotenv("/var/www/html/msaai/.env", override=True)

app = Flask(__name__)

import sys
sys.path.insert(0, "/var/www/html/msaai/ai-service/app")

from modules.proyek import proyek_bp
app.register_blueprint(proyek_bp)

#cors ini buat nembak endpoint python ke mis
CORS(
    app,
    resources={
        r"/chat": {
            "origins": [
                "https://appweb.mitrasinergi.co.id"
            ]
        },
        r"/proyek": {
            "origins": [
                "https://appweb.mitrasinergi.co.id"
            ]
        }
    },
    methods=["GET","POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"]
)
#++VVVVVV Client OpenAI (DIHAPUS dari sini karena
# kode AI track): client dibuat sendiri di src/alokasi_agent/llm.py
# (complete()) dari OPENAI_API_KEY
#//++VVVVVV


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "success": True,
        "message": "AI Service running"
    })


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(silent=True) or {}

        # message is the only required field.
        if not data or not data.get("message"):
            return jsonify({
                "success": False,
                "type": "error",
                "reply": "message wajib diisi",
                "history": []
            }), 400

        user_message = data.get("message")
        user_id = data.get("user_id")

        #++VVVVVV Format tools untuk Responses API (DIHAPUS dari sini karena
        # kode AI track): sekarang ada di src/alokasi_agent/schema.py ->
        # CREATE_ALOKASI_TOOL
        #//++VVVVVV

        #++VVVVVV System prompt (DIHAPUS dari sini karena
        # kode AI track): sekarang ada di src/alokasi_agent/prompt.py ->
        # PROMPT_TEMPLATE
        #//++VVVVVV

        #++VVVVVV Panggil Responses API (DIHAPUS dari sini karena
        # kode AI track): sekarang ada di src/alokasi_agent/llm.py ->
        # complete()
        #//++VVVVVV

        # 1) All AI logic lives in run(). It returns (envelope, history);
        #    the envelope already contains reply + history.
        envelope, _history = run(
            user_message,
            user_name=data.get("user_name") or "",
            employees=data.get("employees") or [],
            projects=data.get("projects") or [],
            history=data.get("history") or [],
            user_id=user_id,
        )
        body = dict(envelope)

        #++VVVVVV Cari function call / ambil arguments (DIHAPUS dari sini karena
        # kode AI track): sekarang ada di src/alokasi_agent/agent.py -> run(),
        # yang mengembalikan envelope berisi type, arguments, reply, history
        #//++VVVVVV

        # 2) The backend half (kept from the old file): only a confirmed
        #    tool call is written to the ERP.
        if body["type"] == "function_call":
            # arguments is a JSON string: one object (single row) or an
            # array of objects (several rows, FR-08).
            arguments = json.loads(body["arguments"])
            single_row = isinstance(arguments, dict)
            rows = [arguments] if single_row else arguments

            # token = os.getenv("ERP_API_TOKEN")
            token = get_erp_token()

            #++VVVVVV TEST TOKEN ERP
            response_validate = requests.get(
                "https://appweb.mitrasinergi.co.id/msa/apiv1/auth/validate",
                headers={
                    "Authorization": f"Bearer {token}"
                },
                timeout=30
            )

            print("VALIDATE HTTP:", response_validate.status_code)
            print("VALIDATE RESPONSE:", response_validate.text)
            #//++VVVVVV

            #++VVVVVV Kirim data ke API ERP CI3
            # One POST per row.
            results = []
            for row in rows:
                response_ci3 = requests.post(
                    "https://appweb.mitrasinergi.co.id/msa/apiv1/aialokasiharian/createAlokasi",
                    json=row,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30
                )

                #++VVVVVV DEBUG RESPONSE
                print("CI3 HTTP STATUS:", response_ci3.status_code)
                print("CI3 RESPONSE:", response_ci3.text)
                #//++VVVVVV

                #++VVVVVV Ambil response dari API ERP CI3
                hasil_ci3 = response_ci3.json()
                results.append(hasil_ci3)
                #//++VVVVVV

            # One row keeps hasil_ci3 an object (the shape callers know);
            # several rows return an array of results.
            body["hasil_ci3"] = results[0] if single_row else results
            return jsonify(body)
            #//++VVVVVV

        #++VVVVVV Jika tidak ada function call (DIHAPUS dari sini karena
        # kode AI track): balasan teks sudah disiapkan run() di
        # src/alokasi_agent/agent.py (ada di field reply envelope)
        return jsonify(body)
        #//++VVVVVV


    except Exception as e:
        # Log the real error here (server-side only); the caller gets a
        # generic message, never the exception text.
        print("ERROR /chat:", repr(e))
        return jsonify({
            "success": False,
            "type": "error",
            "function_name": "",
            "arguments": "",
            "raw_message": user_message,
            "user_id": user_id,
            "reply": "Terjadi kesalahan, coba lagi.",
            "history": data.get("history") or []
        })


#buat login otomatis ke mis biar langsung dapetin tokennya 
def get_erp_token():

    username = os.getenv("ERP_API_USERNAME")
    password = os.getenv("ERP_API_PASSWORD")

    if not username or not password:
        raise Exception("ERP_API_USERNAME / ERP_API_PASSWORD belum tersedia")

    response_login = requests.post(
        "https://appweb.mitrasinergi.co.id/msa/apiv1/auth/login",
        data={
            "username": username,
            "password": password
        },
        timeout=30
    )

    #++VVVVVV Cek response HTTP
    if response_login.status_code != 200:
        raise Exception(
            "Login ERP gagal. HTTP " +
            str(response_login.status_code) +
            " | Response: " +
            response_login.text
        )
    #//++VVVVVV

    #++VVVVVV Parse JSON response
    hasil_login = response_login.json()
    #//++VVVVVV

    #++VVVVVV Response login berbentuk list
    if not isinstance(hasil_login, list) or not hasil_login:
        raise Exception(
            "Format response login ERP tidak sesuai. Response: " +
            str(hasil_login)
        )
    #//++VVVVVV

    #++VVVVVV Ambil object login pertama
    data_login = hasil_login[0]
    #//++VVVVVV

    #++VVVVVV Ambil access token
    token = data_login.get("access_token")

    if not token:
        raise Exception(
            "Access token tidak ditemukan dari response login ERP"
        )
    #//++VVVVVV

    return token

#ini buat kalau server mati/venv ga jalan biar gausah debug/gausah nampilin eror
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5001,
        debug=False
    )
