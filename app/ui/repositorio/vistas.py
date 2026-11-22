"""Secciones de lista de la ventana de un repositorio: una ``DefinicionVista`` por sección.

Teclas de las listas (las atiende la propia lista, no la ventana, para no
chocar con los cuadros de texto): Intro abre, Ctrl+N crea, F2 cambia o
renombra, Supr borra (siempre con confirmación), F4 cambia el filtro de
GitHub. Las comunes (F5, Ctrl+F, Ctrl+C, Ctrl+Mayús+C, Ctrl+B, Ctrl+I, Ctrl+M)
están en ``PanelLista.acciones_comunes``.

Letras de acceso: el menú «Acciones» junta las acciones de la vista con las
comunes, que ya usan A, M, F, Q, O, E, N y D. Por eso las acciones de aquí
usan otras letras («A&brir», «Comen&tar»...). ``tests/test_repositorio.py``
comprueba que no se repiten.

Cada panel recibe en ``panel.datos``: ``nombre`` («dueño/repo»), ``info``
(datos del repositorio cuando llegan), ``ir`` (función de la ventana para
saltar a otra sección con filtros) y los filtros propios de la sección.
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import wx

from app.services import formato as f
from app.services.github.api import ruta_repo
from app.services.github.cliente import Pagina
from app.ui import abrir
from app.ui.comunes import (
	confirmar,
	confirmar_peligro,
	copiar,
	elegir_uno,
	elegir_varios,
	en_segundo_plano,
	mensaje_error,
	mostrar_mensaje,
	pedir_texto,
)
from app.ui.repositorio import dialogos as d
from app.ui.vistas.base import Accion, Columna, DefinicionVista, url_html
from app.ui.vistas.principales import columnas_issue, columnas_repositorio, detalle_issue, detalle_repositorio

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ════════════════════════════════════════════════════════════════════════════
# Marco común
# ════════════════════════════════════════════════════════════════════════════

#: Letras que ya usa la ventana del repositorio: «&Secciones», «&Repositorio»,
#: «Ac&ciones» e «&Ir». Las etiquetas de las listas no pueden usarlas.
LETRAS_OCUPADAS = "rcis"


@dataclass
class VistaRepo(DefinicionVista):
	"""``DefinicionVista`` con una etiqueta que cambia con los filtros (rama, carpeta, estado...)."""

	etiqueta_de: Callable[[Any], str] | None = None


def etiqueta_con_letra(texto: str, ocupadas: str = LETRAS_OCUPADAS) -> str:
	"""Pone la letra de acceso en el primer carácter libre: «Issues» → «Iss&ues» si I y S están ocupadas."""
	limpio = texto.replace("&", "&&")
	for posicion, caracter in enumerate(limpio):
		if caracter.isascii() and caracter.isalnum() and caracter.lower() not in ocupadas:
			return limpio[:posicion] + "&" + limpio[posicion:]
	return limpio


def rotular(panel: Any) -> None:
	"""Pone a la lista la etiqueta de su vista (con los filtros vigentes) y su letra de acceso."""
	definicion = panel.definicion
	texto = definicion.titulo
	if isinstance(definicion, VistaRepo) and definicion.etiqueta_de is not None:
		try:
			texto = definicion.etiqueta_de(panel)
		except Exception:  # noqa: BLE001 - una etiqueta rara no debe impedir ver la lista
			log.debug("No se pudo componer la etiqueta de %s", definicion.id, exc_info=True)
	panel.etiqueta.SetLabel(etiqueta_con_letra(texto.rstrip(":") + ":"))


def _nombre(panel: Any) -> str:
	return panel.datos.get("nombre", "")


def _info(panel: Any) -> dict:
	return panel.datos.get("info") or {}


def _rama_defecto(panel: Any) -> str:
	return _info(panel).get("default_branch", "")


def _ir(panel: Any, seccion: str, **datos: Any) -> None:
	"""Salta a otra sección de la misma ventana (con filtros) o abre el repositorio en ella."""
	ir = panel.datos.get("ir")
	if callable(ir):
		ir(seccion, datos)
	else:
		abrir.repositorio(panel.ctx, _nombre(panel), seccion)


def _hacer(panel: Any, funcion: Callable[[], Any], exito: str | Callable[[Any], str], *, recargar: bool = True,
	al_terminar: Callable[[Any], None] | None = None, inicio: str = "") -> None:
	"""Ejecuta una operación en segundo plano y, al terminar, recarga la lista (sin anunciar el total)."""

	def hecho(resultado: Any) -> None:
		if al_terminar is not None:
			al_terminar(resultado)
		if recargar and panel:
			panel.cargar(anunciar=False)

	en_segundo_plano(panel, panel.ctx, funcion, exito=exito, al_terminar=hecho, inicio=inicio)


def _en_fondo(panel: Any, funcion: Callable[[], Any], continuar: Callable[[Any], None], inicio: str = "") -> None:
	"""Pide datos en segundo plano y sigue en la interfaz (para rellenar una elección)."""
	en_segundo_plano(panel, panel.ctx, funcion, al_terminar=lambda r: continuar(r) if panel else None, sonido="", inicio=inicio)


def _recargar_filtrado(panel: Any) -> None:
	rotular(panel)
	panel.cargar()


def _mostrar_texto(panel: Any, titulo: str, etiqueta: str, texto: str) -> None:
	from app.ui.dialogo_texto import DialogoTexto

	dialogo = DialogoTexto(panel, titulo, etiqueta, texto, copiable=True)
	try:
		dialogo.ShowModal()
	finally:
		dialogo.Destroy()


def _web(host: str, nombre: str) -> str:
	return f"https://{host or 'github.com'}/{nombre}"


def _lista(resultado: Any) -> list:
	if isinstance(resultado, Pagina):
		return list(resultado.elementos)
	return list(resultado or [])


def _nombres_ramas(api: Any, nombre: str) -> list[str]:
	return [r.get("name", "") for r in api.todas_las_ramas(nombre) or [] if isinstance(r, dict)]


def _elegir_rama(panel: Any, titulo: str, etiqueta: str, continuar: Callable[[str], None], actual: str = "",
	excluir: str = "") -> None:
	"""Carga las ramas en segundo plano y deja elegir una."""
	api = panel.ctx.api()
	nombre = _nombre(panel)

	def elegir(ramas: list[str]) -> None:
		ramas = [r for r in ramas if r != excluir]
		if not ramas:
			mostrar_mensaje(panel, _("No hay otras ramas."), titulo)
			return
		preferida = actual or _rama_defecto(panel)
		eleccion = elegir_uno(panel, titulo, etiqueta, ramas, ramas.index(preferida) if preferida in ramas else 0)
		if eleccion is not None:
			continuar(ramas[eleccion])

	_en_fondo(panel, lambda: _nombres_ramas(api, nombre), elegir, inicio=_("Cargando las ramas…"))


def json_legible(datos: Any, nivel: int = 0) -> str:
	"""Convierte datos JSON en líneas «clave: valor» sangradas con tabuladores (sin llaves ni comillas).

	Las llaves y comillas del JSON son ruido para el lector de pantalla; cada
	nivel se oye como una tabulación.
	"""
	sangria = "\t" * nivel

	def escalar(valor: Any) -> str:
		if isinstance(valor, bool):
			return f.si_no(valor)
		if valor is None or valor == "":
			return _("(vacío)")
		return str(valor)

	lineas: list[str] = []
	if isinstance(datos, dict):
		for clave, valor in datos.items():
			anidado = (isinstance(valor, dict) and valor) or (
				isinstance(valor, list) and any(isinstance(v, dict | list) for v in valor))
			if anidado:
				lineas.append(f"{sangria}{clave}:")
				lineas.append(json_legible(valor, nivel + 1))
			elif isinstance(valor, dict):
				lineas.append(f"{sangria}{clave}: {_('(vacío)')}")
			elif isinstance(valor, list):
				lineas.append(f"{sangria}{clave}: {', '.join(escalar(v) for v in valor) if valor else _('(ninguno)')}")
			else:
				lineas.append(f"{sangria}{clave}: {escalar(valor)}")
	elif isinstance(datos, list):
		for posicion, valor in enumerate(datos, 1):
			if isinstance(valor, dict | list):
				lineas.append(f"{sangria}{_('Elemento {n}').format(n=posicion)}:")
				lineas.append(json_legible(valor, nivel + 1))
			else:
				lineas.append(f"{sangria}- {escalar(valor)}")
	else:
		lineas.append(f"{sangria}{escalar(datos)}")
	return "\n".join(l for l in lineas if l)


def _guardar_como(panel: Any, titulo: str, nombre_archivo: str, comodin: str = "*.*") -> Path | None:
	dialogo = wx.FileDialog(panel, titulo, defaultFile=nombre_archivo, wildcard=_("Todos los archivos ({c})|{c}").format(c=comodin),
		style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
	try:
		if dialogo.ShowModal() != wx.ID_OK or not dialogo.GetPath():
			return None
		return Path(dialogo.GetPath())
	finally:
		dialogo.Destroy()


ESTADOS_LISTA = [("open", "abiertas"), ("closed", "cerradas"), ("all", "todas")]


def _texto_estado(clave: str) -> str:
	return _(dict(ESTADOS_LISTA).get(clave, clave))


def _elegir_estado(panel: Any, titulo: str, opciones: list[tuple[str, str]] | None = None) -> bool:
	opciones = opciones or ESTADOS_LISTA
	claves = [c for c, _n in opciones]
	actual = panel.datos.get("estado", claves[0])
	eleccion = elegir_uno(panel, titulo, _("&Mostrar:"), [_(n).capitalize() for _c, n in opciones],
		claves.index(actual) if actual in claves else 0)
	if eleccion is None:
		return False
	panel.datos["estado"] = claves[eleccion]
	return True


# ════════════════════════════════════════════════════════════════════════════
# Código (explorador de archivos)
# ════════════════════════════════════════════════════════════════════════════

TIPOS_CONTENIDO = {"dir": "Carpeta", "file": "Archivo", "symlink": "Enlace simbólico", "submodule": "Submódulo",
	"subir": "Carpeta superior"}


def _carpeta_padre(ruta: str) -> str:
	return ruta.strip("/").rpartition("/")[0]


def vista_codigo(nombre: str, host: str = "github.com") -> VistaRepo:
	def ref(panel: Any) -> str:
		return panel.datos.get("ref", "")

	def cargar(api: Any, pagina: int, panel: Any) -> list:
		ruta = panel.datos.get("ruta", "")
		datos = api.contenido(nombre, ruta, ref(panel))
		if isinstance(datos, dict):
			datos = [datos]
		elementos = sorted((e for e in datos or [] if isinstance(e, dict)),
			key=lambda e: (e.get("type") != "dir", str(e.get("name", "")).casefold()))
		if ruta:
			elementos.insert(0, {"type": "subir", "name": "..", "path": _carpeta_padre(ruta)})
		return elementos

	def etiqueta(panel: Any) -> str:
		rama = ref(panel) or _rama_defecto(panel) or _("rama por defecto")
		return _("Código, rama {r}, carpeta /{c}").format(r=rama, c=panel.datos.get("ruta", ""))

	def entrar(panel: Any, ruta: str) -> None:
		panel.datos["ruta"] = ruta.strip("/")
		panel.filtro = ""
		_recargar_filtrado(panel)

	def activar(panel: Any, elemento: dict) -> None:
		tipo = elemento.get("type")
		if tipo in ("dir", "subir"):
			entrar(panel, elemento.get("path", ""))
		elif tipo == "submodule":
			destino = elemento.get("html_url") or elemento.get("git_url") or ""
			if destino:
				webbrowser.open(destino)
		else:
			from app.ui.detalle.archivos import abrir_archivo

			abrir_archivo(panel.ctx, panel, nombre, elemento.get("path", ""), ref(panel))

	def subir_carpeta(panel: Any, _e: Any) -> None:
		ruta = panel.datos.get("ruta", "")
		if not ruta:
			panel.ctx.avisar(_("Ya está en la carpeta raíz."))
			return
		entrar(panel, _carpeta_padre(ruta))

	def cambiar_rama(panel: Any, _e: Any) -> None:
		def elegida(rama: str) -> None:
			panel.datos["ref"] = rama
			_recargar_filtrado(panel)

		_elegir_rama(panel, _("Cambiar de rama"), _("&Rama:"), elegida, actual=ref(panel))

	def nuevo_archivo(panel: Any, _e: Any) -> None:
		from app.ui.editor import CampoExtra, editar

		api = panel.ctx.api()
		carpeta = panel.datos.get("ruta", "")

		def enviar(valores: dict) -> Any:
			ruta = str(valores.get("ruta", "")).strip().strip("/")
			if not ruta:
				raise ValueError(_("Escriba la ruta del archivo nuevo."))
			mensaje = str(valores.get("mensaje", "")).strip() or _("Crear {r}").format(r=ruta)
			return api.guardar_archivo(nombre, ruta, valores["cuerpo"].encode("utf-8"), mensaje, rama=ref(panel))

		editar(panel, panel.ctx, _("Nuevo archivo en {n}").format(n=nombre), enviar,
			etiqueta_cuerpo=_("Con&tenido del archivo:"), etiqueta_enviar=_("&Guardar (commit)"),
			extras=[
				CampoExtra("ruta", _("&Ruta del archivo nuevo:"), "texto", valor=f"{carpeta}/" if carpeta else "",
					ayuda=_("Ruta dentro del repositorio, con carpetas separadas por barras.")),
				CampoExtra("mensaje", _("&Mensaje del commit:"), "texto", valor="", ayuda=_("Vacío: «Crear» y la ruta.")),
			],
			al_enviar=lambda _r: panel.cargar(anunciar=False))

	def subir_archivo(panel: Any, _e: Any) -> None:
		dialogo = wx.FileDialog(panel, _("Elija el archivo que quiere subir"), style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
		try:
			if dialogo.ShowModal() != wx.ID_OK or not dialogo.GetPath():
				return
			origen = Path(dialogo.GetPath())
		finally:
			dialogo.Destroy()
		carpeta = panel.datos.get("ruta", "")
		destino = f"{carpeta}/{origen.name}" if carpeta else origen.name
		existente = next((e for e in panel.elementos if e.get("path") == destino and e.get("type") == "file"), None)
		if existente and confirmar(panel, _("Ya existe {r}. ¿Sustituirlo?").format(r=destino), _("Subir un archivo"),
			peligroso=True) != wx.ID_YES:
			return
		mensaje = pedir_texto(panel, _("&Mensaje del commit:"), _("Subir un archivo"),
			(_("Actualizar {n}") if existente else _("Añadir {n}")).format(n=origen.name))
		if mensaje is None:
			return
		api = panel.ctx.api()
		sha = (existente or {}).get("sha", "")
		_hacer(panel, lambda: api.guardar_archivo(nombre, destino, origen.read_bytes(), mensaje.strip() or origen.name, sha=sha,
			rama=ref(panel)), _("{r} subido.").format(r=destino), inicio=_("Subiendo {n}…").format(n=origen.name))

	def borrar_archivo(panel: Any, elemento: dict) -> None:
		ruta = elemento.get("path", "")
		if not confirmar_peligro(panel, _("¿Borrar {r} con un commit? Seguirá en el historial.").format(r=ruta),
			_("Borrar el archivo")):
			return
		mensaje = pedir_texto(panel, _("&Mensaje del commit:"), _("Borrar el archivo"), _("Borrar {r}").format(r=ruta))
		if mensaje is None:
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_archivo(nombre, ruta, elemento.get("sha", ""),
			mensaje.strip() or _("Borrar {r}").format(r=ruta), rama=ref(panel)), exito=_("{r} borrado.").format(r=ruta),
			al_terminar=lambda _r: panel.quitar(elemento))

	def descargar_archivo(panel: Any, elemento: dict) -> None:
		destino = _guardar_como(panel, _("Guardar el archivo"), elemento.get("name", "archivo"))
		if destino is None:
			return
		api = panel.ctx.api()

		def trabajo() -> Path:
			contenido, _sha = api.leer_archivo(nombre, elemento.get("path", ""), ref(panel))
			destino.write_bytes(contenido)
			return destino

		en_segundo_plano(panel, panel.ctx, trabajo, inicio=_("Descargando…"),
			exito=lambda r: _("Guardado en {r}.").format(r=r), sonido="descarga")

	def descargar_zip(panel: Any, _e: Any) -> None:
		from app.ui.descarga_codigo import descargar_codigo

		# Con progreso hablado en hitos; el cliente sigue la redirección a codeload y escribe en trozos.
		descargar_codigo(panel, panel.ctx, nombre, ref(panel) or _rama_defecto(panel))

	def buscar_archivo(panel: Any, _e: Any) -> None:
		texto = pedir_texto(panel, _("&Parte del nombre o de la ruta:"), _("Buscar un archivo"))
		if not texto or not texto.strip():
			return
		buscado = texto.strip().casefold()
		api = panel.ctx.api()
		arbol_ref = ref(panel) or _rama_defecto(panel) or "HEAD"

		def elegir(arbol: Any) -> None:
			entradas = [e for e in (arbol or {}).get("tree", []) if buscado in str(e.get("path", "")).casefold()]
			if not entradas:
				panel.ctx.sonar("vacio")
				mostrar_mensaje(panel, _("Ningún archivo ni carpeta contiene «{t}».").format(t=texto.strip()), _("Buscar un archivo"))
				return
			entradas = entradas[:1000]
			aviso = _(" (el árbol es muy grande: GitHub solo devolvió una parte)") if (arbol or {}).get("truncated") else ""
			eleccion = elegir_uno(panel, _("Buscar un archivo"),
				_("{n} &resultados{a}:").format(n=len(entradas), a=aviso),
				[e["path"] + (" " + _("(carpeta)") if e.get("type") == "tree" else "") for e in entradas])
			if eleccion is None:
				return
			elegido = entradas[eleccion]
			if elegido.get("type") == "tree":
				entrar(panel, elegido["path"])
			else:
				from app.ui.detalle.archivos import abrir_archivo

				abrir_archivo(panel.ctx, panel, nombre, elegido["path"], ref(panel))

		_en_fondo(panel, lambda: api.arbol(nombre, arbol_ref, True), elegir, inicio=_("Buscando en todo el repositorio…"))

	def es_archivo(_p: Any, e: dict) -> bool:
		return e.get("type") == "file"

	def es_real(_p: Any, e: dict) -> bool:
		return e.get("type") != "subir"

	return VistaRepo(
		"repo_codigo", _("Código"),
		[
			Columna("nombre", _("Nombre"), lambda e, c: _("(carpeta superior)") if e.get("type") == "subir" else e.get("name", ""), 280),
			Columna("tipo", _("Tipo"), lambda e, c: _(TIPOS_CONTENIDO.get(e.get("type", ""), e.get("type", ""))), 110),
			Columna("tamano", _("Tamaño"), lambda e, c: f.tamano(e.get("size")) if e.get("type") == "file" else "", 90),
			Columna("ruta", _("Ruta"), lambda e, c: e.get("path", ""), 300, visible=False),
		],
		cargar, activar,
		[
			Accion(_("A&brir"), activar, "Intro"),
			Accion(_("Ir a la carpeta su&perior"), subir_carpeta, "Retroceso", requiere_elemento=False),
			Accion(_("Cambiar de &rama…"), cambiar_rama, "F4", requiere_elemento=False),
			Accion(_("Bu&scar un archivo por nombre…"), buscar_archivo, "Ctrl+P", requiere_elemento=False),
			Accion(_("Nuevo arc&hivo…"), nuevo_archivo, "Ctrl+N", requiere_elemento=False, separador_antes=True),
			Accion(_("S&ubir un archivo del disco…"), subir_archivo, "Ctrl+U", requiere_elemento=False),
			Accion(_("Borrar e&l archivo…"), borrar_archivo, "Supr", disponible=es_archivo),
			Accion(_("Des&cargar el archivo…"), descargar_archivo, "Ctrl+S", disponible=es_archivo, separador_antes=True),
			Accion(_("Descargar el repositorio en &zip…"), descargar_zip, requiere_elemento=False),
			Accion(_("Copiar la ru&ta"), lambda p, e: copiar(p.ctx, e.get("path", ""), _("Ruta copiada.")), disponible=es_real),
			Accion(_("Ver el histor&ial de cambios"), lambda p, e: _ir(p, "commits", ruta=e.get("path", ""), rama=ref(p)),
				disponible=es_real),
		],
		_("Esta carpeta está vacía."), url_html, paginada=False, sonido_carga=False, etiqueta_de=etiqueta,
	)


# ════════════════════════════════════════════════════════════════════════════
# Issues y pull requests
# ════════════════════════════════════════════════════════════════════════════


def _etiqueta_conversaciones(panel: Any, titulo: str) -> str:
	datos = panel.datos
	partes = [_texto_estado(datos.get("estado", "open"))]
	if datos.get("etiqueta"):
		partes.append(_("etiqueta «{e}»").format(e=datos["etiqueta"]))
	asignado = datos.get("asignado", "")
	if asignado == "none":
		partes.append(_("sin asignar"))
	elif asignado == "*":
		partes.append(_("con alguien asignado"))
	elif asignado:
		partes.append(_("asignadas a {a}").format(a=asignado))
	if datos.get("hito"):
		partes.append(_("hito {h}").format(h=datos.get("hito_titulo") or datos["hito"]))
	return f"{titulo} ({', '.join(partes)})"


def _cambiar_filtro_conversaciones(panel: Any, es_pr: bool) -> None:
	datos = panel.datos
	api = panel.ctx.api()
	nombre = _nombre(panel)
	opciones = [
		("estado", _("Estado: {v}").format(v=_texto_estado(datos.get("estado", "open")))),
		("etiqueta", _("Etiqueta: {v}").format(v=datos.get("etiqueta") or _("cualquiera"))),
		("asignado", _("Asignación: {v}").format(v=datos.get("asignado") or _("cualquiera"))),
	]
	if not es_pr:
		opciones.append(("hito", _("Hito: {v}").format(v=datos.get("hito_titulo") or _("cualquiera"))))
	opciones.append(("quitar", _("Quitar todos los filtros")))
	eleccion = elegir_uno(panel, _("Filtro de GitHub"), _("&Filtro que quiere cambiar:"), [t for _c, t in opciones])
	if eleccion is None:
		return
	clave = opciones[eleccion][0]
	if clave == "estado":
		if _elegir_estado(panel, _("Estado")):
			_recargar_filtrado(panel)
	elif clave == "quitar":
		for k in ("etiqueta", "asignado", "hito", "hito_titulo"):
			datos.pop(k, None)
		datos["estado"] = "open"
		_recargar_filtrado(panel)
	elif clave == "etiqueta":
		def elegir_etiqueta(etiquetas: list) -> None:
			nombres = [e.get("name", "") for e in etiquetas or []]
			eleccion_e = elegir_uno(panel, _("Filtrar por etiqueta"), _("&Etiqueta:"), [_("(cualquiera)")] + nombres,
				1 + nombres.index(datos["etiqueta"]) if datos.get("etiqueta") in nombres else 0)
			if eleccion_e is not None:
				datos["etiqueta"] = nombres[eleccion_e - 1] if eleccion_e else ""
				_recargar_filtrado(panel)

		_en_fondo(panel, lambda: api.etiquetas(nombre), elegir_etiqueta, inicio=_("Cargando las etiquetas…"))
	elif clave == "asignado":
		def elegir_asignado(personas: list) -> None:
			logins = [p.get("login", "") for p in personas or []]
			valores = ["", "none", "*"] + logins
			eleccion_a = elegir_uno(panel, _("Filtrar por asignación"), _("&Asignación:"),
				[_("(cualquiera)"), _("Sin asignar"), _("Con alguien asignado")] + logins,
				valores.index(datos.get("asignado", "")) if datos.get("asignado", "") in valores else 0)
			if eleccion_a is not None:
				datos["asignado"] = valores[eleccion_a]
				_recargar_filtrado(panel)

		_en_fondo(panel, lambda: api.asignables(nombre), elegir_asignado, inicio=_("Cargando las personas asignables…"))
	elif clave == "hito":
		def elegir_hito(hitos: list) -> None:
			eleccion_h = elegir_uno(panel, _("Filtrar por hito"), _("&Hito:"),
				[_("(cualquiera)"), _("Sin hito")] + [h.get("title", "") for h in hitos or []])
			if eleccion_h is None:
				return
			if eleccion_h == 0:
				datos.pop("hito", None)
				datos.pop("hito_titulo", None)
			elif eleccion_h == 1:
				datos["hito"], datos["hito_titulo"] = "none", _("ninguno")
			else:
				hito = hitos[eleccion_h - 2]
				datos["hito"], datos["hito_titulo"] = str(hito.get("number", "")), hito.get("title", "")
			_recargar_filtrado(panel)

		_en_fondo(panel, lambda: api.hitos(nombre, "all"), elegir_hito, inicio=_("Cargando los hitos…"))


def _numero(elemento: dict) -> int:
	return int(elemento.get("number") or 0)


def _comentar(panel: Any, elemento: dict) -> None:
	from app.ui.editor import editar

	api = panel.ctx.api()
	nombre = _nombre(panel)
	numero = _numero(elemento)

	def comentado(_r: Any) -> None:
		panel.sustituir(elemento, dict(elemento, comments=int(elemento.get("comments") or 0) + 1))

	editar(panel, panel.ctx, _("Comentar en #{n}: {t}").format(n=numero, t=elemento.get("title", "")),
		lambda v: api.comentar(nombre, numero, v["cuerpo"]), texto_contexto=elemento.get("body") or "", al_enviar=comentado,
		con_adjuntos=True)


def _cambiar_etiquetas(panel: Any, elemento: dict) -> None:
	api = panel.ctx.api()
	nombre = _nombre(panel)
	numero = _numero(elemento)
	actuales = {e.get("name") for e in elemento.get("labels") or [] if isinstance(e, dict)}

	def elegir(etiquetas: list) -> None:
		nombres = [e.get("name", "") for e in etiquetas or []]
		if not nombres:
			mostrar_mensaje(panel, _("El repositorio no tiene etiquetas. Créelas en la sección «Etiquetas de issues»."), _("Etiquetas"))
			return
		marcadas = elegir_varios(panel, _("Etiquetas de #{n}").format(n=numero), _("&Etiquetas:"),
			[f"{e.get('name', '')}" + (f" ({e['description']})" if e.get("description") else "") for e in etiquetas],
			[i for i, n in enumerate(nombres) if n in actuales], config=panel.ctx.config)
		if marcadas is None:
			return
		elegidas = [nombres[i] for i in marcadas]
		en_segundo_plano(panel, panel.ctx, lambda: api.poner_etiquetas(nombre, numero, elegidas),
			exito=_("Etiquetas cambiadas."), sonido="completado",
			al_terminar=lambda r: panel.sustituir(elemento, dict(elemento, labels=r if isinstance(r, list) else
				[{"name": n} for n in elegidas])))

	_en_fondo(panel, lambda: api.etiquetas(nombre), elegir, inicio=_("Cargando las etiquetas…"))


def _cambiar_asignados(panel: Any, elemento: dict) -> None:
	api = panel.ctx.api()
	nombre = _nombre(panel)
	numero = _numero(elemento)
	actuales = {u.get("login") for u in elemento.get("assignees") or [] if isinstance(u, dict)}

	def elegir(personas: list) -> None:
		logins = [p.get("login", "") for p in personas or []]
		marcadas = elegir_varios(panel, _("Asignados de #{n}").format(n=numero), _("&Personas asignadas:"), logins,
			[i for i, l in enumerate(logins) if l in actuales], config=panel.ctx.config)
		if marcadas is None:
			return
		elegidos = [logins[i] for i in marcadas]

		def hecho(resultado: Any) -> None:
			nuevo = resultado if isinstance(resultado, dict) and resultado.get("number") else dict(
				elemento, assignees=[{"login": l} for l in elegidos])
			panel.sustituir(elemento, nuevo)

		en_segundo_plano(panel, panel.ctx, lambda: api.editar_issue(nombre, numero, assignees=elegidos),
			exito=_("Asignados cambiados."), al_terminar=hecho)

	_en_fondo(panel, lambda: api.asignables(nombre), elegir, inicio=_("Cargando las personas asignables…"))


MOTIVOS_CIERRE = [("completed", "Completada"), ("not_planned", "No planificada"), ("duplicate", "Duplicada")]


def vista_issues(nombre: str, host: str = "github.com") -> VistaRepo:
	def cargar(api: Any, pagina: int, panel: Any) -> Any:
		datos = panel.datos
		resultado = api.issues(nombre, pagina, estado=datos.get("estado", "open"), etiquetas=datos.get("etiqueta", ""),
			asignado=datos.get("asignado", ""), hito=datos.get("hito", ""))
		# El listado de issues incluye los pull requests: aquí solo van las issues.
		if isinstance(resultado, Pagina):
			resultado.elementos = [i for i in resultado.elementos if not i.get("pull_request")]
			return resultado
		return [i for i in resultado or [] if not i.get("pull_request")]

	def activar(panel: Any, issue: dict) -> None:
		abrir.issue(panel.ctx, panel, nombre, _numero(issue))

	def nueva(panel: Any, _e: Any) -> None:
		# Plantillas Markdown, formularios YAML y config.yml: app/ui/detalle/formulario_issue.py.
		from app.ui.detalle.formulario_issue import nueva_issue

		def creada(issue: dict) -> None:
			panel.cargar(anunciar=False)
			panel.ctx.avisar(_("Issue #{n} creada.").format(n=issue.get("number", "")), interrumpir=False)

		nueva_issue(panel, panel.ctx, nombre, al_crear=creada)

	def cerrar(panel: Any, issue: dict) -> None:
		eleccion = elegir_uno(panel, _("Cerrar la issue #{n}").format(n=_numero(issue)), _("&Motivo del cierre:"),
			[_(t) for _c, t in MOTIVOS_CIERRE])
		if eleccion is None:
			return
		api = panel.ctx.api()
		_hacer(panel, lambda: api.cerrar_issue(nombre, _numero(issue), MOTIVOS_CIERRE[eleccion][0]),
			_("Issue #{n} cerrada.").format(n=_numero(issue)))

	def reabrir(panel: Any, issue: dict) -> None:
		api = panel.ctx.api()
		_hacer(panel, lambda: api.reabrir_issue(nombre, _numero(issue)), _("Issue #{n} reabierta.").format(n=_numero(issue)))

	def cambiar_hito(panel: Any, issue: dict) -> None:
		api = panel.ctx.api()

		def elegir(hitos: list) -> None:
			eleccion = elegir_uno(panel, _("Hito de #{n}").format(n=_numero(issue)), _("&Hito:"),
				[_("(sin hito)")] + [h.get("title", "") for h in hitos or []])
			if eleccion is None:
				return
			numero_hito = hitos[eleccion - 1].get("number") if eleccion else None
			en_segundo_plano(panel, panel.ctx, lambda: api.editar_issue(nombre, _numero(issue), milestone=numero_hito),
				exito=_("Hito cambiado."), al_terminar=lambda r: panel.sustituir(issue, r) if isinstance(r, dict) and r.get("number") else None)

		_en_fondo(panel, lambda: api.hitos(nombre, "open"), elegir, inicio=_("Cargando los hitos…"))

	return VistaRepo(
		"repo_issues", _("Issues"), columnas_issue(con_repo=False), cargar, activar,
		[
			Accion(_("A&brir"), activar, "Intro"),
			Accion(_("Nueva &issue…"), nueva, "Ctrl+N", requiere_elemento=False),
			Accion(_("Comen&tar…"), _comentar, "Ctrl+R", separador_antes=True),
			Accion(_("Cambiar las etiquetas (&labels)…"), _cambiar_etiquetas, "Ctrl+L"),
			Accion(_("Cambiar los a&signados…"), _cambiar_asignados, "Ctrl+Shift+A"),
			Accion(_("Cambiar el &hito…"), cambiar_hito),
			Accion(_("&Cerrar la issue…"), cerrar, "Ctrl+Shift+X", disponible=lambda p, i: i.get("state") == "open"),
			Accion(_("&Reabrir la issue"), reabrir, "Ctrl+Shift+X", disponible=lambda p, i: i.get("state") == "closed"),
			Accion(_("Filtro de &GitHub (estado, etiqueta, asignación, hito)…"), lambda p, e: _cambiar_filtro_conversaciones(p, False),
				"F4", requiere_elemento=False, separador_antes=True),
		],
		_("No hay issues con este filtro. Cree una con Control+N o cambie el filtro con F4."), url_html, detalle_issue,
		etiqueta_de=lambda p: _etiqueta_conversaciones(p, _("Issues")),
	)


def _elegir_plantilla_pr(panel: Any, plantillas: list[tuple[str, str]]) -> str | None:
	"""Texto inicial de la descripción de un pull request según las plantillas del repositorio.

	Sin plantillas, vacío; con una, esa; con varias, se elige (o ninguna).
	Devuelve ``None`` si se cancela la elección.
	"""
	if not plantillas:
		return ""
	if len(plantillas) == 1:
		return plantillas[0][1]
	eleccion = elegir_uno(panel, _("Plantilla del pull request"), _("&Plantilla para la descripción:"),
		[ruta for ruta, _texto in plantillas] + [_("Sin plantilla (descripción vacía)")],
		ayuda=_("El repositorio tiene varias plantillas de pull request; su texto será el principio de la descripción."))
	if eleccion is None:
		return None
	return plantillas[eleccion][1] if eleccion < len(plantillas) else ""


def vista_prs(nombre: str, host: str = "github.com") -> VistaRepo:
	def cargar(api: Any, pagina: int, panel: Any) -> Any:
		datos = panel.datos
		estado = datos.get("estado", "open")
		if not datos.get("etiqueta") and not datos.get("asignado"):
			return api.prs(nombre, pagina, estado)
		# Los filtros por etiqueta o asignación solo existen en la búsqueda.
		consulta = f"repo:{nombre} is:pr"
		if estado != "all":
			consulta += f" is:{estado}"
		if datos.get("etiqueta"):
			consulta += f' label:"{datos["etiqueta"]}"'
		asignado = datos.get("asignado", "")
		if asignado == "none":
			consulta += " no:assignee"
		elif asignado == "*":
			consulta += " -no:assignee"
		elif asignado:
			consulta += f" assignee:{asignado}"
		return api.buscar("issues", consulta, pagina, "updated", por_pagina=int(panel.ctx.config.obtener("listas.por_pagina", 50)))

	def activar(panel: Any, pr: dict) -> None:
		abrir.pull_request(panel.ctx, panel, nombre, _numero(pr))

	def nuevo(panel: Any, _e: Any) -> None:
		from app.ui.editor import CampoExtra, editar

		api = panel.ctx.api()

		def cargar() -> tuple[list[str], list[tuple[str, str]]]:
			ramas = _nombres_ramas(api, nombre)
			try:
				plantillas = api.plantillas_pr(nombre) if len(ramas) >= 2 else []
			except Exception:  # noqa: BLE001 - sin plantilla se escribe la descripción desde cero
				log.warning("No se pudieron leer las plantillas de pull request de %s", nombre, exc_info=True)
				plantillas = []
			return ramas, plantillas

		def abrir_editor(datos: tuple[list[str], list[tuple[str, str]]]) -> None:
			ramas, plantillas = datos
			if len(ramas) < 2:
				mostrar_mensaje(panel, _("Hace falta al menos otra rama además de la principal para abrir un pull request."),
					_("Nuevo pull request"))
				return
			cuerpo = _elegir_plantilla_pr(panel, plantillas)
			if cuerpo is None:
				return
			base = _rama_defecto(panel) if _rama_defecto(panel) in ramas else ramas[0]
			cabeza = next((r for r in ramas if r != base), ramas[0])

			def enviar(v: dict) -> Any:
				if v["cabeza"] == v["base"]:
					raise ValueError(_("La rama de origen y la de destino deben ser distintas."))
				return api.crear_pr(nombre, v["titulo"], v["cabeza"], v["base"], v["cuerpo"], bool(v.get("borrador")))

			def creado(pr: Any) -> None:
				panel.cargar(anunciar=False)
				if isinstance(pr, dict):
					panel.ctx.avisar(_("Pull request #{n} creado.").format(n=pr.get("number", "")), interrumpir=False)

			editar(panel, panel.ctx, _("Nuevo pull request en {n}").format(n=nombre), enviar, con_titulo=True, cuerpo=cuerpo,
				extras=[
					CampoExtra("cabeza", _("Rama de &origen (con los cambios):"), "opcion", cabeza, [(r, r) for r in ramas],
						_("Rama cuyos commits quiere fusionar.")),
					CampoExtra("base", _("Rama de &destino (base):"), "opcion", base, [(r, r) for r in ramas],
						_("Rama en la que se fusionarán los cambios.")),
					CampoExtra("borrador", _("Crear como &borrador"), "bool", False,
						ayuda=_("Un borrador no se puede fusionar hasta marcarlo como listo.")),
				],
				al_enviar=creado, con_adjuntos=True)

		_en_fondo(panel, cargar, abrir_editor, inicio=_("Cargando las ramas…"))

	def cambiar_estado(panel: Any, pr: dict, estado: str) -> None:
		api = panel.ctx.api()
		texto = _("Pull request #{n} cerrado.") if estado == "closed" else _("Pull request #{n} reabierto.")
		_hacer(panel, lambda: api.editar_pr(nombre, _numero(pr), state=estado), texto.format(n=_numero(pr)))

	def ver_diff(panel: Any, pr: dict) -> None:
		from app.ui.detalle.diferencias import abrir_diff

		api = panel.ctx.api()
		abrir_diff(panel.ctx, panel, _("Diferencias del pull request #{n} de {r}").format(n=_numero(pr), r=nombre),
			lambda: api.diff_pr(nombre, _numero(pr)))

	def fusionado(pr: dict) -> bool:
		return bool(pr.get("merged_at") or (pr.get("pull_request") or {}).get("merged_at"))

	return VistaRepo(
		"repo_prs", _("Pull requests"),
		[
			Columna("numero", _("Número"), lambda p, c: f"#{p.get('number', '')}", 70),
			Columna("titulo", _("Título"), lambda p, c: p.get("title", ""), 360),
			Columna("estado", _("Estado"), lambda p, c: f.estado_issue(p), 90),
			Columna("rama", _("Rama"), lambda p, c: (p.get("head") or {}).get("ref", ""), 150),
			Columna("base", _("Destino"), lambda p, c: (p.get("base") or {}).get("ref", ""), 110, visible=False),
			Columna("autor", _("Autor"), lambda p, c: f.login(p.get("user")), 120),
			Columna("etiquetas", _("Etiquetas"), lambda p, c: f.etiquetas(p), 150),
			Columna("asignados", _("Asignados"), lambda p, c: f.asignados(p), 140, visible=False),
			Columna("actualizado", _("Actualizado"), lambda p, c: f.fecha(p.get("updated_at"), c.relativas()), 120),
		],
		cargar, activar,
		[
			Accion(_("A&brir"), activar, "Intro"),
			Accion(_("Nuevo &pull request…"), nuevo, "Ctrl+N", requiere_elemento=False),
			Accion(_("&Ver las diferencias"), ver_diff, "Ctrl+D"),
			Accion(_("Comen&tar…"), _comentar, "Ctrl+R", separador_antes=True),
			Accion(_("Cambiar las etiquetas (&labels)…"), _cambiar_etiquetas, "Ctrl+L"),
			Accion(_("Cambiar los a&signados…"), _cambiar_asignados, "Ctrl+Shift+A"),
			Accion(_("&Cerrar el pull request"), lambda p, pr: cambiar_estado(p, pr, "closed"), "Ctrl+Shift+X",
				disponible=lambda p, pr: pr.get("state") == "open"),
			Accion(_("&Reabrir el pull request"), lambda p, pr: cambiar_estado(p, pr, "open"), "Ctrl+Shift+X",
				disponible=lambda p, pr: pr.get("state") == "closed" and not fusionado(pr)),
			Accion(_("Filtro de &GitHub (estado, etiqueta, asignación)…"), lambda p, e: _cambiar_filtro_conversaciones(p, True),
				"F4", requiere_elemento=False, separador_antes=True),
		],
		_("No hay pull requests con este filtro. Cree uno con Control+N o cambie el filtro con F4."), url_html, detalle_issue,
		etiqueta_de=lambda p: _etiqueta_conversaciones(p, _("Pull requests")),
	)


# ════════════════════════════════════════════════════════════════════════════
# Discusiones
# ════════════════════════════════════════════════════════════════════════════


def _estado_discusion(dis: dict) -> str:
	if dis.get("closed"):
		return _("Cerrada")
	if dis.get("isAnswered"):
		return _("Respondida")
	return _("Abierta")


def vista_discusiones(nombre: str, host: str = "github.com") -> VistaRepo:
	def cargar(api: Any, pagina: int, panel: Any) -> Pagina:
		cursores = panel.datos.setdefault("cursores", {})
		cursor = None if pagina <= 1 else cursores.get(pagina)
		nodos, siguiente = api.discusiones(nombre, 50, cursor)
		if siguiente:
			cursores[pagina + 1] = siguiente
		return Pagina(list(nodos or []), siguiente=siguiente or "")

	def activar(panel: Any, dis: dict) -> None:
		abrir.discusion(panel.ctx, panel, nombre, _numero(dis))

	def nueva(panel: Any, _e: Any) -> None:
		from app.ui.editor import editar

		api = panel.ctx.api()

		def elegir(resultado: tuple[str, list]) -> None:
			id_repo, categorias = resultado
			if not categorias:
				mostrar_mensaje(panel, _("Las discusiones no están activadas en este repositorio."), _("Nueva discusión"))
				return
			eleccion = elegir_uno(panel, _("Nueva discusión"), _("&Categoría:"),
				[c.get("name", "") + (f": {c['description']}" if c.get("description") else "") for c in categorias])
			if eleccion is None:
				return
			categoria = categorias[eleccion]
			editar(panel, panel.ctx, _("Nueva discusión en {c}").format(c=categoria.get("name", "")),
				lambda v: api.crear_discusion(id_repo, categoria["id"], v["titulo"], v["cuerpo"]), con_titulo=True,
				al_enviar=lambda _r: panel.cargar(anunciar=False), con_adjuntos=True)

		_en_fondo(panel, lambda: api.categorias_discusion(nombre), elegir, inicio=_("Cargando las categorías…"))

	def comentar(panel: Any, dis: dict) -> None:
		from app.ui.editor import editar

		api = panel.ctx.api()
		editar(panel, panel.ctx, _("Comentar en la discusión #{n}").format(n=_numero(dis)),
			lambda v: api.comentar_discusion(dis["id"], v["cuerpo"]), al_enviar=lambda _r: panel.cargar(anunciar=False),
			con_adjuntos=True)

	def cerrar(panel: Any, dis: dict) -> None:
		api = panel.ctx.api()
		_hacer(panel, lambda: api.cerrar_discusion(dis["id"]), _("Discusión cerrada."))

	def reabrir(panel: Any, dis: dict) -> None:
		api = panel.ctx.api()
		_hacer(panel, lambda: api.reabrir_discusion(dis["id"]), _("Discusión reabierta."))

	return VistaRepo(
		"repo_discusiones", _("Discusiones"),
		[
			Columna("numero", _("Número"), lambda x, c: f"#{x.get('number', '')}", 70),
			Columna("titulo", _("Título"), lambda x, c: x.get("title", ""), 340),
			Columna("categoria", _("Categoría"), lambda x, c: (x.get("category") or {}).get("name", ""), 130),
			Columna("estado", _("Estado"), lambda x, c: _estado_discusion(x), 90),
			Columna("autor", _("Autor"), lambda x, c: f.login(x.get("author")), 120),
			Columna("respuestas", _("Respuestas"), lambda x, c: str((x.get("comments") or {}).get("totalCount", 0)), 80),
			Columna("votos", _("Votos"), lambda x, c: str(x.get("upvoteCount", 0)), 60, visible=False),
			Columna("actualizada", _("Actualizada"), lambda x, c: f.fecha(x.get("updatedAt"), c.relativas()), 120),
		],
		cargar, activar,
		[
			Accion(_("A&brir"), activar, "Intro"),
			Accion(_("Nue&va discusión…"), nueva, "Ctrl+N", requiere_elemento=False),
			Accion(_("Comen&tar…"), comentar, "Ctrl+R"),
			Accion(_("&Cerrar la discusión"), cerrar, disponible=lambda p, x: not x.get("closed")),
			Accion(_("&Reabrir la discusión"), reabrir, disponible=lambda p, x: bool(x.get("closed"))),
		],
		_("No hay discusiones (o no están activadas en este repositorio)."), url=lambda x: x.get("url", ""),
	)


# ════════════════════════════════════════════════════════════════════════════
# Actions
# ════════════════════════════════════════════════════════════════════════════

EN_CURSO = ("queued", "in_progress", "waiting", "requested", "pending")


def lanzar_flujo_repo(panel: Any) -> None:
	"""Usa el diálogo completo de ``app.ui.detalle.acciones`` si existe; si no, una versión sencilla."""
	try:
		from app.ui.detalle.acciones import lanzar_flujo
	except ImportError:
		log.debug("No hay lanzar_flujo en app.ui.detalle.acciones; se usa la versión sencilla.", exc_info=True)
		_lanzar_flujo_sencillo(panel)
		return
	lanzar_flujo(panel.ctx, panel, _nombre(panel))


def _lanzar_flujo_sencillo(panel: Any) -> None:
	api = panel.ctx.api()
	nombre = _nombre(panel)

	def cargar() -> tuple[list, list[str]]:
		lanzables = []
		for flujo in api.flujos(nombre) or []:
			if flujo.get("state") != "active":
				continue
			try:
				contenido, _sha = api.leer_archivo(nombre, flujo.get("path", ""))
			except Exception:  # noqa: BLE001 - un flujo ilegible (por ejemplo, dinámico) no se ofrece
				log.debug("No se pudo leer el flujo %s", flujo.get("path"), exc_info=True)
				continue
			if b"workflow_dispatch" in contenido:
				lanzables.append(flujo)
		return lanzables, _nombres_ramas(api, nombre)

	def elegir(resultado: tuple[list, list[str]]) -> None:
		lanzables, ramas = resultado
		if not lanzables:
			mostrar_mensaje(panel, _("Ningún flujo de este repositorio se puede lanzar a mano: necesitan el disparador "
				"«workflow_dispatch»."), _("Lanzar un flujo"))
			return
		eleccion = elegir_uno(panel, _("Lanzar un flujo"), _("&Flujo de trabajo:"), [fl.get("name", "") for fl in lanzables])
		if eleccion is None or not ramas:
			return
		defecto = _rama_defecto(panel)
		rama = elegir_uno(panel, _("Lanzar un flujo"), _("&Rama en la que se ejecuta:"), ramas,
			ramas.index(defecto) if defecto in ramas else 0)
		if rama is None:
			return
		flujo = lanzables[eleccion]
		_hacer(panel, lambda: api.lanzar_flujo(nombre, flujo["id"], ramas[rama]),
			_("Flujo «{f}» lanzado en {r}. Aparecerá en la lista en unos segundos.").format(f=flujo.get("name", ""), r=ramas[rama]))

	_en_fondo(panel, cargar, elegir, inicio=_("Buscando los flujos que se pueden lanzar…"))


def vista_acciones(nombre: str, host: str = "github.com") -> VistaRepo:
	def cargar(api: Any, pagina: int, panel: Any) -> Any:
		return api.ejecuciones(nombre, pagina, id_flujo=panel.datos.get("flujo") or None, rama=panel.datos.get("rama", ""))

	def activar(panel: Any, ejecucion: dict) -> None:
		abrir.ejecucion(panel.ctx, panel, nombre, int(ejecucion.get("id") or 0))

	def etiqueta(panel: Any) -> str:
		partes = []
		if panel.datos.get("flujo_nombre"):
			partes.append(_("flujo «{f}»").format(f=panel.datos["flujo_nombre"]))
		if panel.datos.get("rama"):
			partes.append(_("rama {r}").format(r=panel.datos["rama"]))
		return _("Ejecuciones de Actions") + (f" ({', '.join(partes)})" if partes else "")

	def filtro(panel: Any, _e: Any) -> None:
		api = panel.ctx.api()
		opciones = [_("Flujo de trabajo: {v}").format(v=panel.datos.get("flujo_nombre") or _("todos")),
			_("Rama: {v}").format(v=panel.datos.get("rama") or _("todas")), _("Quitar los filtros")]
		eleccion = elegir_uno(panel, _("Filtro de GitHub"), _("&Filtro que quiere cambiar:"), opciones)
		if eleccion == 0:
			def elegir(flujos: list) -> None:
				indice = elegir_uno(panel, _("Flujo de trabajo"), _("&Flujo:"), [_("(todos)")] + [fl.get("name", "") for fl in flujos])
				if indice is None:
					return
				panel.datos["flujo"] = flujos[indice - 1].get("id") if indice else None
				panel.datos["flujo_nombre"] = flujos[indice - 1].get("name", "") if indice else ""
				_recargar_filtrado(panel)

			_en_fondo(panel, lambda: api.flujos(nombre), elegir, inicio=_("Cargando los flujos…"))
		elif eleccion == 1:
			def elegida(rama: str) -> None:
				panel.datos["rama"] = rama
				_recargar_filtrado(panel)

			_elegir_rama(panel, _("Rama"), _("&Rama:"), elegida, actual=panel.datos.get("rama", ""))
		elif eleccion == 2:
			for clave in ("flujo", "flujo_nombre", "rama"):
				panel.datos.pop(clave, None)
			_recargar_filtrado(panel)

	def volver(panel: Any, ejecucion: dict, solo_fallidos: bool = False) -> None:
		api = panel.ctx.api()
		_hacer(panel, lambda: api.volver_a_ejecutar(nombre, ejecucion["id"], solo_fallidos=solo_fallidos),
			_("Ejecución relanzada."))

	def cancelar(panel: Any, ejecucion: dict) -> None:
		api = panel.ctx.api()
		_hacer(panel, lambda: api.cancelar_ejecucion(nombre, ejecucion["id"]), _("Cancelación pedida."))

	def vigilar_ejecucion(panel: Any, ejecucion: dict) -> None:
		from app.services import vigilancia_actions as va

		principal = panel.ctx.ventana_principal
		if principal is None or not hasattr(principal, "vigilar"):
			return
		principal.vigilar(va.nueva_ejecucion(nombre, ejecucion))

	def borrar(panel: Any, ejecucion: dict) -> None:
		if not confirmar_peligro(panel, _("¿Borrar la ejecución «{t}» y sus registros?").format(
			t=ejecucion.get("display_title") or ejecucion.get("name", "")), _("Borrar la ejecución")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_ejecucion(nombre, ejecucion["id"]), exito=_("Ejecución borrada."),
			al_terminar=lambda _r: panel.quitar(ejecucion))

	return VistaRepo(
		"repo_acciones", _("Ejecuciones de Actions"),
		[
			Columna("flujo", _("Flujo"), lambda e, c: e.get("name", ""), 160),
			Columna("titulo", _("Título"), lambda e, c: e.get("display_title", ""), 300),
			Columna("estado", _("Estado"), lambda e, c: f.estado_ejecucion(e), 100),
			Columna("rama", _("Rama"), lambda e, c: e.get("head_branch", ""), 120),
			Columna("evento", _("Evento"), lambda e, c: e.get("event", ""), 100),
			Columna("numero", _("Número"), lambda e, c: f"#{e.get('run_number', '')}", 70, visible=False),
			Columna("actor", _("Lanzada por"), lambda e, c: f.login(e.get("actor")), 110, visible=False),
			Columna("fecha", _("Fecha"), lambda e, c: f.fecha(e.get("created_at"), c.relativas()), 120),
		],
		cargar, activar,
		[
			Accion(_("A&brir"), activar, "Intro"),
			Accion(_("&Volver a ejecutar"), volver, "Ctrl+R", disponible=lambda p, e: e.get("status") == "completed"),
			Accion(_("Volver a ejecutar so&lo los trabajos fallidos"), lambda p, e: volver(p, e, True),
				disponible=lambda p, e: e.get("conclusion") in ("failure", "cancelled", "timed_out", "startup_failure")),
			Accion(_("&Cancelar la ejecución"), cancelar, "Ctrl+Shift+X", disponible=lambda p, e: e.get("status") in EN_CURSO),
			Accion(_("Avisarme cuando &termine"), vigilar_ejecucion, "Ctrl+Shift+W",
				disponible=lambda p, e: e.get("status") != "completed",
				ayuda=_("Vigila la ejecución en segundo plano y avisa con voz y sonido cuando termine, aunque cierre esta ventana.")),
			Accion(_("Borrar la e&jecución…"), borrar, "Supr", disponible=lambda p, e: e.get("status") == "completed"),
			Accion(_("Lan&zar un flujo de trabajo…"), lambda p, e: lanzar_flujo_repo(p), "Ctrl+N", requiere_elemento=False,
				separador_antes=True),
			Accion(_("Filtro de &GitHub (flujo, rama)…"), filtro, "F4", requiere_elemento=False),
		],
		_("No hay ejecuciones de Actions."), url_html, etiqueta_de=etiqueta,
	)


# ════════════════════════════════════════════════════════════════════════════
# Releases, ramas, etiquetas git y commits
# ════════════════════════════════════════════════════════════════════════════


def _tipo_release(r: dict) -> str:
	if r.get("draft"):
		return _("Borrador")
	if r.get("prerelease"):
		return _("Prelanzamiento")
	return _("Publicada")


def vista_releases(nombre: str, host: str = "github.com") -> VistaRepo:
	def activar(panel: Any, release: dict) -> None:
		abrir.release(panel.ctx, panel, nombre, release)

	def nueva(panel: Any, _e: Any) -> None:
		try:
			from app.ui.detalle.releases import nueva_release
		except ImportError:
			log.debug("No hay nueva_release en app.ui.detalle.releases; se usa el editor sencillo.", exc_info=True)
			_nueva_release_sencilla(panel)
			return
		nueva_release(panel, panel.ctx, nombre, lambda _r: panel.cargar(anunciar=False))

	def _nueva_release_sencilla(panel: Any) -> None:
		from app.ui.editor import CampoExtra, editar

		api = panel.ctx.api()

		def enviar(v: dict) -> Any:
			etiqueta = str(v.get("etiqueta", "")).strip()
			if not etiqueta:
				raise ValueError(_("Escriba la etiqueta de la versión (por ejemplo, v1.0.0)."))
			return api.crear_release(nombre, etiqueta, v["titulo"], v["cuerpo"], str(v.get("rama", "")).strip(),
				bool(v.get("borrador")), bool(v.get("pre")), bool(v.get("notas")))

		editar(panel, panel.ctx, _("Nueva release en {n}").format(n=nombre), enviar, con_titulo=True,
			etiqueta_cuerpo=_("Te&xto de la release (Markdown):"),
			extras=[
				CampoExtra("etiqueta", _("Eti&queta de la versión (por ejemplo, v1.0.0):"), "texto", "",
					ayuda=_("Si no existe, GitHub la crea en la rama indicada.")),
				CampoExtra("rama", _("Rama o co&mmit de origen (vacío = rama por defecto):"), "texto", ""),
				CampoExtra("borrador", _("Guardar como &borrador"), "bool", False),
				CampoExtra("pre", _("Marcar como &prelanzamiento"), "bool", False),
				CampoExtra("notas", _("&Generar las notas automáticamente"), "bool", False),
			],
			al_enviar=lambda _r: panel.cargar(anunciar=False))

	def borrar(panel: Any, release: dict) -> None:
		titulo = release.get("name") or release.get("tag_name", "")
		if not confirmar_peligro(panel, _("¿Borrar la release «{t}»? La etiqueta git se conserva.").format(t=titulo),
			_("Borrar la release")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_release(nombre, release["id"]), exito=_("Release borrada."),
			al_terminar=lambda _r: panel.quitar(release))

	def publicar(panel: Any, release: dict) -> None:
		api = panel.ctx.api()
		_hacer(panel, lambda: api.editar_release(nombre, release["id"], draft=False), _("Release publicada."))

	def prelanzamiento(panel: Any, release: dict) -> None:
		api = panel.ctx.api()
		nuevo = not release.get("prerelease")
		_hacer(panel, lambda: api.editar_release(nombre, release["id"], prerelease=nuevo),
			_("Marcada como prelanzamiento.") if nuevo else _("Ya no es un prelanzamiento."))

	return VistaRepo(
		"repo_releases", _("Releases"),
		[
			Columna("nombre", _("Nombre"), lambda r, c: r.get("name") or r.get("tag_name", ""), 240),
			Columna("etiqueta", _("Etiqueta"), lambda r, c: r.get("tag_name", ""), 110),
			Columna("tipo", _("Tipo"), lambda r, c: _tipo_release(r), 110),
			Columna("recursos", _("Archivos"), lambda r, c: str(len(r.get("assets") or [])), 70),
			Columna("autor", _("Autor"), lambda r, c: f.login(r.get("author")), 110, visible=False),
			Columna("fecha", _("Publicada"), lambda r, c: f.fecha(r.get("published_at") or r.get("created_at"), c.relativas()), 120),
		],
		lambda api, pagina, panel: api.releases(nombre, pagina), activar,
		[
			Accion(_("A&brir"), activar, "Intro"),
			Accion(_("Nue&va release…"), nueva, "Ctrl+N", requiere_elemento=False),
			Accion(_("&Publicar el borrador"), publicar, disponible=lambda p, r: bool(r.get("draft"))),
			Accion(_("Cambiar la marca de pre&lanzamiento"), prelanzamiento),
			Accion(_("Bo&rrar la release…"), borrar, "Supr"),
		],
		_("No hay releases. Cree una con Control+N."), url_html,
	)


def vista_ramas(nombre: str, host: str = "github.com") -> VistaRepo:
	def cargar(api: Any, pagina: int, panel: Any) -> Any:
		resultado = api.ramas(nombre, pagina)
		defecto = _rama_defecto(panel)
		elementos = [dict(r, _defecto=r.get("name") == defecto) for r in _lista(resultado)]
		if isinstance(resultado, Pagina):
			return Pagina(elementos, resultado.siguiente, resultado.ultima, resultado.total, resultado.numero)
		return elementos

	def ver_commits(panel: Any, rama: dict) -> None:
		_ir(panel, "commits", rama=rama.get("name", ""), ruta="", autor="")

	def crear(panel: Any, rama: dict) -> None:
		nueva = pedir_texto(panel, _("&Nombre de la rama nueva (a partir de {r}):").format(r=rama.get("name", "")), _("Crear una rama"))
		if not nueva or not nueva.strip():
			return
		api = panel.ctx.api()
		_hacer(panel, lambda: api.crear_rama(nombre, nueva.strip(), (rama.get("commit") or {}).get("sha", "")),
			_("Rama {r} creada.").format(r=nueva.strip()))

	def renombrar(panel: Any, rama: dict) -> None:
		nueva = pedir_texto(panel, _("&Nuevo nombre de la rama:"), _("Renombrar la rama"), rama.get("name", ""))
		if not nueva or not nueva.strip() or nueva.strip() == rama.get("name"):
			return
		api = panel.ctx.api()
		_hacer(panel, lambda: api.renombrar_rama(nombre, rama["name"], nueva.strip()), _("Rama renombrada a {r}.").format(r=nueva.strip()))

	def borrar(panel: Any, rama: dict) -> None:
		if rama.get("_defecto"):
			mostrar_mensaje(panel, _("No se puede borrar la rama por defecto. Elija otra como rama por defecto antes."),
				_("Borrar la rama"))
			return
		if not confirmar_peligro(panel, _("¿Borrar la rama {r}? Los commits que solo estén en ella se perderán.").format(
			r=rama.get("name", "")), _("Borrar la rama")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_rama(nombre, rama["name"]), exito=_("Rama borrada."),
			al_terminar=lambda _r: panel.quitar(rama))

	def proteger(panel: Any, rama: dict) -> None:
		proteger_rama(panel, rama.get("name", ""))

	def desproteger(panel: Any, rama: dict) -> None:
		if confirmar(panel, _("¿Quitar todas las reglas de protección de {r}?").format(r=rama.get("name", "")),
			_("Quitar la protección"), peligroso=True) != wx.ID_YES:
			return
		api = panel.ctx.api()
		_hacer(panel, lambda: api.desproteger(nombre, rama["name"]), _("Protección quitada."))

	def fusionar(panel: Any, rama: dict) -> None:
		cabeza = rama.get("name", "")
		api = panel.ctx.api()

		def elegida(base: str) -> None:
			if confirmar(panel, _("¿Fusionar {c} en {b}? Se creará un commit de fusión en {b}.").format(c=cabeza, b=base),
				_("Fusionar ramas")) != wx.ID_YES:
				return

			def texto(resultado: Any) -> str:
				return _("{c} fusionada en {b}.").format(c=cabeza, b=base) if resultado else _("No había nada que fusionar: "
					"{b} ya contiene {c}.").format(c=cabeza, b=base)

			_hacer(panel, lambda: api.fusionar_rama(nombre, base, cabeza), texto)

		_elegir_rama(panel, _("Fusionar {r}").format(r=cabeza), _("&Rama de destino:"), elegida, excluir=cabeza)

	def comparar(panel: Any, rama: dict) -> None:
		from app.ui.detalle.diferencias import abrir_diff

		cabeza = rama.get("name", "")
		api = panel.ctx.api()

		def elegida(base: str) -> None:
			abrir_diff(panel.ctx, panel, _("Comparación de {b} con {c}").format(b=base, c=cabeza),
				lambda: api.diff_comparacion(nombre, base, cabeza))

		_elegir_rama(panel, _("Comparar {r}").format(r=cabeza), _("&Comparar con la rama:"), elegida, excluir=cabeza)

	def por_defecto(panel: Any, rama: dict) -> None:
		if confirmar(panel, _("¿Hacer de {r} la rama por defecto?").format(r=rama.get("name", "")), _("Rama por defecto")) != wx.ID_YES:
			return
		api = panel.ctx.api()

		def hecho(repo: Any) -> None:
			if isinstance(repo, dict):
				panel.datos["info"] = repo

		_hacer(panel, lambda: api.editar_repositorio(nombre, default_branch=rama["name"]),
			_("{r} es ahora la rama por defecto.").format(r=rama.get("name", "")), al_terminar=hecho)

	return VistaRepo(
		"repo_ramas", _("Ramas"),
		[
			Columna("nombre", _("Nombre"), lambda r, c: r.get("name", ""), 240),
			Columna("defecto", _("Por defecto"), lambda r, c: _("Sí") if r.get("_defecto") else "", 80),
			Columna("protegida", _("Protegida"), lambda r, c: f.si_no(r.get("protected")), 80),
			Columna("commit", _("Último commit"), lambda r, c: ((r.get("commit") or {}).get("sha") or "")[:7], 90),
		],
		cargar, ver_commits,
		[
			Accion(_("&Ver los commits de la rama"), ver_commits, "Intro"),
			Accion(_("E&xplorar el código de esta rama"), lambda p, r: _ir(p, "codigo", ref=r.get("name", ""), ruta="")),
			Accion(_("Crear una rama a &partir de esta…"), crear, "Ctrl+N", separador_antes=True),
			Accion(_("&Renombrar…"), renombrar, "F2"),
			Accion(_("&Borrar la rama…"), borrar, "Supr"),
			Accion(_("Pro&teger la rama…"), proteger, separador_antes=True),
			Accion(_("Q&uitar la protección"), desproteger, disponible=lambda p, r: bool(r.get("protected"))),
			Accion(_("Fu&sionar en otra rama…"), fusionar, separador_antes=True),
			Accion(_("&Comparar con otra rama…"), comparar, "Ctrl+D"),
			Accion(_("&Hacer rama por defecto"), por_defecto, disponible=lambda p, r: not r.get("_defecto")),
		],
		_("No hay ramas."), url=lambda r: f"{_web(host, nombre)}/tree/{r.get('name', '')}",
	)


def proteger_rama(panel: Any, rama: str) -> None:
	"""Carga la protección actual de la rama y abre el diálogo para cambiarla."""
	api = panel.ctx.api()
	nombre = _nombre(panel)

	def mostrar(actual: Any) -> None:
		d.formulario_modal(
			panel, panel.ctx, lambda v: d.DialogoProteccion(panel, rama, actual if isinstance(actual, dict) else None, v),
			lambda v: api.proteger(nombre, rama, **v), exito=_("Protección de {r} guardada.").format(r=rama),
			al_terminar=lambda _r: panel.cargar(anunciar=False), titulo_error=_("No se pudo proteger la rama"))

	_en_fondo(panel, lambda: api.proteccion(nombre, rama), mostrar, inicio=_("Cargando la protección…"))


def vista_etiquetas(nombre: str, host: str = "github.com") -> VistaRepo:
	def ver(panel: Any, etiqueta: dict) -> None:
		abrir.commit(panel.ctx, panel, nombre, (etiqueta.get("commit") or {}).get("sha", ""))

	def crear(panel: Any, _e: Any) -> None:
		nueva = pedir_texto(panel, _("&Nombre de la etiqueta (por ejemplo, v1.0.0):"), _("Crear una etiqueta"))
		if not nueva or not nueva.strip():
			return
		api = panel.ctx.api()

		def elegida(rama: str) -> None:
			mensaje = pedir_texto(panel, _("&Mensaje (vacío = etiqueta ligera, sin anotar):"), _("Crear una etiqueta"))
			if mensaje is None:
				return

			def trabajo() -> Any:
				sha = (api.rama(nombre, rama).get("commit") or {}).get("sha", "")
				return api.crear_etiqueta_git(nombre, nueva.strip(), sha, mensaje.strip())

			_hacer(panel, trabajo, _("Etiqueta {e} creada en {r}.").format(e=nueva.strip(), r=rama))

		_elegir_rama(panel, _("Crear una etiqueta"), _("&Rama cuyo último commit se etiqueta:"), elegida)

	def borrar(panel: Any, etiqueta: dict) -> None:
		if not confirmar_peligro(panel, _("¿Borrar la etiqueta {e}? Las releases que la usen quedarán como borradores.").format(
			e=etiqueta.get("name", "")), _("Borrar la etiqueta")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_etiqueta_git(nombre, etiqueta["name"]), exito=_("Etiqueta borrada."),
			al_terminar=lambda _r: panel.quitar(etiqueta))

	def zip_etiqueta(panel: Any, etiqueta: dict) -> None:
		from app.ui.descarga_codigo import descargar_codigo

		descargar_codigo(panel, panel.ctx, nombre, etiqueta.get("name", ""))

	return VistaRepo(
		"repo_etiquetas", _("Etiquetas git (tags)"),
		[
			Columna("nombre", _("Nombre"), lambda e, c: e.get("name", ""), 240),
			Columna("commit", _("Commit"), lambda e, c: ((e.get("commit") or {}).get("sha") or "")[:7], 90),
		],
		lambda api, pagina, panel: api.etiquetas_git(nombre, pagina), ver,
		[
			Accion(_("&Ver el commit"), ver, "Intro"),
			Accion(_("E&xplorar el código en esta etiqueta"), lambda p, e: _ir(p, "codigo", ref=e.get("name", ""), ruta="")),
			Accion(_("&Crear una etiqueta…"), crear, "Ctrl+N", requiere_elemento=False, separador_antes=True),
			Accion(_("&Borrar la etiqueta…"), borrar, "Supr"),
			Accion(_("Descargar en &zip…"), zip_etiqueta),
		],
		_("No hay etiquetas git."), url=lambda e: f"{_web(host, nombre)}/tree/{e.get('name', '')}",
	)


def _autor_commit(c: dict) -> str:
	if c.get("author"):
		return f.login(c.get("author"))
	return ((c.get("commit") or {}).get("author") or {}).get("name", "")


def detalle_commit(c: dict, ctx: Any) -> str:
	datos = c.get("commit") or {}
	autor = datos.get("author") or {}
	return "\n".join([
		_("Commit {s}").format(s=c.get("sha", "")),
		_("Autor: {a} <{c}>").format(a=autor.get("name", ""), c=autor.get("email", "")),
		_("Fecha: {f}").format(f=f.fecha_completa(autor.get("date"))),
		_("Verificado: {v}").format(v=f.si_no((datos.get("verification") or {}).get("verified"))),
		_("Enlace: {u}").format(u=c.get("html_url", "")),
		"",
		datos.get("message", ""),
	])


def vista_commits(nombre: str, host: str = "github.com") -> VistaRepo:
	def cargar(api: Any, pagina: int, panel: Any) -> Any:
		datos = panel.datos
		return api.commits(nombre, pagina, rama=datos.get("rama", ""), ruta=datos.get("ruta", ""), autor=datos.get("autor", ""))

	def etiqueta(panel: Any) -> str:
		datos = panel.datos
		partes = [_("rama {r}").format(r=datos.get("rama") or _rama_defecto(panel) or _("por defecto"))]
		if datos.get("ruta"):
			partes.append(_("ruta {r}").format(r=datos["ruta"]))
		if datos.get("autor"):
			partes.append(_("autor {a}").format(a=datos["autor"]))
		return _("Commits ({p})").format(p=", ".join(partes))

	def ver(panel: Any, c: dict) -> None:
		abrir.commit(panel.ctx, panel, nombre, c.get("sha", ""))

	def filtro(panel: Any, _e: Any) -> None:
		datos = panel.datos
		opciones = [_("Rama: {v}").format(v=datos.get("rama") or _("por defecto")),
			_("Autor: {v}").format(v=datos.get("autor") or _("cualquiera")),
			_("Ruta: {v}").format(v=datos.get("ruta") or _("todo el repositorio")), _("Quitar los filtros")]
		eleccion = elegir_uno(panel, _("Filtro de GitHub"), _("&Filtro que quiere cambiar:"), opciones)
		if eleccion == 0:
			def elegida(rama: str) -> None:
				datos["rama"] = rama
				_recargar_filtrado(panel)

			_elegir_rama(panel, _("Rama"), _("&Rama:"), elegida, actual=datos.get("rama", ""))
		elif eleccion in (1, 2):
			clave = "autor" if eleccion == 1 else "ruta"
			etiqueta_campo = _("&Usuario de GitHub o correo del autor (vacío = cualquiera):") if eleccion == 1 else \
				_("&Ruta de un archivo o carpeta (vacío = todo):")
			texto = pedir_texto(panel, etiqueta_campo, _("Filtro de commits"), datos.get(clave, ""))
			if texto is not None:
				datos[clave] = texto.strip().strip("/") if clave == "ruta" else texto.strip()
				_recargar_filtrado(panel)
		elif eleccion == 3:
			for clave in ("rama", "autor", "ruta"):
				datos.pop(clave, None)
			_recargar_filtrado(panel)

	def quitar_filtros(panel: Any, _e: Any) -> None:
		for clave in ("rama", "autor", "ruta"):
			panel.datos.pop(clave, None)
		_recargar_filtrado(panel)

	def crear_rama(panel: Any, c: dict) -> None:
		nueva = pedir_texto(panel, _("&Nombre de la rama nueva (en el commit {s}):").format(s=c.get("sha", "")[:7]), _("Crear una rama"))
		if not nueva or not nueva.strip():
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.crear_rama(nombre, nueva.strip(), c["sha"]),
			exito=_("Rama {r} creada.").format(r=nueva.strip()))

	def crear_etiqueta(panel: Any, c: dict) -> None:
		nueva = pedir_texto(panel, _("&Nombre de la etiqueta (por ejemplo, v1.0.0):"), _("Etiquetar el commit"))
		if not nueva or not nueva.strip():
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.crear_etiqueta_git(nombre, nueva.strip(), c["sha"]),
			exito=_("Etiqueta {e} creada.").format(e=nueva.strip()))

	return VistaRepo(
		"repo_commits", _("Commits"),
		[
			Columna("mensaje", _("Mensaje"), lambda c, x: f.primera_linea((c.get("commit") or {}).get("message")), 380),
			Columna("autor", _("Autor"), lambda c, x: _autor_commit(c), 130),
			Columna("fecha", _("Fecha"), lambda c, x: f.fecha(((c.get("commit") or {}).get("author") or {}).get("date"), x.relativas()), 120),
			Columna("sha", _("SHA"), lambda c, x: (c.get("sha") or "")[:7], 80),
			Columna("verificado", _("Verificado"), lambda c, x: f.si_no(((c.get("commit") or {}).get("verification") or {}).get("verified")),
				80, visible=False),
		],
		cargar, ver,
		[
			Accion(_("&Ver el commit"), ver, "Intro"),
			Accion(_("Copiar el &SHA"), lambda p, c: copiar(p.ctx, c.get("sha", ""), _("SHA copiado.")), "Ctrl+Shift+S"),
			Accion(_("E&xplorar el código en este commit"), lambda p, c: _ir(p, "codigo", ref=c.get("sha", ""), ruta="")),
			Accion(_("Crear una &rama desde este commit…"), crear_rama, separador_antes=True),
			Accion(_("Crear una e&tiqueta en este commit…"), crear_etiqueta),
			Accion(_("Filtro de &GitHub (rama, autor, ruta)…"), filtro, "F4", requiere_elemento=False, separador_antes=True),
			Accion(_("Q&uitar los filtros de GitHub"), quitar_filtros, requiere_elemento=False,
				disponible=lambda p, e: any(p.datos.get(k) for k in ("rama", "autor", "ruta"))),
		],
		_("No hay commits con este filtro."), url_html, detalle_commit, etiqueta_de=etiqueta,
	)


# ════════════════════════════════════════════════════════════════════════════
# Proyectos, hitos y etiquetas de issues
# ════════════════════════════════════════════════════════════════════════════


def vista_proyectos(nombre: str, host: str = "github.com") -> VistaRepo:
	def activar(panel: Any, proyecto: dict) -> None:
		abrir.proyecto(panel.ctx, panel, proyecto)

	return VistaRepo(
		"repo_proyectos", _("Proyectos"),
		[
			Columna("titulo", _("Proyecto"), lambda p, c: p.get("title", ""), 260),
			Columna("numero", _("Número"), lambda p, c: str(p.get("number", "")), 70),
			Columna("elementos", _("Elementos"), lambda p, c: str((p.get("items") or {}).get("totalCount", "")), 80),
			Columna("estado", _("Estado"), lambda p, c: _("Cerrado") if p.get("closed") else _("Abierto"), 80),
			Columna("descripcion", _("Descripción"), lambda p, c: p.get("shortDescription") or "", 260),
			Columna("actualizado", _("Actualizado"), lambda p, c: f.fecha(p.get("updatedAt"), c.relativas()), 120),
		],
		lambda api, pagina, panel: api.proyectos_repo(nombre), activar,
		[Accion(_("A&brir"), activar, "Intro")],
		_("Este repositorio no tiene proyectos."), url=lambda p: p.get("url", ""), paginada=False,
	)


def _progreso_hito(h: dict) -> str:
	abiertas, cerradas = int(h.get("open_issues") or 0), int(h.get("closed_issues") or 0)
	total = abiertas + cerradas
	return f"{round(cerradas * 100 / total)} %" if total else _("sin issues")


def vista_hitos(nombre: str, host: str = "github.com") -> VistaRepo:
	def ver(panel: Any, hito: dict) -> None:
		_ir(panel, "issues", hito=str(hito.get("number", "")), hito_titulo=hito.get("title", ""), estado="all")

	def guardar(panel: Any, hito: dict | None) -> None:
		api = panel.ctx.api()

		def enviar(v: dict) -> Any:
			fecha = d.fecha_a_iso(v["fecha"]) or None
			if hito is None:
				creado = api.crear_hito(nombre, v["titulo"], v["descripcion"], fecha or "")
				if v["estado"] == "closed":
					api.editar_hito(nombre, creado["number"], state="closed")
				return creado
			return api.editar_hito(nombre, hito["number"], title=v["titulo"], description=v["descripcion"], due_on=fecha,
				state=v["estado"])

		d.formulario_modal(panel, panel.ctx, lambda v: d.DialogoHito(panel, hito, v), enviar,
			exito=_("Hito guardado."), al_terminar=lambda _r: panel.cargar(anunciar=False))

	def borrar(panel: Any, hito: dict) -> None:
		if not confirmar_peligro(panel, _("¿Borrar el hito «{t}»? Sus issues se quedan sin hito.").format(t=hito.get("title", "")),
			_("Borrar el hito")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_hito(nombre, hito["number"]), exito=_("Hito borrado."),
			al_terminar=lambda _r: panel.quitar(hito))

	def cambiar_estado(panel: Any, hito: dict, estado: str) -> None:
		api = panel.ctx.api()
		_hacer(panel, lambda: api.editar_hito(nombre, hito["number"], state=estado),
			_("Hito cerrado.") if estado == "closed" else _("Hito reabierto."))

	def filtro(panel: Any, _e: Any) -> None:
		if _elegir_estado(panel, _("Hitos"), [("open", "abiertos"), ("closed", "cerrados"), ("all", "todos")]):
			_recargar_filtrado(panel)

	return VistaRepo(
		"repo_hitos", _("Hitos"),
		[
			Columna("titulo", _("Título"), lambda h, c: h.get("title", ""), 240),
			Columna("estado", _("Estado"), lambda h, c: _("Cerrado") if h.get("state") == "closed" else _("Abierto"), 80),
			Columna("progreso", _("Progreso"), lambda h, c: _progreso_hito(h), 80),
			Columna("abiertas", _("Abiertas"), lambda h, c: str(h.get("open_issues", 0)), 70),
			Columna("cerradas", _("Cerradas"), lambda h, c: str(h.get("closed_issues", 0)), 70),
			Columna("fecha", _("Fecha límite"), lambda h, c: f.fecha_completa(h.get("due_on")).split(" ")[0] if h.get("due_on") else "", 100),
			Columna("descripcion", _("Descripción"), lambda h, c: h.get("description") or "", 240, visible=False),
		],
		lambda api, pagina, panel: api.hitos(nombre, panel.datos.get("estado", "open")), ver,
		[
			Accion(_("&Ver las issues del hito"), ver, "Intro"),
			Accion(_("Nuevo &hito…"), lambda p, e: guardar(p, None), "Ctrl+N", requiere_elemento=False),
			Accion(_("Cambiar el hi&to…"), guardar, "F2"),
			Accion(_("&Borrar el hito…"), borrar, "Supr"),
			Accion(_("&Cerrar el hito"), lambda p, h: cambiar_estado(p, h, "closed"), disponible=lambda p, h: h.get("state") == "open"),
			Accion(_("&Reabrir el hito"), lambda p, h: cambiar_estado(p, h, "open"), disponible=lambda p, h: h.get("state") == "closed"),
			Accion(_("Filtro de &GitHub (abiertos, cerrados, todos)…"), filtro, "F4", requiere_elemento=False, separador_antes=True),
		],
		_("No hay hitos con este filtro. Cree uno con Control+N."), url_html, paginada=False,
		etiqueta_de=lambda p: _("Hitos ({e})").format(e={"open": _("abiertos"), "closed": _("cerrados")}.get(
			p.datos.get("estado", "open"), _("todos"))),
	)


def vista_labels(nombre: str, host: str = "github.com") -> VistaRepo:
	def ver(panel: Any, label: dict) -> None:
		_ir(panel, "issues", etiqueta=label.get("name", ""), estado="open")

	def guardar(panel: Any, label: dict | None) -> None:
		api = panel.ctx.api()

		def enviar(v: dict) -> Any:
			if label is None:
				return api.crear_etiqueta(nombre, v["nombre"], v["color"], v["descripcion"])
			return api.editar_etiqueta(nombre, label["name"], nuevo=v["nombre"] if v["nombre"] != label["name"] else "",
				color=v["color"], descripcion=v["descripcion"])

		d.formulario_modal(panel, panel.ctx, lambda v: d.DialogoLabel(panel, label, v), enviar,
			exito=_("Etiqueta guardada."), al_terminar=lambda _r: panel.cargar(anunciar=False))

	def borrar(panel: Any, label: dict) -> None:
		if not confirmar_peligro(panel, _("¿Borrar la etiqueta «{e}»? Se quitará de todas las issues y pull requests.").format(
			e=label.get("name", "")), _("Borrar la etiqueta")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_etiqueta(nombre, label["name"]), exito=_("Etiqueta borrada."),
			al_terminar=lambda _r: panel.quitar(label))

	def color(label: dict) -> str:
		codigo = str(label.get("color", ""))
		descripcion = d.nombre_color(codigo)
		return f"{descripcion} (#{codigo})" if descripcion else f"#{codigo}"

	return VistaRepo(
		"repo_labels", _("Etiquetas de issues (labels)"),
		[
			Columna("nombre", _("Nombre"), lambda l, c: l.get("name", ""), 200),
			Columna("color", _("Color"), lambda l, c: color(l), 150),
			Columna("descripcion", _("Descripción"), lambda l, c: l.get("description") or "", 320),
		],
		lambda api, pagina, panel: api.etiquetas(nombre), ver,
		[
			Accion(_("&Ver las issues con esta etiqueta"), ver, "Intro"),
			Accion(_("Nueva &label…"), lambda p, e: guardar(p, None), "Ctrl+N", requiere_elemento=False),
			Accion(_("Cam&biar la label (nombre, color, descripción)…"), guardar, "F2"),
			Accion(_("Bo&rrar la label…"), borrar, "Supr"),
		],
		_("No hay etiquetas. Cree una con Control+N."), paginada=False,
		url=lambda l: f"{_web(host, nombre)}/labels/{l.get('name', '')}",
	)


# ════════════════════════════════════════════════════════════════════════════
# Personas: colaboradores, bifurcaciones y estrellas
# ════════════════════════════════════════════════════════════════════════════

PERMISOS = [("pull", "Lectura"), ("triage", "Clasificación"), ("push", "Escritura"), ("maintain", "Mantenimiento"),
	("admin", "Administración")]
#: Las invitaciones usan otros nombres para los mismos permisos.
PERMISOS_INVITACION = {"pull": "read", "push": "write", "triage": "triage", "maintain": "maintain", "admin": "admin"}


def _login_colaborador(e: dict) -> str:
	return (e.get("invitee") or {}).get("login", "") if e.get("_invitacion") else e.get("login", "")


def _permiso_colaborador(e: dict) -> str:
	if e.get("_invitacion"):
		return f.estado(e.get("permissions"))
	if e.get("role_name"):
		return f.estado(e["role_name"])
	permisos = e.get("permissions") or {}
	return next((f.estado(p) for p in ("admin", "maintain", "push", "triage", "pull") if permisos.get(p)), "")


def vista_colaboradores(nombre: str, host: str = "github.com") -> VistaRepo:
	def cargar(api: Any, pagina: int, panel: Any) -> Pagina:
		resultado = api.colaboradores(nombre, pagina)
		elementos = _lista(resultado)
		if pagina == 1:
			try:
				invitaciones = [dict(i, _invitacion=True) for i in api.invitaciones_repo(nombre) or []]
			except Exception:  # noqa: BLE001 - sin permiso para ver invitaciones, la lista sigue siendo útil
				log.warning("No se pudieron cargar las invitaciones de %s", nombre, exc_info=True)
				invitaciones = []
			elementos = invitaciones + elementos
		return Pagina(elementos, resultado.siguiente if isinstance(resultado, Pagina) else "")

	def ver(panel: Any, e: dict) -> None:
		abrir.usuario(panel.ctx, panel, _login_colaborador(e))

	def elegir_permiso(panel: Any, actual: str = "push") -> str | None:
		claves = [c for c, _n in PERMISOS]
		eleccion = elegir_uno(panel, _("Permiso"), _("&Permiso:"), [_(n) for _c, n in PERMISOS],
			claves.index(actual) if actual in claves else 2)
		return None if eleccion is None else claves[eleccion]

	def invitar(panel: Any, _e: Any) -> None:
		login = pedir_texto(panel, _("&Usuario de GitHub que quiere invitar:"), _("Invitar a una persona"))
		if not login or not login.strip():
			return
		permiso = elegir_permiso(panel)
		if permiso is None:
			return
		api = panel.ctx.api()
		_hacer(panel, lambda: api.invitar_colaborador(nombre, login.strip().lstrip("@"), permiso),
			_("Invitación enviada a {l}.").format(l=login.strip()))

	def cambiar_permiso(panel: Any, e: dict) -> None:
		permiso = elegir_permiso(panel, e.get("role_name") or "push")
		if permiso is None:
			return
		api = panel.ctx.api()
		if e.get("_invitacion"):
			# No hay función en la fachada para cambiar el permiso de una invitación: cliente directo.
			trabajo: Callable[[], Any] = lambda: api.c.patch(f"{ruta_repo(nombre)}/invitations/{int(e['id'])}",
				{"permissions": PERMISOS_INVITACION[permiso]})
		else:
			trabajo = lambda: api.invitar_colaborador(nombre, e.get("login", ""), permiso)
		_hacer(panel, trabajo, _("Permiso cambiado."))

	def quitar(panel: Any, e: dict) -> None:
		login = _login_colaborador(e)
		if not confirmar_peligro(panel, _("¿Quitar a {l} el acceso al repositorio?").format(l=login), _("Quitar el acceso")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.quitar_colaborador(nombre, login), exito=_("Acceso quitado a {l}.").format(l=login),
			al_terminar=lambda _r: panel.quitar(e))

	def cancelar(panel: Any, e: dict) -> None:
		if not confirmar_peligro(panel, _("¿Cancelar la invitación a {l}?").format(l=_login_colaborador(e)), _("Cancelar la invitación")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.cancelar_invitacion_repo(nombre, e["id"]), exito=_("Invitación cancelada."),
			al_terminar=lambda _r: panel.quitar(e))

	return VistaRepo(
		"repo_colaboradores", _("Colaboradores e invitaciones"),
		[
			Columna("usuario", _("Usuario"), lambda e, c: _login_colaborador(e), 200),
			Columna("permiso", _("Permiso"), lambda e, c: _permiso_colaborador(e), 130),
			Columna("estado", _("Situación"), lambda e, c: _("Invitación pendiente") if e.get("_invitacion") else _("Colaborador"), 150),
			Columna("fecha", _("Invitado"), lambda e, c: f.fecha(e.get("created_at"), c.relativas()) if e.get("_invitacion") else "", 110,
				visible=False),
		],
		cargar, ver,
		[
			Accion(_("&Ver el perfil"), ver, "Intro"),
			Accion(_("&Invitar a una persona…"), invitar, "Ctrl+N", requiere_elemento=False),
			Accion(_("Cambiar el &permiso…"), cambiar_permiso, "F2"),
			Accion(_("Q&uitar el acceso…"), quitar, "Supr", disponible=lambda p, e: not e.get("_invitacion")),
			Accion(_("&Cancelar la invitación…"), cancelar, "Supr", disponible=lambda p, e: bool(e.get("_invitacion"))),
		],
		_("Solo usted tiene acceso. Invite a alguien con Control+N."),
		url=lambda e: e.get("html_url") or (e.get("invitee") or {}).get("html_url", ""),
	)


def vista_bifurcaciones(nombre: str, host: str = "github.com") -> VistaRepo:
	def activar(panel: Any, repo: dict) -> None:
		abrir.repositorio(panel.ctx, repo.get("full_name", ""))

	return VistaRepo(
		"repo_bifurcaciones", _("Bifurcaciones (forks)"), columnas_repositorio(),
		lambda api, pagina, panel: api.bifurcaciones(nombre, pagina), activar,
		[
			Accion(_("A&brir"), activar, "Intro"),
			Accion(_("Ver al &propietario"), lambda p, r: abrir.usuario(p.ctx, p, (r.get("owner") or {}).get("login", ""))),
			Accion(_("&Comparar con este repositorio"), lambda p, r: webbrowser.open(
				f"{_web(host, nombre)}/compare/{_rama_defecto(p) or 'main'}...{(r.get('owner') or {}).get('login', '')}:"
				f"{r.get('default_branch') or 'main'}")),
		],
		_("Nadie ha bifurcado este repositorio."), url_html, detalle_repositorio,
	)


def vista_observadores(nombre: str, host: str = "github.com") -> VistaRepo:
	def ver(panel: Any, u: dict) -> None:
		abrir.usuario(panel.ctx, panel, u.get("login", ""))

	return VistaRepo(
		"repo_observadores", _("Personas que le han dado estrella"),
		[
			Columna("login", _("Usuario"), lambda u, c: u.get("login", ""), 220),
			Columna("tipo", _("Tipo"), lambda u, c: _("Organización") if u.get("type") == "Organization" else _("Persona"), 120),
		],
		lambda api, pagina, panel: api.observadores_estrella(nombre, pagina), ver,
		[Accion(_("&Ver el perfil"), ver, "Intro")],
		_("Nadie le ha dado estrella todavía."), url_html,
	)


# ════════════════════════════════════════════════════════════════════════════
# Seguridad
# ════════════════════════════════════════════════════════════════════════════

TIPOS_ALERTA = {"dependabot": "Dependabot", "codigo": "Escaneo de código", "secretos": "Secretos expuestos", "aviso": "No disponible"}
MOTIVOS_DESCARTE = {
	"dependabot": [("fix_started", "Ya se está corrigiendo"), ("inaccurate", "La alerta no es correcta"),
		("no_bandwidth", "No hay tiempo para corregirla"), ("not_used", "El código vulnerable no se usa"),
		("tolerable_risk", "El riesgo es aceptable")],
	"codigo": [("false positive", "Falso positivo"), ("won't fix", "No se corregirá"), ("used in tests", "Solo se usa en pruebas")],
	"secretos": [("false_positive", "Falso positivo"), ("wont_fix", "No se corregirá"), ("revoked", "El secreto ya se revocó"),
		("used_in_tests", "Solo se usa en pruebas")],
}


def normalizar_alerta(tipo: str, a: dict) -> dict:
	"""Convierte una alerta de cualquiera de los tres orígenes a una forma común para la lista."""
	if tipo == "dependabot":
		aviso = a.get("security_advisory") or {}
		dependencia = a.get("dependency") or {}
		paquete = (dependencia.get("package") or {}).get("name", "")
		return {"_tipo": tipo, "_datos": a, "numero": a.get("number"), "resumen": aviso.get("summary", ""),
			"gravedad": (a.get("security_vulnerability") or {}).get("severity") or aviso.get("severity", ""),
			"estado": a.get("state", ""), "ubicacion": f"{paquete} ({dependencia.get('manifest_path', '')})".strip(),
			"fecha": a.get("created_at"), "html_url": a.get("html_url", "")}
	if tipo == "codigo":
		regla = a.get("rule") or {}
		ubicacion = ((a.get("most_recent_instance") or {}).get("location")) or {}
		return {"_tipo": tipo, "_datos": a, "numero": a.get("number"), "resumen": regla.get("description") or regla.get("name", ""),
			"gravedad": regla.get("security_severity_level") or regla.get("severity", ""), "estado": a.get("state", ""),
			"ubicacion": f"{ubicacion.get('path', '')}:{ubicacion.get('start_line', '')}" if ubicacion.get("path") else "",
			"fecha": a.get("created_at"), "html_url": a.get("html_url", "")}
	return {"_tipo": tipo, "_datos": a, "numero": a.get("number"), "resumen": a.get("secret_type_display_name") or a.get("secret_type", ""),
		"gravedad": "", "estado": a.get("state", ""), "ubicacion": "", "fecha": a.get("created_at"), "html_url": a.get("html_url", "")}


def detalle_alerta(a: dict, ctx: Any) -> str:
	if a.get("_tipo") == "aviso":
		return a.get("resumen", "")
	datos = a.get("_datos") or {}
	lineas = [
		_("Tipo: {t}").format(t=_(TIPOS_ALERTA.get(a["_tipo"], a["_tipo"]))),
		_("Alerta #{n}: {r}").format(n=a.get("numero", ""), r=a.get("resumen", "")),
		_("Gravedad: {g}").format(g=f.estado(a.get("gravedad")) or "-"),
		_("Estado: {e}").format(e=f.estado(a.get("estado"))),
		_("Ubicación: {u}").format(u=a.get("ubicacion") or "-"),
		_("Creada: {c}").format(c=f.fecha_completa(a.get("fecha"))),
		_("Enlace: {u}").format(u=a.get("html_url", "")),
	]
	if a["_tipo"] == "dependabot":
		aviso = datos.get("security_advisory") or {}
		vulnerable = datos.get("security_vulnerability") or {}
		lineas += [
			_("Identificadores: {i}").format(i=", ".join(i.get("value", "") for i in aviso.get("identifiers") or []) or "-"),
			_("Versiones afectadas: {v}").format(v=vulnerable.get("vulnerable_version_range") or "-"),
			_("Versión corregida: {v}").format(v=(vulnerable.get("first_patched_version") or {}).get("identifier") or "-"),
			"", aviso.get("description", ""),
		]
	elif a["_tipo"] == "codigo":
		instancia = datos.get("most_recent_instance") or {}
		lineas += ["", (instancia.get("message") or {}).get("text", ""), (datos.get("rule") or {}).get("full_description", "")]
	return "\n".join(l for l in lineas if l is not None)


def vista_seguridad(nombre: str, host: str = "github.com") -> VistaRepo:
	def cargar(api: Any, pagina: int, panel: Any) -> list:
		estado = panel.datos.get("estado", "open")
		elementos: list[dict] = []
		for tipo, funcion in (("dependabot", api.alertas_dependabot), ("codigo", api.alertas_codigo), ("secretos", api.alertas_secretos)):
			# Cada origen puede estar desactivado o sin permiso (403/404): se dice en una fila y se siguen los demás.
			estado_api = "resolved" if tipo == "secretos" and estado in ("dismissed", "fixed") else estado
			try:
				alertas = funcion(nombre, estado_api) if estado != "all" else funcion(nombre, "")
			except Exception as error:  # noqa: BLE001 - un origen no disponible no oculta los otros
				log.info("Alertas %s de %s no disponibles: %s", tipo, nombre, mensaje_error(error))
				elementos.append({"_tipo": "aviso", "resumen": _("{t}: no disponible ({m}).").format(
					t=_(TIPOS_ALERTA[tipo]), m=mensaje_error(error)), "estado": "", "gravedad": ""})
				continue
			elementos.extend(normalizar_alerta(tipo, a) for a in alertas or [] if isinstance(a, dict))
		return elementos

	def descartar(panel: Any, alerta: dict) -> None:
		tipo = alerta["_tipo"]
		motivos = MOTIVOS_DESCARTE[tipo]
		eleccion = elegir_uno(panel, _("Descartar la alerta"), _("&Motivo:"), [_(n) for _c, n in motivos])
		if eleccion is None:
			return
		comentario = pedir_texto(panel, _("&Comentario (opcional):"), _("Descartar la alerta"))
		if comentario is None:
			return
		api = panel.ctx.api()
		motivo, numero = motivos[eleccion][0], alerta["numero"]
		if tipo == "dependabot":
			trabajo: Callable[[], Any] = lambda: api.cambiar_alerta_dependabot(nombre, numero, "dismissed", motivo, comentario)
		elif tipo == "codigo":
			trabajo = lambda: api.cambiar_alerta_codigo(nombre, numero, "dismissed", motivo, comentario)
		else:
			trabajo = lambda: api.cambiar_alerta_secreto(nombre, numero, "resolved", motivo, comentario)
		_hacer(panel, trabajo, _("Alerta descartada."))

	def reabrir(panel: Any, alerta: dict) -> None:
		api = panel.ctx.api()
		tipo, numero = alerta["_tipo"], alerta["numero"]
		funcion = {"dependabot": api.cambiar_alerta_dependabot, "codigo": api.cambiar_alerta_codigo,
			"secretos": api.cambiar_alerta_secreto}[tipo]
		_hacer(panel, lambda: funcion(nombre, numero, "open"), _("Alerta reabierta."))

	def politica(panel: Any, _e: Any) -> None:
		from app.ui import visor_ayuda

		api = panel.ctx.api()

		def mostrar(texto: str) -> None:
			if not texto:
				mostrar_mensaje(panel, _("El repositorio no tiene política de seguridad (SECURITY.md)."), _("Política de seguridad"))
				return
			visor_ayuda.mostrar_documento(panel, _("Política de seguridad de {n}").format(n=nombre), texto)

		_en_fondo(panel, lambda: api.politica_seguridad(nombre), mostrar, inicio=_("Buscando SECURITY.md…"))

	def filtro(panel: Any, _e: Any) -> None:
		if _elegir_estado(panel, _("Alertas"), [("open", "abiertas"), ("dismissed", "descartadas"), ("fixed", "corregidas"),
			("all", "todas")]):
			_recargar_filtrado(panel)

	def real(_p: Any, a: dict) -> bool:
		return a.get("_tipo") != "aviso"

	return VistaRepo(
		"repo_seguridad", _("Alertas de seguridad"),
		[
			Columna("tipo", _("Tipo"), lambda a, c: _(TIPOS_ALERTA.get(a.get("_tipo", ""), "")), 140),
			Columna("resumen", _("Resumen"), lambda a, c: a.get("resumen", ""), 360),
			Columna("gravedad", _("Gravedad"), lambda a, c: f.estado(a.get("gravedad")), 90),
			Columna("estado", _("Estado"), lambda a, c: f.estado(a.get("estado")), 100),
			Columna("ubicacion", _("Ubicación"), lambda a, c: a.get("ubicacion", ""), 220),
			Columna("numero", _("Número"), lambda a, c: f"#{a['numero']}" if a.get("numero") else "", 60, visible=False),
			Columna("fecha", _("Fecha"), lambda a, c: f.fecha(a.get("fecha"), c.relativas()), 110, visible=False),
		],
		cargar, lambda p, a: p.mostrar_detalles(),
		[
			Accion(_("&Ver los detalles"), lambda p, a: p.mostrar_detalles(), "Intro"),
			Accion(_("Des&cartar la alerta…"), descartar, "Supr", disponible=lambda p, a: real(p, a) and a.get("estado") == "open"),
			Accion(_("&Reabrir la alerta"), reabrir,
				disponible=lambda p, a: real(p, a) and a.get("estado") in ("dismissed", "resolved", "auto_dismissed")),
			Accion(_("Ver la &política de seguridad (SECURITY.md)"), politica, requiere_elemento=False, separador_antes=True),
			Accion(_("Filtro de &GitHub (abiertas, descartadas, corregidas)…"), filtro, "F4", requiere_elemento=False),
		],
		_("No hay alertas de seguridad con este filtro."), url=lambda a: a.get("html_url", ""), detalle=detalle_alerta,
		paginada=False,
		etiqueta_de=lambda p: _("Alertas de seguridad ({e})").format(e={"open": _("abiertas"), "dismissed": _("descartadas"),
			"fixed": _("corregidas")}.get(p.datos.get("estado", "open"), _("todas"))),
	)


# ════════════════════════════════════════════════════════════════════════════
# Entornos, secretos, webhooks, claves, reglas y despliegues
# ════════════════════════════════════════════════════════════════════════════


def _reglas_entorno(e: dict) -> str:
	partes = []
	for regla in e.get("protection_rules") or []:
		if regla.get("type") == "wait_timer":
			partes.append(_("espera {n} min").format(n=regla.get("wait_timer", 0)))
		elif regla.get("type") == "required_reviewers":
			personas = [((r.get("reviewer") or {}).get("login") or (r.get("reviewer") or {}).get("name", ""))
				for r in regla.get("reviewers") or []]
			partes.append(_("revisores: {r}").format(r=", ".join(personas) or "-"))
		elif regla.get("type") == "branch_policy":
			partes.append(_("política de ramas"))
	return ", ".join(partes) or _("ninguna")


def vista_entornos(nombre: str, host: str = "github.com") -> VistaRepo:
	def guardar(panel: Any, entorno: dict | None) -> None:
		api = panel.ctx.api()
		d.formulario_modal(panel, panel.ctx, lambda v: d.DialogoEntorno(panel, entorno, v),
			lambda v: api.crear_entorno(nombre, v["nombre"], **d.DialogoEntorno.reglas(v)),
			exito=_("Entorno guardado."), al_terminar=lambda _r: panel.cargar(anunciar=False))

	def borrar(panel: Any, entorno: dict) -> None:
		if not confirmar_peligro(panel, _("¿Borrar el entorno {e} con sus secretos y reglas?").format(e=entorno.get("name", "")),
			_("Borrar el entorno")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_entorno(nombre, entorno["name"]), exito=_("Entorno borrado."),
			al_terminar=lambda _r: panel.quitar(entorno))

	return VistaRepo(
		"repo_entornos", _("Entornos de despliegue"),
		[
			Columna("nombre", _("Nombre"), lambda e, c: e.get("name", ""), 200),
			Columna("reglas", _("Reglas de protección"), lambda e, c: _reglas_entorno(e), 300),
			Columna("ramas", _("Ramas que pueden desplegar"), lambda e, c: _("solo protegidas") if (e.get("deployment_branch_policy")
				or {}).get("protected_branches") else (_("personalizadas") if e.get("deployment_branch_policy") else _("todas")), 160),
			Columna("actualizado", _("Actualizado"), lambda e, c: f.fecha(e.get("updated_at"), c.relativas()), 120),
		],
		lambda api, pagina, panel: api.entornos(nombre), guardar,
		[
			Accion(_("Cam&biar el entorno…"), guardar, "F2"),
			Accion(_("Nuevo en&torno…"), lambda p, e: guardar(p, None), "Ctrl+N", requiere_elemento=False),
			Accion(_("Bo&rrar el entorno…"), borrar, "Supr"),
		],
		_("No hay entornos. Cree uno con Control+N."), url_html, paginada=False,
	)


def vista_secretos(nombre: str, host: str = "github.com") -> VistaRepo:
	def cargar(api: Any, pagina: int, panel: Any) -> list:
		secretos = [dict(s, _tipo="secreto") for s in api.secretos(nombre) or []]
		try:
			variables = [dict(v, _tipo="variable") for v in api.variables(nombre) or []]
		except Exception:  # noqa: BLE001 - sin permiso para variables se muestran al menos los secretos
			log.warning("No se pudieron cargar las variables de %s", nombre, exc_info=True)
			variables = []
		return sorted(secretos + variables, key=lambda e: (e["_tipo"], e.get("name", "")))

	def guardar(panel: Any, elemento: dict | None) -> None:
		api = panel.ctx.api()
		editando = elemento is not None
		tipo = (elemento or {}).get("_tipo", "secreto")

		def enviar(v: dict) -> Any:
			if v["tipo"] == "secreto":
				return api.guardar_secreto(nombre, v["nombre"], v["valor"])  # cifra con la clave pública del repositorio
			if editando:
				return api.editar_variable(nombre, v["nombre"], v["valor"])
			return api.crear_variable(nombre, v["nombre"], v["valor"])

		d.formulario_modal(
			panel, panel.ctx,
			lambda v: d.DialogoSecreto(panel, tipo, (elemento or {}).get("name", ""),
				(elemento or {}).get("value", "") if tipo == "variable" else "", editando, v),
			enviar, exito=lambda _r: _("Guardado."), al_terminar=lambda _r: panel.cargar(anunciar=False),
			inicio=_("Guardando…"))

	def borrar(panel: Any, elemento: dict) -> None:
		es_secreto = elemento.get("_tipo") == "secreto"
		if not confirmar_peligro(panel, (_("¿Borrar el secreto {n}? Los flujos que lo usen fallarán.") if es_secreto else
			_("¿Borrar la variable {n}?")).format(n=elemento.get("name", "")), _("Borrar")):
			return
		api = panel.ctx.api()
		funcion = api.borrar_secreto if es_secreto else api.borrar_variable
		en_segundo_plano(panel, panel.ctx, lambda: funcion(nombre, elemento["name"]), exito=_("Borrado."),
			al_terminar=lambda _r: panel.quitar(elemento))

	return VistaRepo(
		"repo_secretos", _("Secretos y variables de Actions"),
		[
			Columna("nombre", _("Nombre"), lambda e, c: e.get("name", ""), 240),
			Columna("tipo", _("Tipo"), lambda e, c: _("Secreto") if e.get("_tipo") == "secreto" else _("Variable"), 90),
			Columna("valor", _("Valor"), lambda e, c: _("(oculto)") if e.get("_tipo") == "secreto" else e.get("value", ""), 260),
			Columna("actualizado", _("Actualizado"), lambda e, c: f.fecha(e.get("updated_at"), c.relativas()), 120),
		],
		cargar, guardar,
		[
			Accion(_("Cambiar el &valor…"), guardar, "F2"),
			Accion(_("Nuevo &secreto o variable…"), lambda p, e: guardar(p, None), "Ctrl+N", requiere_elemento=False),
			Accion(_("&Borrar…"), borrar, "Supr"),
			Accion(_("Copiar el va&lor de la variable"), lambda p, e: copiar(p.ctx, e.get("value", ""), _("Valor copiado.")),
				disponible=lambda p, e: e.get("_tipo") == "variable"),
		],
		_("No hay secretos ni variables. Cree uno con Control+N."), paginada=False,
		url=lambda e: f"{_web(host, nombre)}/settings/secrets/actions",
	)


def vista_webhooks(nombre: str, host: str = "github.com") -> VistaRepo:
	def guardar(panel: Any, hook: dict | None) -> None:
		api = panel.ctx.api()

		def enviar(v: dict) -> Any:
			if hook is None:
				return api.crear_webhook(nombre, v["url"], v["eventos"], v["secreto"], v["tipo"], v["activo"])
			resultado = api.editar_webhook(nombre, hook["id"], events=v["eventos"], active=v["activo"])
			# La configuración (URL, tipo, secreto) tiene su propia ruta: así un secreto vacío no borra el que hay.
			configuracion = {"url": v["url"], "content_type": v["tipo"]}
			if v["secreto"]:
				configuracion["secret"] = v["secreto"]
			api.c.patch(f"{ruta_repo(nombre)}/hooks/{int(hook['id'])}/config", configuracion)
			return resultado

		d.formulario_modal(panel, panel.ctx, lambda v: d.DialogoWebhook(panel, panel.ctx.config, hook, v), enviar,
			exito=_("Webhook guardado."), al_terminar=lambda _r: panel.cargar(anunciar=False))

	def borrar(panel: Any, hook: dict) -> None:
		if not confirmar_peligro(panel, _("¿Borrar el webhook a {u}?").format(u=(hook.get("config") or {}).get("url", "")),
			_("Borrar el webhook")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_webhook(nombre, hook["id"]), exito=_("Webhook borrado."),
			al_terminar=lambda _r: panel.quitar(hook))

	def entregas(panel: Any, hook: dict) -> None:
		api = panel.ctx.api()

		def mostrar(lista: list) -> None:
			if not lista:
				mostrar_mensaje(panel, _("Este webhook no tiene entregas recientes."), _("Entregas"))
				return
			lineas = [_("{f}: {e} {a} → {s} {c} ({t} s){r}").format(
				f=f.fecha_completa(e.get("delivered_at")), e=e.get("event", ""), a=e.get("action") or "",
				s=e.get("status_code", ""), c=e.get("status", ""), t=round(float(e.get("duration") or 0), 2),
				r=_(", reenviada") if e.get("redelivery") else "") for e in lista]
			_mostrar_texto(panel, _("Entregas recientes del webhook"), _("&Entregas (la más reciente primero):"), "\n".join(lineas))

		_en_fondo(panel, lambda: api.entregas_webhook(nombre, hook["id"]), mostrar, inicio=_("Cargando las entregas…"))

	def ultima(h: dict) -> str:
		respuesta = h.get("last_response") or {}
		if not respuesta.get("code"):
			return _("sin entregas") if respuesta.get("status") in (None, "unused") else str(respuesta.get("status", ""))
		return f"{respuesta.get('code')} {respuesta.get('message') or ''}".strip()

	return VistaRepo(
		"repo_webhooks", _("Webhooks"),
		[
			Columna("url", _("URL"), lambda h, c: (h.get("config") or {}).get("url", ""), 300),
			Columna("eventos", _("Eventos"), lambda h, c: ", ".join(h.get("events") or []), 220),
			Columna("activo", _("Activo"), lambda h, c: f.si_no(h.get("active")), 60),
			Columna("ultima", _("Última respuesta"), lambda h, c: ultima(h), 140),
			Columna("tipo", _("Contenido"), lambda h, c: (h.get("config") or {}).get("content_type", ""), 80, visible=False),
		],
		lambda api, pagina, panel: api.webhooks(nombre), guardar,
		[
			Accion(_("Cam&biar el webhook…"), guardar, "F2"),
			Accion(_("Nuevo &webhook…"), lambda p, e: guardar(p, None), "Ctrl+N", requiere_elemento=False),
			Accion(_("Bo&rrar el webhook…"), borrar, "Supr"),
			Accion(_("&Probar (enviar un ping)"), lambda p, h: _hacer(p, lambda: p.ctx.api().probar_webhook(nombre, h["id"]),
				_("Prueba enviada. Mire las entregas en unos segundos.")), separador_antes=True),
			Accion(_("&Ver las entregas recientes"), entregas),
			Accion(_("Ac&tivar o desactivar"), lambda p, h: _hacer(p, lambda: p.ctx.api().editar_webhook(nombre, h["id"],
				active=not h.get("active")), _("Webhook desactivado.") if h.get("active") else _("Webhook activado."))),
		],
		_("No hay webhooks. Cree uno con Control+N."), paginada=False,
		url=lambda h: f"{_web(host, nombre)}/settings/hooks/{h.get('id', '')}",
	)


def vista_claves(nombre: str, host: str = "github.com") -> VistaRepo:
	def nueva(panel: Any, _e: Any) -> None:
		api = panel.ctx.api()
		d.formulario_modal(panel, panel.ctx, lambda v: d.DialogoClaveDespliegue(panel, v),
			lambda v: api.anadir_clave_despliegue(nombre, v["titulo"], v["clave"], not v["escritura"]),
			exito=_("Clave añadida."), al_terminar=lambda _r: panel.cargar(anunciar=False))

	def borrar(panel: Any, clave: dict) -> None:
		if not confirmar_peligro(panel, _("¿Borrar la clave «{t}»? Lo que la use dejará de tener acceso.").format(
			t=clave.get("title", "")), _("Borrar la clave")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_clave_despliegue(nombre, clave["id"]), exito=_("Clave borrada."),
			al_terminar=lambda _r: panel.quitar(clave))

	return VistaRepo(
		"repo_claves", _("Claves de despliegue"),
		[
			Columna("titulo", _("Título"), lambda k, c: k.get("title", ""), 220),
			Columna("permiso", _("Permiso"), lambda k, c: _("Solo lectura") if k.get("read_only") else _("Lectura y escritura"), 140),
			Columna("creada", _("Creada"), lambda k, c: f.fecha(k.get("created_at"), c.relativas()), 110),
			Columna("uso", _("Último uso"), lambda k, c: f.fecha(k.get("last_used"), c.relativas()) or _("nunca"), 110),
			Columna("clave", _("Clave"), lambda k, c: f.resumen_texto(k.get("key"), 60), 260, visible=False),
		],
		lambda api, pagina, panel: api.claves_despliegue(nombre), None,
		[
			Accion(_("Nueva &clave…"), nueva, "Ctrl+N", requiere_elemento=False),
			Accion(_("&Borrar la clave…"), borrar, "Supr"),
			Accion(_("Copiar la clave &pública"), lambda p, k: copiar(p.ctx, k.get("key", ""), _("Clave copiada."))),
		],
		_("No hay claves de despliegue. Añada una con Control+N."), paginada=False,
		url=lambda k: f"{_web(host, nombre)}/settings/keys",
	)


APLICACION_REGLAS = {"active": "Activa", "disabled": "Desactivada", "evaluate": "Solo evaluación"}


def vista_reglas(nombre: str, host: str = "github.com") -> VistaRepo:
	def cargar(api: Any, pagina: int, panel: Any) -> list:
		filas = [dict(r, _tipo="conjunto") for r in api.reglas(nombre) or [] if isinstance(r, dict)]
		try:
			protegidas = _lista(api.ramas(nombre, 1, protegidas=True))
		except Exception:  # noqa: BLE001 - sin permiso de administración se muestran al menos los conjuntos
			log.warning("No se pudieron cargar las ramas protegidas de %s", nombre, exc_info=True)
			protegidas = []
		filas += [{"_tipo": "proteccion", "name": r.get("name", ""), "target": "branch", "enforcement": "active"}
			for r in protegidas if isinstance(r, dict)]
		return filas

	def ver(panel: Any, regla: dict) -> None:
		api = panel.ctx.api()
		if regla["_tipo"] == "conjunto":
			obtener: Callable[[], Any] = lambda: api.regla(nombre, regla["id"])
		else:
			obtener = lambda: api.proteccion(nombre, regla["name"])
		_en_fondo(panel, obtener, lambda datos: _mostrar_texto(panel, _("Regla {n}").format(n=regla.get("name", "")),
			_("&Detalle de la regla:"), json_legible(datos) or _("(sin datos)")), inicio=_("Cargando la regla…"))

	def borrar(panel: Any, regla: dict) -> None:
		if not confirmar_peligro(panel, _("¿Borrar la regla «{n}»?").format(n=regla.get("name", "")), _("Borrar la regla")):
			return
		api = panel.ctx.api()
		if regla["_tipo"] == "conjunto":
			trabajo: Callable[[], Any] = lambda: api.borrar_regla(nombre, regla["id"])
		else:
			trabajo = lambda: api.desproteger(nombre, regla["name"])
		en_segundo_plano(panel, panel.ctx, trabajo, exito=_("Regla borrada."), al_terminar=lambda _r: panel.quitar(regla))

	def proteger(panel: Any, _e: Any) -> None:
		_elegir_rama(panel, _("Proteger una rama"), _("&Rama:"), lambda rama: proteger_rama(panel, rama))

	return VistaRepo(
		"repo_reglas", _("Reglas y protección de ramas"),
		[
			Columna("nombre", _("Nombre"), lambda r, c: r.get("name", ""), 240),
			Columna("tipo", _("Tipo"), lambda r, c: _("Conjunto de reglas") if r.get("_tipo") == "conjunto" else _("Protección de rama"), 150),
			Columna("objetivo", _("Se aplica a"), lambda r, c: {"branch": _("ramas"), "tag": _("etiquetas"), "push": _("envíos")}.get(
				r.get("target", ""), r.get("target", "")), 100),
			Columna("aplicacion", _("Aplicación"), lambda r, c: _(APLICACION_REGLAS.get(r.get("enforcement", ""), r.get("enforcement", ""))), 120),
		],
		cargar, ver,
		[
			Accion(_("&Ver el detalle"), ver, "Intro"),
			Accion(_("&Proteger una rama…"), proteger, "Ctrl+N", requiere_elemento=False),
			Accion(_("&Borrar la regla…"), borrar, "Supr"),
		],
		_("No hay reglas ni ramas protegidas. Proteja una con Control+N."), paginada=False,
		url=lambda r: f"{_web(host, nombre)}/settings/rules/{r['id']}" if r.get("_tipo") == "conjunto" else
			f"{_web(host, nombre)}/settings/branches",
	)


def vista_despliegues(nombre: str, host: str = "github.com") -> VistaRepo:
	def estados(panel: Any, despliegue: dict) -> None:
		api = panel.ctx.api()

		def mostrar(lista: list) -> None:
			if not lista:
				mostrar_mensaje(panel, _("Este despliegue no tiene estados."), _("Estados del despliegue"))
				return
			lineas = []
			for e in lista:
				linea = _("{f}: {s}").format(f=f.fecha_completa(e.get("created_at")), s=f.estado(e.get("state")))
				if e.get("description"):
					linea += f". {e['description']}"
				if e.get("environment_url"):
					linea += _(". Dirección: {u}").format(u=e["environment_url"])
				lineas.append(linea)
			_mostrar_texto(panel, _("Estados del despliegue"), _("&Estados (el más reciente primero):"), "\n".join(lineas))

		_en_fondo(panel, lambda: api.estados_despliegue(nombre, despliegue["id"]), mostrar, inicio=_("Cargando los estados…"))

	def borrar(panel: Any, despliegue: dict) -> None:
		if not confirmar_peligro(panel, _("¿Borrar el despliegue a {e}? GitHub solo deja borrar los inactivos.").format(
			e=despliegue.get("environment", "")), _("Borrar el despliegue")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_despliegue(nombre, despliegue["id"]), exito=_("Despliegue borrado."),
			al_terminar=lambda _r: panel.quitar(despliegue))

	return VistaRepo(
		"repo_despliegues", _("Despliegues"),
		[
			Columna("entorno", _("Entorno"), lambda x, c: x.get("environment", ""), 160),
			Columna("ref", _("Rama o etiqueta"), lambda x, c: x.get("ref", ""), 140),
			Columna("sha", _("Commit"), lambda x, c: (x.get("sha") or "")[:7], 80),
			Columna("autor", _("Creado por"), lambda x, c: f.login(x.get("creator")), 120),
			Columna("fecha", _("Fecha"), lambda x, c: f.fecha(x.get("created_at"), c.relativas()), 120),
			Columna("descripcion", _("Descripción"), lambda x, c: x.get("description") or "", 220, visible=False),
		],
		lambda api, pagina, panel: api.despliegues(nombre, pagina), estados,
		[
			Accion(_("&Ver los estados"), estados, "Intro"),
			Accion(_("&Borrar el despliegue…"), borrar, "Supr"),
		],
		_("No hay despliegues."), url=lambda x: f"{_web(host, nombre)}/deployments",
	)


def vista_wiki(nombre: str, host: str = "github.com") -> VistaRepo:
	"""La wiki vive en su propio módulo (usa git, no la API); se importa al abrir la sección."""
	from app.ui.repositorio.wiki import crear_vista_wiki

	return crear_vista_wiki(nombre, host)


#: Fábrica de cada sección de lista: ``(nombre, host) -> VistaRepo``.
VISTAS: dict[str, Callable[..., VistaRepo]] = {
	"codigo": vista_codigo,
	"issues": vista_issues,
	"prs": vista_prs,
	"discusiones": vista_discusiones,
	"acciones": vista_acciones,
	"releases": vista_releases,
	"ramas": vista_ramas,
	"etiquetas": vista_etiquetas,
	"commits": vista_commits,
	"proyectos": vista_proyectos,
	"wiki": vista_wiki,
	"hitos": vista_hitos,
	"labels": vista_labels,
	"colaboradores": vista_colaboradores,
	"bifurcaciones": vista_bifurcaciones,
	"observadores": vista_observadores,
	"seguridad": vista_seguridad,
	"entornos": vista_entornos,
	"secretos": vista_secretos,
	"webhooks": vista_webhooks,
	"claves": vista_claves,
	"reglas": vista_reglas,
	"despliegues": vista_despliegues,
}


