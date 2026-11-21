"""Contexto compartido de la aplicación: lo que casi todas las ventanas necesitan.

Se crea una vez en el arranque y se pasa a las ventanas. Así no hay variables
globales repartidas y las pruebas pueden construir un contexto con piezas
falsas (configuración en una carpeta temporal, API simulada, voz muda).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class Contexto:
	"""Piezas compartidas.

	:param config: ``Configuracion`` de la aplicación.
	:param secretos: ``AlmacenSecretos`` (tokens cifrados).
	:param cuentas: ``GestorCuentas``.
	:param tareas: ``GestorTareas`` (trabajo en segundo plano).
	:param sonidos: reproductor de sonidos (o ``None``).
	:param anunciar: función que habla un texto por el lector.
	"""

	config: Any
	secretos: Any
	cuentas: Any
	tareas: Any
	sonidos: Any = None
	anunciar: Callable[..., None] = lambda texto, **_: None
	ventana_principal: Any = None
	almacen: Any = None
	extra: dict[str, Any] = field(default_factory=dict)

	def api(self, cuenta: Any = None):
		"""Fachada ``ApiGitHub`` de la cuenta indicada o de la activa."""
		from app.services.github import ApiGitHub

		return ApiGitHub(self.cuentas.cliente(cuenta))

	@property
	def cuenta(self):
		return self.cuentas.activa()

	@property
	def usuario(self) -> str:
		cuenta = self.cuentas.activa()
		return cuenta.usuario if cuenta else ""

	@property
	def host(self) -> str:
		cuenta = self.cuentas.activa()
		return cuenta.host if cuenta else "github.com"

	def token(self) -> str | None:
		cuenta = self.cuentas.activa()
		return self.cuentas.token(cuenta) if cuenta else None

	def sonar(self, evento: str) -> None:
		if self.sonidos is not None:
			try:
				self.sonidos.reproducir(evento)
			except Exception:  # noqa: BLE001 - un sonido nunca debe interrumpir una acción
				log.debug("No se pudo reproducir el sonido %s", evento, exc_info=True)

	def avisar(self, texto: str, interrumpir: bool = True) -> None:
		"""Aviso de sistema (canal de avisos): respeta la preferencia de avisos por voz."""
		if self.config.obtener("accesibilidad.avisos_voz", True):
			self.anunciar(texto, interrumpir=interrumpir)

	def relativas(self) -> bool:
		return bool(self.config.obtener("listas.fechas_relativas", True))
