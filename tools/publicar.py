"""Publica una versión: compila, empaqueta, firma, copia al servidor y crea la release de GitHub.

Uso (desde la raíz del proyecto)::

	.venv\\Scripts\\python.exe tools\\publicar.py                 (todo)
	.venv\\Scripts\\python.exe tools\\publicar.py --sin-compilar  (usa build/ tal cual)
	.venv\\Scripts\\python.exe tools\\publicar.py --sin-github    (solo el servidor)
	.venv\\Scripts\\python.exe tools\\publicar.py --sin-servidor  (solo GitHub)

Pasos:

1. ``setup_cx.py build`` (cx_Freeze, con runtimes de Visual C++ y WebView2Loader.dll).
2. ``tools/empaquetar.py``: verifica la compilación, crea ``GithubAccesible_vX.Y.Z.zip``
   y ``version.json`` (versión, archivo, sha256, tamaño, fecha) y lo FIRMA con la
   clave privada de ``tools/claves`` (sin firma, ninguna instalación lo aceptaría).
3. Comprueba la firma con la clave pública incrustada en el actualizador.
4. Copia el ZIP y el ``version.json`` a la carpeta sincronizada con el servidor
   (``CARPETA_SERVIDOR``), que se publica en https://xebolax.synology.me/GithubAccesible/.
5. Crea la release ``vX.Y.Z`` en GitHub con ``gh`` y sube los dos archivos (las
   instalaciones que actualizan desde GitHub leen ``releases/latest/download/version.json``).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
CARPETA_SERVIDOR = Path(r"C:\Users\xebol\SynologyDrive\web\GithubAccesible")
REPOSITORIO = "hxebolax/GithubAccesible"


def version() -> str:
	texto = (RAIZ / "app" / "core" / "version.py").read_text(encoding="utf-8")
	return re.search(r'APP_VERSION\s*=\s*"([^"]+)"', texto).group(1)


def ejecutar(orden: list[str], **opciones) -> None:
	print("> " + " ".join(orden))
	resultado = subprocess.run(orden, cwd=RAIZ, **opciones)
	if resultado.returncode != 0:
		raise SystemExit(f"Falló: {' '.join(orden)} (código {resultado.returncode})")


def notas(version_actual: str) -> str:
	"""Notas de la versión desde docs/changelog.md (sección «## Versión X»)."""
	texto = (RAIZ / "docs" / "changelog.md").read_text(encoding="utf-8")
	patron = re.compile(rf"^## Versión {re.escape(version_actual)}\b.*?$(.*?)(?=^## |\Z)", re.S | re.M)
	coincidencia = patron.search(texto)
	return coincidencia.group(1).strip() if coincidencia else f"Versión {version_actual}."


def comprobar_firma(ruta_json: Path) -> None:
	sys.path.insert(0, str(RAIZ))
	from app.services import actualizador

	manifiesto = json.loads(ruta_json.read_text(encoding="utf-8"))
	actualizador.verificar_firma(manifiesto, actualizador.CLAVES_PUBLICAS_ED25519)
	print("Firma del version.json correcta con la clave pública de la aplicación.")


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("--sin-compilar", action="store_true")
	analizador.add_argument("--sin-servidor", action="store_true")
	analizador.add_argument("--sin-github", action="store_true")
	opciones = analizador.parse_args(argumentos)
	actual = version()
	print(f"Publicando GitHub Accesible {actual}")
	if not opciones.sin_compilar:
		ejecutar([PYTHON, "setup_cx.py", "build"])
		ejecutar([PYTHON, str(RAIZ / "tools" / "empaquetar.py")])
	zip_ = RAIZ / "build" / f"GithubAccesible_v{actual}.zip"
	manifiesto = RAIZ / "build" / "version.json"
	if not zip_.is_file() or not manifiesto.is_file():
		raise SystemExit("No están el ZIP y el version.json en build/. Compile primero.")
	comprobar_firma(manifiesto)
	if not opciones.sin_servidor:
		CARPETA_SERVIDOR.mkdir(parents=True, exist_ok=True)
		shutil.copy2(zip_, CARPETA_SERVIDOR / zip_.name)
		# El manifiesto se copia el ÚLTIMO: así nadie ve una versión nueva cuyo ZIP aún no está.
		shutil.copy2(manifiesto, CARPETA_SERVIDOR / "version.json")
		print(f"Copiado al servidor: {CARPETA_SERVIDOR}")
	if not opciones.sin_github:
		archivo_notas = RAIZ / "build" / "notas_release.md"
		archivo_notas.write_text(notas(actual), encoding="utf-8")
		ejecutar(["gh", "release", "create", f"v{actual}", str(zip_), str(manifiesto), "--repo", REPOSITORIO,
			"--title", f"GitHub Accesible {actual}", "--notes-file", str(archivo_notas), "--latest"])
		print(f"Release v{actual} creada en https://github.com/{REPOSITORIO}/releases/tag/v{actual}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
