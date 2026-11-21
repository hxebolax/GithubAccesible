"""Prueba REAL de actualización de extremo a extremo con los ejecutables compilados.

Qué hace (tarda unos minutos y abre ventanas de la aplicación en pantalla):

1. Compila la aplicación con una versión anterior ficticia (``--version-antigua``,
   por defecto 0.9.9) y la «instala» en una carpeta temporal.
2. Compila la versión actual, la empaqueta y FIRMA su ``version.json``.
3. Sirve el ZIP y el manifiesto con un servidor HTTP en ::1 (el
   actualizador solo admite http contra localhost; en producción, solo https).
4. Configura la instalación antigua con el origen «dirección personalizada»
   apuntando a ese servidor y deja datos de usuario de prueba en ``data``.
5. Arranca la versión antigua, abre «Ayuda, Buscar actualizaciones», pulsa
   «Actualizar ahora» mediante UI Automation (pywinauto) y espera.
6. Comprueba que se relanzó la versión nueva, que confirmó su arranque
   (anti-rollback), que la copia de seguridad existe y que los datos del
   usuario siguen intactos. Cierra la aplicación.

Uso: ``.venv\\Scripts\\python.exe tools\\prueba_actualizacion_real.py``
(``--sin-compilar`` reutiliza ``build/antigua`` y ``build/GithubAccesible`` ya hechos).
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
VERSION_PY = RAIZ / "app" / "core" / "version.py"
NOMBRE = "GithubAccesible"


def version_actual() -> str:
	return re.search(r'APP_VERSION\s*=\s*"([^"]+)"', VERSION_PY.read_text(encoding="utf-8")).group(1)


def compilar(version_forzada: str | None, destino: Path) -> None:
	original = VERSION_PY.read_text(encoding="utf-8")
	try:
		if version_forzada:
			VERSION_PY.write_text(re.sub(r'APP_VERSION\s*=\s*"[^"]+"', f'APP_VERSION = "{version_forzada}"', original), encoding="utf-8")
		subprocess.run([PYTHON, "setup_cx.py", "build"], cwd=RAIZ, check=True, stdout=subprocess.DEVNULL)
	finally:
		VERSION_PY.write_text(original, encoding="utf-8")
	if destino != RAIZ / "build" / NOMBRE:
		if destino.exists():
			shutil.rmtree(destino)
		shutil.copytree(RAIZ / "build" / NOMBRE, destino)


class _ServidorIPv6(http.server.ThreadingHTTPServer):
	# En algunos equipos un filtro de red corta las conexiones a 127.0.0.1 (error 10054);
	# ::1 (IPv6 local) no pasa por él. El actualizador admite http solo contra localhost.
	address_family = socket.AF_INET6


def servir(carpeta: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
	manejador = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(carpeta))
	servidor = _ServidorIPv6(("::1", 0), manejador)
	threading.Thread(target=servidor.serve_forever, daemon=True).start()
	return servidor, servidor.server_address[1]


def esperar(condicion, segundos: float, descripcion: str):
	limite = time.monotonic() + segundos
	while time.monotonic() < limite:
		resultado = condicion()
		if resultado:
			return resultado
		time.sleep(0.5)
	raise SystemExit(f"FALLO: no se cumplió a tiempo: {descripcion}")


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser()
	analizador.add_argument("--version-antigua", default="0.9.9")
	analizador.add_argument("--sin-compilar", action="store_true")
	opciones = analizador.parse_args(argumentos)
	nueva = version_actual()
	antigua_build = RAIZ / "build" / "antigua"

	if not opciones.sin_compilar:
		print(f"1. Compilando la versión antigua {opciones.version_antigua}…")
		compilar(opciones.version_antigua, antigua_build)
		print(f"2. Compilando y empaquetando la versión nueva {nueva}…")
		compilar(None, RAIZ / "build" / NOMBRE)
		subprocess.run([PYTHON, "tools/empaquetar.py"], cwd=RAIZ, check=True)

	trabajo = Path(tempfile.mkdtemp(prefix="prueba_actualizacion_"))
	instalacion = trabajo / NOMBRE
	shutil.copytree(antigua_build, instalacion)
	publicado = trabajo / "servidor"
	publicado.mkdir()
	shutil.copy2(RAIZ / "build" / f"{NOMBRE}_v{nueva}.zip", publicado)
	shutil.copy2(RAIZ / "build" / "version.json", publicado)
	servidor, puerto = servir(publicado)
	url = f"http://[::1]:{puerto}/version.json"
	print(f"3. Versión {nueva} servida en {url}")

	config = instalacion / "data" / "config"
	config.mkdir(parents=True, exist_ok=True)
	ajustes = {
		"version_esquema": 1,
		"general": {"buscar_actualizaciones": False, "anunciar_arranque": False, "preguntar_sesion": False,
			"seccion_inicial": "locales"},
		"actualizaciones": {"origen": "personalizada", "url_personalizada": url},
		"notificaciones": {"comprobar": False},
		"sonidos": {"activados": False},
		"listas": {"por_pagina": 77},
	}
	(config / "settings.json").write_text(json.dumps(ajustes, indent=2), encoding="utf-8")
	(config / "dato_de_prueba.txt").write_text("No se debe tocar", encoding="utf-8")
	print(f"4. Instalación antigua preparada en {instalacion}")

	from pywinauto import Application, Desktop

	ejecutable = instalacion / f"{NOMBRE}.exe"
	print("5. Arrancando la versión antigua…")
	aplicacion = Application(backend="uia").start(str(ejecutable), work_dir=str(instalacion))
	ventana = esperar(lambda: next((v for v in Desktop(backend="uia").windows() if v.window_text().startswith("GitHub Accesible")), None),
		60, "ventana principal de la versión antigua")
	time.sleep(2)
	ventana.menu_select("Ayuda->Buscar actualizaciones…")
	def buscar_dialogo():
		# El diálogo pertenece a la ventana principal: en UI Automation cuelga de ella.
		for candidata in ventana.children():
			if candidata.window_text() == "Actualización disponible":
				return candidata
		return None

	dialogo = esperar(buscar_dialogo, 60, "diálogo «Actualización disponible»")
	print("   Diálogo de actualización abierto; pulsando «Actualizar ahora»…")
	boton = next(h for h in dialogo.descendants(control_type="Button") if h.window_text() == "Actualizar ahora")
	boton.invoke()

	estado = config / "actualizaciones.json"

	def confirmada():
		try:
			datos = json.loads(estado.read_text(encoding="utf-8"))
		except (OSError, ValueError):
			return None
		return datos if datos.get("version_confirmada") == nueva else None

	datos = esperar(confirmada, 240, f"versión {nueva} instalada, relanzada y confirmada")
	print(f"6. Versión {nueva} confirmada tras relanzarse: {datos}")
	registros = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (instalacion / "data" / "logs").glob("sesion_*.log"))
	assert f"{nueva}" in registros, "la sesión de la versión nueva debe aparecer en el registro"
	ajustes_despues = json.loads((config / "settings.json").read_text(encoding="utf-8"))
	assert ajustes_despues["listas"]["por_pagina"] == 77, "la configuración del usuario debe seguir intacta"
	assert (config / "dato_de_prueba.txt").read_text(encoding="utf-8") == "No se debe tocar"
	assert (instalacion / "data" / "temp" / "version_anterior").exists(), "debe quedar la copia de seguridad"
	resultado = instalacion / "data" / "temp" / "actualizacion" / "resultado.txt"
	if resultado.exists():
		print("   Resultado del script:", resultado.read_text(encoding="utf-8", errors="replace").strip())

	print("7. Cerrando la versión nueva…")
	for ventana_nueva in Desktop(backend="uia").windows():
		if ventana_nueva.window_text().startswith("GitHub Accesible"):
			ventana_nueva.close()
	time.sleep(3)
	servidor.shutdown()
	del aplicacion
	print("PRUEBA SUPERADA: la actualización se descargó, verificó (firma y SHA-256), instaló, relanzó y confirmó sin tocar los datos.")
	print(f"Carpeta de la prueba (se puede borrar): {trabajo}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
