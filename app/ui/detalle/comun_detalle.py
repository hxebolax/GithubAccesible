"""Piezas comunes de las ventanas de detalle de Actions, releases, gists, discusiones y proyectos.

- ``VentanaDetalle``: ``wx.Frame`` con panel, barra de estado, Ctrl+H (ayuda del
  control enfocado), Ctrl+W para cerrar (desde su menú) y sonidos de abrir y
  cerrar. Escape NO cierra estas ventanas: son ventanas de trabajo, no diálogos.
- Etiqueta creada SIEMPRE justo antes de su control y con el mismo padre
  (``crear_lista``, ``crear_texto``): el lector la toma como nombre.
- ``en_fondo``: llamada a GitHub en segundo plano que no toca la ventana si
  la persona la ha cerrado mientras tanto.
- ``descargar``: descarga a disco con progreso por hitos (25, 50, 75 y 100 %)
  en la barra de estado y por voz, sin saturar al lector.
"""

from __future__ import annotations

import builtins
import logging
import os
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import wx

from app.services import formato as f
from app.ui.accesibilidad.ayuda import asegurar_ayudas, describir_control_enfocado
from app.ui.accesibilidad.dialogos import mostrar_error
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.teclado import vincular_menu_contextual
from app.ui.comunes import en_segundo_plano, mensaje_error
from app.ui.vistas.base import normalizar_atajo, preferencias_lectura, texto_tecla

log = logging.getLogger(__name__)

#: Una entrada de menú: ``(etiqueta, función)`` o ``(etiqueta, función, ayuda)``; ``None`` = separador.
Entrada = tuple | None


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ════════════════════════════════════════════════════════════════════════════
# Utilidades sin ventanas
# ════════════════════════════════════════════════════════════════════════════


def fecha_iso(texto: str | None) -> datetime | None:
	"""«2024-05-01T10:00:00Z» → ``datetime`` con zona; ``None`` si no se entiende."""
	if not texto:
		return None
	try:
		return datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
	except ValueError:
		log.debug("Fecha no reconocida: %r", texto)
		return None


def duracion_entre(inicio: str | None, fin: str | None, ahora: datetime | None = None) -> str:
	"""Duración legible entre dos fechas ISO; sin fin, hasta ahora (algo que sigue en curso)."""
	desde = fecha_iso(inicio)
	if desde is None:
		return ""
	hasta = fecha_iso(fin) or ahora or datetime.now(UTC)
	return f.duracion(max(0.0, (hasta - desde).total_seconds()))


def carpeta_de_descargas(padre: wx.Window | None, ctx: Any, preguntar: bool = False) -> str | None:
	"""Carpeta de Preferencias («general.carpeta_descargas») o la que elija la persona.

	Si no hay carpeta configurada, o ya no existe, o ``preguntar`` es verdadero,
	se pregunta con el diálogo nativo de Windows. ``None`` si se cancela.
	"""
	carpeta = str(ctx.config.obtener("general.carpeta_descargas", "") or "")
	if carpeta and os.path.isdir(carpeta) and not preguntar:
		return carpeta
	dialogo = wx.DirDialog(padre, _("Elija la carpeta donde guardar la descarga"), carpeta,
		style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
	try:
		if dialogo.ShowModal() != wx.ID_OK:
			return None
		return dialogo.GetPath() or None
	finally:
		dialogo.Destroy()


def elegir_archivos(padre: wx.Window | None, titulo: str) -> list[str]:
	"""Diálogo nativo para elegir uno o varios archivos. Lista vacía si se cancela."""
	dialogo = wx.FileDialog(padre, titulo, style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST)
	try:
		if dialogo.ShowModal() != wx.ID_OK:
			return []
		return list(dialogo.GetPaths())
	finally:
		dialogo.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Ventana base
# ════════════════════════════════════════════════════════════════════════════


class VentanaDetalle(wx.Frame):
	"""Ventana de detalle con las piezas accesibles comunes.

	:param clave: identifica lo que muestra («ejecucion:dueño/repo:123»). Si ya
		hay una ventana abierta con la misma clave, ``abrir_existente`` la trae
		al frente en lugar de abrir otra igual.
	"""

	_abiertas: dict[str, VentanaDetalle] = {}

	def __init__(self, padre: wx.Window | None, ctx: Any, titulo: str, clave: str = "", tamano: tuple[int, int] = (1000, 720)) -> None:
		super().__init__(padre, title=titulo, size=tamano)
		self.ctx = ctx
		self.clave = clave
		self.cerrada = False
		self._descargas: list[Any] = []
		self.panel = wx.Panel(self)
		self.raiz = wx.BoxSizer(wx.VERTICAL)
		self.panel.SetSizer(self.raiz)
		self.CreateStatusBar()
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla_ventana)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar_ventana)
		if clave:
			VentanaDetalle._abiertas[clave] = self

	# ── Registro de ventanas abiertas ─────────────────────────────────────────

	@classmethod
	def abrir_existente(cls, clave: str) -> bool:
		"""Trae al frente la ventana con esa clave si sigue abierta."""
		ventana = cls._abiertas.get(clave)
		if ventana is None or not ventana or ventana.cerrada:
			cls._abiertas.pop(clave, None)
			return False
		if ventana.IsIconized():
			ventana.Iconize(False)
		ventana.Raise()
		ventana.SetFocus()
		return True

	def viva(self) -> bool:
		"""``False`` si la ventana se ha cerrado (los resultados tardíos se descartan)."""
		try:
			return bool(self) and not self.cerrada and not self.IsBeingDeleted()
		except RuntimeError:
			return False

	# ── Construcción ──────────────────────────────────────────────────────────

	def crear_lista(self, etiqueta: str, nombre: str, columnas: Sequence[tuple[str, int]], padre: wx.Window | None = None,
		sizer: wx.Sizer | None = None, proporcion: int = 1, ayuda: str = "") -> ListaAccesible:
		"""Etiqueta y, JUSTO DESPUÉS y con el mismo padre, una ``ListaAccesible``."""
		padre = padre or self.panel
		sizer = sizer if sizer is not None else self.raiz
		sizer.Add(wx.StaticText(padre, label=etiqueta), 0, wx.LEFT | wx.TOP | wx.RIGHT, 4)
		lista = ListaAccesible(
			padre, nombre=nombre, columnas=[(titulo, self.FromDIP(ancho)) for titulo, ancho in columnas],
			leer_preferencias=preferencias_lectura(self.ctx.config),
		)
		if ayuda:
			lista.SetHelpText(ayuda + " " + lista.GetHelpText())
		sizer.Add(lista, proporcion, wx.EXPAND | wx.ALL, 4)
		return lista

	def crear_texto(self, etiqueta: str, valor: str = "", alto: int = 100, padre: wx.Window | None = None,
		sizer: wx.Sizer | None = None, proporcion: int = 0, ayuda: str = "", sin_ajuste: bool = False) -> wx.TextCtrl:
		"""Etiqueta y campo de SOLO LECTURA multilínea (se recorre línea a línea y se copia)."""
		padre = padre or self.panel
		sizer = sizer if sizer is not None else self.raiz
		sizer.Add(wx.StaticText(padre, label=etiqueta), 0, wx.LEFT | wx.TOP | wx.RIGHT, 4)
		estilo = wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2
		if sin_ajuste:
			estilo |= wx.TE_DONTWRAP | wx.HSCROLL
		campo = wx.TextCtrl(padre, value=valor, style=estilo, size=(-1, self.FromDIP(alto)))
		campo.SetHelpText(ayuda or _("Texto de solo lectura. Recórralo con las flechas; puede seleccionarlo y copiarlo."))
		sizer.Add(campo, proporcion, wx.EXPAND | wx.ALL, 4)
		return campo

	def poner_menus(self, menus: Sequence[tuple[str, Sequence[Entrada]]]) -> wx.MenuBar:
		"""Barra de menús. Los atajos tras «\\t» valen en toda la ventana: solo para acciones globales.

		Las teclas propias de una lista (Intro, Supr, F2) se escriben entre
		paréntesis en la etiqueta y las atiende la lista (``teclas_de_lista``).
		"""
		barra = wx.MenuBar()
		for titulo, entradas in menus:
			barra.Append(self._crear_menu(entradas, en_barra=True), titulo)
		self.SetMenuBar(barra)
		return barra

	def _crear_menu(self, entradas: Sequence[Entrada], en_barra: bool = False) -> wx.Menu:
		menu = wx.Menu()
		for entrada in entradas:
			if entrada is None:
				menu.AppendSeparator()
				continue
			etiqueta, funcion, *resto = entrada
			item = menu.Append(wx.ID_ANY, etiqueta, resto[0] if resto else "")
			if en_barra:
				self.Bind(wx.EVT_MENU, lambda _e, fn=funcion: self.ejecutar(fn), item)
			else:
				# Desde un menú emergente, la acción espera a que el menú se cierre
				# (si abre un diálogo, el foco vuelve bien).
				menu.Bind(wx.EVT_MENU, lambda _e, fn=funcion: wx.CallAfter(self.ejecutar, fn), item)
		return menu

	def menu_contextual(self, control: wx.Window, entradas: Callable[[], Sequence[Entrada]]) -> None:
		"""Menú contextual (tecla Aplicaciones, Mayús+F10 o botón derecho) de un control."""

		def crear() -> wx.Menu | None:
			lista = list(entradas())
			return self._crear_menu(lista) if lista else None

		vincular_menu_contextual(control, crear)

	def teclas_de_lista(self, lista: wx.ListCtrl, teclas: dict[str, Callable[[], None]],
		al_activar: Callable[[], None] | None = None) -> None:
		"""Teclas propias de una lista («Supr», «F2», «Ctrl+Intro»...). Intro activa ``al_activar``."""
		normalizadas = {normalizar_atajo(t): fn for t, fn in teclas.items()}

		def al_pulsar(evento: wx.KeyEvent) -> None:
			funcion = normalizadas.get(texto_tecla(evento))
			if funcion is not None:
				self.ejecutar(funcion)
				return
			evento.Skip()

		lista.Bind(wx.EVT_KEY_DOWN, al_pulsar)
		if al_activar is not None:
			lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.ejecutar(al_activar))

	def mostrar(self, foco: wx.Window | None = None) -> None:
		"""Muestra la ventana, suena «abrir» y pone el foco en el control más útil."""
		asegurar_ayudas(self)
		self.Show()
		self.ctx.sonar("abrir")
		if foco is not None:
			foco.SetFocus()

	# ── Acciones ──────────────────────────────────────────────────────────────

	def ejecutar(self, funcion: Callable[[], Any]) -> None:
		"""Ejecuta una acción de menú o tecla; un fallo se registra y se explica, la ventana sigue viva."""
		try:
			funcion()
		except Exception as error:  # noqa: BLE001 - se registra y se informa
			log.exception("Fallo en una acción de la ventana «%s»", self.GetTitle())
			mostrar_error(self, mensaje_error(error), _("Error"))

	def estado(self, texto: str) -> None:
		if self.viva():
			self.SetStatusText(texto)

	def en_fondo(
		self,
		funcion: Callable[[], Any],
		*,
		al_terminar: Callable[[Any], None] | None = None,
		al_fallar: Callable[[BaseException], None] | None = None,
		exito: str | Callable[[Any], str] = "",
		inicio: str = "",
		sonido: str = "completado",
		titulo_error: str = "",
	) -> Any:
		"""``en_segundo_plano`` que descarta el resultado si la ventana ya se cerró."""

		def terminado(resultado: Any) -> None:
			if al_terminar is not None and self.viva():
				al_terminar(resultado)

		def fallado(error: BaseException) -> None:
			if al_fallar is not None and self.viva():
				al_fallar(error)
				return
			mostrar_error(self if self.viva() else None, mensaje_error(error), titulo_error or _("No se pudo completar"))

		return en_segundo_plano(self, self.ctx, funcion, exito=exito, al_terminar=terminado, al_fallar=fallado,
			inicio=inicio, sonido=sonido)

	def descargar(self, url: str, destino: Path, aceptar: str = "application/octet-stream", descripcion: str = "",
		al_terminar: Callable[[Path], None] | None = None) -> Any:
		"""Descarga a disco con progreso en la barra de estado y anuncios SOLO en los hitos."""
		from app.core.tareas import HitosProgreso

		cliente = self.ctx.api().c
		descripcion = descripcion or destino.name
		hitos = HitosProgreso(25)
		self.ctx.avisar(_("Descargando {d}…").format(d=descripcion))
		self.estado(_("Descargando {d}…").format(d=descripcion))

		def trabajo(tarea: Any) -> Path:
			return cliente.descargar(url, destino, aceptar=aceptar,
				progreso=lambda hecho, total: tarea.progresar(hecho, total),
				cancelado=lambda: bool(getattr(tarea, "cancelado", False)))

		def al_progresar(progreso: Any) -> None:
			porcentaje = progreso.porcentaje
			if porcentaje is None:
				self.estado(_("{d}: {t} descargados").format(d=descripcion, t=f.tamano(progreso.hecho)))
				return
			self.estado(_("{d}: {p} %").format(d=descripcion, p=porcentaje))
			hito = hitos.nuevo_hito(porcentaje)
			if hito is not None and hito < 100:
				self.ctx.avisar(_("{p} por ciento").format(p=hito), interrumpir=False)

		def terminado(ruta: Path) -> None:
			self.ctx.sonar("descargado")
			texto = _("Descargado {d} en {c}.").format(d=descripcion, c=str(Path(ruta).parent))
			self.ctx.avisar(texto, interrumpir=False)
			self.estado(texto)
			if al_terminar is not None and self.viva():
				al_terminar(Path(ruta))

		def fallado(error: BaseException) -> None:
			self.ctx.sonar("error")
			self.estado(_("Falló la descarga de {d}.").format(d=descripcion))
			mostrar_error(self if self.viva() else None, mensaje_error(error), _("No se pudo descargar"))

		tarea = self.ctx.tareas.enviar(trabajo, al_terminar=terminado, al_fallar=fallado, al_progresar=al_progresar,
			nombre=f"descargar:{destino.name}", duplicadas="permitir")
		if tarea is not None:
			self._descargas.append(tarea)
		return tarea

	# ── Eventos ───────────────────────────────────────────────────────────────

	def _al_tecla_ventana(self, evento: wx.KeyEvent) -> None:
		if evento.GetModifiers() == wx.MOD_CONTROL and evento.GetKeyCode() == ord("H"):
			describir_control_enfocado(self)
			return
		evento.Skip()

	def al_cerrar(self) -> None:
		"""Para las subclases: parar temporizadores, etc."""

	def _al_cerrar_ventana(self, evento: wx.CloseEvent) -> None:
		self.cerrada = True
		try:
			self.al_cerrar()
		except Exception:  # noqa: BLE001 - cerrar no debe fallar nunca
			log.exception("Fallo al cerrar la ventana «%s»", self.GetTitle())
		for tarea in self._descargas:
			if not getattr(tarea, "terminada", True):
				try:
					tarea.cancelar(_("Se cerró la ventana."))
				except Exception:  # noqa: BLE001
					log.debug("No se pudo cancelar una descarga al cerrar", exc_info=True)
		if self.clave and VentanaDetalle._abiertas.get(self.clave) is self:
			VentanaDetalle._abiertas.pop(self.clave, None)
		self.ctx.sonar("cerrar")
		evento.Skip()


def entrada_cerrar(ventana: wx.Frame, etiqueta: str = "") -> tuple:
	"""Entrada de menú «Cerrar (Ctrl+W)»: Escape no cierra las ventanas, Ctrl+W sí."""
	return (etiqueta or _("C&errar la ventana\tCtrl+W"), ventana.Close, _("Cierra esta ventana."))
