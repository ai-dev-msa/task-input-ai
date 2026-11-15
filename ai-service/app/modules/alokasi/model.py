import requests
#from app.db import get_db_connection

class AlokasiModel:
    # def get_alokasi_harian():
    #     connection = None
    #     cursor = None

    #     try:
    #         connection = get_db_connection()
    #         cursor = connection.cursor(dictionary=True)

    #         sql = """
    #             SELECT *
    #             FROM `ga - alokasi harian`
    #             ORDER BY RecID DESC
    #             LIMIT 100
    #         """

    #         cursor.execute(sql)
    #         return cursor.fetchall()

    #     finally:
    #         if cursor:
    #             cursor.close()
    #         if connection:
    #             connection.close()

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
        # connection = None
        # cursor = None

        # conditions = []
        # values = []

        # try:

        #     if tanggal:
        #         conditions.append("`Tanggal` = %s")
        #         values.append(tanggal)

        #     if nama_alokasi:
        #         conditions.append("`Nama Alokasi` LIKE %s")
        #         values.append(f"%{nama_alokasi}%")

        #     if kode_proyek:
        #         conditions.append("`Kode Proyek` = %s")
        #         values.append(kode_proyek)

        #     if nama_proyek:
        #         conditions.append("`Nama Proyek` LIKE %s")
        #         values.append(f"%{nama_proyek}%")

        #     if jenis_pekerjaan:
        #         conditions.append("`Jenis Pekerjaan` LIKE %s")
        #         values.append(f"%{jenis_pekerjaan}%")
            

        #     sql = " SELECT * FROM `ga - alokasi harian`"
        #     if conditions:
        #         sql += " WHERE " + " AND ".join(conditions)
        #     sql += " ORDER BY RecID DESC LIMIT 100"

        #     connection = get_db_connection()
        #     cursor = connection.cursor(dictionary=True)

        #     cursor.execute(sql, values)
        #     return cursor.fetchall()

        # finally:
        #     if cursor:
        #         cursor.close()
        #     if connection:
        #         connection.close() 