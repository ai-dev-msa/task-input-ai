from flask import Blueprint, request
from .controller import ProyekController
# from app.main import get_erp_token


proyek_bp = Blueprint(
    "proyek",
    __name__,
    url_prefix="/proyek"
)

controller = ProyekController()


@proyek_bp.route("/getProyekMSAByYear", methods=["GET"])
def getProyekMSAByYear():

    import main


    tahun = request.args.get("tahun")

   

    token = main.get_erp_token()

    return controller.getProyekMSAByYear(
        tahun,
        token
    )