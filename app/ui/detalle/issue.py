"""Ventana de una issue: conversación accesible y todas las acciones de gestión.

Menú «Acciones» (Alt+A o F10):

- Cerrar como completada, cerrar como no planificada, reabrir.
- Editar el título y la descripción (Ctrl+Mayús+E), etiquetas (Ctrl+Mayús+L),
  asignados (Ctrl+Mayús+A), hito (Ctrl+Mayús+M).
- Bloquear o desbloquear la conversación, fijar y quitar de fijadas,
  transferir a otro repositorio, suscripción, subissues.
- Abrir en el navegador (Ctrl+Mayús+B), copiar el enlace (Ctrl+Mayús+C),
  actualizar (F5), cerrar la ventana (Ctrl+W). Escape no cierra la ventana.

Las funciones ``editar_etiquetas``, ``editar_asignados`` y ``editar_hito``
también las usa la ventana de pull request (en GitHub un PR es una issue).
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from collections.abc import Callable
from typing import Any

import wx

from app.services import formato as f
from app.ui import abrir, editor
from app.ui.comunes import confirmar, copiar, elegir_uno, elegir_varios, en_segundo_plano, pedir_texto
from app.ui.detalle.conversacion import (
	DialogoLista,
	PanelConversacion,
	VentanaDetalle,
	como_dict,
	como_lista,
	crear_menu_acciones,
)

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def clave_issue(nombre: str, numero: int) -> str:
	return f"issue:{nombre.lower()}#{int(numero)}"


MOTIVOS_BLOQUEO = [
	("", N_("Sin motivo")), ("off-topic", N_("Fuera de tema")), ("too heated", N_("Demasiado acalorada")),
	("resolved", N_("Resuelta")), ("spam", N_("Spam")),
]

SUSCRIPCIONES = [
	("SUBSCRIBED", N_("Suscribirme: recibir todas las notificaciones")),
	("UNSUBSCRIBED", N_("Cancelar la suscripción: solo si participo o me mencionan")),
	("IGNORED", N_("Ignorar: no recibir ninguna notificación")),
]

# Operación que la fachada de la API no tiene: se hace con el cliente crudo.
_MUTACION_SUSCRIPCION = """
mutation($id: ID!, $estado: SubscriptionState!) {
  updateSubscription(input: {subscribableId: $id, state: $estado}) { subscribable { id viewerSubscription } }
}"""


# ════════════════════════════════════════════════════════════════════════════
# Acciones compartidas con los pull requests
# ════════════════════════════════════════════════════════════════════════════


def editar_etiquetas(ventana: wx.Window, ctx: Any, nombre: str, numero: int, actuales: list[str],
	al_terminar: Callable[[Any], None]) -> None:
	"""Pide las etiquetas del repositorio, deja marcar las de la issue y las guarda."""
	api = ctx.api()

	def elegir(etiquetas: Any) -> None:
		nombres = [e.get("name", "") for e in como_lista(etiquetas) if isinstance(e, dict)]
		if not nombres:
			ctx.avisar(_("El repositorio no tiene etiquetas."))
			return
		marcados = [i for i, n in enumerate(nombres) if n in actuales]
		textos = [_("{n}: {d}").format(n=e.get("name", ""), d=e.get("description")) if e.get("description") else e.get("name", "")
			for e in como_lista(etiquetas) if isinstance(e, dict)]
		elegidos = elegir_varios(ventana, _("Etiquetas de #{n}").format(n=numero), _("&Etiquetas:"), textos, marcados, ctx.config,
			_("Marque con Espacio las etiquetas que debe tener."))
		if elegidos is None:
			return
		nuevas = [nombres[i] for i in elegidos]
		en_segundo_plano(ventana, ctx, lambda: api.poner_etiquetas(nombre, numero, nuevas), exito=_("Etiquetas guardadas."),
			al_terminar=al_terminar)

	en_segundo_plano(ventana, ctx, lambda: api.etiquetas(nombre), sonido="", al_terminar=elegir)


def editar_asignados(ventana: wx.Window, ctx: Any, nombre: str, numero: int, actuales: list[str],
	al_terminar: Callable[[Any], None]) -> None:
	"""Pide quién se puede asignar (``api.asignables``) y guarda la elección."""
	api = ctx.api()

	def elegir(personas: Any) -> None:
		logins = [p.get("login", "") for p in como_lista(personas) if isinstance(p, dict)]
		for actual in actuales:
			if actual not in logins:
				logins.append(actual)
		if not logins:
			ctx.avisar(_("No hay nadie a quien asignar."))
			return
		marcados = [i for i, login in enumerate(logins) if login in actuales]
		elegidos = elegir_varios(ventana, _("Asignados de #{n}").format(n=numero), _("&Personas asignadas:"), logins, marcados,
			ctx.config, _("Marque con Espacio a las personas asignadas."))
		if elegidos is None:
			return
		nuevos = [logins[i] for i in elegidos]
		en_segundo_plano(ventana, ctx, lambda: api.editar_issue(nombre, numero, assignees=nuevos), exito=_("Asignados guardados."),
			al_terminar=al_terminar)

	en_segundo_plano(ventana, ctx, lambda: api.asignables(nombre), sonido="", al_terminar=elegir)


def editar_hito(ventana: wx.Window, ctx: Any, nombre: str, numero: int, actual: int | None,
	al_terminar: Callable[[Any], None]) -> None:
	"""Elige el hito abierto (o ninguno)."""
	api = ctx.api()

	def elegir(hitos: Any) -> None:
		lista = [h for h in como_lista(hitos) if isinstance(h, dict)]
		opciones = [_("(sin hito)")] + [
			h.get("title", "") + (" " + _("(vence {f})").format(f=f.fecha_completa(h.get("due_on"))) if h.get("due_on") else "")
			for h in lista
		]
		numeros = [None] + [h.get("number") for h in lista]
		seleccion = numeros.index(actual) if actual in numeros else 0
		eleccion = elegir_uno(ventana, _("Hito de #{n}").format(n=numero), _("&Hito:"), opciones, seleccion)
		if eleccion is None:
			return
		en_segundo_plano(ventana, ctx, lambda: api.editar_issue(nombre, numero, milestone=numeros[eleccion]),
			exito=_("Hito guardado."), al_terminar=al_terminar)

	en_segundo_plano(ventana, ctx, lambda: api.hitos(nombre, "open"), sonido="", al_terminar=elegir)


# ════════════════════════════════════════════════════════════════════════════
# Ventana
# ════════════════════════════════════════════════════════════════════════════


class VentanaIssue(VentanaDetalle):
	def __init__(self, padre: wx.Window | None, contexto: Any, nombre: str, numero: int) -> None:
		super().__init__(padre, contexto, clave_issue(nombre, numero), _("Issue #{n} de {r}").format(n=numero, r=nombre))
		self.nombre = nombre
		self.numero = int(numero)
		self.issue: dict = {}
		self.menu = crear_menu_acciones(self, _("&Acciones"), [
			("cerrar_completada", _("&Cerrar como completada"), lambda: self.cerrar("completed")),
			("cerrar_no_planificada", _("Cerrar como &no planificada"), lambda: self.cerrar("not_planned")),
			("reabrir", _("&Reabrir"), self.reabrir),
			None,
			("editar", _("&Editar el título y la descripción…\tCtrl+Shift+E"), self.editar),
			("etiquetas", _("E&tiquetas…\tCtrl+Shift+L"), self.etiquetas),
			("asignados", _("&Asignados…\tCtrl+Shift+A"), self.asignados),
			("hito", _("&Hito…\tCtrl+Shift+M"), self.hito),
			None,
			("bloquear", _("&Bloquear la conversación…"), self.bloquear),
			("fijar", _("&Fijar en el repositorio"), lambda: self.fijar(True)),
			("desfijar", _("&Quitar de las fijadas"), lambda: self.fijar(False)),
			("transferir", _("Tran&sferir a otro repositorio…"), self.transferir),
			("suscripcion", _("Suscri&pción…"), self.suscripcion),
			("subissues", _("Sub&issues…"), self.subissues),
			None,
			("navegador", _("Abrir en el nave&gador\tCtrl+Shift+B"), self.abrir_navegador),
			("enlace", _("Copiar el en&lace\tCtrl+Shift+C"), self.copiar_enlace),
			("actualizar", _("Act&ualizar\tF5"), self.cargar),
			("cerrar_ventana", _("Cerrar la &ventana\tCtrl+W"), self.Close),
		])
		self.conversacion = PanelConversacion(self, contexto, nombre, numero, al_cargar=self._al_cargar)
		self._actualizar_menu()

	# ── Carga ─────────────────────────────────────────────────────────────────

	def cargar(self) -> None:
		self.conversacion.cargar()

	def enfocar_inicio(self) -> None:
		self.conversacion.lista.SetFocus()

	def _al_cargar(self, issue: dict) -> None:
		if issue.get("pull_request"):
			# Era un pull request: se abre en su ventana propia, con diferencias y checks.
			from app.ui.detalle.pull_request import abrir_pull_request

			padre = self.padre_original
			wx.CallAfter(self.Close)
			wx.CallAfter(abrir_pull_request, self.ctx, padre, self.nombre, self.numero)
			return
		self.issue = issue
		self.SetTitle(_("Issue #{n}: {t} — {r}").format(n=self.numero, t=issue.get("title", ""), r=self.nombre))
		self._actualizar_menu()

	def _actualizar_menu(self) -> None:
		abierta = self.issue.get("state", "open") == "open"
		self.menu["cerrar_completada"].Enable(abierta)
		self.menu["cerrar_no_planificada"].Enable(abierta)
		self.menu["reabrir"].Enable(not abierta)
		etiqueta = _("Des&bloquear la conversación") if self.issue.get("locked") else _("&Bloquear la conversación…")
		self.menu["bloquear"].SetItemLabel(etiqueta)

	def _recargar(self, _resultado: Any = None) -> None:
		if self:
			self.cargar()

	@property
	def _api(self):
		return self.ctx.api()

	# ── Estado ────────────────────────────────────────────────────────────────

	def cerrar(self, motivo: str) -> None:
		texto = _("Issue cerrada como completada.") if motivo == "completed" else _("Issue cerrada como no planificada.")
		api = self._api
		en_segundo_plano(self, self.ctx, lambda: api.cerrar_issue(self.nombre, self.numero, motivo), exito=texto,
			al_terminar=self._recargar)

	def reabrir(self) -> None:
		api = self._api
		en_segundo_plano(self, self.ctx, lambda: api.reabrir_issue(self.nombre, self.numero), exito=_("Issue reabierta."),
			al_terminar=self._recargar)

	def editar(self) -> None:
		api = self._api

		def enviar(valores: dict) -> Any:
			return api.editar_issue(self.nombre, self.numero, title=valores["titulo"], body=valores.get("cuerpo") or "")

		if editor.editar(self, self.ctx, _("Editar la issue #{n}").format(n=self.numero), enviar, con_titulo=True,
			titulo=self.issue.get("title", ""), cuerpo=self.issue.get("body") or "", etiqueta_enviar=_("&Guardar"),
			con_adjuntos=True) is not None:
			self.cargar()

	def etiquetas(self) -> None:
		actuales = [e.get("name", "") for e in self.issue.get("labels") or [] if isinstance(e, dict)]
		editar_etiquetas(self, self.ctx, self.nombre, self.numero, actuales, self._recargar)

	def asignados(self) -> None:
		actuales = [u.get("login", "") for u in self.issue.get("assignees") or [] if isinstance(u, dict)]
		editar_asignados(self, self.ctx, self.nombre, self.numero, actuales, self._recargar)

	def hito(self) -> None:
		editar_hito(self, self.ctx, self.nombre, self.numero, como_dict(self.issue.get("milestone")).get("number"), self._recargar)

	def bloquear(self) -> None:
		api = self._api
		if self.issue.get("locked"):
			en_segundo_plano(self, self.ctx, lambda: api.desbloquear_issue(self.nombre, self.numero),
				exito=_("Conversación desbloqueada."), al_terminar=self._recargar)
			return
		eleccion = elegir_uno(self, _("Bloquear la conversación"), _("&Motivo:"), [_(t) for _c, t in MOTIVOS_BLOQUEO])
		if eleccion is None:
			return
		motivo = MOTIVOS_BLOQUEO[eleccion][0]
		en_segundo_plano(self, self.ctx, lambda: api.bloquear_issue(self.nombre, self.numero, motivo),
			exito=_("Conversación bloqueada: solo colaboradores pueden comentar."), al_terminar=self._recargar)

	def fijar(self, fijar: bool) -> None:
		api = self._api
		id_nodo = self.issue.get("node_id") or ""

		def trabajo() -> None:
			api.fijar_issue(id_nodo or api.id_de_nodo(self.nombre, self.numero), fijar)

		en_segundo_plano(self, self.ctx, trabajo, exito=_("Issue fijada en el repositorio.") if fijar else _("Issue quitada de las fijadas."),
			al_terminar=self._recargar)

	def transferir(self) -> None:
		destino = pedir_texto(self, _("&Repositorio de destino (dueño/nombre):"), _("Transferir la issue"))
		if not destino or "/" not in destino.strip():
			if destino is not None:
				self.ctx.avisar(_("Escriba el repositorio como dueño/nombre."))
			return
		destino = destino.strip()
		if confirmar(self, _("¿Transferir la issue #{n} a {d}? Se moverán sus comentarios y quedará una redirección.").format(
			n=self.numero, d=destino), _("Transferir la issue"), peligroso=True) != wx.ID_YES:
			return
		api = self._api
		id_nodo = self.issue.get("node_id") or ""

		def trabajo() -> dict:
			id_repo = api.id_repo(destino)
			if not id_repo:
				raise ValueError(_("No se encontró el repositorio {d}.").format(d=destino))
			return como_dict(api.transferir_issue(id_nodo or api.id_de_nodo(self.nombre, self.numero), id_repo))

		def hecho(nueva: dict) -> None:
			padre = self.padre_original
			self.Close()
			if nueva.get("number"):
				abrir.issue(self.ctx, padre, destino, int(nueva["number"]))

		en_segundo_plano(self, self.ctx, trabajo, inicio=_("Transfiriendo…"),
			exito=lambda n: _("Issue transferida a {d} con el número {n}.").format(d=destino, n=como_dict(n).get("number", "")),
			al_terminar=hecho)

	def suscripcion(self) -> None:
		eleccion = elegir_uno(self, _("Suscripción a la issue"), _("&Notificaciones:"), [_(t) for _c, t in SUSCRIPCIONES])
		if eleccion is None:
			return
		estado = SUSCRIPCIONES[eleccion][0]
		api = self._api
		id_nodo = self.issue.get("node_id") or ""

		def trabajo() -> None:
			# Cliente crudo: la fachada no tiene ``updateSubscription``.
			api.c.graphql(_MUTACION_SUSCRIPCION, {"id": id_nodo or api.id_de_nodo(self.nombre, self.numero), "estado": estado})

		en_segundo_plano(self, self.ctx, trabajo, exito=_("Suscripción cambiada."))

	def subissues(self) -> None:
		api = self._api

		def anadir(dialogo: DialogoLista, _elemento: Any) -> None:
			texto = pedir_texto(dialogo, _("&Número de la issue de este repositorio:"), _("Añadir subissue"))
			if not texto or not texto.strip().lstrip("#").isdigit():
				return
			numero = int(texto.strip().lstrip("#"))

			def trabajo() -> Any:
				hija = como_dict(api.issue(self.nombre, numero))
				return api.anadir_subissue(self.nombre, self.numero, int(hija.get("id") or 0))

			en_segundo_plano(dialogo, self.ctx, trabajo, exito=_("Subissue añadida."), al_terminar=lambda _r: dialogo and dialogo.recargar())

		def abrir_sub(sub: dict) -> None:
			abrir.issue(self.ctx, self, abrir.nombre_repo_de(sub) or self.nombre, int(sub.get("number") or 0))

		def mostrar(subs: Any) -> None:
			dialogo = DialogoLista(
				self, self.ctx, _("Subissues de #{n}").format(n=self.numero), _("&Subissues:"),
				[(_("Número"), 70), (_("Título"), 360), (_("Estado"), 110), (_("Asignados"), 160)],
				lambda s: [f"#{s.get('number', '')}", s.get("title", ""), f.estado_issue(s), f.asignados(s)],
				como_lista(subs), al_activar=abrir_sub,
				botones=[(_("&Abrir"), lambda d, s: abrir_sub(s), True), (_("Añadir s&ubissue…"), anadir, False)],
				recargar=lambda: api.subissues(self.nombre, self.numero),
			)
			dialogo.mostrar()

		en_segundo_plano(self, self.ctx, lambda: api.subissues(self.nombre, self.numero), sonido="", al_terminar=mostrar)

	def abrir_navegador(self) -> None:
		url = self.issue.get("html_url") or f"https://{self.ctx.host}/{self.nombre}/issues/{self.numero}"
		webbrowser.open(url)

	def copiar_enlace(self) -> None:
		url = self.issue.get("html_url") or f"https://{self.ctx.host}/{self.nombre}/issues/{self.numero}"
		copiar(self.ctx, url, _("Enlace copiado."))


def abrir_issue(ctx: Any, padre: wx.Window | None, nombre: str, numero: int) -> None:
	"""Abre la ventana de una issue (o trae al frente la que ya esté abierta)."""
	if VentanaDetalle.traer_al_frente(clave_issue(nombre, numero)):
		return
	ventana = VentanaIssue(padre, ctx, nombre, int(numero))
	ventana.mostrar()
	ventana.cargar()
