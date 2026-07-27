"""Parsing des pages DevExpress de RegPec.

Les pages sont des `GridView` DevExpress avec un `_DXMainTable`. On localise
la table par son id, on extrait les `<tr>` (`DXDataRow*` = lignes données,
`DXGroupRow*` = en-têtes) puis on regroupe en `{segment, periodes, especes}`.
"""

from __future__ import annotations

import re
from html import unescape


def clean_html(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_main_table(page_html: str, grid_id: str) -> str | None:
    """Extrait le HTML de la `<table>` qui contient `{grid_id}_DXMainTable`."""
    marker = f'id="{grid_id}_DXMainTable"'
    marker_pos = page_html.find(marker)
    if marker_pos == -1:
        return None

    start = page_html.rfind("<table", 0, marker_pos)
    if start == -1:
        return None

    depth = 0
    index = start
    while index < len(page_html):
        if page_html.startswith("<table", index):
            depth += 1
            index += 6
            continue
        if page_html.startswith("</table>", index):
            depth -= 1
            index += 8
            if depth == 0:
                return page_html[start:index]
            continue
        index += 1
    return None


def parse_saison(page_html: str) -> tuple[int, str]:
    id_match = re.search(r"id_saisn_VI\"[^>]*value=\"(\d+)\"", page_html)
    text_match = re.search(r"id_saisn_I\"[^>]*value=\"([^\"]+)\"", page_html)
    saison_id = int(id_match.group(1)) if id_match else 220
    saison_text = unescape(text_match.group(1)) if text_match else ""
    return saison_id, saison_text


def normalize_plan_name(name: str) -> str:
    """Normalise un libellé de plan d'eau pour comparaison."""
    from peche.matching.normalize import normalize_search_text

    return normalize_search_text(name)


def build_endroits_catalog(*pages_html: str) -> dict[int, str]:
    """Fusionne les entrées `(id, nom)` des combobox `id_endro` de plusieurs pages."""
    catalog: dict[int, str] = {}
    for page_html in pages_html:
        for endroit in parse_endroits(page_html):
            catalog[int(endroit["id"])] = str(endroit["nom"])
    return catalog


def extract_plan_label_from_grid_row(row_html: str) -> str:
    """Extrait le nom principal d'une ligne de grille (texte en gras ou préfixe)."""
    bold = re.search(r'<span class="gras">(.*?)</span>', row_html, re.S)
    if bold:
        return clean_html(bold.group(1)).strip()
    cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)
    nom = clean_html(cells[-1]) if cells else ""
    for sep in (" - ", " entre "):
        if sep in nom:
            return nom.split(sep, 1)[0].strip()
    return nom.strip()


def match_endroit_id(plan_label: str, catalog: dict[int, str]) -> int | None:
    """Associe un libellé de grille au `id_endro` du combobox RegPec, si possible."""
    label = normalize_plan_name(plan_label)
    if not label:
        return None
    for endro_id, name in catalog.items():
        normalized = normalize_plan_name(name)
        if (
            label == normalized
            or label.startswith(normalized)
            or normalized.startswith(label)
        ):
            return endro_id
    return None


def parse_endroits(page_html: str) -> list[dict[str, str | int]]:
    """Extrait les endroits depuis le combobox `id_endro` du HTML zone.

    ⚠ Ce combobox DevExpress est **plafonné à 100 items** en mode callback
    (cf. `'callbackPageSize': 100`). Pour les zones de plus de 100 plans
    (zones 10, 18, 28…), utiliser plutôt `parse_endroits_from_partial_grid`
    sur l'endpoint `PartialGrilleReglementsPlanEau`.
    """
    match = re.search(
        r"'id_endro_DDD_L'.*?'itemsInfo':(\[.*?\])\},\{'SelectedIndexChanged'",
        page_html,
        re.S,
    )
    if not match:
        return []

    return [
        {"id": int(value), "nom": text.replace("\\'", "'")}
        for value, text in re.findall(
            r"\{'value':(\d+),'text':'((?:\\'|[^'])*)'", match.group(1)
        )
    ]


def parse_endroits_from_partial_grid(
    partial_html: str,
) -> list[dict[str, str | int]]:
    """Extrait `(id, nom)` depuis la grille HTML complète RegPec.

    L'endpoint `/RegPec/fr/Info/PartialGrilleReglementsPlanEau?id_zone=...`
    renvoie un `<table id="GrilleReglementsPlansEau">` avec un `<tr
    DXGroupRow{N}>` par plan d'eau. Quand le plan a des coordonnées, son
    `id_endro` est exposé dans `OuvrirPopUpCoords(<id>)` (souvent dans les
    liens de coordonnées, pas dans l'en-tête) ; sinon on n'a que le libellé
    et l'id doit être résolu via le combobox `id_endro` (cf. `sync_zone`).

    Renvoie une liste ordonnée de :
      - `{"id": <int>, "nom": <str>, "plan_label": <str>}` pour les plans avec id,
      - `{"id": None, "nom": <str>, "plan_label": <str>, "segment_only": True}`
        pour les autres.
    """
    rows = re.findall(
        r'<tr id="GrilleReglementsPlansEau_DXGroupRow\d+"[^>]*>(.*?)</tr>',
        partial_html,
        re.S,
    )
    out: list[dict[str, str | int]] = []
    for row_html in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)
        if not cells:
            continue
        last = cells[-1]
        m_id = re.search(r"OuvrirPopUpCoords\((\d+)\)", row_html)
        nom = clean_html(last)
        if not nom:
            continue
        plan_label = extract_plan_label_from_grid_row(row_html)
        entry: dict[str, str | int] = {"nom": nom, "plan_label": plan_label}
        if m_id:
            entry["id"] = int(m_id.group(1))
        else:
            entry["id"] = None
            entry["segment_only"] = True
        out.append(entry)
    return out


def _row_cells(row_html: str) -> list[str]:
    cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)
    return [cell for cell in (clean_html(c) for c in cells) if cell]


def _parse_data_row(row_html: str) -> dict[str, str] | None:
    cells = re.findall(r"<td([^>]*)>(.*?)</td>", row_html, re.S)
    data_cells = [
        clean_html(content) for attrs, content in cells if "dxgvIndentCell" not in attrs
    ]
    while len(data_cells) < 5:
        data_cells.append("")
    data_cells = data_cells[:5]
    if not any(data_cells):
        return None
    return {
        "type": "espece",
        "espece": data_cells[0],
        "limite_prise": data_cells[1],
        "limite_longueur": data_cells[2],
        "engin": data_cells[3],
        "note": data_cells[4],
    }


def parse_grid_rows(page_html: str, grid_id: str) -> list[dict[str, str]]:
    table = extract_main_table(page_html, grid_id)
    if not table:
        return []

    rows: list[dict[str, str]] = []
    for row_id, row_html in re.findall(
        rf'<tr id="{re.escape(grid_id)}_(DX[^"]+)"[^>]*>(.*?)</tr>',
        table,
        re.S,
    ):
        if "DXDataRow" in row_id:
            parsed = _parse_data_row(row_html)
            if parsed:
                rows.append(parsed)
            continue
        if "DXGroupRow" not in row_id:
            continue
        cells = _row_cells(row_html)
        if not cells:
            continue
        label = cells[-1]
        if label.startswith("Période"):
            rows.append({"type": "periode", "texte": label})
        elif label and label not in {"Espèce", "Règles de la zone"}:
            rows.append({"type": "plan_eau", "texte": label})
        elif label:
            rows.append({"type": "section", "texte": label})
    return rows


def group_rows(rows: list[dict[str, str]]) -> list[dict]:
    """Regroupe les lignes plates en `[{segment, periodes:[{periode, especes:[]}]}]`."""
    grouped: list[dict] = []
    current: dict | None = None
    current_period: dict | None = None

    for row in rows:
        row_type = row["type"]
        if row_type in {"plan_eau", "section"}:
            current = {"segment": row["texte"], "periodes": []}
            grouped.append(current)
            current_period = None
        elif row_type == "periode":
            if current is None:
                current = {"segment": "", "periodes": []}
                grouped.append(current)
            current_period = {"periode": row["texte"], "especes": []}
            current["periodes"].append(current_period)
        elif row_type == "espece":
            if current is None:
                current = {"segment": "", "periodes": []}
                grouped.append(current)
            if current_period is None:
                current_period = {"periode": "", "especes": []}
                current["periodes"].append(current_period)
            current_period["especes"].append(
                {
                    "espece": row["espece"],
                    "limite_prise": row["limite_prise"],
                    "limite_longueur": row["limite_longueur"],
                    "engin": row["engin"],
                    "note": row["note"],
                }
            )
    return grouped
