"""Compilación con cx_Freeze: ``python setup_cx.py build`` (``--debug`` = con consola).

Genera ``build/GithubAccesible`` con:

- El ejecutable sin consola (``base="gui"``), con autor y versión en sus metadatos.
- Los runtimes de Visual C++ (``include_msvcr``) y ``WebView2Loader.dll``, para que
  arranque en un Windows recién instalado sin redistribuibles.
- Una carpeta ``data`` LIMPIA por lista blanca: sonidos, documentación, iconos y
  traducciones. Nunca configuración, registros ni bases de datos.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from cx_Freeze import Executable, setup

RAIZ = Path(__file__).resolve().parent

# ── CONFIGURACIÓN DEL PROYECTO ───────────────────────────────────────────────

NOMBRE_APP = "GithubAccesible"
EJECUTABLE = "GithubAccesible.exe"
DESCRIPCION = "GitHub Accesible: GitHub y git completos, accesibles con lector de pantalla"
ICONO = RAIZ / "data" / "icons" / "app.ico"

# Subcarpetas de data/ que SÍ se distribuyen (lista blanca).
DATA_DISTRIBUIBLE = ["sounds", "docs", "icons", "locales", "bin"]
# Subcarpetas que JAMÁS pueden distribuirse: si alguien las añade arriba, se para.
DATA_PROHIBIDO = {"config", "logs", "db", "cache", "temp", "sessions", "backups", "downloads"}
# Archivos que nunca se copian aunque estén en una carpeta distribuible.
PATRONES_EXCLUIDOS = ("__pycache__", ".ruff_cache", ".pytest_cache", "*.pyc", "*.log", "*.tmp", "*.bak", "*.db", "*.key", ".gitkeep", "desktop.ini", "Thumbs.db")

PAQUETES = ["wx", "app", "markdown", "requests", "certifi", "cryptography", "urllib3", "charset_normalizer", "idna", "sqlite3"]
# accessible_output2 se importa de forma diferida: sus dependencias hay que nombrarlas.
PAQUETES_OPCIONALES = ["accessible_output2", "libloader", "platform_utils", "comtypes", "win32com", "pythoncom"]
# Documentación de usuario: la fuente está en docs/ y viaja a data/docs/.
ARCHIVOS_EXTRA = [(f"docs/{nombre}", f"data/docs/{nombre}") for nombre in ("manual.md", "teclas.md", "changelog.md")]
ARCHIVOS_EXTRA += [("LICENSE", "LICENSE.txt"), ("README.md", "README.md")]
EXCLUDES = ["tkinter", "unittest", "pydoc_data", "pip", "pytest", "_pytest", "ruff", "cx_Freeze", "tests", "nacl"]

# ─────────────────────────────────────────────────────────────────────────────

DESTINO = RAIZ / "build" / NOMBRE_APP


def leer_constante(nombre: str, por_defecto: str) -> str:
	"""Lee una constante de version.py con una expresión regular: importar la app arrastraría wx."""
	texto = (RAIZ / "app" / "core" / "version.py").read_text(encoding="utf-8")
	coincidencia = re.search(rf"{nombre}\s*=\s*[\"']([^\"']+)[\"']", texto)
	return coincidencia.group(1) if coincidencia else por_defecto


def _excluido(ruta: Path) -> bool:
	return any(Path(parte).match(patron) for parte in ruta.parts for patron in PATRONES_EXCLUIDOS)


def archivos_de_data() -> list[tuple[str, str]]:
	"""Lista ``include_files`` de data/ archivo a archivo, filtrando lo excluido."""
	prohibidas = DATA_PROHIBIDO.intersection(DATA_DISTRIBUIBLE)
	if prohibidas:
		raise SystemExit("ERROR: DATA_DISTRIBUIBLE incluye carpetas personales: " + ", ".join(sorted(prohibidas)))
	resultado = []
	for nombre in DATA_DISTRIBUIBLE:
		carpeta = RAIZ / "data" / nombre
		for archivo in sorted(carpeta.rglob("*")) if carpeta.is_dir() else []:
			relativo = archivo.relative_to(RAIZ)
			if archivo.is_file() and not _excluido(relativo):
				resultado.append((str(archivo), relativo.as_posix()))
	return resultado


def corregir_abi_estable(destino: Path) -> list[str]:
	"""Pone junto al ejecutable las DLL del ABI estable que corresponden a ESTE Python.

	Python 3.15 trae dos ``python3t.dll``: el de su carpeta raíz reenvía a
	``python315t.dll`` (el intérprete sin GIL) y el de ``abi3t-compat`` reenvía a
	``python315.dll`` (el normal). cx_Freeze copia el de la raíz, así que las
	extensiones «abi3t», como ``cryptography`` (verifica la firma de las
	actualizaciones), no cargan en la versión compilada: «DLL load failed».
	También se añade ``python3.dll`` si falta (extensiones «abi3»).
	"""
	import sysconfig

	if sysconfig.get_config_var("Py_GIL_DISABLED"):
		return []  # en un Python sin GIL, los de la raíz son los correctos
	base = Path(sys.base_prefix)
	hechos = []
	compat = base / "abi3t-compat" / "python3t.dll"
	if compat.is_file():
		shutil.copy2(compat, destino / "python3t.dll")
		hechos.append("python3t.dll (de abi3t-compat)")
	python3 = base / "python3.dll"
	if python3.is_file() and not (destino / "python3.dll").exists():
		shutil.copy2(python3, destino / "python3.dll")
		hechos.append("python3.dll")
	return hechos


def copiar_cargador_webview(destino: Path) -> list[str]:
	"""Deja ``WebView2Loader.dll`` junto al ejecutable, además de en ``lib/wx``.

	wxWidgets lo busca por nombre con el orden de búsqueda de Windows, que empieza por
	la carpeta del ``.exe``. Sin este archivo, Edge no estaría disponible aunque el
	sistema tenga WebView2 y la aplicación caería al modo texto.
	"""
	origen = destino / "lib" / "wx" / "WebView2Loader.dll"
	if not origen.is_file():
		import wx

		origen = Path(wx.__file__).resolve().parent / "WebView2Loader.dll"
	if not origen.is_file():
		raise SystemExit("ERROR: no se encuentra WebView2Loader.dll en el paquete wx.")
	shutil.copy2(origen, destino / "WebView2Loader.dll")
	return ["WebView2Loader.dll"]


def _disponible(modulo: str) -> bool:
	import importlib.util

	return importlib.util.find_spec(modulo) is not None


if __name__ == "__main__":
	MODO_DEBUG = "--debug" in sys.argv
	if MODO_DEBUG:
		sys.argv.remove("--debug")
	if any(orden.startswith("build") for orden in sys.argv[1:]) and DESTINO.exists():
		# Si se probó la copia compilada, su data/ tiene configuración y registros.
		print(f"Limpiando la compilación anterior: {DESTINO}")
		shutil.rmtree(DESTINO)

	AUTOR = leer_constante("AUTOR", "")
	setup(
		name=NOMBRE_APP,
		version=leer_constante("APP_VERSION", "0.0.0"),
		description=DESCRIPCION,
		author=AUTOR,
		options={
			"build_exe": {
				"build_exe": str(DESTINO),
				"packages": PAQUETES + [p for p in PAQUETES_OPCIONALES if _disponible(p)],
				"excludes": EXCLUDES,
				"include_files": archivos_de_data() + [(str(RAIZ / o), d) for o, d in ARCHIVOS_EXTRA if (RAIZ / o).is_file()],
				"include_msvcr": True,
				# Trazas con rutas relativas, sin las carpetas del equipo donde se compiló.
				"replace_paths": [("*", "")],
				# optimize=2 quita las docstrings y rompe bibliotecas que las leen.
				"optimize": 1,
			}
		},
		executables=[
			Executable(
				script=str(RAIZ / "main.py"),
				base=None if MODO_DEBUG else "gui",
				target_name=EJECUTABLE,
				icon=str(ICONO) if ICONO.is_file() else None,
				copyright=f"© 2026 {AUTOR}",
			),
		],
	)
	if any(orden.startswith("build") for orden in sys.argv[1:]) and DESTINO.is_dir():
		for hecho in corregir_abi_estable(DESTINO):
			print(f"ABI estable: copiado {hecho}")
		for hecho in copiar_cargador_webview(DESTINO):
			print(f"Edge: copiado {hecho}")
