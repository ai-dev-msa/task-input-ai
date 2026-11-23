# import os
# import requests

# from utils.cache import cache_get, cache_set


# def get_erp_token():
#     cached = cache_get("erp_token")
#     if cached is not None:
#         return cached

#     username = os.getenv("ERP_API_USERNAME")
#     password = os.getenv("ERP_API_PASSWORD")

#     if not username or not password:
#         raise Exception("ERP_API_USERNAME / ERP_API_PASSWORD belum tersedia")

#     response_login = requests.post(
#         "https://appweb.mitrasinergi.co.id/msa/apiv1/auth/login",
#         data={"username": username, "password": password},
#         timeout=30
#     )

#     if response_login.status_code != 200:
#         raise Exception(
#             "Login ERP gagal. HTTP " + str(response_login.status_code)
#             + " | Response: " + response_login.text
#         )

#     hasil_login = response_login.json()

#     if not isinstance(hasil_login, list) or not hasil_login:
#         raise Exception(
#             "Format response login ERP tidak sesuai. Response: " + str(hasil_login)
#         )

#     token = hasil_login[0].get("access_token")

#     if not token:
#         raise Exception("Access token tidak ditemukan dari response login ERP")

#     cache_set("erp_token", token)
#     return token


import os
import requests

from utils.cache import cache_get, cache_set


def get_erp_token(force_refresh=False):

    # Ambil token dari cache jika tidak dipaksa refresh
    if not force_refresh:
        cached = cache_get("erp_token")
        if cached is not None:
            return cached

    username = os.getenv("ERP_API_USERNAME")
    password = os.getenv("ERP_API_PASSWORD")

    if not username or not password:
        raise Exception("ERP_API_USERNAME / ERP_API_PASSWORD belum tersedia")

    response_login = requests.post(
        "https://appweb.mitrasinergi.co.id/msa/apiv1/auth/login",
        data={
            "username": username,
            "password": password
        },
        timeout=30
    )

    if response_login.status_code != 200:
        raise Exception(
            "Login ERP gagal. HTTP " + str(response_login.status_code)
            + " | Response: " + response_login.text
        )

    hasil_login = response_login.json()

    if not isinstance(hasil_login, list) or not hasil_login:
        raise Exception(
            "Format response login ERP tidak sesuai. Response: " + str(hasil_login)
        )

    token = hasil_login[0].get("access_token")

    if not token:
        raise Exception("Access token tidak ditemukan dari response login ERP")

    cache_set("erp_token", token)

    return token
