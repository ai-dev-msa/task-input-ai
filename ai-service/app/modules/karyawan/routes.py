from flask import Blueprint, request
from .controller import KaryawanController
# from app.main import get_erp_token


karyawan_bp = Blueprint(
    "karyawan",
    __name__,
    url_prefix="/karyawan"
)

controller = KaryawanController()


@karyawan_bp.route("/getListKaryawanAktif", methods=["GET"])
def getListKaryawanAktif():

    import main


    # tahun = request.args.get("tahun")

   

    token = main.get_erp_token()

    return controller.getListKaryawanAktif(
        # tahun,
        token
    )
