"""Voz SAPI 5 propia para los avisos en segundo plano (incidencia #5).

Por qué: los avisos que llegan solos (notificación nueva, una ejecución de
Actions que termina) se dicen por el lector de pantalla, y el lector corta lo
que está diciendo en cuanto se pulsa una tecla: si se está escribiendo, el
aviso se pierde. Con una voz SAPI 5 aparte, el aviso se oye entero aunque se
siga trabajando. Es opcional (Preferencias, Notificaciones): las dos voces
pueden hablar a la vez.

Cómo:

- Un hilo propio con su cola y su objeto ``SAPI.SpVoice`` creado DENTRO del
  hilo (con ``CoInitialize``): COM exige usar el objeto en el hilo que lo creó,
  y hablar en el hilo de la interfaz la congelaría mientras dura la frase.
- ``hablar`` nunca falla ni bloquea: si SAPI no está disponible devuelve
  ``False`` y quien llama usa el lector.
- La voz, la velocidad (-10 a 10) y el volumen (0 a 100) se leen en cada aviso:
  un cambio en Preferencias se aplica al siguiente.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)

PROGID = "SAPI.SpVoice"


@dataclass
class _Peticion:
	texto: str
	voz: str
	velocidad: int
	volumen: int


_cola: queue.Queue[_Peticion | None] = queue.Queue()
_hilo: threading.Thread | None = None
_candado = threading.Lock()
_disponible: bool | None = None


def _crear_voz():
	"""Crea ``SAPI.SpVoice`` en el hilo actual (pywin32 y, si falta, comtypes)."""
	try:
		import pythoncom
		import win32com.client

		pythoncom.CoInitialize()
		return win32com.client.Dispatch(PROGID)
	except Exception:  # noqa: BLE001 - se prueba la otra biblioteca COM
		log.debug("SAPI con pywin32 no disponible; se prueba comtypes", exc_info=True)
	import comtypes
	import comtypes.client

	comtypes.CoInitialize()
	return comtypes.client.CreateObject(PROGID)


def _descripcion(token) -> str:
	try:
		return str(token.GetDescription())
	except Exception:  # noqa: BLE001
		return ""


def _aplicar(voz_com, peticion: _Peticion) -> None:
	if peticion.voz:
		tokens = voz_com.GetVoices()
		for indice in range(tokens.Count):
			token = tokens.Item(indice)
			if _descripcion(token) == peticion.voz:
				voz_com.Voice = token
				break
	voz_com.Rate = max(-10, min(10, int(peticion.velocidad)))
	voz_com.Volume = max(0, min(100, int(peticion.volumen)))


def _trabajador() -> None:
	global _disponible
	try:
		voz_com = _crear_voz()
		_disponible = True
	except Exception:  # noqa: BLE001 - sin SAPI los avisos vuelven al lector
		log.warning("No se pudo iniciar la voz SAPI 5; los avisos irán al lector de pantalla.", exc_info=True)
		_disponible = False
		return
	while True:
		peticion = _cola.get()
		if peticion is None:
			return
		try:
			_aplicar(voz_com, peticion)
			# Síncrono dentro de este hilo: los avisos se dicen uno detrás de otro, enteros.
			voz_com.Speak(peticion.texto, 0)
		except Exception:  # noqa: BLE001 - un aviso fallido no debe parar los siguientes
			log.exception("Falló un aviso por la voz SAPI 5")


def _asegurar_hilo() -> None:
	global _hilo
	with _candado:
		if _hilo is None or not _hilo.is_alive():
			_hilo = threading.Thread(target=_trabajador, name="voz-sapi", daemon=True)
			_hilo.start()


def disponible() -> bool:
	"""``False`` si ya se intentó iniciar SAPI y no se pudo (los avisos van al lector)."""
	return _disponible is not False


def hablar(texto: str, voz: str = "", velocidad: int = 0, volumen: int = 100) -> bool:
	"""Dice ``texto`` con la voz SAPI 5. ``False`` si SAPI no está disponible (use el lector)."""
	texto = (texto or "").strip()
	if not texto or _disponible is False:
		return False
	_asegurar_hilo()
	_cola.put(_Peticion(texto, voz, velocidad, volumen))
	return True


def voces(crear: Callable[[], object] | None = None) -> list[str]:
	"""Nombres de las voces SAPI 5 instaladas (en el hilo que llama; la interfaz ya tiene COM)."""
	try:
		voz_com = (crear or _crear_voz)()
		tokens = voz_com.GetVoices()
		return [nombre for nombre in (_descripcion(tokens.Item(i)) for i in range(tokens.Count)) if nombre]
	except Exception:  # noqa: BLE001 - sin voces, el desplegable queda con «la predeterminada»
		log.info("No se pudieron listar las voces SAPI 5", exc_info=True)
		return []


def detener() -> None:
	"""Termina el hilo de la voz al cerrar la aplicación."""
	global _hilo
	with _candado:
		if _hilo is not None and _hilo.is_alive():
			_cola.put(None)
			_hilo.join(timeout=2)
		_hilo = None
