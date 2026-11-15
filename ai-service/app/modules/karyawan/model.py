import requests


class KaryawanModel:

    def getListKaryawanAktif(self, token):
        response = requests.get(
            "https://appweb.mitrasinergi.co.id/msa/apiv1/aikaryawan/getListKaryawanAktif", #ini nembak ke endpoint MIS yang dibuat Ihsan
            # params={
            #     "tahun": tahun
            # },
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        return response

    