"""Conversación de una issue o de un pull request, y piezas comunes de las ventanas de detalle.

La conversación se muestra como una LISTA nativa (no como una página web):
la descripción inicial, cada comentario, cada revisión y cada evento de la
cronología (etiquetas, cierres, referencias, commits...) son filas con
Autor, Fecha, Tipo y Texto. Debajo, un campo de solo lectura muestra el
texto completo del elemento enfocado: se actualiza al moverse por la lista
SIN robarle el foco, así que se puede leer con las flechas cuando se quiera
(Tab) o dejarlo estar.

Teclas de la lista de la conversación:

- Intro: ver el elemento formateado (HTML con encabezados y enlaces reales).
- Ctrl+N: comentar. Ctrl+R: responder citando. F2: editar mi comentario.
- Supr: borrar mi comentario. Ctrl+E: reaccionar. Ctrl+C: copiar el texto.
- Ctrl+B: abrir en el navegador. F5: actualizar.

Piezas comunes que usan todas las ventanas de ``app/ui/detalle``:

- ``VentanaDetalle``: ventana no modal; Ctrl+W la cierra (Escape NO, para no
  cerrar por accidente una ventana con trabajo), sonidos de abrir y cerrar,
  registro de ventanas abiertas (si ya existe, se trae al frente).
- ``crear_menu_acciones``, ``crear_lista``, ``crear_texto``, ``crear_boton``:
  etiqueta SIEMPRE creada justo antes de su control.
- ``DialogoLista``: lista no modal con botones (blame, historial, subissues...).
- ``DialogoFormulario`` / ``pedir_formulario``: formulario sencillo y accesible.
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

import wx

from app.services import formato as f
from app.services.github.cliente import Pagina, fecha_iso
from app.ui import editor
from app.ui.accesibilidad.ayuda import habilitar_ayuda_contextual
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import nombre_limpio
from app.ui.accesibilidad.teclado import vincular_menu_contextual
from app.ui.comunes import (
	confirmar_peligro,
	copiar,
	elegir_uno,
	en_segundo_plano,
	mensaje_error,
	mostrar_error,
)
from app.ui.vistas.base import preferencias_lectura

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ════════════════════════════════════════════════════════════════════════════
# Utilidades sin interfaz
# ════════════════════════════════════════════════════════════════════════════


def como_dict(valor: Any) -> dict:
	"""El valor si es un diccionario; si no, uno vacío (la API puede devolver ``None``)."""
	return valor if isinstance(valor, dict) else {}


def como_lista(valor: Any) -> list:
	"""Lista de elementos de una ``Pagina``, de una lista o tupla; vacía en otro caso."""
	if isinstance(valor, Pagina):
		return list(valor.elementos)
	if isinstance(valor, (list, tuple)):
		return list(valor)
	return []


def marca_tiempo(texto: str | None) -> float:
	"""Segundos desde 1970 de una fecha ISO (0 si falta) para ordenar sin mezclar zonas horarias."""
	fecha = fecha_iso(texto) if texto else None
	if fecha is None:
		return 0.0
	if fecha.tzinfo is None:
		fecha = fecha.replace(tzinfo=UTC)
	return fecha.timestamp()


def citar(texto: str) -> str:
	"""Texto citado en Markdown («> ») para responder."""
	lineas = (texto or "").strip().splitlines() or [""]
	return "\n".join(f"> {linea}" if linea else ">" for linea in lineas) + "\n\n"


# ════════════════════════════════════════════════════════════════════════════
# Elementos de la conversación (funciones puras: se prueban sin wx)
# ════════════════════════════════════════════════════════════════════════════

DESCRIPCION = "descripcion"
COMENTARIO = "comentario"
REVISION = "revision"
EVENTO = "evento"

#: Eventos de la cronología que solo hacen ruido.
EVENTOS_IGNORADOS = {"subscribed", "unsubscribed", "mentioned"}

_MOTIVOS_BLOQUEO = {
	"off-topic": "fuera de tema", "too heated": "demasiado acalorada", "resolved": "resuelta", "spam": "spam",
}


@dataclass
class ElementoConversacion:
	"""Una fila de la conversación.

	:param clase: ``descripcion``, ``comentario``, ``revision`` o ``evento``.
	:param texto: Markdown completo (para el campo de texto, citar o ver en HTML).
	:param resumen: lo que se ve en la columna «Texto».
	:param propio: lo escribió la persona que usa la aplicación.
	"""

	clase: str
	autor: str
	fecha: str
	tipo: str
	resumen: str
	texto: str = ""
	id: int | None = None
	url: str = ""
	propio: bool = False
	reacciones: dict = field(default_factory=dict)
	datos: dict = field(default_factory=dict)

	@property
	def clave(self) -> tuple:
		"""Identifica el elemento entre recargas (para no mover el foco)."""
		return (self.clase, self.id, self.fecha, self.tipo)

	@property
	def tiene_texto(self) -> bool:
		return bool((self.texto or "").strip())


def _login(usuario: Any) -> str:
	return f.login(usuario) if isinstance(usuario, dict) and usuario else ""


def elemento_descripcion(issue: dict, usuario: str) -> ElementoConversacion:
	autor = _login(issue.get("user"))
	es_pr = bool(issue.get("pull_request") or issue.get("head"))
	cuerpo = issue.get("body") or ""
	return ElementoConversacion(
		DESCRIPCION, autor, issue.get("created_at") or "",
		_("Descripción del pull request") if es_pr else _("Descripción"),
		f.primera_linea(cuerpo) or _("(sin descripción)"), cuerpo, issue.get("number"), issue.get("html_url") or "",
		bool(usuario) and (issue.get("user") or {}).get("login") == usuario, como_dict(issue.get("reactions")), issue,
	)


def elemento_comentario(comentario: dict, usuario: str) -> ElementoConversacion:
	cuerpo = comentario.get("body") or ""
	editado = comentario.get("updated_at") and comentario.get("updated_at") != comentario.get("created_at")
	return ElementoConversacion(
		COMENTARIO, _login(comentario.get("user") or comentario.get("actor")), comentario.get("created_at") or "",
		_("Comentario (editado)") if editado else _("Comentario"),
		f.primera_linea(cuerpo) or _("(vacío)"), cuerpo, comentario.get("id"), comentario.get("html_url") or "",
		bool(usuario) and (comentario.get("user") or {}).get("login") == usuario, como_dict(comentario.get("reactions")),
		comentario,
	)


def describir_evento(evento: dict) -> tuple[str, str]:
	"""(tipo, resumen) en español de un evento de la cronología de GitHub."""
	tipo = evento.get("event") or ""
	etiqueta = como_dict(evento.get("label")).get("name", "")
	asignado = _login(evento.get("assignee"))
	hito = como_dict(evento.get("milestone")).get("title", "")
	commit = (evento.get("commit_id") or "")[:7]
	if tipo == "labeled":
		return _("Etiqueta añadida"), _("añadió la etiqueta «{e}»").format(e=etiqueta)
	if tipo == "unlabeled":
		return _("Etiqueta quitada"), _("quitó la etiqueta «{e}»").format(e=etiqueta)
	if tipo == "closed":
		resumen = _("cerró como no planificada") if evento.get("state_reason") == "not_planned" else _("cerró")
		if commit:
			resumen += " " + _("con el commit {c}").format(c=commit)
		return _("Cerrada"), resumen
	if tipo == "reopened":
		return _("Reabierta"), _("reabrió")
	if tipo == "assigned":
		return _("Asignación"), _("asignó a {u}").format(u=asignado)
	if tipo == "unassigned":
		return _("Asignación quitada"), _("quitó la asignación a {u}").format(u=asignado)
	if tipo == "milestoned":
		return _("Hito"), _("añadió al hito «{h}»").format(h=hito)
	if tipo == "demilestoned":
		return _("Hito quitado"), _("quitó del hito «{h}»").format(h=hito)
	if tipo == "renamed":
		cambio = como_dict(evento.get("rename"))
		return _("Título cambiado"), _("cambió el título de «{a}» a «{b}»").format(a=cambio.get("from", ""), b=cambio.get("to", ""))
	if tipo == "referenced":
		return _("Referencia"), _("la referenció desde el commit {c}").format(c=commit)
	if tipo == "cross-referenced":
		fuente = como_dict(como_dict(evento.get("source")).get("issue"))
		repo = como_dict(fuente.get("repository")).get("full_name", "")
		que = _("el pull request") if fuente.get("pull_request") else _("la issue")
		return _("Mención"), _("la mencionó en {q} {r}#{n}: {t}").format(q=que, r=repo, n=fuente.get("number", ""), t=fuente.get("title", ""))
	if tipo == "committed":
		return _("Commit"), f"{(evento.get('sha') or '')[:7]} {f.primera_linea(evento.get('message'))}".strip()
	if tipo == "merged":
		return _("Fusionado"), _("fusionó el commit {c}").format(c=commit) if commit else _("fusionó")
	if tipo == "head_ref_deleted":
		return _("Rama borrada"), _("borró la rama")
	if tipo == "head_ref_restored":
		return _("Rama restaurada"), _("restauró la rama")
	if tipo == "head_ref_force_pushed":
		return _("Envío forzado"), _("forzó un envío a la rama")
	if tipo == "base_ref_changed":
		return _("Rama base cambiada"), _("cambió la rama base")
	if tipo == "review_requested":
		quien = _login(evento.get("requested_reviewer")) or como_dict(evento.get("requested_team")).get("name", "")
		return _("Revisión pedida"), _("pidió revisión a {u}").format(u=quien)
	if tipo == "review_request_removed":
		quien = _login(evento.get("requested_reviewer")) or como_dict(evento.get("requested_team")).get("name", "")
		return _("Petición de revisión quitada"), _("retiró la petición de revisión a {u}").format(u=quien)
	if tipo == "review_dismissed":
		return _("Revisión descartada"), _("descartó una revisión")
	if tipo == "ready_for_review":
		return _("Lista para revisión"), _("la marcó como lista para revisión")
	if tipo == "convert_to_draft":
		return _("Borrador"), _("la volvió a borrador")
	if tipo == "locked":
		motivo = _MOTIVOS_BLOQUEO.get(evento.get("lock_reason") or "", "")
		return _("Bloqueada"), (_("bloqueó la conversación ({m})").format(m=_(motivo)) if motivo else _("bloqueó la conversación"))
	if tipo == "unlocked":
		return _("Desbloqueada"), _("desbloqueó la conversación")
	if tipo == "pinned":
		return _("Fijada"), _("la fijó en el repositorio")
	if tipo == "unpinned":
		return _("Desfijada"), _("la quitó de las fijadas")
	if tipo == "transferred":
		return _("Transferida"), _("la transfirió desde otro repositorio")
	if tipo == "marked_as_duplicate":
		return _("Duplicada"), _("la marcó como duplicada")
	if tipo == "unmarked_as_duplicate":
		return _("No duplicada"), _("quitó la marca de duplicada")
	if tipo == "comment_deleted":
		return _("Comentario borrado"), _("borró un comentario")
	if tipo == "auto_merge_enabled":
		return _("Fusión automática"), _("activó la fusión automática")
	if tipo == "auto_merge_disabled":
		return _("Fusión automática"), _("desactivó la fusión automática")
	if tipo in ("connected", "disconnected"):
		return _("Vínculo"), _("vinculó una issue o un pull request") if tipo == "connected" else _("quitó un vínculo")
	if tipo in ("added_to_project", "added_to_project_v2", "moved_columns_in_project", "removed_from_project",
		"removed_from_project_v2", "project_v2_item_status_changed"):
		return _("Proyecto"), _("cambió su lugar en un proyecto")
	if tipo == "deployed":
		return _("Despliegue"), _("se desplegó")
	return tipo or _("Evento"), tipo.replace("_", " ")


def elemento_evento(evento: dict, usuario: str) -> ElementoConversacion | None:
	"""Elemento de un evento de la cronología (``None`` si se ignora)."""
	tipo = evento.get("event") or ""
	if tipo in EVENTOS_IGNORADOS:
		return None
	if tipo == "commented":
		return elemento_comentario(evento, usuario)
	if tipo == "reviewed":
		cuerpo = evento.get("body") or ""
		estado = f.estado(evento.get("state")) or _("Comentada")
		return ElementoConversacion(
			REVISION, _login(evento.get("user")), evento.get("submitted_at") or "", _("Revisión: {e}").format(e=estado),
			f.primera_linea(cuerpo) or _("(revisión sin texto)"), cuerpo, evento.get("id"), evento.get("html_url") or "",
			bool(usuario) and (evento.get("user") or {}).get("login") == usuario, {}, evento,
		)
	if tipo == "committed":
		autor = como_dict(evento.get("author"))
		titulo, resumen = describir_evento(evento)
		return ElementoConversacion(
			EVENTO, autor.get("name") or "", autor.get("date") or como_dict(evento.get("committer")).get("date") or "",
			titulo, resumen, evento.get("message") or "", None, evento.get("html_url") or "", False, {}, evento,
		)
	titulo, resumen = describir_evento(evento)
	url = ""
	if tipo == "cross-referenced":
		url = como_dict(como_dict(evento.get("source")).get("issue")).get("html_url", "")
	return ElementoConversacion(
		EVENTO, _login(evento.get("actor")), evento.get("created_at") or "", titulo, resumen, "", evento.get("id"), url,
		False, {}, evento,
	)


def construir_elementos(issue: dict, comentarios: Sequence[dict], cronologia: Sequence[dict], usuario: str = "") -> list[ElementoConversacion]:
	"""Descripción + comentarios + eventos, en orden cronológico.

	Los comentarios de la cronología (``commented``) que ya vinieron en la lista
	de comentarios no se repiten.
	"""
	elementos = []
	ids = set()
	for comentario in comentarios:
		if isinstance(comentario, dict):
			elementos.append(elemento_comentario(comentario, usuario))
			ids.add(comentario.get("id"))
	for evento in cronologia:
		if not isinstance(evento, dict):
			continue
		if evento.get("event") == "commented" and evento.get("id") in ids:
			continue
		elemento = elemento_evento(evento, usuario)
		if elemento is not None:
			elementos.append(elemento)
	elementos.sort(key=lambda e: marca_tiempo(e.fecha))
	return [elemento_descripcion(issue, usuario), *elementos]


def texto_informacion(issue: dict, extra: Sequence[str] = ()) -> str:
	"""Resumen de la issue o del PR para la zona «Información»."""
	es_pr = bool(issue.get("pull_request") or issue.get("head"))
	cabecera = _("Pull request #{n}: {t}") if es_pr else _("Issue #{n}: {t}")
	lineas = [
		cabecera.format(n=issue.get("number", ""), t=issue.get("title", "")),
		_("Estado: {e}").format(e=f.estado_issue(issue)),
		_("Autor: {a}").format(a=f.login(issue.get("user"))),
		_("Etiquetas: {e}").format(e=f.etiquetas(issue) or "-"),
		_("Asignados: {a}").format(a=f.asignados(issue) or "-"),
		_("Hito: {h}").format(h=como_dict(issue.get("milestone")).get("title") or "-"),
		_("Reacciones: {r}").format(r=f.reacciones(issue.get("reactions")) or "-"),
		_("Comentarios: {c}").format(c=issue.get("comments", 0)),
	]
	if issue.get("locked"):
		motivo = _MOTIVOS_BLOQUEO.get(issue.get("active_lock_reason") or "", "")
		lineas.append(_("Conversación bloqueada") + (f" ({_(motivo)})" if motivo else ""))
	fechas = _("Creada: {c}; actualizada: {a}").format(c=f.fecha_completa(issue.get("created_at")), a=f.fecha_completa(issue.get("updated_at")))
	if issue.get("closed_at"):
		fechas += "; " + _("cerrada: {c}").format(c=f.fecha_completa(issue.get("closed_at")))
	lineas.append(fechas)
	lineas.extend(extra)
	lineas.append(_("Enlace: {u}").format(u=issue.get("html_url", "")))
	return "\n".join(lineas)


def texto_completo(elemento: ElementoConversacion) -> str:
	"""Lo que se muestra en el campo «Texto» del elemento enfocado."""
	cabecera = f"{elemento.tipo}. {elemento.autor or _('(desconocido)')}, {f.fecha_completa(elemento.fecha)}"
	partes = [cabecera, ""]
	if elemento.clase == EVENTO:
		partes.append(elemento.resumen)
		if elemento.texto and elemento.texto != elemento.resumen:
			partes += ["", elemento.texto]
	else:
		partes.append(elemento.texto.strip() or _("(sin texto)"))
	reacciones = f.reacciones(elemento.reacciones)
	if reacciones:
		partes += ["", _("Reacciones: {r}").format(r=reacciones)]
	if elemento.url:
		partes += ["", elemento.url]
	return "\n".join(partes)


# ════════════════════════════════════════════════════════════════════════════
# Piezas comunes de interfaz
# ════════════════════════════════════════════════════════════════════════════


def ventana_superior(padre: wx.Window | None) -> wx.Window | None:
	"""La ventana de nivel superior de ``padre`` (un panel no puede ser dueño de un marco)."""
	if padre is None or not padre:
		return None
	return padre if isinstance(padre, wx.TopLevelWindow) else wx.GetTopLevelParent(padre)


def enfocar(control: wx.Window) -> None:
	"""Pone el foco en ``control`` solo si su ventana está a la vista (en una oculta no sirve de nada)."""
	if control and control.IsShownOnScreen():
		control.SetFocus()


def ejecutar_seguro(ventana: wx.Window, funcion: Callable[[], Any]) -> None:
	"""Ejecuta una acción de menú o botón; un fallo se registra y se explica, la ventana sigue viva."""
	try:
		funcion()
	except Exception as error:  # noqa: BLE001 - se registra y se muestra; la ventana no debe caerse
		log.exception("Fallo en una acción de la ventana de detalle")
		mostrar_error(ventana, mensaje_error(error), _("Error"))


def crear_lista(padre: wx.Window, contexto: Any, etiqueta: str, columnas: Sequence[tuple[str, int]], sizer: wx.Sizer,
	ayuda: str = "", proporcion: int = 1) -> ListaAccesible:
	"""Etiqueta y, JUSTO DESPUÉS, una ``ListaAccesible`` con lectura por columnas."""
	texto = wx.StaticText(padre, label=etiqueta)
	lista = ListaAccesible(
		padre, nombre=nombre_limpio(etiqueta), columnas=[(t, padre.FromDIP(a)) for t, a in columnas],
		leer_preferencias=preferencias_lectura(contexto.config),
	)
	if ayuda:
		lista.SetHelpText(ayuda)
	sizer.Add(texto, 0, wx.LEFT | wx.RIGHT | wx.TOP, 4)
	sizer.Add(lista, proporcion, wx.EXPAND | wx.ALL, 4)
	return lista


def crear_texto(padre: wx.Window, etiqueta: str, sizer: wx.Sizer, valor: str = "", alto: int = 120, proporcion: int = 0,
	ayuda: str = "", editable: bool = False) -> wx.TextCtrl:
	"""Etiqueta y campo multilínea (de solo lectura salvo ``editable``) con texto íntegro (TE_RICH2)."""
	texto = wx.StaticText(padre, label=etiqueta)
	estilo = wx.TE_MULTILINE | wx.TE_RICH2 | (0 if editable else wx.TE_READONLY)
	campo = wx.TextCtrl(padre, value=valor, style=estilo, size=(-1, padre.FromDIP(alto)))
	campo.SetHelpText(ayuda or _("Texto de solo lectura: recórralo con las flechas; Control+A y Control+C lo copian."))
	sizer.Add(texto, 0, wx.LEFT | wx.RIGHT | wx.TOP, 4)
	sizer.Add(campo, proporcion, wx.EXPAND | wx.ALL, 4)
	return campo


def crear_boton(padre: wx.Window, etiqueta: str, funcion: Callable[[], Any], ayuda: str, sizer: wx.Sizer) -> wx.Button:
	boton = wx.Button(padre, label=etiqueta)
	boton.SetHelpText(ayuda)
	boton.Bind(wx.EVT_BUTTON, lambda _e: ejecutar_seguro(padre, funcion))
	sizer.Add(boton, 0, wx.ALL, 3)
	return boton


ElementoMenu = tuple[str, str, Callable[[], Any]] | tuple[str, str, Callable[[], Any], str] | None


def crear_menu_acciones(ventana: wx.Frame, titulo: str, elementos: Sequence[ElementoMenu]) -> dict[str, wx.MenuItem]:
	"""Barra de menús con un menú de acciones. ``elementos``: ``(clave, etiqueta, función[, ayuda])`` o ``None``.

	Los atajos van en la etiqueta tras un tabulador (``"Act&ualizar\\tF5"``): el
	lector los anuncia al recorrer el menú. Devuelve los elementos por clave
	para habilitarlos o cambiar su texto según el estado.
	"""
	menu = wx.Menu()
	items: dict[str, wx.MenuItem] = {}
	for elemento in elementos:
		if elemento is None:
			menu.AppendSeparator()
			continue
		clave, etiqueta, funcion = elemento[0], elemento[1], elemento[2]
		ayuda = elemento[3] if len(elemento) > 3 else ""
		item = menu.Append(wx.ID_ANY, etiqueta, ayuda)
		ventana.Bind(wx.EVT_MENU, lambda _e, fn=funcion: ejecutar_seguro(ventana, fn), item)
		items[clave] = item
	barra = wx.MenuBar()
	barra.Append(menu, titulo)
	ventana.SetMenuBar(barra)
	return items


def cambiar_etiqueta(item: wx.MenuItem | None, etiqueta: str) -> None:
	"""Cambia el texto de un elemento de menú conservando su atajo."""
	if item is None:
		return
	atajo = item.GetItemLabel().partition("\t")[2]
	item.SetItemLabel(etiqueta + (f"\t{atajo}" if atajo else ""))


class VentanaDetalle(wx.Frame):
	"""Ventana no modal de detalle (issue, PR, archivo, perfil, organización).

	- Si ya hay una ventana con la misma clave, ``traer_al_frente`` la muestra.
	- Ctrl+W cierra (lo pone cada ventana en su menú); Escape NO cierra.
	- Ctrl+H dice la ayuda del control enfocado.
	- Sonido «abrir» al mostrarse y «cerrar» al cerrarse.
	"""

	_abiertas: dict[str, VentanaDetalle] = {}

	def __init__(self, padre: wx.Window | None, contexto: Any, clave: str, titulo: str, tamano: tuple[int, int] = (1000, 720)) -> None:
		super().__init__(ventana_superior(padre), title=titulo, size=tamano)
		self.ctx = contexto
		self.clave = clave
		self.padre_original = padre
		VentanaDetalle._abiertas[clave] = self
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		habilitar_ayuda_contextual(self)

	@classmethod
	def abierta(cls, clave: str) -> VentanaDetalle | None:
		ventana = cls._abiertas.get(clave)
		if ventana is not None and not ventana:
			cls._abiertas.pop(clave, None)
			return None
		return ventana

	@classmethod
	def traer_al_frente(cls, clave: str) -> bool:
		"""Si ya hay una ventana con esa clave, la trae al frente y devuelve ``True``."""
		ventana = cls.abierta(clave)
		if ventana is None:
			return False
		ventana.ctx.sonar("abrir")
		if not ventana.IsShown():
			return True  # aún no se ha mostrado (se está creando): no hay nada que traer
		if ventana.IsIconized():
			ventana.Iconize(False)
		ventana.Raise()
		ventana.enfocar_inicio()
		return True

	def mostrar(self) -> None:
		self.Show()
		self.Raise()
		self.ctx.sonar("abrir")
		self.enfocar_inicio()

	def enfocar_inicio(self) -> None:
		"""Pone el foco en el control principal (cada ventana lo redefine)."""

	def cargar(self) -> None:
		"""Pide los datos (cada ventana lo redefine)."""

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if VentanaDetalle._abiertas.get(self.clave) is self:
			VentanaDetalle._abiertas.pop(self.clave, None)
		self.ctx.sonar("cerrar")
		evento.Skip()


# ════════════════════════════════════════════════════════════════════════════
# Diálogo de lista no modal
# ════════════════════════════════════════════════════════════════════════════

BotonLista = tuple[str, Callable[["DialogoLista", Any], None], bool]


class DialogoLista(wx.Dialog):
	"""Lista con botones en un diálogo NO modal (se puede abrir un commit y volver).

	:param fila: ``(elemento) -> [textos de las columnas]``.
	:param al_activar: lo que hace Intro (o ``None``).
	:param botones: ``(etiqueta, función(dialogo, elemento), requiere_elemento)``.
	:param recargar: si se da, ``recargar()`` (en un hilo) devuelve los elementos de nuevo.
	"""

	def __init__(self, padre: wx.Window | None, contexto: Any, titulo: str, etiqueta: str, columnas: Sequence[tuple[str, int]],
		fila: Callable[[Any], list[str]], elementos: Sequence[Any] = (), al_activar: Callable[[Any], None] | None = None,
		botones: Sequence[BotonLista] = (), recargar: Callable[[], Any] | None = None, ayuda: str = "") -> None:
		super().__init__(ventana_superior(padre), title=titulo, size=(820, 520), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = contexto
		self._fila = fila
		self._al_activar = al_activar
		self._recargar = recargar
		self._botones = list(botones)
		self.elementos: list[Any] = []
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.lista = crear_lista(self, contexto, etiqueta, columnas, raiz,
			ayuda=ayuda or _("Intro abre el elemento; Aplicaciones o Mayúsculas+F10 muestra las acciones."))
		self.estado = wx.StaticText(self, label="")
		raiz.Add(self.estado, 0, wx.LEFT | wx.RIGHT, 4)
		fila_botones = wx.WrapSizer(wx.HORIZONTAL)
		for etiqueta_boton, funcion, requiere in self._botones:
			crear_boton(self, etiqueta_boton, lambda fn=funcion, r=requiere: self._pulsar(fn, r),
				nombre_limpio(etiqueta_boton) + ".", fila_botones)
		cerrar = wx.Button(self, wx.ID_CANCEL, _("C&errar"))
		cerrar.SetHelpText(_("Cierra esta ventana (también Escape)."))
		cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.Close())
		fila_botones.Add(cerrar, 0, wx.ALL, 3)
		raiz.Add(fila_botones, 0, wx.EXPAND | wx.ALL, 4)
		self.SetSizer(raiz)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self._activar())
		vincular_menu_contextual(self.lista, self._menu)
		self.Bind(wx.EVT_CLOSE, lambda _e: self.Destroy())
		preparar_dialogo(self, foco_inicial=self.lista)
		self.mostrar_elementos(elementos)
		self.CentreOnParent()

	@property
	def elemento(self) -> Any:
		fila = self.lista.fila_actual()
		return self.elementos[fila] if 0 <= fila < len(self.elementos) else None

	def mostrar_elementos(self, elementos: Sequence[Any]) -> None:
		self.elementos = list(elementos)
		filas = []
		for elemento in self.elementos:
			try:
				filas.append(self._fila(elemento))
			except Exception:  # noqa: BLE001 - un dato raro no debe vaciar la lista
				log.debug("Fila de lista no representable", exc_info=True)
				filas.append([str(elemento)])
		self.lista.reemplazar_filas(filas)
		self.estado.SetLabel(_("{n} elementos.").format(n=len(self.elementos)) if self.elementos else _("La lista está vacía."))

	def recargar(self) -> None:
		if self._recargar is None:
			return
		en_segundo_plano(self, self.ctx, self._recargar, sonido="", al_terminar=lambda r: self and self.mostrar_elementos(como_lista(r)))

	def _activar(self) -> None:
		if self._al_activar is not None and self.elemento is not None:
			ejecutar_seguro(self, lambda: self._al_activar(self.elemento))

	def _pulsar(self, funcion: Callable[[DialogoLista, Any], None], requiere: bool) -> None:
		if requiere and self.elemento is None:
			self.ctx.avisar(_("No hay ningún elemento elegido."))
			return
		funcion(self, self.elemento)

	def _menu(self) -> wx.Menu:
		menu = wx.Menu()
		for etiqueta, funcion, requiere in self._botones:
			item = menu.Append(wx.ID_ANY, etiqueta)
			item.Enable(not requiere or self.elemento is not None)
			self.Bind(wx.EVT_MENU, lambda _e, fn=funcion, r=requiere: ejecutar_seguro(self, lambda: self._pulsar(fn, r)), item)
		return menu

	def mostrar(self) -> None:
		self.Show()
		self.ctx.sonar("abrir")
		self.lista.SetFocus()


# ════════════════════════════════════════════════════════════════════════════
# Formulario sencillo
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class Campo:
	"""Un campo de ``DialogoFormulario``.

	:param tipo: ``texto``, ``multilinea``, ``bool``, ``opcion`` (``opciones`` = ``[(valor, texto)]``) o ``secreto``.
	"""

	clave: str
	etiqueta: str
	tipo: str = "texto"
	valor: Any = ""
	opciones: list[tuple[Any, str]] = field(default_factory=list)
	ayuda: str = ""


class DialogoFormulario(wx.Dialog):
	"""Formulario con etiquetas antes de cada campo, Aceptar con nombre propio y Cancelar."""

	def __init__(self, padre: wx.Window | None, titulo: str, campos: Sequence[Campo], etiqueta_aceptar: str = "") -> None:
		super().__init__(ventana_superior(padre), title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.campos = list(campos)
		self.controles: dict[str, wx.Window] = {}
		raiz = wx.BoxSizer(wx.VERTICAL)
		primero = None
		for campo in self.campos:
			if campo.tipo == "bool":
				control = wx.CheckBox(self, label=campo.etiqueta)
				control.SetValue(bool(campo.valor))
				raiz.Add(control, 0, wx.ALL, 6)
			elif campo.tipo == "opcion":
				raiz.Add(wx.StaticText(self, label=campo.etiqueta), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
				control = wx.Choice(self, choices=[t for _v, t in campo.opciones])
				valores = [v for v, _t in campo.opciones]
				control.SetSelection(valores.index(campo.valor) if campo.valor in valores else 0)
				raiz.Add(control, 0, wx.EXPAND | wx.ALL, 6)
			else:
				raiz.Add(wx.StaticText(self, label=campo.etiqueta), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
				estilo = {"multilinea": wx.TE_MULTILINE | wx.TE_RICH2, "secreto": wx.TE_PASSWORD}.get(campo.tipo, 0)
				control = wx.TextCtrl(self, value=str(campo.valor or ""), style=estilo,
					size=(self.FromDIP(460), self.FromDIP(110) if campo.tipo == "multilinea" else -1))
				raiz.Add(control, 1 if campo.tipo == "multilinea" else 0, wx.EXPAND | wx.ALL, 6)
			control.SetHelpText(campo.ayuda or nombre_limpio(campo.etiqueta) + ".")
			self.controles[campo.clave] = control
			primero = primero or control
		raiz.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		if etiqueta_aceptar:
			self.FindWindow(wx.ID_OK).SetLabel(etiqueta_aceptar)
		self.SetSizerAndFit(raiz)
		preparar_dialogo(self, foco_inicial=primero)
		self.CentreOnParent()

	def valores(self) -> dict[str, Any]:
		resultado: dict[str, Any] = {}
		for campo in self.campos:
			control = self.controles[campo.clave]
			if isinstance(control, wx.CheckBox):
				resultado[campo.clave] = control.GetValue()
			elif isinstance(control, wx.Choice):
				indice = control.GetSelection()
				resultado[campo.clave] = campo.opciones[indice][0] if 0 <= indice < len(campo.opciones) else None
			else:
				resultado[campo.clave] = control.GetValue()
		return resultado


def pedir_formulario(padre: wx.Window | None, titulo: str, campos: Sequence[Campo], etiqueta_aceptar: str = "") -> dict | None:
	"""Muestra el formulario de forma modal. Devuelve los valores o ``None`` si se cancela."""
	dialogo = DialogoFormulario(padre, titulo, campos, etiqueta_aceptar)
	try:
		return dialogo.valores() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Panel de conversación
# ════════════════════════════════════════════════════════════════════════════


class PanelConversacion(wx.Panel):
	"""Información, conversación (lista) y texto del elemento enfocado de una issue o un PR.

	:param al_cargar: se llama con el diccionario de la issue cada vez que se carga.
	"""

	def __init__(self, padre: wx.Window, contexto: Any, nombre: str, numero: int,
		al_cargar: Callable[[dict], None] | None = None) -> None:
		super().__init__(padre)
		self.ctx = contexto
		self.nombre = nombre
		self.numero = int(numero)
		self.al_cargar = al_cargar
		self.issue: dict = {}
		self.elementos: list[ElementoConversacion] = []
		self.info_extra: list[str] = []
		self.cargando = False
		self.cargado = False
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.info = crear_texto(self, _("&Información:"), raiz, alto=110,
			ayuda=_("Título, estado, autor, etiquetas, asignados, hito, reacciones y fechas. Solo lectura."))
		self.lista = crear_lista(self, contexto, _("C&onversación:"),
			[(_("Autor"), 140), (_("Fecha"), 130), (_("Tipo"), 150), (_("Texto"), 460)], raiz,
			ayuda=_(
				"Descripción, comentarios, revisiones y eventos en orden. Intro: ver formateado. Control+N: comentar. "
				"Control+R: responder citando. F2: editar mi comentario. Suprimir: borrar mi comentario. "
				"Control+E: reaccionar. Control+C: copiar. Control+B: abrir en el navegador. F5: actualizar. "
				"Izquierda y derecha leen las columnas; el texto completo está en el campo Texto."
			))
		self.texto = crear_texto(self, _("&Texto:"), raiz, alto=160, proporcion=1,
			ayuda=_("Texto completo del elemento elegido en la conversación. Se actualiza al moverse por la lista."))
		self.estado = wx.StaticText(self, label="")
		raiz.Add(self.estado, 0, wx.LEFT | wx.RIGHT, 4)
		botones = wx.WrapSizer(wx.HORIZONTAL)
		for etiqueta, funcion, ayuda in self._acciones():
			crear_boton(self, etiqueta.partition("\t")[0], funcion, ayuda, botones)
		raiz.Add(botones, 0, wx.EXPAND | wx.ALL, 4)
		self.SetSizer(raiz)
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, self._al_enfocar)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: ejecutar_seguro(self, self.ver_html))
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_pulsar)
		vincular_menu_contextual(self.lista, self._menu)

	# ── Acciones ──────────────────────────────────────────────────────────────

	def _acciones(self) -> list[tuple[str, Callable[[], Any], str]]:
		"""(etiqueta con atajo, función, ayuda). Botones y menú contextual comparten la lista."""
		return [
			(_("Co&mentar…\tCtrl+N"), self.comentar, _("Escribe un comentario nuevo en Markdown.")),
			(_("Responder &citando…\tCtrl+R"), self.responder_citando, _("Comentario nuevo que cita el elemento elegido.")),
			(_("&Editar mi comentario…\tF2"), self.editar_mio, _("Edita el comentario elegido, si es suyo.")),
			(_("&Borrar mi comentario\tSupr"), self.borrar_mio, _("Borra el comentario elegido, si es suyo (pide confirmación).")),
			(_("Reacciona&r…\tCtrl+E"), self.reaccionar, _("Añade una reacción (me gusta, corazón, cohete...) al elemento elegido.")),
			(_("Ver en &HTML\tIntro"), self.ver_html, _("Muestra el elemento formateado, con encabezados y enlaces navegables.")),
			(_("Co&piar\tCtrl+C"), self.copiar, _("Copia el texto completo del elemento elegido.")),
			(_("Abrir en el &navegador\tCtrl+B"), self.abrir_navegador, _("Abre el elemento elegido en el navegador web.")),
			(_("Act&ualizar\tF5"), self.cargar, _("Vuelve a pedir la conversación a GitHub.")),
		]

	def _menu(self) -> wx.Menu:
		menu = wx.Menu()
		for etiqueta, funcion, ayuda in self._acciones():
			item = menu.Append(wx.ID_ANY, etiqueta, ayuda)
			self.Bind(wx.EVT_MENU, lambda _e, fn=funcion: ejecutar_seguro(self, fn), item)
		return menu

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla, mods = evento.GetKeyCode(), evento.GetModifiers()
		acciones = {
			(wx.MOD_CONTROL, ord("N")): self.comentar,
			(wx.MOD_CONTROL, ord("R")): self.responder_citando,
			(wx.MOD_NONE, wx.WXK_F2): self.editar_mio,
			(wx.MOD_NONE, wx.WXK_DELETE): self.borrar_mio,
			(wx.MOD_CONTROL, ord("E")): self.reaccionar,
			(wx.MOD_CONTROL, ord("C")): self.copiar,
			(wx.MOD_CONTROL, ord("B")): self.abrir_navegador,
			(wx.MOD_NONE, wx.WXK_F5): self.cargar,
		}
		accion = acciones.get((mods, tecla))
		if accion is None:
			evento.Skip()
			return
		ejecutar_seguro(self, accion)

	# ── Datos ─────────────────────────────────────────────────────────────────

	@property
	def elemento(self) -> ElementoConversacion | None:
		fila = self.lista.fila_actual()
		return self.elementos[fila] if 0 <= fila < len(self.elementos) else None

	def cargar(self) -> None:
		"""Pide la issue, sus comentarios y su cronología en segundo plano."""
		if self.cargando:
			return
		self.cargando = True
		self.estado.SetLabel(_("Cargando la conversación…"))
		api = self.ctx.api()
		nombre, numero = self.nombre, self.numero

		def trabajo() -> tuple[dict, list, list]:
			issue = como_dict(api.issue(nombre, numero))
			comentarios = como_lista(api.comentarios(nombre, numero))
			try:
				cronologia = como_lista(api.cronologia(nombre, numero))
			except Exception:  # noqa: BLE001 - sin cronología se ve igualmente la conversación
				log.warning("No se pudo leer la cronología de %s#%s", nombre, numero, exc_info=True)
				cronologia = []
			return issue, comentarios, cronologia

		def fallado(error: BaseException) -> None:
			if not self:
				return
			self.cargando = False
			mensaje = mensaje_error(error)
			self.estado.SetLabel(_("No se pudo cargar: {m}").format(m=mensaje))
			self.ctx.avisar(_("No se pudo cargar la conversación: {m}").format(m=mensaje))

		en_segundo_plano(self, self.ctx, trabajo, sonido="", al_terminar=self._recibir, al_fallar=fallado)

	def _recibir(self, resultado: tuple[dict, list, list]) -> None:
		if not self:
			return
		issue, comentarios, cronologia = resultado
		self.mostrar(issue, comentarios, cronologia)
		if self.al_cargar is not None:
			self.al_cargar(self.issue)

	def mostrar(self, issue: dict, comentarios: Sequence[dict], cronologia: Sequence[dict]) -> None:
		"""Pinta la conversación conservando el elemento en el que estaba la persona."""
		anterior = self.elemento.clave if self.elemento is not None else None
		primera_vez = not self.cargado
		self.cargando = False
		self.cargado = True
		self.issue = como_dict(issue)
		self.elementos = construir_elementos(self.issue, comentarios, cronologia, self.ctx.usuario)
		relativas = self.ctx.relativas()
		filas = [[e.autor, f.fecha(e.fecha, relativas), e.tipo, e.resumen] for e in self.elementos]
		self.lista.reemplazar_filas(filas, conservar_foco=False)
		claves = [e.clave for e in self.elementos]
		if anterior in claves:
			self.lista.enfocar_fila(claves.index(anterior), anunciar=False)
		self.pintar_informacion()
		self.actualizar_texto()
		comentarios_n = sum(1 for e in self.elementos if e.clase == COMENTARIO)
		eventos_n = len(self.elementos) - comentarios_n - 1
		self.estado.SetLabel(_("{c} comentarios y {e} eventos.").format(c=comentarios_n, e=eventos_n))
		if primera_vez:
			self.ctx.sonar("listo")

	def pintar_informacion(self) -> None:
		if self.issue:
			self.info.ChangeValue(texto_informacion(self.issue, self.info_extra))

	def establecer_extra(self, lineas: Sequence[str]) -> None:
		"""Líneas añadidas a «Información» (ramas, fusionable... en un PR)."""
		self.info_extra = list(lineas)
		self.pintar_informacion()

	def actualizar_texto(self) -> None:
		"""Muestra en «Texto» el elemento enfocado (sin mover el foco)."""
		elemento = self.elemento
		self.texto.ChangeValue(texto_completo(elemento) if elemento is not None else "")
		self.texto.SetInsertionPoint(0)

	def _al_enfocar(self, evento: wx.ListEvent) -> None:
		evento.Skip()
		self.actualizar_texto()

	# ── Acciones sobre la conversación ────────────────────────────────────────

	def _requiere(self, condicion: Callable[[ElementoConversacion], bool], mensaje: str) -> ElementoConversacion | None:
		elemento = self.elemento
		if elemento is None:
			self.ctx.avisar(_("No hay ningún elemento elegido."))
			return None
		if not condicion(elemento):
			self.ctx.sonar("aviso")
			self.ctx.avisar(mensaje)
			return None
		return elemento

	def _enviar_comentario(self, cuerpo_inicial: str = "", contexto_texto: str = "") -> None:
		api = self.ctx.api()
		nombre, numero = self.nombre, self.numero

		def enviar(valores: dict) -> Any:
			cuerpo = (valores.get("cuerpo") or "").strip()
			if not cuerpo:
				raise ValueError(_("El comentario está vacío."))
			return api.comentar(nombre, numero, cuerpo)

		resultado = editor.editar(self, self.ctx, _("Comentar en #{n} de {r}").format(n=numero, r=nombre), enviar,
			cuerpo=cuerpo_inicial, etiqueta_enviar=_("&Enviar comentario"), texto_contexto=contexto_texto)
		if resultado is not None:
			self.cargar()

	def comentar(self) -> None:
		self._enviar_comentario()

	def responder_citando(self) -> None:
		elemento = self._requiere(lambda e: e.tiene_texto, _("Este elemento no tiene texto que citar."))
		if elemento is None:
			return
		cita = (f"@{elemento.autor} " + _("escribió:") + "\n\n" if elemento.autor else "") + citar(elemento.texto)
		self._enviar_comentario(cita, elemento.texto)

	def editar_mio(self) -> None:
		elemento = self._requiere(lambda e: e.propio and e.clase in (COMENTARIO, DESCRIPCION),
			_("Solo puede editar sus propios comentarios y descripciones."))
		if elemento is None:
			return
		api = self.ctx.api()
		nombre, numero = self.nombre, self.numero

		def enviar(valores: dict) -> Any:
			cuerpo = valores.get("cuerpo") or ""
			if elemento.clase == DESCRIPCION:
				return api.editar_issue(nombre, numero, body=cuerpo)
			if not cuerpo.strip():
				raise ValueError(_("El comentario está vacío."))
			return api.editar_comentario(nombre, elemento.id, cuerpo)

		titulo = _("Editar la descripción") if elemento.clase == DESCRIPCION else _("Editar mi comentario")
		if editor.editar(self, self.ctx, titulo, enviar, cuerpo=elemento.texto, etiqueta_enviar=_("&Guardar")) is not None:
			self.cargar()

	def borrar_mio(self) -> None:
		elemento = self._requiere(lambda e: e.propio and e.clase == COMENTARIO, _("Solo puede borrar sus propios comentarios."))
		if elemento is None:
			return
		pregunta = _("¿Borrar su comentario del {f}? No se puede deshacer.\n\n{t}").format(
			f=f.fecha_completa(elemento.fecha), t=f.resumen_texto(elemento.texto, 200))
		if not confirmar_peligro(self, pregunta, _("Borrar comentario")):
			return
		api = self.ctx.api()
		en_segundo_plano(self, self.ctx, lambda: api.borrar_comentario(self.nombre, elemento.id), exito=_("Comentario borrado."),
			al_terminar=lambda _r: self and self.cargar())

	def reaccionar(self) -> None:
		from app.services.github.api import REACCIONES

		elemento = self._requiere(lambda e: e.clase in (COMENTARIO, DESCRIPCION),
			_("Solo se puede reaccionar a la descripción y a los comentarios."))
		if elemento is None:
			return
		claves = list(REACCIONES)
		eleccion = elegir_uno(self, _("Reaccionar"), _("&Reacción:"), [_(REACCIONES[c]) for c in claves])
		if eleccion is None:
			return
		reaccion = claves[eleccion]
		api = self.ctx.api()
		if elemento.clase == DESCRIPCION:
			trabajo = lambda: api.reaccionar_issue(self.nombre, self.numero, reaccion)  # noqa: E731
		else:
			trabajo = lambda: api.reaccionar_comentario(self.nombre, elemento.id, reaccion)  # noqa: E731
		en_segundo_plano(self, self.ctx, trabajo, exito=_("Reacción «{r}» añadida.").format(r=_(REACCIONES[reaccion])),
			al_terminar=lambda _r: self and self.cargar())

	def ver_html(self) -> None:
		from app.ui import visor_ayuda

		elemento = self.elemento
		if elemento is None:
			return
		markdown = elemento.texto if elemento.tiene_texto else elemento.resumen
		titulo = _("{t} de {a} en #{n}").format(t=elemento.tipo, a=elemento.autor or _("(desconocido)"), n=self.numero)
		visor_ayuda.mostrar_documento(self, titulo, f"# {titulo}\n\n{markdown}")

	def copiar(self) -> None:
		elemento = self.elemento
		if elemento is not None:
			copiar(self.ctx, elemento.texto if elemento.tiene_texto else texto_completo(elemento))

	def abrir_navegador(self) -> None:
		elemento = self.elemento
		url = (elemento.url if elemento is not None else "") or self.issue.get("html_url", "")
		if url:
			webbrowser.open(url)
		else:
			self.ctx.avisar(_("Este elemento no tiene enlace."))

