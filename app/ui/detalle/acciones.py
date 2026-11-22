"""GitHub Actions: ventana de una ejecución y lanzamiento manual de flujos.

Ventana de una ejecución (``abrir_ejecucion``):

- «Información»: flujo, título, estado en español, evento, rama, commit, actor,
  intento, inicio y duración.
- «Trabajos» y «Pasos»: al enfocar un trabajo se ven sus pasos y se carga su
  registro; Intro en un trabajo lleva al registro; Intro en un paso coloca el
  cursor del registro en su grupo («▸ nombre del paso»).
- «Registro del trabajo»: texto limpio (sin códigos de color ni marcas de
  tiempo, que se pueden mostrar con una casilla). F8 / Mayús+F8 saltan a la
  siguiente / anterior línea con «ERROR:» o «AVISO:» y la leen; Ctrl+F busca,
  F3 / Mayús+F3 repiten la búsqueda.
- «Anotaciones» de los check runs (archivo:línea y mensaje) y «Artefactos»
  (Intro descarga con progreso por hitos; Supr borra).
- «Seguir en vivo»: cada 10 segundos mientras la ejecución está en curso;
  anuncia los cambios de estado de los trabajos y suena al terminar.

Lanzar un flujo (``lanzar_flujo``): lee su YAML y saca las entradas de
``on.workflow_dispatch.inputs`` con un analizador YAML mínimo propio (sin
dependencias externas) para ofrecer un control por entrada.
"""

from __future__ import annotations

import builtins
import json
import logging
import re
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import wx

from app.core.descargas import nombre_seguro
from app.services import formato as f
from app.services.github.api import ruta_repo
from app.services.github.api_extra import limpiar_registro
from app.ui.accesibilidad.dialogos import crear_botonera, elegir_opcion, preparar_dialogo
from app.ui.accesibilidad.foco import enfocar
from app.ui.comunes import (
	confirmar_peligro,
	copiar,
	elegir_uno,
	elegir_varios,
	en_segundo_plano,
	mostrar_error,
	mostrar_mensaje,
	pedir_texto,
)
from app.ui.detalle.comun_detalle import VentanaDetalle, carpeta_de_descargas, duracion_entre, entrada_cerrar

log = logging.getLogger(__name__)

INTERVALO_VIVO_MS = 10_000


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ════════════════════════════════════════════════════════════════════════════
# Analizador YAML mínimo (solo lo necesario para «on:» de un flujo)
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class EntradaFlujo:
	"""Una entrada de ``workflow_dispatch``.

	:param tipo: ``string``, ``choice``, ``boolean``, ``environment`` o ``number``.
	"""

	nombre: str
	descripcion: str = ""
	requerida: bool = False
	defecto: str = ""
	tipo: str = "string"
	opciones: list[str] = field(default_factory=list)


def _sangria(linea: str) -> int:
	return len(linea) - len(linea.lstrip(" "))


def _quitar_comentario(texto: str) -> str:
	"""Quita un comentario «# ...» que no esté dentro de comillas."""
	simple = doble = False
	for posicion, caracter in enumerate(texto):
		if caracter == "'" and not doble:
			simple = not simple
		elif caracter == '"' and not simple and (posicion == 0 or texto[posicion - 1] != "\\"):
			doble = not doble
		elif caracter == "#" and not simple and not doble and (posicion == 0 or texto[posicion - 1] in " \t"):
			return texto[:posicion].rstrip()
	return texto.rstrip()


def _partir_flujo(texto: str) -> list[str]:
	"""Parte «a, 'b, c', [d]» por las comas de primer nivel."""
	partes, actual, nivel = [], [], 0
	simple = doble = False
	for caracter in texto:
		if caracter == "'" and not doble:
			simple = not simple
		elif caracter == '"' and not simple:
			doble = not doble
		elif not simple and not doble:
			if caracter in "[{":
				nivel += 1
			elif caracter in "]}":
				nivel -= 1
			elif caracter == "," and nivel == 0:
				partes.append("".join(actual))
				actual = []
				continue
		actual.append(caracter)
	if "".join(actual).strip():
		partes.append("".join(actual))
	return [p.strip() for p in partes if p.strip()]


def _partir_clave(texto: str) -> tuple[str, str] | None:
	"""«clave: valor» → (clave, valor). ``None`` si la línea no es una clave."""
	simple = doble = False
	for posicion, caracter in enumerate(texto):
		if caracter == "'" and not doble:
			simple = not simple
		elif caracter == '"' and not simple:
			doble = not doble
		elif caracter == ":" and not simple and not doble and (posicion + 1 == len(texto) or texto[posicion + 1] in " \t"):
			clave = texto[:posicion].strip()
			if len(clave) >= 2 and clave[0] == clave[-1] and clave[0] in "'\"":
				clave = clave[1:-1]
			return clave, texto[posicion + 1:].strip()
	return None


def _escalar(texto: str) -> Any:
	"""Valor escalar o de flujo («[a, b]», «{a: 1}») de YAML."""
	texto = texto.strip()
	if texto.startswith("&"):  # ancla: «&nombre valor»
		texto = texto.partition(" ")[2].strip()
	if not texto:
		return None
	if len(texto) >= 2 and texto[0] == '"' and texto[-1] == '"':
		try:
			return json.loads(texto)
		except ValueError:
			return texto[1:-1]
	if len(texto) >= 2 and texto[0] == "'" and texto[-1] == "'":
		return texto[1:-1].replace("''", "'")
	if texto.startswith("[") and texto.endswith("]"):
		return [_escalar(p) for p in _partir_flujo(texto[1:-1])]
	if texto.startswith("{") and texto.endswith("}"):
		resultado = {}
		for parte in _partir_flujo(texto[1:-1]):
			par = _partir_clave(parte) or (parte.strip(), "")
			resultado[par[0]] = _escalar(par[1])
		return resultado
	minusculas = texto.lower()
	if minusculas == "true":
		return True
	if minusculas == "false":
		return False
	if minusculas in ("null", "~"):
		return None
	if re.fullmatch(r"[-+]?\d+", texto):
		return int(texto)
	if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?", texto):
		return float(texto)
	return texto


class _LectorYaml:
	"""Bloques por sangría: mapas, secuencias, escalares y bloques literales «|» y «>»."""

	def __init__(self, lineas: list[str]) -> None:
		self.lineas = lineas
		self.i = 0

	def _util(self) -> int | None:
		"""Salta líneas en blanco y comentarios; devuelve el índice de la siguiente útil."""
		while self.i < len(self.lineas):
			texto = self.lineas[self.i].strip()
			if texto and not texto.startswith("#"):
				return self.i
			self.i += 1
		return None

	def bloque(self, sangria_minima: int) -> Any:
		indice = self._util()
		if indice is None or _sangria(self.lineas[indice]) < sangria_minima:
			return None
		sangria = _sangria(self.lineas[indice])
		texto = self.lineas[indice].strip()
		if texto == "-" or texto.startswith("- "):
			return self._secuencia(sangria)
		return self._mapa(sangria)

	def _mapa(self, sangria: int) -> dict:
		resultado: dict = {}
		while True:
			indice = self._util()
			if indice is None:
				break
			linea = self.lineas[indice]
			propia = _sangria(linea)
			if propia < sangria:
				break
			texto = _quitar_comentario(linea.strip())
			if propia > sangria or texto == "-" or texto.startswith("- "):
				if propia == sangria:
					break  # secuencia al mismo nivel: pertenece al padre
				self.i = indice + 1  # línea suelta que no se entiende: se ignora
				continue
			par = _partir_clave(texto)
			self.i = indice + 1
			if par is None:
				continue
			clave, resto = par
			resultado[clave] = self._valor(resto, sangria)
		return resultado

	def _valor(self, resto: str, sangria: int) -> Any:
		if re.fullmatch(r"[|>][-+]?\d*[-+]?", resto):
			return self._literal(sangria, plegado=resto.startswith(">"))
		if resto and not resto.startswith("&"):
			return _escalar(resto)
		indice = self._util()
		if indice is None:
			return None
		propia = _sangria(self.lineas[indice])
		texto = self.lineas[indice].strip()
		if propia > sangria:
			return self.bloque(propia)
		if propia == sangria and (texto == "-" or texto.startswith("- ")):
			return self._secuencia(sangria)
		return None

	def _secuencia(self, sangria: int) -> list:
		elementos: list = []
		while True:
			indice = self._util()
			if indice is None:
				break
			linea = self.lineas[indice]
			texto = linea.strip()
			if _sangria(linea) != sangria or not (texto == "-" or texto.startswith("- ")):
				break
			contenido = _quitar_comentario(texto[1:].strip())
			if not contenido:
				self.i = indice + 1
				elementos.append(self.bloque(sangria + 1))
				continue
			if _partir_clave(contenido) is not None and not contenido.startswith(("'", '"', "[", "{")):
				# «- clave: valor» abre un mapa cuyo nivel es la columna del contenido.
				columna = sangria + 1 + (len(texto[1:]) - len(texto[1:].lstrip()))
				self.lineas[indice] = " " * columna + texto[1:].lstrip()
				self.i = indice
				elementos.append(self._mapa(columna))
				continue
			self.i = indice + 1
			elementos.append(_escalar(contenido))
		return elementos

	def _literal(self, sangria: int, plegado: bool) -> str:
		lineas: list[str] = []
		propia: int | None = None
		while self.i < len(self.lineas):
			linea = self.lineas[self.i]
			if not linea.strip():
				lineas.append("")
				self.i += 1
				continue
			actual = _sangria(linea)
			if actual <= sangria:
				break
			if propia is None:
				propia = actual
			lineas.append(linea[propia:] if actual >= propia else linea.strip())
			self.i += 1
		while lineas and not lineas[-1]:
			lineas.pop()
		if not plegado:
			return "\n".join(lineas)
		parrafos, actual_parrafo = [], []
		for linea in lineas:
			if linea:
				actual_parrafo.append(linea.strip())
			else:
				parrafos.append(" ".join(actual_parrafo))
				actual_parrafo = []
		parrafos.append(" ".join(actual_parrafo))
		return "\n".join(parrafos)


def analizar_yaml(texto: str) -> Any:
	"""Analiza un subconjunto de YAML (mapas, listas, escalares, bloques «|» y «>»).

	No es un analizador completo: basta para leer la sección «on:» de un flujo.
	"""
	lineas = [linea.replace("\t", "  ") for linea in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
	lineas = [linea for linea in lineas if linea.strip() not in ("---", "...")]
	return _LectorYaml(lineas).bloque(0)


_CLAVE_ON = re.compile(r"""^(?:on|"on"|'on'|true)\s*:(.*)$""")


def _seccion_on(texto: str) -> Any:
	"""Valor de la clave raíz «on» (sin analizar el resto del archivo, que puede ser enorme)."""
	lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
	for indice, linea in enumerate(lineas):
		coincidencia = _CLAVE_ON.match(linea)
		if not coincidencia:
			continue
		bloque = [linea]
		for siguiente in lineas[indice + 1:]:
			if siguiente.strip() and not siguiente.startswith((" ", "\t")) and not siguiente.lstrip().startswith("#"):
				break
			bloque.append(siguiente)
		datos = analizar_yaml("\n".join(["on_:" + coincidencia.group(1)] + bloque[1:]))
		return (datos or {}).get("on_") if isinstance(datos, dict) else None
	return None


def analizar_dispatch(texto_yaml: str) -> tuple[bool, list[EntradaFlujo]]:
	"""¿Se puede lanzar a mano (``workflow_dispatch``)? y sus entradas, en orden."""
	seccion = _seccion_on(texto_yaml)
	if isinstance(seccion, str):
		return seccion == "workflow_dispatch", []
	if isinstance(seccion, list):
		return "workflow_dispatch" in seccion, []
	if not isinstance(seccion, dict) or "workflow_dispatch" not in seccion:
		return False, []
	dispatch = seccion.get("workflow_dispatch")
	entradas_yaml = dispatch.get("inputs") if isinstance(dispatch, dict) else None
	entradas: list[EntradaFlujo] = []
	for nombre, datos in (entradas_yaml or {}).items() if isinstance(entradas_yaml, dict) else ():
		datos = datos if isinstance(datos, dict) else {}
		tipo = str(datos.get("type") or "string").lower()
		defecto = datos.get("default")
		if isinstance(defecto, bool):
			defecto = "true" if defecto else "false"
		opciones = datos.get("options") or []
		if not isinstance(opciones, list):
			opciones = [opciones]
		entradas.append(EntradaFlujo(
			nombre=str(nombre),
			descripcion=str(datos.get("description") or "").strip(),
			requerida=datos.get("required") is True or str(datos.get("required")).lower() == "true",
			defecto="" if defecto is None else str(defecto),
			tipo=tipo,
			opciones=[str(o) for o in opciones if o is not None],
		))
	return True, entradas


def entradas_workflow_dispatch(texto_yaml: str) -> list[EntradaFlujo]:
	"""Solo las entradas de ``on.workflow_dispatch.inputs``."""
	return analizar_dispatch(texto_yaml)[1]


def asignar_letras(textos: list[str], ocupadas: set[str] | frozenset[str] = frozenset()) -> list[str]:
	"""Pone una letra de acceso (``&``) distinta a cada texto, sin usar las ``ocupadas``."""
	usadas = {c.lower() for c in ocupadas}
	resultado = []
	for texto in textos:
		escapado = texto.replace("&", "&&")
		posicion = next((i for i, c in enumerate(escapado) if c != "&" and c.isascii() and c.isalnum() and c.lower() not in usadas), None)
		if posicion is not None:
			usadas.add(escapado[posicion].lower())
			resultado.append(escapado[:posicion] + "&" + escapado[posicion:])
			continue
		libre = next((c for c in "abcdefghijklmnopqrstuvwxyz0123456789" if c not in usadas), None)
		if libre is None:
			resultado.append(escapado)
		else:
			usadas.add(libre)
			resultado.append(f"&{libre.upper()}. {escapado}")
	return resultado


# ════════════════════════════════════════════════════════════════════════════
# Funciones puras de la ventana de ejecución
# ════════════════════════════════════════════════════════════════════════════

EVENTOS = {
	"push": N_("envío (push)"), "pull_request": N_("pull request"), "pull_request_target": N_("pull request (destino)"),
	"workflow_dispatch": N_("lanzado a mano"), "schedule": N_("programado"), "release": N_("release"),
	"workflow_run": N_("al terminar otro flujo"), "repository_dispatch": N_("evento externo"), "merge_group": N_("cola de fusión"),
	"issues": N_("issue"), "issue_comment": N_("comentario de issue"), "dynamic": N_("dinámico"),
}

NIVELES_ANOTACION = {"failure": N_("Error"), "warning": N_("Aviso"), "notice": N_("Nota")}


def texto_informacion(ejecucion: dict) -> str:
	"""Resumen legible de una ejecución, una línea por dato."""
	commit = ejecucion.get("head_commit") or {}
	terminada = ejecucion.get("status") == "completed"
	inicio = ejecucion.get("run_started_at") or ejecucion.get("created_at")
	duracion = duracion_entre(inicio, ejecucion.get("updated_at") if terminada else None)
	actor = f.login(ejecucion.get("actor"))
	lanzador = f.login(ejecucion.get("triggering_actor")) if ejecucion.get("triggering_actor") else actor
	evento = ejecucion.get("event") or ""
	lineas = [
		_("Flujo: {n}").format(n=ejecucion.get("name") or ""),
		_("Título: {t}").format(t=ejecucion.get("display_title") or f.primera_linea(commit.get("message")) or "-"),
		_("Estado: {e}").format(e=f.estado_ejecucion(ejecucion)),
		_("Evento: {e}").format(e=_(EVENTOS.get(evento, evento))),
		_("Rama: {r}").format(r=ejecucion.get("head_branch") or "-"),
		_("Commit: {s} {m}").format(s=(ejecucion.get("head_sha") or "")[:7], m=f.primera_linea(commit.get("message"))).rstrip(),
		_("Actor: {a}").format(a=actor) + ("" if lanzador == actor else _(" (lanzada por {l})").format(l=lanzador)),
		_("Ejecución número {n}, intento {i}").format(n=ejecucion.get("run_number", ""), i=ejecucion.get("run_attempt", 1)),
		_("Inicio: {f}").format(f=f.fecha_completa(inicio)),
		_("Duración: {d}").format(d=duracion or "-") + ("" if terminada else _(" (sigue en curso)")),
		_("Archivo del flujo: {p}").format(p=ejecucion.get("path") or "-"),
		_("Enlace: {u}").format(u=ejecucion.get("html_url") or ""),
	]
	return "\n".join(lineas)


def fila_trabajo(trabajo: dict) -> list[str]:
	terminado = trabajo.get("status") == "completed"
	duracion = duracion_entre(trabajo.get("started_at"), trabajo.get("completed_at") if terminado else None) \
		if trabajo.get("status") not in ("queued", "waiting", "pending") else ""
	return [trabajo.get("name", ""), f.estado_ejecucion(trabajo), duracion]


def fila_paso(paso: dict) -> list[str]:
	terminado = paso.get("status") == "completed"
	duracion = duracion_entre(paso.get("started_at"), paso.get("completed_at") if terminado else None) \
		if paso.get("started_at") else ""
	return [str(paso.get("number", "")), paso.get("name", ""), f.estado_ejecucion(paso), duracion]


def cambios_de_estado(anteriores: list[dict], nuevos: list[dict]) -> list[str]:
	"""Frases con los trabajos que han cambiado de estado («build: En curso → Correcto»)."""
	previos = {t.get("id"): f.estado_ejecucion(t) for t in anteriores}
	frases = []
	for trabajo in nuevos:
		estado = f.estado_ejecucion(trabajo)
		nombre = trabajo.get("name", "")
		if trabajo.get("id") not in previos:
			frases.append(_("Nuevo trabajo {n}: {e}.").format(n=nombre, e=estado))
		elif previos[trabajo.get("id")] != estado:
			frases.append(_("{n}: {a} → {e}.").format(n=nombre, a=previos[trabajo.get("id")], e=estado))
	return frases


def es_linea_marcada(linea: str) -> bool:
	"""Línea de error o de aviso del registro (tras ``limpiar_registro``)."""
	# Las mismas marcas traducidas que pone limpiar_registro.
	return _("ERROR: ").strip() in linea or _("AVISO: ").strip() in linea


def siguiente_marca(lineas: list[str], actual: int, atras: bool = False) -> int | None:
	"""Índice de la siguiente (o anterior) línea con «ERROR:» o «AVISO:»."""
	rango = range(actual - 1, -1, -1) if atras else range(actual + 1, len(lineas))
	return next((i for i in rango if es_linea_marcada(lineas[i])), None)


def buscar_linea(lineas: list[str], texto: str, actual: int, atras: bool = False) -> tuple[int, int, bool] | None:
	"""Busca ``texto`` (sin distinguir mayúsculas) desde la línea siguiente, dando la vuelta.

	Devuelve (línea, columna, ha_dado_la_vuelta) o ``None``.
	"""
	buscado = texto.casefold()
	total = len(lineas)
	if not buscado or not total:
		return None
	for paso in range(1, total + 1):
		indice = (actual - paso) % total if atras else (actual + paso) % total
		columna = lineas[indice].casefold().find(buscado)
		if columna >= 0:
			vuelta = indice >= actual if atras else indice <= actual
			return indice, columna, vuelta
	return None


def linea_de_paso(limpias: list[str], crudas: list[str], paso: dict) -> int | None:
	"""Línea del registro donde empieza un paso.

	1. Grupo con el nombre exacto («▸ nombre»).
	2. Primera línea con marca de tiempo igual o posterior al inicio del paso
	   (prefiriendo un grupo en las líneas siguientes).
	3. Grupo que contiene el nombre.
	"""
	nombre = (paso.get("name") or "").strip()
	for indice, linea in enumerate(limpias):
		posicion = linea.find("▸ ")
		if posicion >= 0 and nombre and linea[posicion + 2:].strip() == nombre:
			return indice
	inicio = (paso.get("started_at") or "")[:19]
	if inicio:
		for indice, cruda in enumerate(crudas):
			marca = cruda.lstrip("﻿")[:19]
			if len(marca) == 19 and marca[4] == "-" and marca[10] == "T" and marca >= inicio:
				for candidata in range(indice, min(indice + 5, len(limpias))):
					if "▸ " in limpias[candidata]:
						return candidata
				return min(indice, len(limpias) - 1) if limpias else None
	for indice, linea in enumerate(limpias):
		if "▸ " in linea and nombre and nombre in linea:
			return indice
	return None


# ════════════════════════════════════════════════════════════════════════════
# Ventana de una ejecución
# ════════════════════════════════════════════════════════════════════════════


class VentanaEjecucion(VentanaDetalle):
	"""Una ejecución de Actions con sus trabajos, pasos, registro, anotaciones y artefactos."""

	def __init__(self, ctx: Any, padre: wx.Window | None, nombre: str, id_ejecucion: int) -> None:
		super().__init__(padre, ctx, _("Ejecución {i} de {n}").format(i=id_ejecucion, n=nombre),
			clave=f"ejecucion:{nombre}:{int(id_ejecucion)}", tamano=(1100, 820))
		self.nombre = nombre
		self.id_ejecucion = int(id_ejecucion)
		self.ejecucion: dict = {}
		self.trabajos: list[dict] = []
		self.anotaciones: list[dict] = []
		self.artefactos: list[dict] = []
		self.registros: dict[int, str] = {}
		self.id_registro: int | None = None
		self.crudo = ""
		self.lineas: list[str] = []
		self.lineas_crudas: list[str] = []
		self.buscado = ""
		self.cargada = False
		self._sondeando = False
		self._carga_pendiente: wx.CallLater | None = None
		self.temporizador = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, self._al_temporizador, self.temporizador)
		self._construir()

	# ── Construcción ──────────────────────────────────────────────────────────

	def _construir(self) -> None:
		self.info = self.crear_texto(_("&Información:"), alto=120,
			ayuda=_("Datos de la ejecución: flujo, estado, evento, rama, commit, actor y duración."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		izquierda, derecha = wx.BoxSizer(wx.VERTICAL), wx.BoxSizer(wx.VERTICAL)
		self.lista_trabajos = self.crear_lista(_("&Trabajos:"), _("Trabajos"),
			[(_("Nombre"), 260), (_("Estado"), 110), (_("Duración"), 100)], sizer=izquierda,
			ayuda=_("Al moverse por los trabajos se muestran sus pasos y su registro. Intro lleva al registro."))
		self.lista_pasos = self.crear_lista(_("&Pasos:"), _("Pasos"),
			[(_("Número"), 60), (_("Nombre"), 280), (_("Estado"), 110), (_("Duración"), 100)], sizer=derecha,
			ayuda=_("Intro coloca el cursor del registro en el principio de este paso."))
		fila.Add(izquierda, 1, wx.EXPAND)
		fila.Add(derecha, 1, wx.EXPAND)
		self.raiz.Add(fila, 1, wx.EXPAND)
		self.registro = self.crear_texto(_("&Registro del trabajo:"), alto=240, proporcion=2, sin_ajuste=True, ayuda=_(
			"Registro del trabajo elegido, sin códigos de color. F8 y Mayúsculas+F8: siguiente y anterior error o aviso. "
			"Control+F: buscar. F3 y Mayúsculas+F3: buscar siguiente y anterior."))
		opciones = wx.BoxSizer(wx.HORIZONTAL)
		self.casilla_horas = wx.CheckBox(self.panel, label=_("&Mostrar las marcas de tiempo del registro"))
		self.casilla_horas.SetValue(bool(self.ctx.config.obtener("acciones.mostrar_horas", False)))
		self.casilla_horas.SetHelpText(_("Muestra al principio de cada línea del registro la hora en que se escribió."))
		self.casilla_horas.Bind(wx.EVT_CHECKBOX, lambda _e: self._rehacer_registro())
		opciones.Add(self.casilla_horas, 0, wx.ALL, 4)
		self.casilla_vivo = wx.CheckBox(self.panel, label=_("Seguir en &vivo (cada 10 segundos)"))
		self.casilla_vivo.SetHelpText(_("Mientras la ejecución esté en curso, comprueba su estado cada 10 segundos, "
			"anuncia los cambios de los trabajos y suena al terminar."))
		self.casilla_vivo.Bind(wx.EVT_CHECKBOX, lambda _e: self.seguir_en_vivo(self.casilla_vivo.GetValue()))
		opciones.Add(self.casilla_vivo, 0, wx.ALL, 4)
		self.raiz.Add(opciones, 0)
		abajo = wx.BoxSizer(wx.HORIZONTAL)
		col_notas, col_artefactos = wx.BoxSizer(wx.VERTICAL), wx.BoxSizer(wx.VERTICAL)
		self.lista_anotaciones = self.crear_lista(_("A&notaciones:"), _("Anotaciones"),
			[(_("Nivel"), 70), (_("Ubicación"), 220), (_("Mensaje"), 360), (_("Trabajo"), 140)], sizer=col_notas,
			ayuda=_("Errores y avisos que los trabajos han marcado en archivos. Intro muestra el mensaje completo."))
		self.lista_artefactos = self.crear_lista(_("Arte&factos:"), _("Artefactos"),
			[(_("Nombre"), 220), (_("Tamaño"), 90), (_("Caduca"), 120), (_("Estado"), 90)], sizer=col_artefactos,
			ayuda=_("Archivos que ha guardado la ejecución. Intro descarga; Supr borra."))
		abajo.Add(col_notas, 3, wx.EXPAND)
		abajo.Add(col_artefactos, 2, wx.EXPAND)
		self.raiz.Add(abajo, 1, wx.EXPAND)

		self.lista_trabajos.Bind(wx.EVT_LIST_ITEM_FOCUSED, self._al_enfocar_trabajo)
		self.lista_pasos.Bind(wx.EVT_LIST_ITEM_FOCUSED, self._al_enfocar_paso)
		self.teclas_de_lista(self.lista_trabajos, {}, al_activar=self.ir_al_registro)
		self.teclas_de_lista(self.lista_pasos, {}, al_activar=lambda: self.ir_al_paso(anunciar=True))
		self.teclas_de_lista(self.lista_anotaciones, {}, al_activar=self.ver_anotacion)
		self.teclas_de_lista(self.lista_artefactos, {"Supr": self.borrar_artefacto, "Shift+Intro": lambda: self.descargar_artefacto(True)},
			al_activar=self.descargar_artefacto)
		self.menu_contextual(self.lista_trabajos, lambda: [
			(_("Ver el &registro\tIntro"), self.ir_al_registro),
			(_("&Volver a ejecutar este trabajo"), self.volver_a_ejecutar_trabajo),
			(_("Volver a &cargar el registro"), lambda: self.recargar_registro()),
		])
		self.menu_contextual(self.lista_pasos, lambda: [(_("&Ir al paso en el registro\tIntro"), lambda: self.ir_al_paso(True))])
		self.menu_contextual(self.lista_anotaciones, lambda: [(_("&Ver el mensaje completo\tIntro"), self.ver_anotacion)])
		self.menu_contextual(self.lista_artefactos, self._entradas_artefactos)
		self.poner_menus([
			(_("&Ejecución"), [
				(_("&Actualizar\tF5"), lambda: self.cargar()),
				None,
				(_("Volver a ejecutar &todo\tCtrl+R"), lambda: self.volver_a_ejecutar()),
				(_("Volver a ejecutar solo &los fallidos\tCtrl+Shift+R"), lambda: self.volver_a_ejecutar(solo_fallidos=True)),
				(_("Volver a ejecutar con &depuración"), lambda: self.volver_a_ejecutar(depuracion=True)),
				(_("Volver a ejecutar el t&rabajo elegido"), self.volver_a_ejecutar_trabajo),
				None,
				(_("&Cancelar la ejecución"), lambda: self.cancelar()),
				(_("Cancelar a la &fuerza"), lambda: self.cancelar(forzar=True)),
				(_("A&probar la ejecución pendiente"), self.aprobar),
				(_("Re&visar los despliegues pendientes…"), self.revisar_despliegues),
				(_("Avisar&me cuando termine, aunque cierre la ventana"), self.vigilar_en_segundo_plano),
				None,
				(_("&Borrar la ejecución…"), self.borrar),
				(_("Borrar los re&gistros…"), self.borrar_registros),
				(_("Descargar todos los registros (&zip)…"), self.descargar_registros),
				None,
				(_("Abrir en el &navegador\tCtrl+B"), self.abrir_navegador),
				(_("C&opiar el enlace\tCtrl+Shift+C"), self.copiar_enlace),
				entrada_cerrar(self),
			]),
			(_("Re&gistro"), [
				(_("Siguiente &error o aviso\tF8"), lambda: self.saltar_marca()),
				(_("E&rror o aviso anterior\tShift+F8"), lambda: self.saltar_marca(atras=True)),
				(_("&Buscar en el registro…\tCtrl+F"), self.buscar),
				(_("Buscar &siguiente\tF3"), lambda: self.buscar_siguiente()),
				(_("Buscar &anterior\tShift+F3"), lambda: self.buscar_siguiente(atras=True)),
				None,
				(_("Ir al &paso elegido"), lambda: self.ir_al_paso(True)),
				(_("&Mostrar u ocultar las marcas de tiempo"), self._alternar_horas),
				(_("&Volver a cargar el registro"), lambda: self.recargar_registro()),
			]),
			(_("&Artefactos"), self._entradas_artefactos()),
		])

	def _entradas_artefactos(self) -> list:
		return [
			(_("&Descargar el artefacto (Intro)"), self.descargar_artefacto),
			(_("Descargar en &otra carpeta… (Mayús+Intro)"), lambda: self.descargar_artefacto(True)),
			(_("Descargar &todos los artefactos"), self.descargar_todos_los_artefactos),
			(_("&Borrar el artefacto… (Supr)"), self.borrar_artefacto),
		]

	def al_cerrar(self) -> None:
		if self.temporizador.IsRunning():
			self.temporizador.Stop()
		if self._carga_pendiente is not None and self._carga_pendiente.IsRunning():
			self._carga_pendiente.Stop()

	# ── Datos ─────────────────────────────────────────────────────────────────

	@property
	def terminada(self) -> bool:
		return self.ejecucion.get("status") == "completed"

	@property
	def trabajo(self) -> dict | None:
		fila = self.lista_trabajos.fila_actual()
		return self.trabajos[fila] if 0 <= fila < len(self.trabajos) else None

	@property
	def paso(self) -> dict | None:
		trabajo = self.trabajo
		pasos = (trabajo or {}).get("steps") or []
		fila = self.lista_pasos.fila_actual()
		return pasos[fila] if 0 <= fila < len(pasos) else None

	def cargar(self, anunciar: bool = True) -> None:
		"""Pide la ejecución, sus trabajos y sus artefactos en segundo plano."""
		api = self.ctx.api()

		def obtener() -> tuple[dict, list, list]:
			ejecucion = api.ejecucion(self.nombre, self.id_ejecucion)
			trabajos = api.trabajos(self.nombre, self.id_ejecucion)
			try:
				artefactos = api.artefactos(self.nombre, self.id_ejecucion)
			except Exception:  # noqa: BLE001 - sin artefactos la ventana sigue siendo útil
				log.warning("No se pudieron leer los artefactos de %s/%s", self.nombre, self.id_ejecucion, exc_info=True)
				artefactos = []
			return ejecucion, trabajos, artefactos

		self.estado(_("Cargando la ejecución…"))
		self.en_fondo(obtener, al_terminar=lambda r: self._recibir(*r, anunciar=anunciar), sonido="",
			inicio=_("Cargando la ejecución…") if anunciar and not self.cargada else "")

	def _recibir(self, ejecucion: dict, trabajos: list, artefactos: list, anunciar: bool = True) -> None:
		primera = not self.cargada
		self.cargada = True
		self._poner_datos(ejecucion, trabajos)
		self.artefactos = list(artefactos or [])
		self._pintar_artefactos()
		if primera and self.trabajos:
			self.lista_trabajos.enfocar_fila(self._trabajo_interesante(), anunciar=False)
			self._mostrar_pasos()
			trabajo = self.trabajo
			if trabajo is not None:
				self._cargar_registro(trabajo)
		self._cargar_anotaciones()
		if not self.terminada and (primera or self.casilla_vivo.GetValue()):
			self.casilla_vivo.SetValue(True)
			self.seguir_en_vivo(True, anunciar=False)
		if anunciar:
			self.ctx.sonar("listo")
			self.ctx.avisar(self._resumen(), interrumpir=False)

	def _trabajo_interesante(self) -> int:
		"""El primer trabajo fallido (es lo que la persona viene a mirar) o el primero."""
		for indice, trabajo in enumerate(self.trabajos):
			if trabajo.get("conclusion") in ("failure", "timed_out", "startup_failure"):
				return indice
		return 0

	def _resumen(self) -> str:
		fallidos = sum(1 for t in self.trabajos if t.get("conclusion") in ("failure", "timed_out"))
		texto = _("{n}: {e}. {t} trabajos").format(n=self.ejecucion.get("name") or _("Ejecución"),
			e=f.estado_ejecucion(self.ejecucion), t=len(self.trabajos))
		if fallidos:
			texto += _(", {f} con fallos").format(f=fallidos)
		return texto + "."

	def _poner_datos(self, ejecucion: dict, trabajos: list) -> None:
		self.ejecucion = dict(ejecucion or {})
		self.trabajos = list(trabajos or [])
		self.info.SetValue(texto_informacion(self.ejecucion))
		self.SetTitle(_("{n} #{r} ({e}) de {repo}").format(n=self.ejecucion.get("name") or _("Ejecución"),
			r=self.ejecucion.get("run_number", self.id_ejecucion), e=f.estado_ejecucion(self.ejecucion), repo=self.nombre))
		self.lista_trabajos.reemplazar_filas([fila_trabajo(t) for t in self.trabajos], conservar_foco=True)
		self._mostrar_pasos()
		self.estado(self._resumen())

	def _mostrar_pasos(self) -> None:
		pasos = (self.trabajo or {}).get("steps") or []
		self.lista_pasos.reemplazar_filas([fila_paso(p) for p in pasos], conservar_foco=True)
		if pasos and self.lista_pasos.fila_actual() == wx.NOT_FOUND:
			self.lista_pasos.enfocar_fila(0, anunciar=False)

	def _pintar_artefactos(self) -> None:
		filas = []
		for artefacto in self.artefactos:
			filas.append([artefacto.get("name", ""), f.tamano(artefacto.get("size_in_bytes")),
				f.fecha(artefacto.get("expires_at"), self.ctx.relativas()), _("Caducado") if artefacto.get("expired") else _("Disponible")])
		self.lista_artefactos.reemplazar_filas(filas, conservar_foco=True)

	def _cargar_anotaciones(self) -> None:
		api = self.ctx.api()
		trabajos = [t for t in self.trabajos if t.get("status") == "completed" and t.get("id")]
		if not trabajos:
			self.anotaciones = []
			self.lista_anotaciones.reemplazar_filas([], conservar_foco=False)
			return

		def obtener() -> list[dict]:
			resultado = []
			for trabajo in trabajos:
				try:
					notas = api.anotaciones_check(self.nombre, trabajo["id"])
				except Exception:  # noqa: BLE001 - un trabajo sin anotaciones legibles no impide ver las demás
					log.warning("No se pudieron leer las anotaciones del trabajo %s", trabajo.get("id"), exc_info=True)
					continue
				resultado.extend(dict(n, _trabajo=trabajo.get("name", "")) for n in notas or [])
			return resultado

		def listo(notas: list[dict]) -> None:
			self.anotaciones = notas
			filas = []
			for nota in notas:
				ubicacion = nota.get("path") or ""
				if nota.get("start_line"):
					ubicacion += f":{nota['start_line']}"
				mensaje = " ".join(p for p in (nota.get("title") or "", f.primera_linea(nota.get("message"))) if p)
				nivel = nota.get("annotation_level") or ""
				filas.append([_(NIVELES_ANOTACION.get(nivel, nivel)), ubicacion, mensaje, nota.get("_trabajo", "")])
			self.lista_anotaciones.reemplazar_filas(filas, conservar_foco=True)

		self.en_fondo(obtener, al_terminar=listo, sonido="", al_fallar=lambda e: log.warning("Anotaciones: %s", e))

	# ── Registro ──────────────────────────────────────────────────────────────

	def _al_enfocar_trabajo(self, evento: wx.ListEvent) -> None:
		evento.Skip()
		self._mostrar_pasos()
		trabajo = self.trabajo
		if trabajo is None or trabajo.get("id") == self.id_registro:
			return
		# Se espera un poco: moverse deprisa por la lista no debe pedir un registro por fila.
		if self._carga_pendiente is not None and self._carga_pendiente.IsRunning():
			self._carga_pendiente.Stop()
		self._carga_pendiente = wx.CallLater(450, self._cargar_si_sigue, trabajo.get("id"))

	def _cargar_si_sigue(self, id_trabajo: int) -> None:
		trabajo = self.trabajo
		if self.viva() and trabajo is not None and trabajo.get("id") == id_trabajo:
			self._cargar_registro(trabajo)

	def _cargar_registro(self, trabajo: dict, forzar: bool = False, al_cargar: Any = None) -> None:
		id_trabajo = trabajo.get("id")
		if not forzar and id_trabajo in self.registros:
			self._mostrar_registro(id_trabajo, self.registros[id_trabajo])
			if al_cargar:
				al_cargar()
			return
		api = self.ctx.api()
		self.registro.SetValue(_("Cargando el registro de «{n}»…").format(n=trabajo.get("name", "")))
		terminado = trabajo.get("status") == "completed"

		def listo(texto: str) -> None:
			texto = texto or ""
			if terminado:
				self.registros[id_trabajo] = texto
			if (self.trabajo or {}).get("id") == id_trabajo:
				self._mostrar_registro(id_trabajo, texto)
				if al_cargar:
					al_cargar()

		def fallo(error: BaseException) -> None:
			if (self.trabajo or {}).get("id") != id_trabajo:
				return
			self.id_registro = None
			mensaje = getattr(error, "mensaje_usuario", None) or str(error)
			texto = _("No se pudo cargar el registro: {m}").format(m=mensaje)
			if not terminado:
				texto += "\n" + _("El trabajo sigue en curso: el registro completo estará disponible cuando termine.")
			self.lineas, self.lineas_crudas, self.crudo = texto.split("\n"), [], ""
			self.registro.SetValue(texto)

		self.en_fondo(lambda: api.registro_trabajo(self.nombre, id_trabajo), al_terminar=listo, al_fallar=fallo, sonido="")

	def _mostrar_registro(self, id_trabajo: int, crudo: str) -> None:
		self.id_registro = id_trabajo
		self.crudo = crudo
		self.lineas_crudas = crudo.splitlines()
		self.lineas = limpiar_registro(crudo, quitar_horas=not self.casilla_horas.GetValue()).split("\n") if crudo else []
		self.registro.SetValue("\n".join(self.lineas))
		self.registro.SetInsertionPoint(0)
		errores = sum(1 for linea in self.lineas if "ERROR:" in linea)
		avisos = sum(1 for linea in self.lineas if "AVISO:" in linea)
		self.estado(_("Registro: {l} líneas, {e} errores y {a} avisos. F8 salta al siguiente.").format(
			l=len(self.lineas), e=errores, a=avisos))
		paso = self.paso
		if paso is not None:
			self.ir_al_paso(anunciar=False, mover_foco=False)

	def _rehacer_registro(self) -> None:
		self.ctx.config.establecer("acciones.mostrar_horas", bool(self.casilla_horas.GetValue()))
		if self.id_registro is None or not self.crudo:
			return
		linea = self.linea_actual()
		self._mostrar_registro(self.id_registro, self.crudo)
		self.ir_a_linea(min(linea, max(0, len(self.lineas) - 1)), anunciar=False, mover_foco=False)

	def _alternar_horas(self) -> None:
		self.casilla_horas.SetValue(not self.casilla_horas.GetValue())
		self._rehacer_registro()
		self.ctx.avisar(_("Marcas de tiempo visibles.") if self.casilla_horas.GetValue() else _("Marcas de tiempo ocultas."))

	def recargar_registro(self) -> None:
		trabajo = self.trabajo
		if trabajo is None:
			self.ctx.avisar(_("No hay ningún trabajo elegido."))
			return
		self.registros.pop(trabajo.get("id"), None)
		self._cargar_registro(trabajo, forzar=True)

	def linea_actual(self) -> int:
		"""Línea (lógica) donde está el cursor del registro."""
		resultado = self.registro.PositionToXY(self.registro.GetInsertionPoint())
		if isinstance(resultado, tuple) and len(resultado) == 3:
			correcto, _x, y = resultado
			return int(y) if correcto else 0
		if isinstance(resultado, tuple) and len(resultado) == 2:
			return int(resultado[1])
		return 0

	def posicion_de(self, linea: int, columna: int = 0) -> int:
		posicion = self.registro.XYToPosition(columna, linea)
		if posicion < 0:  # respaldo: cada salto de línea ocupa una posición
			posicion = sum(len(texto) + 1 for texto in self.lineas[:linea]) + columna
		return posicion

	def ir_a_linea(self, linea: int, anunciar: bool = True, mover_foco: bool = True, largo: int = 0, columna: int = 0) -> None:
		if not self.lineas or not 0 <= linea < len(self.lineas):
			return
		posicion = self.posicion_de(linea, columna)
		if mover_foco:
			enfocar(self.registro)
		if largo:
			self.registro.SetSelection(posicion, posicion + largo)
		else:
			self.registro.SetInsertionPoint(posicion)
		self.registro.ShowPosition(posicion)
		if anunciar:
			self.ctx.anunciar(self.lineas[linea].strip() or _("(línea en blanco)"))

	def ir_al_registro(self) -> None:
		trabajo = self.trabajo
		if trabajo is None:
			return
		if trabajo.get("id") != self.id_registro:
			self._cargar_registro(trabajo, al_cargar=lambda: self._enfocar_registro())
			return
		self._enfocar_registro()

	def _enfocar_registro(self) -> None:
		enfocar(self.registro)
		self.ctx.avisar(self.GetStatusBar().GetStatusText() if self.GetStatusBar() else "", interrumpir=False)

	def ir_al_paso(self, anunciar: bool = True, mover_foco: bool = True) -> None:
		paso = self.paso
		if paso is None or not self.lineas:
			if anunciar:
				self.ctx.avisar(_("El registro de este trabajo aún no está cargado."))
			return
		linea = linea_de_paso(self.lineas, self.lineas_crudas, paso)
		if linea is None:
			if anunciar:
				self.ctx.sonar("vacio")
				self.ctx.anunciar(_("No se encontró el paso «{p}» en el registro.").format(p=paso.get("name", "")))
			return
		self.ir_a_linea(linea, anunciar=anunciar, mover_foco=mover_foco)

	def _al_enfocar_paso(self, evento: wx.ListEvent) -> None:
		evento.Skip()
		# Sin mover el foco: así, al pasar al registro con Tab, el cursor ya está en el paso.
		self.ir_al_paso(anunciar=False, mover_foco=False)

	def saltar_marca(self, atras: bool = False) -> None:
		if not self.lineas:
			self.ctx.avisar(_("No hay registro cargado."))
			return
		destino = siguiente_marca(self.lineas, self.linea_actual(), atras)
		if destino is None:
			self.ctx.sonar("vacio")
			self.ctx.anunciar(_("No hay más errores ni avisos antes.") if atras else _("No hay más errores ni avisos."))
			return
		self.ir_a_linea(destino)

	def buscar(self) -> None:
		texto = pedir_texto(self, _("&Texto que buscar en el registro:"), _("Buscar en el registro"), self.buscado)
		if texto is None or not texto.strip():
			return
		self.buscado = texto.strip()
		self.buscar_siguiente()

	def buscar_siguiente(self, atras: bool = False) -> None:
		if not self.buscado:
			self.buscar()
			return
		resultado = buscar_linea(self.lineas, self.buscado, self.linea_actual(), atras)
		if resultado is None:
			self.ctx.sonar("vacio")
			self.ctx.anunciar(_("No se encontró «{t}».").format(t=self.buscado))
			return
		linea, columna, vuelta = resultado
		if vuelta:
			self.ctx.anunciar(_("Se ha dado la vuelta al registro."), interrumpir=True)
		self.ir_a_linea(linea, largo=len(self.buscado), columna=columna)

	# ── Seguimiento en vivo ───────────────────────────────────────────────────

	def vigilar_en_segundo_plano(self) -> None:
		"""La vigila la ventana principal: avisa al terminar aunque esta ventana se cierre."""
		from app.services import vigilancia_actions as va

		if self.ejecucion.get("status") == "completed":
			self.ctx.avisar(_("Esta ejecución ya ha terminado."))
			return
		principal = self.ctx.ventana_principal
		if principal is None or not hasattr(principal, "vigilar"):
			return
		principal.vigilar(va.nueva_ejecucion(self.nombre, dict(self.ejecucion, id=self.id_ejecucion)))

	def seguir_en_vivo(self, activar: bool, anunciar: bool = True) -> None:
		if activar and self.cargada and self.terminada:
			self.casilla_vivo.SetValue(False)
			if anunciar:
				self.ctx.avisar(_("La ejecución ya ha terminado: no hay nada que seguir."))
			return
		self.casilla_vivo.SetValue(activar)
		if activar:
			if not self.temporizador.IsRunning():
				self.temporizador.Start(INTERVALO_VIVO_MS)
			if anunciar:
				self.ctx.avisar(_("Siguiendo la ejecución en vivo."))
		else:
			if self.temporizador.IsRunning():
				self.temporizador.Stop()
			if anunciar:
				self.ctx.avisar(_("Seguimiento en vivo detenido."))

	def _al_temporizador(self, _evento: wx.TimerEvent | None = None) -> None:
		if self._sondeando or not self.viva():
			return
		self._sondeando = True
		api = self.ctx.api()

		def listo(resultado: tuple[dict, list]) -> None:
			self._sondeando = False
			self.actualizar_en_vivo(*resultado)

		def fallo(error: BaseException) -> None:
			self._sondeando = False
			log.warning("No se pudo actualizar la ejecución en vivo: %s", error)
			self.estado(_("No se pudo actualizar: {m}").format(m=getattr(error, "mensaje_usuario", None) or str(error)))

		self.en_fondo(lambda: (api.ejecucion(self.nombre, self.id_ejecucion), api.trabajos(self.nombre, self.id_ejecucion)),
			al_terminar=listo, al_fallar=fallo, sonido="")

	def actualizar_en_vivo(self, ejecucion: dict, trabajos: list) -> None:
		"""Aplica un sondeo: anuncia los cambios y, si terminó, suena y para el temporizador."""
		estaba_terminada = self.terminada
		anterior_mostrado = self.trabajo
		cambios = cambios_de_estado(self.trabajos, trabajos)
		self._poner_datos(ejecucion, trabajos)
		for frase in cambios:
			self.ctx.avisar(frase, interrumpir=False)
		actual = self.trabajo
		if (actual is not None and anterior_mostrado is not None and actual.get("id") == anterior_mostrado.get("id")
			and actual.get("status") == "completed" and anterior_mostrado.get("status") != "completed"):
			self._cargar_registro(actual, forzar=True)
		if self.terminada and not estaba_terminada:
			self.seguir_en_vivo(False, anunciar=False)
			correcta = self.ejecucion.get("conclusion") == "success"
			self.ctx.sonar("accion_exito" if correcta else "accion_fallo")
			self.ctx.avisar(_("Ejecución terminada: {e}.").format(e=f.estado_ejecucion(self.ejecucion)), interrumpir=False)
			self.cargar(anunciar=False)  # artefactos y anotaciones, que solo existen al terminar

	# ── Acciones sobre la ejecución ───────────────────────────────────────────

	def volver_a_ejecutar(self, solo_fallidos: bool = False, depuracion: bool = False) -> None:
		if self.cargada and not self.terminada:
			self.ctx.avisar(_("La ejecución sigue en curso: cancélela antes de volver a ejecutarla."))
			return
		api = self.ctx.api()
		if solo_fallidos:
			texto = _("Volviendo a ejecutar los trabajos fallidos.")
		elif depuracion:
			texto = _("Volviendo a ejecutar con el registro de depuración.")
		else:
			texto = _("Volviendo a ejecutar todos los trabajos.")
		self.en_fondo(lambda: api.volver_a_ejecutar(self.nombre, self.id_ejecucion, solo_fallidos, depuracion), exito=texto,
			al_terminar=lambda _r: self._tras_relanzar())

	def _tras_relanzar(self) -> None:
		self.registros.clear()
		self.id_registro = None
		self.cargar(anunciar=False)
		self.casilla_vivo.SetValue(True)
		self.seguir_en_vivo(True, anunciar=False)

	def volver_a_ejecutar_trabajo(self) -> None:
		trabajo = self.trabajo
		if trabajo is None:
			self.ctx.avisar(_("No hay ningún trabajo elegido."))
			return
		api = self.ctx.api()
		self.en_fondo(lambda: api.volver_a_ejecutar_trabajo(self.nombre, trabajo["id"]),
			exito=_("Volviendo a ejecutar el trabajo {n}.").format(n=trabajo.get("name", "")), al_terminar=lambda _r: self._tras_relanzar())

	def cancelar(self, forzar: bool = False) -> None:
		if self.cargada and self.terminada:
			self.ctx.avisar(_("La ejecución ya ha terminado."))
			return
		if forzar and not confirmar_peligro(self, _("¿Cancelar a la fuerza la ejecución? Se detiene aunque haya pasos que "
			"deberían ejecutarse siempre (por ejemplo, de limpieza)."), _("Cancelar a la fuerza")):
			return
		api = self.ctx.api()
		self.en_fondo(lambda: api.cancelar_ejecucion(self.nombre, self.id_ejecucion, forzar),
			exito=_("Cancelación pedida."), al_terminar=lambda _r: self.cargar(anunciar=False))

	def aprobar(self) -> None:
		api = self.ctx.api()
		self.en_fondo(lambda: api.aprobar_ejecucion(self.nombre, self.id_ejecucion), exito=_("Ejecución aprobada."),
			al_terminar=lambda _r: self.cargar(anunciar=False))

	def revisar_despliegues(self) -> None:
		api = self.ctx.api()
		self.en_fondo(lambda: api.despliegues_pendientes(self.nombre, self.id_ejecucion), al_terminar=self._elegir_despliegues,
			sonido="", inicio=_("Buscando despliegues pendientes…"))

	def _elegir_despliegues(self, pendientes: list) -> None:
		if not pendientes:
			mostrar_mensaje(self, _("Esta ejecución no tiene despliegues pendientes de revisión."), _("Despliegues pendientes"))
			return
		opciones = []
		for pendiente in pendientes:
			entorno = (pendiente.get("environment") or {}).get("name", "")
			if not pendiente.get("current_user_can_approve", True):
				entorno += _(" (no tiene permiso para aprobarlo)")
			opciones.append(entorno)
		marcados = elegir_varios(self, _("Despliegues pendientes"), _("&Entornos que revisar:"), opciones,
			list(range(len(opciones))), config=self.ctx.config)
		if not marcados:
			return
		decision = elegir_opcion(self, _("¿Qué hacer con los {n} entornos elegidos?").format(n=len(marcados)),
			_("Revisar despliegues"), [_("&Aprobar"), _("&Rechazar")])
		if decision is None:
			return
		comentario = pedir_texto(self, _("C&omentario (opcional):"), _("Revisar despliegues"))
		if comentario is None:
			return
		ids = [(pendientes[i].get("environment") or {}).get("id") for i in marcados]
		aprobar = decision == 0
		api = self.ctx.api()
		self.en_fondo(lambda: api.revisar_despliegue(self.nombre, self.id_ejecucion, ids, aprobar, comentario),
			exito=_("Despliegues aprobados.") if aprobar else _("Despliegues rechazados."), al_terminar=lambda _r: self.cargar(anunciar=False))

	def borrar(self) -> None:
		if not confirmar_peligro(self, _("¿Borrar esta ejecución con sus registros y artefactos? No se puede deshacer."),
			_("Borrar ejecución")):
			return
		api = self.ctx.api()
		self.en_fondo(lambda: api.borrar_ejecucion(self.nombre, self.id_ejecucion), exito=_("Ejecución borrada."),
			al_terminar=lambda _r: self.Close())

	def borrar_registros(self) -> None:
		if not confirmar_peligro(self, _("¿Borrar todos los registros de esta ejecución? No se puede deshacer."), _("Borrar registros")):
			return
		api = self.ctx.api()

		def hecho(_r: Any) -> None:
			self.registros.clear()
			self.id_registro = None
			self.lineas, self.lineas_crudas, self.crudo = [], [], ""
			self.registro.SetValue(_("Los registros se han borrado."))

		self.en_fondo(lambda: api.borrar_registros(self.nombre, self.id_ejecucion), exito=_("Registros borrados."), al_terminar=hecho)

	def descargar_registros(self) -> None:
		carpeta = carpeta_de_descargas(self, self.ctx)
		if not carpeta:
			return
		cliente = self.ctx.api().c
		# Operación sin envoltura en la API: se usa el cliente crudo para descargar el zip a disco.
		url = cliente.url(f"{ruta_repo(self.nombre)}/actions/runs/{self.id_ejecucion}/logs")
		destino = Path(carpeta) / nombre_seguro(f"registros-{self.nombre.replace('/', '-')}-{self.id_ejecucion}.zip")
		self.descargar(url, destino, aceptar="application/vnd.github+json", descripcion=_("los registros"))

	def abrir_navegador(self) -> None:
		url = self.ejecucion.get("html_url") or f"https://{self.ctx.host}/{self.nombre}/actions/runs/{self.id_ejecucion}"
		webbrowser.open(url)

	def copiar_enlace(self) -> None:
		url = self.ejecucion.get("html_url") or f"https://{self.ctx.host}/{self.nombre}/actions/runs/{self.id_ejecucion}"
		copiar(self.ctx, url, _("Enlace copiado."))

	# ── Anotaciones y artefactos ──────────────────────────────────────────────

	def ver_anotacion(self) -> None:
		fila = self.lista_anotaciones.fila_actual()
		if not 0 <= fila < len(self.anotaciones):
			return
		nota = self.anotaciones[fila]
		ubicacion = nota.get("path") or ""
		if nota.get("start_line"):
			ubicacion += f":{nota['start_line']}"
			if nota.get("end_line") and nota.get("end_line") != nota.get("start_line"):
				ubicacion += f"-{nota['end_line']}"
		texto = "\n".join(p for p in (
			_("Nivel: {n}").format(n=_(NIVELES_ANOTACION.get(nota.get("annotation_level") or "", nota.get("annotation_level") or ""))),
			_("Ubicación: {u}").format(u=ubicacion),
			_("Trabajo: {t}").format(t=nota.get("_trabajo", "")),
			nota.get("title") or "",
			"",
			nota.get("message") or "",
			nota.get("raw_details") or "",
		) if p is not None)
		from app.ui.dialogo_texto import DialogoTexto

		dialogo = DialogoTexto(self, _("Anotación"), _("&Anotación:"), texto, copiable=True)
		try:
			dialogo.ShowModal()
		finally:
			dialogo.Destroy()

	@property
	def artefacto(self) -> dict | None:
		fila = self.lista_artefactos.fila_actual()
		return self.artefactos[fila] if 0 <= fila < len(self.artefactos) else None

	def descargar_artefacto(self, preguntar: bool = False, artefacto: dict | None = None, carpeta: str | None = None) -> None:
		artefacto = artefacto or self.artefacto
		if artefacto is None:
			self.ctx.avisar(_("No hay ningún artefacto elegido."))
			return
		if artefacto.get("expired"):
			self.ctx.avisar(_("El artefacto {n} ha caducado: ya no se puede descargar.").format(n=artefacto.get("name", "")))
			return
		carpeta = carpeta or carpeta_de_descargas(self, self.ctx, preguntar)
		if not carpeta:
			return
		url = self.ctx.api().url_artefacto(self.nombre, artefacto["id"])
		destino = Path(carpeta) / nombre_seguro(f"{artefacto.get('name') or 'artefacto'}.zip")
		self.descargar(url, destino, aceptar="application/vnd.github+json", descripcion=artefacto.get("name", ""))

	def descargar_todos_los_artefactos(self) -> None:
		disponibles = [a for a in self.artefactos if not a.get("expired")]
		if not disponibles:
			self.ctx.avisar(_("No hay artefactos que descargar."))
			return
		carpeta = carpeta_de_descargas(self, self.ctx)
		if not carpeta:
			return
		for artefacto in disponibles:
			self.descargar_artefacto(artefacto=artefacto, carpeta=carpeta)

	def borrar_artefacto(self) -> None:
		artefacto = self.artefacto
		if artefacto is None:
			return
		if not confirmar_peligro(self, _("¿Borrar el artefacto {n}? No se puede deshacer.").format(n=artefacto.get("name", "")),
			_("Borrar artefacto")):
			return
		api = self.ctx.api()

		def hecho(_r: Any) -> None:
			if artefacto in self.artefactos:
				self.artefactos.remove(artefacto)
			self._pintar_artefactos()

		self.en_fondo(lambda: api.borrar_artefacto(self.nombre, artefacto["id"]), exito=_("Artefacto borrado."), al_terminar=hecho)


def abrir_ejecucion(ctx: Any, padre: wx.Window | None, nombre: str, id_ejecucion: int) -> wx.Frame:
	"""Abre (o trae al frente) la ventana de una ejecución de Actions y la carga en segundo plano."""
	clave = f"ejecucion:{nombre}:{int(id_ejecucion)}"
	if VentanaDetalle.abrir_existente(clave):
		return VentanaDetalle._abiertas[clave]
	ventana = VentanaEjecucion(ctx, padre, nombre, int(id_ejecucion))
	ventana.mostrar(ventana.lista_trabajos)
	ventana.cargar()
	return ventana


# ════════════════════════════════════════════════════════════════════════════
# Lanzar un flujo (workflow_dispatch)
# ════════════════════════════════════════════════════════════════════════════


class DialogoLanzarFlujo(wx.Dialog):
	"""Rama y un control por entrada del flujo (desplegable, casilla o campo de texto)."""

	def __init__(self, padre: wx.Window | None, nombre_flujo: str, ramas: list[str], rama_defecto: str,
		entradas: list[EntradaFlujo], entornos: list[str] | None = None) -> None:
		super().__init__(padre, title=_("Lanzar el flujo {n}").format(n=nombre_flujo), size=(620, 560),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.entradas = entradas
		self.controles: list[wx.Window] = []
		raiz = wx.BoxSizer(wx.VERTICAL)
		zona = wx.ScrolledWindow(self, style=wx.VSCROLL)
		zona.SetScrollRate(0, 20)
		columna = wx.BoxSizer(wx.VERTICAL)
		columna.Add(wx.StaticText(zona, label=_("&Rama o etiqueta en la que lanzarlo:")), 0, wx.LEFT | wx.TOP, 6)
		self.ramas = list(ramas) or ([rama_defecto] if rama_defecto else [])
		self.selector_rama = wx.Choice(zona, choices=self.ramas)
		if rama_defecto in self.ramas:
			self.selector_rama.SetSelection(self.ramas.index(rama_defecto))
		elif self.ramas:
			self.selector_rama.SetSelection(0)
		self.selector_rama.SetHelpText(_("Rama cuyo archivo del flujo se usará."))
		columna.Add(self.selector_rama, 0, wx.EXPAND | wx.ALL, 6)

		textos = []
		for entrada in entradas:
			base = entrada.descripcion if entrada.descripcion and len(entrada.descripcion) <= 70 else entrada.nombre
			if entrada.requerida:
				base += _(" (obligatorio)")
			textos.append(base if entrada.tipo == "boolean" else base + ":")
		etiquetas = asignar_letras(textos, {"r", "l", "c"})
		for entrada, etiqueta in zip(entradas, etiquetas, strict=True):
			ayuda = _("Entrada «{n}».").format(n=entrada.nombre)
			if entrada.descripcion:
				ayuda += " " + entrada.descripcion
			if entrada.defecto:
				ayuda += " " + _("Valor por defecto: {d}.").format(d=entrada.defecto)
			if entrada.tipo == "boolean":
				control = wx.CheckBox(zona, label=etiqueta)
				control.SetValue(entrada.defecto.lower() == "true")
				columna.Add(control, 0, wx.ALL, 6)
			else:
				columna.Add(wx.StaticText(zona, label=etiqueta), 0, wx.LEFT | wx.TOP, 6)
				opciones = entrada.opciones if entrada.tipo == "choice" else (entornos or []) if entrada.tipo == "environment" else []
				if opciones:
					if entrada.defecto and entrada.defecto not in opciones:
						opciones = [entrada.defecto, *opciones]
					control = wx.Choice(zona, choices=opciones)
					control.SetSelection(opciones.index(entrada.defecto) if entrada.defecto in opciones else 0)
					control._opciones = opciones
				else:
					control = wx.TextCtrl(zona, value=entrada.defecto)
					if entrada.tipo == "number":
						ayuda += " " + _("Escriba un número.")
				columna.Add(control, 0, wx.EXPAND | wx.ALL, 6)
			control.SetHelpText(ayuda)
			self.controles.append(control)
		if not entradas:
			columna.Add(wx.StaticText(zona, label=_("Este flujo no pide ningún dato.")), 0, wx.ALL, 6)
		zona.SetSizer(columna)
		raiz.Add(zona, 1, wx.EXPAND | wx.ALL, 4)
		botones = crear_botonera(self, wx.OK | wx.CANCEL)
		self.FindWindow(wx.ID_OK).SetLabel(_("&Lanzar el flujo"))
		raiz.Add(botones, 0, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(raiz)
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		preparar_dialogo(self, foco_inicial=self.controles[0] if self.controles else self.selector_rama)
		self.CentreOnParent()

	def rama(self) -> str:
		indice = self.selector_rama.GetSelection()
		return self.ramas[indice] if 0 <= indice < len(self.ramas) else ""

	def valores(self) -> dict[str, str]:
		"""Valores como texto, que es como los espera la API de ``workflow_dispatch``."""
		resultado: dict[str, str] = {}
		for entrada, control in zip(self.entradas, self.controles, strict=True):
			if isinstance(control, wx.CheckBox):
				resultado[entrada.nombre] = "true" if control.GetValue() else "false"
			elif isinstance(control, wx.Choice):
				indice = control.GetSelection()
				resultado[entrada.nombre] = control._opciones[indice] if indice >= 0 else ""
			else:
				resultado[entrada.nombre] = control.GetValue().strip()
		return resultado

	def comprobar(self) -> tuple[str, wx.Window | None]:
		"""Mensaje del primer error y su control («», None si todo está bien)."""
		if not self.rama():
			return _("Elija una rama."), self.selector_rama
		valores = self.valores()
		for entrada, control in zip(self.entradas, self.controles, strict=True):
			valor = valores[entrada.nombre]
			if entrada.requerida and entrada.tipo != "boolean" and not valor:
				return _("La entrada «{n}» es obligatoria.").format(n=entrada.nombre), control
			if entrada.tipo == "number" and valor:
				try:
					float(valor.replace(",", "."))
				except ValueError:
					return _("La entrada «{n}» debe ser un número.").format(n=entrada.nombre), control
		return "", None

	def _al_aceptar(self, _evento: wx.CommandEvent) -> None:
		mensaje, control = self.comprobar()
		if mensaje:
			mostrar_error(self, mensaje, _("Falta un dato"))
			if control is not None:
				control.SetFocus()
			return
		self.EndModal(wx.ID_OK)


def lanzar_flujo(ctx: Any, padre: wx.Window | None, nombre: str, flujo: dict | None = None) -> None:
	"""Lanza un flujo a mano (``workflow_dispatch``) pidiendo la rama y sus entradas."""
	api = ctx.api()
	if flujo is None:
		def elegir(flujos: list) -> None:
			if not flujos:
				mostrar_mensaje(padre, _("Este repositorio no tiene flujos de Actions."), _("Lanzar un flujo"))
				return
			opciones = []
			for elemento in flujos:
				texto = f"{elemento.get('name', '')} ({elemento.get('path', '')})"
				if elemento.get("state") not in (None, "active"):
					texto += _(", desactivado")
				opciones.append(texto)
			indice = elegir_uno(padre, _("Lanzar un flujo"), _("&Flujo que lanzar:"), opciones)
			if indice is not None:
				lanzar_flujo(ctx, padre, nombre, flujos[indice])

		en_segundo_plano(padre, ctx, lambda: api.flujos(nombre), al_terminar=elegir, sonido="", inicio=_("Cargando los flujos…"))
		return

	nombre_flujo = flujo.get("name") or flujo.get("path") or str(flujo.get("id", ""))

	def obtener() -> tuple[bool, list[EntradaFlujo], list[str], str, list[str]]:
		contenido, _sha = api.leer_archivo(nombre, flujo["path"])
		texto = contenido.decode("utf-8", errors="replace") if isinstance(contenido, bytes) else str(contenido)
		admite, entradas = analizar_dispatch(texto)
		ramas = [r.get("name", "") for r in api.todas_las_ramas(nombre) or [] if r.get("name")]
		defecto = (api.repositorio(nombre) or {}).get("default_branch", "")
		entornos: list[str] = []
		if any(e.tipo == "environment" for e in entradas):
			try:
				entornos = [e.get("name", "") for e in api.entornos(nombre) or []]
			except Exception:  # noqa: BLE001 - sin la lista de entornos se escribe a mano
				log.warning("No se pudieron leer los entornos de %s", nombre, exc_info=True)
		return admite, entradas, ramas, defecto, entornos

	def mostrar(datos: tuple) -> None:
		admite, entradas, ramas, defecto, entornos = datos
		if not admite:
			mostrar_error(padre, _("El flujo «{n}» no se puede lanzar a mano: su archivo no tiene «workflow_dispatch» "
				"en la sección «on».").format(n=nombre_flujo), _("Lanzar un flujo"))
			return
		dialogo = DialogoLanzarFlujo(padre, nombre_flujo, ramas, defecto, entradas, entornos)
		try:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			mensaje, _control = dialogo.comprobar()
			if mensaje:
				mostrar_error(padre, mensaje, _("Falta un dato"))
				return
			rama, valores = dialogo.rama(), dialogo.valores()
		finally:
			dialogo.Destroy()
		en_segundo_plano(padre, ctx, lambda: api.lanzar_flujo(nombre, flujo["id"], rama, valores), sonido="enviado",
			inicio=_("Lanzando el flujo…"),
			exito=_("Flujo «{n}» lanzado en {r}. La ejecución aparecerá en unos segundos.").format(n=nombre_flujo, r=rama))

	en_segundo_plano(padre, ctx, obtener, al_terminar=mostrar, sonido="", inicio=_("Leyendo el flujo…"))
