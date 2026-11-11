"""Observabilité Langfuse — optionnelle et sans effet de bord si désactivée.

Activée uniquement si `LANGFUSE_PUBLIC_KEY` et `LANGFUSE_SECRET_KEY` sont
définies (et `LANGFUSE_ENABLED` != 0). Sinon, toutes les fonctions de ce module
sont des no-op : le reste du code peut les appeler sans condition.

Deux styles d'usage, selon le contexte d'exécution :

* **Sections synchrones** (outils, appel LLM non-streamé) :
  `with observation("nom", as_type="tool") as obs:` — l'observation devient la
  courante et les observations imbriquées s'y rattachent automatiquement.
* **Générateurs** (boucle agent en streaming) : `Span.child(...)` +
  `.end()` explicites. Le générateur est itéré depuis différents threads par
  Starlette ; un contexte OpenTelemetry ouvert à travers des `yield` serait
  détaché dans le mauvais thread. On passe donc le parent explicitement.

L'instrumentation ne doit jamais casser l'application : toute erreur du SDK
est journalisée (debug) puis ignorée.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from contextlib import ExitStack, contextmanager, nullcontext
from typing import Any, Iterator

log = logging.getLogger("peche.observability")

# Au-delà, un input/output est remplacé par un extrait (évite des traces de
# plusieurs Mo : réponses d'outils GeoJSON, historique long…).
MAX_PAYLOAD_CHARS = int(os.environ.get("LANGFUSE_MAX_PAYLOAD_CHARS", "100000"))

_SECRET_RE = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
_SECRET_KEYS = {"api_key", "apikey", "x-gemini-api-key", "authorization"}

_lock = threading.Lock()
_state: dict[str, Any] = {"init": False, "client": None}


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


def _mask(*, data: Any, **_: Any) -> Any:
    """Retire les clés API (BYOK) de tout ce qui part vers Langfuse."""
    if isinstance(data, str):
        return _SECRET_RE.sub("[REDACTED_API_KEY]", data)
    if isinstance(data, dict):
        return {
            k: "[REDACTED]"
            if isinstance(k, str) and k.lower() in _SECRET_KEYS
            else _mask(data=v)
            for k, v in data.items()
        }
    if isinstance(data, (list, tuple)):
        return [_mask(data=v) for v in data]
    return data


def _sanitize_env() -> None:
    """Retire espaces et CR/LF des variables LANGFUSE_* (un .env en CRLF
    laisse `\\r` dans la clé, et l'exporteur OTel rejette le header)."""
    for name, value in list(os.environ.items()):
        if name.startswith("LANGFUSE_") and value != value.strip():
            os.environ[name] = value.strip()


def _configured() -> bool:
    _sanitize_env()
    if os.environ.get("LANGFUSE_ENABLED", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )


def get_client() -> Any | None:
    """Client Langfuse (singleton) ou None si désactivé / indisponible."""
    with _lock:
        if not _state["init"]:
            _state["init"] = True
            if _configured():
                try:
                    from langfuse import Langfuse

                    _state["client"] = Langfuse(mask=_mask)
                    log.info("Langfuse tracing enabled")
                except Exception:  # noqa: BLE001
                    log.warning("Langfuse init failed — tracing disabled", exc_info=True)
        return _state["client"]


def set_client(client: Any | None) -> None:
    """Injecte un client (tests) ; `None` désactive le tracing."""
    with _lock:
        _state["init"] = True
        _state["client"] = client


def reset() -> None:
    """Oublie le client courant (la prochaine utilisation relit l'environnement)."""
    with _lock:
        _state["init"] = False
        _state["client"] = None


def flush() -> None:
    client = get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:  # noqa: BLE001
        log.debug("Langfuse flush failed", exc_info=True)


# --------------------------------------------------------------------------- #
# Payloads
# --------------------------------------------------------------------------- #


def clip(value: Any, limit: int | None = None) -> Any:
    """Renvoie `value` tel quel s'il est raisonnable, sinon un extrait texte."""
    limit = limit or MAX_PAYLOAD_CHARS
    if value is None or isinstance(value, (bool, int, float)):
        return value
    try:
        text = value if isinstance(value, str) else json.dumps(
            value, ensure_ascii=False, default=str
        )
    except Exception:  # noqa: BLE001
        text = repr(value)
    if len(text) <= limit:
        return value
    return f"{text[:limit]}…[tronqué : {len(text)} caractères au total]"


def _prep(kw: dict[str, Any]) -> dict[str, Any]:
    out = dict(kw)
    for key in ("input", "output"):
        if key in out:
            out[key] = clip(out[key])
    if isinstance(out.get("metadata"), dict):
        out["metadata"] = {
            k: clip(v, limit=MAX_PAYLOAD_CHARS // 2)
            for k, v in out["metadata"].items()
            if v is not None
        }
    return out


def _propagate(attrs: dict[str, Any]):
    if not attrs:
        return nullcontext()
    from langfuse import propagate_attributes

    return propagate_attributes(**attrs)


# --------------------------------------------------------------------------- #
# Span wrapper
# --------------------------------------------------------------------------- #


class Span:
    """Enveloppe sûre d'une observation Langfuse (ou no-op si désactivé)."""

    __slots__ = ("_obs", "_attrs", "stats", "_ended")

    def __init__(
        self,
        obs: Any | None = None,
        attrs: dict[str, Any] | None = None,
        stats: dict[str, Any] | None = None,
    ) -> None:
        self._obs = obs
        self._attrs = attrs or {}
        self.stats: dict[str, Any] = stats if stats is not None else {}
        self._ended = False

    def __bool__(self) -> bool:
        return self._obs is not None

    # -- création -----------------------------------------------------------

    def child(self, name: str, as_type: str = "span", **kw: Any) -> "Span":
        """Observation enfant à cycle de vie manuel (appeler `.end()`)."""
        if self._obs is None:
            return NOOP
        try:
            with _propagate(self._attrs):
                obs = self._obs.start_observation(
                    name=name, as_type=as_type, **_prep(kw)
                )
            return Span(obs, self._attrs, self.stats)
        except Exception:  # noqa: BLE001
            log.debug("Langfuse child(%s) failed", name, exc_info=True)
            return NOOP

    @contextmanager
    def current(self, name: str, as_type: str = "span", **kw: Any) -> Iterator["Span"]:
        """Enfant rendu courant le temps du bloc (sections 100 % synchrones)."""
        span = NOOP
        stack = ExitStack()
        if self._obs is not None:
            try:
                stack.enter_context(_propagate(self._attrs))
                obs = stack.enter_context(
                    self._obs.start_as_current_observation(
                        name=name, as_type=as_type, **_prep(kw)
                    )
                )
                span = Span(obs, self._attrs, self.stats)
            except Exception:  # noqa: BLE001
                log.debug("Langfuse current(%s) failed", name, exc_info=True)
                _close(stack)
                stack = ExitStack()
        try:
            yield span
        except BaseException as exc:
            span.fail(exc)
            raise
        finally:
            _close(stack)

    # -- mise à jour --------------------------------------------------------

    def update(self, **kw: Any) -> None:
        if self._obs is None:
            return
        try:
            self._obs.update(**_prep(kw))
        except Exception:  # noqa: BLE001
            log.debug("Langfuse update failed", exc_info=True)

    def fail(self, exc: BaseException | str) -> None:
        msg = exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
        self.update(level="ERROR", status_message=msg)

    def end(self) -> None:
        if self._obs is None or self._ended:
            return
        self._ended = True
        try:
            self._obs.end()
        except Exception:  # noqa: BLE001
            log.debug("Langfuse end failed", exc_info=True)

    # -- statistiques agrégées (remontées sur l'observation racine) ----------

    def count(self, key: str, n: int = 1) -> None:
        if self._obs is not None:
            self.stats[key] = self.stats.get(key, 0) + n

    def append(self, key: str, value: Any) -> None:
        if self._obs is not None:
            self.stats.setdefault(key, []).append(value)


def _close(stack: ExitStack) -> None:
    try:
        stack.close()
    except Exception:  # noqa: BLE001
        log.debug("Langfuse context close failed", exc_info=True)


NOOP = Span()


# --------------------------------------------------------------------------- #
# Points d'entrée
# --------------------------------------------------------------------------- #


def start_trace(
    name: str,
    *,
    as_type: str = "agent",
    session_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    trace_metadata: dict[str, str] | None = None,
    **kw: Any,
) -> Span:
    """Ouvre une trace racine (cycle de vie manuel : appeler `.end()`).

    `trace_metadata` est propagé à *toutes* les observations (valeurs `str`
    ≤ 200 car., filtrable dans l'UI). Les données riches vont dans
    `metadata=` de la racine.
    """
    client = get_client()
    if client is None:
        return NOOP
    attrs: dict[str, Any] = {"trace_name": name}
    if session_id:
        attrs["session_id"] = session_id
    if user_id:
        attrs["user_id"] = user_id
    if tags:
        attrs["tags"] = tags
    if trace_metadata:
        attrs["metadata"] = {k: str(v)[:200] for k, v in trace_metadata.items() if v}
    try:
        with _propagate(attrs):
            obs = client.start_observation(name=name, as_type=as_type, **_prep(kw))
        return Span(obs, attrs)
    except Exception:  # noqa: BLE001
        log.debug("Langfuse start_trace(%s) failed", name, exc_info=True)
        return NOOP


@contextmanager
def observation(name: str, as_type: str = "span", **kw: Any) -> Iterator[Span]:
    """Observation courante (rattachée au contexte actif, sinon nouvelle trace)."""
    client = get_client()
    span = NOOP
    stack = ExitStack()
    if client is not None:
        try:
            obs = stack.enter_context(
                client.start_as_current_observation(
                    name=name, as_type=as_type, **_prep(kw)
                )
            )
            span = Span(obs)
        except Exception:  # noqa: BLE001
            log.debug("Langfuse observation(%s) failed", name, exc_info=True)
            _close(stack)
            stack = ExitStack()
    try:
        yield span
    except BaseException as exc:
        span.fail(exc)
        raise
    finally:
        _close(stack)
