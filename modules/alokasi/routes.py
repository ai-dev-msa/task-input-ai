from flask import Blueprint, request
from .controller import AlokasiController
from modules.auth.service import get_erp_token

alokasi_bp = Blueprint('alokasi', __name__, url_prefix='/alokasi')

controller = AlokasiController()

@alokasi_bp.route('/getAlokasiByManyParams', methods =['GET'])
def getAlokasiByManyParams():
    tanggal = request.args.get("tanggal")
    nama_alokasi = request.args.get("nama_alokasi")
    kode_proyek = request.args.get("kode_proyek")
    nama_proyek = request.args.get("nama_proyek")
    jenis_pekerjaan = request.args.get("jenis_pekerjaan")

    token = get_erp_token()

    return controller.getAlokasiByManyParams(tanggal, nama_alokasi, kode_proyek,
                                             nama_proyek, jenis_pekerjaan, token)

def createAlokasi(self, row, token):
    if not isinstance(row, dict) or not row:
        return jsonify({"success": False, "error": "Data alokasi wajib diisi"}), 400

    response = self.model.createAlokasi(row, token)

    try:
        hasil = response.json()
    except Exception:
        return jsonify({
            "success": False,
            "error": "Response MIS bukan JSON",
            "response": response.text
        }), 500

    if response.status_code != 200:
        return jsonify({
            "success": False,
            "error": "Gagal membuat alokasi di MIS",
            "http_status": response.status_code,
            "data": hasil
        }), response.status_code

    return jsonify({"success": True, "data": hasil}), 200

@alokasi_bp.route('/updateAlokasi', methods=['POST'])
def updateAlokasi():
    payload = request.get_json(silent=True)
    token = get_erp_token()

    return controller.updateAlokasi(payload, token)