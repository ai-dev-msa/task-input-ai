from flask import Blueprint, request
from .controller import AlokasiController
# from app.modules.alokasi import controller

alokasi_bp = Blueprint('alokasi', __name__, url_prefix='/alokasi')

controller = AlokasiController()

# @alokasi_bp.route('/alokasi', methods=['GET'])
# @token_required
# def get_alokasi_harian():
#     return controller.get_alokasi_harian()

@alokasi_bp.route('/getAlokasiByManyParams', methods =['GET'])
def getAlokasiByManyParams():
    import main
    

    tanggal = request.args.get("tanggal")
    nama_alokasi = request.args.get("nama_alokasi")
    kode_proyek = request.args.get("kode_proyek")
    nama_proyek = request.args.get("nama_proyek")
    jenis_pekerjaan = request.args.get("jenis_pekerjaan")

    token = main.get_erp_token()

    return controller.getAlokasiByManyParams(tanggal, nama_alokasi, kode_proyek,
                                             nama_proyek, jenis_pekerjaan, token)