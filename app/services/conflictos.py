"""Conflictos de git: análisis y resolución bloque a bloque (funciones puras, sin wx).

Por qué así:

- La persona que usa un lector de pantalla no puede «ver» los marcadores
  ``<<<<<<<``, ``|||||||``, ``=======`` y ``>>>>>>>`` repartidos por el
  archivo. Aquí cada conflicto es un ``BloqueConflicto`` con sus dos (o tres)
  versiones separadas, que la interfaz lee de uno en uno: «Bloque 2 de 5. Su
  versión: … La otra versión: …».
- Se habla de «su versión» (la de la persona) y de «la otra versión», nunca de
  ours y theirs. En una REORGANIZACIÓN (rebase) git pone arriba (ours) la rama
  sobre la que se reorganiza y abajo (theirs) el commit de la persona que se
  está aplicando: por eso todas las funciones reciben ``invertido`` y lo
  tienen en cuenta al nombrar y al elegir.
- El texto se analiza conservando los finales de línea originales (``\\r\\n`` o
  ``\\n``): ``componer`` devuelve exactamente el archivo de partida si no se
  resuelve nada, y solo cambia los bloques resueltos.
- Sin wx ni git: se prueba con cadenas (``tests/test_conflictos.py``).
"""

from __future__ import annotations

import builtins
import re
from dataclasses import dataclass, field


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# Elecciones posibles para un bloque (siempre desde el punto de vista de la persona).
PROPIA = "propia"
OTRA = "otra"
AMBAS_PROPIA_PRIMERO = "ambas_propia_primero"
AMBAS_OTRA_PRIMERO = "ambas_otra_primero"
MANUAL = "manual"
ELECCIONES = (PROPIA, OTRA, AMBAS_PROPIA_PRIMERO, AMBAS_OTRA_PRIMERO, MANUAL)

_INICIO = re.compile(r"^<{7}(?:[ \t](.*))?$")
_BASE = re.compile(r"^\|{7}(?:[ \t](.*))?$")
_SEPARADOR = re.compile(r"^={7}$")
_FIN = re.compile(r"^>{7}(?:[ \t](.*))?$")


def _sin_fin(linea: str) -> str:
	return linea.rstrip("\r\n")


@dataclass
class BloqueConflicto:
	"""Un conflicto del archivo.

	:param numero: posición del bloque (empieza en 1).
	:param linea_inicio: línea del marcador ``<<<<<<<`` en el archivo original (empieza en 1).
	:param linea_fin: línea del marcador ``>>>>>>>``.
	:param superior: líneas de arriba (ours, HEAD), con su final de línea.
	:param inferior: líneas de abajo (theirs).
	:param base: líneas de la versión común (solo con ``merge.conflictStyle=diff3``/``zdiff3``).
	:param original: todas las líneas del bloque tal cual, marcadores incluidos.
	:param resolucion: líneas elegidas; ``None`` mientras está pendiente.
	"""

	numero: int
	linea_inicio: int
	linea_fin: int
	superior: list[str]
	inferior: list[str]
	base: list[str] | None = None
	etiqueta_superior: str = ""
	etiqueta_inferior: str = ""
	etiqueta_base: str = ""
	original: list[str] = field(default_factory=list)
	resolucion: list[str] | None = None
	eleccion: str = ""

	@property
	def resuelto(self) -> bool:
		return self.resolucion is not None


@dataclass
class ArchivoConflicto:
	"""Archivo troceado en texto normal (listas de líneas) y bloques de conflicto."""

	partes: list = field(default_factory=list)
	fin_linea: str = "\n"

	@property
	def bloques(self) -> list[BloqueConflicto]:
		return [p for p in self.partes if isinstance(p, BloqueConflicto)]

	@property
	def pendientes(self) -> list[BloqueConflicto]:
		return [b for b in self.bloques if not b.resuelto]

	@property
	def resuelto(self) -> bool:
		return not self.pendientes

	def componer(self) -> str:
		"""Texto del archivo: bloques resueltos sustituidos, pendientes con sus marcadores."""
		trozos: list[str] = []
		for parte in self.partes:
			if isinstance(parte, BloqueConflicto):
				trozos.extend(parte.resolucion if parte.resolucion is not None else parte.original)
			else:
				trozos.extend(parte)
		return "".join(trozos)


# ════════════════════════════════════════════════════════════════════════════
# Análisis
# ════════════════════════════════════════════════════════════════════════════


def tiene_marcadores(texto: str) -> bool:
	"""``True`` si el texto contiene al menos un bloque de conflicto completo."""
	return bool(analizar(texto).bloques)


def analizar(texto: str) -> ArchivoConflicto:
	"""Trocea ``texto`` en partes normales y bloques de conflicto.

	Un ``<<<<<<<`` sin su ``=======`` y su ``>>>>>>>`` se deja como texto normal
	(puede ser contenido legítimo, por ejemplo documentación sobre git).
	"""
	lineas = texto.splitlines(keepends=True)
	archivo = ArchivoConflicto(fin_linea="\r\n" if "\r\n" in texto else "\n")
	normal: list[str] = []
	i = 0
	numero = 0
	while i < len(lineas):
		inicio = _INICIO.match(_sin_fin(lineas[i]))
		if not inicio:
			normal.append(lineas[i])
			i += 1
			continue
		superior: list[str] = []
		inferior: list[str] = []
		base: list[str] | None = None
		etiqueta_base = ""
		etiqueta_inferior = ""
		zona = "superior"
		cerrado = False
		j = i + 1
		while j < len(lineas):
			sin_fin = _sin_fin(lineas[j])
			if zona == "superior" and (marca_base := _BASE.match(sin_fin)):
				zona = "base"
				base = []
				etiqueta_base = (marca_base.group(1) or "").strip()
			elif zona in ("superior", "base") and _SEPARADOR.match(sin_fin):
				zona = "inferior"
			elif zona == "inferior" and (fin := _FIN.match(sin_fin)):
				etiqueta_inferior = (fin.group(1) or "").strip()
				cerrado = True
				break
			elif _INICIO.match(sin_fin):
				break  # bloque mal formado o anidado: se trata como texto
			elif zona == "superior":
				superior.append(lineas[j])
			elif zona == "base":
				base.append(lineas[j])  # type: ignore[union-attr]
			else:
				inferior.append(lineas[j])
			j += 1
		if not cerrado:
			normal.append(lineas[i])
			i += 1
			continue
		if normal:
			archivo.partes.append(normal)
			normal = []
		numero += 1
		archivo.partes.append(BloqueConflicto(
			numero=numero, linea_inicio=i + 1, linea_fin=j + 1, superior=superior, inferior=inferior, base=base,
			etiqueta_superior=(inicio.group(1) or "").strip(), etiqueta_inferior=etiqueta_inferior,
			etiqueta_base=etiqueta_base, original=lineas[i:j + 1],
		))
		i = j + 1
	if normal:
		archivo.partes.append(normal)
	return archivo


# ════════════════════════════════════════════════════════════════════════════
# Lados: «su versión» y «la otra»
# ════════════════════════════════════════════════════════════════════════════


def version_propia(bloque: BloqueConflicto, invertido: bool = False) -> list[str]:
	"""Líneas de la persona: arriba en una fusión, abajo en una reorganización."""
	return bloque.inferior if invertido else bloque.superior


def version_otra(bloque: BloqueConflicto, invertido: bool = False) -> list[str]:
	return bloque.superior if invertido else bloque.inferior


def etiqueta_propia(bloque: BloqueConflicto, invertido: bool = False) -> str:
	return bloque.etiqueta_inferior if invertido else bloque.etiqueta_superior


def etiqueta_otra(bloque: BloqueConflicto, invertido: bool = False) -> str:
	return bloque.etiqueta_superior if invertido else bloque.etiqueta_inferior


def version_git(eleccion: str, invertido: bool = False) -> str:
	"""«ours» o «theirs» para ``git checkout --ours/--theirs`` según lo que elige la persona."""
	if eleccion not in (PROPIA, OTRA):
		raise ValueError(eleccion)
	propia = eleccion == PROPIA
	return ("theirs" if propia else "ours") if invertido else ("ours" if propia else "theirs")


def es_invertido(operacion: str) -> bool:
	"""En una reorganización git llama «ours» a la rama de destino y «theirs» a lo de la persona."""
	return operacion.strip().lower() in (_("reorganización").lower(), "reorganización", "rebase")


def explicar_lados(operacion: str) -> str:
	"""Frase que explica qué es «su versión» y qué es «la otra» en la operación en curso."""
	if es_invertido(operacion):
		return _(
			"Reorganización en curso: «su versión» es la del commit suyo que se está aplicando de nuevo; "
			"«la otra versión» es la de la rama sobre la que reorganiza. Git las llama al revés (theirs y ours)."
		)
	if operacion == _("fusión"):
		return _("Fusión en curso: «su versión» es la de su rama actual; «la otra versión» es la de la rama que se fusiona.")
	if operacion in (_("cherry-pick"), _("reversión")):
		return _("«Su versión» es la de su rama actual; «la otra versión» es la del commit que se aplica.")
	return _("«Su versión» es la de su rama actual (ours); «la otra versión» es la que llega (theirs).")


# ════════════════════════════════════════════════════════════════════════════
# Resolución
# ════════════════════════════════════════════════════════════════════════════


def lineas_de(bloque: BloqueConflicto, eleccion: str, invertido: bool = False) -> list[str]:
	"""Líneas que quedan en el archivo con ``eleccion`` (salvo ``MANUAL``)."""
	propia = list(version_propia(bloque, invertido))
	otra = list(version_otra(bloque, invertido))
	if eleccion == PROPIA:
		return propia
	if eleccion == OTRA:
		return otra
	if eleccion == AMBAS_PROPIA_PRIMERO:
		return propia + otra
	if eleccion == AMBAS_OTRA_PRIMERO:
		return otra + propia
	raise ValueError(eleccion)


def texto_a_lineas(texto: str, fin_linea: str = "\n") -> list[str]:
	"""Texto escrito a mano → líneas con el final de línea del archivo (vacío = borrar el bloque)."""
	if texto == "":
		return []
	return [linea + fin_linea for linea in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def resolver(archivo: ArchivoConflicto, indice: int, eleccion: str, invertido: bool = False, texto: str | None = None) -> BloqueConflicto:
	"""Resuelve el bloque ``indice`` (empieza en 0) con ``eleccion``; con ``MANUAL`` usa ``texto``."""
	bloque = archivo.bloques[indice]
	if eleccion == MANUAL:
		if texto is None:
			raise ValueError(_("Falta el texto escrito a mano."))
		bloque.resolucion = texto_a_lineas(texto, archivo.fin_linea)
	else:
		bloque.resolucion = lineas_de(bloque, eleccion, invertido)
	bloque.eleccion = eleccion
	return bloque


def deshacer(archivo: ArchivoConflicto, indice: int) -> BloqueConflicto:
	"""Vuelve a dejar pendiente un bloque."""
	bloque = archivo.bloques[indice]
	bloque.resolucion = None
	bloque.eleccion = ""
	return bloque


def resolver_todos(archivo: ArchivoConflicto, eleccion: str, invertido: bool = False) -> None:
	for indice in range(len(archivo.bloques)):
		resolver(archivo, indice, eleccion, invertido)


def siguiente_pendiente(archivo: ArchivoConflicto, desde: int = -1) -> int | None:
	"""Índice del siguiente bloque pendiente después de ``desde`` (da la vuelta); ``None`` si no queda ninguno."""
	bloques = archivo.bloques
	total = len(bloques)
	for paso in range(1, total + 1):
		indice = (desde + paso) % total
		if not bloques[indice].resuelto:
			return indice
	return None


def texto_inicial_manual(bloque: BloqueConflicto, invertido: bool = False) -> str:
	"""Punto de partida para editar a mano: su versión y debajo la otra, sin marcadores."""
	return "".join(version_propia(bloque, invertido) + version_otra(bloque, invertido)).replace("\r\n", "\n").rstrip("\n")


# ════════════════════════════════════════════════════════════════════════════
# Textos para leer
# ════════════════════════════════════════════════════════════════════════════


def nombre_eleccion(eleccion: str) -> str:
	return {
		PROPIA: _("su versión"),
		OTRA: _("la otra versión"),
		AMBAS_PROPIA_PRIMERO: _("ambas, su versión primero"),
		AMBAS_OTRA_PRIMERO: _("ambas, la otra primero"),
		MANUAL: _("texto editado a mano"),
	}.get(eleccion, eleccion)


def texto_lineas(lineas: list[str]) -> str:
	"""Las líneas sin sus finales, para leer; «(vacía)» si no hay ninguna."""
	if not lineas:
		return _("(vacía)")
	return "\n".join(_sin_fin(linea) for linea in lineas)


def _con_etiqueta(nombre: str, etiqueta: str) -> str:
	return _("{n}, marcada como «{e}»").format(n=nombre, e=etiqueta) if etiqueta else nombre


def describir_bloque(archivo: ArchivoConflicto, indice: int, invertido: bool = False) -> str:
	"""«Bloque 2 de 5, líneas 20 a 34, pendiente.» y debajo su versión, la otra y la común."""
	bloques = archivo.bloques
	bloque = bloques[indice]
	estado = (_("resuelto con {e}").format(e=nombre_eleccion(bloque.eleccion)) if bloque.resuelto else _("pendiente"))
	partes = [
		_("Bloque {n} de {t}, líneas {a} a {b}, {e}.").format(
			n=indice + 1, t=len(bloques), a=bloque.linea_inicio, b=bloque.linea_fin, e=estado),
		_con_etiqueta(_("Su versión"), etiqueta_propia(bloque, invertido)) + ":",
		texto_lineas(version_propia(bloque, invertido)),
		_con_etiqueta(_("La otra versión"), etiqueta_otra(bloque, invertido)) + ":",
		texto_lineas(version_otra(bloque, invertido)),
	]
	if bloque.base is not None:
		partes += [_("Versión común (base):"), texto_lineas(bloque.base)]
	if bloque.resuelto:
		partes += [_("Quedará así:"), texto_lineas(bloque.resolucion or [])]
	return "\n".join(partes)


def resumen(archivo: ArchivoConflicto) -> str:
	total = len(archivo.bloques)
	if not total:
		return _("No quedan marcadores de conflicto en el archivo.")
	pendientes = len(archivo.pendientes)
	return _("{t} bloques: {r} resueltos y {p} pendientes.").format(t=total, r=total - pendientes, p=pendientes)
