import requests
#from app.db import get_db_connection

class AlokasiModel:
    def getAlokasiByManyParams(self,
                                tanggal, 
                                nama_alokasi, 
                                kode_proyek,
                                nama_proyek,
                                jenis_pekerjaan,
                                token):
        response = requests.get(
        "https://appweb.mitrasinergi.co.id/msa/apiv1/aialokasiharian/getAlokasiByManyParams",
        params={
            "tanggal": tanggal,
            "nama_alokasi": nama_alokasi,
            "kode_proyek": kode_proyek,
            "nama_proyek": nama_proyek,
            "jenis_pekerjaan": jenis_pekerjaan,
                },
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
                },
            timeout=30
            )

        return response

    def updateAlokasi(self, payload, token):
        response = requests.post(
            "https://appweb.mitrasinergi.co.id/msa/apiv1/aialokasiharian/updateAlokasi",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        return response

    def createAlokasi(self, row, token):
        response = requests.post(
            "https://appweb.mitrasinergi.co.id/msa/apiv1/aialokasiharian/createAlokasi",
            json=row,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        return response
 