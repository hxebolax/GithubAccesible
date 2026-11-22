"""Progreso accesible de las órdenes de red de git (clone, fetch, pull, push).

git escribe con ``--progress`` líneas como «Receiving objects:  45% (450/1000)»
(o traducidas: «Recibiendo objetos: 45%») muchas veces por segundo. Leerlas
todas dejaría al lector de pantalla sin respiro. Aquí:

- ``analizar_linea``/``SeguidorProgreso`` (puros, sin wx): extraen fase y
  porcentaje, traducen la fase y deciden qué se anuncia: solo los hitos 25,
  50, 75 y 100 % de las fases largas (recibir, resolver, enviar, actualizar
  archivos), nunca cada porcentaje.
- ``PanelProgresoGit``: etiqueta «&Progreso:» + campo de solo lectura que se
  puede consultar en cualquier momento + barra (``wx.Gauge``) + botón para
  cancelar. ``recibir_linea`` se llama desde el hilo de git y solo pasa a la
  interfaz (``wx.CallAfter``) cuando cambia algo visible.
"""

from __future__ import annotations

import builtins
import logging
import re
import threading
from typing import Any

import wx

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


HITOS = (25, 50, 75, 100)

_FASES = {
	"counting objects": N_("Contando objetos"),
	"compressing objects": N_("Comprimiendo objetos"),
	"enumerating objects": N_("Enumerando objetos"),
	"receiving objects": N_("Recibiendo objetos"),
	"resolving deltas": N_("Resolviendo diferencias"),
	"writing objects": N_("Enviando objetos"),
	"updating files": N_("Actualizando archivos"),
	"checking out files": N_("Extrayendo archivos"),
	"filtering content": N_("Filtrando contenido"),
	"checking connectivity": N_("Comprobando la conectividad"),
	"updating index flags": N_("Actualizando el índice"),
}

#: Fases rápidas que se muestran pero no se anuncian (en inglés y en español).
_SILENCIOSAS = ("counting", "compressing", "enumerating", "contando", "comprimiendo", "enumerando", "checking connectivity")

_PORCENTAJE = re.compile(r"^(?:remote:\s*|remoto:\s*)?([^:]{3,60}?):\s+(\d{1,3})\s?%")


def traducir_fase(fase: str) -> str:
	return _(_FASES.get(fase.strip().lower(), fase.strip()))


def analizar_linea(linea: str) -> tuple[str, int | None]:
	"""«Receiving objects:  45% (450/1000)» → («Recibiendo objetos», 45). Sin porcentaje: (línea, None)."""
	texto = linea.strip()
	coincidencia = _PORCENTAJE.match(texto)
	if not coincidencia:
		return texto, None
	return traducir_fase(coincidencia.group(1)), max(0, min(100, int(coincidencia.group(2))))


class SeguidorProgreso:
	"""Recibe las líneas de git y decide qué mostrar y qué anunciar (sin wx)."""

	def __init__(self) -> None:
		self.fase = ""
		self.porcentaje: int | None = None
		self.texto = ""
		self._hitos: set[tuple[str, int]] = set()
		self.lineas: list[str] = []

	def procesar(self, linea: str) -> tuple[bool, str]:
		"""Devuelve (hay cambio visible, texto que anunciar o «»)."""
		linea = linea.strip()
		if not linea:
			return False, ""
		self.lineas.append(linea)
		del self.lineas[:-200]
		fase, porcentaje = analizar_linea(linea)
		if porcentaje is None:
			cambio = linea != self.texto
			self.texto = linea
			return cambio, ""
		cambio = (fase, porcentaje) != (self.fase, self.porcentaje)
		self.fase, self.porcentaje = fase, porcentaje
		self.texto = _("{f}: {p} %").format(f=fase, p=porcentaje)
		anuncio = ""
		silenciosa = linea.lower().startswith(("remote:", "remoto:")) or fase.lower().startswith(_SILENCIOSAS) \
			or linea.lower().startswith(_SILENCIOSAS)
		hito = max((h for h in HITOS if porcentaje >= h), default=None)
		if hito is not None and not silenciosa and (fase, hito) not in self._hitos:
			# Al llegar de golpe al 100 % no se dicen los hitos saltados.
			for anterior in HITOS:
				if anterior <= hito:
					self._hitos.add((fase, anterior))
			anuncio = _("{f}, {p} por ciento").format(f=fase, p=hito)
		return cambio, anuncio


class PanelProgresoGit(wx.Panel):
	"""Zona de progreso consultable con anuncios por hitos y botón para cancelar.

	:param etiqueta: texto de la etiqueta del campo (con ``&``).
	:param etiqueta_cancelar: texto del botón; «» para no crear botón (el diálogo usa el suyo).
	"""

	def __init__(self, padre: wx.Window, contexto: Any, etiqueta: str = "", etiqueta_cancelar: str = "") -> None:
		super().__init__(padre)
		self.ctx = contexto
		self.seguidor = SeguidorProgreso()
		self._cancelar = threading.Event()
		self.en_curso = False
		raiz = wx.BoxSizer(wx.VERTICAL)
		# Etiqueta creada justo antes del campo: el lector la toma como nombre.
		self.etiqueta = wx.StaticText(self, label=etiqueta or _("&Progreso:"))
		raiz.Add(self.etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 4)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.campo = wx.TextCtrl(self, value=_("Sin operaciones de red en curso."), style=wx.TE_READONLY)
		self.campo.SetHelpText(_("Estado de la operación de red en curso (traer, tirar, enviar, clonar). Se puede consultar en cualquier momento."))
		fila.Add(self.campo, 1, wx.EXPAND | wx.RIGHT, 4)
		self.barra = wx.Gauge(self, range=100, name=_("Barra de progreso"))
		fila.Add(self.barra, 1, wx.EXPAND | wx.RIGHT, 4)
		self.boton: wx.Button | None = None
		if etiqueta_cancelar:
			self.boton = wx.Button(self, label=etiqueta_cancelar)
			self.boton.SetHelpText(_("Cancela la operación de red en curso."))
			self.boton.Bind(wx.EVT_BUTTON, lambda _e: self.cancelar())
			self.boton.Disable()
			fila.Add(self.boton, 0)
		raiz.Add(fila, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
		self.SetSizer(raiz)

	# ── Desde el hilo de la interfaz ─────────────────────────────────────────

	def empezar(self, texto: str) -> None:
		self.seguidor = SeguidorProgreso()
		self._cancelar.clear()
		self.en_curso = True
		self.campo.SetValue(texto)
		self.barra.SetValue(0)
		if self.boton is not None:
			self.boton.Enable()
		self.ctx.avisar(texto)

	def terminar(self, texto: str, correcto: bool = True) -> None:
		self.en_curso = False
		self.campo.SetValue(texto)
		self.barra.SetValue(100 if correcto else 0)
		if self.boton is not None:
			if self.boton.HasFocus():
				self.campo.SetFocus()
			self.boton.Disable()

	def cancelar(self) -> None:
		if not self.en_curso:
			return
		self._cancelar.set()
		self.campo.SetValue(_("Cancelando…"))
		self.ctx.avisar(_("Cancelando…"))

	def cancelado(self) -> bool:
		"""Se pasa a git como ``cancelado=``; seguro desde cualquier hilo."""
		return self._cancelar.is_set()

	def ultimas_lineas(self, cantidad: int = 15) -> str:
		return "\n".join(self.seguidor.lineas[-cantidad:])

	# ── Desde el hilo de git ─────────────────────────────────────────────────

	def recibir_linea(self, linea: str) -> None:
		"""Se pasa a git como ``al_linea``: se llama desde el hilo de trabajo."""
		cambio, anuncio = self.seguidor.procesar(linea)
		if cambio or anuncio:
			wx.CallAfter(self._aplicar, self.seguidor.texto, self.seguidor.porcentaje, anuncio)

	def _aplicar(self, texto: str, porcentaje: int | None, anuncio: str) -> None:
		if not self:
			return
		if not self.en_curso:
			return  # llegó tarde, tras terminar
		self.campo.SetValue(texto)
		if porcentaje is not None:
			self.barra.SetValue(porcentaje)
		else:
			self.barra.Pulse()
		if anuncio:
			self.ctx.avisar(anuncio, interrumpir=False)
