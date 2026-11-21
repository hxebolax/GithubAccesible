"""Ventana de un pull request: conversación, commits, archivos y diferencias, checks e hilos.

Pestañas (Ctrl+Tab y Ctrl+Mayús+Tab para cambiar):

1. Conversación: la misma lista accesible que en las issues (incluye revisiones).
2. Commits: Intro abre el commit con sus diferencias.
3. Archivos cambiados: lista de archivos (Intro salta a su diff) y visor de
   diferencias línea a línea. Intro en una línea la comenta: al momento o
   añadiéndola a la revisión pendiente. Las líneas con comentarios suenan y
   tienen la columna «Comentarios» (Ctrl+Intro los lee).
4. Checks: estado combinado y cada check; Intro abre la ejecución de Actions.
5. Hilos de revisión: resolver o reabrir, responder, ir a la línea.

Fuera de las pestañas: «Revisar» (Alt+V) y «Fusionar» (Alt+F). El menú
«Acciones» (Alt+A) tiene todo lo demás: fusión automática, listo para
revisión o borrador, pedir revisión, actualizar la rama, cerrar o reabrir,
editar, etiquetas, asignados, checkout local, navegador, F5 y Ctrl+W.
"""

from __future__ import annotations

import builtins
import logging
import re
import webbrowser
from typing import Any

import wx

from app.services import diferencias as d
from app.services import formato as f
from app.ui import abrir, editor
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.teclado import vincular_menu_contextual
from app.ui.comunes import (
	confirmar,
	copiar,
	elegir_uno,
	elegir_varios,
	en_segundo_plano,
	mensaje_error,
	mostrar_error,
	mostrar_mensaje,
)
from app.ui.detalle.conversacion import (
	PanelConversacion,
	VentanaDetalle,
	cambiar_etiqueta,
	como_dict,
	como_lista,
	crear_boton,
	crear_lista,
	crear_menu_acciones,
	crear_texto,
	ejecutar_seguro,
	enfocar,
	marca_tiempo,
)
from app.ui.detalle.diferencias import PanelDiferencias
from app.ui.detalle.issue import editar_asignados, editar_etiquetas

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def clave_pr(nombre: str, numero: int) -> str:
	return f"pr:{nombre.lower()}#{int(numero)}"


ESTADOS_ARCHIVO = {
	"added": "Añadido", "modified": "Modificado", "removed": "Eliminado", "renamed": "Renombrado",
	"copied": "Copiado", "changed": "Cambiado", "unchanged": "Sin cambios",
}

METODOS_FUSION = [
	("merge", "MERGE", "Crear un commit de &fusión (merge)"),
	("squash", "SQUASH", "&Squash: un solo commit con todos los cambios"),
	("rebase", "REBASE", "&Rebase: reaplicar los commits sobre la base"),
]

_RUN_ACTIONS = re.compile(r"/actions/runs/(\d+)")


# ════════════════════════════════════════════════════════════════════════════
# Funciones puras
# ════════════════════════════════════════════════════════════════════════════


def explicar_fusion(pr: dict) -> tuple[str, bool]:
	"""(explicación del estado de fusión, si tiene sentido intentar fusionar)."""
	if pr.get("merged"):
		return _("Este pull request ya está fusionado."), False
	if pr.get("state") == "closed":
		return _("Este pull request está cerrado. Reábralo para poder fusionarlo."), False
	if pr.get("draft"):
		return _("Es un borrador: márquelo como listo para revisión antes de fusionar."), False
	estado = pr.get("mergeable_state") or "unknown"
	if pr.get("mergeable") is False or estado == "dirty":
		return _("Hay conflictos con la rama base: hay que resolverlos antes de fusionar (por ejemplo, con un checkout local)."), False
	textos = {
		"clean": _("Se puede fusionar sin problemas."),
		"has_hooks": _("Se puede fusionar; hay ganchos de fusión configurados."),
		"unstable": _("Se puede fusionar, pero hay checks que fallan o no han terminado."),
		"behind": _("La rama está desactualizada respecto a la base. Puede actualizarla con «Actualizar la rama con la base»."),
		"blocked": _("La fusión está bloqueada por las reglas de la rama: faltan revisiones aprobadas o checks obligatorios."),
		"draft": _("Es un borrador: márquelo como listo para revisión antes de fusionar."),
	}
	if estado == "draft":
		return textos["draft"], False
	return textos.get(estado, _("GitHub todavía está comprobando si se puede fusionar. Actualice con F5 dentro de unos segundos.")), True


def comentarios_por_linea(comentarios: list[dict], pendientes: list[dict] = ()) -> dict[tuple[str, str, int], list[str]]:
	"""``{(ruta, lado, línea): [textos]}`` para ``PanelDiferencias``."""
	resultado: dict[tuple[str, str, int], list[str]] = {}
	for comentario in comentarios:
		if not isinstance(comentario, dict):
			continue
		linea = comentario.get("line") or comentario.get("original_line")
		if not linea or not comentario.get("path"):
			continue
		clave = (comentario["path"], comentario.get("side") or "RIGHT", int(linea))
		texto = f"{f.login(comentario.get('user'))} ({f.fecha_completa(comentario.get('created_at'))}): {comentario.get('body') or ''}"
		resultado.setdefault(clave, []).append(texto)
	for pendiente in pendientes:
		clave = (pendiente["path"], pendiente.get("side") or "RIGHT", int(pendiente["line"]))
		resultado.setdefault(clave, []).append(_("(pendiente, sin enviar) {t}").format(t=pendiente.get("body", "")))
	return resultado


def lineas_extra_pr(pr: dict, pendientes: int = 0) -> list[str]:
	"""Líneas de «Información» propias de un pull request."""
	base = como_dict(pr.get("base"))
	cabeza = como_dict(pr.get("head"))
	revisores = ", ".join(f.login(u) for u in pr.get("requested_reviewers") or [] if isinstance(u, dict))
	equipos = ", ".join(t.get("name", "") for t in pr.get("requested_teams") or [] if isinstance(t, dict))
	explicacion, _posible = explicar_fusion(pr)
	lineas = [
		_("Ramas: {c} hacia {b}").format(c=cabeza.get("label") or cabeza.get("ref", ""), b=base.get("ref", "")),
		_("Commits: {c}; archivos: {a}; {m} líneas añadidas y {e} eliminadas").format(
			c=pr.get("commits", 0), a=pr.get("changed_files", 0), m=pr.get("additions", 0), e=pr.get("deletions", 0)),
		_("Fusión: {e}").format(e=explicacion),
		_("Revisión pedida a: {r}").format(r=", ".join(x for x in (revisores, equipos) if x) or "-"),
	]
	if pr.get("auto_merge"):
		lineas.append(_("Fusión automática activada ({m}).").format(m=como_dict(pr.get("auto_merge")).get("merge_method", "")))
	if pr.get("merged_at"):
		lineas.append(_("Fusionado por {u} el {f}").format(u=f.login(pr.get("merged_by")), f=f.fecha_completa(pr.get("merged_at"))))
	if pendientes:
		lineas.append(_("Comentarios en línea pendientes de enviar: {n}").format(n=pendientes))
	return lineas


def remoto_coincide(url: str, nombre: str) -> bool:
	"""Si la URL de un remoto de git apunta a «dueño/repo» (HTTPS o SSH)."""
	limpia = url.strip().removesuffix("/").removesuffix(".git").lower()
	return limpia.endswith("/" + nombre.lower()) or limpia.endswith(":" + nombre.lower())


# ════════════════════════════════════════════════════════════════════════════
# Diálogos
# ════════════════════════════════════════════════════════════════════════════


class DialogoRevision(wx.Dialog):
	"""Enviar una revisión: Comentar, Aprobar o Pedir cambios, con los comentarios pendientes."""

	EVENTOS = [("COMMENT", "C&omentar"), ("APPROVE", "&Aprobar"), ("REQUEST_CHANGES", "Pedir ca&mbios")]

	def __init__(self, padre: wx.Window | None, pendientes: list[dict]) -> None:
		super().__init__(padre, title=_("Enviar la revisión"), size=(640, 520), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.tipo = wx.RadioBox(self, label=_("Tipo de revisión"), choices=[_(t) for _e, t in self.EVENTOS], majorDimension=1,
			style=wx.RA_SPECIFY_COLS)
		self.tipo.SetHelpText(_("Comentar no aprueba ni bloquea; Aprobar da el visto bueno; Pedir cambios bloquea la fusión."))
		raiz.Add(self.tipo, 0, wx.EXPAND | wx.ALL, 6)
		self.cuerpo = crear_texto(self, _("&Texto de la revisión:"), raiz, alto=150, proporcion=1, editable=True,
			ayuda=_("Comentario general de la revisión en Markdown. Obligatorio al pedir cambios."))
		resumen = "\n\n".join(f"{p['path']}, " + _("línea {n}").format(n=p["line"]) + f": {p['body']}" for p in pendientes)
		self.pendientes = crear_texto(self, _("Comentarios en &línea pendientes:"), raiz,
			resumen or _("No hay comentarios en línea pendientes."), alto=110,
			ayuda=_("Comentarios en líneas que se publicarán junto con esta revisión."))
		raiz.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		self.FindWindow(wx.ID_OK).SetLabel(_("&Enviar la revisión"))
		self.SetSizer(raiz)
		preparar_dialogo(self, foco_inicial=self.tipo)
		self.CentreOnParent()

	def valores(self) -> tuple[str, str]:
		return self.EVENTOS[max(0, self.tipo.GetSelection())][0], self.cuerpo.GetValue()


class DialogoFusion(wx.Dialog):
	"""Método (merge, squash, rebase), título y mensaje del commit, borrar la rama."""

	def __init__(self, padre: wx.Window | None, pr: dict, puede_borrar_rama: bool) -> None:
		super().__init__(padre, title=_("Fusionar el pull request #{n}").format(n=pr.get("number", "")), size=(640, 560),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.pr = pr
		raiz = wx.BoxSizer(wx.VERTICAL)
		explicacion, _posible = explicar_fusion(pr)
		self.estado = crear_texto(self, _("&Estado de la fusión:"), raiz, explicacion, alto=60)
		self.metodo = wx.RadioBox(self, label=_("Método de fusión"), choices=[_(t) for _m, _g, t in METODOS_FUSION],
			majorDimension=1, style=wx.RA_SPECIFY_COLS)
		self.metodo.SetHelpText(_("Merge conserva los commits y añade uno de fusión; squash los junta en uno; rebase los reaplica."))
		self.metodo.Bind(wx.EVT_RADIOBOX, self._al_cambiar_metodo)
		raiz.Add(self.metodo, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Título del commit:")), 0, wx.LEFT | wx.TOP, 6)
		self._titulo_defecto = self._titulo_para("merge")
		self.titulo = wx.TextCtrl(self, value=self._titulo_defecto)
		self.titulo.SetHelpText(_("Primera línea del commit de fusión (no se usa con rebase)."))
		raiz.Add(self.titulo, 0, wx.EXPAND | wx.ALL, 6)
		self.mensaje = crear_texto(self, _("Me&nsaje del commit:"), raiz, "", alto=110,
			proporcion=1, editable=True, ayuda=_("Descripción del commit de fusión (opcional)."))
		self.borrar_rama = wx.CheckBox(self, label=_("&Borrar la rama al terminar"))
		self.borrar_rama.SetHelpText(_("Borra la rama del pull request después de fusionar (solo si está en este repositorio)."))
		self.borrar_rama.Enable(puede_borrar_rama)
		raiz.Add(self.borrar_rama, 0, wx.ALL, 6)
		raiz.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		self.FindWindow(wx.ID_OK).SetLabel(_("F&usionar"))
		self.SetSizer(raiz)
		preparar_dialogo(self, foco_inicial=self.estado)
		self.CentreOnParent()

	def _titulo_para(self, metodo: str) -> str:
		numero = self.pr.get("number", "")
		if metodo == "squash":
			return f"{self.pr.get('title', '')} (#{numero})"
		cabeza = como_dict(self.pr.get("head")).get("label") or como_dict(self.pr.get("head")).get("ref", "")
		return f"Merge pull request #{numero} from {cabeza}"

	def _al_cambiar_metodo(self, _evento: wx.CommandEvent) -> None:
		metodo = METODOS_FUSION[self.metodo.GetSelection()][0]
		if self.titulo.GetValue() == self._titulo_defecto:
			self._titulo_defecto = self._titulo_para(metodo)
			self.titulo.SetValue(self._titulo_defecto)
		self.titulo.Enable(metodo != "rebase")
		self.mensaje.Enable(metodo != "rebase")

	def valores(self) -> dict:
		metodo = METODOS_FUSION[max(0, self.metodo.GetSelection())][0]
		return {"metodo": metodo, "titulo": self.titulo.GetValue().strip(), "mensaje": self.mensaje.GetValue(),
			"borrar_rama": self.borrar_rama.IsEnabled() and self.borrar_rama.GetValue()}


# ════════════════════════════════════════════════════════════════════════════
# Ventana
# ════════════════════════════════════════════════════════════════════════════


PAGINA_CONVERSACION, PAGINA_COMMITS, PAGINA_ARCHIVOS, PAGINA_CHECKS, PAGINA_HILOS = range(5)


class VentanaPullRequest(VentanaDetalle):
	def __init__(self, padre: wx.Window | None, contexto: Any, nombre: str, numero: int) -> None:
		super().__init__(padre, contexto, clave_pr(nombre, numero), _("Pull request #{n} de {r}").format(n=numero, r=nombre),
			(1100, 780))
		self.nombre = nombre
		self.numero = int(numero)
		self.pr: dict = {}
		self.pendientes: list[dict] = []
		self.comentarios_linea: list[dict] = []
		self.commits: list[dict] = []
		self.archivos: list[dict] = []
		self.checks: list[dict] = []
		self.hilos: list[dict] = []
		self.cargadas: set[int] = set()
		self._crear_menu()
		raiz_panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.libro = wx.Notebook(raiz_panel)
		self.libro.SetHelpText(_("Pestañas del pull request. Control+Tabulador pasa a la siguiente."))
		self.conversacion = PanelConversacion(self.libro, contexto, nombre, numero, al_cargar=self._al_cargar_conversacion)
		self.libro.AddPage(self.conversacion, _("Conversación"))
		self.libro.AddPage(self._crear_commits(), _("Commits"))
		self.libro.AddPage(self._crear_archivos(), _("Archivos cambiados"))
		self.libro.AddPage(self._crear_checks(), _("Checks"))
		self.libro.AddPage(self._crear_hilos(), _("Hilos de revisión"))
		self.libro.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._al_cambiar_pagina)
		raiz.Add(self.libro, 1, wx.EXPAND | wx.ALL, 2)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		crear_boton(raiz_panel, _("Re&visar…"), self.revisar,
			_("Envía una revisión: comentar, aprobar o pedir cambios, con los comentarios en línea pendientes."), botones)
		crear_boton(raiz_panel, _("&Fusionar…"), self.fusionar, _("Fusiona el pull request (merge, squash o rebase)."), botones)
		raiz.Add(botones, 0, wx.ALL, 2)
		raiz_panel.SetSizer(raiz)
		self._actualizar_menu()

	# ── Construcción ──────────────────────────────────────────────────────────

	def _crear_menu(self) -> None:
		self.menu = crear_menu_acciones(self, _("&Acciones"), [
			("revisar", _("Re&visar…\tCtrl+Shift+R"), self.revisar),
			("descartar", _("&Descartar los comentarios pendientes"), self.descartar_pendientes),
			("fusionar", _("&Fusionar…\tCtrl+Shift+F"), self.fusionar),
			("auto", _("Activar la fusión a&utomática…"), self.fusion_automatica),
			("listo", _("Marcar como &listo para revisión"), self.cambiar_borrador),
			("pedir", _("&Pedir revisión…"), self.pedir_revision),
			("actualizar_rama", _("Actualizar la rama con la &base"), self.actualizar_rama),
			("estado", _("&Cerrar el pull request"), self.cerrar_o_reabrir),
			None,
			("editar", _("&Editar el título y la descripción…\tCtrl+Shift+E"), self.editar),
			("etiquetas", _("E&tiquetas…\tCtrl+Shift+L"), self.etiquetas),
			("asignados", _("&Asignados…\tCtrl+Shift+A"), self.asignados),
			("checkout", _("Hacer chec&kout local…"), self.checkout_local),
			None,
			("navegador", _("Abrir en el nave&gador\tCtrl+Shift+B"), self.abrir_navegador),
			("enlace", _("C&opiar el enlace\tCtrl+Shift+C"), self.copiar_enlace),
			("actualizar", _("Actuali&zar\tF5"), self.cargar),
			("cerrar_ventana", _("Cerrar la ve&ntana\tCtrl+W"), self.Close),
		])

	def _crear_commits(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.lista_commits = crear_lista(pagina, self.ctx, _("&Commits:"),
			[(_("Commit"), 80), (_("Mensaje"), 480), (_("Autor"), 140), (_("Fecha"), 130)], sizer,
			ayuda=_("Commits del pull request. Intro abre el commit con sus diferencias."))
		self.lista_commits.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: ejecutar_seguro(self, self.abrir_commit))
		self.estado_commits = wx.StaticText(pagina, label="")
		sizer.Add(self.estado_commits, 0, wx.ALL, 4)
		pagina.SetSizer(sizer)
		return pagina

	def _crear_archivos(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.lista_archivos = crear_lista(pagina, self.ctx, _("Arc&hivos cambiados:"),
			[(_("Archivo"), 420), (_("Estado"), 110), (_("Añadidas"), 80), (_("Eliminadas"), 80)], sizer, proporcion=0,
			ayuda=_("Archivos del pull request. Intro salta a sus diferencias."))
		self.lista_archivos.SetMinSize((-1, self.FromDIP(150)))
		self.lista_archivos.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: ejecutar_seguro(self, self.ir_al_diff_del_archivo))
		self.diferencias = PanelDiferencias(pagina, self.ctx, _("&Diferencias:"), al_comentar=self.comentar_linea)
		sizer.Add(self.diferencias, 1, wx.EXPAND)
		pagina.SetSizer(sizer)
		return pagina

	def _crear_checks(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.resumen_checks = crear_texto(pagina, _("&Resumen de los checks:"), sizer, alto=60)
		self.lista_checks = crear_lista(pagina, self.ctx, _("C&hecks:"),
			[(_("Nombre"), 280), (_("Estado"), 120), (_("Origen"), 140), (_("Duración"), 100), (_("Detalle"), 300)], sizer,
			ayuda=_("Checks del último commit. Intro abre la ejecución de Actions o los detalles en el navegador."))
		self.lista_checks.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: ejecutar_seguro(self, self.abrir_check))
		botones = wx.BoxSizer(wx.HORIZONTAL)
		crear_boton(pagina, _("Abrir los &detalles"), self.abrir_check, _("Abre la ejecución de Actions o la página del check."), botones)
		crear_boton(pagina, _("Volver a &pedir el check"), self.volver_a_pedir_check, _("Pide a GitHub que vuelva a ejecutar el check."), botones)
		sizer.Add(botones, 0, wx.ALL, 2)
		pagina.SetSizer(sizer)
		return pagina

	def _crear_hilos(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.lista_hilos = crear_lista(pagina, self.ctx, _("&Hilos de revisión:"),
			[(_("Archivo"), 260), (_("Línea"), 60), (_("Estado"), 160), (_("Comentarios"), 90), (_("Primer comentario"), 380)], sizer,
			ayuda=_("Conversaciones sobre líneas de código. Intro responde; los botones resuelven o llevan a la línea."))
		self.lista_hilos.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda e: (e.Skip(), self._mostrar_hilo()))
		self.lista_hilos.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: ejecutar_seguro(self, self.responder_hilo))
		vincular_menu_contextual(self.lista_hilos, self._menu_hilos)
		self.texto_hilo = crear_texto(pagina, _("C&omentarios del hilo:"), sizer, alto=150, proporcion=1)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		crear_boton(pagina, _("&Resolver o reabrir"), self.resolver_hilo, _("Marca el hilo como resuelto, o lo reabre si ya lo estaba."), botones)
		crear_boton(pagina, _("Res&ponder…"), self.responder_hilo, _("Responde en el hilo elegido."), botones)
		crear_boton(pagina, _("Ir a la &línea en las diferencias"), self.ir_a_linea_hilo, _("Muestra la línea comentada en la pestaña Archivos cambiados."), botones)
		sizer.Add(botones, 0, wx.ALL, 2)
		pagina.SetSizer(sizer)
		return pagina

	def _menu_hilos(self) -> wx.Menu:
		menu = wx.Menu()
		for etiqueta, funcion in ((_("&Resolver o reabrir"), self.resolver_hilo), (_("Res&ponder…\tIntro"), self.responder_hilo),
			(_("Ir a la &línea en las diferencias"), self.ir_a_linea_hilo)):
			item = menu.Append(wx.ID_ANY, etiqueta)
			self.Bind(wx.EVT_MENU, lambda _e, fn=funcion: ejecutar_seguro(self, fn), item)
		return menu

	# ── Carga ─────────────────────────────────────────────────────────────────

	def enfocar_inicio(self) -> None:
		self.conversacion.lista.SetFocus()

	def cargar(self) -> None:
		"""Pide el PR y la conversación; las demás pestañas se recargan al visitarlas."""
		self.cargadas.clear()
		self.conversacion.cargar()
		self._cargar_pr(al_terminar=lambda: self._cargar_pagina(self.libro.GetSelection()))

	def _cargar_pr(self, al_terminar=None) -> None:
		api = self.ctx.api()

		def recibido(pr: Any) -> None:
			if not self:
				return
			self.pr = como_dict(pr)
			self.SetTitle(_("Pull request #{n}: {t} — {r}").format(n=self.numero, t=self.pr.get("title", ""), r=self.nombre))
			self._actualizar_menu()
			self.conversacion.establecer_extra(lineas_extra_pr(self.pr, len(self.pendientes)))
			if al_terminar:
				al_terminar()

		en_segundo_plano(self, self.ctx, lambda: api.pr(self.nombre, self.numero), sonido="", al_terminar=recibido,
			al_fallar=lambda e: self and self.ctx.avisar(_("No se pudo cargar el pull request: {m}").format(m=mensaje_error(e))))

	def _al_cargar_conversacion(self, _issue: dict) -> None:
		if self.pr:
			self.conversacion.establecer_extra(lineas_extra_pr(self.pr, len(self.pendientes)))

	def _al_cambiar_pagina(self, evento: wx.BookCtrlEvent) -> None:
		evento.Skip()
		self._cargar_pagina(evento.GetSelection())

	def _cargar_pagina(self, indice: int, forzar: bool = False) -> None:
		if not self or (indice in self.cargadas and not forzar) or not self.pr:
			return
		self.cargadas.add(indice)
		cargadores = {
			PAGINA_COMMITS: self._cargar_commits, PAGINA_ARCHIVOS: self._cargar_archivos,
			PAGINA_CHECKS: self._cargar_checks, PAGINA_HILOS: self._cargar_hilos,
		}
		if indice in cargadores:
			cargadores[indice]()

	@property
	def sha_cabeza(self) -> str:
		return como_dict(self.pr.get("head")).get("sha", "")

	def _cargar_commits(self) -> None:
		api = self.ctx.api()

		def recibido(commits: Any) -> None:
			if not self:
				return
			self.commits = [c for c in como_lista(commits) if isinstance(c, dict)]
			filas = []
			for commit in self.commits:
				datos = como_dict(commit.get("commit"))
				autor = f.login(commit.get("author")) if commit.get("author") else como_dict(datos.get("author")).get("name", "")
				filas.append([(commit.get("sha") or "")[:7], f.primera_linea(datos.get("message")), autor,
					f.fecha(como_dict(datos.get("author")).get("date"), self.ctx.relativas())])
			self.lista_commits.reemplazar_filas(filas)
			self.estado_commits.SetLabel(_("{n} commits.").format(n=len(self.commits)))

		en_segundo_plano(self, self.ctx, lambda: api.commits_pr(self.nombre, self.numero), sonido="", al_terminar=recibido)

	def _cargar_archivos(self) -> None:
		api = self.ctx.api()

		def trabajo() -> tuple[list, str, list]:
			return (como_lista(api.archivos_pr(self.nombre, self.numero)), api.diff_pr(self.nombre, self.numero),
				como_lista(api.comentarios_revision(self.nombre, self.numero)))

		def recibido(resultado: tuple[list, str, list]) -> None:
			if not self:
				return
			archivos, texto_diff, comentarios = resultado
			self.archivos = [a for a in archivos if isinstance(a, dict)]
			self.comentarios_linea = [c for c in comentarios if isinstance(c, dict)]
			self.lista_archivos.reemplazar_filas([
				[a.get("filename", ""), _(ESTADOS_ARCHIVO.get(a.get("status", ""), a.get("status", ""))),
					f"+{a.get('additions', 0)}", f"-{a.get('deletions', 0)}"] for a in self.archivos
			])
			self.diferencias.comentarios = comentarios_por_linea(self.comentarios_linea, self.pendientes)
			self.diferencias.mostrar(texto_diff if isinstance(texto_diff, str) else "")

		en_segundo_plano(self, self.ctx, trabajo, sonido="", al_terminar=recibido)

	def _cargar_checks(self) -> None:
		api = self.ctx.api()
		sha = self.sha_cabeza

		def trabajo() -> tuple[list, dict]:
			return como_lista(api.checks_de(self.nombre, sha)), como_dict(api.estado_combinado(self.nombre, sha))

		def recibido(resultado: tuple[list, dict]) -> None:
			if not self:
				return
			checks, combinado = resultado
			self.checks = [dict(c, _tipo="check") for c in checks if isinstance(c, dict)]
			self.checks += [dict(s, _tipo="estado") for s in combinado.get("statuses") or [] if isinstance(s, dict)]
			filas = []
			fallidos = correctos = en_curso = 0
			for check in self.checks:
				if check["_tipo"] == "check":
					estado = f.estado_ejecucion(check)
					conclusion = check.get("conclusion") if check.get("status") == "completed" else "in_progress"
					origen = como_dict(check.get("app")).get("name", "")
					duracion = ""
					if check.get("started_at") and check.get("completed_at"):
						duracion = f.duracion(marca_tiempo(check["completed_at"]) - marca_tiempo(check["started_at"]))
					detalle = como_dict(check.get("output")).get("title") or ""
					nombre_check = check.get("name", "")
				else:
					estado = f.estado(check.get("state"))
					conclusion = {"success": "success", "pending": "in_progress"}.get(check.get("state"), "failure")
					origen, duracion, detalle, nombre_check = _("Estado externo"), "", check.get("description") or "", check.get("context", "")
				if conclusion in ("success", "neutral", "skipped"):
					correctos += 1
				elif conclusion in ("in_progress", None):
					en_curso += 1
				else:
					fallidos += 1
				filas.append([nombre_check, estado, origen, duracion, detalle])
			self.lista_checks.reemplazar_filas(filas)
			self.resumen_checks.ChangeValue(_(
				"Estado combinado del commit {s}: {e}. {n} checks: {c} correctos, {fa} fallidos y {p} en curso o pendientes."
			).format(s=sha[:7], e=f.estado(combinado.get("state")) or "-", n=len(self.checks), c=correctos, fa=fallidos, p=en_curso))
			if fallidos:
				self.ctx.sonar("accion_fallo")

		en_segundo_plano(self, self.ctx, trabajo, sonido="", al_terminar=recibido)

	def _cargar_hilos(self) -> None:
		api = self.ctx.api()

		def recibido(hilos: Any) -> None:
			if not self:
				return
			self.hilos = [h for h in como_lista(hilos) if isinstance(h, dict)]
			filas = []
			for hilo in self.hilos:
				comentarios = como_lista(como_dict(hilo.get("comments")).get("nodes"))
				primero = como_dict(comentarios[0]) if comentarios else {}
				estado = _("Resuelto") if hilo.get("isResolved") else _("Sin resolver")
				if hilo.get("isOutdated"):
					estado += ", " + _("desactualizado")
				filas.append([hilo.get("path", ""), str(hilo.get("line") or hilo.get("originalLine") or ""), estado, str(len(comentarios)),
					f"{como_dict(primero.get('author')).get('login', '')}: {f.primera_linea(primero.get('body'))}"])
			self.lista_hilos.reemplazar_filas(filas)
			self._mostrar_hilo()

		en_segundo_plano(self, self.ctx, lambda: api.hilos_revision(self.nombre, self.numero), sonido="", al_terminar=recibido)

	def _actualizar_menu(self) -> None:
		abierto = self.pr.get("state", "open") == "open" and not self.pr.get("merged")
		cambiar_etiqueta(self.menu["estado"], _("&Cerrar el pull request") if abierto else _("&Reabrir el pull request"))
		self.menu["estado"].Enable(not self.pr.get("merged"))
		cambiar_etiqueta(self.menu["listo"], _("Vo&lver a borrador") if not self.pr.get("draft") else _("Marcar como &listo para revisión"))
		cambiar_etiqueta(self.menu["auto"], _("Desactivar la fusión a&utomática") if self.pr.get("auto_merge") else _("Activar la fusión a&utomática…"))
		self.menu["descartar"].Enable(bool(self.pendientes))
		for clave in ("fusionar", "auto", "listo", "actualizar_rama", "checkout"):
			self.menu[clave].Enable(abierto)

	def _recargar(self, _resultado: Any = None) -> None:
		if self:
			self.cargar()

	# ── Commits, archivos, checks, hilos ──────────────────────────────────────

	def abrir_commit(self) -> None:
		fila = self.lista_commits.fila_actual()
		if 0 <= fila < len(self.commits):
			abrir.commit(self.ctx, self, self.nombre, self.commits[fila].get("sha", ""))

	def ir_al_diff_del_archivo(self) -> None:
		fila = self.lista_archivos.fila_actual()
		if not 0 <= fila < len(self.archivos):
			return
		ruta = self.archivos[fila].get("filename", "")
		for indice, linea in enumerate(self.diferencias.lineas):
			if linea.tipo == d.ARCHIVO and linea.archivo == ruta:
				enfocar(self.diferencias.lista)
				self.diferencias.lista.enfocar_fila(indice)
				return
		self.ctx.avisar(_("Este archivo no tiene diferencias de texto que mostrar."))

	def comentar_linea(self, linea: d.LineaDiff) -> None:
		if not self.sha_cabeza:
			self.ctx.avisar(_("Todavía no se ha cargado el pull request."))
			return
		lado = "LEFT" if linea.tipo == d.ELIMINADA else "RIGHT"
		numero_linea = linea.antigua if lado == "LEFT" else linea.nueva
		if not numero_linea:
			return
		api = self.ctx.api()
		sha = self.sha_cabeza

		def enviar(valores: dict) -> Any:
			cuerpo = (valores.get("cuerpo") or "").strip()
			if not cuerpo:
				raise ValueError(_("El comentario está vacío."))
			if valores.get("pendiente"):
				return {"pendiente": True, "path": linea.archivo, "line": int(numero_linea), "side": lado, "body": cuerpo}
			return api.comentar_linea(self.nombre, self.numero, sha, linea.archivo, int(numero_linea), cuerpo, lado)

		contexto = _("{r}, línea {n} ({t}): {x}").format(r=linea.archivo, n=numero_linea, t=linea.nombre_tipo(), x=linea.texto)
		resultado = editor.editar(self, self.ctx, _("Comentar la línea {n} de {r}").format(n=numero_linea, r=linea.archivo), enviar,
			texto_contexto=contexto, etiqueta_enviar=_("&Enviar"),
			extras=[editor.CampoExtra("pendiente", _("Añadir a la revisión &pendiente (se publica al enviar la revisión)"), "bool",
				bool(self.pendientes), ayuda=_("Si se marca, el comentario se guarda y se publica junto con la revisión."))])
		if resultado is None:
			return
		if isinstance(resultado, dict) and resultado.get("pendiente"):
			self.pendientes.append({k: resultado[k] for k in ("path", "line", "side", "body")})
			self.ctx.avisar(_("Comentario añadido a la revisión pendiente. Pendientes: {n}.").format(n=len(self.pendientes)))
		else:
			self.comentarios_linea.append(como_dict(resultado))
		self._refrescar_comentarios()

	def _refrescar_comentarios(self) -> None:
		"""Vuelve a marcar las líneas comentadas SIN mover a la persona de la línea en la que está."""
		fila, tenia_foco = self.diferencias.actual, self.diferencias.lista.HasFocus()
		self.diferencias.actualizar_comentarios(comentarios_por_linea(self.comentarios_linea, self.pendientes))
		if self.diferencias.lineas:
			# Si apareció la columna «Comentarios», la lista se rehízo: se recoloca el foco.
			self.diferencias.lista.enfocar_fila(min(fila, len(self.diferencias.lineas) - 1), anunciar=False)
			if tenia_foco:
				enfocar(self.diferencias.lista)
		self._actualizar_menu()
		if self.pr:
			self.conversacion.establecer_extra(lineas_extra_pr(self.pr, len(self.pendientes)))

	def descartar_pendientes(self) -> None:
		if not self.pendientes:
			return
		if confirmar(self, _("¿Descartar los {n} comentarios en línea pendientes?").format(n=len(self.pendientes)),
			_("Descartar comentarios"), peligroso=True) != wx.ID_YES:
			return
		self.pendientes.clear()
		self._refrescar_comentarios()
		self.ctx.avisar(_("Comentarios pendientes descartados."))

	def _check_actual(self) -> dict | None:
		fila = self.lista_checks.fila_actual()
		return self.checks[fila] if 0 <= fila < len(self.checks) else None

	def abrir_check(self) -> None:
		check = self._check_actual()
		if check is None:
			return
		url = check.get("details_url") or check.get("target_url") or check.get("html_url") or ""
		coincidencia = _RUN_ACTIONS.search(url)
		if coincidencia:
			abrir.ejecucion(self.ctx, self, self.nombre, int(coincidencia.group(1)))
		elif url:
			webbrowser.open(url)
		else:
			self.ctx.avisar(_("Este check no tiene detalles."))

	def volver_a_pedir_check(self) -> None:
		check = self._check_actual()
		if check is None or check.get("_tipo") != "check" or not check.get("id"):
			self.ctx.avisar(_("Solo se pueden volver a pedir los checks, no los estados externos."))
			return
		api = self.ctx.api()
		en_segundo_plano(self, self.ctx, lambda: api.volver_a_pedir_check(self.nombre, int(check["id"])),
			exito=_("Check «{n}» pedido de nuevo.").format(n=check.get("name", "")),
			al_terminar=lambda _r: self and self._cargar_pagina(PAGINA_CHECKS, forzar=True))

	def _hilo_actual(self) -> dict | None:
		fila = self.lista_hilos.fila_actual()
		return self.hilos[fila] if 0 <= fila < len(self.hilos) else None

	def _mostrar_hilo(self) -> None:
		hilo = self._hilo_actual()
		if hilo is None:
			self.texto_hilo.ChangeValue("")
			return
		partes = [f"{hilo.get('path', '')}, " + _("línea {n}").format(n=hilo.get("line") or hilo.get("originalLine") or "-"), ""]
		for comentario in como_lista(como_dict(hilo.get("comments")).get("nodes")):
			comentario = como_dict(comentario)
			partes += [f"{como_dict(comentario.get('author')).get('login', '')} ({f.fecha_completa(comentario.get('createdAt'))}):",
				comentario.get("body") or "", ""]
		self.texto_hilo.ChangeValue("\n".join(partes))
		self.texto_hilo.SetInsertionPoint(0)

	def resolver_hilo(self) -> None:
		hilo = self._hilo_actual()
		if hilo is None:
			return
		resolver = not hilo.get("isResolved")
		api = self.ctx.api()
		en_segundo_plano(self, self.ctx, lambda: api.resolver_hilo(hilo["id"], resolver),
			exito=_("Hilo resuelto.") if resolver else _("Hilo reabierto."),
			al_terminar=lambda _r: self and self._cargar_pagina(PAGINA_HILOS, forzar=True))

	def responder_hilo(self) -> None:
		hilo = self._hilo_actual()
		if hilo is None:
			return
		comentarios = como_lista(como_dict(hilo.get("comments")).get("nodes"))
		if not comentarios:
			return
		id_comentario = como_dict(comentarios[0]).get("databaseId")
		api = self.ctx.api()

		def enviar(valores: dict) -> Any:
			cuerpo = (valores.get("cuerpo") or "").strip()
			if not cuerpo:
				raise ValueError(_("La respuesta está vacía."))
			return api.responder_comentario_revision(self.nombre, self.numero, int(id_comentario), cuerpo)

		if editor.editar(self, self.ctx, _("Responder en el hilo de {r}").format(r=hilo.get("path", "")), enviar,
			texto_contexto=self.texto_hilo.GetValue(), etiqueta_enviar=_("&Enviar respuesta")) is not None:
			self._cargar_pagina(PAGINA_HILOS, forzar=True)

	def ir_a_linea_hilo(self) -> None:
		hilo = self._hilo_actual()
		if hilo is None:
			return
		ruta = hilo.get("path", "")
		numero = hilo.get("line") or hilo.get("originalLine")
		lado = hilo.get("diffSide") or "RIGHT"
		self.libro.SetSelection(PAGINA_ARCHIVOS)
		self._cargar_pagina(PAGINA_ARCHIVOS)
		for indice, linea in enumerate(self.diferencias.lineas):
			if linea.archivo != ruta or linea.tipo not in (d.AÑADIDA, d.ELIMINADA, d.CONTEXTO):
				continue
			if (lado == "LEFT" and linea.tipo != d.AÑADIDA and linea.antigua == numero) or (
				lado != "LEFT" and linea.tipo != d.ELIMINADA and linea.nueva == numero):
				enfocar(self.diferencias.lista)
				self.diferencias.lista.enfocar_fila(indice)
				return
		self.ctx.avisar(_("La línea ya no aparece en las diferencias (el hilo puede estar desactualizado)."))

	# ── Acciones del pull request ─────────────────────────────────────────────

	def revisar(self) -> None:
		if self.ctx.usuario and f.login(self.pr.get("user")) == self.ctx.usuario:
			self.ctx.avisar(_("Es su propio pull request: solo podrá enviar una revisión de tipo Comentar."))
		dialogo = DialogoRevision(self, self.pendientes)
		try:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			evento, cuerpo = dialogo.valores()
		finally:
			dialogo.Destroy()
		if evento == "REQUEST_CHANGES" and not cuerpo.strip():
			mostrar_error(self, _("Para pedir cambios hay que explicar cuáles en el texto de la revisión."), _("Falta el texto"))
			return
		if evento == "COMMENT" and not cuerpo.strip() and not self.pendientes:
			mostrar_error(self, _("Una revisión de tipo Comentar necesita texto o comentarios en línea."), _("Falta el texto"))
			return
		api = self.ctx.api()
		comentarios = list(self.pendientes)

		def hecho(_r: Any) -> None:
			if not self:
				return
			self.pendientes.clear()
			self._refrescar_comentarios()
			self.cargar()

		textos = {"APPROVE": _("Revisión enviada: aprobado."), "REQUEST_CHANGES": _("Revisión enviada: cambios pedidos."),
			"COMMENT": _("Revisión enviada.")}
		en_segundo_plano(self, self.ctx, lambda: api.crear_revision(self.nombre, self.numero, evento, cuerpo, comentarios, self.sha_cabeza),
			exito=textos[evento], sonido="enviado", al_terminar=hecho)

	def fusionar(self) -> None:
		if not self.pr:
			self.ctx.avisar(_("Todavía no se ha cargado el pull request."))
			return
		explicacion, posible = explicar_fusion(self.pr)
		if not posible:
			mostrar_mensaje(self, explicacion, _("No se puede fusionar"))
			return
		cabeza, base = como_dict(self.pr.get("head")), como_dict(self.pr.get("base"))
		misma = como_dict(cabeza.get("repo")).get("full_name") == como_dict(base.get("repo")).get("full_name") == self.nombre
		dialogo = DialogoFusion(self, self.pr, misma)
		try:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			valores = dialogo.valores()
		finally:
			dialogo.Destroy()
		api = self.ctx.api()
		sha = self.sha_cabeza
		rama = cabeza.get("ref", "")

		def trabajo() -> Any:
			resultado = api.fusionar_pr(self.nombre, self.numero, valores["metodo"], valores["titulo"], valores["mensaje"], sha)
			if valores["borrar_rama"] and rama:
				try:
					api.borrar_rama(self.nombre, rama)
				except Exception:  # noqa: BLE001 - la fusión ya está hecha; se avisa en el registro
					log.warning("No se pudo borrar la rama %s tras fusionar", rama, exc_info=True)
			return resultado

		en_segundo_plano(self, self.ctx, trabajo, inicio=_("Fusionando…"), sonido="fusionado",
			exito=_("Pull request #{n} fusionado.").format(n=self.numero), al_terminar=self._recargar,
			titulo_error=_("No se pudo fusionar"))

	def fusion_automatica(self) -> None:
		api = self.ctx.api()
		id_nodo = self.pr.get("node_id") or ""
		if self.pr.get("auto_merge"):
			en_segundo_plano(self, self.ctx, lambda: api.desactivar_fusion_automatica(id_nodo),
				exito=_("Fusión automática desactivada."), al_terminar=self._recargar)
			return
		eleccion = elegir_uno(self, _("Fusión automática"), _("&Método cuando se cumplan los requisitos:"),
			[_(t).replace("&", "") for _m, _g, t in METODOS_FUSION])
		if eleccion is None:
			return
		metodo = METODOS_FUSION[eleccion][1]
		en_segundo_plano(self, self.ctx, lambda: api.activar_fusion_automatica(id_nodo, metodo),
			exito=_("Fusión automática activada: se fusionará cuando pase todo lo obligatorio."), al_terminar=self._recargar)

	def cambiar_borrador(self) -> None:
		api = self.ctx.api()
		listo = bool(self.pr.get("draft"))
		en_segundo_plano(self, self.ctx, lambda: api.marcar_listo(self.pr.get("node_id") or "", listo),
			exito=_("Marcado como listo para revisión.") if listo else _("Vuelto a borrador."), al_terminar=self._recargar)

	def pedir_revision(self) -> None:
		api = self.ctx.api()
		actuales = [u.get("login", "") for u in self.pr.get("requested_reviewers") or [] if isinstance(u, dict)]
		autor = f.login(self.pr.get("user"))

		def elegir(personas: Any) -> None:
			logins = [p.get("login", "") for p in como_lista(personas) if isinstance(p, dict) and p.get("login") != autor]
			for actual in actuales:
				if actual not in logins:
					logins.append(actual)
			if not logins:
				self.ctx.avisar(_("No hay nadie a quien pedir revisión."))
				return
			elegidos = elegir_varios(self, _("Pedir revisión"), _("&Revisores:"), logins,
				[i for i, x in enumerate(logins) if x in actuales], self.ctx.config, _("Marque con Espacio a quién pedir la revisión."))
			if elegidos is None:
				return
			nuevos = [logins[i] for i in elegidos if logins[i] not in actuales]
			quitados = [x for x in actuales if x not in [logins[i] for i in elegidos]]

			def trabajo() -> None:
				if nuevos:
					api.pedir_revision(self.nombre, self.numero, nuevos)
				if quitados:
					api.quitar_revision(self.nombre, self.numero, quitados)

			en_segundo_plano(self, self.ctx, trabajo, exito=_("Revisores actualizados."), al_terminar=self._recargar)

		en_segundo_plano(self, self.ctx, lambda: api.asignables(self.nombre), sonido="", al_terminar=elegir)

	def actualizar_rama(self) -> None:
		api = self.ctx.api()
		en_segundo_plano(self, self.ctx, lambda: api.actualizar_rama_pr(self.nombre, self.numero), inicio=_("Actualizando la rama…"),
			exito=_("GitHub está actualizando la rama con los cambios de la base."), al_terminar=self._recargar)

	def cerrar_o_reabrir(self) -> None:
		api = self.ctx.api()
		abierto = self.pr.get("state", "open") == "open"
		en_segundo_plano(self, self.ctx, lambda: api.editar_pr(self.nombre, self.numero, state="closed" if abierto else "open"),
			exito=_("Pull request cerrado.") if abierto else _("Pull request reabierto."), al_terminar=self._recargar)

	def editar(self) -> None:
		api = self.ctx.api()

		def enviar(valores: dict) -> Any:
			return api.editar_pr(self.nombre, self.numero, title=valores["titulo"], body=valores.get("cuerpo") or "")

		if editor.editar(self, self.ctx, _("Editar el pull request #{n}").format(n=self.numero), enviar, con_titulo=True,
			titulo=self.pr.get("title", ""), cuerpo=self.pr.get("body") or "", etiqueta_enviar=_("&Guardar")) is not None:
			self.cargar()

	def etiquetas(self) -> None:
		actuales = [e.get("name", "") for e in self.pr.get("labels") or [] if isinstance(e, dict)]
		editar_etiquetas(self, self.ctx, self.nombre, self.numero, actuales, self._recargar)

	def asignados(self) -> None:
		actuales = [u.get("login", "") for u in self.pr.get("assignees") or [] if isinstance(u, dict)]
		editar_asignados(self, self.ctx, self.nombre, self.numero, actuales, self._recargar)

	def checkout_local(self) -> None:
		"""git fetch <remoto> pull/N/head:pr-N y git switch pr-N en un repositorio local configurado."""
		from app.services.git_local import RepositorioLocal

		carpetas = [str(c) for c in self.ctx.config.obtener("git.repos_locales", []) or []]
		nombre, numero = self.nombre, self.numero

		def buscar() -> list[tuple[str, str]]:
			encontrados = []
			for carpeta in carpetas:
				try:
					for remoto, url, tipo in RepositorioLocal(carpeta).remotos():
						if tipo == "fetch" and remoto_coincide(url, nombre):
							encontrados.append((carpeta, remoto))
							break
				except Exception:  # noqa: BLE001 - una carpeta movida o sin git no impide mirar las demás
					log.debug("No se pudieron leer los remotos de %s", carpeta, exc_info=True)
			return encontrados

		def elegido(encontrados: list[tuple[str, str]]) -> None:
			if not encontrados:
				mostrar_mensaje(self, _(
					"No hay ningún repositorio local configurado cuyo remoto sea {r}.\n\n"
					"Clone el repositorio o añada su carpeta en la sección «Repositorios locales» de la ventana principal "
					"y vuelva a intentarlo. Entonces se ejecutará «git fetch origin pull/{n}/head:pr-{n}» y se cambiará "
					"a la rama pr-{n}."
				).format(r=nombre, n=numero), _("Checkout local"))
				return
			indice = 0
			if len(encontrados) > 1:
				eleccion = elegir_uno(self, _("Checkout local"), _("&Repositorio local:"), [c for c, _r in encontrados])
				if eleccion is None:
					return
				indice = eleccion
			carpeta, remoto = encontrados[indice]
			rama = f"pr-{numero}"

			def trabajo() -> str:
				repo = RepositorioLocal(carpeta, token=self.ctx.token)
				if repo.rama_actual() == rama:
					repo.git_red("pull", remoto, f"pull/{numero}/head")
				else:
					repo.git_red("fetch", remoto, f"+pull/{numero}/head:{rama}")
					repo.cambiar_rama(rama)
				return carpeta

			en_segundo_plano(self, self.ctx, trabajo, inicio=_("Trayendo el pull request…"),
				exito=_("Rama {b} lista en {c}.").format(b=rama, c=carpeta), titulo_error=_("No se pudo hacer el checkout"))

		en_segundo_plano(self, self.ctx, buscar, sonido="", al_terminar=elegido)

	def abrir_navegador(self) -> None:
		webbrowser.open(self.pr.get("html_url") or f"https://{self.ctx.host}/{self.nombre}/pull/{self.numero}")

	def copiar_enlace(self) -> None:
		copiar(self.ctx, self.pr.get("html_url") or f"https://{self.ctx.host}/{self.nombre}/pull/{self.numero}", _("Enlace copiado."))

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if self.pendientes and evento.CanVeto():
			if confirmar(self, _("Hay {n} comentarios en línea pendientes sin enviar. ¿Cerrar y perderlos?").format(n=len(self.pendientes)),
				_("Comentarios pendientes"), peligroso=True) != wx.ID_YES:
				evento.Veto()
				return
		super()._al_cerrar(evento)


def abrir_pull_request(ctx: Any, padre: wx.Window | None, nombre: str, numero: int) -> None:
	"""Abre la ventana de un pull request (o trae al frente la que ya esté abierta)."""
	if VentanaDetalle.traer_al_frente(clave_pr(nombre, numero)):
		return
	ventana = VentanaPullRequest(padre, ctx, nombre, int(numero))
	ventana.mostrar()
	ventana.cargar()
