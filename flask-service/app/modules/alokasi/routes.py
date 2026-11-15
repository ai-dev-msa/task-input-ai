from flask import Blueprint
from app.decorators import token_required
from app.modules.alokasi import controller

alokasi_bp = Blueprint('alokasi', __name__)

@alokasi_bp.route('/alokasi', methods=['GET'])
@token_required
def get_alokasi_harian():
    return controller.get_alokasi_harian()