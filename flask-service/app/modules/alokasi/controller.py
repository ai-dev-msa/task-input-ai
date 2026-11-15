from flask import jsonify

from app.utils import serialize_data
from app.modules.alokasi import model

def get_alokasi_harian():
    try:
        data = model.get_alokasi_harian()
        data = serialize_data(data)

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