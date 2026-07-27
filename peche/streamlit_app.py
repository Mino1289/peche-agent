"""UI Streamlit pour peche-agent.

Lancement :
    streamlit run peche/streamlit_app.py
ou
    python3 -m peche.ui

Utilise directement `peche.agent.loop.stream_chat` (pas de couche HTTP).
L'historique de conversation et les messages affichés vivent dans
`st.session_state` ; le streaming utilise `st.empty()` pour mettre à jour
le bloc de texte en place au fur et à mesure des chunks Gemini.
"""

from __future__ import annotations

import os
from datetime import date

import streamlit as st

import peche  # déclenche le chargement .env
from peche.agent.loop import DEFAULT_MODEL, stream_chat
from peche.agent.schemas import TOOL_SCHEMAS
from peche.conversations.store import ConversationStore
from peche.dates import today as _today

_ = peche  # silence unused


# Description courte par outil (1 ligne) pour la sidebar.
_TOOL_DESCRIPTIONS: dict[str, str] = {
    "list_zones": "lister les 34 zones",
    "search_plans": "trouver un plan d'eau (fuzzy)",
    "get_reglements": "règlements (espèces, limites, périodes)",
    "get_weather": "météo à des coordonnées",
    "get_weather_at_plan": "météo pour un plan d'eau",
    "get_weather_at_place": "météo pour un nom de lieu libre",
    "search_stations": "trouver une station hydro par rivière / id",
    "get_hydromet": "niveau / débit d'une station",
    "get_hydromet_for_waterbody": "hydro multi-stations pour un plan d'eau",
    "get_hydromet_at_plan": "hydro pour un plan d'eau (station primaire)",
    "get_iqbp": "qualité d'eau IQBP (MELCC)",
    "search_tide_stations": "station marégraphique SHC (code ou nom)",
    "get_tides": "pleines et basses mers (prédictions SHC)",
    "get_water_levels": "niveau d'eau actuel (Vigilance + IWLS)",
    "get_tides_at_place": "marées pour un lieu libre (géocodage)",
    "get_tides_at_plan": "marées pour un plan d'eau RegPec",
    "search_barrages": "répertoire CEHQ (~6000 barrages)",
    "get_barrages_at_plan": "barrages ≤10 km d'un plan d'eau",
    "get_barrages_at_place": "barrages ≤10 km d'un lieu",
    "get_fishing_advice": "conseils leurres et techniques (expert)",
}

_AVAILABLE_TOOLS: list[dict] = [
    {"name": s["name"], "desc": _TOOL_DESCRIPTIONS.get(s["name"], "")}
    for s in TOOL_SCHEMAS
]

st.set_page_config(
    page_title="peche-agent",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------- État ----------


def _conversation_store() -> ConversationStore:
    return ConversationStore()


def _ensure_state() -> None:
    if "history" not in st.session_state:
        st.session_state.history = []  # google.genai.types.Content[]
    if "messages" not in st.session_state:
        st.session_state.messages = []  # [{role, text, tools?}]
    if "running" not in st.session_state:
        st.session_state.running = False
    if "history_search" not in st.session_state:
        st.session_state.history_search = ""
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None
    if "stream_prompt" not in st.session_state:
        st.session_state.stream_prompt = None


def _current_conversation_meta() -> dict | None:
    cid = st.session_state.get("conversation_id")
    if not cid:
        return None
    return _conversation_store().get_conversation(cid)


def _ensure_conversation_id() -> str:
    cid = st.session_state.get("conversation_id")
    if cid:
        return cid
    cid = _conversation_store().create_conversation()
    st.session_state.conversation_id = cid
    return cid


def _start_new_conversation() -> None:
    st.session_state.conversation_id = _conversation_store().create_conversation()
    st.session_state.history = []
    st.session_state.messages = []
    st.session_state.stream_prompt = None
    st.session_state.running = False


def _load_conversation(conversation_id: str) -> None:
    store = _conversation_store()
    st.session_state.conversation_id = conversation_id
    st.session_state.messages = store.load_messages(conversation_id)
    st.session_state.history = store.load_gemini_history(conversation_id)
    st.session_state.stream_prompt = None
    st.session_state.running = False


def _on_select_conversation(conversation_id: str) -> None:
    if conversation_id != st.session_state.get("conversation_id"):
        _load_conversation(conversation_id)
        st.session_state.conversation_loaded_hint = True


def _on_rename_conversation() -> None:
    cid = st.session_state.get("conversation_id")
    new_title = st.session_state.get("rename_conversation_input", "").strip()
    if cid and new_title:
        _conversation_store().rename_conversation(cid, new_title)


_ensure_state()


# ---------- Sidebar : statut + actions ----------


def _sidebar() -> None:
    with st.sidebar:
        st.markdown("### peche-agent")
        st.caption("Pêche sportive au Québec — règlements, météo, hydro.")

        if st.button(
            "Nouvelle conversation",
            width="stretch",
            disabled=st.session_state.running,
        ):
            _start_new_conversation()
            st.rerun()

        st.markdown("---")
        today = _today()
        st.markdown(f"**Date du jour :** {today.isoformat()}")
        st.markdown(f"**Modèle :** `{os.environ.get('LLM_MODEL', DEFAULT_MODEL)}`")
        if peche.DOTENV_LOADED:
            st.caption("Config : `.env` chargé (`LLM_MODEL`).")
        else:
            st.caption("Config : variables d'environnement shell (pas de `LLM_MODEL` dans `.env`).")

        with st.expander("Outils disponibles", expanded=False):
            # HTML + <code> : unsafe_allow_html n'interprète pas les backticks MD.
            lines = [
                f"<code>{tool['name']}</code> — {tool['desc']}"
                for tool in _AVAILABLE_TOOLS
            ]
            st.markdown(
                "<div style='font-size:0.85rem; line-height:1.35;'>"
                + "<br/>".join(lines)
                + "</div>",
                unsafe_allow_html=True,
            )


# ---------- Affichage de l'historique ----------


_URL_KEYS = {
    "cehq",
    "cehq_tableau",
    "cehq_export",
    "vigilance",
    "atlas_eau",
    "donnees_quebec",
    "url",
}


def _collect_links(
    obj, found: list[tuple[str, str]] | None = None
) -> list[tuple[str, str]]:
    """Parcourt récursivement un dict/list pour récupérer les URLs cliquables."""
    if found is None:
        found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                if k.lower() in _URL_KEYS or "url" in k.lower():
                    found.append((str(k), v))
            else:
                _collect_links(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _collect_links(item, found)
    return found


def _hydro_label(result: dict) -> str:
    desc = result.get("description") or ""
    if desc:
        if "barrage" in desc.lower():
            for part in desc.split("barrage", 1)[-1].split():
                cleaned = part.strip(" .,-")
                if cleaned and len(cleaned) > 2:
                    return cleaned
        if len(desc) <= 60:
            return desc
        return desc[:57] + "…"
    raw = (
        result.get("plan_nom")
        or result.get("plan_eau")
        or result.get("station_id")
        or "Station"
    )
    text = str(raw)
    if " - " in text:
        return text.split(" - ", 1)[0].strip()
    return text


def _flatten_waterbody_result(wb: dict) -> list[dict]:
    """Déplie un retour get_hydromet_for_waterbody en entrées chartables."""
    if wb.get("error") or wb.get("error_no_station"):
        return [wb]
    plan_nom = wb.get("plan_nom", "")
    metrics = wb.get("requested_metrics", "both")
    out: list[dict] = []
    for st in wb.get("stations") or []:
        if not isinstance(st, dict):
            continue
        out.append(
            {
                "plan_nom": plan_nom,
                "requested_metrics": metrics,
                "station_id": st.get("station_id"),
                "plan_eau": st.get("plan_eau"),
                "description": st.get("description"),
                "distance_km": st.get("distance_km"),
                "match_reason": st.get("match_reason"),
                "niveau_m": st.get("niveau_m"),
                "debit_m3s": st.get("debit_m3s"),
                "observed_at": st.get("observed_at"),
                "history": st.get("history"),
                "error": st.get("error"),
            }
        )
    return out or [wb]


def _collect_hydro_results(tools_log: list[dict]) -> list[dict]:
    results: list[dict] = []
    for entry in tools_log:
        if entry.get("result_pending"):
            continue
        name = entry.get("name")
        if name not in (
            "get_hydromet",
            "get_hydromet_at_plan",
            "get_hydromet_for_waterbody",
        ):
            continue
        result = entry.get("result")
        if not isinstance(result, dict):
            continue
        if name == "get_hydromet_for_waterbody":
            results.extend(_flatten_waterbody_result(result))
        else:
            results.append(result)
    return results


def _hydro_metrics_mode(results: list[dict]) -> str:
    for r in results:
        m = r.get("requested_metrics")
        if m in ("level", "flow", "both"):
            return m
    return "both"


def _format_hydro_value(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _render_hydro_summary_table(results: list[dict]) -> None:
    import pandas as pd

    metrics = _hydro_metrics_mode(results)
    rows: list[dict[str, str]] = []
    for result in results:
        plan_label = result.get("plan_nom") or _hydro_label(result)
        station_label = _hydro_label(result)
        if result.get("error_no_station"):
            rows.append(
                {
                    "Plan d'eau": plan_label,
                    "Station": "—",
                    "Niveau (m)": "—",
                    "Débit (m³/s)": "—",
                    "Observé": "—",
                    "Note": "Pas de station à moins de 25 km",
                }
            )
            continue
        if result.get("error"):
            rows.append(
                {
                    "Plan d'eau": plan_label,
                    "Station": station_label,
                    "Niveau (m)": "—",
                    "Débit (m³/s)": "—",
                    "Observé": "—",
                    "Note": str(result["error"]),
                }
            )
            continue

        history = (
            result.get("history") if isinstance(result.get("history"), dict) else {}
        )
        trend = history.get("trend") if isinstance(history.get("trend"), dict) else {}
        station = result.get("matched_station_plan_eau") or result.get("plan_eau") or ""
        note = ""
        if result.get("distance_km") is not None:
            note = f"{result['distance_km']} km"
        if result.get("match_reason") == "geo" and station:
            note = f"rivière voisine ({station}). {note}".strip()

        row: dict[str, str] = {
            "Plan d'eau": plan_label,
            "Station": station_label,
            "Observé": _format_hydro_value(result.get("observed_at")),
            "Note": note or "—",
        }
        if metrics in ("level", "both"):
            row["Niveau (m)"] = _format_hydro_value(result.get("niveau_m"))
            if trend.get("niveau_m"):
                row["Tendance niveau"] = _format_hydro_value(trend.get("niveau_m"))
        if metrics in ("flow", "both"):
            row["Débit (m³/s)"] = _format_hydro_value(result.get("debit_m3s"))
            if trend.get("debit_m3s"):
                row["Tendance débit"] = _format_hydro_value(trend.get("debit_m3s"))
        rows.append(row)

    if rows:
        st.markdown("**Comparatif hydrométrique**")
        st.dataframe(pd.DataFrame(rows), hide_index=True)


def _unique_chart_label(base: str, used: set[str]) -> str:
    label = base
    suffix = 2
    while label in used:
        label = f"{base} ({suffix})"
        suffix += 1
    used.add(label)
    return label


def _render_hydro_history(result: dict, metrics: str = "both") -> None:
    history = result.get("history")
    if not isinstance(history, dict):
        return
    series = history.get("series")
    if not series:
        return

    import pandas as pd

    label = _hydro_label(result)
    if label:
        st.markdown(f"**{label}**")

    df = pd.DataFrame(series)
    if df.empty or "observed_at" not in df.columns:
        return
    df["observed_at"] = pd.to_datetime(df["observed_at"])
    df = df.set_index("observed_at").sort_index()

    period = history.get("period_days", 7)
    st.caption(f"Historique CEHQ — {period} derniers jours (points horaires)")

    if metrics in ("level", "both") and history.get("has_niveau") and "niveau_m" in df.columns:
        st.markdown("**Niveau (m)**")
        st.line_chart(df[["niveau_m"]])
    if metrics in ("flow", "both") and history.get("has_debit") and "debit_m3s" in df.columns:
        st.markdown("**Débit (m³/s)**")
        st.line_chart(df[["debit_m3s"]])

    daily = history.get("daily")
    if daily:
        with st.expander("Résumé journalier", expanded=False):
            st.dataframe(pd.DataFrame(daily), hide_index=True)


def _render_combined_hydro_charts(results: list[dict], metrics: str = "both") -> None:
    import pandas as pd

    debit_series: dict[str, pd.Series] = {}
    niveau_series: dict[str, pd.Series] = {}
    used_labels: set[str] = set()
    period: int | None = None

    for result in results:
        history = result.get("history")
        if not isinstance(history, dict):
            continue
        series = history.get("series")
        if not series:
            continue

        label = _unique_chart_label(_hydro_label(result), used_labels)
        period = history.get("period_days", period)

        df = pd.DataFrame(series)
        if df.empty or "observed_at" not in df.columns:
            continue
        df["observed_at"] = pd.to_datetime(df["observed_at"])
        df = df.set_index("observed_at").sort_index()

        if metrics in ("flow", "both") and history.get("has_debit") and "debit_m3s" in df.columns:
            debit_series[label] = df["debit_m3s"]
        if metrics in ("level", "both") and history.get("has_niveau") and "niveau_m" in df.columns:
            niveau_series[label] = df["niveau_m"]

    if not debit_series and not niveau_series:
        return

    days = period or 7
    st.caption(
        f"Historique CEHQ — {days} derniers jours (comparaison, points horaires)"
    )

    if niveau_series:
        st.markdown("**Niveau (m)**")
        st.line_chart(pd.DataFrame(niveau_series).sort_index())
    if debit_series:
        st.markdown("**Débit (m³/s)**")
        st.line_chart(pd.DataFrame(debit_series).sort_index())

    daily_blocks = [
        (_hydro_label(r), r["history"]["daily"])
        for r in results
        if isinstance(r.get("history"), dict) and r["history"].get("daily")
    ]
    if daily_blocks:
        with st.expander("Résumés journaliers", expanded=False):
            for label, daily in daily_blocks:
                st.markdown(f"**{label}**")
                st.dataframe(pd.DataFrame(daily), hide_index=True)


def _render_visible_hydro_outputs(tools_log: list[dict]) -> None:
    """Tableau + graphiques hydro visibles dans le chat (hors expander outils)."""
    results = _collect_hydro_results(tools_log)
    if not results:
        return

    metrics = _hydro_metrics_mode(results)
    with_history = [
        r
        for r in results
        if isinstance(r.get("history"), dict) and r["history"].get("series")
    ]

    if len(results) >= 2:
        _render_hydro_summary_table(results)
        if len(with_history) >= 2:
            _render_combined_hydro_charts(with_history, metrics=metrics)
        elif len(with_history) == 1:
            _render_hydro_history(with_history[0], metrics=metrics)
        return

    _render_hydro_summary_table(results)
    if with_history:
        if len(with_history) >= 2:
            _render_combined_hydro_charts(with_history, metrics=metrics)
        else:
            _render_hydro_history(with_history[0], metrics=metrics)


def _render_tools(tools_log: list[dict]) -> None:
    label = f"{len(tools_log)} appel{'s' if len(tools_log) > 1 else ''} d'outil"
    with st.expander(label, expanded=False):
        for i, entry in enumerate(tools_log, start=1):
            cols = st.columns([3, 1])
            with cols[0]:
                st.markdown(f"**{i}. `{entry['name']}`**")
                if entry.get("args"):
                    st.caption(f"`{entry['args']}`")
            with cols[1]:
                if entry.get("duration_ms") is not None:
                    st.caption(f"{entry['duration_ms']} ms")

            if entry.get("result_pending"):
                st.info("en cours…")
                continue

            links = _collect_links(entry.get("result"))
            if links:
                seen = set()
                bullets = []
                for label_url, url in links:
                    if url in seen:
                        continue
                    seen.add(url)
                    bullets.append(f"[{label_url}]({url})")
                st.markdown("Liens : " + " · ".join(bullets))

            with st.expander("voir le JSON brut", expanded=False):
                st.json(entry.get("result"), expanded=2)
            st.divider()


def _render_history_page() -> None:
    store = _conversation_store()
    current = st.session_state.conversation_id

    st.markdown("## Historique des conversations")
    if st.session_state.pop("conversation_loaded_hint", False):
        st.success("Conversation chargée — passez à l'onglet **Chat** pour continuer.")

    st.text_input(
        "Rechercher",
        key="history_search",
        placeholder="Nom de conversation…",
        disabled=st.session_state.running,
    )
    query = st.session_state.get("history_search") or None

    list_col, detail_col = st.columns([1, 2], gap="large")

    with list_col:
        st.markdown("#### Liste")
        convs = store.list_conversations(limit=50, query=query)
        if not convs:
            st.caption("Aucune conversation.")
        else:
            for conv in convs:
                cid = conv["id"]
                title = conv["title"]
                updated = conv["updated_at"][:10] if conv.get("updated_at") else ""
                n_msgs = conv.get("message_count", 0)
                suffix = " (vide)" if n_msgs == 0 else f" ({n_msgs} msg)"
                label = (
                    f"{title[:48]}{'…' if len(title) > 48 else ''}{suffix} · {updated}"
                )
                st.button(
                    label,
                    key=f"conv_{cid}",
                    width="stretch",
                    type="primary" if cid == current else "secondary",
                    disabled=st.session_state.running,
                    on_click=_on_select_conversation,
                    args=(cid,),
                )

    with detail_col:
        meta = _current_conversation_meta()
        if meta:
            st.markdown("#### Conversation active")
            if st.session_state.get("_rename_sync_cid") != current:
                st.session_state["rename_conversation_input"] = meta["title"]
                st.session_state["_rename_sync_cid"] = current
            st.text_input(
                "Nom",
                key="rename_conversation_input",
                disabled=st.session_state.running,
            )
            st.button(
                "Enregistrer le nom",
                key="rename_conversation_save",
                disabled=st.session_state.running,
                on_click=_on_rename_conversation,
            )
            st.caption(
                f"Créée le {meta.get('created_at', '')[:10]} · "
                f"MAJ {meta.get('updated_at', '')[:16].replace('T', ' ')}"
            )

            if st.session_state.messages:
                st.markdown("#### Aperçu")
                for msg in st.session_state.messages:
                    role = "Vous" if msg["role"] == "user" else "Assistant"
                    preview = msg["text"][:500]
                    if len(msg["text"]) > 500:
                        preview += "…"
                    st.markdown(f"**{role}** — {preview}")
            else:
                st.info("Cette conversation est vide.")
        else:
            st.caption("Sélectionnez une conversation dans la liste.")


def _render_map_page() -> None:
    from peche.map_view import (
        map_context_from_messages,
        map_layer_counts,
        map_unavailable_reason,
        render_map_streamlit,
    )

    st.markdown("## Carte — hydro, LCE, bassins et règlements")
    counts = map_layer_counts()
    lce_note = (
        f" · **{counts.get('lce', 0):,}** entités LCE (viewport zoom ≥ 10)"
        if counts.get("lce")
        else ""
    )
    st.caption(
        f"**{counts['hydro']}** stations hydro · "
        f"**{counts['barrages']}** barrages CEHQ · "
        f"**{counts['tides']}** marées SHC{lce_note}. "
        "Couches activables en haut à droite. "
        "Pin vert = plan RegPec du chat ; popups = espèces en vigueur."
    )
    if counts["barrages"] == 0:
        st.info(
            "Pas de cache barrages — lancer `python3 -m peche.barrages sync` "
            "(inclus dans `scripts/refresh-data.sh`)."
        )
    reason = map_unavailable_reason()
    if reason:
        st.warning(reason)
        return
    if counts["tides"] == 0:
        st.info(
            "Pas de cache marées — lancer `python3 -m peche.tides sync` "
            "(inclus dans `scripts/refresh-data.sh`)."
        )
    ctx = map_context_from_messages(st.session_state.messages)
    if ctx.get("label"):
        st.info(f"Contexte chat : **{ctx['label']}**")
    if ctx.get("lce_match"):
        lm = ctx["lce_match"]
        st.caption(
            f"Match LCE : {lm.get('type', '—')} "
            f"({lm.get('distance_km', '—')} km, score {lm.get('match_score', '—')})"
        )

    bbox = st.session_state.get("map_bbox") or ctx.get("bbox")
    zoom = ctx.get("zoom", 7)
    if st.session_state.get("map_zoom"):
        zoom = int(st.session_state["map_zoom"])

    try:
        folium_state = render_map_streamlit(
            center=ctx.get("center"),
            zoom=zoom,
            plan_pin=ctx.get("plan_pin"),
            weather=ctx.get("weather"),
            height=720,
            bbox=bbox,
            segment_points=ctx.get("segment_points"),
            reg_summary=ctx.get("reg_summary"),
        )
        if folium_state and folium_state.get("bounds"):
            b = folium_state["bounds"]
            st.session_state["map_bbox"] = (
                b["_southWest"]["lng"],
                b["_southWest"]["lat"],
                b["_northEast"]["lng"],
                b["_northEast"]["lat"],
            )
            st.session_state["map_zoom"] = zoom
    except Exception as exc:  # noqa: BLE001
        st.error(f"Carte indisponible : {exc}")


# ---------- Streaming chat ----------


import time as _time


def _run_chat_stream(prompt: str) -> None:
    """Stream la réponse assistant (appelé dans la zone de messages, au-dessus de la saisie)."""
    with st.chat_message("assistant"):
        text_box = st.empty()
        charts_box = st.empty()
        tools_box = st.empty()

        text_acc: list[str] = []
        tools_log: list[dict] = []

        def _refresh_assistant_ui(*, streaming: bool = False) -> None:
            text = "".join(text_acc)
            if streaming and text:
                text += " _…_"
            text_box.markdown(text or "\u200b")
            with charts_box.container():
                _render_visible_hydro_outputs(tools_log)
            with tools_box.container():
                if tools_log:
                    _render_tools(tools_log)

        try:
            for evt in stream_chat(prompt, history=st.session_state.history):
                kind = evt["type"]
                if kind == "text":
                    text_acc.append(evt["text"])
                    _refresh_assistant_ui(streaming=True)
                elif kind == "tool_call":
                    tools_log.append(
                        {
                            "name": evt["name"],
                            "args": evt["args"],
                            "result": None,
                            "result_pending": True,
                            "duration_ms": None,
                            "_t0": _time.monotonic(),
                        }
                    )
                    _refresh_assistant_ui(streaming=bool(text_acc))
                elif kind == "tool_result":
                    if tools_log:
                        last = tools_log[-1]
                        last["result"] = evt["result"]
                        last["result_pending"] = False
                        last["duration_ms"] = int(
                            (_time.monotonic() - last.pop("_t0", _time.monotonic()))
                            * 1000
                        )
                    _refresh_assistant_ui(streaming=bool(text_acc))
                elif kind == "error":
                    text_acc.append(f"\n\n*[erreur : {evt['error']}]*")
                    _refresh_assistant_ui()
                elif kind == "done":
                    _refresh_assistant_ui()
        finally:
            st.session_state.running = False
            st.session_state.stream_prompt = None

        assistant_text = "".join(text_acc)
        st.session_state.messages.append(
            {
                "role": "assistant",
                "text": assistant_text,
                "tools": tools_log,
            }
        )
        _store = _conversation_store()
        _cid = _ensure_conversation_id()
        _store.append_exchange(_cid, prompt, assistant_text, tools_log or None)
        _store.save_gemini_history(_cid, st.session_state.history)
        st.rerun()


def _chat_scroll_height() -> int | None:
    """Hauteur du fil : compacte si vide, croît avec les messages (max 560 px)."""
    msgs = st.session_state.messages
    streaming = bool(st.session_state.stream_prompt and st.session_state.running)
    if not msgs and not streaming:
        return None

    units = len(msgs) + (1 if streaming else 0)
    for msg in msgs:
        tools = msg.get("tools") or []
        if tools:
            units += min(len(tools), 4)

    height = 64 + units * 96
    if streaming:
        height += 128  # marge pour la réponse en cours (+ graphiques hydro)
    return min(560, max(140, height))


# ---------- Pages (onglets) ----------


_sidebar()

tab_chat, tab_history, tab_map = st.tabs(["Chat", "Historique", "Carte"])

with tab_chat:
    st.markdown("# Pêche au Québec")
    _conv_meta = _current_conversation_meta()
    if _conv_meta:
        st.caption(
            f"Conversation : **{_conv_meta['title']}** — "
            f"Aujourd'hui : {date.isoformat(_today())}"
        )
    else:
        st.caption(f"Aujourd'hui : {date.isoformat(_today())}")

    scroll_h = _chat_scroll_height()
    chat_scroll = (
        st.container(height=scroll_h, border=False)
        if scroll_h is not None
        else st.container()
    )
    with chat_scroll:
        if not st.session_state.messages and not st.session_state.stream_prompt:
            st.caption(
                "Posez une question pour démarrer, ou chargez une conversation "
                "depuis l'onglet **Historique**."
            )

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["text"])
                if msg.get("tools"):
                    _render_visible_hydro_outputs(msg["tools"])
                    _render_tools(msg["tools"])

        if st.session_state.stream_prompt and st.session_state.running:
            _run_chat_stream(st.session_state.stream_prompt)

    prompt = st.chat_input(
        "Posez votre question…",
        disabled=st.session_state.running,
        key="chat_input_main",
    )

    if prompt:
        _ensure_conversation_id()
        st.session_state.messages.append({"role": "user", "text": prompt})
        st.session_state.stream_prompt = prompt
        st.session_state.running = True
        st.rerun()

with tab_history:
    _render_history_page()

with tab_map:
    _render_map_page()
