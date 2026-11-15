from flask import Blueprint
from app.modules.auth import controller

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login", methods=["POST"])
def login():
  return controller.login()