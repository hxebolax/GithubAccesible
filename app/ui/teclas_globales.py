"""Teclas globales: combinaciones que funcionan desde cualquier programa de Windows.

Por qué y cómo:

- Con la aplicación en la bandeja o detrás de otras ventanas, volver a ella o
  saber si hay notificaciones cuesta varias pulsaciones (Windows+B, flechas,
  Alt+Tab...). Una tecla global lo hace de una vez.
- Se registran con ``wx.Window.RegisterHotKey`` (``RegisterHotKey`` de Win32)
  en la ventana principal. Windows avisa con ``EVT_HOTKEY`` aunque la ventana
  esté oculta.
- Cada orden tiene su combinación en ``teclas_globales.<orden>`` y se cambia en
  Preferencias, Teclas globales (el campo recoge la combinación que se pulsa).
  Vacía = sin tecla.
- Si otro programa ya tiene la combinación, Windows no la da: se dice cuál
  falló en lugar de dejar una tecla muerta en silencio.
- Las combinaciones se guardan como texto legible en español
  («Control+Alt+Mayúsculas+G»), que es lo que lee el lector en Preferencias.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import wx

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	return texto


#: Órdenes globales: (clave de configuración, nombre para Preferencias y avisos).
ORDENES: tuple[tuple[str, str], ...] = (
	("mostrar_ocultar", N_("Mostrar u ocultar la aplicación")),
	("decir_notificaciones", N_("Decir las notificaciones sin leer")),
	("abrir_notificaciones", N_("Abrir la sección Notificaciones")),
	("buscar", N_("Buscar en GitHub")),
	("comprobar_notificaciones", N_("Comprobar ahora si hay notificaciones nuevas")),
	("abrir_descargas", N_("Abrir el gestor de descargas")),
)

# Identificadores de RegisterHotKey: deben estar entre 0 y 0xBFFF en una aplicación.
ID_BASE = 0x2A00

MOD_CONTROL, MOD_ALT, MOD_MAYUS, MOD_WIN = wx.MOD_CONTROL, wx.MOD_ALT, wx.MOD_SHIFT, wx.MOD_WIN
_NOMBRES_MOD = ((MOD_CONTROL, "Control"), (MOD_ALT, "Alt"), (MOD_MAYUS, "Mayúsculas"), (MOD_WIN, "Windows"))
_ALIAS_MOD = {
	"control": MOD_CONTROL, "ctrl": MOD_CONTROL, "ctl": MOD_CONTROL,
	"alt": MOD_ALT,
	"mayúsculas": MOD_MAYUS, "mayusculas": MOD_MAYUS, "mayús": MOD_MAYUS, "mayus": MOD_MAYUS, "shift": MOD_MAYUS,
	"windows": MOD_WIN, "win": MOD_WIN,
}


@dataclass(frozen=True)
class Combinacion:
	"""Modificadores de wx y código de tecla virtual de Windows (VK)."""

	modificadores: int
	tecla_virtual: int

	@property
	def texto(self) -> str:
		# En el idioma de la interfaz («Mayúsculas» / «Shift»): analizar() acepta los dos.
		partes = [pgettext("tecla", "Mayúsculas") if valor == MOD_MAYUS else nombre
			for valor, nombre in _NOMBRES_MOD if self.modificadores & valor]
		return "+".join([*partes, nombre_tecla(self.tecla_virtual)])


def nombre_tecla(vk: int) -> str:
	"""«G», «7», «F5»... a partir del código virtual."""
	if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
		return chr(vk)
	if 0x70 <= vk <= 0x87:
		return f"F{vk - 0x6F}"
	return f"VK{vk:02X}"


def tecla_virtual(nombre: str) -> int | None:
	"""Código virtual de una letra, un número o una tecla de función; ``None`` si no se admite."""
	nombre = (nombre or "").strip().upper()
	if len(nombre) == 1 and (nombre.isascii() and nombre.isalnum()):
		return ord(nombre)
	if nombre.startswith("F") and nombre[1:].isdigit() and 1 <= int(nombre[1:]) <= 24:
		return 0x6F + int(nombre[1:])
	return None


def analizar(texto: str) -> Combinacion | None:
	"""«Control+Alt+Mayúsculas+G» (o «Ctrl+Alt+Shift+G») → ``Combinacion``; vacío o inválido → ``None``.

	Se exige al menos Control, Alt o Windows: una tecla global sola (o con solo
	Mayúsculas) dejaría de escribirse en todos los programas.
	"""
	partes = [p.strip() for p in (texto or "").replace(" ", "").split("+") if p.strip()]
	if len(partes) < 2:
		return None
	modificadores = 0
	for parte in partes[:-1]:
		valor = _ALIAS_MOD.get(parte.casefold())
		if valor is None:
			return None
		modificadores |= valor
	vk = tecla_virtual(partes[-1])
	if vk is None or not modificadores & (MOD_CONTROL | MOD_ALT | MOD_WIN):
		return None
	return Combinacion(modificadores, vk)


def normalizar(texto: str) -> str:
	"""Texto canónico en español, o «» si no es una combinación válida."""
	combinacion = analizar(texto)
	return combinacion.texto if combinacion else ""


def desde_evento(codigo_wx: int, modificadores: int) -> Combinacion | None:
	"""Combinación a partir de una pulsación de wx (para el campo de Preferencias)."""
	if ord("A") <= codigo_wx <= ord("Z") or ord("0") <= codigo_wx <= ord("9"):
		vk = codigo_wx
	elif wx.WXK_F1 <= codigo_wx <= wx.WXK_F24:
		vk = 0x70 + (codigo_wx - wx.WXK_F1)
	else:
		return None
	modificadores &= MOD_CONTROL | MOD_ALT | MOD_MAYUS | MOD_WIN
	if not modificadores & (MOD_CONTROL | MOD_ALT | MOD_WIN):
		return None
	return Combinacion(modificadores, vk)


def nombre_orden(clave: str) -> str:
	return _(dict(ORDENES).get(clave, clave))


class GestorTeclasGlobales:
	"""Registra en ``ventana`` las teclas configuradas y llama a la función de cada orden.

	:param funciones: clave de la orden → función sin argumentos.
	"""

	def __init__(self, ventana: wx.Window, config: Any, funciones: dict[str, Callable[[], None]],
		avisar: Callable[[str], None] | None = None) -> None:
		self.ventana = ventana
		self.config = config
		self.funciones = funciones
		self.avisar = avisar or (lambda _texto: None)
		self.registradas: dict[int, str] = {}
		self.fallidas: list[tuple[str, str]] = []
		ventana.Bind(wx.EVT_HOTKEY, self._al_tecla)

	def registrar(self, anunciar_fallos: bool = True) -> list[tuple[str, str]]:
		"""(Re)registra todas. Devuelve ``(orden, combinación)`` de las que Windows no dio."""
		self.quitar()
		self.fallidas = []
		if not self.config.obtener("teclas_globales.activadas", True):
			return []
		usadas: set[tuple[int, int]] = set()
		for indice, (clave, _nombre) in enumerate(ORDENES):
			texto = str(self.config.obtener(f"teclas_globales.{clave}", "") or "")
			combinacion = analizar(texto)
			if combinacion is None or clave not in self.funciones:
				if texto.strip() and combinacion is None:
					self.fallidas.append((clave, texto))
				continue
			par = (combinacion.modificadores, combinacion.tecla_virtual)
			identificador = ID_BASE + indice
			if par in usadas or not self._registrar_una(identificador, combinacion):
				self.fallidas.append((clave, combinacion.texto))
				continue
			usadas.add(par)
			self.registradas[identificador] = clave
		if self.fallidas and anunciar_fallos:
			self.avisar(self.texto_fallos())
		return list(self.fallidas)

	def _registrar_una(self, identificador: int, combinacion: Combinacion) -> bool:
		try:
			return bool(self.ventana.RegisterHotKey(identificador, combinacion.modificadores, combinacion.tecla_virtual))
		except Exception:  # noqa: BLE001 - una tecla que no se puede registrar no impide arrancar
			log.warning("No se pudo registrar la tecla global %s", combinacion.texto, exc_info=True)
			return False

	def texto_fallos(self) -> str:
		partes = [_("{o} ({t})").format(o=nombre_orden(clave), t=texto) for clave, texto in self.fallidas]
		return _("No se pudieron activar estas teclas globales: {l}. Puede que otro programa ya las use o que no sean "
			"válidas; cámbielas en Preferencias, Teclas globales.").format(l="; ".join(partes))

	def quitar(self) -> None:
		for identificador in list(self.registradas):
			try:
				self.ventana.UnregisterHotKey(identificador)
			except Exception:  # noqa: BLE001 - al cerrar puede que ya no exista
				log.debug("No se pudo quitar la tecla global %s", identificador, exc_info=True)
		self.registradas.clear()

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		clave = self.registradas.get(evento.GetId())
		funcion = self.funciones.get(clave or "")
		if funcion is None:
			evento.Skip()
			return
		try:
			funcion()
		except Exception:  # noqa: BLE001 - una tecla global no debe tumbar la aplicación
			log.exception("Fallo en la tecla global %s", clave)
