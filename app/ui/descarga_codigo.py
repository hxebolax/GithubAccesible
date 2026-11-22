"""Descargar el código de un repositorio en zip desde cualquier sitio (listas, búsqueda, ventana).

Por qué un módulo propio: la misma orden está en la sección Código, en las
listas de repositorios, en los resultados de búsqueda y en el menú
Repositorio. Aquí se pide dónde guardarlo, se descarga en segundo plano con
la cabecera correcta (``zipball`` exige JSON: con «octet-stream» GitHub da
415) y se va diciendo el progreso SOLO en hitos para no saturar al lector.

GitHub manda el zip sin tamaño total (se genera al vuelo), así que en vez de
porcentajes se anuncian los megas cada ``AVISO_CADA_MB``.
"""

from __future__ import annotations

import builtins
import logging
from pathlib import Path
from typing import Any

import wx

from app.services import formato as f
from app.ui.comunes import mensaje_error, mostrar_error

log = logging.getLogger(__name__)

#: Cada cuántos megas se dice cuánto lleva descargado (si GitHub no da el total).
AVISO_CADA_MB = 10


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def nombre_zip(nombre: str, ref: str = "") -> str:
	"""«ana/proyecto» y «main» → «proyecto-main.zip» (las barras de la rama pasan a guiones)."""
	corto = (nombre or "repositorio").strip("/").rpartition("/")[2] or "repositorio"
	return f"{corto}-{ref or 'principal'}.zip".replace("/", "-")


def _carpeta_inicial(ctx: Any) -> str:
	configurada = str(ctx.config.obtener("descargas.carpeta", "") or "")
	if configurada and Path(configurada).is_dir():
		return configurada
	try:
		from app.ui.git.clonar import carpeta_por_defecto

		return carpeta_por_defecto(ctx)
	except Exception:  # noqa: BLE001 - sin carpeta propuesta, el diálogo usa la suya
		return ""


def pedir_destino(padre: wx.Window | None, ctx: Any, nombre: str, ref: str = "") -> Path | None:
	dialogo = wx.FileDialog(padre, _("Guardar el código de {n} en zip").format(n=nombre), defaultDir=_carpeta_inicial(ctx),
		defaultFile=nombre_zip(nombre, ref), wildcard=_("Archivos zip (*.zip)|*.zip"), style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
	try:
		if dialogo.ShowModal() != wx.ID_OK or not dialogo.GetPath():
			return None
		return Path(dialogo.GetPath())
	finally:
		dialogo.Destroy()


def descargar_codigo(padre: wx.Window | None, ctx: Any, nombre: str, ref: str = "", destino: Path | None = None) -> Any:
	"""Pregunta dónde guardar (si no se indica) y descarga el código de ``ref`` (vacío: la rama principal)."""
	if not nombre:
		return None
	destino = destino or pedir_destino(padre, ctx, nombre, ref)
	if destino is None:
		return None
	from app.core.tareas import HitosProgreso

	api = ctx.api()
	hitos = HitosProgreso(25)
	avisado = {"mb": 0}
	ctx.avisar(_("Descargando el código de {n}…").format(n=nombre))

	def trabajo(tarea: Any) -> Path:
		return api.c.descargar(api.archivo_zip(nombre, ref), destino,
			progreso=lambda hecho, total: tarea.progresar(hecho, total),
			cancelado=lambda: bool(getattr(tarea, "cancelado", False)))

	def al_progresar(progreso: Any) -> None:
		if progreso.porcentaje is not None:
			hito = hitos.nuevo_hito(progreso.porcentaje)
			if hito is not None and hito < 100:
				ctx.avisar(_("{p} por ciento").format(p=hito), interrumpir=False)
			return
		megas = int((progreso.hecho or 0) // (1024 * 1024))
		if megas >= avisado["mb"] + AVISO_CADA_MB:
			avisado["mb"] = megas - megas % AVISO_CADA_MB
			ctx.avisar(_("{t} descargados").format(t=f.tamano(progreso.hecho)), interrumpir=False)

	def terminado(ruta: Path) -> None:
		ctx.sonar("descargado")
		ruta = Path(ruta)
		tamano = f.tamano(ruta.stat().st_size) if ruta.exists() else ""
		ctx.avisar(_("Código de {n} guardado en {r} ({t}).").format(n=nombre, r=ruta, t=tamano))

	def fallado(error: BaseException) -> None:
		ctx.sonar("error")
		ventana = padre if isinstance(padre, wx.Window) and padre else None
		mostrar_error(ventana, mensaje_error(error), _("No se pudo descargar el código"))

	return ctx.tareas.enviar(trabajo, al_terminar=terminado, al_fallar=fallado, al_progresar=al_progresar,
		nombre=f"zip:{nombre}", duplicadas="permitir")
