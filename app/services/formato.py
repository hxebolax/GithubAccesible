"""Textos para mostrar y anunciar: fechas, tamaños, estados y resúmenes (sin wx).

Todo lo que llega de GitHub en inglés o en formato técnico (``open``,
``2024-05-01T10:00:00Z``, ``12345`` bytes) se convierte aquí en español
breve y fácil de escuchar.
"""

from __future__ import annotations

import builtins
from datetime import UTC, datetime
from typing import Any

from app.services.github.cliente import fecha_iso


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def ngettext_(singular: str, plural: str, n: int) -> str:
	traducir = getattr(builtins, "ngettext", None)
	if callable(traducir):
		return traducir(singular, plural, n)
	return singular if n == 1 else plural


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
		cantidad = ngettext_("{n} minuto", "{n} minutos", max(1, minutos)).format(n=max(1, minutos))
	elif horas < 24:
		cantidad = ngettext_("{n} hora", "{n} horas", horas).format(n=horas)
	elif dias == 1 and not futuro:
		return _("ayer")
	elif dias < 30:
		cantidad = ngettext_("{n} día", "{n} días", dias).format(n=dias)
	elif dias < 365:
		meses = dias // 30
		cantidad = ngettext_("{n} mes", "{n} meses", meses).format(n=meses)
	else:
		return _("el {fecha}").format(fecha=fecha.astimezone().strftime("%d/%m/%Y"))
	return (_("dentro de {c}") if futuro else _("hace {c}")).format(c=cantidad)


def fecha_completa(texto_o_fecha: str | datetime | None) -> str:
	fecha = texto_o_fecha if isinstance(texto_o_fecha, datetime) else fecha_iso(texto_o_fecha)
	if fecha is None:
		return ""
	return fecha.astimezone().strftime("%d/%m/%Y %H:%M")


def fecha(texto: str | None, relativa: bool = True) -> str:
	return fecha_relativa(texto) if relativa else fecha_completa(texto)


def tamano(octetos: int | float | None) -> str:
	if octetos is None:
		return ""
	valor = float(octetos)
	for unidad in ("bytes", "KB", "MB", "GB", "TB"):
		if valor < 1024 or unidad == "TB":
			if unidad == "bytes":
				return ngettext_("{n} byte", "{n} bytes", int(valor)).format(n=int(valor))
			return f"{valor:.1f} {unidad}".replace(".", ",")
		valor /= 1024
	return ""


def numero(valor: int | None) -> str:
	if valor is None:
		return ""
	return f"{int(valor):,}".replace(",", ".")


def duracion(segundos: float | None) -> str:
	if segundos is None:
		return ""
	segundos = int(segundos)
	if segundos < 60:
		return ngettext_("{n} segundo", "{n} segundos", segundos).format(n=segundos)
	minutos, s = divmod(segundos, 60)
	if minutos < 60:
		return _("{m} min {s} s").format(m=minutos, s=s)
	horas, m = divmod(minutos, 60)
	return _("{h} h {m} min").format(h=horas, m=m)


ESTADOS = {
	"open": "Abierta",
	"closed": "Cerrada",
	"merged": "Fusionada",
	"draft": "Borrador",
	"queued": "En cola",
	"in_progress": "En curso",
	"completed": "Terminada",
	"waiting": "Esperando",
	"requested": "Pedida",
	"pending": "Pendiente",
	"success": "Correcto",
	"failure": "Fallo",
	"cancelled": "Cancelada",
	"skipped": "Omitida",
	"neutral": "Neutral",
	"timed_out": "Tiempo agotado",
	"action_required": "Requiere acción",
	"stale": "Obsoleta",
	"startup_failure": "Fallo al arrancar",
	"error": "Error",
	"active": "Activa",
	"inactive": "Inactiva",
	"dismissed": "Descartada",
	"fixed": "Corregida",
	"resolved": "Resuelta",
	"auto_dismissed": "Descartada automáticamente",
	"APPROVED": "Aprobada",
	"CHANGES_REQUESTED": "Cambios pedidos",
	"COMMENTED": "Comentada",
	"DISMISSED": "Descartada",
	"PENDING": "Pendiente",
	"Available": "Disponible",
	"Shutdown": "Apagado",
	"Starting": "Arrancando",
	"public": "Público",
	"private": "Privado",
	"internal": "Interno",
	"admin": "Administración",
	"maintain": "Mantenimiento",
	"push": "Escritura",
	"triage": "Clasificación",
	"pull": "Lectura",
	"write": "Escritura",
	"read": "Lectura",
	"member": "Miembro",
	"maintainer": "Mantenedor",
	"critical": "Crítica",
	"high": "Alta",
	"medium": "Media",
	"moderate": "Moderada",
	"low": "Baja",
	"note": "Nota",
	"warning": "Aviso",
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


TIPOS_EVENTO = {
	"PushEvent": "envió commits a",
	"CreateEvent": "creó",
	"DeleteEvent": "borró",
	"ForkEvent": "bifurcó",
	"WatchEvent": "puso estrella a",
	"IssuesEvent": "issue en",
	"IssueCommentEvent": "comentó en",
	"PullRequestEvent": "pull request en",
	"PullRequestReviewEvent": "revisó un pull request en",
	"PullRequestReviewCommentEvent": "comentó una revisión en",
	"ReleaseEvent": "publicó una release en",
	"PublicEvent": "hizo público",
	"MemberEvent": "añadió un colaborador a",
	"GollumEvent": "editó la wiki de",
	"CommitCommentEvent": "comentó un commit en",
	"DiscussionEvent": "discusión en",
	"SponsorshipEvent": "patrocinio",
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
		return _("{a} envió {n} commits a {r} (rama {b})").format(a=actor, n=n, r=repo, b=rama)
	if tipo == "CreateEvent":
		return _("{a} creó {t} {nombre} en {r}").format(a=actor, t=_(carga.get("ref_type", "")), nombre=carga.get("ref") or "", r=repo)
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
	return f"{actor} {_(TIPOS_EVENTO.get(tipo, tipo))} {repo}".strip()


def url_web_de_api(url_api: str | None, host: str = "github.com") -> str:
	"""Convierte una URL de la API (de una notificación) en la URL de la web."""
	if not url_api:
		return ""
	texto = url_api.replace("https://api.github.com/repos/", f"https://{host}/")
	texto = texto.replace(f"https://{host}/api/v3/repos/", f"https://{host}/")
	texto = texto.replace("/pulls/", "/pull/").replace("/commits/", "/commit/")
	return texto
