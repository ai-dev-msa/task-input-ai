from app.db import get_db_connection

def get_alokasi_harian():
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        sql = """
            SELECT *
            FROM `ga - alokasi harian`
            ORDER BY RecID DESC
            LIMIT 100
        """

        cursor.execute(sql)
        return cursor.fetchall()

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close() 