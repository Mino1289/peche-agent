"""Contrat d'affichage : inversion toponymique sur la dernière virgule.

Miroir de web/src/names.ts — uninvertName.
"""


def uninvert_name(raw: str) -> str:
    s = raw.strip()
    idx = s.rfind(",")
    if idx < 0:
        return s
    head = s[:idx].strip()
    tail = s[idx + 1 :].strip()
    if not head or not tail:
        return s
    return f"{tail} {head}"


def test_uninvert_last_comma():
    assert (
        uninvert_name("Chute-à-la-Savane, Barrage de la")
        == "Barrage de la Chute-à-la-Savane"
    )
    assert uninvert_name("head, mid, tail") == "tail head, mid"
    assert uninvert_name("Sans virgule") == "Sans virgule"
    assert uninvert_name("  virgule finale,  ") == "virgule finale,"
