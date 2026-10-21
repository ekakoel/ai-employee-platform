
from app.agents.profile_prompt import (
    build_agent_instructions,
)


def test_build_agent_instructions():
    configuration = {
        "job_description": "Membuat laporan keuangan.",
        "responsibilities": [
            "Memeriksa transaksi"
        ],
        "sop": [
            "Periksa data",
            "Validasi hasil"
        ],
        "rules": [
            "Jangan mengarang angka"
        ],
        "success_criteria": [
            "Angka memiliki sumber"
        ],
    }

    result = build_agent_instructions(configuration)

    assert "Membuat laporan keuangan." in result
    assert "Memeriksa transaksi" in result
    assert "Periksa data" in result
    assert "Jangan mengarang angka" in result
    assert "Angka memiliki sumber" in result


def test_empty_configuration_is_supported():
    result = build_agent_instructions({})

    assert "# JOB DESCRIPTION" in result
    assert "# STANDARD OPERATING PROCEDURE" in result
    assert "# RULES" in result
