from flask import jsonify

#from app.utils import serialize_data
from .model import AlokasiModel

class AlokasiController:
    def __init__(self):
        self.model = AlokasiModel()

    def get_alokasi_harian():
        try:
            data = model.get_alokasi_harian()
            #data = serialize_data(data)

            return jsonify({
                "status": True,
                "message": "Data alokasi harian berhasil diambil",
                "total": len(data),
                "data": data
            })

        except Exception as e:
            return jsonify({
                "status": False,
                "message": "Terjadi kesalahan",
                "error": str(e)
            }), 500

    def getAlokasiByManyParams(self, tanggal, nama_alokasi, kode_proyek, nama_proyek, jenis_pekerjaan, token):

        if not (kode_proyek or '').strip() and not (nama_proyek or '').strip():
            return jsonify({
                "success": False,
                "error": "Setidaknya salah satu dari kode proyek atau nama proyek harus diisi"
            }), 400
        
        response = self.model.getAlokasiByManyParams(
            tanggal, nama_alokasi, kode_proyek,
            nama_proyek, jenis_pekerjaan,
            token
        )

        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": "Gagal mengambil data alokasi dari MIS",
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

