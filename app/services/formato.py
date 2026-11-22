"""Textos para mostrar y anunciar: fechas, tamaños, estados y resúmenes (sin wx).

Todo lo que llega de GitHub en inglés o en formato técnico (``open``,
``2024-05-01T10:00:00Z``, ``12345`` bytes) se convierte aquí en español
breve y fácil de escuchar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core import i18n  # noqa: F401 - instala _, N_ y ngettext en builtins aunque se importe suelto (pruebas)
from app.services.github.cliente import fecha_iso


def ngettext_(singular: str, plural: str, n: int) -> str:
	"""Alias antiguo de ``ngettext`` (lo importa ``app.ui.editor``). El extractor no lo reconoce: use ``ngettext``."""
	return ngettext(singular, plural, n)


def fecha_relativa(texto_o_fecha: str | datetime | None, ahora: datetime | None = None) -> str:
	"""«hace 5 minutos», «ayer», «hace 3 días», «el 12/03/2023»."""
	fecha = texto_o_fecha if isinstance(texto_o_fecha, datetime) else fecha_iso(texto_o_fecha)
	if fecha is None:
		return ""
	ahora = ahora or datetime.now(UTC)
	if fecha.tzinfo is None:
		fecha = fecha.replace(tzinfo=UTC)
	segundos = (ahora - fecha).total_seconds()
	futuro = segundos < 0
	segundos = abs(segundos)
	if segundos < 45:
		return _("ahora mismo")
	minutos = int(segundos // 60)
	horas = int(segundos // 3600)
	dias = int(segundos // 86400)
	if minutos < 60:
		cantidad = ngettext("{n} minuto", "{n} minutos", max(1, minutos)).format(n=max(1, minutos))
	elif horas < 24:
		cantidad = ngettext("{n} hora", "{n} horas", horas).format(n=horas)
	elif dias == 1 and not futuro:
		return _("ayer")
	elif dias < 30:
		cantidad = ngettext("{n} día", "{n} días", dias).format(n=dias)
	elif dias < 365:
		meses = dias // 30
		cantidad = ngettext("{n} mes", "{n} meses", meses).format(n=meses)
	else:
		return _("el {fecha}").format(fecha=fecha.astimezone().strftime(_FORMATO_FECHA()))
	return (_("dentro de {c}") if futuro else _("hace {c}")).format(c=cantidad)


def fecha_completa(texto_o_fecha: str | datetime | None) -> str:
	fecha = texto_o_fecha if isinstance(texto_o_fecha, datetime) else fecha_iso(texto_o_fecha)
	if fecha is None:
		return ""
	return fecha.astimezone().strftime(_FORMATO_FECHA_HORA())


# Formatos que cambian con el idioma. Se deciden en el código y no en el catálogo: los
# marcadores de strftime (%d, %Y...) no pueden cambiar en una traducción.
#: idioma → (fecha, fecha y hora, separador decimal, separador de miles).
_FORMATOS = {
	"es": ("%d/%m/%Y", "%d/%m/%Y %H:%M", ",", "."),
	# «Nov 22, 2026»: sin la ambigüedad de 11/22 frente a 22/11 entre países de habla inglesa.
	"en": ("%b %d, %Y", "%b %d, %Y %H:%M", ".", ","),
}


def _formatos() -> tuple[str, str, str, str]:

	return _FORMATOS.get(i18n.idioma_corto(), _FORMATOS["es"])


def _FORMATO_FECHA() -> str:  # noqa: N802
	return _formatos()[0]


def _FORMATO_FECHA_HORA() -> str:  # noqa: N802
	return _formatos()[1]


def _SEPARADORES() -> str:  # noqa: N802
	return _formatos()[2] + _formatos()[3]


def _decimal(valor: float) -> str:
	"""Un decimal con la coma o el punto del idioma."""
	return f"{valor:.1f}".replace(".", _SEPARADORES()[0])


def fecha(texto: str | None, relativa: bool = True) -> str:
	return fecha_relativa(texto) if relativa else fecha_completa(texto)


def tamano(octetos: int | float | None) -> str:
	if octetos is None:
		return ""
	valor = float(octetos)
	for unidad in ("bytes", "KB", "MB", "GB", "TB"):
		if valor < 1024 or unidad == "TB":
			if unidad == "bytes":
				return ngettext("{n} byte", "{n} bytes", int(valor)).format(n=int(valor))
			return f"{_decimal(valor)} {unidad}"
		valor /= 1024
	return ""


def numero(valor: int | None) -> str:
	if valor is None:
		return ""
	# El inglés agrupa los miles con coma (1,234); el español, con punto (1.234).
	return f"{int(valor):,}".replace(",", _SEPARADORES()[1])


def duracion(segundos: float | None) -> str:
	if segundos is None:
		return ""
	segundos = int(segundos)
	if segundos < 60:
		return ngettext("{n} segundo", "{n} segundos", segundos).format(n=segundos)
	minutos, s = divmod(segundos, 60)
	if minutos < 60:
		return _("{m} min {s} s").format(m=minutos, s=s)
	horas, m = divmod(minutos, 60)
	return _("{h} h {m} min").format(h=horas, m=m)


ESTADOS = {
	"open": N_("Abierta"),
	"closed": N_("Cerrada"),
	"merged": N_("Fusionada"),
	"draft": N_("Borrador"),
	"queued": N_("En cola"),
	"in_progress": N_("En curso"),
	"completed": N_("Terminada"),
	"waiting": N_("Esperando"),
	"requested": N_("Pedida"),
	"pending": N_("Pendiente"),
	"success": N_("Correcto"),
	"failure": N_("Fallo"),
	"cancelled": N_("Cancelada"),
	"skipped": N_("Omitida"),
	"neutral": N_("Neutral"),
	"timed_out": N_("Tiempo agotado"),
	"action_required": N_("Requiere acción"),
	"stale": N_("Obsoleta"),
	"startup_failure": N_("Fallo al arrancar"),
	"error": N_("Error"),
	"active": N_("Activa"),
	"inactive": N_("Inactiva"),
	"dismissed": N_("Descartada"),
	"fixed": N_("Corregida"),
	"resolved": N_("Resuelta"),
	"auto_dismissed": N_("Descartada automáticamente"),
	"APPROVED": N_("Aprobada"),
	"CHANGES_REQUESTED": N_("Cambios pedidos"),
	"COMMENTED": N_("Comentada"),
	"DISMISSED": N_("Descartada"),
	"PENDING": N_("Pendiente"),
	"Available": N_("Disponible"),
	"Shutdown": N_("Apagado"),
	"Starting": N_("Arrancando"),
	"public": N_("Público"),
	"private": N_("Privado"),
	"internal": N_("Interno"),
	"admin": N_("Administración"),
	"maintain": N_("Mantenimiento"),
	"push": N_("Escritura"),
	"triage": N_("Clasificación"),
	"pull": N_("Lectura"),
	"write": N_("Escritura"),
	"read": N_("Lectura"),
	"member": N_("Miembro"),
	"maintainer": N_("Mantenedor"),
	"critical": N_("Crítica"),
	"high": N_("Alta"),
	"medium": N_("Media"),
	"moderate": N_("Moderada"),
	"low": N_("Baja"),
	"note": N_("Nota"),
	"warning": N_("Aviso"),
}


def estado(valor: str | None) -> str:
	if not valor:
		return ""
	return _(ESTADOS.get(valor, ESTADOS.get(str(valor).lower(), str(valor))))


def estado_issue(issue: dict) -> str:
	if issue.get("pull_request"):
		if (issue.get("pull_request") or {}).get("merged_at"):
			return _("Fusionado")
	if issue.get("draft"):
		return _("Borrador")
	if issue.get("merged_at") or issue.get("merged"):
		return _("Fusionado")
	texto = estado(issue.get("state"))
	motivo = issue.get("state_reason")
	if issue.get("state") == "closed" and motivo == "not_planned":
		texto += " " + _("(no planificada)")
	return texto


def estado_ejecucion(ejecucion: dict) -> str:
	"""Estado de una ejecución o trabajo de Actions: «En curso», «Correcto», «Fallo»..."""
	if ejecucion.get("status") != "completed":
		return estado(ejecucion.get("status"))
	return estado(ejecucion.get("conclusion")) or estado("completed")


def login(usuario: dict | None) -> str:
	if not usuario:
		return _("(desconocido)")
	texto = usuario.get("login") or usuario.get("name") or ""
	if usuario.get("type") == "Bot" or texto.endswith("[bot]"):
		texto = texto.replace("[bot]", "") + " " + _("(bot)")
	return texto


def nombres(lista: list[dict] | None, clave: str = "name") -> str:
	return ", ".join(str(e.get(clave, "")) for e in (lista or []) if e)


def etiquetas(issue: dict) -> str:
	return nombres(issue.get("labels"))


def asignados(issue: dict) -> str:
	return ", ".join(login(u) for u in issue.get("assignees") or [])


def reacciones(datos: dict | None) -> str:
	if not datos:
		return ""
	nombres_reaccion = {
		"+1": _("me gusta"), "-1": _("no me gusta"), "laugh": _("risa"), "hooray": _("celebración"),
		"confused": _("confusión"), "heart": _("corazón"), "rocket": _("cohete"), "eyes": _("ojos"),
	}
	partes = [f"{datos[c]} {n}" for c, n in nombres_reaccion.items() if datos.get(c)]
	return ", ".join(partes)


def si_no(valor: Any) -> str:
	return _("Sí") if valor else _("No")


def primera_linea(texto: str | None, maximo: int = 200) -> str:
	if not texto:
		return ""
	linea = texto.strip().splitlines()[0] if texto.strip() else ""
	return linea if len(linea) <= maximo else linea[: maximo - 1] + "…"


def resumen_texto(texto: str | None, maximo: int = 300) -> str:
	if not texto:
		return ""
	plano = " ".join(texto.split())
	return plano if len(plano) <= maximo else plano[: maximo - 1] + "…"


#: Frase de cada tipo de evento del feed que no tiene una más detallada en ``describir_evento``.
#: Son frases enteras con marcadores ({a} quien lo hizo, {r} el repositorio) para que la
#: traducción pueda reordenarlas.
TIPOS_EVENTO = {
	"PushEvent": N_("{a} envió commits a {r}"),
	"CreateEvent": N_("{a} creó {r}"),
	"DeleteEvent": N_("{a} borró {r}"),
	"ForkEvent": N_("{a} bifurcó {r}"),
	"WatchEvent": N_("{a} puso estrella a {r}"),
	"IssuesEvent": N_("{a} issue en {r}"),
	"IssueCommentEvent": N_("{a} comentó en {r}"),
	"PullRequestEvent": N_("{a} pull request en {r}"),
	"PullRequestReviewEvent": N_("{a} revisó un pull request en {r}"),
	"PullRequestReviewCommentEvent": N_("{a} comentó una revisión en {r}"),
	"ReleaseEvent": N_("{a} publicó una release en {r}"),
	"PublicEvent": N_("{a} hizo público {r}"),
	"MemberEvent": N_("{a} añadió un colaborador a {r}"),
	"GollumEvent": N_("{a} editó la wiki de {r}"),
	"CommitCommentEvent": N_("{a} comentó un commit en {r}"),
	"DiscussionEvent": N_("{a} discusión en {r}"),
	"SponsorshipEvent": N_("{a} patrocinio {r}"),
}


def describir_evento(evento: dict) -> str:
	"""Frase corta para un evento del feed: «ana envió 3 commits a dueño/repo»."""
	actor = login(evento.get("actor"))
	repo = (evento.get("repo") or {}).get("name", "")
	tipo = evento.get("type", "")
	carga = evento.get("payload") or {}
	accion = carga.get("action", "")
	acciones = {"opened": _("abrió"), "closed": _("cerró"), "reopened": _("reabrió"), "created": _("creó"),
		"published": _("publicó"), "merged": _("fusionó"), "submitted": _("envió"), "edited": _("editó")}
	if tipo == "PushEvent":
		n = carga.get("size") or len(carga.get("commits") or []) or 1
		rama = str(carga.get("ref", "")).removeprefix("refs/heads/")
		return ngettext("{a} envió {n} commit a {r} (rama {b})", "{a} envió {n} commits a {r} (rama {b})", n).format(
			a=actor, n=n, r=repo, b=rama)
	if tipo == "CreateEvent":
		# ref_type llega de GitHub en inglés: se traduce aquí con artículo, no con _() sobre el dato.
		tipo_ref = carga.get("ref_type", "")
		if tipo_ref == "repository" or not carga.get("ref"):
			return _("{a} creó el repositorio {r}").format(a=actor, r=repo)
		cosas = {"branch": _("la rama"), "tag": _("la etiqueta")}
		return _("{a} creó {t} {nombre} en {r}").format(a=actor, t=cosas.get(tipo_ref, tipo_ref), nombre=carga.get("ref"), r=repo)
	if tipo in ("IssuesEvent", "PullRequestEvent"):
		objeto = carga.get("issue") or carga.get("pull_request") or {}
		que = _("la issue") if tipo == "IssuesEvent" else _("el pull request")
		return _("{a} {acc} {que} #{n} en {r}: {t}").format(
			a=actor, acc=acciones.get(accion, accion), que=que, n=objeto.get("number", ""), r=repo, t=objeto.get("title", ""))
	if tipo == "IssueCommentEvent":
		objeto = carga.get("issue") or {}
		return _("{a} comentó en #{n} de {r}: {t}").format(a=actor, n=objeto.get("number", ""), r=repo, t=objeto.get("title", ""))
	if tipo == "ReleaseEvent":
		release = carga.get("release") or {}
		return _("{a} publicó la release {t} de {r}").format(a=actor, t=release.get("name") or release.get("tag_name", ""), r=repo)
	if tipo == "WatchEvent":
		return _("{a} puso estrella a {r}").format(a=actor, r=repo)
	if tipo == "ForkEvent":
		return _("{a} bifurcó {r}").format(a=actor, r=repo)
	if tipo in TIPOS_EVENTO:
		return _(TIPOS_EVENTO[tipo]).format(a=actor, r=repo).strip()
	# Tipo desconocido: el nombre técnico del evento, tal cual (no hay nada que traducir).
	return f"{actor} {tipo} {repo}".strip()


def url_web_de_api(url_api: str | None, host: str = "github.com") -> str:
	"""Convierte una URL de la API (de una notificación) en la URL de la web."""
	if not url_api:
		return ""
	texto = url_api.replace("https://api.github.com/repos/", f"https://{host}/")
	texto = texto.replace(f"https://{host}/api/v3/repos/", f"https://{host}/")
	texto = texto.replace("/pulls/", "/pull/").replace("/commits/", "/commit/")
	return texto
