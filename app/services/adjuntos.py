"""Adjuntar archivos de texto a issues, pull requests, discusiones y comentarios.

La API de GitHub no permite subir adjuntos (el botón de la web usa un servicio
interno que exige la sesión del navegador), así que hay dos caminos:

- **Dentro del texto**: el contenido va en un bloque de código plegado
  (``<details>``), que en GitHub se ve como «nombre.log» y se despliega al pulsar.
  Sirve mientras quepa en el límite de 65 536 caracteres del cuerpo.
- **Como gist secreto**: el archivo se sube a un gist que no aparece en los
  listados, y el texto lleva solo su enlace. Para registros largos.

Las imágenes y demás archivos binarios no se pueden subir sin la web; quien los
necesite los arrastra luego en el navegador.

Aquí solo hay lógica sin interfaz, para poder probarla sin ventanas.
"""

from __future__ import annotations

import builtins
import html
import os
import re

#: Límite de caracteres del cuerpo de una issue o un comentario en GitHub.
LIMITE_CUERPO = 65536
#: Tamaño máximo que se lee de un archivo (un gist no admite mucho más).
LIMITE_ARCHIVO = 10 * 1024 * 1024

#: Lenguaje del bloque de código según la extensión (para el resaltado de GitHub).
_LENGUAJES = {
	".py": "python", ".js": "javascript", ".ts": "typescript", ".json": "json", ".xml": "xml", ".html": "html",
	".htm": "html", ".css": "css", ".md": "markdown", ".yml": "yaml", ".yaml": "yaml", ".toml": "toml",
	".ini": "ini", ".cfg": "ini", ".sh": "bash", ".bat": "batch", ".cmd": "batch", ".ps1": "powershell",
	".c": "c", ".h": "c", ".cpp": "cpp", ".cs": "csharp", ".java": "java", ".kt": "kotlin", ".go": "go",
	".rs": "rust", ".rb": "ruby", ".php": "php", ".sql": "sql", ".diff": "diff", ".patch": "diff",
	".csv": "csv",
}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorAdjunto(Exception):
	"""El archivo no se puede adjuntar; ``mensaje_usuario`` explica por qué."""

	def __init__(self, mensaje: str) -> None:
		super().__init__(mensaje)
		self.mensaje_usuario = mensaje


def leer_texto(ruta: str) -> str:
	"""Lee un archivo de texto y lo devuelve con saltos de línea ``\\n``.

	Prueba UTF-8 (con o sin BOM), UTF-16 con BOM y, si no, Windows-1252, que es
	como guardan sus registros muchos programas de Windows.

	:raises ErrorAdjunto: si es demasiado grande, está vacío o no es de texto.
	"""
	tamano = os.path.getsize(ruta)
	if tamano > LIMITE_ARCHIVO:
		raise ErrorAdjunto(_("El archivo ocupa más de 10 MB; GitHub no admite adjuntar tanto texto."))
	with open(ruta, "rb") as archivo:
		datos = archivo.read()
	if not datos.strip():
		raise ErrorAdjunto(_("El archivo está vacío."))
	texto = _decodificar(datos)
	if texto is None:
		raise ErrorAdjunto(_(
			"No es un archivo de texto. GitHub solo deja subir imágenes y otros archivos binarios desde su web: "
			"envíe el texto y, después, ábralo en el navegador con Control+B para arrastrar el archivo."
		))
	return texto.replace("\r\n", "\n").replace("\r", "\n")


def _decodificar(datos: bytes) -> str | None:
	if datos.startswith((b"\xff\xfe", b"\xfe\xff")):
		try:
			return datos.decode("utf-16")
		except UnicodeDecodeError:
			return None
	# Un byte nulo no aparece en texto UTF-8 ni Windows-1252: es un binario.
	if b"\x00" in datos[:65536]:
		return None
	try:
		return datos.decode("utf-8-sig")
	except UnicodeDecodeError:
		pass
	texto = datos.decode("cp1252", errors="replace")
	# Muchos caracteres de control raros: probablemente binario sin bytes nulos.
	raros = sum(1 for c in texto[:65536] if ord(c) < 32 and c not in "\t\n\r\f")
	return None if raros > len(texto[:65536]) // 100 else texto


def lenguaje(nombre: str) -> str:
	"""Lenguaje del bloque de código para ``nombre`` (``text`` si no se conoce)."""
	return _LENGUAJES.get(os.path.splitext(nombre)[1].lower(), "text")


def _valla(texto: str) -> str:
	"""Comillas invertidas para abrir el bloque: más que la racha más larga del texto."""
	rachas = [len(r) for r in re.findall(r"`+", texto)]
	return "`" * max(3, max(rachas, default=0) + 1)


def bloque_plegado(nombre: str, texto: str, tamano_texto: str = "") -> str:
	"""Markdown con el contenido en un bloque de código plegado bajo el nombre del archivo."""
	resumen = html.escape(nombre) + (f" ({tamano_texto})" if tamano_texto else "")
	valla = _valla(texto)
	cuerpo = texto if texto.endswith("\n") else texto + "\n"
	return f"<details>\n<summary>{resumen}</summary>\n\n{valla}{lenguaje(nombre)}\n{cuerpo}{valla}\n\n</details>\n"


def cabe_en_cuerpo(cuerpo_actual: str, bloque: str) -> bool:
	"""``True`` si el texto con el bloque añadido sigue dentro del límite de GitHub."""
	return len(cuerpo_actual) + len(bloque) + 2 <= LIMITE_CUERPO


def enlace_gist(nombre: str, url: str) -> str:
	"""Línea de Markdown que enlaza el archivo subido a un gist."""
	nombre_seguro = nombre.replace("[", "\\[").replace("]", "\\]")
	return _("Archivo adjunto: [{n}]({u})").format(n=nombre_seguro, u=url) + "\n"


def url_archivo_gist(gist: dict, nombre: str) -> str:
	"""Enlace web al gist (al archivo concreto si se puede)."""
	url = gist.get("html_url") or ""
	if not url:
		raise ErrorAdjunto(_("GitHub no devolvió la dirección del gist."))
	ancla = re.sub(r"[^a-z0-9]+", "-", nombre.lower()).strip("-")
	return f"{url}#file-{ancla}" if ancla else url


def insertar(cuerpo: str, posicion: int, bloque: str) -> tuple[str, int]:
	"""Inserta ``bloque`` en ``posicion`` dejándolo en líneas propias.

	Devuelve el texto nuevo y la posición del cursor justo después del bloque.
	"""
	posicion = max(0, min(posicion, len(cuerpo)))
	antes, despues = cuerpo[:posicion], cuerpo[posicion:]
	if antes and not antes.endswith("\n\n"):
		antes += "\n" if antes.endswith("\n") else "\n\n"
	if despues and not despues.startswith("\n"):
		bloque += "\n"
	return antes + bloque + despues, len(antes) + len(bloque)
