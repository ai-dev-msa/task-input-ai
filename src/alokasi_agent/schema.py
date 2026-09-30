from typing import Any

from pydantic import BaseModel, ConfigDict, Field

CREATE_ALOKASI_DESCRIPTION = (
    "Buat satu baris alokasi kerja karyawan untuk satu tanggal: "
    "nama karyawan, nama proyek, tanggal, jenis pekerjaan, dan jam mulai/selesai."
)


class CreateAlokasiArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nama_karyawan: str = Field(
        description="Nama lengkap karyawan, contoh: Imam Ihsani"
    )
    nama_proyek: str = Field(
        description="Nama proyek, contoh: OPRS Divisi WIN 2026"
    )
    tanggal: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Tanggal pekerjaan dalam format YYYY-MM-DD, contoh: 2026-09-29",
    )
    jenis_pekerjaan: str = Field(
        description="Uraian pekerjaan, contoh: Development Modul PPN"
    )
    jam_mulai: str = Field(
        pattern=r"^\d{2}:\d{2}$",
        description="Jam mulai dalam format HH:MM, contoh: 09:00",
    )
    jam_selesai: str = Field(
        pattern=r"^\d{2}:\d{2}$",
        description="Jam selesai dalam format HH:MM, contoh: 12:00",
    )


CREATE_ALOKASI_TOOL: dict[str, Any] = {
    "name": "create_alokasi",
    "description": CREATE_ALOKASI_DESCRIPTION,
    "input_schema": CreateAlokasiArgs.model_json_schema(),
}
