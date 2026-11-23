from flask import Blueprint, request
from .controller import ProyekController
from modules.auth.service import get_erp_token


proyek_bp = Blueprint(
    "proyek",
    __name__,
    url_prefix="/proyek"
)

controller = ProyekController()

@proyek_bp.route("/getProyekByName", methods=["GET"])
def getProyekByName():
    nama_proyek = request.args.get("nama_proyek")
    token = get_erp_token()

    return controller.getProyekByName(
        nama_proyek,
        token
    )


@proyek_bp.route("/getProyekMSAByYear", methods=["GET"])
def getProyekMSAByYear():
    tahun = request.args.get("tahun")
    token = get_erp_token()

    return controller.getProyekMSAByYear(
        tahun,
        token
    )

@proyek_bp.route("/getProyekWINByYear", methods=["GET"])
def getProyekWINByYear():
    tahun = request.args.get("tahun")
    token = get_erp_token()

    return controller.getProyekWINByYear(
        tahun,
        token
    )