import requests


class ProyekModel:

    def getProyekByName(self, nama_proyek, token):
            response = requests.get(
                "https://appweb.mitrasinergi.co.id/msa/apiv1/aiproyek/getProyekByName",
                params={
                    "nama_proyek": nama_proyek
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                timeout=30
            )
    
            return response

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

    def getProyekWINByYear(self, tahun, token):
        response = requests.get(
            "https://appweb.mitrasinergi.co.id/msa/apiv1/aiproyek/getProyekWINByYear",
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