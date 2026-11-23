from flask import jsonify
from .model import AlokasiModel
from modules.auth.service import get_erp_token

class AlokasiController:
    def __init__(self):
        self.model = AlokasiModel()

    # def get_alokasi_harian():
    #     try:
    #         data = model.get_alokasi_harian()
    #         #data = serialize_data(data)

    #         return jsonify({
    #             "status": True,
    #             "message": "Data alokasi harian berhasil diambil",
    #             "total": len(data),
    #             "data": data
    #         })

    #     except Exception as e:
    #         return jsonify({
    #             "status": False,
    #             "message": "Terjadi kesalahan",
    #             "error": str(e)
    #         }), 500

    def getAlokasiByManyParams(self, tanggal, nama_alokasi, kode_proyek, nama_proyek, jenis_pekerjaan, token):

        if not (kode_proyek or '').strip() and not (nama_proyek or '').strip():
            return jsonify({
                "success": False,
                "error": "Setidaknya salah satu dari kode proyek atau nama proyek harus diisi"
            }), 400
        
        response = self.model.getAlokasiByManyParams(
            tanggal, nama_alokasi, kode_proyek,
            nama_proyek, jenis_pekerjaan,
            token
        )

        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": "Gagal mengambil data alokasi dari MIS",
                "http_status": response.status_code,
                "response": response.text
            }), response.status_code

        try:
            hasil = response.json()
        except Exception:
            return jsonify({
                "success": False,
                "error": "Response MIS bukan JSON",
                "response": response.text
            }), 500

        return jsonify({
            "success": True,
            "data": hasil
        }), 200

    @staticmethod
    def _slim_alokasi_row(row):
        """Ambil hanya field yang dibutuhkan model; jam dipotong jadi HH:MM
        (schema.py memakai HH:MM, HH:MM:SS ditolak)."""

        def hhmm(value):
            return str(value)[:5] if value else None

        return {
            "id_edit": row.get("id_edit"),
            "nama": row.get("nama"),
            "nama_proyek": row.get("nama_proyek"),
            "tanggal": row.get("tanggal"),
            "jam_mulai": hhmm(row.get("jam_mulai")),
            "jam_selesai": hhmm(row.get("jam_selesai")),
            "jenis_pekerjaan": row.get("jenis_pekerjaan"),
            "keterangan": row.get("keterangan"),
        }

    def find_alokasi_by_params(self, arguments):
        """Daftar alokasi untuk agent. Gagal -> None."""
        try:
            token = get_erp_token()

            response, status_code = self.getAlokasiByManyParams(
                tanggal=arguments.get("tanggal"),
                nama_alokasi=arguments.get("nama_alokasi"),
                kode_proyek=arguments.get("kode_proyek"),
                nama_proyek=arguments.get("nama_proyek"),
                jenis_pekerjaan=arguments.get("jenis_pekerjaan"),
                token=token
            )

            hasil = response.get_json()

            # if status_code != 200 or not hasil.get("success"):
            #     raise Exception(
            #         hasil.get("error", "Gagal mengambil data alokasi MIS")
            #     )

            if status_code != 200 or not hasil.get("success"):
                raise Exception(
                    f"{hasil.get('error', 'Gagal mengambil data alokasi MIS')} "
                    f"| HTTP: {hasil.get('http_status', status_code)} "
                    f"| Response: {hasil.get('response', hasil)}"
                )

            # controller membungkus response MIS: data.data = daftar baris
            rows = (hasil.get("data") or {}).get("data", [])

            if not isinstance(rows, list):
                raise Exception("Format data alokasi MIS tidak sesuai")

            return [
                self._slim_alokasi_row(row)
                for row in rows
                if isinstance(row, dict)
            ]

        except Exception as exc:
            print("find_alokasi_by_params gagal:", repr(exc), flush=True)
            return None

    def updateAlokasi(self, payload, token):
        if not isinstance(payload, dict) or not str(payload.get("id_edit") or "").strip():
            return jsonify({"success": False, "error": "id_edit wajib diisi"}), 400

        if len(payload) < 2:
            return jsonify({"success": False, "error": "Tidak ada field yang diubah"}), 400

        response = self.model.updateAlokasi(payload, token)

        if response.status_code != 200:
            try:
                mis_message = response.json().get("message")
            except Exception:
                mis_message = None
            return jsonify({
                "success": False,
                "error": mis_message or "Gagal mengubah alokasi di MIS",
                "http_status": response.status_code,
                "response": response.text
            }), response.status_code

        try:
            hasil = response.json()
        except Exception:
            return jsonify({
                "success": False,
                "error": "Response MIS bukan JSON",
                "response": response.text
            }), 500

        # CI3 kadang membalas HTTP 200 tapi success:false di body
        if isinstance(hasil, dict) and hasil.get("success") is False:
            return jsonify({"success": False, "data": hasil}), 400

        return jsonify({"success": True, "data": hasil}), 200

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
    

