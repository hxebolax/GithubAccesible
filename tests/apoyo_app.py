"""Apoyo para probar la interfaz: un ``Contexto`` con piezas falsas.

- Configuración real en la carpeta ``data`` temporal de la prueba.
- Secretos en memoria, cuenta de prueba, API simulada (``unittest.mock``).
- Tareas SÍNCRONAS: ``enviar`` ejecuta la función en el acto y llama a
  ``al_terminar`` o ``al_fallar``; así las pruebas no esperan hilos.
- Voz y sonidos se guardan en listas para comprobar lo que se anuncia.
"""

from __future__ import annotations

from typing import Any
from unittest import mock


class SecretosMemoria(dict):
	def obtener(self, nombre, por_defecto=None):
		return self.get(nombre, por_defecto)

	def guardar(self, nombre, valor):
		self[nombre] = valor

	def guardar_varios(self, cambios):
		for nombre, valor in cambios.items():
			if valor is None:
				self.pop(nombre, None)
			else:
				self[nombre] = valor

	def borrar(self, nombre):
		self.pop(nombre, None)

	def nombres(self):
		return list(self)


class TareasSincronas:
	"""Sustituto de ``GestorTareas`` que ejecuta todo en el acto."""

	def __init__(self) -> None:
		self.enviadas: list[str] = []

	def enviar(self, funcion, *args, al_terminar=None, al_fallar=None, al_progresar=None, nombre=None, **_opciones):
		self.enviadas.append(nombre or getattr(funcion, "__name__", "?"))
		tarea = mock.Mock(cancelado=False)
		tarea.comprobar = lambda: None
		tarea.progresar = lambda *a, **k: None
		try:
			resultado = funcion(tarea, *args)
		except Exception as error:  # noqa: BLE001 - se entrega como en el gestor real
			if al_fallar:
				al_fallar(error)
			return tarea
		if al_terminar:
			al_terminar(resultado)
		return tarea

	def cancelar(self, *_a, **_k):
		return True

	def activa(self, _clave):
		return False

	def apagar(self, espera=0):
		return True


class SonidosGrabados:
	def __init__(self) -> None:
		self.eventos: list[str] = []

	def reproducir(self, evento: str, forzar: bool = False) -> bool:
		self.eventos.append(evento)
		return True

	def probar(self, evento: str) -> bool:
		return self.reproducir(evento, True)


def crear_contexto(api: Any | None = None, con_cuenta: bool = True):
	"""Contexto de prueba. Devuelve ``(contexto, api_simulada, anuncios)``."""
	from app.core.configuracion import Configuracion
	from app.core.contexto import Contexto
	from app.services.github.autenticacion import Cuenta, GestorCuentas

	config = Configuracion()
	# Las teclas globales son de todo Windows: las pruebas no deben quitárselas a la aplicación de verdad
	# si está abierta. Las pruebas de teclas globales usan una ventana simulada.
	config.establecer("teclas_globales.activadas", False)
	secretos = SecretosMemoria()
	cuentas = GestorCuentas(config, secretos)
	if con_cuenta:
		cuentas.anadir(Cuenta("ana", nombre="Ana"), "ghp_prueba_12345")
	anuncios: list[str] = []
	contexto = Contexto(config, secretos, cuentas, TareasSincronas(), SonidosGrabados(),
		anunciar=lambda texto, **_k: anuncios.append(texto))
	api_simulada = api if api is not None else mock.MagicMock(name="ApiGitHub")
	contexto.api = lambda cuenta=None: api_simulada  # type: ignore[method-assign]
	return contexto, api_simulada, anuncios
