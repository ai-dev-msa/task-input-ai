from flask import jsonify

from .model import KaryawanModel
from modules.auth.service import get_erp_token
from utils.cache import cache_get, cache_set


class KaryawanController:

    def __init__(self):
        self.model = KaryawanModel()

    def getListKaryawanAktif(self, token):

        # if not tahun:
        #     return jsonify({
        #         "success": False,
        #         "error": "tahun wajib diisi"
        #     }), 400

        response = self.model.getListKaryawanAktif(
            # tahun,
            token
        )

        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": "Gagal mengambil data karyawan dari MIS",
                "http_status": response.status_code,
                "response": response.text
            }), response.status_code

        try:
            hasil = response.json()
        except Exception:
            return jsonify({
                "success": False,
                "error": "Response MIS bukan JSON",
                "response": response.text
            }), 500

        return jsonify({
            "success": True,
            "data": hasil
        }), 200

    def get_employees(self):
        """Daftar nama karyawan aktif, di-cache. Gagal -> []."""
        cached = cache_get("employees")
        if cached is not None:
            return cached

        try:
            token = get_erp_token()
            response, status_code = self.getListKaryawanAktif(token)

            if status_code != 200:
                print("get_employees gagal:", status_code, response.get_json(), flush=True)
                return []

            hasil = response.get_json()
            if not isinstance(hasil, dict) or hasil.get("success") is not True:
                raise Exception("Response controller karyawan tidak valid")

            data = hasil.get("data", [])
            # Menyesuaikan response MIS yang dibungkus controller
            if isinstance(data, dict):
                data = data.get("data", [])

            employees = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("nama"):
                        nama = str(item["nama"]).strip()
                        if nama:
                            employees.append(nama)

            # Dedupe nama (case-insensitive, urutan pertama dipertahankan)
            seen = set()
            result = []
            for name in employees:
                key = name.casefold()
                if key not in seen:
                    seen.add(key)
                    result.append(name)

            print("Jumlah employee aktif:", len(result), flush=True)
            cache_set("employees", result)
            return result

        except Exception as exc:
            print("get_employees exception:", repr(exc), flush=True)
            return []

    def check_employee_by_name(self, nama_karyawan):
        try:
            keyword = str(nama_karyawan or "").strip()
            if not keyword:
                return []
            return [
                nama for nama in self.get_employees()
                if keyword.casefold() in nama.casefold()
            ]
        except Exception as exc:
            print("check_employee_by_name gagal:", repr(exc), flush=True)
            return None


    