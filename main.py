from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import json
import os
import requests
import time 
from datetime import datetime 
from zoneinfo import ZoneInfo 

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

get_projects = proyek_controller.get_projects
check_project_by_name = proyek_controller.check_project_by_name

from modules.karyawan import karyawan_bp 
from modules.karyawan.routes import controller as karyawan_controller 
app.register_blueprint(karyawan_bp)

get_employees = karyawan_controller.get_employees
check_employee_by_name = karyawan_controller.check_employee_by_name

from modules.alokasi import alokasi_bp
from modules.alokasi.routes import controller as alokasi_controller
app.register_blueprint(alokasi_bp)

find_alokasi_by_params = alokasi_controller.find_alokasi_by_params

from utils.cache import cache_get as _cache_get, cache_set as _cache_set
from modules.auth.service import get_erp_token


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
        r"/karyawan": {
            "origins": [
                "https://appweb.mitrasinergi.co.id"
            ]
        },
        r"/alokasi": {
            "origins": [
                "https://appweb.mitrasinergi.co.id"
            ]
        },
    },
    methods=["GET","POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"]
)

def _text_body(body, data, user_message, reply, success=True, **extra):
    """Turn a function_call envelope into a plain text reply."""
    body["success"] = success
    body["type"] = "text"
    body["function_name"] = ""
    body["arguments"] = ""
    body["reply"] = reply
    body["history"] = [
        *(data.get("history") or []),
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": reply},
    ]
    body.update(extra)
    return body

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
            id_divisi=id_divisi,
            lookup_alokasi=find_alokasi_by_params,
        )
        body = dict(envelope)
        body["user_name"] = user_name
        body["id_divisi"] = id_divisi

        if body["type"] == "function_call":

            #cek keberadaan proyek
            if body.get("function_name") == "check_project":
                arguments = json.loads(body.get("arguments") or "{}")
                nama_proyek = str(arguments.get("nama_proyek", "")).strip()

                hasil_cek = check_project_by_name(nama_proyek) if nama_proyek else None

                if hasil_cek is None:
                    ok = False
                    reply = "Pengecekan proyek ke MIS gagal. Silakan coba lagi."
                elif hasil_cek:
                    ok = True
                    reply = f"Proyek {nama_proyek} tersedia di MIS."
                else:
                    ok = True
                    reply = f"Proyek {nama_proyek} tidak ditemukan di MIS."

                return jsonify(_text_body(body, data, user_message, reply, ok))

            #cek keberadaan karyawan
            if body.get("function_name") == "check_employee":
                arguments = json.loads(body.get("arguments") or "{}")
                nama_karyawan = str(arguments.get("nama_karyawan", "")).strip()

                hasil_cek = check_employee_by_name(nama_karyawan) if nama_karyawan else None

                if hasil_cek is None:
                    ok = False
                    reply = "Pengecekan karyawan ke MIS gagal. Silakan coba lagi."
                elif hasil_cek:
                    ok = True
                    daftar_nama = "\n".join(f"- {nama}" for nama in hasil_cek)
                    reply = (
                        f'Karyawan dengan kata kunci "{nama_karyawan}" ditemukan:\n'
                        f"{daftar_nama}"
                    )
                else:
                    ok = True
                    reply = (
                        f'Karyawan aktif dengan kata kunci '
                        f'"{nama_karyawan}" tidak ditemukan di MIS.'
                    )

                return jsonify(_text_body(body, data, user_message, reply, ok))

            #for updating alokasi
            if body.get("function_name") == "update_alokasi":
                arguments = json.loads(body.get("arguments") or "{}")
                changed = [key for key in arguments if key != "id_edit"]

                try:
                    token = get_erp_token()
                    response, status = alokasi_controller.updateAlokasi(arguments, token)
                    hasil_ci3 = response.get_json()
                    ok = status == 200 and hasil_ci3.get("success") is True
                except Exception as exc:
                    print("update_alokasi gagal:", repr(exc), flush=True)
                    hasil_ci3 = None
                    ok = False

                if ok:
                    reply = (
                        f"Alokasi {arguments.get('id_edit')} berhasil diubah "
                        f"({', '.join(changed)})."
                    )
                else:
                    reply = "Perubahan alokasi gagal disimpan di MIS. Silakan coba lagi."

                return jsonify(
                    _text_body(body, data, user_message, reply, ok, hasil_ci3=hasil_ci3)
                )

            #++VVVVVV CREATE ALOKASI
            # arguments is a JSON string: one object (single row) or an
            # array of objects (several rows, FR-08).
            arguments = json.loads(body["arguments"])
            single_row = isinstance(arguments, dict)
            rows = [arguments] if single_row else arguments

            # Validasi proyek langsung ke MIS, semua baris sebelum ada yang dikirim
            for row in rows:
                nama_proyek_alokasi = str(row.get("nama_proyek", "")).strip()

                if not nama_proyek_alokasi:
                    return jsonify(_text_body(
                        body, data, user_message,
                        "Nama proyek wajib diisi.", False
                    ))

                hasil_cek = check_project_by_name(nama_proyek_alokasi)

                if hasil_cek is None:
                    return jsonify(_text_body(
                        body, data, user_message,
                        "Pengecekan proyek ke MIS gagal. "
                        "Alokasi belum dikirim. Silakan coba lagi.",
                        False
                    ))

                if not hasil_cek:
                    return jsonify(_text_body(
                        body, data, user_message,
                        f'Proyek "{nama_proyek_alokasi}" tidak ditemukan di MIS. '
                        "Mohon periksa kembali nama proyek.",
                        False
                    ))

            # Kirim ke CI3 lewat controller, satu panggilan per baris
            token = get_erp_token()
            results = []
            for row in rows:
                response, status = alokasi_controller.createAlokasi(row, token)
                payload = response.get_json() or {}
                print("CI3 CREATE STATUS:", status, flush=True)
                results.append(payload.get("data", payload))

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