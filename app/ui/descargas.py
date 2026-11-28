"""Ventana «Descargas» (el gestor) y la forma de pedir una descarga desde cualquier ventana.

- ``iniciar_descarga(padre, ctx, url, destino, ...)``: la pone en el gestor de la
  aplicación. La ventana que la pide puede cerrarse: la descarga sigue.
- ``abrir_gestor(ctx)``: la ventana con la lista de descargas, que se puede cerrar
  y volver a abrir cuando se quiera (Control+Mayúsculas+D en la ventana principal y
  en las de detalle, Herramientas, «Descargas», el menú de la bandeja o una tecla
  global).
- ``instalar_avisos(ctx)``: sonido y aviso al terminar o fallar cada descarga,
  aunque la ventana del gestor esté cerrada.

En la lista: Intro abre el archivo terminado (o pausa y reanuda), Espacio pausa o
reanuda, Suprimir cancela o quita, Control+O abre la carpeta y Control+D dice el
estado de la elegida. Los botones repiten todo. Las filas se actualizan solas,
sin anunciar cada cambio: al moverse por la lista se oye el progreso al día.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx

from app.services import formato as f
from app.services import gestor_descargas as gd
from app.ui.accesibilidad.dialogos import confirmar, mostrar_error
from app.ui.accesibilidad.foco import enfocar
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.teclado import vincular_menu_contextual
from app.ui.vistas.base import preferencias_lectura, texto_tecla

log = logging.getLogger(__name__)

_ventana: VentanaDescargas | None = None
_quitar_avisos: list[Callable[[], None]] = []


# ════════════════════════════════════════════════════════════════════════════
# Pedir una descarga
# ════════════════════════════════════════════════════════════════════════════


def iniciar_descarga(padre: wx.Window | None, ctx: Any, url: str, destino: Path, nombre: str = "", *, aceptar: str = "",
	sha256: str = "", origen: str = "", sobrescribir: bool = False,
	al_terminar: Callable[[Path], None] | None = None) -> gd.Descarga | None:
	"""Añade la descarga al gestor de la aplicación y lo dice. ``al_terminar(ruta)`` al completarse."""
	gestor = getattr(ctx, "descargas", None)
	if gestor is None:
		return None
	if not aceptar:
		from app.services.github.cliente import aceptar_para_descarga

		aceptar = aceptar_para_descarga(url)
	cuenta = ctx.cuenta.clave if getattr(ctx, "cuenta", None) else ""
	descarga = gestor.anadir(url, destino, nombre or Path(destino).name, aceptar=aceptar, sha256=sha256, cuenta=cuenta, origen=origen,
		sobrescribir=sobrescribir)
	if al_terminar is not None:
		_al_completar(gestor, descarga.id, al_terminar)
	if descarga.estado == gd.PENDIENTE:
		texto = _("«{n}» está en la cola de descargas (Control+Mayúsculas+D para verla).").format(n=descarga.nombre)
	else:
		texto = _("Descargando «{n}». Puede cerrar esta ventana: la descarga sigue (Control+Mayúsculas+D para verla).").format(
			n=descarga.nombre)
	ctx.avisar(texto)
	if ctx.config.obtener("descargas.abrir_gestor", False):
		abrir_gestor(ctx)
	return descarga


def _al_completar(gestor: gd.GestorDescargas, identificador: str, funcion: Callable[[Path], None]) -> None:
	"""Llama a ``funcion(ruta)`` una vez, en el hilo de la interfaz, cuando esa descarga se complete."""
	quitar: list[Callable[[], None]] = []

	def oyente(evento: str, descarga: gd.Descarga) -> None:
		if descarga.id != identificador or evento not in ("estado", "quitada"):
			return
		if descarga.estado == gd.COMPLETADA and evento == "estado":
			wx.CallAfter(funcion, Path(descarga.ruta_final or descarga.destino))
		if descarga.estado in (gd.COMPLETADA, gd.CANCELADA) or evento == "quitada":
			for q in quitar:
				q()

	quitar.append(gestor.suscribir(oyente))


def instalar_avisos(ctx: Any) -> None:
	"""Sonido y aviso al completarse o fallar cualquier descarga (una sola vez por aplicación)."""
	gestor = getattr(ctx, "descargas", None)
	if gestor is None or _quitar_avisos:
		return

	def oyente(evento: str, descarga: gd.Descarga) -> None:
		if evento != "estado" or descarga.estado not in (gd.COMPLETADA, gd.ERROR):
			return

		def avisar() -> None:
			if ctx.horas_silencio.silenciar("otro"):
				return  # horas de silencio (incidencia #15): se resume al terminar
			if descarga.estado == gd.COMPLETADA:
				ctx.sonar("descargado")
				texto = _("Descarga completada: {n}.").format(n=descarga.nombre)
				if descarga.sha256:
					texto += " " + _("Su suma SHA-256 coincide con la de GitHub.")
			else:
				ctx.sonar("error")
				texto = _("Falló la descarga de {n}: {e}").format(n=descarga.nombre, e=descarga.error)
			ctx.avisar_en_segundo_plano(texto)

		wx.CallAfter(avisar)

	_quitar_avisos.append(gestor.suscribir(oyente))


def instalar_tecla(ventana: wx.Frame, ctx: Any) -> None:
	"""Control+Mayúsculas+D abre «Descargas» desde ``ventana`` (salvo que su menú ya use esa tecla).

	Se pone después de crear la barra de menús. Usa ``instalar_atajos``, que deja la tecla
	anotada para la revisión de teclado.
	"""
	from app.ui.accesibilidad.teclado import instalar_atajos

	barra = ventana.GetMenuBar()
	if barra is not None:
		for indice in range(barra.GetMenuCount()):
			if any(e.GetItemLabel().endswith("\tCtrl+Shift+D") for e in barra.GetMenu(indice).GetMenuItems()):
				return
	instalar_atajos(ventana, [(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("D"), lambda: abrir_gestor(ctx))])


def abrir_gestor(ctx: Any, padre: wx.Window | None = None) -> VentanaDescargas | None:
	"""Abre la ventana «Descargas» (o la trae al frente si ya está abierta)."""
	global _ventana
	if getattr(ctx, "descargas", None) is None:
		return None
	if _ventana is not None and _ventana:
		_ventana.Show()
		_ventana.Raise()
		enfocar(_ventana.lista)
		return _ventana
	_ventana = VentanaDescargas(ctx)
	_ventana.Show()
	enfocar(_ventana.lista)
	return _ventana


# ════════════════════════════════════════════════════════════════════════════
# Textos de una descarga
# ════════════════════════════════════════════════════════════════════════════


def texto_estado(d: gd.Descarga) -> str:
	return _(gd.NOMBRES_ESTADO.get(d.estado, d.estado))


def texto_progreso(d: gd.Descarga) -> str:
	if d.porcentaje is not None:
		return _("{p} %").format(p=d.porcentaje)
	return f.tamano(d.hecho) if d.hecho else ""


def texto_tamano(d: gd.Descarga) -> str:
	if d.total:
		return _("{h} de {t}").format(h=f.tamano(d.hecho), t=f.tamano(d.total))
	return f.tamano(d.hecho) if d.hecho else ""


def texto_velocidad(d: gd.Descarga) -> str:
	return _("{v} por segundo").format(v=f.tamano(int(d._velocidad))) if d.estado == gd.DESCARGANDO and d._velocidad > 0 else ""


def texto_restante(d: gd.Descarga) -> str:
	segundos = d.restante_s
	return f.duracion(segundos) if segundos is not None else ""


def resumen(d: gd.Descarga) -> str:
	"""Lo que dice Control+D: nombre, estado y lo que importe en ese estado."""
	partes = [d.nombre, texto_estado(d)]
	if d.estado in (gd.DESCARGANDO, gd.PAUSADA, gd.PENDIENTE) and (d.hecho or d.total):
		partes.append(texto_tamano(d) + (f" ({texto_progreso(d)})" if d.porcentaje is not None else ""))
	if texto_velocidad(d):
		partes.append(texto_velocidad(d))
	if texto_restante(d):
		partes.append(_("quedan {t}").format(t=texto_restante(d)))
	if d.estado == gd.ERROR and d.error:
		partes.append(d.error)
	if d.estado == gd.COMPLETADA:
		partes.append(str(Path(d.ruta_final or d.destino)))
	return ". ".join(p for p in partes if p) + "."


COLUMNAS: list[tuple[str, Callable[[gd.Descarga], str], int]] = [
	(N_("Nombre"), lambda d: d.nombre, 260),
	(N_("Estado"), texto_estado, 110),
	(N_("Progreso"), texto_progreso, 80),
	(N_("Tamaño"), texto_tamano, 170),
	(N_("Velocidad"), texto_velocidad, 130),
	(N_("Tiempo restante"), texto_restante, 110),
	(N_("Origen"), lambda d: d.origen, 220),
	(N_("Carpeta"), lambda d: str(Path(d.ruta_final or d.destino).parent), 260),
	(N_("Error"), lambda d: d.error, 300),
]


def fila(d: gd.Descarga) -> list[str]:
	return [funcion(d) for _titulo, funcion, _ancho in COLUMNAS]


# ════════════════════════════════════════════════════════════════════════════
# Ventana
# ════════════════════════════════════════════════════════════════════════════


class VentanaDescargas(wx.Frame):
	"""Lista de descargas con sus órdenes. Cerrarla NO para ninguna descarga."""

	def __init__(self, ctx: Any) -> None:
		super().__init__(None, title=_("Descargas"), size=(980, 520))
		self.ctx = ctx
		self.gestor: gd.GestorDescargas = ctx.descargas
		self.ids: list[str] = []
		self._pendiente_refresco = False
		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)

		raiz.Add(wx.StaticText(panel, label=_("&Lista de descargas:")), 0, wx.LEFT | wx.TOP, 6)
		self.lista = ListaAccesible(panel, _("Descargas"), [(_(t), self.FromDIP(a)) for t, _fn, a in COLUMNAS],
			leer_preferencias=preferencias_lectura(ctx.config))
		self.lista.SetHelpText(_(
			"Descargas de la aplicación, también las de ventanas ya cerradas. Intro abre el archivo terminado o pausa y "
			"reanuda; Espacio pausa o reanuda; Suprimir cancela la descarga o la quita de la lista; Control+O abre la "
			"carpeta; Control+D dice su estado. Izquierda y derecha leen las columnas."))
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 6)
		self.estado = wx.StaticText(panel, label="")
		raiz.Add(self.estado, 0, wx.LEFT | wx.RIGHT, 6)

		botones = wx.WrapSizer(wx.HORIZONTAL)
		self.botones: dict[str, wx.Button] = {}
		for clave, etiqueta, ayuda, funcion in (
			("pausar", _("&Pausar"), _("Para la descarga elegida conservando lo bajado (Espacio)."), self.pausar),
			("reanudar", _("&Reanudar"), _("Sigue donde se quedó, o vuelve a intentarlo si falló (Espacio)."), self.reanudar),
			("cancelar", _("Ca&ncelar la descarga"), _("La para y borra lo bajado (Suprimir)."), self.cancelar),
			("abrir", _("Abrir el arc&hivo"), _("Abre el archivo descargado con su programa (Intro)."), self.abrir_archivo),
			("carpeta", _("Abrir la c&arpeta"), _("Abre en el Explorador la carpeta de la descarga (Control+O)."), self.abrir_carpeta),
			("quitar", _("&Quitar de la lista"), _("Quita la descarga de la lista; el archivo descargado no se borra."), self.quitar),
			("terminadas", _("Quitar las &terminadas"), _("Quita de la lista las completadas y las canceladas."), self.quitar_terminadas),
			("pausar_todas", _("Pausar to&das"), _("Pausa todas las descargas en curso o en cola."), self.pausar_todas),
			("reanudar_todas", _("Reanudar todas las en pa&usa"), _("Reanuda todas las que están en pausa o con error."),
				self.reanudar_todas),
			("cerrar", _("C&errar"), _("Cierra esta ventana; las descargas siguen."), self.Close),
		):
			boton = wx.Button(panel, label=etiqueta)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, lambda _e, fn=funcion: fn())
			botones.Add(boton, 0, wx.ALL, 4)
			self.botones[clave] = boton
		raiz.Add(botones, 0, wx.ALL, 2)
		panel.SetSizer(raiz)

		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_pulsar)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.activar())
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda e: (e.Skip(), self._actualizar_botones()))
		vincular_menu_contextual(self.lista, self._menu)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla_ventana)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self._quitar_oyente = self.gestor.suscribir(self._al_cambiar)
		self.refrescar()
		if self.ids:
			self.lista.enfocar_fila(0, anunciar=False)

	# ── Datos ─────────────────────────────────────────────────────────────────

	@property
	def elegida(self) -> gd.Descarga | None:
		fila_actual = self.lista.fila_actual()
		if fila_actual == wx.NOT_FOUND or fila_actual >= len(self.ids):
			return None
		return self.gestor.buscar(self.ids[fila_actual])

	def refrescar(self) -> None:
		"""Vuelve a pintar todo conservando la descarga enfocada."""
		elegida = self.elegida
		# Las más recientes arriba: lo último que se ha pedido es lo que se quiere ver.
		descargas = list(reversed(self.gestor.descargas()))
		self.ids = [d.id for d in descargas]
		self.lista.reemplazar_filas([fila(d) for d in descargas], conservar_foco=True)
		if elegida is not None and elegida.id in self.ids:
			self.lista.enfocar_fila(self.ids.index(elegida.id), anunciar=False)
		self._actualizar_estado()
		self._actualizar_botones()

	def _actualizar_estado(self) -> None:
		cuentas = self.gestor.cuenta_por_estado()
		if not cuentas:
			self.estado.SetLabel(_("No hay descargas. Las que pida desde una release, un artefacto o el código en zip aparecen aquí."))
			return
		partes = [_("{n} {e}").format(n=n, e=_(gd.NOMBRES_ESTADO[e]).lower()) for e, n in cuentas.items() if e in gd.NOMBRES_ESTADO]
		self.estado.SetLabel(", ".join(partes) + ".")

	def _actualizar_botones(self) -> None:
		d = self.elegida
		estado = d.estado if d else ""
		disponibles = {
			"pausar": estado in (gd.DESCARGANDO, gd.PENDIENTE),
			"reanudar": estado in (gd.PAUSADA, gd.ERROR, gd.CANCELADA),
			"cancelar": estado in (gd.DESCARGANDO, gd.PENDIENTE, gd.PAUSADA, gd.ERROR),
			"abrir": estado == gd.COMPLETADA,
			"carpeta": d is not None,
			"quitar": d is not None,
		}
		for clave, activo in disponibles.items():
			# Un botón que se desactiva con el foco encima lo dejaría en ninguna parte: no se toca el que tiene el foco.
			if self.botones[clave].HasFocus() and not activo:
				continue
			self.botones[clave].Enable(activo)

	def _al_cambiar(self, evento: str, descarga: gd.Descarga) -> None:
		"""Avisos del gestor (desde cualquier hilo): se repinta en el de la interfaz, agrupando."""
		if evento in ("anadida", "quitada"):
			wx.CallAfter(self._refrescar_si_viva)
			return
		if not self._pendiente_refresco:
			self._pendiente_refresco = True
			wx.CallAfter(self._actualizar_fila, descarga.id)

	def _refrescar_si_viva(self) -> None:
		if self:
			self.refrescar()

	def _actualizar_fila(self, identificador: str) -> None:
		self._pendiente_refresco = False
		if not self:
			return
		# Se repintan todas las filas que cambian (barato: pocas descargas), sin mover el foco.
		for posicion, ident in enumerate(self.ids):
			d = self.gestor.buscar(ident)
			if d is not None:
				self.lista.actualizar_fila(posicion, fila(d))
		self._actualizar_estado()
		self._actualizar_botones()

	# ── Órdenes ───────────────────────────────────────────────────────────────

	def _con_elegida(self) -> gd.Descarga | None:
		d = self.elegida
		if d is None:
			self.ctx.avisar(_("No hay ninguna descarga elegida."))
		return d

	def pausar(self) -> None:
		d = self._con_elegida()
		if d is not None and self.gestor.pausar(d.id):
			self.ctx.avisar(_("En pausa: {n}.").format(n=d.nombre))

	def reanudar(self) -> None:
		d = self._con_elegida()
		if d is not None and self.gestor.reanudar(d.id):
			self.ctx.avisar(_("Reanudada: {n}.").format(n=d.nombre))

	def alternar(self) -> None:
		d = self._con_elegida()
		if d is None:
			return
		if d.estado in (gd.DESCARGANDO, gd.PENDIENTE):
			self.pausar()
		elif d.estado in (gd.PAUSADA, gd.ERROR, gd.CANCELADA):
			self.reanudar()
		else:
			self.ctx.avisar(resumen(d))

	def cancelar(self) -> None:
		d = self._con_elegida()
		if d is None or d.estado in (gd.COMPLETADA, gd.CANCELADA):
			return
		if confirmar(self, _("¿Cancelar la descarga de {n}? Se borrará lo que ya se ha bajado.").format(n=d.nombre),
				_("Cancelar la descarga"), peligroso=True) != wx.ID_YES:
			return
		if self.gestor.cancelar(d.id):
			self.ctx.avisar(_("Cancelada: {n}.").format(n=d.nombre))

	def quitar(self) -> None:
		d = self._con_elegida()
		if d is None:
			return
		if d.estado not in (gd.COMPLETADA, gd.CANCELADA) and confirmar(
				self, _("{n} no ha terminado. ¿Cancelarla y quitarla de la lista? Se borrará lo que ya se ha bajado.").format(n=d.nombre),
				_("Quitar de la lista"), peligroso=True) != wx.ID_YES:
			return
		self.gestor.quitar(d.id)
		self.ctx.avisar(_("Quitada de la lista: {n}.").format(n=d.nombre))

	def quitar_terminadas(self) -> None:
		cuantas = self.gestor.quitar_terminadas()
		self.ctx.avisar(ngettext("{n} descarga quitada de la lista.", "{n} descargas quitadas de la lista.", cuantas).format(n=cuantas)
			if cuantas else _("No hay descargas terminadas que quitar."))

	def pausar_todas(self) -> None:
		cuantas = self.gestor.pausar_todas()
		self.ctx.avisar(ngettext("{n} descarga en pausa.", "{n} descargas en pausa.", cuantas).format(n=cuantas)
			if cuantas else _("No hay descargas en curso."))

	def reanudar_todas(self) -> None:
		cuantas = self.gestor.reanudar_todas()
		self.ctx.avisar(ngettext("{n} descarga reanudada.", "{n} descargas reanudadas.", cuantas).format(n=cuantas)
			if cuantas else _("No hay descargas en pausa ni con error."))

	def abrir_archivo(self) -> None:
		d = self._con_elegida()
		if d is None:
			return
		ruta = Path(d.ruta_final or d.destino)
		if d.estado != gd.COMPLETADA or not ruta.exists():
			self.ctx.avisar(_("{n} todavía no está descargado.").format(n=d.nombre) if d.estado != gd.COMPLETADA
				else _("El archivo ya no está en {r}.").format(r=ruta))
			return
		try:
			os.startfile(str(ruta))  # noqa: S606 - abrir el archivo que la persona ha descargado
		except OSError as error:
			mostrar_error(self, _("No se pudo abrir {n}: {e}").format(n=ruta.name, e=error), _("Abrir el archivo"))

	def abrir_carpeta(self) -> None:
		d = self._con_elegida()
		if d is None:
			return
		ruta = Path(d.ruta_final or d.destino)
		carpeta = ruta.parent
		try:
			if ruta.exists():
				import subprocess

				subprocess.Popen(["explorer", "/select,", str(ruta)])  # noqa: S603, S607 - el Explorador de Windows
			else:
				os.startfile(str(carpeta))  # noqa: S606
		except OSError as error:
			mostrar_error(self, _("No se pudo abrir la carpeta {c}: {e}").format(c=carpeta, e=error), _("Abrir la carpeta"))

	def activar(self) -> None:
		d = self.elegida
		if d is not None and d.estado == gd.COMPLETADA:
			self.abrir_archivo()
		else:
			self.alternar()

	def decir_estado(self) -> None:
		d = self._con_elegida()
		if d is not None:
			self.ctx.avisar(resumen(d))

	# ── Teclado y menú ────────────────────────────────────────────────────────

	def _menu(self) -> wx.Menu:
		menu = wx.Menu()
		d = self.elegida
		entradas = [
			(_("&Pausar o reanudar (Espacio)"), self.alternar, d is not None),
			(_("Abrir el arc&hivo (Intro)"), self.abrir_archivo, d is not None and d.estado == gd.COMPLETADA),
			(_("Abrir la c&arpeta (Control+O)"), self.abrir_carpeta, d is not None),
			(_("&Decir el estado (Control+D)"), self.decir_estado, d is not None),
			(_("Ca&ncelar la descarga (Suprimir)"), self.cancelar, d is not None and d.estado not in (gd.COMPLETADA, gd.CANCELADA)),
			(_("&Quitar de la lista"), self.quitar, d is not None),
		]
		for etiqueta, funcion, activa in entradas:
			item = menu.Append(wx.ID_ANY, etiqueta)
			item.Enable(bool(activa))
			menu.Bind(wx.EVT_MENU, lambda _e, fn=funcion: wx.CallAfter(fn), item)
		return menu

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla = texto_tecla(evento)
		acciones = {"Espacio": self.alternar, "Supr": self._suprimir, "Ctrl+O": self.abrir_carpeta, "Ctrl+D": self.decir_estado}
		accion = acciones.get(tecla)
		if accion is not None:
			accion()
			return
		evento.Skip()

	def _suprimir(self) -> None:
		d = self.elegida
		if d is not None and d.estado in (gd.COMPLETADA, gd.CANCELADA):
			self.quitar()
		else:
			self.cancelar()

	def _al_tecla_ventana(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_ESCAPE and not evento.HasAnyModifiers():
			self.Close()
			return
		evento.Skip()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		global _ventana
		try:
			self._quitar_oyente()
		except Exception:  # noqa: BLE001 - cerrar no debe fallar
			log.debug("No se pudo quitar el oyente del gestor", exc_info=True)
		if _ventana is self:
			_ventana = None
		evento.Skip()
