"""Piezas de interfaz comunes a todas las ventanas.

- ``en_segundo_plano``: ejecuta una llamada a GitHub sin congelar la interfaz,
  con aviso de inicio, sonido, mensaje de éxito y error legible.
- ``ListaCasillas``: lista de casillas cuyo anuncio (estado, posición, orden)
  se configura en Preferencias, Accesibilidad.
- ``elegir_varios`` / ``elegir_uno``: diálogos accesibles para elegir etiquetas,
  asignados, revisores, ramas...
- ``confirmar_peligro``: confirmación con «No» por defecto y, si se pide,
  escribir el nombre de lo que se va a borrar (como hace la web de GitHub).
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from collections.abc import Callable, Sequence
from typing import Any

import wx

from app.ui.accesibilidad import voz as voz_ui
from app.ui.accesibilidad.casillas import CheckListBoxAccesible
from app.ui.accesibilidad.dialogos import (
	confirmar,
	crear_botonera,
	mostrar_error,
	mostrar_mensaje,
	pedir_texto,
	preparar_dialogo,
)
from app.ui.accesibilidad.teclado import copiar_texto

log = logging.getLogger(__name__)

__all__ = [
	"ListaCasillas", "abrir_url", "confirmar", "confirmar_peligro", "copiar", "elegir_uno", "elegir_varios",
	"en_segundo_plano", "mensaje_error", "mostrar_error", "mostrar_mensaje", "pedir_texto",
]


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def mensaje_error(error: BaseException) -> str:
	return getattr(error, "mensaje_usuario", None) or str(error) or type(error).__name__


def en_segundo_plano(
	padre: wx.Window | None,
	contexto: Any,
	funcion: Callable[[], Any],
	*,
	exito: str | Callable[[Any], str] = "",
	al_terminar: Callable[[Any], None] | None = None,
	al_fallar: Callable[[BaseException], None] | None = None,
	inicio: str = "",
	sonido: str = "completado",
	titulo_error: str = "",
	clave: str | None = None,
) -> Any:
	"""Ejecuta ``funcion()`` en un hilo y vuelve a la interfaz con el resultado.

	:param exito: frase que se anuncia al terminar (o función del resultado).
	:param inicio: frase que se anuncia al empezar («Fusionando…»).
	:param sonido: evento de sonido al terminar bien («» = ninguno).
	"""
	if inicio:
		contexto.avisar(inicio)

	def terminado(resultado: Any) -> None:
		if sonido:
			contexto.sonar(sonido)
		texto = exito(resultado) if callable(exito) else exito
		if texto:
			contexto.avisar(texto, interrumpir=False)
		if al_terminar:
			al_terminar(resultado)

	def fallado(error: BaseException) -> None:
		contexto.sonar("error")
		if al_fallar:
			al_fallar(error)
			return
		ventana = padre if padre and not padre.IsBeingDeleted() else None
		mostrar_error(ventana, mensaje_error(error), titulo_error or _("No se pudo completar"))

	return contexto.tareas.enviar(
		lambda tarea: funcion(), al_terminar=terminado, al_fallar=fallado, clave_unica=clave,
		nombre=clave or getattr(funcion, "__name__", "accion"), duplicadas="permitir" if clave is None else None,
	)


def abrir_url(url: str) -> None:
	if url:
		webbrowser.open(url)


def copiar(contexto: Any, texto: str, aviso: str = "") -> None:
	if copiar_texto(texto):
		contexto.sonar("copiado")
		contexto.avisar(aviso or _("Copiado."))


# ════════════════════════════════════════════════════════════════════════════
# Lista de casillas configurable
# ════════════════════════════════════════════════════════════════════════════


def componer_casilla(texto: str, marcada: bool, posicion: int, total: int, *, decir_estado: bool = True,
	estado_primero: bool = False, decir_posicion: bool = False) -> str:
	"""Texto del anuncio de una casilla según Preferencias (función pura, se prueba sin wx)."""
	estado = _("marcada") if marcada else _("no marcada")
	partes = [texto]
	if decir_estado:
		partes = [estado, texto] if estado_primero else [texto, estado]
	if decir_posicion and total:
		partes.append(_("{p} de {t}").format(p=posicion + 1, t=total))
	return ", ".join(p for p in partes if p)


class ListaCasillas(CheckListBoxAccesible):
	"""``CheckListBox`` accesible que anuncia según Preferencias, Accesibilidad.

	- «Anunciar el estado al marcar o desmarcar» (``accesibilidad.casillas_decir_estado``).
	- «Decir el estado antes del texto» (``accesibilidad.casillas_estado_primero``).
	- «Decir la posición» (``accesibilidad.casillas_decir_posicion``).

	Las preferencias se leen en cada anuncio: un cambio se aplica sin reiniciar.
	"""

	def __init__(self, padre: wx.Window, nombre: str, opciones: Sequence[str] = (), config: Any = None, **kwargs) -> None:
		super().__init__(padre, nombre, opciones, anunciar_estado=False, **kwargs)
		self._config = config

	def _preferencia(self, clave: str, defecto: bool) -> bool:
		if self._config is None:
			return defecto
		return bool(self._config.obtener(f"accesibilidad.{clave}", defecto))

	def _al_marcar(self, evento: wx.CommandEvent) -> None:
		super()._al_marcar(evento)
		indice = evento.GetInt()
		if not self._preferencia("casillas_decir_estado", True):
			return
		texto = componer_casilla(
			self.GetString(indice), self.IsChecked(indice), indice, self.GetCount(),
			estado_primero=self._preferencia("casillas_estado_primero", False),
			decir_posicion=self._preferencia("casillas_decir_posicion", False),
		)
		voz_ui.hablar(texto, canal=voz_ui.NAVEGACION)


# ════════════════════════════════════════════════════════════════════════════
# Diálogos de elección
# ════════════════════════════════════════════════════════════════════════════


class DialogoElegirVarios(wx.Dialog):
	def __init__(self, padre: wx.Window | None, titulo: str, etiqueta: str, opciones: Sequence[str],
		marcados: Sequence[int] = (), config: Any = None, ayuda: str = "") -> None:
		super().__init__(padre, title=titulo, size=(520, 480), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=etiqueta), 0, wx.LEFT | wx.TOP, 8)
		self.lista = ListaCasillas(self, etiqueta.replace("&", "").rstrip(":"), list(opciones), config=config)
		for indice in marcados:
			if 0 <= indice < self.lista.GetCount():
				wx.CheckListBox.Check(self.lista, indice, True)
		if ayuda:
			self.lista.SetHelpText(ayuda + " " + self.lista.GetHelpText())
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
		raiz.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(raiz)
		if self.lista.GetCount() and self.lista.GetSelection() < 0:
			self.lista.SetSelection(0)
		preparar_dialogo(self, foco_inicial=self.lista)
		self.CentreOnParent()

	def marcados(self) -> list[int]:
		return list(self.lista.GetCheckedItems())


def elegir_varios(padre: wx.Window | None, titulo: str, etiqueta: str, opciones: Sequence[str],
	marcados: Sequence[int] = (), config: Any = None, ayuda: str = "") -> list[int] | None:
	"""Lista de casillas en un diálogo. Devuelve los índices marcados o ``None`` si se cancela."""
	dialogo = DialogoElegirVarios(padre, titulo, etiqueta, opciones, marcados, config, ayuda)
	try:
		return dialogo.marcados() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


class DialogoElegirUno(wx.Dialog):
	def __init__(self, padre: wx.Window | None, titulo: str, etiqueta: str, opciones: Sequence[str], seleccion: int = 0,
		ayuda: str = "") -> None:
		super().__init__(padre, title=titulo, size=(520, 440), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=etiqueta), 0, wx.LEFT | wx.TOP, 8)
		self.lista = wx.ListBox(self, choices=list(opciones), style=wx.LB_SINGLE)
		if opciones:
			self.lista.SetSelection(max(0, min(seleccion, len(opciones) - 1)))
		if ayuda:
			self.lista.SetHelpText(ayuda)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.EndModal(wx.ID_OK))
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
		raiz.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(raiz)
		preparar_dialogo(self, foco_inicial=self.lista)
		self.CentreOnParent()


def elegir_uno(padre: wx.Window | None, titulo: str, etiqueta: str, opciones: Sequence[str], seleccion: int = 0,
	ayuda: str = "") -> int | None:
	"""Lista simple en un diálogo. Devuelve el índice elegido o ``None``."""
	if not opciones:
		mostrar_mensaje(padre, _("No hay opciones para elegir."), titulo)
		return None
	dialogo = DialogoElegirUno(padre, titulo, etiqueta, opciones, seleccion, ayuda)
	try:
		return dialogo.lista.GetSelection() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


def confirmar_peligro(padre: wx.Window | None, mensaje: str, titulo: str, nombre_a_escribir: str = "") -> bool:
	"""Confirmación de una acción irreversible.

	Con ``nombre_a_escribir`` pide además escribir ese nombre (por ejemplo, al
	borrar un repositorio), igual que la web de GitHub.
	"""
	if confirmar(padre, mensaje, titulo, peligroso=True) != wx.ID_YES:
		return False
	if not nombre_a_escribir:
		return True
	escrito = pedir_texto(padre, _("Para confirmar, escriba «{n}»:").format(n=nombre_a_escribir), titulo)
	if escrito is None:
		return False
	if escrito.strip() != nombre_a_escribir:
		mostrar_error(padre, _("El texto no coincide. No se ha hecho nada."), titulo)
		return False
	return True
