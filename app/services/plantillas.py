"""Plantillas y formularios de issue de GitHub y su ``config.yml`` (sin wx).

Por qué existe:

- En ``.github/ISSUE_TEMPLATE/`` hay dos clases de plantilla. Las ``.md`` llevan
  una cabecera YAML (``name``, ``about``, ``title``, ``labels``, ``assignees``,
  ``type``) y el cuerpo en Markdown. Los formularios ``.yml``/``.yaml`` describen
  campos (``input``, ``textarea``, ``dropdown``, ``checkboxes`` y texto
  ``markdown``) y la web compone con ellos el cuerpo de la issue. Antes se
  quitaba la cabecera (se perdían título, etiquetas y asignados) y los
  formularios se descartaban.
- ``config.yml`` decide si se ofrece «Issue en blanco» y añade enlaces de
  contacto (foros, seguridad...).
- No se usa PyYAML: sería una dependencia más para leer un subconjunto pequeño.
  ``leer_yaml`` entiende lo que usan estos archivos: mapas y listas por
  sangría, cadenas con y sin comillas, bloques ``|`` y ``>``, listas y mapas
  en línea (``[a, b]``), booleanos, números, nulos y comentarios. Lo que no
  entiende lo dice con el número de línea (``ErrorYaml``).
- El cuerpo se compone como lo hace la web de GitHub (``### Etiqueta``, la
  respuesta y «_No response_» si está vacía), para que la issue quede igual
  que si se hubiera creado desde el navegador.
"""

from __future__ import annotations

import builtins
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Lo que escribe la web de GitHub en un campo que se deja vacío (no se traduce: va en la issue).
SIN_RESPUESTA = "_No response_"
#: Tipos de elemento de un formulario de issue.
TIPOS_ELEMENTO = ("markdown", "input", "textarea", "dropdown", "checkboxes")
#: Extensiones de los formularios (las demás plantillas son Markdown).
EXTENSIONES_FORMULARIO = (".yml", ".yaml")
#: Archivos de configuración de la carpeta de plantillas (no son plantillas).
ARCHIVOS_CONFIG = ("config.yml", "config.yaml")


class ErrorYaml(ValueError):
	"""El texto no es YAML válido (o usa algo que este lector no entiende).

	:param linea: número de línea (desde 1) donde está el problema, o 0 si no se sabe.
	"""

	def __init__(self, mensaje: str, linea: int = 0) -> None:
		self.linea = linea
		self.motivo = mensaje
		super().__init__(_("Línea {n}: {m}").format(n=linea, m=mensaje) if linea else mensaje)


class ErrorPlantilla(ValueError):
	"""La plantilla o el formulario no se puede usar (YAML mal escrito, sin ``body``...)."""


# ════════════════════════════════════════════════════════════════════════════
# Lector de YAML (subconjunto)
# ════════════════════════════════════════════════════════════════════════════

_NULOS = {"", "~", "null", "Null", "NULL"}
_VERDADEROS = {"true", "True", "TRUE"}
_FALSOS = {"false", "False", "FALSE"}
_ENTERO = re.compile(r"[-+]?[0-9]+")
_HEXADECIMAL = re.compile(r"0x[0-9a-fA-F]+")
_OCTAL = re.compile(r"0o[0-7]+")
_REAL = re.compile(r"[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?")
_INFINITO = re.compile(r"[-+]?\.(inf|Inf|INF)")
_NO_NUMERO = {".nan", ".NaN", ".NAN"}
_CABECERA_BLOQUE = re.compile(r"([|>])([+-]?)([1-9]?)([+-]?)")
_ESCAPES = {
	"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v", "f": "\f", "r": "\r",
	"e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\", "N": "\x85", "_": "\xa0", "L": " ", "P": " ",
}
_LARGO_ESCAPE = {"x": 2, "u": 4, "U": 8}


def resolver_escalar(texto: str) -> Any:
	"""Convierte un escalar sin comillas en ``None``, ``bool``, ``int``, ``float`` o ``str``.

	Sigue el esquema básico de YAML 1.2: ``yes``/``no`` son texto (en un
	desplegable «Yes» y «No» son opciones, no booleanos).
	"""
	if texto in _NULOS:
		return None
	if texto in _VERDADEROS:
		return True
	if texto in _FALSOS:
		return False
	if _ENTERO.fullmatch(texto):
		return int(texto)
	if _HEXADECIMAL.fullmatch(texto):
		return int(texto, 16)
	if _OCTAL.fullmatch(texto):
		return int(texto[2:], 8)
	if _REAL.fullmatch(texto):
		return float(texto)
	if _INFINITO.fullmatch(texto):
		return -math.inf if texto.startswith("-") else math.inf
	if texto in _NO_NUMERO:
		return math.nan
	return texto


def _sangria(linea: str) -> int:
	return len(linea) - len(linea.lstrip(" "))


def _vacia(linea: str) -> bool:
	"""Línea sin contenido: en blanco o solo un comentario."""
	limpia = linea.strip()
	return not limpia or limpia.startswith("#")


def _quitar_comentario(texto: str) -> str:
	"""Quita « # comentario» de un escalar sin comillas (un ``#`` pegado a una palabra no es comentario)."""
	if texto.startswith("#"):
		return ""
	encontrado = re.search(r"[ \t]#", texto)
	return (texto[:encontrado.start()] if encontrado else texto).rstrip()


def _es_guion(texto: str) -> bool:
	"""``texto`` (sin la sangría) empieza un elemento de lista («- algo» o «-» solo)."""
	return texto == "-" or texto.startswith(("- ", "-\t"))


def _comillas_dobles(texto: str, inicio: int, linea: int) -> tuple[str, int] | None:
	"""Lee ``"…"`` desde ``texto[inicio]`` (la comilla).

	Devuelve ``(valor, posición tras la comilla de cierre)`` o ``None`` si no se cierra.
	"""
	partes: list[str] = []
	i = inicio + 1
	while i < len(texto):
		caracter = texto[i]
		if caracter == '"':
			return "".join(partes), i + 1
		if caracter != "\\":
			partes.append(caracter)
			i += 1
			continue
		i += 1
		if i >= len(texto):
			return None
		escape = texto[i]
		if escape in _ESCAPES:
			partes.append(_ESCAPES[escape])
			i += 1
		elif escape in _LARGO_ESCAPE:
			largo = _LARGO_ESCAPE[escape]
			codigo = texto[i + 1:i + 1 + largo]
			if len(codigo) != largo or not re.fullmatch(r"[0-9a-fA-F]+", codigo):
				raise ErrorYaml(_("escape «\\{e}» mal escrito").format(e=escape + codigo), linea)
			partes.append(chr(int(codigo, 16)))
			i += 1 + largo
		elif escape == "\n":
			# Barra al final de la línea: el salto no cuenta y se ignora la sangría siguiente.
			i += 1
			while i < len(texto) and texto[i] in " \t":
				i += 1
		else:
			raise ErrorYaml(_("escape «\\{e}» desconocido entre comillas dobles").format(e=escape), linea)
	return None


def _comillas_simples(texto: str, inicio: int) -> tuple[str, int] | None:
	"""Lee ``'…'`` desde ``texto[inicio]``; ``''`` es una comilla. ``None`` si no se cierra."""
	partes: list[str] = []
	i = inicio + 1
	while i < len(texto):
		caracter = texto[i]
		if caracter == "'":
			if i + 1 < len(texto) and texto[i + 1] == "'":
				partes.append("'")
				i += 2
				continue
			return "".join(partes), i + 1
		partes.append(caracter)
		i += 1
	return None


def _entrecomillado(texto: str, inicio: int, linea: int) -> tuple[str, int] | None:
	if texto[inicio] == '"':
		return _comillas_dobles(texto, inicio, linea)
	return _comillas_simples(texto, inicio)


class _FlujoIncompleto(Exception):
	"""Una lista o un mapa en línea (``[…]``, ``{…}``) sigue en la línea siguiente."""


class _Flujo:
	"""Lee listas y mapas en línea: ``[bug, "a b"]``, ``{name: x, url: y}``."""

	def __init__(self, texto: str, linea: int) -> None:
		self.t = texto
		self.i = 0
		self.linea = linea

	def _espacios(self) -> None:
		while self.i < len(self.t) and self.t[self.i] in " \t":
			self.i += 1

	def _actual(self) -> str:
		if self.i >= len(self.t):
			raise _FlujoIncompleto
		return self.t[self.i]

	def valor(self) -> Any:
		self._espacios()
		caracter = self._actual()
		if caracter == "[":
			return self._lista()
		if caracter == "{":
			return self._mapa()
		if caracter in "\"'":
			leido = _entrecomillado(self.t, self.i, self.linea)
			if leido is None:
				raise _FlujoIncompleto
			self.i = leido[1]
			return leido[0]
		return self._plano()

	def _plano(self) -> Any:
		inicio = self.i
		while self.i < len(self.t):
			caracter = self.t[self.i]
			if caracter in ",]}":
				break
			siguiente = self.t[self.i + 1] if self.i + 1 < len(self.t) else " "
			if caracter == ":" and siguiente in " \t,]}":
				break
			self.i += 1
		return resolver_escalar(self.t[inicio:self.i].strip())

	def _separador(self, cierre: str) -> bool:
		"""Tras un elemento: ``True`` si se cierra la colección, ``False`` si sigue otro."""
		self._espacios()
		caracter = self._actual()
		if caracter == ",":
			self.i += 1
			return False
		if caracter == cierre:
			self.i += 1
			return True
		raise ErrorYaml(_("se esperaba «,» o «{c}» y hay «{x}»").format(c=cierre, x=caracter), self.linea)

	def _lista(self) -> list:
		self.i += 1
		resultado: list = []
		while True:
			self._espacios()
			if self._actual() == "]":
				self.i += 1
				return resultado
			resultado.append(self.valor())
			if self._separador("]"):
				return resultado

	def _mapa(self) -> dict:
		self.i += 1
		resultado: dict = {}
		while True:
			self._espacios()
			if self._actual() == "}":
				self.i += 1
				return resultado
			clave = self.valor()
			self._espacios()
			valor = None
			if self._actual() == ":":
				self.i += 1
				self._espacios()
				valor = None if self._actual() in ",}" else self.valor()
			resultado[clave if isinstance(clave, str) else str(clave)] = valor
			if self._separador("}"):
				return resultado


class _Lector:
	"""Lector por líneas: cada colección de bloque se reconoce por su sangría."""

	def __init__(self, texto: str) -> None:
		texto = texto.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
		self.lineas = texto.split("\n")
		self.i = 0

	# ── Ayudas ────────────────────────────────────────────────────────────────

	def _sin_tabulaciones(self, linea: str) -> None:
		"""YAML no admite tabulaciones en la sangría (sí dentro de un bloque ``|``, que no pasa por aquí)."""
		if linea.lstrip(" ").startswith("\t"):
			raise ErrorYaml(_("la sangría no puede llevar tabulaciones, solo espacios"), self.i + 1)

	def _fin(self) -> bool:
		return self.i >= len(self.lineas)

	def _saltar_vacias(self) -> None:
		while not self._fin() and _vacia(self.lineas[self.i]):
			self.i += 1

	def _fin_de_documento(self) -> bool:
		linea = self.lineas[self.i].rstrip()
		return linea in ("---", "...") or linea.startswith("--- ")

	# ── Documento ─────────────────────────────────────────────────────────────

	def documento(self) -> Any:
		self._saltar_vacias()
		while not self._fin() and self.lineas[self.i].startswith("%"):
			self.i += 1  # directivas (%YAML 1.2)
			self._saltar_vacias()
		if not self._fin() and self.lineas[self.i].rstrip() == "---":
			self.i += 1
		self._saltar_vacias()
		if self._fin() or self._fin_de_documento():
			return None
		resultado = self._bloque(_sangria(self.lineas[self.i]), -1)
		self._saltar_vacias()
		if not self._fin() and not self._fin_de_documento():
			raise ErrorYaml(_("sangría inesperada o contenido que sobra"), self.i + 1)
		return resultado

	def _bloque(self, sangria: int, padre: int) -> Any:
		"""Lo que empieza en la línea actual con esa sangría: lista, mapa o escalar."""
		self._sin_tabulaciones(self.lineas[self.i])
		texto = self.lineas[self.i][sangria:]
		if _es_guion(texto):
			return self._lista(sangria)
		if self._partir_clave(texto) is not None:
			return self._mapa(sangria)
		self.i += 1
		return self._escalar(texto, padre)

	# ── Colecciones ───────────────────────────────────────────────────────────

	def _lista(self, sangria: int) -> list:
		resultado: list = []
		while True:
			self._saltar_vacias()
			if self._fin():
				return resultado
			linea = self.lineas[self.i]
			self._sin_tabulaciones(linea)
			texto = linea[sangria:]
			if _sangria(linea) != sangria or not _es_guion(texto):
				if _sangria(linea) > sangria:
					raise ErrorYaml(_("sangría inesperada dentro de una lista"), self.i + 1)
				return resultado
			resto = texto[1:]
			contenido = resto.lstrip(" \t")
			if not _quitar_comentario(contenido):
				# «-» solo: el elemento va en las líneas siguientes, más sangradas.
				self.i += 1
				resultado.append(self._valor_anidado(sangria, permitir_lista_igual=False))
				continue
			columna = sangria + 1 + (len(resto) - len(contenido))
			if _es_guion(contenido) or self._partir_clave(contenido) is not None:
				# «- clave: valor» o «- - x»: se lee como si empezara en la columna del contenido.
				self.lineas[self.i] = " " * columna + contenido
				resultado.append(self._bloque(columna, sangria))
			else:
				self.i += 1
				resultado.append(self._escalar(contenido, sangria))

	def _mapa(self, sangria: int) -> dict:
		resultado: dict = {}
		while True:
			self._saltar_vacias()
			if self._fin() or self._fin_de_documento():
				return resultado
			linea = self.lineas[self.i]
			self._sin_tabulaciones(linea)
			actual = _sangria(linea)
			if actual < sangria:
				return resultado
			if actual > sangria:
				raise ErrorYaml(_("sangría inesperada"), self.i + 1)
			texto = linea[sangria:]
			if _es_guion(texto):
				return resultado  # la lista de la clave anterior ya terminó
			partes = self._partir_clave(texto)
			if partes is None:
				raise ErrorYaml(_("se esperaba «clave: valor»"), self.i + 1)
			clave, resto = partes
			self.i += 1
			resultado[clave] = self._valor(resto, sangria)

	def _partir_clave(self, texto: str) -> tuple[str, str] | None:
		"""``(clave, resto)`` si ``texto`` es «clave: valor»; ``None`` si no lo es."""
		if not texto:
			return None
		if texto[0] in "\"'":
			leido = _entrecomillado(texto, 0, self.i + 1)
			if leido is None:
				return None
			resto = texto[leido[1]:].lstrip(" \t")
			if resto.startswith(":") and (len(resto) == 1 or resto[1] in " \t"):
				return leido[0], resto[1:]
			return None
		if texto[0] in "[{#|>!&*%@`" or _es_guion(texto) or texto.startswith("? "):
			return None
		separador = re.search(r":(?:[ \t]|$)", texto)
		if separador is None:
			return None
		clave = texto[:separador.start()].rstrip()
		if not clave or re.search(r"[ \t]#", clave):
			return None  # los dos puntos están dentro de un comentario
		return clave, texto[separador.end():]

	def _valor(self, resto: str, sangria: int) -> Any:
		"""Valor de una clave: en la misma línea o, si no hay nada, en las siguientes."""
		if _quitar_comentario(resto.strip()):
			return self._escalar(resto, sangria)
		return self._valor_anidado(sangria, permitir_lista_igual=True)

	def _valor_anidado(self, sangria: int, permitir_lista_igual: bool) -> Any:
		self._saltar_vacias()
		if self._fin() or self._fin_de_documento():
			return None
		linea = self.lineas[self.i]
		actual = _sangria(linea)
		if actual > sangria:
			return self._bloque(actual, sangria)
		# «body:» seguido de «- type: …» a la misma altura: es válido en YAML y muy común.
		if permitir_lista_igual and actual == sangria and _es_guion(linea[actual:]):
			return self._lista(sangria)
		return None

	# ── Escalares ─────────────────────────────────────────────────────────────

	def _escalar(self, texto: str, padre: int) -> Any:
		"""Escalar que empieza en ``texto`` (ya consumido); puede seguir en otras líneas."""
		texto = texto.strip()
		numero = self.i  # línea del escalar (la actual ya se pasó)
		if texto.startswith("!"):
			etiqueta, _sep, texto = texto.partition(" ")
			texto = texto.strip()
			if etiqueta == "!!str":
				valor = self._escalar(texto, padre) if texto else ""
				return valor if isinstance(valor, str) else _texto(valor)
		if texto[:1] in ("|", ">"):
			return self._bloque_literal(texto, padre, numero)
		if texto[:1] in ("\"", "'"):
			return self._entrecomillado_multilinea(texto, padre, numero)
		if texto[:1] in ("[", "{"):
			return self._flujo(texto, padre, numero)
		valor = _quitar_comentario(texto)
		if valor != texto:
			return resolver_escalar(valor)  # un comentario cierra el escalar
		continuado = self._continuar_plano(valor, padre)
		return resolver_escalar(valor) if continuado == valor else continuado

	def _continuar_plano(self, valor: str, padre: int) -> str:
		"""Un escalar sin comillas sigue en las líneas más sangradas que su clave (se unen con espacios)."""
		partes = [valor]
		vacias = 0
		j = self.i
		while j < len(self.lineas):
			linea = self.lineas[j]
			limpia = linea.strip()
			if not limpia:
				vacias += 1
				j += 1
				continue
			if _sangria(linea) <= padre or limpia.startswith("#") or linea.rstrip() in ("---", "..."):
				break
			continuacion = _quitar_comentario(limpia)
			if re.search(r":(?:[ \t]|$)", continuacion):
				# «clave: valor» más sangrado que la clave anterior: es un error de sangría,
				# no la continuación del texto (YAML tampoco lo admite).
				raise ErrorYaml(_("sangría inesperada"), j + 1)
			partes.append("\n" * vacias if vacias else " ")
			partes.append(continuacion)
			vacias = 0
			j += 1
			self.i = j
			if continuacion != limpia:
				break
		return "".join(partes)

	def _entrecomillado_multilinea(self, texto: str, padre: int, numero: int) -> str:
		acumulado = texto
		vacias = 0
		while True:
			leido = _entrecomillado(acumulado, 0, numero)
			if leido is not None:
				resto = acumulado[leido[1]:].strip()
				if resto and not resto.startswith("#"):
					raise ErrorYaml(_("texto después de cerrar las comillas: «{t}»").format(t=resto), self.i)
				return leido[0]
			if self._fin():
				raise ErrorYaml(_("faltan las comillas de cierre"), numero)
			siguiente = self.lineas[self.i].strip()
			self.i += 1
			if not siguiente:
				vacias += 1
				continue
			# Dentro de comillas, un salto de línea se convierte en espacio y una línea vacía en «\n».
			if acumulado.endswith("\\") and acumulado.startswith('"'):
				union = "\n"
			else:
				acumulado = acumulado.rstrip(" \t")
				union = "\n" * vacias if vacias else " "
			acumulado += union + siguiente
			vacias = 0

	def _flujo(self, texto: str, padre: int, numero: int) -> Any:
		acumulado = texto
		while True:
			lector = _Flujo(acumulado, numero)
			try:
				valor = lector.valor()
			except _FlujoIncompleto:
				# El cierre («]» o «}») puede ir a la misma sangría que la clave, como en
				# «options: [» … «]»: lo admiten GitHub y PyYAML (plantilla de errores de NVDA).
				siguiente = "" if self._fin() else self.lineas[self.i].strip()
				cierre = siguiente[:1] in ("]", "}")
				if self._fin() or (_sangria(self.lineas[self.i]) <= padre and siguiente and not cierre):
					raise ErrorYaml(_("falta cerrar «{c}»").format(c="]" if texto.startswith("[") else "}"), numero) from None
				acumulado += " " + _quitar_comentario(self.lineas[self.i].strip())
				self.i += 1
				continue
			resto = acumulado[lector.i:].strip()
			if resto and not resto.startswith("#"):
				raise ErrorYaml(_("texto que sobra tras «{c}»").format(c=acumulado[lector.i - 1]), numero)
			return valor

	def _bloque_literal(self, cabecera: str, padre: int, numero: int) -> str:
		"""Bloques ``|`` (se conservan los saltos) y ``>`` (se pliegan en espacios)."""
		indicadores = _CABECERA_BLOQUE.match(_quitar_comentario(cabecera))
		if indicadores is None or indicadores.end() != len(_quitar_comentario(cabecera)):
			raise ErrorYaml(_("cabecera de bloque no válida: «{c}»").format(c=cabecera), numero)
		estilo, recorte1, explicita, recorte2 = indicadores.groups()
		recorte = recorte1 or recorte2
		sangria = max(padre, 0) + int(explicita) if explicita else None
		lineas: list[str] = []
		while not self._fin():
			linea = self.lineas[self.i]
			if not linea.strip():
				lineas.append(linea[sangria:] if sangria is not None and len(linea) > sangria else "")
				self.i += 1
				continue
			actual = _sangria(linea)
			if sangria is None:
				if actual <= padre:
					break
				sangria = actual
			if actual < sangria:
				break
			lineas.append(linea[sangria:])
			self.i += 1
		finales = 0
		while lineas and not lineas[-1].strip():
			lineas.pop()
			finales += 1
		contenido = "\n".join(lineas) if estilo == "|" else _plegar(lineas)
		if recorte == "-" or not lineas:
			return contenido if recorte != "+" else contenido + "\n" * finales
		if recorte == "+":
			return contenido + "\n" + "\n" * finales
		return contenido + "\n"


def _plegar(lineas: list[str]) -> str:
	"""Plegado de un bloque ``>``: las líneas seguidas se unen con un espacio.

	Una línea vacía deja un salto de línea, y las líneas más sangradas (código,
	listas) conservan los suyos.
	"""
	resultado = ""
	anterior: str | None = None
	vacias = 0
	for linea in lineas:
		if not linea.strip():
			resultado += "\n"
			vacias += 1
			continue
		if anterior is None:
			resultado += linea
		else:
			sangradas = linea[:1] in (" ", "\t") or anterior[:1] in (" ", "\t")
			if vacias:
				resultado += ("\n" if sangradas else "") + linea
			else:
				resultado += ("\n" if sangradas else " ") + linea
		anterior = linea
		vacias = 0
	return resultado


def leer_yaml(texto: str) -> Any:
	"""Lee un documento YAML del subconjunto que usan las plantillas de GitHub.

	:raises ErrorYaml: con el número de línea si algo no se entiende.
	"""
	return _Lector(texto).documento()


# ════════════════════════════════════════════════════════════════════════════
# Modelo de plantillas y formularios
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class Casilla:
	"""Opción de un elemento ``checkboxes``."""

	etiqueta: str
	obligatoria: bool = False


@dataclass
class Elemento:
	"""Un elemento del ``body`` de un formulario de issue.

	:param tipo: ``markdown``, ``input``, ``textarea``, ``dropdown`` o ``checkboxes``.
	:param valor: texto del ``markdown`` o valor inicial de ``input`` y ``textarea``.
	:param por_defecto: posición de la opción elegida al abrir un ``dropdown``.
	"""

	tipo: str
	indice: int = 0
	id: str = ""
	etiqueta: str = ""
	descripcion: str = ""
	marcador: str = ""
	valor: str = ""
	render: str = ""
	obligatorio: bool = False
	opciones: list[str] = field(default_factory=list)
	multiple: bool = False
	por_defecto: int | None = None
	casillas: list[Casilla] = field(default_factory=list)

	@property
	def clave(self) -> str:
		"""Clave de su respuesta: el ``id`` del formulario o, si no tiene, su posición."""
		return self.id or f"campo_{self.indice}"

	@property
	def pregunta(self) -> bool:
		"""``True`` si pide una respuesta (todo menos el texto ``markdown``)."""
		return self.tipo != "markdown"


@dataclass
class Plantilla:
	"""Plantilla Markdown o formulario de issue, con sus metadatos.

	:param archivo: nombre del archivo en ``.github/ISSUE_TEMPLATE``.
	:param cuerpo: texto de una plantilla Markdown (sin la cabecera).
	:param elementos: campos de un formulario (vacío en las plantillas Markdown).
	"""

	archivo: str
	nombre: str
	descripcion: str = ""
	titulo: str = ""
	etiquetas: list[str] = field(default_factory=list)
	asignados: list[str] = field(default_factory=list)
	tipo: str = ""
	cuerpo: str = ""
	elementos: list[Elemento] = field(default_factory=list)
	formulario: bool = False

	@property
	def preguntas(self) -> list[Elemento]:
		return [e for e in self.elementos if e.pregunta]


@dataclass
class EnlaceContacto:
	"""Enlace de ``contact_links`` de ``config.yml`` (se abre en el navegador)."""

	nombre: str
	url: str
	descripcion: str = ""


@dataclass
class ConfigIssues:
	"""``config.yml`` de la carpeta de plantillas."""

	en_blanco: bool = True
	enlaces: list[EnlaceContacto] = field(default_factory=list)


@dataclass
class Falta:
	"""Un campo obligatorio sin rellenar.

	:param opcion: en ``checkboxes``, la casilla obligatoria sin marcar (``-1`` si es el elemento entero).
	"""

	elemento: Elemento
	opcion: int = -1

	@property
	def texto(self) -> str:
		nombre = self.elemento.etiqueta or self.elemento.clave
		if 0 <= self.opcion < len(self.elemento.casillas):
			return f"{nombre}: {self.elemento.casillas[self.opcion].etiqueta}"
		return nombre


def _texto(valor: Any) -> str:
	"""Escalar como texto: ``None`` es vacío y los booleanos se escriben como en YAML."""
	if valor is None:
		return ""
	if isinstance(valor, bool):
		return "true" if valor else "false"
	return str(valor)


def _es_verdadero(valor: Any) -> bool:
	"""``true`` y, por tolerancia con YAML 1.1 (el que usa GitHub), también ``yes`` y ``on``."""
	if isinstance(valor, bool):
		return valor
	return isinstance(valor, str) and valor.strip().lower() in ("true", "yes", "on")


def _es_falso(valor: Any) -> bool:
	if isinstance(valor, bool):
		return not valor
	return isinstance(valor, str) and valor.strip().lower() in ("false", "no", "off")


def lista_de_textos(valor: Any) -> list[str]:
	"""``labels`` y ``assignees``: una lista o una cadena separada por comas."""
	if valor is None:
		return []
	elementos = valor if isinstance(valor, list) else _texto(valor).split(",")
	resultado: list[str] = []
	for elemento in elementos:
		limpio = _texto(elemento).strip()
		if limpio and limpio not in resultado:
			resultado.append(limpio)
	return resultado


def _nombre_de_archivo(archivo: str) -> str:
	base = archivo.rsplit("/", 1)[-1]
	return base.rsplit(".", 1)[0] if "." in base else base


_CABECERA = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)^---[ \t]*(?:\r?\n|\Z)", re.S | re.M)


def separar_cabecera(texto: str) -> tuple[str | None, str]:
	"""Separa la cabecera YAML («--- … ---» al principio) del cuerpo de una plantilla Markdown.

	Devuelve ``(cabecera, cuerpo)``; ``cabecera`` es ``None`` si no hay.
	"""
	encontrada = _CABECERA.match(texto)
	if encontrada is None:
		return None, texto.lstrip("﻿")
	return encontrada.group(1), texto[encontrada.end():].lstrip("\r\n")


def leer_plantilla_md(archivo: str, texto: str) -> Plantilla:
	"""Plantilla Markdown: cabecera con ``name``, ``about``, ``title``, ``labels``, ``assignees`` y ``type``.

	Una cabecera ilegible no impide usar el cuerpo (se registra y se sigue sin metadatos).
	"""
	cabecera, cuerpo = separar_cabecera(texto)
	datos: Any = {}
	if cabecera is not None:
		try:
			datos = leer_yaml(cabecera)
		except ErrorYaml as error:
			log.warning("Cabecera ilegible en la plantilla %s: %s", archivo, error)
	if not isinstance(datos, dict):
		datos = {}
	return Plantilla(
		archivo=archivo,
		nombre=_texto(datos.get("name")).strip() or _nombre_de_archivo(archivo),
		descripcion=_texto(datos.get("about") or datos.get("description")).strip(),
		titulo=_texto(datos.get("title")),
		etiquetas=lista_de_textos(datos.get("labels")),
		asignados=lista_de_textos(datos.get("assignees")),
		tipo=_texto(datos.get("type")).strip(),
		cuerpo=cuerpo,
	)


def _leer_elemento(dato: Any, indice: int, archivo: str) -> Elemento:
	if not isinstance(dato, dict):
		raise ErrorPlantilla(_("El elemento {n} del formulario «{a}» no es un mapa «type: …».").format(n=indice + 1, a=archivo))
	tipo = _texto(dato.get("type")).strip().lower()
	if tipo not in TIPOS_ELEMENTO:
		raise ErrorPlantilla(_("El elemento {n} del formulario «{a}» tiene un tipo desconocido: «{t}».").format(
			n=indice + 1, a=archivo, t=_texto(dato.get("type"))))
	atributos = dato.get("attributes") if isinstance(dato.get("attributes"), dict) else {}
	validaciones = dato.get("validations") if isinstance(dato.get("validations"), dict) else {}
	elemento = Elemento(
		tipo=tipo,
		indice=indice,
		id=_texto(dato.get("id")).strip(),
		etiqueta=_texto(atributos.get("label")).strip(),
		descripcion=_texto(atributos.get("description")).strip(),
		marcador=_texto(atributos.get("placeholder")).strip(),
		valor=_texto(atributos.get("value")).rstrip("\n"),
		render=_texto(atributos.get("render")).strip(),
		obligatorio=tipo != "markdown" and _es_verdadero(validaciones.get("required")),
	)
	if tipo == "dropdown":
		opciones = atributos.get("options")
		elemento.opciones = [_texto(o).strip() for o in opciones] if isinstance(opciones, list) else []
		elemento.multiple = _es_verdadero(atributos.get("multiple"))
		defecto = atributos.get("default")
		if isinstance(defecto, int) and not isinstance(defecto, bool) and 0 <= defecto < len(elemento.opciones):
			elemento.por_defecto = defecto
	elif tipo == "checkboxes":
		opciones = atributos.get("options")
		for opcion in opciones if isinstance(opciones, list) else []:
			if isinstance(opcion, dict):
				elemento.casillas.append(Casilla(_texto(opcion.get("label")).strip(), _es_verdadero(opcion.get("required"))))
			else:
				elemento.casillas.append(Casilla(_texto(opcion).strip()))
	return elemento


def leer_formulario(archivo: str, texto: str) -> Plantilla:
	"""Formulario de issue (``.yml``): metadatos y elementos de ``body``.

	:raises ErrorPlantilla: si el YAML está mal escrito o no es un formulario.
	"""
	try:
		datos = leer_yaml(texto)
	except ErrorYaml as error:
		raise ErrorPlantilla(_("El formulario «{a}» no se puede leer. {e}").format(a=archivo, e=error)) from error
	if not isinstance(datos, dict):
		raise ErrorPlantilla(_("«{a}» no es un formulario de issue.").format(a=archivo))
	cuerpo = datos.get("body")
	if not isinstance(cuerpo, list) or not cuerpo:
		raise ErrorPlantilla(_("El formulario «{a}» no tiene campos («body»).").format(a=archivo))
	return Plantilla(
		archivo=archivo,
		nombre=_texto(datos.get("name")).strip() or _nombre_de_archivo(archivo),
		descripcion=_texto(datos.get("description") or datos.get("about")).strip(),
		titulo=_texto(datos.get("title")),
		etiquetas=lista_de_textos(datos.get("labels")),
		asignados=lista_de_textos(datos.get("assignees")),
		tipo=_texto(datos.get("type")).strip(),
		elementos=[_leer_elemento(dato, indice, archivo) for indice, dato in enumerate(cuerpo)],
		formulario=True,
	)


def leer_plantilla(archivo: str, texto: str) -> Plantilla:
	"""Plantilla Markdown o formulario según la extensión del archivo."""
	if archivo.lower().endswith(EXTENSIONES_FORMULARIO):
		return leer_formulario(archivo, texto)
	return leer_plantilla_md(archivo, texto)


def leer_plantillas(archivos: list[tuple[str, str]]) -> tuple[list[Plantilla], list[str]]:
	"""Lee varias plantillas ``(archivo, texto)``. Devuelve ``(plantillas, errores)``.

	Un formulario mal escrito no impide usar los demás: su error se devuelve
	para poder explicarlo.
	"""
	plantillas: list[Plantilla] = []
	errores: list[str] = []
	for archivo, texto in archivos:
		try:
			plantillas.append(leer_plantilla(archivo, texto))
		except ErrorPlantilla as error:
			log.warning("Plantilla de issue descartada: %s", error)
			errores.append(str(error))
	return plantillas, errores


def leer_config(texto: str) -> ConfigIssues:
	"""``config.yml``: ``blank_issues_enabled`` y ``contact_links`` (``name``, ``url``, ``about``).

	Si no se puede leer, se usa lo de GitHub por defecto (issue en blanco y sin enlaces).
	"""
	if not texto or not texto.strip():
		return ConfigIssues()
	try:
		datos = leer_yaml(texto)
	except ErrorYaml as error:
		log.warning("config.yml de las plantillas ilegible: %s", error)
		return ConfigIssues()
	if not isinstance(datos, dict):
		return ConfigIssues()
	enlaces = []
	contactos = datos.get("contact_links")
	for enlace in contactos if isinstance(contactos, list) else []:
		if not isinstance(enlace, dict):
			continue
		url = _texto(enlace.get("url")).strip()
		if not url:
			continue
		enlaces.append(EnlaceContacto(_texto(enlace.get("name")).strip() or url, url, _texto(enlace.get("about")).strip()))
	return ConfigIssues(en_blanco=not _es_falso(datos.get("blank_issues_enabled")), enlaces=enlaces)


# ════════════════════════════════════════════════════════════════════════════
# Respuestas: cuerpo de la issue y obligatorios
# ════════════════════════════════════════════════════════════════════════════


def _respuesta(elemento: Elemento, valor: Any) -> str:
	if elemento.tipo == "checkboxes":
		marcadas = list(valor or [])
		return "\n".join(
			f"- [{'x' if posicion < len(marcadas) and marcadas[posicion] else ' '}] {casilla.etiqueta}"
			for posicion, casilla in enumerate(elemento.casillas))
	if elemento.tipo == "dropdown":
		elegidas = [_texto(o) for o in (valor or []) if _texto(o)]
		return ", ".join(elegidas) or SIN_RESPUESTA
	texto = _texto(valor).rstrip().lstrip("\r\n")
	if not texto.strip():
		return SIN_RESPUESTA
	if elemento.tipo == "textarea" and elemento.render:
		return f"```{elemento.render}\n{texto}\n```"
	return texto


def componer_cuerpo(plantilla: Plantilla, respuestas: dict[str, Any]) -> str:
	"""Cuerpo de la issue como lo compone la web de GitHub a partir de un formulario.

	:param respuestas: por ``Elemento.clave``: texto en ``input`` y ``textarea``,
		lista de opciones elegidas en ``dropdown`` y lista de booleanos (una por
		casilla) en ``checkboxes``.

	Cada campo es «### Etiqueta», una línea en blanco y la respuesta; los
	textos ``markdown`` del formulario no van en la issue.
	"""
	secciones = [f"### {e.etiqueta}\n\n{_respuesta(e, respuestas.get(e.clave))}" for e in plantilla.preguntas]
	return "\n\n".join(secciones)


def faltan_obligatorios(plantilla: Plantilla, respuestas: dict[str, Any]) -> list[Falta]:
	"""Campos obligatorios sin rellenar, en el orden del formulario."""
	faltas: list[Falta] = []
	for elemento in plantilla.preguntas:
		valor = respuestas.get(elemento.clave)
		if elemento.tipo == "checkboxes":
			marcadas = list(valor or [])
			for posicion, casilla in enumerate(elemento.casillas):
				if casilla.obligatoria and not (posicion < len(marcadas) and marcadas[posicion]):
					faltas.append(Falta(elemento, posicion))
			if elemento.obligatorio and not any(marcadas):
				faltas.append(Falta(elemento))
		elif elemento.tipo == "dropdown":
			if elemento.obligatorio and not [o for o in valor or [] if _texto(o)]:
				faltas.append(Falta(elemento))
		elif elemento.obligatorio and not _texto(valor).strip():
			faltas.append(Falta(elemento))
	return faltas


def describir_faltas(faltas: list[Falta]) -> str:
	"""Frase para la persona: qué campos obligatorios faltan."""
	if not faltas:
		return ""
	if len(faltas) == 1:
		return _("Falta rellenar el campo obligatorio «{c}».").format(c=faltas[0].texto)
	return _("Faltan {n} campos obligatorios: {c}.").format(n=len(faltas), c=", ".join(f"«{f.texto}»" for f in faltas))


def describir_plantilla(plantilla: Plantilla) -> str:
	"""Texto de una plantilla en la lista para elegir: nombre, si es formulario, y descripción."""
	nombre = plantilla.nombre + (_(" (formulario)") if plantilla.formulario else "")
	return f"{nombre}: {plantilla.descripcion}" if plantilla.descripcion else nombre


def describir_descartados(descartados: list[str]) -> str:
	"""Aviso de que GitHub no aplicó etiquetas, asignados o tipo de la plantilla.

	:param descartados: claves que devuelve ``ApiGitHub.crear_issue_con_plantilla``.
	"""
	nombres = {"etiquetas": _("las etiquetas"), "asignados": _("los asignados"), "tipo": _("el tipo")}
	partes = [nombres.get(d, d) for d in descartados]
	if not partes:
		return ""
	lista = partes[0] if len(partes) == 1 else _("{a} y {b}").format(a=", ".join(partes[:-1]), b=partes[-1])
	return _(
		"GitHub no ha aplicado {l} de la plantilla: hace falta permiso de clasificación (triage) o de escritura "
		"en el repositorio. La issue se ha creado sin ellos; quien mantiene el repositorio puede ponerlos."
	).format(l=lista)
