"""Horas de silencio de los avisos en segundo plano (incidencia #15).

Entre dos horas del día (por ejemplo de 23:00 a 7:00, de noche, con el
ordenador encendido) las notificaciones nuevas de GitHub no suenan, no se
dicen y no muestran la notificación de Windows. Si se quiere, tampoco los
avisos de las ejecuciones de Actions vigiladas ni los de las descargas.

Nada se pierde: las notificaciones se siguen comprobando (el contador de la
lista de secciones y de la bandeja sigue al día) y lo silenciado se cuenta,
para decir un resumen cuando terminan las horas de silencio.

Es lógica pura con un reloj que se puede cambiar, para probarla sin esperar a
la noche. La ventana principal la consulta antes de cada aviso y cada poco
para saber si acaban de terminar.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)

from app.core.configuracion import PATRON_HORA

_PATRON = re.compile(PATRON_HORA)

#: Tipos de aviso que se pueden silenciar.
NOTIFICACION = "notificacion"
OTRO = "otro"  # ejecuciones de Actions vigiladas y descargas


def interpretar_hora(texto: Any) -> int | None:
	"""Minutos desde la medianoche de una hora escrita, o ``None`` si no es una hora válida."""
	coincidencia = _PATRON.fullmatch(str(texto or ""))
	if coincidencia is None:
		return None
	return int(coincidencia.group(1)) * 60 + int(coincidencia.group(2) or 0)


def formatear_hora(minutos: int) -> str:
	"""«07:00» a partir de los minutos desde la medianoche."""
	minutos %= 24 * 60
	return f"{minutos // 60:02d}:{minutos % 60:02d}"


def dentro(desde: int, hasta: int, ahora: int) -> bool:
	"""Si ``ahora`` (minutos del día) está entre ``desde`` (incluido) y ``hasta`` (excluido).

	Si ``desde`` es mayor que ``hasta``, el periodo cruza la medianoche (de 23:00 a 7:00).
	Las dos horas iguales no silencian nada: es más probable un descuido que querer
	silenciar el día entero, y para eso ya están las casillas de cada aviso.
	"""
	if desde == hasta:
		return False
	if desde < hasta:
		return desde <= ahora < hasta
	return ahora >= desde or ahora < hasta


@dataclass
class Recuento:
	"""Lo que se ha callado durante unas horas de silencio."""

	notificaciones: int = 0
	otros: int = 0

	def __bool__(self) -> bool:
		return bool(self.notificaciones or self.otros)


class HorasSilencio:
	"""Decide si un aviso en segundo plano se calla y lleva la cuenta de lo callado.

	:param config: ``Configuracion`` (se lee en cada consulta: los cambios valen al momento).
	:param reloj: devuelve la hora actual (las pruebas ponen la que quieran).
	"""

	def __init__(self, config: Any, reloj: Callable[[], datetime] = datetime.now) -> None:
		self._config = config
		self._reloj = reloj
		self._cerrojo = threading.Lock()
		self._recuento = Recuento()
		self._estaba_en_silencio = False

	def _horas(self) -> tuple[int, int] | None:
		"""(desde, hasta) en minutos si están activadas y bien escritas; si no, ``None``."""
		if not self._config.obtener("notificaciones.silencio_activado", False):
			return None
		desde = interpretar_hora(self._config.obtener("notificaciones.silencio_desde", "23:00"))
		hasta = interpretar_hora(self._config.obtener("notificaciones.silencio_hasta", "07:00"))
		if desde is None or hasta is None:
			return None
		return desde, hasta

	def activas(self) -> bool:
		"""Si ahora mismo son horas de silencio."""
		horas = self._horas()
		if horas is None:
			return False
		ahora = self._reloj()
		return dentro(horas[0], horas[1], ahora.hour * 60 + ahora.minute)

	def hasta(self) -> str:
		"""Hora en que terminan, «07:00» (vacío si no están activadas)."""
		horas = self._horas()
		return formatear_hora(horas[1]) if horas else ""

	def silenciar(self, tipo: str = NOTIFICACION, cantidad: int = 1) -> bool:
		"""``True`` si el aviso se calla (y se cuenta para el resumen); ``False`` si se avisa.

		Los avisos de Actions y de descargas (``OTRO``) solo se callan si así lo dice
		«notificaciones.silencio_actions».
		"""
		if not self.activas():
			return False
		if tipo != NOTIFICACION and not self._config.obtener("notificaciones.silencio_actions", True):
			return False
		with self._cerrojo:
			self._estaba_en_silencio = True
			if tipo == NOTIFICACION:
				self._recuento.notificaciones += cantidad
			else:
				self._recuento.otros += cantidad
		log.info("Aviso silenciado por las horas de silencio (%s, %d)", tipo, cantidad)
		return True

	def revisar(self) -> Recuento | None:
		"""Se llama cada poco: si las horas de silencio acaban de terminar, devuelve lo callado.

		Devuelve ``None`` mientras duran, si no han empezado o si al terminar no se calló
		nada. El recuento vuelve a cero al devolverlo, para empezar de nuevo la noche siguiente.
		"""
		activas = self.activas()
		with self._cerrojo:
			if activas:
				self._estaba_en_silencio = True
				return None
			if not self._estaba_en_silencio:
				return None
			self._estaba_en_silencio = False
			recuento, self._recuento = self._recuento, Recuento()
		log.info("Terminan las horas de silencio: %d notificaciones y %d avisos más callados",
			recuento.notificaciones, recuento.otros)
		return recuento if recuento else None
