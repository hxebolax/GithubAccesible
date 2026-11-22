"""Ventana de un repositorio: lista de secciones a la izquierda y su contenido a la derecha.

Teclas de la ventana:

- F6: alterna entre la lista de secciones y el contenido.
- Ctrl+Tab / Ctrl+Mayús+Tab: sección siguiente / anterior.
- Alt+1 … Alt+9: las nueve primeras secciones (menú «Ir»).
- F5: actualiza el repositorio y la sección visible. Ctrl+W: cierra.
- Escape NO cierra la ventana (se cerraría por accidente al salir de un menú).

El menú «Acciones» se rehace cada vez que se abre con las acciones de la
sección visible y del elemento elegido. Sus atajos se escriben entre
paréntesis y no tras un tabulador: así no se registran como atajos de toda
la ventana (los atiende la propia lista y no roban teclas a los campos).

Cada sección se crea la primera vez que se elige (y entonces carga sus
datos), de modo que abrir la ventana solo pide a GitHub lo que se ve.
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from dataclasses import dataclass
from typing import Any

import wx

from app.ui.comunes import confirmar, copiar, en_segundo_plano, mensaje_error, mostrar_error
from app.ui.repositorio.paneles import PANELES
from app.ui.repositorio.vistas import VISTAS, etiqueta_con_letra, rotular
from app.ui.vistas.base import PanelLista

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class Seccion:
	"""Una sección: identificador estable, nombre en la lista y etiqueta del menú «Ir» (con su letra)."""

	id: str
	titulo: str
	menu: str


SECCIONES: list[Seccion] = [
	Seccion("resumen", "Resumen", "&1 Resumen"),
	Seccion("codigo", "Código", "&2 Código"),
	Seccion("issues", "Issues", "&3 Issues"),
	Seccion("prs", "Pull requests", "&4 Pull requests"),
	Seccion("discusiones", "Discusiones", "&5 Discusiones"),
	Seccion("acciones", "Actions", "&6 Actions"),
	Seccion("releases", "Releases", "&7 Releases"),
	Seccion("ramas", "Ramas", "&8 Ramas"),
	Seccion("etiquetas", "Etiquetas git (tags)", "&9 Etiquetas git (tags)"),
	Seccion("commits", "Commits", "&Commits"),
	Seccion("proyectos", "Proyectos", "&Proyectos"),
	Seccion("wiki", "Wiki", "Wi&ki"),
	Seccion("hitos", "Hitos", "&Hitos"),
	Seccion("labels", "Etiquetas de issues (labels)", "Eti&quetas de issues (labels)"),
	Seccion("colaboradores", "Colaboradores", "C&olaboradores"),
	Seccion("bifurcaciones", "Bifurcaciones", "&Bifurcaciones"),
	Seccion("observadores", "Estrellas (quién le dio estrella)", "Es&trellas (quién le dio estrella)"),
	Seccion("seguridad", "Seguridad", "S&eguridad"),
	Seccion("entornos", "Entornos", "E&ntornos"),
	Seccion("secretos", "Secretos y variables", "Secretos y &variables"),
	Seccion("webhooks", "Webhooks", "&Webhooks"),
	Seccion("claves", "Claves de despliegue", "C&laves de despliegue"),
	Seccion("reglas", "Reglas y protección", "Re&glas y protección"),
	Seccion("estadisticas", "Estadísticas", "Esta&dísticas"),
	Seccion("despliegues", "Despliegues", "Desplieg&ues"),
	Seccion("pages", "Pages", "P&ages"),
]
IDS = [s.id for s in SECCIONES]
TITULOS = {s.id: s.titulo for s in SECCIONES}

#: Ventanas abiertas por nombre de repositorio (en minúsculas: GitHub no distingue).
_VENTANAS: dict[str, VentanaRepositorio] = {}


def titulo_ventana(nombre: str) -> str:
	return _("{n} — GitHub Accesible").format(n=nombre)


class VentanaRepositorio(wx.Frame):
	"""Ventana con todas las secciones de un repositorio."""

	def __init__(self, ctx: Any, nombre: str, seccion: str = "resumen") -> None:
		padre = ctx.ventana_principal if isinstance(ctx.ventana_principal, wx.Window) else None
		super().__init__(padre, title=titulo_ventana(nombre), size=(1100, 720))
		self.ctx = ctx
		self.nombre = nombre
		self.info: dict = {}
		self.paginas: dict[str, wx.Window] = {}
		self.actual = ""
		self._ids_acciones: list[int] = []
		self._temporizador: wx.CallLater | None = None
		self._crear_contenido()
		self._crear_menus()
		self.CreateStatusBar()
		self.SetStatusText(_("Cargando el repositorio…"))
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.Bind(wx.EVT_MENU_OPEN, self._al_abrir_menu)
		self.mostrar_seccion(seccion or "resumen", enfocar=False)
		self.cargar_info()

	# ── Construcción ─────────────────────────────────────────────────────────

	def _crear_contenido(self) -> None:
		self.panel = wx.Panel(self)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		columna = wx.BoxSizer(wx.VERTICAL)
		# Etiqueta ANTES de la lista: el lector la anuncia como su nombre.
		columna.Add(wx.StaticText(self.panel, label=_("&Secciones:")), 0, wx.ALL, 4)
		self.lista_secciones = wx.ListBox(self.panel, choices=[_(s.titulo) for s in SECCIONES], style=wx.LB_SINGLE)
		self.lista_secciones.SetHelpText(_(
			"Secciones del repositorio. Las flechas cambian de sección; Intro o F6 van a su contenido. "
			"Control+Tabulador pasa a la sección siguiente desde cualquier sitio."))
		self.lista_secciones.Bind(wx.EVT_LISTBOX, self._al_elegir_seccion)
		self.lista_secciones.Bind(wx.EVT_KEY_DOWN, self._al_pulsar_secciones)
		columna.Add(self.lista_secciones, 1, wx.EXPAND | wx.ALL, 4)
		fila.Add(columna, 0, wx.EXPAND)
		self.libro = wx.Simplebook(self.panel)
		fila.Add(self.libro, 1, wx.EXPAND)
		self.panel.SetSizer(fila)

	def _elemento(self, menu: wx.Menu, etiqueta: str, funcion: Any, ayuda: str = "") -> wx.MenuItem:
		item = menu.Append(wx.ID_ANY, etiqueta, ayuda)
		self.Bind(wx.EVT_MENU, lambda _e: funcion(), item)
		return item

	def _crear_menus(self) -> None:
		barra = wx.MenuBar()
		menu = wx.Menu()
		self._elemento(menu, _("&Actualizar\tF5"), self.actualizar, _("Vuelve a cargar el repositorio y la sección visible."))
		self._elemento(menu, _("Abrir en el &navegador"), self.abrir_navegador, _("Abre la página del repositorio en GitHub."))
		self._elemento(menu, _("Copiar la &URL de clonado"), self.copiar_url_clonado, _("Copia la dirección https para git clone."))
		self._elemento(menu, _("C&lonar…"), self.clonar, _("Descarga el repositorio a una carpeta del equipo con git."))
		self._elemento(menu, _("Descargar el código en &zip…"), self.descargar_zip,
			_("Guarda el código de la rama principal en un archivo zip, sin necesidad de git."))
		menu.AppendSeparator()
		self._elemento(menu, _("Poner o quitar la &estrella"), self.estrella, _("Marca el repositorio como favorito, o lo desmarca."))
		self._elemento(menu, _("&Vigilar…"), self.vigilar, _("Elige qué avisos recibir de este repositorio."))
		self._elemento(menu, _("&Bifurcar (fork)"), self.bifurcar, _("Crea una copia del repositorio en su cuenta."))
		self.item_original = self._elemento(menu, _("Abrir el repositorio &original"), self.abrir_original,
			_("Solo en una bifurcación: abre el repositorio del que se copió."))
		self.item_sincronizar = self._elemento(menu, _("&Sincronizar con el original…"), self.sincronizar_bifurcacion,
			_("Solo en una bifurcación: trae a una rama suya los cambios nuevos del repositorio original."))
		self._elemento(menu, _("Ver el &propietario\tCtrl+Shift+P"), self.ver_propietario,
			_("Abre el perfil de la persona u organización dueña del repositorio: sus repositorios y el botón Seguir."))
		self._elemento(menu, _("Con&figuración…"), self.configuracion, _("Nombre, visibilidad, fusiones, archivar, borrar…"))
		menu.AppendSeparator()
		self._elemento(menu, _("&Cerrar\tCtrl+W"), self.Close, _("Cierra la ventana del repositorio."))
		barra.Append(menu, _("&Repositorio"))

		self.menu_acciones = wx.Menu()
		barra.Append(self.menu_acciones, _("Ac&ciones"))

		menu_ir = wx.Menu()
		for posicion, seccion in enumerate(SECCIONES):
			etiqueta = _(seccion.menu) + (f"\tAlt+{posicion + 1}" if posicion < 9 else "")
			self._elemento(menu_ir, etiqueta, lambda s=seccion.id: self.mostrar_seccion(s), _("Va a la sección {s}.").format(
				s=_(seccion.titulo)))
		menu_ir.AppendSeparator()
		self._elemento(menu_ir, _("&Sección siguiente (Ctrl+Tab)"), lambda: self.cambiar_seccion(1))
		self._elemento(menu_ir, _("Sección ante&rior (Ctrl+Mayús+Tab)"), lambda: self.cambiar_seccion(-1))
		self._elemento(menu_ir, _("Ca&mbiar entre secciones y contenido (F6)"), self.alternar_foco)
		barra.Append(menu_ir, _("&Ir"))
		self.SetMenuBar(barra)
		self.reconstruir_menu_acciones()
		self._habilitar_bifurcacion()

	# ── Secciones ─────────────────────────────────────────────────────────────

	def panel_actual(self) -> wx.Window | None:
		return self.paginas.get(self.actual)

	def _datos_base(self) -> dict:
		return {"nombre": self.nombre, "info": self.info, "ir": self._ir}

	def _ir(self, seccion: str, datos: dict | None = None) -> None:
		self.mostrar_seccion(seccion, enfocar=True, datos=datos)

	def _crear_panel(self, ident: str, datos: dict | None) -> wx.Window:
		base = self._datos_base()
		base.update(datos or {})
		if ident in PANELES:
			panel = PANELES[ident](self.libro, self.ctx, base)
		else:
			definicion = VISTAS[ident](self.nombre, self.ctx.host)
			panel = PanelLista(self.libro, self.ctx, definicion, base, etiqueta=etiqueta_con_letra(definicion.titulo + ":"))
			rotular(panel)
		self.libro.AddPage(panel, _(TITULOS[ident]))
		self.paginas[ident] = panel
		return panel

	def mostrar_seccion(self, seccion: str, enfocar: bool = True, datos: dict | None = None) -> None:
		"""Muestra una sección (creándola si hace falta). ``datos`` cambia sus filtros y recarga."""
		if seccion == "configuracion":
			wx.CallAfter(self.configuracion)
			seccion = self.actual or "resumen"
		if seccion not in IDS:
			if seccion:
				log.warning("Sección desconocida «%s»; se muestra el resumen.", seccion)
			seccion = "resumen"
		# Recorrer las secciones no mueve el foco: la persona entra con Tab, Intro o F6.
		en_secciones = wx.Window.FindFocus() is self.lista_secciones
		panel = self.paginas.get(seccion)
		if panel is None:
			panel = self._crear_panel(seccion, datos)
		elif datos:
			cambiado = any(panel.datos.get(clave) != valor for clave, valor in datos.items())
			panel.datos.update(datos)
			if cambiado:
				if isinstance(panel, PanelLista):
					panel.filtro = ""
					rotular(panel)
				panel.cargar()
		self.libro.ChangeSelection(self.libro.FindPage(panel))
		self.actual = seccion
		indice = IDS.index(seccion)
		if self.lista_secciones.GetSelection() != indice:
			self.lista_secciones.SetSelection(indice)
		panel.cargar_si_hace_falta()
		self.reconstruir_menu_acciones()
		if enfocar:
			self.enfocar_contenido()
		elif en_secciones and wx.Window.FindFocus() is not self.lista_secciones:
			self.lista_secciones.SetFocus()

	def control_contenido(self) -> wx.Window | None:
		panel = self.panel_actual()
		if panel is None:
			return None
		if isinstance(panel, PanelLista):
			return panel.lista
		return panel.control_foco()

	def enfocar_contenido(self) -> None:
		if not self:
			return
		control = self.control_contenido()
		if control is None:
			return
		control.SetFocus()
		if isinstance(control, wx.ListCtrl) and control.GetItemCount() and control.GetFocusedItem() < 0:
			control.Focus(0)
			control.Select(0)

	def alternar_foco(self) -> None:
		"""F6: de la lista de secciones al contenido y viceversa."""
		if wx.Window.FindFocus() is self.lista_secciones:
			self.enfocar_contenido()
		else:
			self.lista_secciones.SetFocus()

	def cambiar_seccion(self, paso: int) -> None:
		posicion = (IDS.index(self.actual or "resumen") + paso) % len(IDS)
		en_lista = wx.Window.FindFocus() is self.lista_secciones
		self.mostrar_seccion(IDS[posicion], enfocar=not en_lista)
		self.ctx.avisar(_(TITULOS[IDS[posicion]]))

	def _al_elegir_seccion(self, evento: wx.CommandEvent) -> None:
		# Se espera un momento: al recorrer la lista con las flechas no se carga cada sección por la que se pasa.
		if self._temporizador is not None and self._temporizador.IsRunning():
			self._temporizador.Stop()
		self._temporizador = wx.CallLater(350, self._mostrar_elegida)
		evento.Skip()

	def _mostrar_elegida(self) -> None:
		if not self:
			return
		indice = self.lista_secciones.GetSelection()
		if 0 <= indice < len(IDS) and IDS[indice] != self.actual:
			self.mostrar_seccion(IDS[indice], enfocar=False)

	def _al_pulsar_secciones(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not evento.HasAnyModifiers():
			indice = self.lista_secciones.GetSelection()
			if 0 <= indice < len(IDS):
				self.mostrar_seccion(IDS[indice], enfocar=True)
			return
		evento.Skip()

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla, modificadores = evento.GetKeyCode(), evento.GetModifiers()
		if tecla == wx.WXK_F6 and modificadores == wx.MOD_NONE:
			self.alternar_foco()
			return
		if tecla == wx.WXK_TAB and modificadores in (wx.MOD_CONTROL, wx.MOD_CONTROL | wx.MOD_SHIFT):
			self.cambiar_seccion(-1 if modificadores & wx.MOD_SHIFT else 1)
			return
		# Escape no hace nada aquí a propósito: esta ventana solo se cierra con Ctrl+W o el menú.
		evento.Skip()

	# ── Menú «Acciones» ──────────────────────────────────────────────────────

	def reconstruir_menu_acciones(self) -> None:
		"""Rellena «Acciones» con las de la sección visible (etiqueta «Acción (Atajo)», sin tabulador)."""
		menu = self.menu_acciones
		for identificador in self._ids_acciones:
			self.Unbind(wx.EVT_MENU, id=identificador)
		self._ids_acciones = []
		for item in list(menu.GetMenuItems()):
			menu.Delete(item)
		panel = self.panel_actual()
		acciones = panel.acciones_disponibles() if panel is not None else []
		if not acciones:
			item = menu.Append(wx.ID_ANY, _("(&Sin acciones)"))
			item.Enable(False)
			return
		primero = True
		for accion in acciones:
			if accion.separador_antes and not primero:
				menu.AppendSeparator()
			etiqueta = accion.etiqueta + (f" ({accion.atajo})" if accion.atajo else "")
			item = menu.Append(wx.ID_ANY, etiqueta, accion.ayuda)
			self.Bind(wx.EVT_MENU, lambda _e, a=accion, p=panel: wx.CallAfter(p.ejecutar, a), item)
			self._ids_acciones.append(item.GetId())
			primero = False

	def _al_abrir_menu(self, evento: wx.MenuEvent) -> None:
		if evento.GetMenu() is self.menu_acciones:
			self.reconstruir_menu_acciones()
		evento.Skip()

	# ── Datos del repositorio ─────────────────────────────────────────────────

	def cargar_info(self) -> None:
		api = self.ctx.api()
		nombre = self.nombre

		def al_terminar(repo: Any) -> None:
			if self and isinstance(repo, dict):
				self.aplicar_info(repo)

		def al_fallar(error: BaseException) -> None:
			if not self:
				return
			mensaje = mensaje_error(error)
			self.SetStatusText(_("No se pudo cargar el repositorio: {m}").format(m=mensaje))
			self.ctx.sonar("error")
			self.ctx.avisar(_("No se pudo cargar {n}: {m}").format(n=nombre, m=mensaje))

		self.ctx.tareas.enviar(lambda tarea: api.repositorio(nombre), al_terminar=al_terminar, al_fallar=al_fallar,
			nombre=f"repositorio:{nombre}", duplicadas="permitir")

	def aplicar_info(self, repo: dict) -> None:
		self.info = repo
		self._habilitar_bifurcacion()
		self.SetTitle(titulo_ventana(repo.get("full_name") or self.nombre))
		self.SetStatusText(self.texto_estado())
		for panel in self.paginas.values():
			panel.datos["info"] = repo
			if isinstance(panel, PanelLista):
				rotular(panel)

	def texto_estado(self) -> str:
		r = self.info
		from app.services import formato as f

		partes = [
			_("Rama por defecto: {r}").format(r=r.get("default_branch") or "-"),
			f.estado(r.get("visibility") or ("private" if r.get("private") else "public")),
			_("{n} estrellas").format(n=f.numero(r.get("stargazers_count") or 0)),
		]
		if r.get("archived"):
			partes.append(_("archivado (solo lectura)"))
		if r.get("fork") and r.get("parent"):
			partes.append(_("bifurcación de {p}").format(p=r["parent"].get("full_name", "")))
		return ". ".join(partes) + "."

	# ── Menú «Repositorio» ───────────────────────────────────────────────────

	def actualizar(self) -> None:
		self.cargar_info()
		panel = self.panel_actual()
		if panel is not None:
			panel.cargar()

	def url_web(self) -> str:
		return self.info.get("html_url") or f"https://{self.ctx.host}/{self.nombre}"

	def url_clonado(self) -> str:
		return self.info.get("clone_url") or f"https://{self.ctx.host}/{self.nombre}.git"

	def abrir_navegador(self) -> None:
		webbrowser.open(self.url_web())

	def copiar_url_clonado(self) -> None:
		copiar(self.ctx, self.url_clonado(), _("Copiada: {u}").format(u=self.url_clonado()))

	def clonar(self) -> None:
		try:
			from app.ui.git.clonar import dialogo_clonar
		except ImportError:
			log.warning("El diálogo de clonar no está disponible", exc_info=True)
			mostrar_error(self, _("La función de clonar todavía no está disponible en esta versión. "
				"Puede copiar la URL de clonado desde el menú Repositorio."), _("Clonar"))
			return
		dialogo_clonar(self, self.ctx, self.url_clonado(), self.nombre)

	def estrella(self) -> None:
		api = self.ctx.api()
		nombre = self.nombre

		def trabajo() -> bool:
			if api.tiene_estrella(nombre):
				api.quitar_estrella(nombre)
				return False
			api.dar_estrella(nombre)
			return True

		en_segundo_plano(self, self.ctx, trabajo, sonido="estrella",
			exito=lambda puesta: (_("Estrella puesta a {n}.") if puesta else _("Estrella quitada a {n}.")).format(n=nombre),
			al_terminar=lambda _r: self.cargar_info() if self else None)

	def original(self) -> str:
		"""«dueño/repo» del repositorio original si este es una bifurcación (si no, «»)."""
		if not self.info.get("fork"):
			return ""
		return str((self.info.get("parent") or {}).get("full_name") or "")

	def _habilitar_bifurcacion(self) -> None:
		# Desactivadas (no ocultas) cuando no procede: el lector dice «no disponible» y se entiende por qué.
		hay = bool(self.original())
		for item in (getattr(self, "item_original", None), getattr(self, "item_sincronizar", None)):
			if item is not None:
				item.Enable(hay)

	def abrir_original(self) -> None:
		if not self.original():
			self.ctx.avisar(_("Este repositorio no es una bifurcación."))
			return
		abrir_ventana_repositorio(self.ctx, self.original())

	def sincronizar_bifurcacion(self) -> None:
		"""«Sync fork» de la web: GitHub fusiona en la rama elegida lo nuevo de la misma rama del original."""
		if not self.original():
			self.ctx.avisar(_("Este repositorio no es una bifurcación."))
			return
		from app.ui.comunes import pedir_texto

		rama = pedir_texto(self, _("&Rama que quiere poner al día:"), _("Sincronizar con el original"),
			self.info.get("default_branch") or "main")
		if not rama or not rama.strip():
			return
		rama = rama.strip()
		api = self.ctx.api()

		def explicar(resultado: Any) -> str:
			datos = resultado if isinstance(resultado, dict) else {}
			tipo = datos.get("merge_type", "")
			if tipo == "none":
				return _("La rama {r} ya estaba al día con {o}.").format(r=rama, o=self.original())
			if tipo == "fast-forward":
				return _("Rama {r} puesta al día con {o} (avance rápido).").format(r=rama, o=self.original())
			return datos.get("message") or _("Rama {r} sincronizada con {o}.").format(r=rama, o=self.original())

		en_segundo_plano(self, self.ctx, lambda: api.sincronizar_bifurcacion(self.nombre, rama), exito=explicar,
			inicio=_("Sincronizando con el original…"), al_terminar=lambda _r: self.actualizar() if self else None)

	def descargar_zip(self) -> None:
		from app.ui.descarga_codigo import descargar_codigo

		descargar_codigo(self, self.ctx, self.nombre, self.info.get("default_branch", "") or "")

	def propietario(self) -> str:
		"""Dueño del repositorio: el de GitHub si ya llegó la información, si no el del nombre."""
		return (self.info.get("owner") or {}).get("login") or self.nombre.partition("/")[0]

	def ver_propietario(self) -> None:
		from app.ui import abrir

		abrir.usuario(self.ctx, self, self.propietario())

	def vigilar(self) -> None:
		from app.ui.repositorio.dialogos import dialogo_vigilancia

		dialogo_vigilancia(self, self.ctx, self.nombre)

	def bifurcar(self) -> None:
		if confirmar(self, _("¿Crear una bifurcación (fork) de {n} en su cuenta?").format(n=self.nombre), _("Bifurcar")) != wx.ID_YES:
			return
		api = self.ctx.api()
		en_segundo_plano(self, self.ctx, lambda: api.bifurcar(self.nombre), inicio=_("Creando la bifurcación…"),
			exito=lambda r: _("Bifurcación creada: {n}. GitHub puede tardar unos segundos en tenerla lista.").format(
				n=(r or {}).get("full_name", "") if isinstance(r, dict) else ""))

	def configuracion(self) -> None:
		if not self:
			return
		from app.ui.repositorio.dialogos import dialogo_configuracion

		dialogo_configuracion(self, self.ctx, self.nombre, al_guardar=self._al_guardar_configuracion,
			al_desaparecer=self._al_desaparecer)

	def _al_guardar_configuracion(self, repo: dict) -> None:
		if not self or not isinstance(repo, dict):
			return
		nuevo = repo.get("full_name") or self.nombre
		if nuevo.casefold() != self.nombre.casefold():
			# Cambió el nombre: se abre la ventana con el nombre nuevo en la misma sección.
			seccion = self.actual
			self.Close()
			abrir_ventana_repositorio(self.ctx, nuevo, seccion)
			return
		self.aplicar_info(repo)
		resumen = self.paginas.get("resumen")
		if resumen is not None:
			resumen.cargar(anunciar=False)

	def _al_desaparecer(self, motivo: str) -> None:
		self.ctx.avisar(_("El repositorio se ha {m}. Se cierra su ventana.").format(m=motivo), interrumpir=False)
		if self:
			wx.CallAfter(self.Close)

	# ── Mostrar y cerrar ─────────────────────────────────────────────────────

	def traer_al_frente(self) -> None:
		if self.IsIconized():
			self.Iconize(False)
		self.Show()
		self.Raise()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if self._temporizador is not None and self._temporizador.IsRunning():
			self._temporizador.Stop()
		clave = self.nombre.casefold()
		if _VENTANAS.get(clave) is self:
			del _VENTANAS[clave]
		self.ctx.sonar("cerrar")
		evento.Skip()


def abrir_ventana_repositorio(ctx: Any, nombre: str, seccion: str = "") -> VentanaRepositorio | None:
	"""Abre la ventana de un repositorio, o trae al frente la que ya esté abierta y cambia de sección.

	:param nombre: «dueño/repo».
	:param seccion: identificador de ``SECCIONES`` o «configuracion» (abre su diálogo).
	"""
	nombre = (nombre or "").strip().strip("/")
	if nombre.endswith(".git"):
		nombre = nombre[:-4]
	if nombre.count("/") != 1:
		mostrar_error(ctx.ventana_principal if isinstance(ctx.ventana_principal, wx.Window) else None,
			_("El repositorio debe tener la forma «dueño/nombre»: {n}").format(n=nombre), _("Abrir repositorio"))
		return None
	clave = nombre.casefold()
	ventana = _VENTANAS.get(clave)
	if ventana is not None and not ventana:
		del _VENTANAS[clave]  # se destruyó sin pasar por el cierre normal
		ventana = None
	if ventana is not None:
		ventana.traer_al_frente()
		if seccion:
			ventana.mostrar_seccion(seccion, enfocar=True)
		else:
			wx.CallAfter(ventana.enfocar_contenido)
		return ventana
	ventana = VentanaRepositorio(ctx, nombre, seccion or "resumen")
	_VENTANAS[clave] = ventana
	ventana.Show()
	ventana.Raise()
	ctx.sonar("abrir")
	wx.CallAfter(ventana.enfocar_contenido)
	return ventana


def ventanas_abiertas() -> list[VentanaRepositorio]:
	"""Ventanas de repositorio vivas (para cerrarlas al salir o para las pruebas)."""
	return [v for v in _VENTANAS.values() if v]
