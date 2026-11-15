from flask import jsonify

from .model import ProyekModel


class ProyekController:

    def __init__(self):
        self.model = ProyekModel()

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