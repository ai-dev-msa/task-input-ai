from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import json
import os
import requests
import time # jangan lupa tambahin karena ada time.monotonic //notes
from datetime import datetime # jangan lupa tambahin karena ada time.monotonic //notes
from zoneinfo import ZoneInfo # jangan lupa tambahin karena ada time.monotonic //notes

import sys
sys.path.insert(0, "/var/www/html/msaai/ai-service/app/src")

import threading #tambahan ihsan 2 11 2026 (install plugin)
from watchdog.observers import Observer #tambahan ihsan 2 11 2026 (install plugin)
from watchdog.events import FileSystemEventHandler #tambahan ihsan 2 11 2026 (install plugin)

from alokasi_agent import run



load_dotenv("/var/www/html/msaai/.env", override=True)

app = Flask(__name__)


#register controller-cotroller modul yang udah dibuat di src
from modules.proyek import proyek_bp
from modules.proyek.routes import controller as proyek_controller
app.register_blueprint(proyek_bp)

from modules.karyawan import karyawan_bp #tiap kali bikin module langsung register ke sini yak //notes
from modules.karyawan.routes import controller as karyawan_controller
app.register_blueprint(karyawan_bp) #//notes

# Satu TTL untuk cache proyek & token ERP (detik).
CACHE_TTL = float(os.getenv("ALOKASI_CACHE_TTL", "300"))
_cache = {}

#tambahan ihsan 2 11 2026 (auto save code tanpa restart server)
class AutoReloadHandler(FileSystemEventHandler):

    def __init__(self):
        self.timer = None
        self.lock = threading.Lock()

    def on_any_event(self, event):
        if event.event_type not in ('modified', 'created', 'deleted', 'moved'):
            return

        if event.is_directory:
            return

        path = event.src_path

        if not path.endswith('.py'):
            return

        if '__pycache__' in path:
            return

        with self.lock:
            if self.timer:
                self.timer.cancel()

            self.timer = threading.Timer(1.5, self.restart_app)
            self.timer.daemon = True
            self.timer.start()

    def restart_app(self):
        print(
            "Perubahan file Python terdeteksi. Menghentikan aplikasi untuk restart...",
            flush=True
        )

        os.kill(os.getpid(), 15)
# ====================

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
        print("Menggunakan cache projects:", len(cached), flush=True) # debug
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
        #()()())( DEBUG DAFTAR PROYEK - AWAL
        print("Tahun proyek:", tahun, flush=True)
        print("Jumlah nama proyek sebelum merge:", len(names), flush=True)
        print(
            "Proyek Bandung/OPRS:",
            [
                name for name in names
                if "bandung" in name.lower() or "oprs" in name.lower()
            ],
            flush=True
        )
        #()()())( DEBUG DAFTAR PROYEK - AKHIR
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
    #()()())( DEBUG HASIL AKHIR PROJECTS - AWAL
    print("Jumlah proyek setelah merge:", len(merged), flush=True)
    print(
        "Hasil akhir OPRS Bandung:",
        [
            name for name in merged
            if "bandung" in name.lower() or "oprs" in name.lower()
        ],
        flush=True
    )
    #()()())( DEBUG HASIL AKHIR PROJECTS - AKHIR
    return merged

def check_project_by_name(nama_proyek):
    try:
        token = get_erp_token()

        response, status = proyek_controller.getProyekByName(
            nama_proyek,
            token
        )

        if status != 200:
            return None

        result = response.get_json() or {}

        if not result.get("success"):
            return None

        hasil = result.get("data", [])

        while isinstance(hasil, dict) and "data" in hasil:
            hasil = hasil["data"]

        if isinstance(hasil, dict):
            hasil = [hasil]

        if not isinstance(hasil, list):
            return None

        # nama_dicari = nama_proyek.strip().casefold()
        nama_dicari = str(nama_proyek or "").strip().casefold()


        return [
            item for item in hasil
            if isinstance(item, dict)
            and nama_dicari in str(item.get("nama_proyek", "")).strip().casefold()
                # == nama_dicari
        ]

    except Exception as exc:
        print("check_project_by_name gagal:", repr(exc), flush=True)
        return None

def get_employees():
    cached = _cache_get("employees")

    if cached is not None:
        return cached

    employees = []

    try:
        token = get_erp_token()

        response = requests.get(
            "https://appweb.mitrasinergi.co.id/msa/apiv1/aikaryawan/getListKaryawanAktif",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        if response.status_code != 200:
            print(
                "get_employees gagal:",
                response.status_code,
                response.text,
                flush=True
            )
            return []

        hasil = response.json()

        if (
            isinstance(hasil, dict)
            and hasil.get("success") is True
            and isinstance(hasil.get("data"), list)
        ):
            for item in hasil["data"]:
                if isinstance(item, dict) and item.get("nama"):
                    employees.append(
                        str(item["nama"]).strip()
                    )

        #++VVVVVV Dedupe nama
        seen = set()
        result = []

        for name in employees:
            key = name.casefold()

            if key not in seen:
                seen.add(key)
                result.append(name)

        employees = result
        #//++VVVVVV

        print(
            "Jumlah employee aktif:",
            len(employees),
            flush=True
        )

        _cache_set("employees", employees)

        return employees

    except Exception as exc:
        print(
            "get_employees exception:",
            repr(exc),
            flush=True
        )
        return []

def check_employee_by_name(nama_karyawan):
    try:
        keyword = str(nama_karyawan or "").strip()

        if not keyword:
            return []

        employees = get_employees()

        hasil = [
            nama for nama in employees
            if keyword.casefold() in nama.casefold()
        ]

        return hasil

    except Exception as exc:
        print(
            "check_employee_by_name gagal:",
            repr(exc),
            flush=True
        )
        return None

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
        },
        r"/karyawan": { # Ihsan nambahin //notes
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
        user_name = data.get("user_name") or ""
        id_divisi = data.get("id_divisi")
        projects = get_projects() or (data.get("projects") or [])
        employees = get_employees() or (data.get("employees") or [])
       
        envelope, _history = run(
            user_message,
            user_name=user_name,
            employees=employees, 
            projects=projects, 
            history=data.get("history") or [],
            user_id=user_id,
            id_divisi = id_divisi
        )
        body = dict(envelope) #ini buat nampilin di response
        body["user_name"] = user_name #ini buat nampilin di response
        body["id_divisi"] = id_divisi #ini buat nampilin di response

        if body["type"] == "function_call":

            #cek keberadaan proyek
            if body.get("function_name") == "check_project":
                arguments = json.loads(body.get("arguments") or "{}")
                nama_proyek = str(
                    arguments.get("nama_proyek", "")
                ).strip()

                hasil_cek = (
                    check_project_by_name(nama_proyek)
                    if nama_proyek
                    else None
                )

                if hasil_cek is None:
                    body["success"] = False
                    reply = (
                        "Pengecekan proyek ke MIS gagal. "
                        "Silakan coba lagi."
                    )
                elif hasil_cek:
                    body["success"] = True
                    reply = f"Proyek {nama_proyek} tersedia di MIS."
                else:
                    body["success"] = True
                    reply = f"Proyek {nama_proyek} tidak ditemukan di MIS."

                body["type"] = "text"
                body["function_name"] = ""
                body["arguments"] = ""
                body["reply"] = reply

                history = data.get("history") or []
                body["history"] = [
                    *history,
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": reply},
                ]

                return jsonify(body)
            
            #cek keberadaan karyawan
            if body.get("function_name") == "check_employee":
                arguments = json.loads(body.get("arguments") or "{}")

                nama_karyawan = str(
                    arguments.get("nama_karyawan", "")
                ).strip()

                hasil_cek = (
                    check_employee_by_name(nama_karyawan)
                    if nama_karyawan
                    else None
                )

                if hasil_cek is None:
                    body["success"] = False
                    reply = (
                        "Pengecekan karyawan ke MIS gagal. "
                        "Silakan coba lagi."
                    )

                elif hasil_cek:
                    body["success"] = True

                    daftar_nama = "\n".join(
                        f"- {nama}" for nama in hasil_cek
                    )

                    reply = (
                        f"Karyawan dengan kata kunci "
                        f'"{nama_karyawan}" ditemukan:\n'
                        f"{daftar_nama}"
                    )

                else:
                    body["success"] = True
                    reply = (
                        f'Karyawan aktif dengan kata kunci '
                        f'"{nama_karyawan}" tidak ditemukan di MIS.'
                    )

                body["type"] = "text"
                body["function_name"] = ""
                body["arguments"] = ""
                body["reply"] = reply

                history = data.get("history") or []
                body["history"] = [
                    *history,
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": reply},
                ]

                return jsonify(body)

            #++VVVVVV CREATE ALOKASI (KODE LAMA)
            # arguments is a JSON string: one object (single row) or an
            # array of objects (several rows, FR-08).
            arguments = json.loads(body["arguments"])
            single_row = isinstance(arguments, dict)
            rows = [arguments] if single_row else arguments

            #++VVVVVV VALIDASI PROYEK LANGSUNG KE MIS
            for row in rows:
                nama_proyek_alokasi = str(
                    row.get("nama_proyek", "")
                ).strip()

                if not nama_proyek_alokasi:
                    body["success"] = False
                    body["type"] = "text"
                    body["function_name"] = ""
                    body["arguments"] = ""
                    body["reply"] = "Nama proyek wajib diisi."
                    return jsonify(body)

                hasil_cek = check_project_by_name(
                    nama_proyek_alokasi
                )

                if hasil_cek is None:
                    body["success"] = False
                    body["type"] = "text"
                    body["function_name"] = ""
                    body["arguments"] = ""
                    body["reply"] = (
                        "Pengecekan proyek ke MIS gagal. "
                        "Alokasi belum dikirim. Silakan coba lagi."
                    )
                    return jsonify(body)

                if not hasil_cek:
                    body["success"] = False
                    body["type"] = "text"
                    body["function_name"] = ""
                    body["arguments"] = ""
                    body["reply"] = (
                        f'Proyek "{nama_proyek_alokasi}" '
                        "tidak ditemukan di MIS. "
                        "Mohon periksa kembali nama proyek."
                    )
                    return jsonify(body)
            #++VVVVVV AKHIR VALIDASI PROYEK LANGSUNG KE MIS


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

            body["hasil_ci3"] = results[0] if single_row else results
            return jsonify(body)
            #//++VVVVVV AKHIR CREATE ALOKASI

        #++VVVVVV Balasan teks biasa
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
# if __name__ == "__main__":
#     app.run(
#         host="0.0.0.0",
#         port=5001,
#         debug=False
#     )

# tambahan ihsan 2 11 2026 (ini berfungsi buat misal abis ngubah script ga perlu restart server)
if __name__ == "__main__":

    observer = Observer()
    handler = AutoReloadHandler()

    observer.schedule(
        handler,
        path=os.path.dirname(os.path.abspath(__file__)),
        recursive=True
    )

    observer.start()

    print("MSA AI Auto Reload aktif.", flush=True)

    try:
        app.run(
            host="0.0.0.0",
            port=5001,
            debug=False,
            use_reloader=False
        )
    finally:
        observer.stop()
        observer.join()
