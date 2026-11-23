from flask import Blueprint, request
from .controller import KaryawanController

karyawan_bp = Blueprint(
    "karyawan",
    __name__,
    url_prefix="/karyawan"
)

controller = KaryawanController()


@karyawan_bp.route("/getListKaryawanAktif", methods=["GET"])
def getListKaryawanAktif():
    token = main.get_erp_token()

    return controller.getListKaryawanAktif(token)
