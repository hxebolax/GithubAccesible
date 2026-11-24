"""Descargar el código de un repositorio en zip desde cualquier sitio (listas, búsqueda, ventana).

Por qué un módulo propio: la misma orden está en la sección Código, en las
listas de repositorios, en los resultados de búsqueda y en el menú
Repositorio. Aquí se pide dónde guardarlo y se pone en el gestor de descargas
de la aplicación (sigue aunque se cierre la ventana; se pausa y se reanuda en
«Descargas»). La cabecera la elige ``aceptar_para_descarga``: ``zipball`` exige
JSON (con «octet-stream» GitHub da 415).

GitHub manda el zip sin tamaño total (se genera al vuelo): el gestor muestra lo
descargado en vez de un porcentaje.
"""

from __future__ import annotations

import builtins
import logging
from pathlib import Path
from typing import Any

import wx

log = logging.getLogger(__name__)


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
	from app.ui.descargas import iniciar_descarga

	# En el gestor de descargas: sigue aunque se cierre la ventana, se puede pausar y reanudar.
	descripcion = _("Código de {n}").format(n=nombre) + (f" ({ref})" if ref else "")
	return iniciar_descarga(padre, ctx, ctx.api().archivo_zip(nombre, ref), destino, destino.name, origen=descripcion,
		sobrescribir=True)
