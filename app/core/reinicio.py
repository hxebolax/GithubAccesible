"""Reinicio de la aplicación pedido desde la interfaz (por ejemplo, al cambiar el idioma).

El idioma de los menús y de los botones estándar de wx se fija al arrancar, así
que cambiarlo exige reiniciar. La ventana pide el reinicio con ``solicitar()`` y
se cierra como siempre; ``main.py``, cuando ya ha liberado la instancia única,
llama a ``relanzar_si_procede()``. Se relanza DESPUÉS de liberar el mutex: si se
hiciera antes, la instancia nueva encontraría a la vieja aún viva y solo le
pediría que se mostrara.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_pendiente = False


def solicitar() -> None:
	"""Marca que, al terminar el cierre, hay que volver a abrir la aplicación."""
	global _pendiente
	_pendiente = True


def pendiente() -> bool:
	return _pendiente


def orden_relanzar() -> list[str]:
	"""El ejecutable compilado, o el intérprete con ``main.py`` al ejecutar desde código."""
	if getattr(sys, "frozen", False):
		return [sys.executable]
	return [sys.executable, str(Path(__file__).resolve().parent.parent.parent / "main.py")]


def relanzar_si_procede() -> bool:
	"""Abre otra vez la aplicación si se pidió. Devuelve si la ha lanzado."""
	global _pendiente
	if not _pendiente:
		return False
	_pendiente = False
	orden = orden_relanzar()
	try:
		subprocess.Popen(orden, cwd=str(Path(orden[-1]).parent), close_fds=True)  # noqa: S603 - nuestro propio ejecutable
	except OSError:
		log.exception("No se pudo volver a abrir la aplicación tras el reinicio pedido")
		return False
	log.info("Aplicación relanzada: %s", orden)
	return True
