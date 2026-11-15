import requests


class ProyekModel:

    def getProyekMSAByYear(self, tahun, token):
        response = requests.get(
            "https://appweb.mitrasinergi.co.id/msa/apiv1/aiproyek/getProyekMSAByYear",
            params={
                "tahun": tahun
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        return response