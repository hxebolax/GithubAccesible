"""Análisis de diferencias unificadas (diff) para leerlas de forma accesible (sin wx).

Leer un diff en la web con lector de pantalla es de lo más pedido y de lo
peor resuelto: los signos «+» y «-» se pierden, no se sabe en qué línea del
archivo se está y saltar al siguiente cambio es imposible. Aquí se convierte
el texto del diff en una lista de ``LineaDiff`` con:

- tipo explícito (añadida, eliminada, sin cambios, cabecera de bloque, aviso),
- número de línea antiguo y nuevo,
- archivo al que pertenece,
- posición en el diff del archivo (la que pide la API para comentar en línea).

La interfaz la muestra en una lista accesible y ofrece saltar al siguiente
cambio, bloque o archivo, con un sonido distinto para añadidas y eliminadas.
"""

from __future__ import annotations

import builtins
import re
from dataclasses import dataclass, field

AÑADIDA = "añadida"
ELIMINADA = "eliminada"
CONTEXTO = "sin cambios"
BLOQUE = "bloque"
ARCHIVO = "archivo"
AVISO = "aviso"

_CABECERA_BLOQUE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
_DIFF_GIT = re.compile(r'^diff --git "?a/(.+?)"? "?b/(.+?)"?$')


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class LineaDiff:
	tipo: str
	texto: str
	archivo: str = ""
	antigua: int | None = None
	nueva: int | None = None
	posicion: int | None = None
	indice_bloque: int = -1

	@property
	def es_cambio(self) -> bool:
		return self.tipo in (AÑADIDA, ELIMINADA)

	def nombre_tipo(self) -> str:
		return {
			AÑADIDA: _("Añadida"), ELIMINADA: _("Eliminada"), CONTEXTO: _("Sin cambios"),
			BLOQUE: _("Bloque"), ARCHIVO: _("Archivo"), AVISO: _("Aviso"),
		}.get(self.tipo, self.tipo)

	def numero(self) -> str:
		"""Número de línea para mostrar: el nuevo, o el antiguo en las eliminadas."""
		if self.tipo == ELIMINADA:
			return str(self.antigua or "")
		return str(self.nueva or self.antigua or "")


@dataclass
class ArchivoDiff:
	ruta: str
	ruta_antigua: str = ""
	estado: str = "modificado"
	añadidas: int = 0
	eliminadas: int = 0
	binario: bool = False
	lineas: list[LineaDiff] = field(default_factory=list)

	def resumen(self) -> str:
		texto = _("{ruta}: {estado}, {a} añadidas y {e} eliminadas").format(
			ruta=self.ruta, estado=_(self.estado), a=self.añadidas, e=self.eliminadas
		)
		if self.ruta_antigua and self.ruta_antigua != self.ruta:
			texto += " " + _("(antes {r})").format(r=self.ruta_antigua)
		if self.binario:
			texto += " " + _("(archivo binario)")
		return texto


def analizar(texto: str, archivo_por_defecto: str = "") -> list[ArchivoDiff]:
	"""Convierte un diff unificado (de git o de la API de GitHub) en archivos y líneas.

	Admite tanto el diff completo de ``git diff`` (con «diff --git») como el
	``patch`` de un solo archivo que da la API (empieza directamente en «@@»).
	"""
	archivos: list[ArchivoDiff] = []
	actual: ArchivoDiff | None = None
	antigua = nueva = 0
	posicion = 0
	bloque = -1

	def nuevo_archivo(ruta: str, antigua_ruta: str = "") -> ArchivoDiff:
		nonlocal posicion, bloque
		posicion = 0
		bloque = -1
		elemento = ArchivoDiff(ruta, antigua_ruta)
		archivos.append(elemento)
		return elemento

	for linea in (texto or "").splitlines():
		coincidencia = _DIFF_GIT.match(linea)
		if coincidencia:
			actual = nuevo_archivo(coincidencia.group(2), coincidencia.group(1))
			continue
		if actual is None:
			actual = nuevo_archivo(archivo_por_defecto)
		if linea.startswith("new file mode"):
			actual.estado = "añadido"
			continue
		if linea.startswith("deleted file mode"):
			actual.estado = "eliminado"
			continue
		if linea.startswith("rename from "):
			actual.ruta_antigua = linea[12:]
			actual.estado = "renombrado"
			continue
		if linea.startswith("rename to "):
			actual.ruta = linea[10:]
			continue
		if linea.startswith("Binary files") or linea.startswith("GIT binary patch"):
			actual.binario = True
			actual.lineas.append(LineaDiff(AVISO, _("Archivo binario: no se muestran las diferencias."), actual.ruta))
			continue
		if linea.startswith(("index ", "similarity index", "dissimilarity index", "old mode", "new mode", "copy from", "copy to")):
			continue
		if linea.startswith("--- "):
			if linea[4:] != "/dev/null" and not actual.ruta_antigua:
				actual.ruta_antigua = linea[4:].removeprefix("a/")
			continue
		if linea.startswith("+++ "):
			if linea[4:] == "/dev/null":
				actual.estado = "eliminado"
			elif not actual.ruta:
				actual.ruta = linea[4:].removeprefix("b/")
			continue
		cabecera = _CABECERA_BLOQUE.match(linea)
		if cabecera:
			antigua = int(cabecera.group(1))
			nueva = int(cabecera.group(3))
			# La «posición» de la API cuenta desde la primera cabecera de bloque (que es la 0... la
			# siguiente línea es la 1); las cabeceras posteriores también cuentan.
			if bloque >= 0:
				posicion += 1
			bloque += 1
			contexto = cabecera.group(5).strip()
			descripcion = _("Líneas {a} y {n}").format(a=antigua, n=nueva)
			if contexto:
				descripcion += f": {contexto}"
			actual.lineas.append(LineaDiff(BLOQUE, descripcion, actual.ruta, antigua, nueva, posicion, bloque))
			continue
		if linea.startswith("\\"):
			actual.lineas.append(LineaDiff(AVISO, _("Sin salto de línea al final del archivo."), actual.ruta, indice_bloque=bloque))
			continue
		if bloque < 0:
			continue
		posicion += 1
		if linea.startswith("+"):
			actual.lineas.append(LineaDiff(AÑADIDA, linea[1:], actual.ruta, None, nueva, posicion, bloque))
			actual.añadidas += 1
			nueva += 1
		elif linea.startswith("-"):
			actual.lineas.append(LineaDiff(ELIMINADA, linea[1:], actual.ruta, antigua, None, posicion, bloque))
			actual.eliminadas += 1
			antigua += 1
		else:
			actual.lineas.append(LineaDiff(CONTEXTO, linea[1:] if linea.startswith(" ") else linea, actual.ruta, antigua, nueva, posicion, bloque))
			antigua += 1
			nueva += 1
	return [a for a in archivos if a.lineas or a.ruta or a.binario]


def aplanar(archivos: list[ArchivoDiff]) -> list[LineaDiff]:
	"""Todas las líneas seguidas, con una línea de tipo ARCHIVO al principio de cada archivo."""
	lineas: list[LineaDiff] = []
	for archivo in archivos:
		lineas.append(LineaDiff(ARCHIVO, archivo.resumen(), archivo.ruta))
		lineas.extend(archivo.lineas)
	return lineas


def siguiente(lineas: list[LineaDiff], desde: int, condicion, hacia_atras: bool = False) -> int | None:
	"""Índice de la siguiente línea que cumple ``condicion`` (o ``None``)."""
	rango = range(desde - 1, -1, -1) if hacia_atras else range(desde + 1, len(lineas))
	for indice in rango:
		if condicion(lineas[indice]):
			return indice
	return None


def siguiente_cambio(lineas: list[LineaDiff], desde: int, hacia_atras: bool = False) -> int | None:
	"""Salta al principio del siguiente grupo de cambios (no a cada línea del mismo grupo)."""
	indice = desde
	paso = -1 if hacia_atras else 1
	# Salir del grupo actual.
	while 0 <= indice < len(lineas) and lineas[indice].es_cambio:
		indice += paso
	while 0 <= indice < len(lineas) and not lineas[indice].es_cambio:
		indice += paso
	if not 0 <= indice < len(lineas):
		return None
	if hacia_atras:
		while indice - 1 >= 0 and lineas[indice - 1].es_cambio:
			indice -= 1
	return indice


def resumen_total(archivos: list[ArchivoDiff]) -> str:
	añadidas = sum(a.añadidas for a in archivos)
	eliminadas = sum(a.eliminadas for a in archivos)
	return _("{n} archivos cambiados, {a} líneas añadidas y {e} eliminadas.").format(
		n=len(archivos), a=añadidas, e=eliminadas
	)


def texto_legible(archivos: list[ArchivoDiff]) -> str:
	"""Versión en texto plano para leer seguido o copiar: cada línea con su tipo en palabras."""
	salida = []
	for archivo in archivos:
		salida.append(archivo.resumen())
		for linea in archivo.lineas:
			if linea.tipo == BLOQUE:
				salida.append(f"  {linea.texto}")
			elif linea.tipo == AVISO:
				salida.append(f"  {linea.texto}")
			else:
				salida.append(f"  {linea.nombre_tipo()} {linea.numero()}: {linea.texto}")
		salida.append("")
	return "\n".join(salida)
