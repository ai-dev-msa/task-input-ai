from flask import Flask, jsonify
from app.db import get_db_connection
from app.config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    from app.modules.auth.routes import auth_bp
    from app.modules.alokasi.routes import alokasi_bp
    # from app.modules.karyawan.routes import karyawan_bp
    # from app.modules.absensi.routes import absensi_bp
    from app.modules.proyek import proyek_bp


    app.register_blueprint(auth_bp)
    app.register_blueprint(alokasi_bp)
    app.register_blueprint(proyek_bp)

    # app.register_blueprint(karyawan_bp)
    # app.register_blueprint(absensi_bp)

    @app.route("/", methods=["GET"])
    def home():

        return jsonify({
          "status": True,
          "message": "Flask API is running"
        })

    @app.route("/test-db", methods=["GET"])
    def test_db():

        connection = None

        try:

          connection = get_db_connection()

          return jsonify({
              "status": True,
              "message": "Koneksi database berhasil"
          })

        except Exception as e:

          return jsonify({
              "status": False,
              "message": "Koneksi database gagal",
              "error": str(e)
          }), 500

        finally:
          if connection:
              connection.close()

    return app