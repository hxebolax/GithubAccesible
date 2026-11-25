"""Ventana principal de GitHub Accesible.

Disposición (de izquierda a derecha, en orden de tabulación):

1. «Secciones»: lista con Inicio, Notificaciones, Mis repositorios, Estrellas,
   Mis issues, Mis pull requests, Gists, Organizaciones, Proyectos,
   Repositorios locales... Al moverse por ella se muestra la sección.
2. El contenido de la sección: una lista accesible (``PanelLista``).

Teclas globales (también en los menús): F6 alterna entre secciones y
contenido; Alt+1 a Alt+9 y Alt+0 van a cada sección; F5 actualiza; Ctrl+O
abre un repositorio por nombre o enlace; Ctrl+E busca en GitHub; Ctrl+U
muestra un perfil; Ctrl+Mayús+N crea un repositorio; Ctrl+Mayús+K clona;
Ctrl+Mayús+G abre un repositorio local; Ctrl+Mayús+L añade una cuenta;
Ctrl+Mayús+U cambia de cuenta; Ctrl+P abre Preferencias; Ctrl+Q sale.
El menú «Acciones» cambia según la sección y el elemento elegido.
"""

from __future__ import annotations

import builtins
import logging
import os
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx

from app.core import paths
from app.core.instancia_unica import ORDEN_ABRIR, ORDEN_MOSTRAR, InstanciaUnica, traer_al_frente
from app.core.version import APP_VERSION, NOMBRE_APLICACION, URL_DONACIONES, URL_PROYECTO
from app.ui import abrir
from app.ui.accesibilidad.dialogos import pedir_texto
from app.ui import orden_secciones, paleta
from app.ui.bandeja import IconoBandeja, OrdenBandeja
from app.ui.comunes import confirmar, elegir_uno, en_segundo_plano, mostrar_error, mostrar_mensaje
from app.ui.vistas import principales
from app.ui.teclas_globales import GestorTeclasGlobales
from app.ui.vistas.base import PanelLista, atajo_visible

log = logging.getLogger(__name__)

#: Secciones que no se actualizan solas: Notificaciones ya se comprueba en segundo plano y
#: Búsqueda es lo que la persona ha buscado (y su límite de GitHub es mucho más bajo).
SECCIONES_SIN_ACTUALIZACION = ("notificaciones", "busqueda")
#: Cada cuánto se mira si la sección a la vista ya toca actualizarse.
INTERVALO_REVISAR_LISTAS_MS = 30_000

INTERVALO_BUZON_MS = 700
TAMANO_MINIMO = (640, 420)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class VentanaPrincipal(wx.Frame):
	"""Ventana principal: secciones a la izquierda y su lista a la derecha."""

	def __init__(self, contexto: Any, instancia: InstanciaUnica | None = None) -> None:
		super().__init__(None, title=NOMBRE_APLICACION)
		self.ctx = contexto
		contexto.ventana_principal = self
		self._instancia = instancia
		self._bandeja: IconoBandeja | None = None
		self._forzar_salida = False
		self._rect_normal: wx.Rect | None = None
		self._ids_acciones: list[int] = []
		self._notificaciones_vistas: set[str] = set()
		self._primera_comprobacion = True
		self._sin_leer = 0
		self._ultimas_notificaciones: list[dict] = []
		# Todas las secciones (de fábrica) y las visibles en el orden que eligió la persona.
		self._todas_definiciones = [(clave, fabrica()) for clave, fabrica in principales.SECCIONES]
		self.definiciones = self._secciones_visibles()
		self.paneles: dict[str, PanelLista] = {}
		self.config_actualizador = None
		self.comprobador_actualizaciones = None

		self._crear_contenido()
		self._crear_menus()
		self.CreateStatusBar(2)
		self.SetStatusWidths([-2, -3])
		self._aplicar_icono()
		self._restaurar_geometria()
		self._actualizar_titulo()

		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.Bind(wx.EVT_ICONIZE, self._al_minimizar)
		self.Bind(wx.EVT_SIZE, self._al_cambiar_geometria)
		self.Bind(wx.EVT_MOVE, self._al_cambiar_geometria)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_tecla)

		self._temporizador_buzon = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, self._al_revisar_buzon, self._temporizador_buzon)
		if self._instancia is not None:
			self._temporizador_buzon.Start(INTERVALO_BUZON_MS)
		self._temporizador_notificaciones = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self.comprobar_notificaciones(), self._temporizador_notificaciones)
		self._temporizador_estado = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self._actualizar_estado(), self._temporizador_estado)
		self._temporizador_estado.Start(20000)
		contexto.cuentas.suscribir(lambda _cuenta: wx.CallAfter(self._al_cambiar_cuenta))
		contexto.config.suscribir(self._al_cambiar_config, prefijo="notificaciones.")
		contexto.config.suscribir(self._al_cambiar_config, prefijo="actualizaciones.")
		contexto.config.suscribir(self._al_cambiar_config, prefijo="teclas_globales.")
		contexto.config.suscribir(self._al_cambiar_config, prefijo="secciones.")
		contexto.config.suscribir(self._al_cambiar_config, prefijo="general.icono_bandeja")
		contexto.config.suscribir(self._al_cambiar_config, prefijo="acciones.")

		# Teclas que funcionan desde cualquier programa (se registran ya: la ventana existe aunque esté oculta).
		self.teclas_globales = GestorTeclasGlobales(self, contexto.config, {
			"mostrar_ocultar": self.mostrar_u_ocultar,
			"decir_notificaciones": self.decir_notificaciones,
			"abrir_notificaciones": self.abrir_notificaciones_desde_fuera,
			"buscar": self.buscar_desde_fuera,
			"comprobar_notificaciones": lambda: self.comprobar_notificaciones(informar=True),
			"abrir_descargas": self.abrir_descargas,
		}, avisar=lambda texto: self.ctx.avisar(texto, interrumpir=False))
		wx.CallAfter(self.teclas_globales.registrar)
		paleta.instalar(self)

		# Ejecuciones de Actions vigiladas en segundo plano.
		self._vigilando = False
		self._temporizador_actions = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self.comprobar_vigiladas(), self._temporizador_actions)
		wx.CallAfter(self.programar_vigilancia)
		wx.CallAfter(self._actualizar_bandeja)

		# Secciones que se ponen al día solas (incidencia #14). El temporizador solo mira cada
		# poco si la sección a la vista ya toca: las peticiones las decide «cada cuántos minutos».
		self._temporizador_listas = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, lambda _e: self.actualizar_seccion_sola(), self._temporizador_listas)
		contexto.config.suscribir(self._al_cambiar_config, prefijo="listas.actualizar")
		wx.CallAfter(self.programar_actualizacion_listas)

		inicial = contexto.config.obtener("general.seccion_inicial", "notificaciones")
		visibles = dict(self.definiciones)
		self.ir_a_seccion(inicial if inicial in visibles else next(iter(visibles)), enfocar=False)

	# ── Construcción ──────────────────────────────────────────────────────────

	def _crear_contenido(self) -> None:
		self.panel = wx.Panel(self)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		izquierda = wx.BoxSizer(wx.VERTICAL)
		izquierda.Add(wx.StaticText(self.panel, label=_("&Secciones:")), 0, wx.ALL, 4)
		self.secciones = wx.ListBox(self.panel, choices=[d.titulo for _c, d in self.definiciones], style=wx.LB_SINGLE)
		self.secciones.SetHelpText(_(
			"Secciones de GitHub. Muévase con las flechas: la sección se muestra a la derecha. "
			"Tabulador o F6 pasa a su lista; Alt más un número salta a cada sección."
		))
		self.secciones.Bind(wx.EVT_LISTBOX, self._al_elegir_seccion)
		self.secciones.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.enfocar_contenido())
		self.secciones.Bind(wx.EVT_KEY_DOWN, self._al_tecla_secciones)
		izquierda.Add(self.secciones, 1, wx.EXPAND | wx.ALL, 4)
		fila.Add(izquierda, 0, wx.EXPAND)
		self.libro = wx.Simplebook(self.panel)
		fila.Add(self.libro, 1, wx.EXPAND)
		self.panel.SetSizer(fila)
		self.secciones.SetMinSize(self.FromDIP(wx.Size(220, -1)))

	def _item(self, menu: wx.Menu, etiqueta: str, ayuda: str, manejador: Callable[[], Any], nombre: str = "") -> wx.MenuItem:
		elemento = menu.Append(wx.ID_ANY, etiqueta, ayuda)
		self.Bind(wx.EVT_MENU, lambda _e: manejador(), elemento)
		if nombre:
			self.elementos_menu[nombre] = elemento
		return elemento

	def _crear_menus(self) -> None:
		self.elementos_menu: dict[str, wx.MenuItem] = {}
		barra = wx.MenuBar()

		archivo = wx.Menu()
		self._item(archivo, _("&Abrir un repositorio por nombre o enlace…\tCtrl+O"), _("Escriba «dueño/repositorio» o pegue un enlace de GitHub."), self.abrir_por_nombre, "abrir")
		self._item(archivo, _("&Nuevo repositorio…\tCtrl+Shift+N"), _("Crea un repositorio en GitHub."), self.nuevo_repositorio, "nuevo")
		self._item(archivo, _("C&lonar un repositorio…\tCtrl+Shift+K"), _("Clona un repositorio en una carpeta de este equipo."), self.clonar, "clonar")
		self._item(archivo, _("Abrir una carpeta de &git local…\tCtrl+Shift+G"), _("Abre una carpeta con un repositorio de git."), self.abrir_local, "local")
		self._item(archivo, _("Nuevo gis&t…"), _("Crea un gist."), self.nuevo_gist)
		archivo.AppendSeparator()
		self._item(archivo, _("&Iniciar sesión con otra cuenta…\tCtrl+Shift+L"), _("Añade una cuenta de GitHub o de GitHub Enterprise."), self.iniciar_sesion, "sesion")
		self._item(archivo, _("Cambiar de c&uenta…\tCtrl+Shift+U"), _("Elige la cuenta activa."), self.cambiar_cuenta, "cambiar_cuenta")
		self._item(archivo, _("Ad&ministrar las cuentas…"), _("Lista de cuentas: añadir, comprobar y quitar."), self.gestionar_cuentas)
		archivo.AppendSeparator()
		self._item(archivo, _("Ocultar en la &bandeja del sistema"), _("Oculta la ventana; la aplicación sigue en la bandeja, junto al reloj."),
			self.ocultar_en_bandeja, "ocultar")
		self._item(archivo, _("&Salir\tCtrl+Q"), _("Cierra la aplicación."), self.salir, "salir")
		barra.Append(archivo, _("&Archivo"))

		barra.Append(self._crear_menu_ver(), _("&Ver"))

		self.menu_acciones = wx.Menu()
		barra.Append(self.menu_acciones, _("Ac&ciones"))
		self.Bind(wx.EVT_MENU_OPEN, self._al_abrir_menu)

		ir = wx.Menu()
		self._item(ir, _("&Buscar en GitHub…\tCtrl+E"), _("Busca repositorios, código, issues, usuarios, commits o temas."), self.buscar, "buscar")
		self._item(ir, _("Ver el perfil de un &usuario…\tCtrl+U"), _("Muestra el perfil de una persona u organización."), self.ver_usuario, "usuario")
		self._item(ir, _("Mi &perfil"), _("Muestra su propio perfil."), lambda: abrir.usuario(self.ctx, self, self.ctx.usuario) if self.ctx.usuario else self.iniciar_sesion())
		self._item(ir, _("&Notificaciones en el navegador"), _("Abre la página de notificaciones de GitHub."), lambda: webbrowser.open(f"https://{self.ctx.host}/notifications"))
		barra.Append(ir, _("&Ir"))

		herramientas = wx.Menu()
		self._item(herramientas, _("&Preferencias…\tCtrl+P"), _("Opciones de la aplicación: accesibilidad, sonidos, columnas, notificaciones, git…"), self.preferencias, "preferencias")
		self._item(herramientas, _("Claves &SSH y GPG…"), _("Administra las claves de la cuenta y genera una clave SSH."), self.claves)
		self._item(herramientas, _("Configuración de &git…"), _("Nombre, correo, rama por defecto y firma de git en este equipo."), self.configuracion_git)
		self._item(herramientas, _("Pale&ta de órdenes…\tCtrl+Shift+O"), _("Busca cualquier orden escribiendo parte de su nombre."),
			lambda: paleta.abrir(self), "paleta")
		self._item(herramientas, _("Ejecuciones de Actions &vigiladas…"), _("Lo que se vigila en segundo plano: ver y dejar de vigilar."),
			self.ver_vigiladas, "vigiladas")
		self._item(herramientas, _("Des&cargas…\tCtrl+Shift+D"),
			_("Gestor de descargas: progreso, pausar, reanudar, cancelar y errores de todas las descargas."),
			self.abrir_descargas, "descargas")
		self._item(herramientas, _("Traduct&or…	Ctrl+Shift+Y"),
			_("Traduce el texto que escriba o pegue, con el motor y los idiomas que elija."), self.abrir_traductor, "traductor")
		herramientas.AppendSeparator()
		self._item(herramientas, _("&Límite de uso de la API"), _("Cuántas peticiones quedan y cuándo se renuevan."), self.limite_uso)
		self._item(herramientas, _("&Estado de GitHub"), _("Si GitHub tiene incidencias en este momento."), self.estado_github)
		herramientas.AppendSeparator()
		self._item(herramientas, _("&Historial de avisos de voz\tCtrl+Shift+H"), _("Lista de lo último que ha dicho la aplicación."), self.historial_avisos, "historial")
		self._item(herramientas, _("Abrir la carpeta de &registros"), _("Abre data/logs en el Explorador."), lambda: self._abrir_carpeta(paths.ruta_registros()))
		self._item(herramientas, _("Generar un paquete de &diagnóstico…"), _("Crea un ZIP con los registros (sin datos personales) para pedir ayuda."), self.diagnostico)
		self._item(herramientas, _("Abrir la carpeta de datos de la &aplicación"), _("Abre la carpeta data de la aplicación."), lambda: self._abrir_carpeta(paths.ruta_datos()))
		barra.Append(herramientas, _("&Herramientas"))

		ayuda = wx.Menu()
		self._item(ayuda, _("&Manual de uso\tF1"), _("Abre el manual."), self.manual, "manual")
		self._item(ayuda, _("&Lista de teclas\tShift+F1"), _("Todas las teclas de la aplicación."), self.teclas, "teclas")
		self._item(ayuda, _("&Novedades de esta versión"), _("Qué ha cambiado."), self.novedades)
		self.menu_ayuda = ayuda
		self._item(ayuda, _("Buscar &actualizaciones…"), _("Comprueba si hay una versión nueva."), self.buscar_actualizaciones, "actualizaciones")
		self._item(ayuda, _("&Página del proyecto"), _("Abre el repositorio de GitHub Accesible."), lambda: webbrowser.open(URL_PROYECTO))
		ayuda.AppendSeparator()
		self._item(ayuda, _("&Invítame a un café si te gusta mi trabajo"), _("Abre la página de donaciones de PayPal en el navegador."),
			lambda: webbrowser.open(URL_DONACIONES), "cafe")
		elemento = ayuda.Append(wx.ID_ABOUT, _("Acerca &de…"), _("Versión, autor, licencia y datos técnicos."))
		self.Bind(wx.EVT_MENU, lambda _e: self.acerca_de(), elemento)
		self.elementos_menu["acerca"] = elemento
		barra.Append(ayuda, _("A&yuda"))
		self.SetMenuBar(barra)

	def _crear_menu_ver(self) -> wx.Menu:
		"""Menú Ver con las secciones visibles en su orden: las diez primeras con su número (Alt+1 a Alt+0)."""
		from app.ui.repositorio.vistas import etiqueta_con_letra

		ver = wx.Menu()
		# Letra de acceso: el número de la sección (1 a 9 y 0) y, a partir de la undécima, una letra libre.
		letras_extra = {"vigilados": _("Repositorios &vigilados"), "seguidores": _("S&eguidores"), "seguidos": _("&Personas que sigo"),
			"codespaces": _("C&odespaces"), "busqueda": _("&Resultados de la búsqueda")}
		# Las letras de «&Actualizar» y «Cambiar entre secciones y &contenido», en el idioma de la interfaz.
		ocupadas = "".join(t.partition("&")[2][:1].lower() for t in (
			_("&Actualizar\tF5"), _("Cambiar entre secciones y &contenido\tF6")))
		for indice, (clave, definicion) in enumerate(self.definiciones):
			if indice < 10:
				numero = (indice + 1) % 10
				etiqueta = f"&{numero} {definicion.titulo}\tAlt+{numero}"
			else:
				etiqueta = letras_extra.get(clave, "")
				letra = etiqueta.partition("&")[2][:1].lower()
				if not letra or letra in ocupadas:
					etiqueta = etiqueta_con_letra(definicion.titulo, ocupadas)
				ocupadas += etiqueta.partition("&")[2][:1].lower()
			self._item(ver, etiqueta, _("Ir a la sección {s}.").format(s=definicion.titulo),
				lambda c=clave: self.ir_a_seccion(c))
		ver.AppendSeparator()
		self._item(ver, _("&Actualizar\tF5"), _("Vuelve a cargar la sección."), self.actualizar, "actualizar")
		self._item(ver, _("Cambiar entre secciones y &contenido\tF6"), _("Lleva el foco a la otra zona."), self.alternar_zona)
		return ver

	# ── Orden y secciones visibles ────────────────────────────────────────────

	def _secciones_visibles(self) -> list[tuple[str, Any]]:
		todas = dict(self._todas_definiciones)
		claves = orden_secciones.de_configuracion(self.ctx.config, "principal", [c for c, _d in self._todas_definiciones])
		return [(clave, todas[clave]) for clave in claves]

	def aplicar_secciones(self) -> None:
		"""Rehace la lista de secciones y el menú Ver con el orden elegido en Preferencias (al momento)."""
		if not self:
			return
		actual = self._clave_actual()
		self.definiciones = self._secciones_visibles()
		claves = [c for c, _d in self.definiciones]
		en_secciones = self.secciones.HasFocus()
		self.secciones.Set([d.titulo for _c, d in self.definiciones])
		barra = self.GetMenuBar()
		posicion = barra.FindMenu(_("Ver"))
		if posicion != wx.NOT_FOUND:
			anterior = barra.Replace(posicion, self._crear_menu_ver(), _("&Ver"))
			if anterior is not None:
				anterior.Destroy()
		destino = actual if actual in claves else claves[0]
		self.secciones.SetSelection(claves.index(destino))
		self._mostrar_seccion(claves.index(destino))
		if en_secciones and not self.secciones.HasFocus():
			self.secciones.SetFocus()
		self.marcar_contador_notificaciones(self._sin_leer)

	def _aplicar_icono(self) -> None:
		icono = paths.ruta_iconos() / "app.ico"
		if icono.is_file():
			self.SetIcon(wx.Icon(str(icono), wx.BITMAP_TYPE_ICO))

	# ── Secciones ─────────────────────────────────────────────────────────────

	def _clave_actual(self) -> str:
		indice = self.secciones.GetSelection()
		return self.definiciones[indice][0] if indice >= 0 else self.definiciones[0][0]

	@property
	def panel_actual(self) -> PanelLista | None:
		return self.paneles.get(self._clave_actual())

	def ir_a_seccion(self, clave: str, enfocar: bool = True) -> PanelLista:
		claves = [c for c, _d in self.definiciones]
		if clave not in claves:
			# Oculta en Preferencias: se avisa y se va a la primera, en vez de fallar.
			definicion = dict(self._todas_definiciones).get(clave)
			self.ctx.avisar(_("La sección {s} está oculta. Puede mostrarla en Preferencias, Secciones.").format(
				s=getattr(definicion, "titulo", clave)))
			clave = claves[0]
		indice = claves.index(clave)
		self.secciones.SetSelection(indice)
		panel = self._mostrar_seccion(indice)
		if enfocar:
			self.enfocar_contenido()
		return panel

	def _mostrar_seccion(self, indice: int) -> PanelLista:
		# Moverse por las secciones solo muestra la sección: el foco se queda en la lista
		# de secciones. Al cambiar de página, wx puede pasar el foco a la página nueva;
		# si estaba en las secciones, se devuelve allí (la persona decide cuándo entrar).
		en_secciones = self.secciones.HasFocus()
		clave, definicion = self.definiciones[indice]
		panel = self.paneles.get(clave)
		if panel is None:
			panel = PanelLista(self.libro, self.ctx, definicion)
			self.paneles[clave] = panel
			self.libro.AddPage(panel, definicion.titulo)
		self.libro.ChangeSelection(self.libro.FindPage(panel))
		if clave != "busqueda":
			if not panel.cargado:
				panel.cargar_si_hace_falta()
			elif self._toca_actualizar(clave, panel, al_volver=True):
				panel.actualizar_en_silencio()
		if en_secciones:
			self._mantener_foco_en_secciones()
		return panel

	def _mantener_foco_en_secciones(self) -> None:
		if not self.secciones.HasFocus():
			self.secciones.SetFocus()
		# Por si el cambio de foco llega después (creación de la página, carga asíncrona).
		wx.CallAfter(lambda: self and not self.secciones.HasFocus() and self._foco_seguia_en_contenido() and self.secciones.SetFocus())

	def _foco_seguia_en_contenido(self) -> bool:
		"""Solo se corrige si el foco cayó dentro del libro (no si la persona fue a otra ventana)."""
		foco = wx.Window.FindFocus()
		while foco is not None:
			if foco is self.libro:
				return True
			foco = foco.GetParent()
		return False

	def _al_elegir_seccion(self, evento: wx.CommandEvent) -> None:
		if evento.GetSelection() >= 0:
			self._mostrar_seccion(evento.GetSelection())

	def _al_tecla_secciones(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
			self.enfocar_contenido()
			return
		# Los atajos de la sección también funcionan desde aquí (incidencia #6).
		panel = self.panel_actual
		if panel is not None and panel.atender_desde_secciones(evento):
			return
		evento.Skip()

	def enfocar_contenido(self) -> None:
		panel = self.panel_actual
		if panel is None:
			return
		panel.lista.SetFocus()
		if panel.lista.numero_filas() and panel.lista.fila_actual() == wx.NOT_FOUND:
			panel.lista.enfocar_fila(0, anunciar=False)

	def alternar_zona(self) -> None:
		if self.secciones.HasFocus():
			self.enfocar_contenido()
		else:
			self.secciones.SetFocus()

	def actualizar(self) -> None:
		panel = self.panel_actual
		if panel is not None:
			panel.cargar()

	def _al_abrir_menu(self, evento: wx.MenuEvent) -> None:
		if evento.GetMenu() is self.menu_acciones:
			self._rehacer_menu_acciones()
		evento.Skip()

	def _rehacer_menu_acciones(self) -> None:
		for identificador in self._ids_acciones:
			self.Unbind(wx.EVT_MENU, id=identificador)
		for elemento in list(self.menu_acciones.GetMenuItems()):
			self.menu_acciones.Delete(elemento)
		self._ids_acciones = []
		panel = self.panel_actual
		if panel is None:
			return
		primero = True
		for accion in panel.acciones_disponibles():
			if accion.separador_antes and not primero:
				self.menu_acciones.AppendSeparator()
			# Atajo entre paréntesis (no con tabulador): lo atiende la lista, no la ventana.
			etiqueta = accion.etiqueta + (f" ({atajo_visible(accion.atajo)})" if accion.atajo else "")
			elemento = self.menu_acciones.Append(wx.ID_ANY, etiqueta, accion.ayuda)
			self.Bind(wx.EVT_MENU, lambda _e, a=accion, p=panel: wx.CallAfter(p.ejecutar, a), elemento)
			self._ids_acciones.append(elemento.GetId())
			primero = False
		if primero:
			self.menu_acciones.Append(wx.ID_ANY, _("(sin acciones)")).Enable(False)

	def _al_tecla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_F6 and not evento.HasAnyModifiers():
			self.alternar_zona()
			return
		if evento.GetKeyCode() == ord("H") and evento.GetModifiers() == wx.MOD_CONTROL:
			from app.ui.accesibilidad.ayuda import describir_control_enfocado

			describir_control_enfocado(self)
			return
		evento.Skip()

	# ── Cuentas ───────────────────────────────────────────────────────────────

	def _actualizar_titulo(self) -> None:
		cuenta = self.ctx.cuenta
		if cuenta:
			self.SetTitle(f"{NOMBRE_APLICACION} — {cuenta.descripcion()}")
		else:
			self.SetTitle(_("{n} — sin sesión iniciada").format(n=NOMBRE_APLICACION))
		self._actualizar_estado()

	def _actualizar_estado(self) -> None:
		if not self:
			return
		cuenta = self.ctx.cuenta
		self.SetStatusText(_("Cuenta: {c}").format(c=cuenta.descripcion()) if cuenta else _("Sin sesión iniciada"), 0)
		try:
			self.SetStatusText(self.ctx.cuentas.cliente().limite.describir(), 1)
		except Exception:  # noqa: BLE001 - la barra de estado es informativa
			log.debug("No se pudo leer el límite de uso", exc_info=True)

	def _al_cambiar_cuenta(self) -> None:
		if not self:
			return
		self._actualizar_titulo()
		self._notificaciones_vistas.clear()
		self._avisadas = {}
		self._primera_comprobacion = True
		for panel in self.paneles.values():
			if panel.cargado or panel.cargando:
				panel.cargar(anunciar=False)
		self.programar_notificaciones()

	def iniciar_sesion(self) -> None:
		from app.ui.sesion import iniciar_sesion

		iniciar_sesion(self, self.ctx)

	def gestionar_cuentas(self) -> None:
		from app.ui.sesion import gestionar_cuentas

		gestionar_cuentas(self, self.ctx)

	def cambiar_cuenta(self) -> None:
		cuentas = self.ctx.cuentas.cuentas()
		if len(cuentas) < 2:
			if confirmar(self, _("Solo hay una cuenta guardada. ¿Iniciar sesión con otra?"), _("Cambiar de cuenta")) == wx.ID_YES:
				self.iniciar_sesion()
			return
		activa = self.ctx.cuenta
		actual = next((i for i, c in enumerate(cuentas) if activa and c.clave == activa.clave), 0)
		eleccion = elegir_uno(self, _("Cambiar de cuenta"), _("&Cuenta:"), [c.descripcion() for c in cuentas], actual)
		if eleccion is not None:
			self.ctx.cuentas.activar(cuentas[eleccion])
			self.ctx.avisar(_("Cuenta activa: {c}.").format(c=cuentas[eleccion].descripcion()))

	def pedir_sesion_si_falta(self) -> None:
		if not self.ctx.config.obtener("general.preguntar_sesion", True):
			return
		if self.ctx.cuenta is None and confirmar(self, _(
			"Bienvenido a {n}. Todavía no ha iniciado sesión en GitHub. ¿Quiere hacerlo ahora? "
			"Sin sesión solo podrá buscar y ver repositorios públicos."
		).format(n=NOMBRE_APLICACION), _("Iniciar sesión")) == wx.ID_YES:
			self.iniciar_sesion()

	# ── Órdenes de los menús ──────────────────────────────────────────────────

	def abrir_por_nombre(self) -> None:
		texto = pedir_texto(self, _("&Repositorio («dueño/nombre») o enlace de GitHub:"), _("Abrir un repositorio"))
		if texto and texto.strip() and not abrir.url_github(self.ctx, self, texto.strip()):
			mostrar_error(self, _("No se reconoce «{t}». Escriba, por ejemplo, «octocat/Hello-World».").format(t=texto), _("Abrir un repositorio"))

	def nuevo_repositorio(self) -> None:
		from app.ui.repositorio.dialogos import dialogo_crear_repositorio

		def creado(repo: dict) -> None:
			panel = self.paneles.get("repositorios")
			if panel is not None:
				panel.cargar(anunciar=False)

		dialogo_crear_repositorio(self, self.ctx, al_crear=creado)

	def clonar(self) -> None:
		from app.ui.git.clonar import dialogo_clonar

		dialogo_clonar(self, self.ctx, "", "", al_clonar=lambda carpeta: self._recargar("locales"))

	def abrir_local(self) -> None:
		dialogo = wx.DirDialog(self, _("Elija la carpeta del repositorio"), style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
		try:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			carpeta = dialogo.GetPath()
		finally:
			dialogo.Destroy()
		from app.services import git_local

		if not git_local.git_disponible():
			mostrar_error(self, _("Git no está instalado. Instálelo desde https://git-scm.com o indique su ruta en Preferencias, Git."), _("Git no encontrado"))
			return
		if not git_local.RepositorioLocal.es_repositorio(carpeta):
			if confirmar(self, _("La carpeta no es un repositorio de git. ¿Crear uno (git init)?"), _("Repositorio local")) != wx.ID_YES:
				return
			git_local.iniciar(carpeta)
		principales.anadir_repo_local(self.ctx, carpeta)
		self._recargar("locales")
		abrir.repositorio_local(self.ctx, carpeta)

	def nuevo_gist(self) -> None:
		from app.ui.detalle.gist import nuevo_gist

		nuevo_gist(self, self.ctx, al_crear=lambda g: self._recargar("gists"))

	def _recargar(self, clave: str) -> None:
		panel = self.paneles.get(clave)
		if panel is not None:
			panel.cargar(anunciar=False)

	def buscar(self) -> None:
		from app.ui.busqueda import dialogo_busqueda

		datos = dialogo_busqueda(self, self.ctx)
		if not datos:
			return
		panel = self.ir_a_seccion("busqueda")
		panel.datos.update(datos)
		from app.ui.vistas.base import etiqueta_lista

		panel.etiqueta.SetLabel(etiqueta_lista(_("resultados de «{q}»").format(q=datos["consulta"]), datos["nombre_tipo"]))
		panel.cargar()

	def ver_usuario(self) -> None:
		# Se propone la persona de la fila elegida (dueño del repositorio, autor, quien hizo la actividad):
		# así no hay que escribir el nombre; se cambia escribiendo encima.
		from app.ui.vistas.principales import persona_del_elemento

		panel = self.panel_actual
		propuesta = ""
		if panel is not None:
			try:
				propuesta = persona_del_elemento(panel.elemento, panel.datos)
			except Exception:  # noqa: BLE001 - sin propuesta, el campo sale vacío
				log.debug("No se pudo proponer un perfil", exc_info=True)
		texto = pedir_texto(self, _("&Nombre de usuario u organización:"), _("Ver un perfil"), propuesta)
		if texto and texto.strip():
			abrir.usuario(self.ctx, self, texto.strip().lstrip("@"))

	def preferencias(self) -> None:
		from app.ui.preferencias import mostrar_preferencias
		from app.ui.vistas import principales as p

		vistas = [d for _c, d in self._todas_definiciones]
		try:
			from app.ui.repositorio import vistas as vistas_repo

			ids = {x.id for x in vistas}
			for fabrica in vistas_repo.VISTAS.values():
				vista = fabrica("dueño/repositorio", self.ctx.host)
				if vista.id not in ids:
					vista.titulo = _("Repositorio: {t}").format(t=vista.titulo)
					vistas.append(vista)
					ids.add(vista.id)
		except Exception:  # noqa: BLE001 - las vistas de repositorio son opcionales aquí
			log.debug("No se pudieron cargar las vistas del repositorio para Preferencias", exc_info=True)
		del p
		mostrar_preferencias(self, self.ctx, vistas)

	def claves(self) -> None:
		from app.ui.herramientas.claves import abrir_claves

		abrir_claves(self.ctx, self)

	def configuracion_git(self) -> None:
		from app.ui.herramientas.config_git import abrir_configuracion_git

		abrir_configuracion_git(self.ctx, self)

	def limite_uso(self) -> None:
		def obtener() -> str:
			datos = self.ctx.api().limite_uso()
			lineas = []
			for nombre, valor in (datos.get("resources") or {}).items():
				from datetime import datetime

				hora = datetime.fromtimestamp(valor.get("reset", 0)).strftime("%H:%M")
				lineas.append(_("{n}: quedan {r} de {l}; se renueva a las {h}.").format(n=nombre, r=valor.get("remaining"), l=valor.get("limit"), h=hora))
			return "\n".join(lineas)

		from app.ui.dialogo_texto import mostrar_texto

		en_segundo_plano(self, self.ctx, obtener, sonido="", al_terminar=lambda t: mostrar_texto(self, _("Límite de uso de la API"), _("&Límites:"), t, copiable=True))

	def estado_github(self) -> None:
		def obtener() -> str:
			datos = self.ctx.api().estado_github()
			lineas = [_("Estado general: {e}").format(e=(datos.get("status") or {}).get("description", ""))]
			for componente in datos.get("components") or []:
				lineas.append(f"{componente.get('name')}: {componente.get('status')}")
			for incidencia in datos.get("incidents") or []:
				lineas.append(_("Incidencia: {n} ({e})").format(n=incidencia.get("name"), e=incidencia.get("status")))
			return "\n".join(lineas)

		from app.ui.dialogo_texto import mostrar_texto

		en_segundo_plano(self, self.ctx, obtener, sonido="", al_terminar=lambda t: mostrar_texto(self, _("Estado de GitHub"), _("&Estado:"), t, copiable=True))

	def historial_avisos(self) -> None:
		from datetime import datetime

		from app.ui.accesibilidad import voz as voz_ui
		from app.ui.dialogo_texto import mostrar_texto

		lineas = [f"{datetime.fromtimestamp(m).strftime('%H:%M:%S')} {t}" for m, t in reversed(voz_ui.historial())]
		mostrar_texto(self, _("Historial de avisos"), _("&Avisos (el más reciente primero):"), "\n".join(lineas) or _("Todavía no hay avisos."))

	def diagnostico(self) -> None:
		from app.core import diagnostico

		def hecho(ruta: Path) -> None:
			mostrar_mensaje(self, _("Paquete de diagnóstico creado en:\n{r}\n\nNo contiene tokens ni su nombre de usuario de Windows.").format(r=ruta), _("Diagnóstico"))
			self._abrir_carpeta(ruta.parent)

		en_segundo_plano(self, self.ctx, lambda: diagnostico.generar_paquete(NOMBRE_APLICACION, APP_VERSION), al_terminar=hecho)

	def _abrir_carpeta(self, carpeta: Path) -> None:
		try:
			os.startfile(str(carpeta))  # noqa: S606 - carpeta propia de la aplicación
		except OSError as error:
			mostrar_error(self, str(error), _("No se pudo abrir la carpeta"))

	def manual(self) -> None:
		from app.ui import visor_ayuda

		visor_ayuda.abrir_manual(self)

	def teclas(self) -> None:
		from app.ui import visor_ayuda

		visor_ayuda.abrir_teclas(self)

	def novedades(self) -> None:
		from app.ui import visor_ayuda

		visor_ayuda.abrir_novedades(self)

	def acerca_de(self) -> None:
		from app.ui.acerca_de import mostrar_acerca_de

		mostrar_acerca_de(self)

	# ── Actualizaciones ───────────────────────────────────────────────────────

	def preparar_actualizaciones(self) -> None:
		"""Configura el actualizador y la comprobación periódica (tras mostrar la ventana)."""
		from app.services import actualizador
		from app.ui import dialogo_actualizacion

		self.config_actualizador = actualizador.configuracion_por_defecto(APP_VERSION)
		self._aplicar_origen_actualizaciones()
		dialogo_actualizacion.al_arrancar(self, self.config_actualizador, anunciar=self.ctx.avisar)
		if self.ctx.config.obtener("general.buscar_actualizaciones", True):
			self.comprobador_actualizaciones = dialogo_actualizacion.ComprobadorPeriodico(
				self, self.config_actualizador, intervalo_horas=24, anunciar=self.ctx.avisar)
			self.comprobador_actualizaciones.iniciar()

	def _aplicar_origen_actualizaciones(self) -> None:
		from app.services import actualizador

		if self.config_actualizador is None:
			return
		self.config_actualizador.extra["urls"] = actualizador.urls_de_origen(
			self.ctx.config.obtener("actualizaciones.origen", "ambos"),
			self.ctx.config.obtener("actualizaciones.url_personalizada", ""),
		)

	def buscar_actualizaciones(self) -> None:
		from app.services import actualizador
		from app.ui import dialogo_actualizacion

		if self.config_actualizador is None:
			self.config_actualizador = actualizador.configuracion_por_defecto(APP_VERSION)
		self._aplicar_origen_actualizaciones()
		dialogo_actualizacion.comprobar_manualmente(self, self.config_actualizador, anunciar=self.ctx.avisar)

	# ── Notificaciones en segundo plano ───────────────────────────────────────

	def programar_notificaciones(self) -> None:
		self._temporizador_notificaciones.Stop()
		if not self.ctx.config.obtener("notificaciones.comprobar", True) or self.ctx.cuenta is None:
			return
		cliente = self.ctx.cuentas.cliente()
		intervalo = max(int(self.ctx.config.obtener("notificaciones.intervalo_s", 60)), int(cliente.intervalo_sondeo_notificaciones or 60))
		self._temporizador_notificaciones.Start(intervalo * 1000)
		wx.CallLater(3000, self.comprobar_notificaciones)

	def _al_cambiar_config(self, clave: str, _anterior: Any, _nuevo: Any) -> None:
		if clave.startswith("notificaciones."):
			wx.CallAfter(self.programar_notificaciones)
		elif clave.startswith("actualizaciones."):
			wx.CallAfter(self._aplicar_origen_actualizaciones)
		elif clave.startswith("teclas_globales."):
			wx.CallAfter(self._reprogramar_teclas)
		elif clave.startswith("secciones.principal"):
			wx.CallAfter(self.aplicar_secciones)
		elif clave == "general.icono_bandeja_siempre":
			wx.CallAfter(self._actualizar_bandeja)
		elif clave == "acciones.intervalo_vigilancia_s":
			wx.CallAfter(self.programar_vigilancia)
		elif clave.startswith("listas.actualizar"):
			wx.CallAfter(self.programar_actualizacion_listas)

	def _reprogramar_teclas(self) -> None:
		# Varias claves cambian a la vez al Aplicar: se registra una sola vez, al final.
		if self and not getattr(self, "_teclas_pendientes", False):
			self._teclas_pendientes = True

			def hacer() -> None:
				self._teclas_pendientes = False
				if self:
					self.teclas_globales.registrar()

			wx.CallLater(200, hacer)

	def comprobar_notificaciones(self, informar: bool = False) -> None:
		"""Pregunta a GitHub por las notificaciones. ``informar``: decir el resultado aunque no haya nuevas."""
		if not self or self.ctx.cuenta is None:
			if informar:
				self.ctx.avisar(_("No hay ninguna sesión iniciada."))
			return
		participando = self.ctx.config.obtener("notificaciones.solo_participando", False)
		api = self.ctx.api()

		def obtener() -> list:
			return api.notificaciones(participando=participando).elementos

		def recibidas(lista: list) -> None:
			if not self:
				return
			cuenta = self.ctx.cuenta.clave if self.ctx.cuenta else ""
			if self._primera_comprobacion and self.ctx.almacen is not None:
				try:
					self._avisadas = self.ctx.almacen.avisadas(cuenta)
				except Exception:  # noqa: BLE001
					log.warning("No se pudieron leer las notificaciones avisadas", exc_info=True)
					self._avisadas = {}
			avisadas = getattr(self, "_avisadas", {})
			# Nueva = sin leer y nunca avisada, o avisada pero con actividad posterior.
			nuevas = [n for n in lista if n.get("unread") and avisadas.get(n.get("id")) != n.get("updated_at")
				and n.get("id") not in self._notificaciones_vistas]
			self._notificaciones_vistas.update(n.get("id") for n in lista)
			for n in lista:
				avisadas[n.get("id")] = n.get("updated_at")
			self._avisadas = avisadas
			if self.ctx.almacen is not None:
				datos = [(n.get("id"), n.get("updated_at") or "") for n in lista]
				self.ctx.tareas.enviar(lambda tarea: self.ctx.almacen.marcar_avisadas(cuenta, datos), nombre="notificaciones:guardar")
			sin_leer = sum(1 for n in lista if n.get("unread"))
			self._ultimas_notificaciones = [n for n in lista if n.get("unread")]
			self.marcar_contador_notificaciones(sin_leer)
			if informar and not nuevas:
				self.ctx.avisar(self.texto_sin_leer(), interrumpir=False)
			if self._primera_comprobacion:
				self._primera_comprobacion = False
				if nuevas:
					self._avisar_nuevas(nuevas)
				elif sin_leer:
					self.ctx.avisar_en_segundo_plano(_("Tiene {n} notificaciones sin leer.").format(n=sin_leer))
				return
			if nuevas:
				self._avisar_nuevas(nuevas)
				panel = self.paneles.get("notificaciones")
				if panel is not None and panel.cargado:
					panel.cargar(anunciar=False)

		def fallo(error: BaseException) -> None:
			log.info("No se pudieron comprobar las notificaciones: %s", error)
			if informar and self:
				self.ctx.avisar(_("No se pudieron comprobar las notificaciones: {m}").format(
					m=getattr(error, "mensaje_usuario", None) or error))

		self.ctx.tareas.enviar(lambda tarea: obtener(), al_terminar=recibidas, al_fallar=fallo, clave_unica="notificaciones:sondeo",
			nombre="notificaciones:sondeo")

	# ── Ejecuciones de Actions vigiladas ──────────────────────────────────────

	@property
	def vigiladas(self) -> list[dict]:
		return [dict(v) for v in self.ctx.config.obtener("acciones.vigiladas", []) or [] if isinstance(v, dict)]

	def _guardar_vigiladas(self, vigiladas: list[dict]) -> None:
		self.ctx.config.establecer("acciones.vigiladas", vigiladas)

	def vigilar(self, elemento: dict, anunciar: bool = True) -> None:
		"""Añade algo que vigilar (ejecución, commit o repositorio) y empieza a comprobar."""
		from app.services import vigilancia_actions as va

		actuales = self.vigiladas
		if any(va.misma(elemento, v) for v in actuales):
			if anunciar:
				self.ctx.avisar(_("Ya se está vigilando: {d}.").format(d=va.describir(elemento)))
			return
		self._guardar_vigiladas([*actuales, elemento])
		if anunciar:
			self.ctx.avisar(_("Vigilando: {d}. Se avisará al terminar.").format(d=va.describir(elemento)))
		self.programar_vigilancia()

	def dejar_de_vigilar(self, elemento: dict) -> None:
		from app.services import vigilancia_actions as va

		self._guardar_vigiladas([v for v in self.vigiladas if not va.misma(elemento, v)])
		self.programar_vigilancia()

	def esta_vigilado(self, elemento: dict) -> bool:
		from app.services import vigilancia_actions as va

		return any(va.misma(elemento, v) for v in self.vigiladas)

	# ── Secciones que se actualizan solas (incidencia #14) ───────────────────

	def _minutos_actualizacion(self) -> int:
		return max(1, int(self.ctx.config.obtener("listas.actualizar_cada_min", 5) or 5))

	def _toca_actualizar(self, clave: str, panel: PanelLista, al_volver: bool = False) -> bool:
		"""Si la sección ``clave`` está entre las elegidas y sus datos ya tienen los minutos configurados."""
		config = self.ctx.config
		if not config.obtener("listas.actualizar_al_volver" if al_volver else "listas.actualizar_sola", True):
			return False
		if clave in SECCIONES_SIN_ACTUALIZACION or clave not in (config.obtener("listas.actualizar_secciones", []) or []):
			return False
		return time.monotonic() - panel.ultima_carga >= self._minutos_actualizacion() * 60

	def _temporizadores(self) -> tuple[wx.Timer, ...]:
		return (self._temporizador_buzon, self._temporizador_notificaciones, self._temporizador_estado,
			self._temporizador_actions, self._temporizador_listas)

	def Destroy(self) -> bool:  # noqa: N802 - nombre de wx
		# Un temporizador que siguiera en marcha tras destruir la ventana avisaría a un objeto que ya
		# no existe (y Windows acaba la aplicación con «corrupción del montón», 0xc0000374). Al cerrar
		# se paran en _al_cerrar; aquí también, para quien destruye la ventana sin cerrarla. Y un
		# CallAfter pendiente no debe volver a arrancar el de las listas mientras se destruye.
		self._destruyendose = True
		for temporizador in self._temporizadores():
			temporizador.Stop()
		return super().Destroy()

	def programar_actualizacion_listas(self) -> None:
		if not self or getattr(self, "_destruyendose", False) or self.IsBeingDeleted():
			return
		self._temporizador_listas.Stop()
		if self.ctx.config.obtener("listas.actualizar_sola", True):
			self._temporizador_listas.Start(INTERVALO_REVISAR_LISTAS_MS)

	def actualizar_seccion_sola(self) -> bool:
		"""Pone al día la sección a la vista si ya toca. Devuelve si se ha pedido.

		Solo la que se ve y solo con la ventana a la vista: oculta en la bandeja o minimizada no
		gasta peticiones a GitHub. Lo que no ha cambiado llega como 304 (ETag) y GitHub no lo
		descuenta del límite; si algo cambió, la lista se rehace sin mover el foco.
		"""
		if not self or not self.IsShown() or self.IsIconized():
			return False
		clave = self._clave_actual()
		panel = self.paneles.get(clave)
		if panel is None or not self._toca_actualizar(clave, panel):
			return False
		return panel.actualizar_en_silencio()

	def programar_vigilancia(self) -> None:
		if not self:
			return
		self._temporizador_actions.Stop()
		if self.vigiladas and self.ctx.cuenta is not None:
			intervalo = max(15, int(self.ctx.config.obtener("acciones.intervalo_vigilancia_s", 30)))
			self._temporizador_actions.Start(intervalo * 1000)

	def comprobar_vigiladas(self) -> None:
		"""Pregunta por lo vigilado en un hilo y dice lo que haya terminado."""
		from app.services import vigilancia_actions as va

		if not self or self._vigilando or self.ctx.cuenta is None:
			return
		vigiladas = self.vigiladas
		if not vigiladas:
			self._temporizador_actions.Stop()
			return
		self._vigilando = True
		api = self.ctx.api()

		def recibidos(resultado: tuple[list, list[dict]]) -> None:
			self._vigilando = False
			if not self:
				return
			avisos, siguen = resultado
			# Lo que la persona quitó o añadió mientras se comprobaba se respeta: siguen las comprobadas
			# que aún estén en la lista (con su estado al día) y las añadidas entretanto.
			actuales = self.vigiladas
			restantes = [s for s in siguen if any(va.misma(s, a) for a in actuales)]
			restantes += [a for a in actuales if not any(va.misma(a, v) for v in vigiladas)]
			if restantes != actuales:
				self._guardar_vigiladas(restantes)
			for aviso in avisos:
				self._avisar_ejecucion(aviso)
			if not restantes:
				self._temporizador_actions.Stop()

		def fallo(error: BaseException) -> None:
			self._vigilando = False
			log.info("No se pudo comprobar la vigilancia de Actions: %s", error)

		self.ctx.tareas.enviar(lambda tarea: va.comprobar(api, vigiladas), al_terminar=recibidos, al_fallar=fallo,
			clave_unica="actions:vigilancia", nombre="actions:vigilancia")

	def _avisar_ejecucion(self, aviso: Any) -> None:
		"""Avisa de una ejecución vigilada que ha terminado, como diga Preferencias, Actions (incidencia #8)."""
		from app.services import vigilancia_actions as va

		config = self.ctx.config
		if not va.hay_que_avisar(aviso, str(config.obtener("acciones.avisar_resultados", "todas"))):
			log.info("Ejecución terminada sin aviso por las preferencias: %s", aviso.texto)
			return
		if config.obtener("acciones.sonido_al_terminar", True):
			self.ctx.sonar("accion_exito" if aviso.correcta else "accion_fallo")
		if config.obtener("acciones.voz_al_terminar", True):
			self.ctx.avisar_en_segundo_plano(aviso.texto)
		if config.obtener("acciones.notificacion_windows", True):
			try:
				import wx.adv

				nota = wx.adv.NotificationMessage(NOMBRE_APLICACION, aviso.texto, self)
				nota.Show(timeout=wx.adv.NotificationMessage.Timeout_Auto)
			except Exception:  # noqa: BLE001 - el aviso del sistema es opcional
				log.debug("No se pudo mostrar la notificación de Windows", exc_info=True)

	def ver_vigiladas(self) -> None:
		"""Lista de lo vigilado: elegir uno lo deja de vigilar (pregunta antes)."""
		from app.services import vigilancia_actions as va

		vigiladas = self.vigiladas
		if not vigiladas:
			mostrar_mensaje(self, _("No se está vigilando ninguna ejecución. Para vigilar una, use «Avisarme cuando termine» en la "
				"sección Actions de un repositorio, o «Avisar al terminar cada ejecución de Actions» en su menú Repositorio."),
				_("Ejecuciones vigiladas"))
			return
		eleccion = elegir_uno(self, _("Ejecuciones vigiladas"), _("&Vigiladas (Intro deja de vigilar la elegida):"),
			[va.describir(v) for v in vigiladas])
		if eleccion is None:
			return
		elegido = vigiladas[eleccion]
		if confirmar(self, _("¿Dejar de vigilar: {d}?").format(d=va.describir(elegido)), _("Ejecuciones vigiladas")) == wx.ID_YES:
			self.dejar_de_vigilar(elegido)
			self.ctx.avisar(_("Ya no se vigila: {d}.").format(d=va.describir(elegido)))

	def marcar_contador_notificaciones(self, sin_leer: int) -> None:
		"""Pone «Notificaciones (n)» en la lista de secciones, o solo el nombre si no hay."""
		if not self:
			return
		self._sin_leer = sin_leer
		self._actualizar_bandeja()
		claves = [c for c, _d in self.definiciones]
		if "notificaciones" not in claves:
			return  # sección oculta en Preferencias
		indice = claves.index("notificaciones")
		titulo = dict(self.definiciones)["notificaciones"].titulo
		texto = f"{titulo} ({sin_leer})" if sin_leer else titulo
		if self.secciones.GetString(indice) != texto:
			self.secciones.SetString(indice, texto)

	def texto_sin_leer(self, detalle: int = 3) -> str:
		"""«3 notificaciones sin leer. nvaccess/nvda: título; …» con las ``detalle`` más recientes."""
		if not self._sin_leer:
			return _("No hay notificaciones sin leer.")
		cabecera = _("1 notificación sin leer.") if self._sin_leer == 1 else _("{n} notificaciones sin leer.").format(n=self._sin_leer)
		partes = [_("{r}: {t}").format(r=(n.get("repository") or {}).get("full_name", ""), t=(n.get("subject") or {}).get("title", ""))
			for n in self._ultimas_notificaciones[:detalle]]
		return " ".join([cabecera, "; ".join(partes)]).strip()

	# ── Órdenes de las teclas globales ────────────────────────────────────────

	def mostrar_u_ocultar(self) -> None:
		"""A la vista y en primer plano: se oculta en la bandeja. Si no: se muestra y se trae al frente."""
		if self.IsShown() and not self.IsIconized() and self.IsActive():
			if not self.ocultar_en_bandeja():
				self.Iconize(True)
			return
		self.restaurar()

	def decir_notificaciones(self) -> None:
		if self.ctx.cuenta is None:
			self.ctx.avisar(_("No hay ninguna sesión iniciada."))
			return
		self.ctx.avisar(self.texto_sin_leer())

	def abrir_notificaciones_desde_fuera(self) -> None:
		self.restaurar()
		wx.CallAfter(lambda: self and self.ir_a_seccion("notificaciones"))

	def buscar_desde_fuera(self) -> None:
		self.restaurar()
		wx.CallAfter(lambda: self and self.buscar())

	def _avisar_nuevas(self, nuevas: list) -> None:
		importante = any(n.get("reason") in ("mention", "team_mention", "review_requested", "assign") for n in nuevas)
		if self.ctx.config.obtener("notificaciones.sonido", True):
			self.ctx.sonar("mencion" if importante else "notificacion")
		if len(nuevas) == 1:
			sujeto = nuevas[0].get("subject") or {}
			texto = _("Notificación nueva de {r}: {t}").format(r=(nuevas[0].get("repository") or {}).get("full_name", ""), t=sujeto.get("title", ""))
		else:
			texto = _("{n} notificaciones nuevas. La última: {t}").format(n=len(nuevas), t=(nuevas[0].get("subject") or {}).get("title", ""))
		if self.ctx.config.obtener("notificaciones.voz", True):
			self.ctx.avisar_en_segundo_plano(texto)
		if self.ctx.config.obtener("notificaciones.notificacion_windows", False):
			try:
				import wx.adv

				aviso = wx.adv.NotificationMessage(NOMBRE_APLICACION, texto, self)
				aviso.Show(timeout=wx.adv.NotificationMessage.Timeout_Auto)
			except Exception:  # noqa: BLE001 - el aviso del sistema es opcional
				log.debug("No se pudo mostrar la notificación de Windows", exc_info=True)

	# ── Mostrar, bandeja, geometría y cierre ──────────────────────────────────

	def mostrar(self) -> None:
		self.Show()
		self.Raise()
		wx.CallAfter(self.secciones.SetFocus)

	def texto_bandeja(self) -> str:
		"""Lo que lee el lector al llegar al icono: el nombre y las notificaciones sin leer."""
		if self._sin_leer:
			return _("{a}: {n} notificaciones sin leer").format(a=NOMBRE_APLICACION, n=self._sin_leer)
		return NOMBRE_APLICACION

	def abrir_traductor(self) -> None:
		"""Ventana «Traductor» vacía, para traducir cualquier texto (incidencia #13)."""
		from app.ui.traductor import abrir_traductor

		abrir_traductor(self.ctx, self)

	def abrir_descargas(self) -> None:
		"""Ventana «Descargas» (el gestor). Desde la bandeja o una tecla global también."""
		from app.ui.descargas import abrir_gestor

		abrir_gestor(self.ctx)

	def ordenes_bandeja(self) -> list[OrdenBandeja]:
		"""Órdenes del menú del icono (se piden cada vez que se abre: así dicen lo de ahora)."""
		notificaciones = _("&Notificaciones ({n} sin leer)").format(n=self._sin_leer) if self._sin_leer else _("&Notificaciones")
		ordenes: list[OrdenBandeja] = []
		if self.IsShown():
			ordenes.append((_("&Ocultar en la bandeja"), self.ocultar_en_bandeja))
		ordenes += [
			(notificaciones, self.abrir_notificaciones_desde_fuera),
			(_("&Decir las notificaciones sin leer"), self.decir_notificaciones),
			(_("&Comprobar notificaciones ahora"), lambda: self.comprobar_notificaciones(informar=True)),
			None,
			(_("&Buscar en GitHub…"), self.buscar_desde_fuera),
			(_("D&escargas…"), self.abrir_descargas),
			(_("&Preferencias…"), lambda: (self.restaurar(), wx.CallAfter(self.preferencias))),
		]
		return ordenes

	def _crear_bandeja(self) -> IconoBandeja:
		if self._bandeja is None:
			self._bandeja = IconoBandeja(self.texto_bandeja(), self.restaurar, self.salir, self.ordenes_bandeja)
		return self._bandeja

	def _actualizar_bandeja(self) -> None:
		"""Pone o quita el icono permanente y le pone el texto con el contador."""
		if not self:
			return
		siempre = bool(self.ctx.config.obtener("general.icono_bandeja_siempre", False))
		if siempre and self._bandeja is None:
			if not self._crear_bandeja().mostrar():
				log.warning("No se pudo poner el icono permanente en la bandeja.")
				self._quitar_bandeja()
				return
		elif not siempre and self._bandeja is not None and self.IsShown():
			self._quitar_bandeja()
			return
		if self._bandeja is not None:
			self._bandeja.cambiar_texto(self.texto_bandeja())

	def ocultar_en_bandeja(self) -> bool:
		bandeja = self._crear_bandeja()
		bandeja.cambiar_texto(self.texto_bandeja())
		if not bandeja.IsIconInstalled() and not bandeja.mostrar():
			log.warning("No se pudo poner el icono en la bandeja; la ventana no se oculta.")
			self._quitar_bandeja()
			return False
		self.Hide()
		self.ctx.avisar(_("{nombre} sigue en la bandeja del sistema.").format(nombre=NOMBRE_APLICACION))
		return True

	def _quitar_bandeja(self) -> None:
		if self._bandeja is not None:
			self._bandeja.quitar()
			self._bandeja = None

	def restaurar(self) -> None:
		if not self:
			return
		self.Show()
		if self.IsIconized():
			self.Iconize(False)
		self.Raise()
		if not self.ctx.config.obtener("general.icono_bandeja_siempre", False):
			wx.CallAfter(self._quitar_bandeja)
		dialogo = next((v for v in wx.GetTopLevelWindows() if isinstance(v, wx.Dialog) and v.IsShown() and v.IsEnabled()), None)
		if dialogo is not None:
			dialogo.Raise()
			dialogo.SetFocus()
		else:
			wx.CallAfter(self.secciones.SetFocus)
		if not traer_al_frente(self.GetHandle()):
			self.RequestUserAttention()

	def salir(self) -> None:
		self._forzar_salida = True
		self.Close()

	def _restaurar_geometria(self) -> None:
		config = self.ctx.config
		ancho, alto = int(config.obtener("ventana.ancho", 1000)), int(config.obtener("ventana.alto", 700))
		if ancho < TAMANO_MINIMO[0] or alto < TAMANO_MINIMO[1]:
			ancho, alto = 1000, 700
		self.SetSize(wx.Size(ancho, alto))
		x, y = int(config.obtener("ventana.x", -1)), int(config.obtener("ventana.y", -1))
		if x >= -50 and y >= -50 and wx.Display.GetFromPoint(wx.Point(x + 60, y + 15)) != wx.NOT_FOUND:
			self.SetPosition(wx.Point(x, y))
		else:
			self.Centre()
		if config.obtener("ventana.maximizada", False):
			self.Maximize(True)

	def _al_cambiar_geometria(self, evento: wx.Event) -> None:
		if self.IsShown() and not self.IsMaximized() and not self.IsIconized():
			self._rect_normal = self.GetRect()
		evento.Skip()

	def _guardar_geometria(self) -> None:
		rect = self._rect_normal or self.GetRect()
		self.ctx.config.establecer_varias({
			"ventana.x": rect.x, "ventana.y": rect.y, "ventana.ancho": rect.width, "ventana.alto": rect.height,
			"ventana.maximizada": bool(self.IsMaximized()),
		})

	def _al_minimizar(self, evento: wx.IconizeEvent) -> None:
		if evento.IsIconized() and self.ctx.config.obtener("general.minimizar_a_bandeja", False):
			wx.CallAfter(self.ocultar_en_bandeja)
		evento.Skip()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		# «Al cerrar, dejarla en la bandeja»: Alt+F4 y el botón X la ocultan; Salir (Ctrl+Q) pone _forzar_salida.
		if (not self._forzar_salida and evento.CanVeto() and self.ctx.config.obtener("general.cerrar_a_bandeja", False)
			and self.ocultar_en_bandeja()):
			evento.Veto()
			return
		if (not self._forzar_salida and evento.CanVeto() and self.ctx.config.obtener("general.confirmar_salida", False)
			and confirmar(self, _("¿Salir de {n}?").format(n=NOMBRE_APLICACION), _("Salir")) != wx.ID_YES):
			evento.Veto()
			return
		gestor = getattr(self.ctx, "descargas", None)
		if evento.CanVeto() and gestor is not None and gestor.hay_activas():
			activas = sum(1 for d in gestor.descargas() if d.activa)
			reanudar = self.ctx.config.obtener("descargas.reanudar_al_iniciar", True)
			texto = ngettext("Hay {n} descarga en curso o en cola.", "Hay {n} descargas en curso o en cola.", activas).format(n=activas)
			texto += " " + (_("Si sale, se pausan y siguen solas la próxima vez que abra la aplicación. ¿Salir?") if reanudar
				else _("Si sale, quedan en pausa y podrá reanudarlas en «Descargas». ¿Salir?"))
			if confirmar(self, texto, _("Salir")) != wx.ID_YES:
				evento.Veto()
				return
		for temporizador in self._temporizadores():
			temporizador.Stop()
		self.teclas_globales.quitar()
		if self.comprobador_actualizaciones is not None:
			try:
				self.comprobador_actualizaciones.detener()
			except Exception:  # noqa: BLE001
				log.debug("No se pudo detener el comprobador de actualizaciones", exc_info=True)
		self._guardar_geometria()
		try:
			self.ctx.config.guardar_pendiente()
		except Exception:  # noqa: BLE001 - guardar no debe impedir cerrar
			log.exception("No se pudo guardar la configuración al cerrar")
		self._quitar_bandeja()
		for ventana in list(wx.GetTopLevelWindows()):
			if ventana is not self:
				try:
					ventana.Destroy()
				except RuntimeError:
					log.debug("Ventana ya destruida al cerrar", exc_info=True)
		log.info("Ventana principal cerrada.")
		self.Destroy()

	def _al_revisar_buzon(self, _evento: wx.TimerEvent) -> None:
		try:
			ordenes = self._instancia.recoger_ordenes() if self._instancia else []
			for orden in ordenes:
				if orden.orden == ORDEN_ABRIR:
					for argumento in orden.argumentos:
						self.abrir_argumento(argumento)
				if orden.orden in (ORDEN_MOSTRAR, ORDEN_ABRIR):
					self.restaurar()
		except Exception:  # noqa: BLE001 - el temporizador late toda la sesión
			log.exception("Error al atender las órdenes de otra instancia")

	def abrir_argumento(self, argumento: str) -> None:
		"""Abre lo que llega por la línea de órdenes: una carpeta local o un enlace de GitHub."""
		if os.path.isdir(argumento):
			principales.anadir_repo_local(self.ctx, argumento)
			abrir.repositorio_local(self.ctx, argumento)
		elif argumento:
			abrir.url_github(self.ctx, self, argumento)
