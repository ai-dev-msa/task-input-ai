from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from alokasi_agent import run
import json
import os
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo



load_dotenv("/var/www/html/msaai/.env", override=True)

app = Flask(__name__)

import sys
sys.path.insert(0, "/var/www/html/msaai/ai-service/app")

from modules.proyek import proyek_bp, controller
app.register_blueprint(proyek_bp)

from modules.karyawan import karyawan_bp
from modules.karyawan.routes import controller as karyawan_controller
app.register_blueprint(karyawan_bp)

# Satu TTL untuk cache proyek & token ERP (detik).
CACHE_TTL = float(os.getenv("ALOKASI_CACHE_TTL", "300"))
_cache = {}


def _cache_get(key):
    hit = _cache.get(key)
    if hit and time.monotonic() < hit[1]:
        return hit[0]
    return None


def _cache_set(key, value):
    _cache[key] = (value, time.monotonic() + CACHE_TTL)


def _names_from(data):
    """Ambil nama proyek dari response MIS: string dipakai apa adanya,
    dict dicoba lewat key nama yang umum, sisanya dilewati."""
    if isinstance(data, dict):
        data = data.get("data") or data.get("hasil") or []
    names = []
    for item in data or []:
        if isinstance(item, str) and item.strip():
            names.append(item)
        elif isinstance(item, dict):
            for key in ("nama", "name", "nama_proyek"):
                if item.get(key):
                    names.append(str(item[key]))
                    break
    return names


def get_projects():
    """Daftar proyek MSA+WIN tahun berjalan, digabung dan di-cache.
    Kalau gagal, kembalikan [] dan biarkan /chat pakai projects dari body."""
    cached = _cache_get("projects")
    if cached is not None:
        return cached
    names = []
    ok = True
    try:
        token = get_erp_token()
        tahun = str(datetime.now(ZoneInfo("Asia/Jakarta")).year)
        for fetch in (controller.getProyekMSAByYear, controller.getProyekWINByYear):
            response, status = fetch(tahun, token)
            if status == 200:
                names += _names_from(response.get_json().get("data"))
            else:
                ok = False
    except Exception as exc:
        print("get_projects gagal:", repr(exc))
        ok = False
    # Satu sumber gagal -> buang hasil parsial, jangan cache setengah daftar.
    if not ok:
        names = []
    # Dedupe case-insensitive, urutan pertama dipertahankan.
    seen = set()
    merged = []
    for name in names:
        key = name.strip().casefold()
        if key not in seen:
            seen.add(key)
            merged.append(name.strip())
    _cache_set("projects", merged)
    return merged


def get_employees():
    """Daftar karyawan aktif dari MIS, di-cache.
    Kalau gagal, kembalikan [] dan biarkan /chat pakai employees dari body."""
    cached = _cache_get("employees")
    if cached is not None:
        return cached
    names = []
    try:
        token = get_erp_token()
        response, status = karyawan_controller.getListKaryawanAktif(token)
        if status == 200:
            names = _names_from(response.get_json().get("data"))
    except Exception as exc:
        print("get_employees gagal:", repr(exc))
    # Dedupe case-insensitive, urutan pertama dipertahankan.
    seen = set()
    merged = []
    for name in names:
        key = name.strip().casefold()
        if key not in seen:
            seen.add(key)
            merged.append(name.strip())
    _cache_set("employees", merged)
    return merged

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
        # Proyek & karyawan dari endpoint server (cached); body hanya fallback.
        projects = get_projects() or (data.get("projects") or [])
        employees = get_employees() or (data.get("employees") or [])
        envelope, _history = run(
            user_message,
            user_name=data.get("user_name") or "",
            employees=employees,
            projects=projects,
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
    cached = _cache_get("erp_token")
    if cached is not None:
        return cached

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

    _cache_set("erp_token", token)
    return token

#ini buat kalau server mati/venv ga jalan biar gausah debug/gausah nampilin eror
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5001,
        debug=False
    )
