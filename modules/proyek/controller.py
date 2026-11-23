from flask import jsonify
from .model import ProyekModel

from datetime import datetime
from zoneinfo import ZoneInfo

from modules.auth.service import get_erp_token
from utils.cache import cache_get, cache_set


class ProyekController:

    def __init__(self):
        self.model = ProyekModel()

    def getProyekByName(self, nama_proyek, token):
    
            if not nama_proyek:
                return jsonify({
                    "success": False,
                    "error": "nama proyek wajib diisi"
                }), 400
    
            response = self.model.getProyekByName(
                nama_proyek,
                token
            )
    
            if response.status_code != 200:
                return jsonify({
                    "success": False,
                    "error": "Gagal mengambil data proyek dari MIS",
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

    def getProyekMSAByYear(self, tahun, token):

        if not tahun:
            return jsonify({
                "success": False,
                "error": "tahun wajib diisi"
            }), 400

        response = self.model.getProyekMSAByYear(
            tahun,
            token
        )

        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": "Gagal mengambil data proyek dari MIS",
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


    def getProyekWINByYear(self, tahun, token):
    
            if not tahun:
                return jsonify({
                    "success": False,
                    "error": "tahun wajib diisi"
                }), 400
    
            response = self.model.getProyekWINByYear(
                tahun,
                token
            )
    
            if response.status_code != 200:
                return jsonify({
                    "success": False,
                    "error": "Gagal mengambil data proyek dari MIS",
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

    @staticmethod
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

    def get_projects(self):
        """Daftar proyek MSA+WIN tahun berjalan, digabung dan di-cache.
        Kalau gagal, kembalikan []."""
        cached = cache_get("projects")
        if cached is not None:
            return cached
        names = []
        ok = True
        try:
            token = get_erp_token()
            tahun = str(datetime.now(ZoneInfo("Asia/Jakarta")).year)
            for fetch in (self.getProyekMSAByYear, self.getProyekWINByYear):
                response, status = fetch(tahun, token)
                if status == 200:
                    names += self._names_from(response.get_json().get("data"))
                else:
                    ok = False
        except Exception as exc:
            print("get_projects gagal:", repr(exc), flush=True)
            ok = False
        # Satu sumber gagal -> buang hasil parsial.
        if not ok:
            names = []
        seen = set()
        merged = []
        for name in names:
            key = name.strip().casefold()
            if key not in seen:
                seen.add(key)
                merged.append(name.strip())
        cache_set("projects", merged)
        return merged

    def check_project_by_name(self, nama_proyek):
        try:
            token = get_erp_token()
            response, status = self.getProyekByName(nama_proyek, token)
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
            nama_dicari = str(nama_proyek or "").strip().casefold()
            return [
                item for item in hasil
                if isinstance(item, dict)
                and nama_dicari in str(item.get("nama_proyek", "")).strip().casefold()
            ]
        except Exception as exc:
            print("check_project_by_name gagal:", repr(exc), flush=True)
            return None