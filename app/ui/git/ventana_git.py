"""Ventana de un repositorio git local: cambios, commit, historial, ramas, conflictos y red.

Diseño pensado para lector de pantalla:

- Arriba, «&Estado:» (campo de solo lectura que se puede releer): rama,
  adelante y detrás, cambios y la operación en curso (fusión, reorganización…).
  Lo mismo va a la barra de estado.
- «&Secciones:» (lista) a la izquierda y la sección elegida a la derecha
  (``wx.Simplebook``). F6 alterna entre la lista de secciones y la sección;
  Ctrl+Tab y Ctrl+Mayús+Tab pasan a la sección siguiente o anterior.
- Cada sección es un ``PanelLista`` (lectura por columnas, menú contextual,
  filtro, copiar) con sus acciones y atajos; el menú «&Acciones» de la barra
  muestra las de la sección y el elemento actuales.
- Menú «&Git» con las órdenes de red (traer, tirar, enviar, sincronizar),
  GitHub, carpeta, consola, limpieza, mantenimiento, bisección y configuración.
- Las órdenes de red muestran el progreso en «&Progreso:» (consultable) y lo
  anuncian solo por hitos; «Cance&lar la operación de red» las detiene.
- Todo git va en segundo plano (``en_segundo_plano``) y los controles solo se
  tocan en el hilo de la interfaz. Escape NO cierra la ventana; Ctrl+W sí.
"""

from __future__ import annotations

import builtins
import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx

from app.services import conflictos as c
from app.services import formato as f
from app.services import git_local
from app.services.github.cliente import Pagina
from app.ui.accesibilidad.dialogos import elegir_opcion
from app.ui.accesibilidad.foco import conservar_foco
from app.ui.comunes import (
	confirmar,
	confirmar_peligro,
	copiar,
	elegir_uno,
	en_segundo_plano,
	mensaje_error,
	mostrar_error,
	mostrar_mensaje,
	pedir_texto,
)
from app.ui.git import dialogos as dlg
from app.ui.git import operaciones as op
from app.ui.git.progreso_red import PanelProgresoGit
from app.ui.vistas.base import Accion, Columna, DefinicionVista, PanelLista, atajo_visible

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


POR_PAGINA_HISTORIAL = 100

MENSAJE_SIN_GIT = N_(
	"Git no está instalado o no se encuentra.\n\n"
	"Instale Git for Windows desde https://git-scm.com/download/win (o con «winget install --id Git.Git -e») "
	"y vuelva a abrir la ventana. Si ya lo tiene en otra carpeta, indique la ruta de git.exe en "
	"Herramientas, Configuración de git."
)

#: Ventanas abiertas por carpeta (para traer al frente la que ya existe).
_ABIERTAS: dict[str, VentanaGit] = {}


def _clave(carpeta: str) -> str:
	return os.path.normcase(os.path.abspath(carpeta))


def abrir_ventana_git(ctx: Any, carpeta: str) -> wx.Frame | None:
	"""Abre la ventana git de ``carpeta`` o trae al frente la que ya está abierta."""
	existente = _ABIERTAS.get(_clave(carpeta))
	if existente and not existente.IsBeingDeleted():
		if existente.IsIconized():
			existente.Iconize(False)
		existente.Raise()
		existente.enfocar_contenido()
		ctx.sonar("abrir")
		return existente
	if not git_local.git_disponible():
		mostrar_error(ctx.ventana_principal, _(MENSAJE_SIN_GIT), _("Git no está instalado"))
		return None
	ventana = VentanaGit(ctx, carpeta)
	ventana.Show()
	ctx.sonar("abrir")
	ventana.enfocar_contenido()
	return ventana


def _fecha(valor: str, ctx: Any) -> str:
	if not valor:
		return ""
	try:
		return f.fecha_relativa(valor) if ctx.relativas() else f.fecha_completa(valor)
	except Exception:  # noqa: BLE001 - una fecha rara no rompe la lista
		log.debug("Fecha no reconocida: %s", valor, exc_info=True)
		return valor


class VentanaGit(wx.Frame):
	"""Ventana de un repositorio local.

	:param contexto: ``Contexto`` de la aplicación.
	:param carpeta: carpeta de trabajo del repositorio.
	"""

	def __init__(self, contexto: Any, carpeta: str, padre: wx.Window | None = None) -> None:
		self.carpeta = os.path.normpath(str(carpeta))
		self.nombre = os.path.basename(self.carpeta.rstrip("\\/")) or self.carpeta
		super().__init__(padre, title=_("{n}: Git").format(n=self.nombre), size=(1100, 760))
		self.ctx = contexto
		self.raiz = Path(self.carpeta)
		token = contexto.token if contexto.config.obtener("git.usar_token", True) else None
		self.repo = git_local.RepositorioLocal(self.carpeta, token=token)
		self.estado: git_local.EstadoRepositorio | None = None
		self.operacion = ""
		self._acciones_menu: dict[int, tuple[PanelLista, Accion]] = {}
		_ABIERTAS[_clave(self.carpeta)] = self

		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)
		# Etiquetas SIEMPRE antes de su control (el lector las toma como nombre).
		raiz.Add(wx.StaticText(panel, label=_("&Estado:")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_estado = wx.TextCtrl(panel, value=_("Cargando el estado…"), style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
			size=(-1, self.FromDIP(52)))
		self.campo_estado.SetHelpText(_("Rama, cambios y operación en curso del repositorio. Control+R lo actualiza."))
		raiz.Add(self.campo_estado, 0, wx.EXPAND | wx.ALL, 6)

		cuerpo = wx.BoxSizer(wx.HORIZONTAL)
		columna = wx.BoxSizer(wx.VERTICAL)
		columna.Add(wx.StaticText(panel, label=_("&Secciones:")), 0, wx.BOTTOM, 4)
		self.secciones = wx.ListBox(panel, style=wx.LB_SINGLE, size=(self.FromDIP(190), -1))
		self.secciones.SetHelpText(_(
			"Secciones del repositorio. F6 pasa al contenido de la sección; Control+Tabulador cambia de sección."))
		columna.Add(self.secciones, 1, wx.EXPAND)
		cuerpo.Add(columna, 0, wx.EXPAND | wx.ALL, 6)
		self.libro = wx.Simplebook(panel)
		cuerpo.Add(self.libro, 1, wx.EXPAND | wx.ALL, 6)
		raiz.Add(cuerpo, 1, wx.EXPAND)

		self.progreso = PanelProgresoGit(panel, contexto, _("&Progreso:"), _("Cance&lar la operación de red"))
		raiz.Add(self.progreso, 0, wx.EXPAND | wx.ALL, 2)
		panel.SetSizer(raiz)

		self.paneles: dict[str, PanelLista] = {}
		self.ids_secciones: list[str] = []
		self._titulos: dict[str, str] = {}
		self._crear_secciones()
		self.CreateStatusBar()
		self.SetStatusText(_("Cargando…"))
		self._crear_menus()

		self.secciones.Bind(wx.EVT_LISTBOX, lambda _e: self.mostrar_seccion(self.secciones.GetSelection()))
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.Bind(wx.EVT_MENU_OPEN, self._al_abrir_menu)
		from app.ui import paleta

		paleta.instalar(self)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir)
		self.secciones.SetSelection(0)
		self.mostrar_seccion(0)
		self.refrescar()

	# ════════════════════════════════════════════════════════════════════════
	# Construcción
	# ════════════════════════════════════════════════════════════════════════

	def _crear_secciones(self) -> None:
		self._anadir_seccion("cambios", _("Cambios"), self._pagina_cambios())
		self._anadir_seccion("historial", _("Historial"), self._pagina_historial())
		for clave, titulo, definicion, etiqueta in (
			("ramas", _("Ramas"), self._vista_ramas(), _("&Ramas:")),
			("etiquetas", pgettext("git", "Etiquetas"), self._vista_etiquetas(), _("E&tiquetas:")),
			("stash", _("Stash"), self._vista_stash(), _("&Cambios guardados (stash):")),
			("remotos", _("Remotos"), self._vista_remotos(), _("&Remotos:")),
			("submodulos", _("Submódulos"), self._vista_submodulos(), _("S&ubmódulos:")),
			("worktrees", _("Worktrees"), self._vista_worktrees(), _("&Worktrees:")),
			("reflog", _("Reflog"), self._vista_reflog(), _("Re&flog:")),
		):
			panel = PanelLista(self.libro, self.ctx, definicion, etiqueta=etiqueta)
			self.paneles[clave] = panel
			self._anadir_seccion(clave, titulo, panel)
		self._anadir_seccion("conflictos", _("Conflictos"), self._pagina_conflictos())

	def _anadir_seccion(self, clave: str, titulo: str, pagina: wx.Window) -> None:
		self.libro.AddPage(pagina, titulo)
		self.secciones.Append(titulo)
		self.ids_secciones.append(clave)
		self._titulos[clave] = titulo

	def _pagina_cambios(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		lista = PanelLista(pagina, self.ctx, self._vista_cambios(), etiqueta=_("Lista de &cambios:"))
		self.paneles["cambios"] = lista
		sizer.Add(lista, 1, wx.EXPAND)
		sizer.Add(wx.StaticText(pagina, label=_("&Mensaje del commit:")), 0, wx.LEFT | wx.RIGHT, 4)
		self.campo_mensaje = wx.TextCtrl(pagina, style=wx.TE_MULTILINE | wx.TE_RICH2, size=(-1, self.FromDIP(110)))
		self.campo_mensaje.SetHelpText(_(
			"Mensaje del commit: la primera línea es el resumen; deje una línea en blanco antes de la descripción. "
			"Control+Intro confirma."))
		sizer.Add(self.campo_mensaje, 0, wx.EXPAND | wx.ALL, 4)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.casilla_enmendar = wx.CheckBox(pagina, label=_("E&nmendar el último commit"))
		self.casilla_enmendar.SetHelpText(_("Sustituye el último commit por uno nuevo con lo preparado y este mensaje (--amend)."))
		self.casilla_enmendar.Bind(wx.EVT_CHECKBOX, self._al_marcar_enmendar)
		fila.Add(self.casilla_enmendar, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 12)
		self.casilla_firmar = wx.CheckBox(pagina, label=_("F&irmar el commit"))
		self.casilla_firmar.SetValue(bool(self.ctx.config.obtener("git.firmar_commits", False)))
		self.casilla_firmar.SetHelpText(_("Firma el commit con su clave GPG o SSH (-S)."))
		fila.Add(self.casilla_firmar, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 12)
		self.boton_confirmar = wx.Button(pagina, label=_("C&onfirmar (commit)"))
		self.boton_confirmar.SetHelpText(_("Crea el commit con los cambios preparados y el mensaje escrito (Control+Intro desde el mensaje)."))
		self.boton_confirmar.Bind(wx.EVT_BUTTON, lambda _e: self.confirmar_commit())
		fila.Add(self.boton_confirmar, 0)
		sizer.Add(fila, 0, wx.ALL, 4)
		pagina.SetSizer(sizer)
		return pagina

	def _pagina_historial(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		lista = PanelLista(pagina, self.ctx, self._vista_historial(), {"filtro": {}}, etiqueta=_("&Historial:"))
		self.paneles["historial"] = lista
		sizer.Add(lista, 1, wx.EXPAND)
		self.texto_filtro = wx.StaticText(pagina, label=dlg.describir_filtro({}))
		sizer.Add(self.texto_filtro, 0, wx.ALL, 4)
		pagina.SetSizer(sizer)
		return pagina

	def _pagina_conflictos(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.texto_conflictos = wx.StaticText(pagina, label=_("No hay ninguna operación en curso."))
		sizer.Add(self.texto_conflictos, 0, wx.ALL, 4)
		lista = PanelLista(pagina, self.ctx, self._vista_conflictos(), etiqueta=_("Archivos en &conflicto:"))
		self.paneles["conflictos"] = lista
		sizer.Add(lista, 1, wx.EXPAND)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_continuar = wx.Button(pagina, label=_("C&ontinuar la operación"))
		self.boton_continuar.SetHelpText(_("Termina la fusión o sigue con la reorganización, cherry-pick o reversión una vez resueltos los conflictos."))
		self.boton_continuar.Bind(wx.EVT_BUTTON, lambda _e: self.continuar_operacion())
		self.boton_abortar = wx.Button(pagina, label=_("A&bortar la operación…"))
		self.boton_abortar.SetHelpText(_("Deja el repositorio como estaba antes de empezar la operación."))
		self.boton_abortar.Bind(wx.EVT_BUTTON, lambda _e: self.abortar_operacion())
		self.boton_saltar = wx.Button(pagina, label=_("Saltar es&te commit"))
		self.boton_saltar.SetHelpText(_("En una reorganización, omite el commit que da conflicto y sigue con el siguiente."))
		self.boton_saltar.Bind(wx.EVT_BUTTON, lambda _e: self.saltar_commit())
		for boton in (self.boton_continuar, self.boton_abortar, self.boton_saltar):
			fila.Add(boton, 0, wx.ALL, 3)
		sizer.Add(fila, 0, wx.ALL, 2)
		pagina.SetSizer(sizer)
		return pagina

	def _crear_menus(self) -> None:
		barra = wx.MenuBar()
		menu = wx.Menu()
		self._items: dict[str, wx.MenuItem] = {}

		def anadir(clave: str, etiqueta: str, accion: Callable[[], None], ayuda: str = "") -> None:
			item = menu.Append(wx.ID_ANY, etiqueta, ayuda)
			self._items[clave] = item
			self.Bind(wx.EVT_MENU, lambda _e: accion(), item)

		anadir("traer", _("&Traer (fetch)\tCtrl+Shift+T"), self.traer, _("Trae los cambios de todos los remotos sin tocar sus archivos."))
		anadir("tirar", _("T&irar (pull)\tCtrl+Shift+U"), self.tirar, _("Trae y aplica los cambios de la rama remota."))
		anadir("enviar", _("&Enviar (push)\tCtrl+Shift+P"), lambda: self.enviar(), _("Envía sus commits a la rama remota."))
		anadir("forzar", _("Enviar &forzando (con lease)…"), lambda: self.enviar(forzar=True),
			_("Sobrescribe la rama remota si nadie más la ha cambiado (--force-with-lease)."))
		anadir("sincronizar", _("&Sincronizar (pull y push)\tCtrl+Shift+Y"), self.sincronizar, _("Tira y después envía."))
		menu.AppendSeparator()
		anadir("github", _("Abrir en &GitHub\tCtrl+Shift+G"), self.abrir_en_github, _("Abre el repositorio de GitHub del remoto origin."))
		anadir("pr", _("Crear un &pull request de la rama actual…\tCtrl+Shift+R"), self.crear_pull_request)
		menu.AppendSeparator()
		anadir("carpeta", _("Abrir la &carpeta\tCtrl+Shift+E"), self.abrir_carpeta)
		anadir("consola", _("Abrir una c&onsola aquí\tCtrl+Shift+K"), self.abrir_consola)
		menu.AppendSeparator()
		anadir("continuar", _("Continuar la operación en c&urso"), self.continuar_operacion)
		anadir("abortar", _("A&bortar la operación en curso…"), self.abortar_operacion)
		anadir("saltar", _("Saltar este co&mmit (reorganización)"), self.saltar_commit)
		menu.AppendSeparator()
		anadir("limpiar", _("&Limpiar archivos sin seguimiento…"), self.limpiar)
		anadir("mantenimiento", _("Mante&nimiento (gc)"), self.mantenimiento)
		anadir("bisecar", _("Bisección guia&da…"), self.biseccion_guiada)
		anadir("config", _("Configuración del &repositorio…"), self.configurar_repositorio)
		menu.AppendSeparator()
		anadir("actualizar", _("&Actualizar el estado\tCtrl+R"), self.refrescar)
		anadir("cerrar", _("Cerrar la &ventana\tCtrl+W"), self.Close)
		barra.Append(menu, _("&Git"))
		self.menu_acciones = wx.Menu()
		barra.Append(self.menu_acciones, _("&Acciones"))
		self.SetMenuBar(barra)
		from app.ui.descargas import instalar_tecla

		instalar_tecla(self, self.ctx)
		# Un único manejador para el menú «Acciones», que se rehace al abrirlo.
		self.Bind(wx.EVT_MENU, self._al_menu_accion)
		self._habilitar_operacion()

	# ════════════════════════════════════════════════════════════════════════
	# Secciones, foco y menús
	# ════════════════════════════════════════════════════════════════════════

	@property
	def seccion(self) -> str:
		indice = self.libro.GetSelection()
		return self.ids_secciones[indice] if 0 <= indice < len(self.ids_secciones) else ""

	def panel_actual(self) -> PanelLista | None:
		return self.paneles.get(self.seccion)

	def mostrar_seccion(self, indice: int, enfocar: bool = False) -> None:
		if not (0 <= indice < len(self.ids_secciones)):
			return
		if self.secciones.GetSelection() != indice:
			self.secciones.SetSelection(indice)
		# Moverse por las secciones no cambia el foco: se entra con Tabulador, Intro o F6.
		with conservar_foco(self):
			self.libro.ChangeSelection(indice)
		panel = self.paneles.get(self.ids_secciones[indice])
		if panel is not None:
			panel.cargar_si_hace_falta()
			if enfocar:
				panel.lista.SetFocus()

	def ir_a_seccion(self, clave: str, enfocar: bool = True) -> None:
		if clave in self.ids_secciones:
			self.mostrar_seccion(self.ids_secciones.index(clave), enfocar)

	def cambiar_seccion(self, paso: int) -> None:
		total = len(self.ids_secciones)
		indice = (self.libro.GetSelection() + paso) % total
		# Control+Tabulador desde la lista de secciones se queda en ella, como en las demás ventanas.
		self.mostrar_seccion(indice, enfocar=wx.Window.FindFocus() is not self.secciones)
		self.ctx.anunciar(self.secciones.GetString(indice))

	def enfocar_contenido(self) -> None:
		panel = self.panel_actual()
		(panel.lista if panel is not None else self.secciones).SetFocus()

	def alternar_zona(self) -> None:
		foco = wx.Window.FindFocus()
		if foco is self.secciones:
			self.enfocar_contenido()
		else:
			self.secciones.SetFocus()

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if tecla == wx.WXK_F6 and modificadores == wx.MOD_NONE:
			self.alternar_zona()
			return
		if tecla == wx.WXK_TAB and evento.ControlDown() and not evento.AltDown():
			self.cambiar_seccion(-1 if evento.ShiftDown() else 1)
			return
		if tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and modificadores == wx.MOD_NONE \
			and wx.Window.FindFocus() is self.secciones:
			# Como en la ventana principal: Intro en las secciones entra en el contenido.
			self.enfocar_contenido()
			return
		if tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and modificadores == wx.MOD_CONTROL \
			and wx.Window.FindFocus() is self.campo_mensaje:
			self.confirmar_commit()
			return
		evento.Skip()

	def _al_abrir_menu(self, evento: wx.MenuEvent) -> None:
		if evento.GetMenu() is self.menu_acciones:
			self.rellenar_menu_acciones()
		evento.Skip()

	def rellenar_menu_acciones(self) -> None:
		"""Rehace «Acciones» con las de la sección y el elemento actuales (atajos entre paréntesis)."""
		for item in list(self.menu_acciones.GetMenuItems()):
			self.menu_acciones.Delete(item)
		self._acciones_menu.clear()
		panel = self.panel_actual()
		if panel is None:
			item = self.menu_acciones.Append(wx.ID_ANY, _("(&Sin acciones en esta sección)"))
			item.Enable(False)
			return
		primero = True
		for accion in panel.acciones_disponibles():
			if accion.separador_antes and not primero:
				self.menu_acciones.AppendSeparator()
			etiqueta = accion.etiqueta + (f" ({atajo_visible(accion.atajo)})" if accion.atajo else "")
			item = self.menu_acciones.Append(wx.ID_ANY, etiqueta, accion.ayuda)
			self._acciones_menu[item.GetId()] = (panel, accion)
			primero = False

	def _al_menu_accion(self, evento: wx.CommandEvent) -> None:
		destino = self._acciones_menu.get(evento.GetId())
		if destino is None:
			evento.Skip()
			return
		panel, accion = destino
		wx.CallAfter(panel.ejecutar, accion)

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if self.progreso.en_curso and evento.CanVeto():
			if confirmar(self, _("Hay una operación de red en curso. ¿Cancelarla y cerrar la ventana?"), _("Cerrar")) != wx.ID_YES:
				evento.Veto()
				return
			self.progreso.cancelar()
		self.ctx.sonar("cerrar")
		_ABIERTAS.pop(_clave(self.carpeta), None)
		evento.Skip()

	def Destroy(self) -> bool:  # noqa: N802 - mismo nombre que wx
		"""Al destruirla deja de contar como abierta en el acto (wx la borra más tarde)."""
		if _ABIERTAS.get(_clave(self.carpeta)) is self:
			_ABIERTAS.pop(_clave(self.carpeta), None)
		return super().Destroy()

	def _al_destruir(self, evento: wx.WindowDestroyEvent) -> None:
		if evento.GetEventObject() is self and _ABIERTAS.get(_clave(self.carpeta)) is self:
			_ABIERTAS.pop(_clave(self.carpeta), None)
		evento.Skip()

	# ════════════════════════════════════════════════════════════════════════
	# Estado
	# ════════════════════════════════════════════════════════════════════════

	def _vivo(self, funcion: Callable[..., Any]) -> Callable[..., Any]:
		"""Envuelve una respuesta de segundo plano: no hace nada si la ventana ya se cerró."""

		def envoltura(*args: Any) -> Any:
			if not self or self.IsBeingDeleted():
				return None
			return funcion(*args)

		return envoltura

	def refrescar(self, recargar_listas: bool = True) -> None:
		"""Lee estado, operación en curso y raíz en segundo plano y actualiza todo."""

		def trabajo() -> tuple[git_local.EstadoRepositorio, str, Path]:
			return self.repo.estado(), self.repo.operacion_en_curso(), self.repo.raiz()

		def listo(resultado: tuple[git_local.EstadoRepositorio, str, Path]) -> None:
			self.mostrar_estado(*resultado)
			if recargar_listas:
				self.recargar_listas()

		def fallo(error: BaseException) -> None:
			texto = mensaje_error(error)
			self.campo_estado.SetValue(texto)
			self.SetStatusText(texto.splitlines()[0] if texto else "")
			self.ctx.avisar(texto.splitlines()[0] if texto else _("Error"))

		en_segundo_plano(self, self.ctx, trabajo, al_terminar=self._vivo(listo), al_fallar=self._vivo(fallo), sonido="")

	def texto_estado(self) -> str:
		if self.estado is None:
			return ""
		texto = self.estado.resumen()
		if self.operacion:
			conflictos = len(self.estado.conflictos)
			texto += " " + _("{o} en curso").format(o=self.operacion.capitalize())
			texto += (_(" con {n} archivos en conflicto.").format(n=conflictos) if conflictos else ".")
		if self.estado.stashes:
			texto += " " + _("{n} cambios guardados en stash.").format(n=self.estado.stashes)
		return texto

	def mostrar_estado(self, estado: git_local.EstadoRepositorio, operacion: str, raiz: Path | None = None) -> None:
		self.estado = estado
		self.operacion = operacion
		if raiz is not None:
			self.raiz = Path(raiz)
		texto = self.texto_estado()
		self.campo_estado.SetValue(texto)
		self.SetStatusText(texto)
		self.SetTitle(_("{n} ({r}): Git").format(n=self.nombre, r=estado.rama or _("HEAD separado")))
		cambios = len(estado.archivos)
		conflictos = len(estado.conflictos)
		self._titular("cambios", _("Cambios ({n})").format(n=cambios) if cambios else _("Cambios"))
		self._titular("conflictos", _("Conflictos ({n})").format(n=conflictos) if conflictos else _("Conflictos"))
		if operacion:
			self.texto_conflictos.SetLabel(_("{o} en curso. {e}").format(o=operacion.capitalize(), e=c.explicar_lados(operacion)))
		else:
			self.texto_conflictos.SetLabel(_("No hay ninguna operación en curso."))
		self.texto_conflictos.Wrap(self.FromDIP(800))
		self._habilitar_operacion()

	def _titular(self, clave: str, titulo: str) -> None:
		indice = self.ids_secciones.index(clave)
		if self.secciones.GetString(indice) != titulo:
			self.secciones.SetString(indice, titulo)

	def _habilitar_operacion(self) -> None:
		hay = bool(self.operacion) and self.operacion != _("bisección")
		reorganizando = self.operacion == _("reorganización")
		for clave, activo in (("continuar", hay), ("abortar", bool(self.operacion)), ("saltar", reorganizando)):
			self._items[clave].Enable(activo)
		if hasattr(self, "boton_continuar"):
			self.boton_continuar.Enable(hay)
			self.boton_abortar.Enable(bool(self.operacion))
			self.boton_saltar.Enable(reorganizando)

	def recargar_listas(self) -> None:
		"""Recarga la sección visible y deja las demás para cuando se visiten."""
		actual = self.seccion
		for clave, panel in self.paneles.items():
			if clave == actual:
				panel.cargar(anunciar=False)
			else:
				panel.cargado = False

	def _con_estado(self, despues: Callable[[git_local.EstadoRepositorio, list[str]], None]) -> None:
		"""Lee estado y remotos en segundo plano y sigue en la interfaz."""

		def trabajo() -> tuple[git_local.EstadoRepositorio, list[str]]:
			return self.repo.estado(), sorted({nombre for nombre, _u, _t in self.repo.remotos()})

		en_segundo_plano(self, self.ctx, trabajo, al_terminar=self._vivo(lambda r: despues(*r)), sonido="")

	def ejecutar_git(self, funcion: Callable[[], Any], *, inicio: str = "", exito: str | Callable[[Any], str] = "",
		al_terminar: Callable[[Any], None] | None = None, sonido: str = "completado") -> None:
		"""Orden git local en segundo plano; si deja conflictos, lleva a la sección Conflictos."""

		def listo(resultado: Any) -> None:
			if al_terminar:
				al_terminar(resultado)
			self.refrescar()

		def fallo(error: BaseException) -> None:
			texto = mensaje_error(error)
			self.refrescar()
			# «conflict» vale para el español («conflicto»), el inglés y la salida de git
			# («CONFLICT»), que va al final del mensaje: el aviso puede venir traducido.
			if "conflict" in texto.lower():
				self.ctx.sonar("aviso")
				mostrar_mensaje(self, texto + "\n\n" + _("Resuélvalos en la sección Conflictos."), _("Hay conflictos"),
					wx.ICON_WARNING)
				self.ir_a_seccion("conflictos")
				return
			mostrar_error(self, texto, _("No se pudo completar"))

		en_segundo_plano(self, self.ctx, funcion, inicio=inicio, exito=exito, al_terminar=self._vivo(listo),
			al_fallar=self._vivo(fallo), sonido=sonido)

	# ════════════════════════════════════════════════════════════════════════
	# Red con progreso
	# ════════════════════════════════════════════════════════════════════════

	def operacion_red(self, inicio: str, funcion: Callable[[Callable[[str], None], Callable[[], bool]], Any], exito: str,
		al_terminar: Callable[[Any], None] | None = None) -> None:
		"""Ejecuta ``funcion(al_linea, cancelado)`` en segundo plano con el progreso accesible."""
		if self.progreso.en_curso:
			self.ctx.avisar(_("Ya hay una operación de red en curso. Espere o cancélela."))
			return
		self.progreso.empezar(inicio)

		def trabajo() -> Any:
			return funcion(self.progreso.recibir_linea, self.progreso.cancelado)

		def listo(resultado: Any) -> None:
			self.progreso.terminar(exito)
			self.SetStatusText(exito)
			if al_terminar:
				al_terminar(resultado)
			self.refrescar()

		def fallo(error: BaseException) -> None:
			texto = mensaje_error(error)
			self.progreso.terminar(_("No se pudo completar: {m}").format(m=texto.splitlines()[0] if texto else ""), correcto=False)
			self.refrescar()
			if "conflict" in texto.lower():  # Ver ejecutar_git.
				mostrar_mensaje(self, texto + "\n\n" + _("Resuélvalos en la sección Conflictos."), _("Hay conflictos"), wx.ICON_WARNING)
				self.ir_a_seccion("conflictos")
				return
			if texto != _("Operación cancelada."):
				mostrar_error(self, texto, _("No se pudo completar"))

		en_segundo_plano(self, self.ctx, trabajo, exito=exito, al_terminar=self._vivo(listo), al_fallar=self._vivo(fallo))

	def traer(self) -> None:
		self.operacion_red(_("Trayendo cambios de todos los remotos…"),
			lambda al_linea, cancelado: self.repo.traer(al_linea=al_linea, cancelado=cancelado), _("Cambios traídos."))

	def tirar(self) -> None:
		reorganizar = bool(self.ctx.config.obtener("git.tirar_con_reorganizacion", False))
		inicio = _("Tirando con reorganización…") if reorganizar else _("Tirando (pull)…")
		self.operacion_red(inicio, lambda al_linea, cancelado: self.repo.tirar(
			reorganizar=reorganizar, al_linea=al_linea, cancelado=cancelado), _("Rama actualizada con los cambios remotos."))

	def enviar(self, forzar: bool = False) -> None:
		def seguir(estado: git_local.EstadoRepositorio, remotos: list[str]) -> None:
			if not estado.rama:
				mostrar_error(self, _("No está en ninguna rama (HEAD separado). Cree una rama antes de enviar."), _("Enviar"))
				return
			if not remotos:
				mostrar_error(self, _("El repositorio no tiene remotos. Añada uno en la sección Remotos."), _("Enviar"))
				return
			if forzar and not confirmar_peligro(self, _(
				"Se sobrescribirá la rama remota con su rama «{r}». Los commits remotos que usted no tenga se perderán "
				"(si alguien más ha enviado cambios, git se negará: --force-with-lease). ¿Continuar?"
			).format(r=estado.rama), _("Enviar forzando")):
				return
			if estado.rama_remota:
				remoto, _barra, rama_remota = estado.rama_remota.partition("/")
				destino = f"{estado.rama}:{rama_remota or estado.rama}"
				seguimiento = False
			else:
				remoto = "origin" if "origin" in remotos else remotos[0]
				if len(remotos) > 1 and "origin" not in remotos:
					indice = elegir_uno(self, _("Enviar"), _("&Remoto al que publicar la rama:"), remotos)
					if indice is None:
						return
					remoto = remotos[indice]
				if confirmar(self, _(
					"La rama «{r}» no tiene rama remota. ¿Publicarla en «{o}» y seguirla desde ahora (--set-upstream)?"
				).format(r=estado.rama, o=remoto), _("Publicar la rama")) != wx.ID_YES:
					return
				destino = estado.rama
				seguimiento = True
			self.operacion_red(
				_("Enviando la rama {r} a {o}…").format(r=estado.rama, o=remoto),
				lambda al_linea, cancelado: self.repo.empujar(remoto, destino, forzar=forzar, establecer_seguimiento=seguimiento,
					al_linea=al_linea, cancelado=cancelado),
				_("Rama {r} enviada a {o}.").format(r=estado.rama, o=remoto),
				al_terminar=lambda _r: self.vigilar_actions_del_envio(remoto),
			)

		self._con_estado(seguir)

	def vigilar_actions_del_envio(self, remoto: str) -> None:
		"""Tras enviar a GitHub, vigila las ejecuciones de Actions que lance ese commit y avisa al terminar.

		Se hace en silencio (sin anunciar que se vigila): si el repositorio no tiene
		flujos de Actions, se deja de esperar a los pocos minutos sin decir nada.
		"""
		if not self.ctx.config.obtener("acciones.vigilar_tras_enviar", True):
			return
		principal = self.ctx.ventana_principal
		if principal is None or not hasattr(principal, "vigilar") or self.ctx.cuenta is None:
			return

		def trabajo() -> tuple[str, str]:
			url = self.repo.git("remote", "get-url", remoto).strip()
			return op.nombre_github(url, self.ctx.host) or "", self.repo.git("rev-parse", "HEAD").strip()

		def listo(datos: tuple[str, str]) -> None:
			nombre, sha = datos
			if nombre and sha:
				from app.services import vigilancia_actions as va

				principal.vigilar(va.nuevo_commit(nombre, sha), anunciar=False)

		en_segundo_plano(self, self.ctx, trabajo, al_terminar=listo, sonido="",
			al_fallar=lambda error: log.info("No se pudo vigilar Actions tras enviar: %s", error))

	def sincronizar(self) -> None:
		def seguir(estado: git_local.EstadoRepositorio, _remotos: list[str]) -> None:
			if not estado.rama_remota:
				mostrar_mensaje(self, _("La rama actual no tiene rama remota. Use «Enviar» para publicarla primero."), _("Sincronizar"))
				return
			reorganizar = bool(self.ctx.config.obtener("git.tirar_con_reorganizacion", False))
			remoto, _barra, rama_remota = estado.rama_remota.partition("/")

			def trabajo(al_linea: Callable[[str], None], cancelado: Callable[[], bool]) -> str:
				salida = self.repo.tirar(reorganizar=reorganizar, al_linea=al_linea, cancelado=cancelado)
				return salida + self.repo.empujar(remoto, f"{estado.rama}:{rama_remota}", al_linea=al_linea, cancelado=cancelado)

			self.operacion_red(_("Sincronizando con {r}…").format(r=estado.rama_remota), trabajo, _("Rama sincronizada."))

		self._con_estado(seguir)

	# ════════════════════════════════════════════════════════════════════════
	# GitHub, carpeta y consola
	# ════════════════════════════════════════════════════════════════════════

	def _url_origin(self) -> str:
		try:
			return self.repo.git("remote", "get-url", "origin").strip()
		except git_local.ErrorGit:
			log.debug("Sin remoto origin", exc_info=True)
			return ""

	def abrir_en_github(self) -> None:
		def listo(url: str) -> None:
			nombre = op.nombre_github(url, self.ctx.host)
			if not nombre:
				mostrar_mensaje(self, _("El remoto origin no es de {h}: {u}").format(h=self.ctx.host, u=url or _("(no hay origin)")),
					_("Abrir en GitHub"))
				return
			from app.ui import abrir

			abrir.repositorio(self.ctx, nombre)

		en_segundo_plano(self, self.ctx, self._url_origin, al_terminar=self._vivo(listo), sonido="")

	def crear_pull_request(self) -> None:
		api = self.ctx.api()

		def trabajo() -> tuple[str, git_local.EstadoRepositorio, list[str], list[tuple[str, str]]]:
			ramas = [r.nombre for r in self.repo.ramas(remotas=True) if r.remota and r.nombre.startswith("origin/")]
			url = self._url_origin()
			nombre = op.nombre_github(url, self.ctx.host)
			plantillas: list[tuple[str, str]] = []
			if nombre:
				try:
					plantillas = list(api.plantillas_pr(nombre) or [])
				except Exception:  # noqa: BLE001 - sin plantilla se escribe la descripción desde cero
					log.warning("No se pudieron leer las plantillas de pull request de %s", nombre, exc_info=True)
			return url, self.repo.estado(), ramas, plantillas

		def listo(resultado: tuple[str, git_local.EstadoRepositorio, list[str], list[tuple[str, str]]]) -> None:
			url, estado, ramas, plantillas = resultado
			nombre = op.nombre_github(url, self.ctx.host)
			if not nombre:
				mostrar_mensaje(self, _("El remoto origin no es de {h}: no se puede crear un pull request.").format(h=self.ctx.host),
					_("Crear pull request"))
				return
			if not estado.rama or not estado.rama_remota:
				mostrar_mensaje(self, _("Envíe primero la rama actual a GitHub (menú Git, Enviar)."), _("Crear pull request"))
				return
			from app.ui.repositorio.vistas import _elegir_plantilla_pr

			cuerpo = _elegir_plantilla_pr(self, plantillas)
			if cuerpo is None:
				return
			self.dialogo_pull_request(nombre, estado.rama, [r.removeprefix("origin/") for r in ramas], cuerpo)

		en_segundo_plano(self, self.ctx, trabajo, al_terminar=self._vivo(listo), sonido="")

	def dialogo_pull_request(self, nombre: str, rama: str, bases: list[str], cuerpo: str = "") -> Any:
		from app.ui.editor import CampoExtra, editar

		bases = [b for b in bases if b != rama] or ["main"]
		defecto = next((b for b in ("main", "master", "develop") if b in bases), bases[0])
		api = self.ctx.api()

		def enviar(valores: dict) -> dict:
			return api.crear_pr(nombre, valores["titulo"], rama, valores["base"], valores["cuerpo"], bool(valores.get("borrador")))

		resultado = editar(
			self, self.ctx, _("Nuevo pull request desde {r}").format(r=rama), enviar, con_titulo=True, cuerpo=cuerpo,
			etiqueta_enviar=_("Crear el &pull request"), con_adjuntos=True,
			extras=[
				CampoExtra("base", _("Rama &base:"), "opcion", defecto, [(b, b) for b in bases], _("Rama en la que se fusionarán los cambios.")),
				CampoExtra("borrador", _("Crear como bo&rrador"), "bool", False, ayuda=_("Un borrador no se puede fusionar hasta marcarlo como listo.")),
			],
		)
		if isinstance(resultado, dict) and resultado.get("number"):
			numero = int(resultado["number"])
			self.ctx.avisar(_("Pull request {n} creado.").format(n=numero), interrumpir=False)
			if confirmar(self, _("Pull request {n} creado. ¿Abrirlo?").format(n=numero), _("Pull request")) == wx.ID_YES:
				from app.ui import abrir

				abrir.pull_request(self.ctx, self, nombre, numero)
		return resultado

	def abrir_carpeta(self) -> None:
		try:
			os.startfile(self.carpeta)  # noqa: S606 - abre el Explorador en la carpeta del repositorio
		except OSError as error:
			log.exception("No se pudo abrir la carpeta %s", self.carpeta)
			mostrar_error(self, _("No se pudo abrir la carpeta: {e}").format(e=error), _("Error"))

	def abrir_consola(self) -> None:
		try:
			subprocess.Popen(["cmd.exe"], cwd=self.carpeta, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))  # noqa: S603,S607
		except OSError as error:
			log.exception("No se pudo abrir la consola en %s", self.carpeta)
			mostrar_error(self, _("No se pudo abrir la consola: {e}").format(e=error), _("Error"))

	# ════════════════════════════════════════════════════════════════════════
	# Operaciones en curso, limpieza, mantenimiento, bisección, configuración
	# ════════════════════════════════════════════════════════════════════════

	def continuar_operacion(self) -> None:
		if not self.operacion:
			self.ctx.avisar(_("No hay ninguna operación en curso."))
			return
		operacion = self.operacion
		self.ejecutar_git(lambda: op.continuar_operacion(self.repo, operacion), inicio=_("Continuando…"),
			exito=_("{o} continuada.").format(o=operacion.capitalize()))

	def abortar_operacion(self) -> None:
		if not self.operacion:
			self.ctx.avisar(_("No hay ninguna operación en curso."))
			return
		operacion = self.operacion
		if not confirmar_peligro(self, _(
			"¿Abortar la {o}? El repositorio vuelve a como estaba antes y se pierden las resoluciones de conflictos hechas."
		).format(o=operacion), _("Abortar")):
			return
		self.ejecutar_git(lambda: op.abortar_operacion(self.repo, operacion), exito=_("{o} abortada.").format(o=operacion.capitalize()))

	def saltar_commit(self) -> None:
		if self.operacion != _("reorganización"):
			self.ctx.avisar(_("Solo se puede saltar un commit durante una reorganización."))
			return
		if confirmar(self, _("¿Saltar el commit que da conflicto? Sus cambios no se aplicarán."), _("Saltar commit"),
			peligroso=True) != wx.ID_YES:
			return
		self.ejecutar_git(self.repo.saltar_reorganizacion, exito=_("Commit saltado."))

	def limpiar(self) -> None:
		def listo(salida: str) -> None:
			rutas = [linea.removeprefix("Would remove ").strip() for linea in salida.splitlines() if linea.strip()]
			if not rutas:
				self.ctx.avisar(_("No hay archivos sin seguimiento que borrar."))
				return
			if not confirmar_peligro(self, _(
				"Se borrarán para siempre estos {n} archivos y carpetas sin seguimiento (no van a la papelera):\n\n{l}\n\n¿Continuar?"
			).format(n=len(rutas), l="\n".join(rutas)), _("Limpiar")):
				return
			self.ejecutar_git(lambda: self.repo.limpiar(simular=False), exito=ngettext(
				"{n} elemento borrado.", "{n} elementos borrados.", len(rutas)).format(n=len(rutas)))

		en_segundo_plano(self, self.ctx, lambda: self.repo.limpiar(simular=True), al_terminar=self._vivo(listo), sonido="",
			inicio=_("Buscando archivos sin seguimiento…"))

	def mantenimiento(self) -> None:
		self.ejecutar_git(self.repo.mantenimiento, inicio=_("Haciendo el mantenimiento (git gc)…"), exito=_("Mantenimiento terminado."))

	def biseccion_guiada(self) -> None:
		if self.operacion == _("bisección"):
			self._mostrar_biseccion(_("Bisección en curso. Pruebe el commit actual y diga si está bien o mal."))
			return
		mostrar_mensaje(self, _(dlg.EXPLICACION_BISECCION), _("Bisección guiada"))
		malo = pedir_texto(self, _("Commit &malo (donde ya falla):"), _("Bisección guiada"), "HEAD")
		if not malo:
			return
		bueno = pedir_texto(self, _("Commit &bueno (donde aún funcionaba; SHA, etiqueta o rama):"), _("Bisección guiada"))
		if not bueno:
			return
		en_segundo_plano(self, self.ctx, lambda: op.empezar_biseccion(self.repo, malo.strip(), bueno.strip()),
			al_terminar=self._vivo(lambda salida: (self.refrescar(), self._mostrar_biseccion(salida))), sonido="",
			titulo_error=_("No se pudo empezar la bisección"))

	def _mostrar_biseccion(self, texto: str) -> None:
		dialogo = dlg.DialogoBiseccion(self, self.ctx, self.repo, texto, al_cambiar=self.refrescar)
		try:
			dialogo.ShowModal()
		finally:
			dialogo.Destroy()

	def configurar_repositorio(self) -> None:
		dialogo = dlg.DialogoConfigRepo(self, self.ctx, self.repo)
		try:
			dialogo.ShowModal()
		finally:
			dialogo.Destroy()

	# ════════════════════════════════════════════════════════════════════════
	# Commit
	# ════════════════════════════════════════════════════════════════════════

	def _al_marcar_enmendar(self, _evento: wx.CommandEvent) -> None:
		if not self.casilla_enmendar.GetValue() or self.campo_mensaje.GetValue().strip():
			return

		def listo(mensaje: str) -> None:
			if not self.campo_mensaje.GetValue().strip():
				self.campo_mensaje.SetValue(mensaje)
				self.ctx.avisar(_("Mensaje del último commit copiado en el campo."))

		en_segundo_plano(self, self.ctx, self.repo.ultimo_mensaje, al_terminar=self._vivo(listo), sonido="")

	def confirmar_commit(self) -> None:
		mensaje = self.campo_mensaje.GetValue().strip()
		if not mensaje:
			mostrar_error(self, _("Escriba el mensaje del commit."), _("Falta el mensaje"))
			self.campo_mensaje.SetFocus()
			return
		enmendar = self.casilla_enmendar.GetValue()
		firmar = self.casilla_firmar.GetValue()

		def seguir(estado: git_local.EstadoRepositorio, _remotos: list[str]) -> None:
			if estado.conflictos:
				mostrar_error(self, _("Hay archivos en conflicto. Resuélvalos antes de hacer commit."), _("Commit"))
				self.ir_a_seccion("conflictos")
				return
			preparar_todo = False
			if not estado.preparados and not enmendar:
				if not estado.sin_preparar:
					mostrar_error(self, _("No hay cambios que confirmar."), _("Commit"))
					return
				if confirmar(self, _("No hay cambios preparados. ¿Preparar todos los cambios ({n} archivos) y confirmarlos?").format(
					n=len(estado.sin_preparar)), _("Commit")) != wx.ID_YES:
					return
				preparar_todo = True

			def trabajo() -> str:
				if preparar_todo:
					self.repo.preparar_todo()
				return self.repo.confirmar(mensaje, enmendar=enmendar, firmar=firmar)

			def listo(salida: str) -> None:
				self.campo_mensaje.SetValue("")
				self.casilla_enmendar.SetValue(False)
				self.SetStatusText(op.describir_commit_creado(salida))

			self.ejecutar_git(trabajo, inicio=_("Creando el commit…"), exito=op.describir_commit_creado, al_terminar=listo,
				sonido="enviado")

		self._con_estado(seguir)

	# ════════════════════════════════════════════════════════════════════════
	# Sección Cambios
	# ════════════════════════════════════════════════════════════════════════

	def _vista_cambios(self) -> DefinicionVista:
		def cargar(_api, _pagina, _panel):
			return self.repo.estado().archivos

		def ruta(a: git_local.ArchivoEstado, _c: Any) -> str:
			return a.ruta

		return DefinicionVista(
			"git_cambios", _("Cambios"),
			[
				Columna("archivo", _("Archivo"), ruta, 320),
				Columna("preparado", _("Preparado"), lambda a, _c: op.preparado_texto(a), 100),
				Columna("estado", _("Estado"), lambda a, _c: a.describir(), 300),
			],
			cargar, lambda p, a: self.alternar_preparacion(a),
			[
				Accion(_("&Preparar o quitar de preparados"), lambda p, a: self.alternar_preparacion(a), "Espacio"),
				Accion(_("Preparar &todo"), lambda p, a: self.preparar_todo(), "Ctrl+A", requiere_elemento=False),
				Accion(_("Q&uitar todo de preparados"), lambda p, a: self.quitar_todo(), "Ctrl+Shift+A", requiere_elemento=False),
				Accion(_("&Ver las diferencias"), lambda p, a: self.ver_diferencias_archivo(a), "Ctrl+D", separador_antes=True),
				Accion(_("Desca&rtar los cambios…"), lambda p, a: self.descartar(a), "Supr",
					disponible=lambda p, a: a is not None and not a.sin_seguimiento and not a.conflicto),
				Accion(_("&Borrar el archivo sin seguimiento…"), lambda p, a: self.borrar_sin_seguimiento(a), "Shift+Supr",
					disponible=lambda p, a: a is not None and a.sin_seguimiento),
				Accion(_("Añadir a .&gitignore…"), lambda p, a: self.ignorar(a)),
			],
			_("No hay cambios: el árbol de trabajo está limpio."), paginada=False, sonido_carga=False,
			detalle=lambda a, _c: "\n".join(filter(None, [
				_("Archivo: {r}").format(r=a.ruta), _("Antes: {r}").format(r=a.ruta_original) if a.ruta_original else "",
				_("Estado: {e}").format(e=a.describir()), _("Preparado: {p}").format(p=op.preparado_texto(a)),
			])),
		)

	def _recargar(self, clave: str) -> None:
		panel = self.paneles.get(clave)
		if panel is not None:
			panel.cargar(anunciar=False)

	def alternar_preparacion(self, archivo: git_local.ArchivoEstado) -> None:
		if archivo.conflicto:
			self.ctx.avisar(_("Este archivo está en conflicto: resuélvalo en la sección Conflictos."))
			return
		if archivo.sin_preparar:
			funcion = lambda: self.repo.preparar([archivo.ruta])  # noqa: E731
			exito = _("Preparado: {r}.").format(r=archivo.ruta)
		else:
			funcion = lambda: op.quitar_de_preparados(self.repo, [archivo.ruta])  # noqa: E731
			exito = _("Quitado de preparados: {r}.").format(r=archivo.ruta)
		self.ejecutar_git(funcion, exito=exito, sonido="")

	def preparar_todo(self) -> None:
		self.ejecutar_git(self.repo.preparar_todo, exito=_("Todos los cambios preparados."), sonido="")

	def quitar_todo(self) -> None:
		self.ejecutar_git(lambda: op.quitar_todo_de_preparados(self.repo), exito=_("Ningún cambio preparado."), sonido="")

	def ver_diferencias_archivo(self, archivo: git_local.ArchivoEstado) -> None:
		from app.ui.detalle.diferencias import abrir_diff

		def obtener() -> str:
			if archivo.sin_seguimiento:
				return self.repo.diferencias_sin_seguimiento(archivo.ruta)
			texto = ""
			if archivo.preparado:
				texto += self.repo.diferencias(archivo.ruta, preparados=True)
			if archivo.arbol != "." or archivo.conflicto:
				texto += self.repo.diferencias(archivo.ruta)
			return texto

		abrir_diff(self.ctx, self, _("Diferencias de {r}").format(r=archivo.ruta), obtener, cabecera=_(
			"Archivo {r}. {e}. Si tiene cambios preparados y sin preparar, salen primero los preparados.").format(
				r=archivo.ruta, e=archivo.describir()))

	def descartar(self, archivo: git_local.ArchivoEstado) -> None:
		if archivo.arbol == ".":
			mostrar_mensaje(self, _("{r} solo tiene cambios preparados. Quítelos primero de preparados (Espacio).").format(r=archivo.ruta),
				_("Descartar"))
			return
		if not confirmar_peligro(self, _("¿Descartar los cambios sin preparar de {r}? No se puede deshacer.").format(r=archivo.ruta),
			_("Descartar cambios")):
			return
		self.ejecutar_git(lambda: self.repo.descartar_cambios([archivo.ruta]), exito=_("Cambios descartados."))

	def borrar_sin_seguimiento(self, archivo: git_local.ArchivoEstado) -> None:
		if not confirmar_peligro(self, _("¿Borrar para siempre {r}? No va a la papelera.").format(r=archivo.ruta), _("Borrar archivo")):
			return
		self.ejecutar_git(lambda: self.repo.borrar_sin_seguimiento([archivo.ruta]), exito=_("Archivo borrado."))

	def ignorar(self, archivo: git_local.ArchivoEstado) -> None:
		modos = [("archivo", _("Este &archivo: {l}")), ("extension", _("Todos los de la &extensión: {l}")),
			("carpeta", _("Toda la &carpeta: {l}"))]
		opciones = [texto.format(l=op.linea_gitignore(archivo.ruta, modo)) for modo, texto in modos]
		indice = elegir_opcion(self, _("¿Qué quiere añadir al archivo .gitignore?"), _("Añadir a .gitignore"), opciones)
		if indice is None:
			return
		linea = op.linea_gitignore(archivo.ruta, modos[indice][0])
		aviso = "" if archivo.sin_seguimiento else _(" Git sigue el archivo: para dejar de seguirlo, bórrelo del índice.")
		self.ejecutar_git(lambda: op.anadir_a_gitignore(self.raiz, linea),
			exito=lambda anadida: (_("Añadido «{l}» a .gitignore.") if anadida else _("«{l}» ya estaba en .gitignore.")).format(l=linea) + aviso)

	# ════════════════════════════════════════════════════════════════════════
	# Sección Historial
	# ════════════════════════════════════════════════════════════════════════

	def _vista_historial(self) -> DefinicionVista:
		def cargar(_api, pagina, panel):
			filtro = panel.datos.get("filtro") or {}
			commits = self.repo.historial(
				cantidad=POR_PAGINA_HISTORIAL, saltar=(pagina - 1) * POR_PAGINA_HISTORIAL, ruta=filtro.get("ruta") or None,
				todas=bool(filtro.get("todas")), buscar=filtro.get("buscar", ""), autor=filtro.get("autor", ""),
			)
			return Pagina(commits, siguiente="mas" if len(commits) >= POR_PAGINA_HISTORIAL else "", numero=pagina)

		def detalle(commit: git_local.Commit, _c: Any) -> str:
			return "\n".join(filter(None, [
				_("Commit {s}").format(s=commit.sha), _("Autor: {a} <{c}>").format(a=commit.autor, c=commit.correo),
				_("Fecha: {f}").format(f=_fecha(commit.fecha, self.ctx)),
				_("Padres: {p}").format(p=", ".join(p[:10] for p in commit.padres)) if commit.padres else "",
				_("Referencias: {r}").format(r=commit.referencias) if commit.referencias else "",
				"", commit.asunto, "", commit.cuerpo,
			]))

		return DefinicionVista(
			"git_historial", _("Historial"),
			[
				Columna("sha", _("Commit"), lambda m, _c: m.sha_corto, 90),
				Columna("asunto", _("Asunto"), lambda m, _c: (_("Fusión: ") if m.es_fusion else "") + m.asunto, 420),
				Columna("autor", _("Autor"), lambda m, _c: m.autor, 150),
				Columna("fecha", _("Fecha"), lambda m, ctx: _fecha(m.fecha, ctx), 150),
				Columna("referencias", _("Referencias"), lambda m, _c: m.referencias, 200),
			],
			cargar, lambda p, m: self.ver_commit(m),
			[
				Accion(_("&Ver las diferencias"), lambda p, m: self.ver_commit(m), "Intro"),
				Accion(_("A&plicar este commit (cherry-pick)…"), lambda p, m: self.cherry_pick(m), separador_antes=True),
				Accion(_("&Revertir este commit…"), lambda p, m: self.revertir(m)),
				Accion(_("Res&tablecer la rama aquí…"), lambda p, m: self.restablecer(m.sha, f"{m.sha_corto} «{m.asunto}»")),
				Accion(_("Crear u&na rama aquí…"), lambda p, m: self.crear_rama(m.sha, m.sha_corto), "Ctrl+N"),
				Accion(_("Crear una &etiqueta aquí…"), lambda p, m: self.crear_etiqueta(m.sha), "Ctrl+E"),
				Accion(_("Copiar el &SHA"), lambda p, m: copiar(self.ctx, m.sha, _("SHA copiado.")), "Ctrl+Shift+C"),
				Accion(_("Filtrar por a&utor, texto o ruta…"), lambda p, m: self.filtrar_historial(), "F4",
					requiere_elemento=False, separador_antes=True),
				Accion(_("Quitar el filtro del &historial"), lambda p, m: self.quitar_filtro_historial(), "Shift+F4",
					requiere_elemento=False, disponible=lambda p, m: bool(p.datos.get("filtro"))),
			],
			_("No hay commits que mostrar."), detalle=detalle, sonido_carga=False,
		)

	def ver_commit(self, commit: git_local.Commit) -> None:
		from app.ui.detalle.diferencias import abrir_diff

		cabecera = "\n".join([
			_("Commit {s}").format(s=commit.sha),
			_("Autor: {a} <{c}>, {f}").format(a=commit.autor, c=commit.correo, f=_fecha(commit.fecha, self.ctx)),
			"", commit.asunto, commit.cuerpo,
		]).rstrip()
		abrir_diff(self.ctx, self, _("Commit {s}: {a}").format(s=commit.sha_corto, a=commit.asunto),
			lambda: self.repo.diferencias_commit(commit.sha), cabecera)

	def cherry_pick(self, commit: git_local.Commit) -> None:
		if confirmar(self, _("¿Aplicar el commit {s} «{a}» sobre la rama actual (cherry-pick)?").format(
			s=commit.sha_corto, a=commit.asunto), _("Cherry-pick")) != wx.ID_YES:
			return
		self.ejecutar_git(lambda: self.repo.elegir_cherry(commit.sha), inicio=_("Aplicando el commit…"), exito=_("Commit aplicado."))

	def revertir(self, commit: git_local.Commit) -> None:
		if confirmar(self, _("¿Crear un commit nuevo que deshace {s} «{a}»?").format(s=commit.sha_corto, a=commit.asunto),
			_("Revertir")) != wx.ID_YES:
			return
		self.ejecutar_git(lambda: self.repo.revertir(commit.sha), inicio=_("Revirtiendo…"), exito=_("Commit revertido."))

	def restablecer(self, ref: str, descripcion: str) -> None:
		modo = dlg.elegir_modo_restablecer(self, descripcion)
		if modo:
			self.ejecutar_git(lambda: self.repo.restablecer(ref, modo), exito=_("Rama restablecida a {d}.").format(d=descripcion))

	def crear_rama(self, desde: str = "", descripcion: str = "") -> None:
		nombre = pedir_texto(self, _("&Nombre de la rama nueva:"), _("Nueva rama desde {d}").format(d=descripcion or _("la actual")))
		if not nombre or not nombre.strip():
			return
		nombre = nombre.strip()
		cambiar = confirmar(self, _("¿Cambiar a la rama «{n}» después de crearla?").format(n=nombre), _("Nueva rama")) == wx.ID_YES
		self.ejecutar_git(lambda: self.repo.crear_rama(nombre, desde, cambiar),
			exito=(_("Rama {n} creada; ahora está en ella.") if cambiar else _("Rama {n} creada.")).format(n=nombre))

	def crear_etiqueta(self, ref: str = "HEAD") -> None:
		nombre = pedir_texto(self, _("&Nombre de la etiqueta (por ejemplo v1.0):"), _("Nueva etiqueta"))
		if not nombre or not nombre.strip():
			return
		mensaje = pedir_texto(self, _("&Mensaje (vacío para una etiqueta ligera):"), _("Nueva etiqueta"))
		if mensaje is None:
			return
		self.ejecutar_git(lambda: self.repo.crear_etiqueta(nombre.strip(), mensaje.strip(), ref),
			exito=_("Etiqueta {n} creada.").format(n=nombre.strip()))

	def filtrar_historial(self) -> None:
		panel = self.paneles["historial"]
		filtro = dlg.pedir_filtro_historial(self, panel.datos.get("filtro"))
		if filtro is None:
			return
		panel.datos["filtro"] = {k: v for k, v in filtro.items() if v}
		self._aplicar_filtro_historial()

	def quitar_filtro_historial(self) -> None:
		self.paneles["historial"].datos["filtro"] = {}
		self._aplicar_filtro_historial()

	def _aplicar_filtro_historial(self) -> None:
		panel = self.paneles["historial"]
		texto = dlg.describir_filtro(panel.datos.get("filtro"))
		self.texto_filtro.SetLabel(texto)
		self.ctx.avisar(texto)
		panel.cargar()

	# ════════════════════════════════════════════════════════════════════════
	# Sección Ramas
	# ════════════════════════════════════════════════════════════════════════

	def _vista_ramas(self) -> DefinicionVista:
		def tipo(r: git_local.Rama, _c: Any) -> str:
			if r.actual:
				return _("actual")
			return _("remota") if r.remota else _("local")

		def seguimiento(r: git_local.Rama, _c: Any) -> str:
			if not r.seguimiento:
				return ""
			estado = op.describir_seguimiento(r.estado_seguimiento) or _("al día")
			return f"{r.seguimiento}, {estado}"

		return DefinicionVista(
			"git_ramas", _("Ramas"),
			[
				Columna("nombre", _("Rama"), lambda r, _c: r.nombre, 220),
				Columna("tipo", _("Tipo"), tipo, 80),
				Columna("seguimiento", _("Seguimiento"), seguimiento, 260),
				Columna("asunto", _("Último commit"), lambda r, _c: r.asunto, 300),
				Columna("fecha", _("Fecha"), lambda r, ctx: _fecha(r.fecha, ctx), 140),
			],
			lambda _a, _p, _panel: self.repo.ramas(remotas=True), lambda p, r: self.cambiar_rama(r),
			[
				Accion(_("&Cambiar a esta rama"), lambda p, r: self.cambiar_rama(r), "Intro"),
				Accion(_("&Nueva rama desde esta…"), lambda p, r: self.crear_rama(r.nombre, r.nombre), "Ctrl+N"),
				Accion(_("&Renombrar…"), lambda p, r: self.renombrar_rama(r), "F2", disponible=lambda p, r: r is not None and not r.remota),
				Accion(_("&Borrar la rama…"), lambda p, r: self.borrar_rama(r), "Supr", disponible=lambda p, r: r is not None and not r.remota),
				Accion(_("Borrar la rama del ser&vidor…"), lambda p, r: self.borrar_rama_remota(r), "Shift+Supr",
					disponible=lambda p, r: r is not None and (r.remota or bool(r.seguimiento))),
				Accion(_("Fusionar en la rama ac&tual…"), lambda p, r: self.fusionar(r), separador_antes=True,
					disponible=lambda p, r: r is not None and not r.actual),
				Accion(_("Reor&ganizar la rama actual sobre esta…"), lambda p, r: self.reorganizar(r),
					disponible=lambda p, r: r is not None and not r.actual),
				Accion(_("Establecer como &seguimiento de la actual"), lambda p, r: self.establecer_seguimiento(r),
					disponible=lambda p, r: r is not None and r.remota),
			],
			_("No hay ramas todavía: haga el primer commit."), paginada=False, sonido_carga=False,
		)

	def cambiar_rama(self, rama: git_local.Rama) -> None:
		if rama.actual:
			self.ctx.avisar(_("Ya está en la rama {r}.").format(r=rama.nombre))
			return
		if rama.remota:
			local = rama.nombre.split("/", 1)[1] if "/" in rama.nombre else rama.nombre
			locales = {r.nombre for r in self.paneles["ramas"].elementos if not r.remota}
			if local in locales:
				funcion = lambda: self.repo.cambiar_rama(local)  # noqa: E731
			else:
				funcion = lambda: self.repo.cambiar_rama(rama.nombre, crear_seguimiento=True)  # noqa: E731
			destino = local
		else:
			funcion = lambda: self.repo.cambiar_rama(rama.nombre)  # noqa: E731
			destino = rama.nombre
		self.ejecutar_git(funcion, exito=_("Ahora está en la rama {r}.").format(r=destino))

	def renombrar_rama(self, rama: git_local.Rama) -> None:
		nuevo = pedir_texto(self, _("&Nombre nuevo:"), _("Renombrar la rama {r}").format(r=rama.nombre), rama.nombre)
		if nuevo and nuevo.strip() and nuevo.strip() != rama.nombre:
			self.ejecutar_git(lambda: self.repo.renombrar_rama(rama.nombre, nuevo.strip()),
				exito=_("Rama renombrada a {n}.").format(n=nuevo.strip()))

	def borrar_rama(self, rama: git_local.Rama) -> None:
		if rama.actual:
			mostrar_error(self, _("No se puede borrar la rama en la que está. Cambie antes a otra."), _("Borrar rama"))
			return
		if not confirmar_peligro(self, _("¿Borrar la rama local {r}?").format(r=rama.nombre), _("Borrar rama")):
			return

		def fallo(error: BaseException) -> None:
			salida = getattr(error, "salida", "") or ""
			if "not fully merged" in salida and confirmar_peligro(self, _(
				"La rama {r} tiene commits que no están en ninguna otra rama. Si la borra, se perderán. ¿Borrarla igualmente?"
			).format(r=rama.nombre), _("Borrar rama")):
				self.ejecutar_git(lambda: self.repo.borrar_rama(rama.nombre, forzar=True), exito=_("Rama borrada."))
				return
			if "not fully merged" not in salida:
				mostrar_error(self, mensaje_error(error), _("No se pudo borrar"))

		en_segundo_plano(self, self.ctx, lambda: self.repo.borrar_rama(rama.nombre), exito=_("Rama borrada."),
			al_terminar=self._vivo(lambda _r: self.refrescar()), al_fallar=self._vivo(fallo))

	def borrar_rama_remota(self, rama: git_local.Rama) -> None:
		completa = rama.nombre if rama.remota else rama.seguimiento
		remoto, _barra, nombre = completa.partition("/")
		if not nombre:
			return
		if not confirmar_peligro(self, _("¿Borrar la rama {n} del remoto {r}? Las demás personas dejarán de verla.").format(
			n=nombre, r=remoto), _("Borrar rama remota")):
			return
		self.operacion_red(_("Borrando la rama {n} de {r}…").format(n=nombre, r=remoto),
			lambda al_linea, cancelado: self.repo.git_red("push", "--progress", remoto, "--delete", nombre,
				al_linea=al_linea, cancelado=cancelado),
			_("Rama {n} borrada de {r}.").format(n=nombre, r=remoto))

	def fusionar(self, rama: git_local.Rama) -> None:
		actual = self.estado.rama if self.estado else ""
		if confirmar(self, _("¿Fusionar {r} en la rama actual {a}?").format(r=rama.nombre, a=actual or _("(actual)")),
			_("Fusionar")) != wx.ID_YES:
			return
		self.ejecutar_git(lambda: self.repo.fusionar(rama.nombre), inicio=_("Fusionando…"),
			exito=_("{r} fusionada en la rama actual.").format(r=rama.nombre))

	def reorganizar(self, rama: git_local.Rama) -> None:
		if confirmar(self, _(
			"¿Reorganizar la rama actual sobre {r}? Sus commits se volverán a aplicar encima de {r} (rebase)."
		).format(r=rama.nombre), _("Reorganizar")) != wx.ID_YES:
			return
		self.ejecutar_git(lambda: self.repo.reorganizar(rama.nombre), inicio=_("Reorganizando…"),
			exito=_("Rama reorganizada sobre {r}.").format(r=rama.nombre))

	def establecer_seguimiento(self, rama: git_local.Rama) -> None:
		self.ejecutar_git(lambda: op.establecer_seguimiento(self.repo, rama.nombre),
			exito=_("La rama actual sigue ahora a {r}.").format(r=rama.nombre))

	# ════════════════════════════════════════════════════════════════════════
	# Etiquetas, stash, remotos, submódulos, worktrees y reflog
	# ════════════════════════════════════════════════════════════════════════

	def _vista_etiquetas(self) -> DefinicionVista:
		def cargar(_a, _p, _panel):
			return [{"nombre": n, "sha": s, "fecha": fe, "asunto": a} for n, s, fe, a in self.repo.etiquetas()]

		return DefinicionVista(
			"git_etiquetas", _("Etiquetas"),
			[
				Columna("nombre", _("Etiqueta"), lambda e, _c: e["nombre"], 180),
				Columna("sha", _("Commit"), lambda e, _c: e["sha"], 90),
				Columna("fecha", _("Fecha"), lambda e, ctx: _fecha(e["fecha"], ctx), 150),
				Columna("asunto", _("Mensaje"), lambda e, _c: e["asunto"], 360),
			],
			cargar, lambda p, e: self._ver_ref(e["nombre"]),
			[
				Accion(_("&Ver el commit"), lambda p, e: self._ver_ref(e["nombre"]), "Intro"),
				Accion(_("&Nueva etiqueta en el commit actual…"), lambda p, e: self.crear_etiqueta("HEAD"), "Ctrl+N", requiere_elemento=False),
				Accion(_("&Borrar la etiqueta…"), lambda p, e: self.borrar_etiqueta(e["nombre"]), "Supr"),
				Accion(_("&Enviar al remoto"), lambda p, e: self.enviar_etiqueta(e["nombre"]), "Ctrl+E"),
			],
			_("No hay etiquetas."), paginada=False, sonido_carga=False,
		)

	def _ver_ref(self, ref: str) -> None:
		from app.ui.detalle.diferencias import abrir_diff

		abrir_diff(self.ctx, self, _("Commit de {r}").format(r=ref), lambda: self.repo.diferencias_commit(ref))

	def borrar_etiqueta(self, nombre: str) -> None:
		if confirmar_peligro(self, _("¿Borrar la etiqueta local {n}? (En el remoto, si la envió, sigue existiendo.)").format(n=nombre),
			_("Borrar etiqueta")):
			self.ejecutar_git(lambda: self.repo.borrar_etiqueta(nombre), exito=_("Etiqueta borrada."))

	def enviar_etiqueta(self, nombre: str) -> None:
		def seguir(_estado: git_local.EstadoRepositorio, remotos: list[str]) -> None:
			if not remotos:
				mostrar_error(self, _("El repositorio no tiene remotos."), _("Enviar etiqueta"))
				return
			remoto = "origin" if "origin" in remotos else remotos[0]
			self.operacion_red(_("Enviando la etiqueta {n} a {r}…").format(n=nombre, r=remoto),
				lambda al_linea, cancelado: self.repo.git_red("push", "--progress", remoto, f"refs/tags/{nombre}",
					al_linea=al_linea, cancelado=cancelado),
				_("Etiqueta {n} enviada a {r}.").format(n=nombre, r=remoto))

		self._con_estado(seguir)

	def _vista_stash(self) -> DefinicionVista:
		def cargar(_a, _p, _panel):
			return [{"ref": r, "fecha": fe, "mensaje": m} for r, fe, m in self.repo.stashes()]

		return DefinicionVista(
			"git_stash", _("Stash"),
			[
				Columna("ref", _("Referencia"), lambda s, _c: s["ref"], 110),
				Columna("mensaje", _("Mensaje"), lambda s, _c: s["mensaje"], 420),
				Columna("fecha", _("Fecha"), lambda s, ctx: _fecha(s["fecha"], ctx), 150),
			],
			cargar, lambda p, s: self.ver_stash(s),
			[
				Accion(_("&Ver las diferencias"), lambda p, s: self.ver_stash(s), "Intro"),
				Accion(_("&Guardar los cambios en un stash…"), lambda p, s: self.guardar_stash(), "Ctrl+N", requiere_elemento=False),
				Accion(_("A&plicar"), lambda p, s: self.aplicar_stash(s, False), "Ctrl+L"),
				Accion(_("Aplicar y &borrar"), lambda p, s: self.aplicar_stash(s, True), "Ctrl+Shift+L"),
				Accion(_("Bo&rrar…"), lambda p, s: self.borrar_stash(s), "Supr"),
			],
			_("No hay cambios guardados en stash."), paginada=False, sonido_carga=False,
		)

	def ver_stash(self, stash: dict) -> None:
		from app.ui.detalle.diferencias import abrir_diff

		abrir_diff(self.ctx, self, _("Stash {r}: {m}").format(r=stash["ref"], m=stash["mensaje"]), lambda: self.repo.ver_stash(stash["ref"]))

	def guardar_stash(self) -> None:
		mensaje = pedir_texto(self, _("&Mensaje para reconocerlo (opcional):"), _("Guardar en stash"))
		if mensaje is None:
			return
		self.ejecutar_git(lambda: self.repo.guardar_stash(mensaje.strip()),
			exito=_("Cambios guardados en el stash (incluidos los archivos sin seguimiento)."))

	def aplicar_stash(self, stash: dict, borrar: bool) -> None:
		self.ejecutar_git(lambda: self.repo.aplicar_stash(stash["ref"], borrar=borrar),
			exito=_("Stash aplicado y borrado.") if borrar else _("Stash aplicado."))

	def borrar_stash(self, stash: dict) -> None:
		if confirmar_peligro(self, _("¿Borrar {r} «{m}»? Sus cambios se perderán.").format(r=stash["ref"], m=stash["mensaje"]),
			_("Borrar stash")):
			self.ejecutar_git(lambda: self.repo.borrar_stash(stash["ref"]), exito=_("Stash borrado."))

	def _vista_remotos(self) -> DefinicionVista:
		return DefinicionVista(
			"git_remotos", _("Remotos"),
			[
				Columna("nombre", _("Remoto"), lambda r, _c: r["nombre"], 120),
				Columna("traer", _("URL para traer"), lambda r, _c: r["traer"], 380),
				Columna("enviar", _("URL para enviar"), lambda r, _c: r["enviar"], 380, visible=False),
			],
			lambda _a, _p, _panel: op.agrupar_remotos(self.repo.remotos()), None,
			[
				Accion(_("&Traer de este remoto"), lambda p, r: self.traer_de(r["nombre"]), "Ctrl+T"),
				Accion(_("&Nuevo remoto…"), lambda p, r: self.nuevo_remoto(), "Ctrl+N", requiere_elemento=False),
				Accion(_("Cambiar la &URL…"), lambda p, r: self.cambiar_url_remoto(r), "F2"),
				Accion(_("&Borrar el remoto…"), lambda p, r: self.borrar_remoto(r), "Supr"),
			],
			_("No hay remotos. Añada uno con Control+N."), paginada=False, sonido_carga=False,
		)

	def traer_de(self, remoto: str) -> None:
		self.operacion_red(_("Trayendo cambios de {r}…").format(r=remoto),
			lambda al_linea, cancelado: self.repo.traer(remoto=remoto, al_linea=al_linea, cancelado=cancelado),
			_("Cambios traídos de {r}.").format(r=remoto))

	def nuevo_remoto(self) -> None:
		existentes = {r["nombre"] for r in self.paneles["remotos"].elementos}
		nombre = pedir_texto(self, _("&Nombre del remoto:"), _("Nuevo remoto"), "upstream" if "origin" in existentes else "origin")
		if not nombre or not nombre.strip():
			return
		url = pedir_texto(self, _("&URL o dueño/repositorio:"), _("Nuevo remoto"))
		if not url or not url.strip():
			return
		url = op.normalizar_url(url, "https", self.ctx.host)
		self.ejecutar_git(lambda: self.repo.anadir_remoto(nombre.strip(), url), exito=_("Remoto {n} añadido.").format(n=nombre.strip()))

	def cambiar_url_remoto(self, remoto: dict) -> None:
		url = pedir_texto(self, _("&URL nueva:"), _("Cambiar la URL de {n}").format(n=remoto["nombre"]), remoto["traer"])
		if url and url.strip() and url.strip() != remoto["traer"]:
			nueva = op.normalizar_url(url, "https", self.ctx.host)
			self.ejecutar_git(lambda: self.repo.cambiar_url_remoto(remoto["nombre"], nueva), exito=_("URL cambiada."))

	def borrar_remoto(self, remoto: dict) -> None:
		if confirmar_peligro(self, _("¿Quitar el remoto {n} de este repositorio? (En el servidor no se borra nada.)").format(
			n=remoto["nombre"]), _("Borrar remoto")):
			self.ejecutar_git(lambda: self.repo.borrar_remoto(remoto["nombre"]), exito=_("Remoto quitado."))

	def _vista_submodulos(self) -> DefinicionVista:
		return DefinicionVista(
			"git_submodulos", _("Submódulos"),
			[
				Columna("ruta", _("Ruta"), lambda s, _c: s["ruta"], 260),
				Columna("estado", _("Estado"), lambda s, _c: s["estado"], 140),
				Columna("sha", _("Commit"), lambda s, _c: s["sha"], 100),
				Columna("descripcion", _("Descripción"), lambda s, _c: s["descripcion"], 200),
			],
			lambda _a, _p, _panel: [op.analizar_submodulo(linea) for linea in self.repo.submodulos()], None,
			[Accion(_("Act&ualizar los submódulos"), lambda p, s: self.actualizar_submodulos(), "Ctrl+U", requiere_elemento=False)],
			_("Este repositorio no tiene submódulos."), paginada=False, sonido_carga=False,
		)

	def actualizar_submodulos(self) -> None:
		self.operacion_red(_("Actualizando los submódulos…"),
			lambda al_linea, _cancelado: self.repo.actualizar_submodulos(al_linea=al_linea), _("Submódulos actualizados."))

	def _vista_worktrees(self) -> DefinicionVista:
		return DefinicionVista(
			"git_worktrees", _("Worktrees"),
			[
				Columna("carpeta", _("Carpeta"), lambda w, _c: w["carpeta"], 420),
				Columna("rama", _("Rama"), lambda w, _c: w["rama"], 180),
				Columna("sha", _("Commit"), lambda w, _c: w["sha"], 100),
			],
			lambda _a, _p, _panel: [op.analizar_worktree(linea) for linea in self.repo.worktrees()],
			lambda p, w: abrir_ventana_git(self.ctx, w["carpeta"]),
			[
				Accion(_("A&brir en otra ventana de git"), lambda p, w: abrir_ventana_git(self.ctx, w["carpeta"]), "Intro"),
				Accion(_("&Nuevo worktree…"), lambda p, w: self.nuevo_worktree(), "Ctrl+N", requiere_elemento=False),
			],
			_("No hay worktrees."), paginada=False, sonido_carga=False,
		)

	def nuevo_worktree(self) -> None:
		def seguir(ramas: list[str]) -> None:
			if not ramas:
				mostrar_error(self, _("No hay ramas locales."), _("Nuevo worktree"))
				return
			actual = self.estado.rama if self.estado else ""
			libres = [r for r in ramas if r != actual] or ramas
			indice = elegir_uno(self, _("Nuevo worktree"), _("&Rama para el worktree:"), libres)
			if indice is None:
				return
			rama = libres[indice]
			propuesta = str(Path(self.carpeta).parent / f"{self.nombre}-{rama.replace('/', '-')}")
			carpeta = pedir_texto(self, _("&Carpeta nueva del worktree:"), _("Nuevo worktree"), propuesta)
			if not carpeta or not carpeta.strip():
				return
			self.ejecutar_git(lambda: self.repo.anadir_worktree(carpeta.strip(), rama),
				exito=_("Worktree creado en {c}.").format(c=carpeta.strip()))

		en_segundo_plano(self, self.ctx, lambda: [r.nombre for r in self.repo.ramas(remotas=False)],
			al_terminar=self._vivo(seguir), sonido="")

	def _vista_reflog(self) -> DefinicionVista:
		return DefinicionVista(
			"git_reflog", _("Reflog"),
			[
				Columna("sha", _("Commit"), lambda r, _c: r["sha"], 90),
				Columna("referencia", _("Referencia"), lambda r, _c: r["referencia"], 120),
				Columna("descripcion", _("Qué pasó"), lambda r, _c: r["descripcion"], 480),
			],
			lambda _a, _p, _panel: [op.analizar_reflog(linea) for linea in self.repo.reflog(200)],
			lambda p, r: self._ver_ref(r["sha"]),
			[
				Accion(_("&Ver el commit"), lambda p, r: self._ver_ref(r["sha"]), "Intro"),
				Accion(_("Res&tablecer la rama aquí…"), lambda p, r: self.restablecer(r["sha"], f"{r['sha']} ({r['referencia']})")),
				Accion(_("Copiar el &SHA"), lambda p, r: copiar(self.ctx, r["sha"], _("SHA copiado.")), "Ctrl+Shift+C"),
			],
			_("El reflog está vacío."), paginada=False, sonido_carga=False,
		)

	# ════════════════════════════════════════════════════════════════════════
	# Sección Conflictos
	# ════════════════════════════════════════════════════════════════════════

	def _vista_conflictos(self) -> DefinicionVista:
		return DefinicionVista(
			"git_conflictos", _("Conflictos"),
			[
				Columna("archivo", _("Archivo"), lambda a, _c: a.ruta, 360),
				Columna("tipo", _("Conflicto"), lambda a, _c: describir_tipo_conflicto(a.indice + a.arbol, c.es_invertido(self.operacion)), 320),
			],
			lambda _a, _p, _panel: self.repo.estado().conflictos, lambda p, a: self.resolver_bloques(a),
			[
				Accion(_("&Resolver bloque a bloque…"), lambda p, a: self.resolver_bloques(a), "Intro"),
				Accion(_("Usar &su versión entera"), lambda p, a: self.resolver_entero(a, c.PROPIA)),
				Accion(_("Usar la o&tra versión entera"), lambda p, a: self.resolver_entero(a, c.OTRA)),
				Accion(_("Mar&car como resuelto"), lambda p, a: self.marcar_resuelto(a)),
				Accion(_("&Ver las diferencias"), lambda p, a: self.ver_diferencias_archivo(a), "Ctrl+D"),
			],
			_("No hay archivos en conflicto."), paginada=False, sonido_carga=False,
		)

	def resolver_bloques(self, archivo: git_local.ArchivoEstado) -> None:
		dlg.resolver_archivo(self, self.ctx, self.repo, self.raiz, archivo.ruta, self.operacion,
			al_resolver=lambda _ruta: self.refrescar())

	def resolver_entero(self, archivo: git_local.ArchivoEstado, eleccion: str) -> None:
		version = c.version_git(eleccion, c.es_invertido(self.operacion))
		nombre = c.nombre_eleccion(eleccion)
		self.ejecutar_git(lambda: self.repo.resolver_con(archivo.ruta, version),
			exito=_("{r} resuelto con {n}.").format(r=archivo.ruta, n=nombre))

	def marcar_resuelto(self, archivo: git_local.ArchivoEstado) -> None:
		def seguir(con_marcadores: bool) -> None:
			if con_marcadores and confirmar(self, _(
				"{r} todavía tiene marcadores de conflicto (<<<<<<<). ¿Marcarlo como resuelto igualmente?"
			).format(r=archivo.ruta), _("Marcar como resuelto"), peligroso=True) != wx.ID_YES:
				return
			self.ejecutar_git(lambda: self.repo.marcar_resuelto(archivo.ruta), exito=_("{r} marcado como resuelto.").format(r=archivo.ruta))

		def comprobar() -> bool:
			ruta = self.raiz / archivo.ruta
			if not ruta.is_file():
				return False
			return c.tiene_marcadores(ruta.read_bytes().decode("utf-8", errors="replace"))

		en_segundo_plano(self, self.ctx, comprobar, al_terminar=self._vivo(seguir), sonido="")


def describir_tipo_conflicto(xy: str, invertido: bool = False) -> str:
	"""Código de conflicto de ``status`` (UU, AA, DU…) en palabras, desde el punto de vista de la persona."""
	suya, otra = (_("la otra versión"), _("su versión")) if invertido else (_("su versión"), _("la otra versión"))
	textos = {
		"UU": _("modificado en las dos versiones"),
		"AA": _("añadido en las dos versiones"),
		"DD": _("borrado en las dos versiones"),
		"AU": _("añadido solo en {v}").format(v=suya),
		"UA": _("añadido solo en {v}").format(v=otra),
		"DU": _("borrado en {v} y modificado en la otra").format(v=suya),
		"UD": _("borrado en {v} y modificado en la otra").format(v=otra),
	}
	return textos.get(xy, xy)
