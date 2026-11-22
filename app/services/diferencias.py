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

«Diferencias narradas» (al final del módulo): un diff dice QUÉ líneas cambian,
pero no qué cambia DENTRO de una línea; con lector hay que leer las dos
versiones y compararlas de memoria. Aquí se numeran los grupos de cambios, se
emparejan las líneas eliminadas con las añadidas que las sustituyen, se
describe la diferencia palabra a palabra y se hacen visibles los caracteres
que el lector no anuncia (controles, espacios raros y bidireccionales).
"""

from __future__ import annotations

import bisect
import builtins
import difflib
import re
import unicodedata
from dataclasses import dataclass, field

AÑADIDA = "añadida"
ELIMINADA = "eliminada"
CONTEXTO = "sin cambios"
BLOQUE = "bloque"
ARCHIVO = "archivo"
AVISO = "aviso"

# Los tipos y los estados son claves (se comparan): se traducen solo al mostrarlos.
#: Estado de un archivo dentro de una frase («ruta: modificado, …»).
_ESTADOS_EN_FRASE = {
	"modificado": N_("modificado"), "añadido": N_("añadido"), "eliminado": N_("eliminado"), "renombrado": N_("renombrado"),
}

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
			ruta=self.ruta, estado=_(_ESTADOS_EN_FRASE.get(self.estado, self.estado)), a=self.añadidas, e=self.eliminadas
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

	for linea in _lineas_del_diff(texto):
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
			if linea[4:] == "/dev/null":
				# Sin «new file mode» (diff que no viene de git) es la única pista de un archivo nuevo.
				actual.estado = "añadido"
			elif not actual.ruta_antigua:
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
	while 0 <= indice < len(lineas) and _en_cambio(lineas, indice):
		indice += paso
	while 0 <= indice < len(lineas) and not _en_cambio(lineas, indice):
		indice += paso
	if not 0 <= indice < len(lineas):
		return None
	if hacia_atras:
		while indice - 1 >= 0 and _en_cambio(lineas, indice - 1):
			indice -= 1
	return indice


def _en_cambio(lineas: list[LineaDiff], indice: int) -> bool:
	"""La línea forma parte de un grupo de cambios.

	El aviso «Sin salto de línea al final del archivo» que git pone entre la
	última línea eliminada y su sustituta no corta el grupo: si lo cortara,
	cambiar la última línea de un archivo sin salto final contaría como dos
	cambios y la eliminada se quedaría sin pareja.
	"""
	linea = lineas[indice]
	if linea.es_cambio:
		return True
	return (linea.tipo == AVISO and linea.indice_bloque >= 0 and 0 < indice < len(lineas) - 1
		and lineas[indice - 1].es_cambio and lineas[indice + 1].es_cambio)


def _lineas_del_diff(texto: str) -> list[str]:
	"""Parte el diff solo por «\\n» y quita el «\\r» final de Windows.

	``str.splitlines`` también corta en U+2028, U+0085, el salto de página y
	otros separadores: una línea de código que los llevara se partiría en dos
	y el carácter, justo el que hay que enseñar, desaparecería.
	"""
	filas = (texto or "").split("\n")
	if filas and filas[-1] == "":
		filas.pop()
	return [fila[:-1] if fila.endswith("\r") else fila for fila in filas]


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
		salida.append(hacer_visibles(archivo.resumen()))
		for linea in archivo.lineas:
			if linea.tipo == BLOQUE:
				salida.append(f"  {hacer_visibles(linea.texto)}")
			elif linea.tipo == AVISO:
				salida.append(f"  {linea.texto}")
			else:
				salida.append(f"  {linea.nombre_tipo()} {linea.numero()}: {hacer_visibles(linea.texto)}")
		salida.append("")
	return "\n".join(salida)


# ════════════════════════════════════════════════════════════════════════════
# Caracteres invisibles
# ════════════════════════════════════════════════════════════════════════════

#: Controles sin nombre en ``unicodedata`` (los C0 y C1 no lo tienen).
_NOMBRES_CONTROL = {
	0x00: "NULL", 0x07: "BELL", 0x08: "BACKSPACE", 0x0A: "LINE FEED", 0x0B: "LINE TABULATION",
	0x0C: "FORM FEED", 0x0D: "CARRIAGE RETURN", 0x1B: "ESCAPE", 0x7F: "DELETE", 0x85: "NEXT LINE",
}

#: Marcas que cambian la dirección del texto: con ellas el código que se ve no
#: es el que se ejecuta (ataque «Trojan Source»), por eso tienen aviso propio.
BIDIRECCIONALES = frozenset(
	[chr(c) for c in range(0x202A, 0x202F)] + [chr(c) for c in range(0x2066, 0x206A)] + ["‎", "‏", "؜"]
)

#: Controles (salvo el tabulador), formato (ancho cero, bidireccionales, BOM,
#: guion virtual...) y separadores que no son el espacio normal.
_CATEGORIAS_INVISIBLES = frozenset({"Cc", "Cf", "Zs", "Zl", "Zp"})


def es_invisible(caracter: str) -> bool:
	"""El carácter no se ve o el lector no lo anuncia, aunque cambia el significado de la línea."""
	if caracter in ("\t", " "):
		return False
	return unicodedata.category(caracter) in _CATEGORIAS_INVISIBLES


def nombre_invisible(caracter: str) -> str:
	"""«U+202E RIGHT-TO-LEFT OVERRIDE» (el nombre Unicode es el que se busca en la web)."""
	codigo = ord(caracter)
	nombre = unicodedata.name(caracter, "") or _NOMBRES_CONTROL.get(codigo, "CONTROL")
	return f"U+{codigo:04X} {nombre}"


def tiene_invisibles(texto: str) -> bool:
	# ``isprintable`` descarta en C la inmensa mayoría de las líneas sin mirar carácter a carácter.
	return not texto.isprintable() and any(es_invisible(c) for c in texto)


def invisibles(texto: str) -> list[str]:
	"""Nombres de los caracteres invisibles de ``texto``, sin repetir y en orden de aparición."""
	if texto.isprintable():
		return []
	return list(dict.fromkeys(nombre_invisible(c) for c in texto if es_invisible(c)))


def hacer_visibles(texto: str) -> str:
	"""Sustituye cada carácter invisible por «<U+202E RIGHT-TO-LEFT OVERRIDE>»."""
	if texto.isprintable():
		return texto
	return "".join(f"<{nombre_invisible(c)}>" if es_invisible(c) else c for c in texto)


def texto_visible(texto: str) -> str:
	"""Texto de una línea para mostrar o leer: con los invisibles a la vista y sin filas mudas."""
	visible = hacer_visibles(texto)
	# ``strip`` también quita el espacio no separable: por eso se mira el texto YA hecho visible.
	return visible if visible.strip() else _("(línea en blanco)")


def aviso_invisibles(texto: str) -> str:
	"""Aviso breve para decir al llegar a la línea («» si no hay nada que avisar)."""
	if not tiene_invisibles(texto):
		return ""
	if any(c in BIDIRECCIONALES for c in texto):
		return _("Contiene caracteres invisibles que cambian la dirección del texto.")
	return _("Contiene caracteres invisibles.")


# ════════════════════════════════════════════════════════════════════════════
# Resumen
# ════════════════════════════════════════════════════════════════════════════

_ESTADOS = {"modificado": N_("Modificado"), "añadido": N_("Nuevo"), "eliminado": N_("Borrado"), "renombrado": N_("Renombrado")}


def resumen_archivo(archivo: ArchivoDiff, posicion: int, total: int) -> str:
	"""«Archivo 1 de 3: ruta. Modificado. 5 añadidas y 1 eliminada.»"""
	estado = _(_ESTADOS.get(archivo.estado, archivo.estado.capitalize()))
	renombrado = archivo.ruta_antigua and archivo.ruta_antigua != archivo.ruta and archivo.estado not in ("añadido", "eliminado")
	if renombrado:
		estado = _("Renombrado desde {r}").format(r=hacer_visibles(archivo.ruta_antigua))
	if archivo.binario:
		cambios = _("Archivo binario")
	else:
		partes = []
		if archivo.añadidas:
			partes.append(ngettext("{n} añadida", "{n} añadidas", archivo.añadidas).format(n=archivo.añadidas))
		if archivo.eliminadas:
			partes.append(ngettext("{n} eliminada", "{n} eliminadas", archivo.eliminadas).format(n=archivo.eliminadas))
		cambios = _y(partes) if partes else _("Sin líneas cambiadas")
	return _("Archivo {p} de {t}: {r}. {e}. {c}.").format(
		p=posicion, t=total, r=hacer_visibles(archivo.ruta) or _("(sin nombre)"), e=estado, c=cambios)


def resumen_diff(archivos: list[ArchivoDiff], total_cambios: int | None = None) -> list[str]:
	"""Primera frase con el total y después una por archivo (ver ``resumen_archivo``)."""
	if not archivos:
		return [_("No hay diferencias.")]
	if total_cambios is None:
		total_cambios = len(grupos_de_cambios(aplanar(archivos)))
	añadidas = sum(a.añadidas for a in archivos)
	eliminadas = sum(a.eliminadas for a in archivos)
	total = _("{archivos} con {cambios}: {a} y {e}.").format(
		archivos=ngettext("{n} archivo cambiado", "{n} archivos cambiados", len(archivos)).format(n=len(archivos)),
		cambios=ngettext("{n} cambio", "{n} cambios", total_cambios).format(n=total_cambios),
		a=ngettext("{n} línea añadida", "{n} líneas añadidas", añadidas).format(n=añadidas),
		e=ngettext("{n} eliminada", "{n} eliminadas", eliminadas).format(n=eliminadas),
	)
	return [total] + [resumen_archivo(archivo, posicion, len(archivos)) for posicion, archivo in enumerate(archivos, 1)]


def archivo_de(lineas: list[LineaDiff], indice: int) -> int | None:
	"""Posición (desde 0) del archivo al que pertenece la línea ``indice`` de ``aplanar``."""
	posicion = -1
	for linea in lineas[: indice + 1]:
		if linea.tipo == ARCHIVO:
			posicion += 1
	return posicion if posicion >= 0 else None


# ════════════════════════════════════════════════════════════════════════════
# Grupos de cambios y parejas
# ════════════════════════════════════════════════════════════════════════════

#: Parecido mínimo (0 a 1, por caracteres) para considerar que una línea añadida sustituye a una eliminada
#: cuando no se pueden emparejar una a una.
UMBRAL_PAREJA = 0.5
#: Por encima de tantas comparaciones en un grupo se empareja por orden (la interfaz no debe notarlo).
LIMITE_COMPARACIONES = 400
#: Solo se comparan los primeros caracteres de cada línea (líneas minificadas de miles de caracteres).
LARGO_COMPARADO = 500


@dataclass
class GrupoCambio:
	"""Líneas añadidas y eliminadas seguidas (lo que salta F8), con índices de ``aplanar``."""

	numero: int
	inicio: int
	fin: int
	archivo: str = ""
	eliminadas: list[int] = field(default_factory=list)
	añadidas: list[int] = field(default_factory=list)
	#: ``(eliminada, añadida)``; se calculan la primera vez que se piden (``parejas_del_grupo``).
	parejas: list[tuple[int, int]] | None = field(default=None, repr=False)


def grupos_de_cambios(lineas: list[LineaDiff]) -> list[GrupoCambio]:
	"""Numera los grupos de cambios (los mismos a los que salta ``siguiente_cambio``)."""
	grupos: list[GrupoCambio] = []
	indice = 0
	while indice < len(lineas):
		if not _en_cambio(lineas, indice):
			indice += 1
			continue
		grupo = GrupoCambio(len(grupos) + 1, indice, indice, lineas[indice].archivo)
		while indice < len(lineas) and _en_cambio(lineas, indice):
			if lineas[indice].tipo == ELIMINADA:
				grupo.eliminadas.append(indice)
			elif lineas[indice].tipo == AÑADIDA:
				grupo.añadidas.append(indice)
			grupo.fin = indice
			indice += 1
		grupos.append(grupo)
	return grupos


def grupo_de(grupos: list[GrupoCambio], indice: int) -> GrupoCambio | None:
	"""Grupo que contiene la línea ``indice`` (o ``None`` si no está en ninguno)."""
	posicion = bisect.bisect_right(grupos, indice, key=lambda g: g.inicio) - 1
	if posicion >= 0 and grupos[posicion].inicio <= indice <= grupos[posicion].fin:
		return grupos[posicion]
	return None


def nombre_cambio(grupo: GrupoCambio, total: int) -> str:
	return _("Cambio {n} de {t}").format(n=grupo.numero, t=total)


def _similitud(a: str, b: str) -> float:
	a, b = a.strip()[:LARGO_COMPARADO], b.strip()[:LARGO_COMPARADO]
	if a == b:
		return 1.0
	comparador = difflib.SequenceMatcher(None, a, b, autojunk=False)
	# Las cotas rápidas descartan casi todas las parejas imposibles sin el cálculo completo.
	if comparador.real_quick_ratio() < UMBRAL_PAREJA or comparador.quick_ratio() < UMBRAL_PAREJA:
		return 0.0
	return comparador.ratio()


def emparejar(eliminadas: list[str], añadidas: list[str]) -> list[tuple[int, int]]:
	"""Qué línea añadida sustituye a cada eliminada: ``[(i_eliminada, i_añadida)]`` en orden.

	1. Alineación que respeta el orden y suma el mayor parecido entre las
	   parejas que se parecen al menos ``UMBRAL_PAREJA`` (así, si se borra una
	   línea y se cambia la siguiente, no se empareja la borrada con la cambiada).
	2. Entre dos parejas, si quedan tantas eliminadas como añadidas, se
	   emparejan una a una aunque no se parezcan: es una línea reescrita.
	"""
	n, m = len(eliminadas), len(añadidas)
	if not n or not m:
		return []
	if n * m > LIMITE_COMPARACIONES:
		return [(k, k) for k in range(min(n, m)) if n == m or _similitud(eliminadas[k], añadidas[k]) >= UMBRAL_PAREJA]
	puntos = [[_similitud(a, b) for b in añadidas] for a in eliminadas]
	mejor = [[0.0] * (m + 1) for _fila in range(n + 1)]
	for i in range(1, n + 1):
		for j in range(1, m + 1):
			candidato = max(mejor[i - 1][j], mejor[i][j - 1])
			if puntos[i - 1][j - 1] >= UMBRAL_PAREJA:
				candidato = max(candidato, mejor[i - 1][j - 1] + puntos[i - 1][j - 1])
			mejor[i][j] = candidato
	parejas: list[tuple[int, int]] = []
	i, j = n, m
	while i and j:
		punto = puntos[i - 1][j - 1]
		if punto >= UMBRAL_PAREJA and mejor[i][j] == mejor[i - 1][j - 1] + punto:
			parejas.append((i - 1, j - 1))
			i, j = i - 1, j - 1
		elif mejor[i][j] == mejor[i - 1][j]:
			i -= 1
		else:
			j -= 1
	parejas.reverse()
	return _rellenar_huecos(parejas, n, m)


def _rellenar_huecos(parejas: list[tuple[int, int]], n: int, m: int) -> list[tuple[int, int]]:
	resultado: list[tuple[int, int]] = []
	anterior = (-1, -1)
	for siguiente_pareja in [*parejas, (n, m)]:
		huecos_e = range(anterior[0] + 1, siguiente_pareja[0])
		huecos_a = range(anterior[1] + 1, siguiente_pareja[1])
		if len(huecos_e) == len(huecos_a):
			resultado.extend(zip(huecos_e, huecos_a, strict=True))
		if siguiente_pareja != (n, m):
			resultado.append(siguiente_pareja)
		anterior = siguiente_pareja
	return resultado


def parejas_del_grupo(grupo: GrupoCambio, lineas: list[LineaDiff]) -> list[tuple[int, int]]:
	"""Parejas ``(índice eliminada, índice añadida)`` del grupo, calculadas una sola vez."""
	if grupo.parejas is None:
		locales = emparejar([lineas[i].texto for i in grupo.eliminadas], [lineas[i].texto for i in grupo.añadidas])
		grupo.parejas = [(grupo.eliminadas[a], grupo.añadidas[b]) for a, b in locales]
	return grupo.parejas


def pareja_de(grupos: list[GrupoCambio], lineas: list[LineaDiff], indice: int) -> int | None:
	"""Índice de la línea que forma pareja con ``indice`` (la que sustituye o a la que sustituye)."""
	grupo = grupo_de(grupos, indice)
	if grupo is None:
		return None
	for eliminada, añadida in parejas_del_grupo(grupo, lineas):
		if eliminada == indice:
			return añadida
		if añadida == indice:
			return eliminada
	return None


# ════════════════════════════════════════════════════════════════════════════
# Qué cambia dentro de una línea
# ════════════════════════════════════════════════════════════════════════════

_PALABRA = re.compile(r"\S+")
#: Si se conserva menos de esta parte del texto, se dice «línea reescrita» en vez de enumerar cambios.
UMBRAL_REESCRITA = 0.4
#: Cambios que se enumeran como mucho; del resto solo se dice cuántos quedan.
CAMBIOS_DICHOS = 4


def _y(partes: list[str]) -> str:
	if len(partes) <= 1:
		return "".join(partes)
	return _("{a} y {b}").format(a=", ".join(partes[:-1]), b=partes[-1])


def _nombrar_espacios(espacios: str) -> str:
	tabuladores = espacios.count("\t")
	normales = espacios.count(" ")
	otros = len(espacios) - tabuladores - normales
	partes = []
	if tabuladores:
		partes.append(ngettext("{n} tabulador", "{n} tabuladores", tabuladores).format(n=tabuladores))
	if normales:
		partes.append(ngettext("{n} espacio", "{n} espacios", normales).format(n=normales))
	if otros:
		partes.append(ngettext("{n} espacio especial", "{n} espacios especiales", otros).format(n=otros))
	return _y(partes)


def _cambio_de_sangria(antes: str, despues: str) -> str:
	sangria_a = antes[: len(antes) - len(antes.lstrip())]
	sangria_d = despues[: len(despues) - len(despues.lstrip())]
	if sangria_a == sangria_d:
		return ""
	if not sangria_a:
		return _("añade una sangría de {d}").format(d=_nombrar_espacios(sangria_d))
	if not sangria_d:
		return _("quita la sangría de {a}").format(a=_nombrar_espacios(sangria_a))
	return _("cambia la sangría de {a} a {d}").format(a=_nombrar_espacios(sangria_a), d=_nombrar_espacios(sangria_d))


def _frase(partes: list[str]) -> str:
	texto = "; ".join(p for p in partes if p)
	return texto[:1].upper() + texto[1:] + "." if texto else ""


def _describir_espacios(antes: str, despues: str) -> str:
	"""Las palabras son las mismas: solo pueden cambiar espacios (que el lector no dice)."""
	if antes == despues:
		return _("El texto se ve igual; puede cambiar el final de línea.")
	if not antes.strip() and not despues.strip():
		return _frase([_("solo cambian los espacios de una línea en blanco: de {a} a {d}").format(
			a=_nombrar_espacios(antes) or _("nada"), d=_nombrar_espacios(despues) or _("nada"))])
	partes = [_cambio_de_sangria(antes, despues)]
	if antes[len(antes.rstrip()):] != despues[len(despues.rstrip()):]:
		partes.append(_("cambian los espacios del final de la línea"))
	if antes.strip() != despues.strip():
		interior = _("cambian los espacios entre las palabras")
		if tiene_invisibles(antes) or tiene_invisibles(despues):
			interior += _(": antes «{a}», ahora «{d}»").format(a=hacer_visibles(antes.strip()), d=hacer_visibles(despues.strip()))
		partes.append(interior)
	return _("Solo cambian espacios: {p}.").format(p="; ".join(p for p in partes if p))


def _fragmento(texto: str, posiciones: list[tuple[int, int]], desde: int, hasta: int) -> str:
	"""Texto original de las palabras ``desde``..``hasta`` (con sus espacios interiores)."""
	return hacer_visibles(texto[posiciones[desde][0]:posiciones[hasta - 1][1]])


def describir_cambio(antes: str, despues: str) -> str:
	"""Qué cambia de ``antes`` a ``despues``, palabra a palabra, en una frase para el lector.

	«Cambia «timeout=30» por «timeout=60».», «Quita «, b».», «Añade «x» al
	final.»; «Línea reescrita.» si apenas queda nada de la original.
	"""
	posiciones_a = [m.span() for m in _PALABRA.finditer(antes)]
	posiciones_d = [m.span() for m in _PALABRA.finditer(despues)]
	palabras_a = [antes[i:j] for i, j in posiciones_a]
	palabras_d = [despues[i:j] for i, j in posiciones_d]
	if palabras_a == palabras_d:
		return _describir_espacios(antes, despues)
	comparador = difflib.SequenceMatcher(None, palabras_a, palabras_d, autojunk=False)
	operaciones = comparador.get_opcodes()
	iguales = 0
	for etiqueta, i1, i2, j1, j2 in operaciones:
		if etiqueta == "equal":
			iguales += sum(len(palabra) for palabra in palabras_a[i1:i2])
		elif etiqueta == "replace":
			# Dentro de una palabra cambiada también se conserva texto («acceso:» → «acceso:» con una
			# marca invisible): sin contarlo, una línea corta pasaría por reescrita. Las letras sueltas
			# que coinciden por casualidad no cuentan.
			bloques = difflib.SequenceMatcher(None, "".join(palabras_a[i1:i2]), "".join(palabras_d[j1:j2]),
				autojunk=False).get_matching_blocks()
			iguales += sum(bloque.size for bloque in bloques if bloque.size >= 2)
	total = max(sum(map(len, palabras_a)), sum(map(len, palabras_d)))
	if total and iguales / total < UMBRAL_REESCRITA:
		return _("Línea reescrita.")
	cambios = [op for op in operaciones if op[0] != "equal"]
	partes = []
	for etiqueta, i1, i2, j1, j2 in cambios[:CAMBIOS_DICHOS]:
		if etiqueta == "replace":
			partes.append(_("cambia «{a}» por «{d}»").format(
				a=_fragmento(antes, posiciones_a, i1, i2), d=_fragmento(despues, posiciones_d, j1, j2)))
		elif etiqueta == "delete":
			partes.append(_("quita «{a}»").format(a=_fragmento(antes, posiciones_a, i1, i2)))
		else:
			if i1 == 0:
				lugar = _("al principio")
			elif i1 == len(palabras_a):
				lugar = _("al final")
			else:
				lugar = _("después de «{p}»").format(p=hacer_visibles(palabras_a[i1 - 1]))
			partes.append(_("añade «{d}» {lugar}").format(d=_fragmento(despues, posiciones_d, j1, j2), lugar=lugar))
	resto = len(cambios) - CAMBIOS_DICHOS
	if resto > 0:
		partes.append(ngettext("y {n} cambio más", "y {n} cambios más", resto).format(n=resto))
	partes.append(_cambio_de_sangria(antes, despues))
	return _frase(partes)


def explicar_linea(lineas: list[LineaDiff], grupos: list[GrupoCambio], indice: int) -> str:
	"""Lo que dice Control+D sobre la línea ``indice``: con qué línea forma pareja y qué cambia."""
	if not 0 <= indice < len(lineas):
		return ""
	linea = lineas[indice]
	if linea.tipo == CONTEXTO:
		texto = _("Esta línea no ha cambiado.")
	elif not linea.es_cambio:
		texto = _("Sitúese en una línea añadida o eliminada para saber qué cambia en ella.")
	else:
		otra = pareja_de(grupos, lineas, indice)
		if otra is None:
			texto = (_("Línea nueva: no sustituye a ninguna línea eliminada.") if linea.tipo == AÑADIDA
				else _("Línea eliminada sin sustituta: ninguna línea añadida ocupa su lugar."))
		elif linea.tipo == AÑADIDA:
			antes = lineas[otra]
			texto = _("Sustituye a la antigua línea {n}. {d}").format(n=antes.antigua, d=describir_cambio(antes.texto, linea.texto))
		else:
			despues = lineas[otra]
			texto = _("La sustituye la nueva línea {n}. {d}").format(n=despues.nueva, d=describir_cambio(linea.texto, despues.texto))
	nombres = invisibles(linea.texto)
	if nombres:
		texto += " " + _("Caracteres invisibles: {l}.").format(l=", ".join(nombres))
	return texto


def resumen_en(archivos: list[ArchivoDiff], lineas: list[LineaDiff], grupos: list[GrupoCambio], indice: int) -> str:
	"""Lo que dice Control+R: el total, el archivo de la línea ``indice`` y en qué cambio está."""
	partes = [resumen_diff(archivos, len(grupos))[0]]
	posicion = archivo_de(lineas, indice) if lineas else None
	if posicion is not None and posicion < len(archivos):
		partes.append(resumen_archivo(archivos[posicion], posicion + 1, len(archivos)))
	grupo = grupo_de(grupos, indice)
	if grupo is not None:
		partes.append(nombre_cambio(grupo, len(grupos)) + ".")
	return " ".join(partes)


# ════════════════════════════════════════════════════════════════════════════
# Vista narrada
# ════════════════════════════════════════════════════════════════════════════

def _rango(desde: int, hasta: int) -> str:
	if desde == hasta:
		return _("línea {n}").format(n=desde)
	return _("líneas {a} a {b}").format(a=desde, b=hasta)


def _lugar_del_grupo(grupo: GrupoCambio, lineas: list[LineaDiff]) -> str:
	antiguas = [lineas[i].antigua for i in grupo.eliminadas if lineas[i].antigua is not None]
	nuevas = [lineas[i].nueva for i in grupo.añadidas if lineas[i].nueva is not None]
	partes = []
	if antiguas:
		partes.append(_("antes {r}").format(r=_rango(min(antiguas), max(antiguas))))
	if nuevas:
		partes.append(_("ahora {r}").format(r=_rango(min(nuevas), max(nuevas))))
	return ", ".join(partes)


def _narrar_grupo(grupo: GrupoCambio, lineas: list[LineaDiff], total: int) -> list[str]:
	sustituta = dict(parejas_del_grupo(grupo, lineas))
	emparejadas = set(sustituta.values())
	lugar = _lugar_del_grupo(grupo, lineas)
	salida = [f"{nombre_cambio(grupo, total)}, {lugar}:" if lugar else f"{nombre_cambio(grupo, total)}:"]
	for indice in range(grupo.inicio, grupo.fin + 1):
		linea = lineas[indice]
		if linea.tipo == AVISO:
			salida.append(f"  {linea.texto}")
		elif indice in emparejadas:
			continue
		elif linea.tipo == ELIMINADA and indice in sustituta:
			nueva = lineas[sustituta[indice]]
			numero = str(linea.antigua) if linea.antigua == nueva.nueva else _("{a} (ahora {n})").format(a=linea.antigua, n=nueva.nueva)
			salida.append("  " + _("Cambió la línea {n}: {t}").format(n=numero, t=texto_visible(linea.texto)))
			salida.append("  " + _("Por: {t}").format(t=texto_visible(nueva.texto)))
			salida.append("  " + describir_cambio(linea.texto, nueva.texto))
		elif linea.tipo == ELIMINADA:
			salida.append("  " + _("Eliminada la línea {n}: {t}").format(n=linea.antigua, t=texto_visible(linea.texto)))
		else:
			salida.append("  " + _("Añadida la línea {n}: {t}").format(n=linea.nueva, t=texto_visible(linea.texto)))
	return salida


def texto_narrado(archivos: list[ArchivoDiff]) -> str:
	"""El diff contado para leerlo seguido: resumen y después cada cambio con sus parejas.

	Puede tardar con diffs enormes (empareja todas las líneas): la interfaz lo
	llama en segundo plano.
	"""
	lineas = aplanar(archivos)
	grupos = grupos_de_cambios(lineas)
	salida = resumen_diff(archivos, len(grupos))
	por_inicio = {grupo.inicio: grupo for grupo in grupos}
	posicion = 0
	indice = 0
	while indice < len(lineas):
		if lineas[indice].tipo == ARCHIVO:
			salida += ["", resumen_archivo(archivos[posicion], posicion + 1, len(archivos))]
			posicion += 1
		elif indice in por_inicio:
			grupo = por_inicio[indice]
			salida += ["", *_narrar_grupo(grupo, lineas, len(grupos))]
			indice = grupo.fin + 1
			continue
		indice += 1
	return "\n".join(salida)
