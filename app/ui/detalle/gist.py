"""Gists: ventana de un gist y diálogo para crear uno nuevo.

Ventana de un gist (``abrir_gist``):

- «Información»: descripción, autor, visibilidad, fechas, comentarios y enlace.
- «Archivos»: nombre, lenguaje y tamaño; al moverse por ellos su contenido
  aparece en «Contenido del archivo» (solo lectura, sin ajuste de línea).
- Intro edita el archivo, F2 lo renombra, Supr lo borra, Ctrl+N añade otro.
- Descripción, estrella (Ctrl+S), bifurcar, historial de revisiones,
  comentarios (Ctrl+M), copiar el enlace (Ctrl+Mayús+C), copiar la URL para
  clonar (Ctrl+K), abrir en el navegador (Ctrl+B) y borrar el gist.

Nuevo gist (``nuevo_gist``): descripción, público o secreto y uno o varios
archivos (nombre y contenido) con «Añadir otro archivo» y «Cargar desde disco».
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx

from app.services import formato as f
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.comunes import (
	confirmar_peligro,
	copiar,
	elegir_uno,
	en_segundo_plano,
	mensaje_error,
	mostrar_error,
	mostrar_mensaje,
	pedir_texto,
)
from app.ui.detalle.comun_detalle import VentanaDetalle, elegir_archivos, entrada_cerrar
from app.ui.editor import CampoExtra, editar
from app.ui.vistas.base import preferencias_lectura

log = logging.getLogger(__name__)

TAMANO_MAXIMO_DISCO = 1024 * 1024


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def texto_informacion(gist: dict) -> str:
	lineas = [
		_("Descripción: {d}").format(d=gist.get("description") or _("(sin descripción)")),
		_("Autor: {a}").format(a=f.login(gist.get("owner"))),
		_("Visibilidad: {v}").format(v=_("Público") if gist.get("public") else _("Secreto")),
		_("Archivos: {n}").format(n=len(gist.get("files") or {})),
		_("Comentarios: {c}").format(c=gist.get("comments", 0)),
		_("Creado: {c}; actualizado: {a}").format(c=f.fecha_completa(gist.get("created_at")), a=f.fecha_completa(gist.get("updated_at"))),
		_("Enlace: {u}").format(u=gist.get("html_url") or ""),
	]
	if gist.get("fork_of"):
		lineas.append(_("Bifurcación de: {u}").format(u=(gist.get("fork_of") or {}).get("html_url", "")))
	return "\n".join(lineas)


def leer_archivo_texto(ruta: str) -> str:
	"""Contenido de un archivo de texto (UTF-8, o Latin-1 si no lo es). ``ValueError`` si es binario o enorme."""
	datos = Path(ruta).read_bytes()
	if len(datos) > TAMANO_MAXIMO_DISCO:
		raise ValueError(_("El archivo {n} ocupa más de 1 MB.").format(n=Path(ruta).name))
	if b"\x00" in datos:
		raise ValueError(_("El archivo {n} no es de texto.").format(n=Path(ruta).name))
	try:
		return datos.decode("utf-8-sig")
	except UnicodeDecodeError:
		return datos.decode("latin-1")


# ════════════════════════════════════════════════════════════════════════════
# Ventana de un gist
# ════════════════════════════════════════════════════════════════════════════


class VentanaGist(VentanaDetalle):
	def __init__(self, ctx: Any, padre: wx.Window | None, id_gist: str) -> None:
		super().__init__(padre, ctx, _("Gist {i}").format(i=id_gist), clave=f"gist:{id_gist}", tamano=(980, 720))
		self.id_gist = id_gist
		self.gist: dict = {}
		self.nombres: list[str] = []
		self._construir()

	def _construir(self) -> None:
		self.info = self.crear_texto(_("&Información:"), alto=120)
		self.lista = self.crear_lista(_("&Archivos:"), _("Archivos"), [(_("Nombre"), 280), (_("Lenguaje"), 120), (_("Tamaño"), 100)],
			proporcion=1, ayuda=_("Intro edita el archivo; F2 lo renombra; Supr lo borra; Control+N añade otro."))
		self.contenido = self.crear_texto(_("&Contenido del archivo:"), alto=260, proporcion=2, sin_ajuste=True)
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda e: (e.Skip(), self._mostrar_contenido()))
		self.teclas_de_lista(self.lista, {"F2": self.renombrar_archivo, "Supr": self.borrar_archivo}, al_activar=self.editar_archivo)
		self.menu_contextual(self.lista, lambda: self._entradas_archivo()[:4])
		self.poner_menus([(_("&Gist"), [
			*self._entradas_archivo(),
			None,
			(_("Editar la &descripción…"), self.editar_descripcion),
			(_("Poner o quitar la e&strella\tCtrl+S"), self.estrella),
			(_("Bi&furcar (fork)"), self.bifurcar),
			(_("&Historial de revisiones…"), self.historial),
			(_("C&omentarios…\tCtrl+M"), self.comentarios),
			None,
			(_("&Copiar el enlace\tCtrl+Shift+C"), self.copiar_enlace),
			(_("Copiar la &URL para clonar\tCtrl+K"), self.copiar_url_clonar),
			(_("Abrir en el &navegador\tCtrl+B"), self.abrir_navegador),
			(_("Borrar el &gist…"), self.borrar_gist),
			(_("Ac&tualizar\tF5"), lambda: self.cargar()),
			entrada_cerrar(self, _("Cerrar la &ventana\tCtrl+W")),
		])])

	def _entradas_archivo(self) -> list:
		return [
			(_("&Editar el archivo… (Intro)"), self.editar_archivo),
			(_("&Renombrar el archivo… (F2)"), self.renombrar_archivo),
			(_("&Borrar el archivo… (Supr)"), self.borrar_archivo),
			(_("&Añadir un archivo…\tCtrl+N"), self.anadir_archivo),
		]

	# ── Datos ─────────────────────────────────────────────────────────────────

	def cargar(self, anunciar: bool = True) -> None:
		api = self.ctx.api()

		def listo(gist: dict) -> None:
			self.poner_gist(gist)
			if anunciar:
				self.ctx.sonar("listo")

		self.en_fondo(lambda: api.gist(self.id_gist), al_terminar=listo, sonido="")

	def poner_gist(self, gist: dict) -> None:
		elegido = self.archivo_actual
		self.gist = dict(gist or {})
		archivos = self.gist.get("files") or {}
		self.nombres = list(archivos.keys())
		self.info.SetValue(texto_informacion(self.gist))
		self.lista.reemplazar_filas([[n, archivos[n].get("language") or "", f.tamano(archivos[n].get("size"))] for n in self.nombres],
			conservar_foco=True)
		if elegido in self.nombres:
			self.lista.enfocar_fila(self.nombres.index(elegido), anunciar=False)
		elif self.nombres and self.lista.fila_actual() == wx.NOT_FOUND:
			self.lista.enfocar_fila(0, anunciar=False)
		self.SetTitle(_("Gist: {d}").format(d=f.primera_linea(self.gist.get("description"), 80) or self.nombres[0] if self.nombres
			else self.id_gist))
		self._mostrar_contenido()
		self.estado(_("{n} archivos.").format(n=len(self.nombres)))

	@property
	def archivo_actual(self) -> str | None:
		fila = self.lista.fila_actual() if hasattr(self, "lista") else wx.NOT_FOUND
		return self.nombres[fila] if 0 <= fila < len(self.nombres) else None

	def _mostrar_contenido(self) -> None:
		nombre = self.archivo_actual
		if nombre is None:
			self.contenido.SetValue("")
			return
		datos = (self.gist.get("files") or {}).get(nombre) or {}
		if datos.get("truncated") and datos.get("raw_url"):
			self.contenido.SetValue(_("Cargando el archivo completo…"))
			cliente = self.ctx.api().c

			def listo(texto: str) -> None:
				datos["content"], datos["truncated"] = texto, False
				if self.archivo_actual == nombre:
					self.contenido.SetValue(texto)

			# Sin envoltura en la API: el archivo completo se pide con el cliente crudo a su raw_url.
			self.en_fondo(lambda: cliente.texto(datos["raw_url"], "text/plain"), al_terminar=listo, sonido="")
			return
		self.contenido.SetValue(datos.get("content") or "")
		self.contenido.SetInsertionPoint(0)

	def _es_mio(self) -> bool:
		mio = (self.gist.get("owner") or {}).get("login") == self.ctx.usuario
		if not mio:
			self.ctx.avisar(_("Solo quien creó el gist puede cambiarlo. Puede bifurcarlo para tener su propia copia."))
		return mio

	# ── Archivos ──────────────────────────────────────────────────────────────

	def editar_archivo(self) -> None:
		nombre = self.archivo_actual
		if nombre is None or not self._es_mio():
			return
		api = self.ctx.api()
		contenido = ((self.gist.get("files") or {}).get(nombre) or {}).get("content") or ""
		resultado = editar(self, self.ctx, _("Editar {n}").format(n=nombre),
			lambda valores: api.editar_gist(self.id_gist, {nombre: valores["cuerpo"]}),
			cuerpo=contenido, etiqueta_cuerpo=_("C&ontenido del archivo:"), etiqueta_enviar=_("&Guardar"))
		if resultado is not None and self.viva():
			self.poner_gist(resultado)

	def anadir_archivo(self) -> None:
		if not self._es_mio():
			return
		api = self.ctx.api()

		def enviar(valores: dict) -> dict:
			nombre = (valores.get("archivo") or "").strip()
			if not nombre:
				raise ValueError(_("Escriba el nombre del archivo."))
			if nombre in self.nombres:
				raise ValueError(_("Ya hay un archivo llamado {n}.").format(n=nombre))
			if not valores.get("cuerpo", "").strip():
				raise ValueError(_("El archivo no puede estar vacío."))
			return api.editar_gist(self.id_gist, {nombre: valores["cuerpo"]})

		resultado = editar(self, self.ctx, _("Añadir un archivo al gist"), enviar, etiqueta_cuerpo=_("C&ontenido:"),
			etiqueta_enviar=_("&Añadir"), extras=[CampoExtra("archivo", _("&Nombre del archivo:"), "texto", "",
				ayuda=_("Con extensión, por ejemplo notas.md o script.py."))])
		if resultado is not None and self.viva():
			self.poner_gist(resultado)

	def renombrar_archivo(self) -> None:
		nombre = self.archivo_actual
		if nombre is None or not self._es_mio():
			return
		nuevo = pedir_texto(self, _("&Nuevo nombre del archivo:"), _("Renombrar archivo"), nombre)
		if not nuevo or not nuevo.strip() or nuevo.strip() == nombre:
			return
		api = self.ctx.api()
		self.en_fondo(lambda: api.editar_gist(self.id_gist, {}, renombrar={nombre: nuevo.strip()}),
			exito=_("Archivo renombrado."), al_terminar=self.poner_gist)

	def borrar_archivo(self) -> None:
		nombre = self.archivo_actual
		if nombre is None or not self._es_mio():
			return
		if len(self.nombres) <= 1:
			mostrar_error(self, _("Un gist necesita al menos un archivo. Para quitarlo todo, borre el gist."), _("Borrar archivo"))
			return
		if not confirmar_peligro(self, _("¿Borrar el archivo {n} del gist?").format(n=nombre), _("Borrar archivo")):
			return
		api = self.ctx.api()
		self.en_fondo(lambda: api.editar_gist(self.id_gist, {nombre: None}), exito=_("Archivo borrado."), al_terminar=self.poner_gist)

	# ── Gist ──────────────────────────────────────────────────────────────────

	def editar_descripcion(self) -> None:
		if not self._es_mio():
			return
		texto = pedir_texto(self, _("&Descripción del gist:"), _("Editar la descripción"), self.gist.get("description") or "")
		if texto is None:
			return
		api = self.ctx.api()
		self.en_fondo(lambda: api.editar_gist(self.id_gist, {}, descripcion=texto.strip()), exito=_("Descripción cambiada."),
			al_terminar=self.poner_gist)

	def estrella(self) -> None:
		api = self.ctx.api()

		def trabajo() -> bool:
			poner = not api.tiene_estrella_gist(self.id_gist)
			api.estrella_gist(self.id_gist, poner)
			return poner

		self.en_fondo(trabajo, sonido="estrella", exito=lambda puesta: _("Estrella puesta.") if puesta else _("Estrella quitada."))

	def bifurcar(self) -> None:
		api = self.ctx.api()

		def hecho(nuevo: dict) -> None:
			if (nuevo or {}).get("id"):
				abrir_gist(self.ctx, self.GetParent(), nuevo["id"])

		self.en_fondo(lambda: api.bifurcar_gist(self.id_gist), inicio=_("Bifurcando el gist…"),
			exito=_("Bifurcación creada; se abre en otra ventana."), al_terminar=hecho)

	def historial(self) -> None:
		api = self.ctx.api()
		self.en_fondo(lambda: api.historial_gist(self.id_gist), al_terminar=self._elegir_revision, sonido="",
			inicio=_("Cargando el historial…"))

	def _elegir_revision(self, revisiones: list) -> None:
		if not revisiones:
			mostrar_mensaje(self, _("Este gist no tiene revisiones."), _("Historial"))
			return
		opciones = []
		for revision in revisiones:
			cambios = revision.get("change_status") or {}
			opciones.append(_("{f}, {a}: {m} añadidas, {e} eliminadas").format(
				f=f.fecha_completa(revision.get("committed_at")), a=f.login(revision.get("user")),
				m=cambios.get("additions", 0), e=cambios.get("deletions", 0)))
		indice = elegir_uno(self, _("Historial del gist"), _("&Revisiones (Intro muestra su contenido):"), opciones)
		if indice is None:
			return
		version = revisiones[indice].get("version", "")
		cliente = self.ctx.api().c

		def mostrar(datos: dict) -> None:
			partes = []
			for nombre, archivo in ((datos or {}).get("files") or {}).items():
				partes += [f"=== {nombre} ===", archivo.get("content") or "", ""]
			from app.ui.dialogo_texto import DialogoTexto

			dialogo = DialogoTexto(self, _("Revisión {v}").format(v=version[:7]), _("&Contenido de la revisión:"), "\n".join(partes),
				copiable=True)
			try:
				dialogo.ShowModal()
			finally:
				dialogo.Destroy()

		# Sin envoltura en la API: una revisión concreta se pide con el cliente crudo (GET /gists/{id}/{sha}).
		self.en_fondo(lambda: cliente.get(f"/gists/{self.id_gist}/{version}"), al_terminar=mostrar, sonido="")

	def comentarios(self) -> None:
		api = self.ctx.api()

		def mostrar(lista: list) -> None:
			dialogo = DialogoComentariosGist(self, self.ctx, self.id_gist, lista)
			try:
				dialogo.ShowModal()
			finally:
				dialogo.Destroy()

		self.en_fondo(lambda: api.comentarios_gist(self.id_gist), al_terminar=mostrar, sonido="", inicio=_("Cargando los comentarios…"))

	def copiar_enlace(self) -> None:
		if self.gist.get("html_url"):
			copiar(self.ctx, self.gist["html_url"], _("Enlace copiado."))

	def copiar_url_clonar(self) -> None:
		url = self.gist.get("git_pull_url") or (self.gist.get("html_url", "") + ".git" if self.gist.get("html_url") else "")
		if url:
			copiar(self.ctx, url, _("URL para clonar copiada: {u}").format(u=url))

	def abrir_navegador(self) -> None:
		if self.gist.get("html_url"):
			webbrowser.open(self.gist["html_url"])

	def borrar_gist(self) -> None:
		if not self._es_mio():
			return
		if not confirmar_peligro(self, _("¿Borrar el gist «{d}» con todos sus archivos? No se puede deshacer.").format(
			d=self.gist.get("description") or self.id_gist), _("Borrar gist")):
			return
		api = self.ctx.api()
		self.en_fondo(lambda: api.borrar_gist(self.id_gist), exito=_("Gist borrado."), al_terminar=lambda _r: self.Close())


class DialogoComentariosGist(wx.Dialog):
	"""Comentarios de un gist: lista, texto completo, comentar y borrar."""

	def __init__(self, padre: wx.Window | None, ctx: Any, id_gist: str, comentarios: list) -> None:
		super().__init__(padre, title=_("Comentarios del gist"), size=(760, 560), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = ctx
		self.id_gist = id_gist
		self.comentarios: list[dict] = list(comentarios or [])
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=_("&Comentarios:")), 0, wx.LEFT | wx.TOP, 6)
		self.lista = ListaAccesible(self, nombre=_("Comentarios"), columnas=[(_("Autor"), 140), (_("Fecha"), 140), (_("Texto"), 420)],
			leer_preferencias=preferencias_lectura(ctx.config))
		self.lista.SetHelpText(_("Supr borra el comentario; el texto completo está en el campo siguiente."))
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Texto del comentario:")), 0, wx.LEFT | wx.TOP, 6)
		self.texto = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=(-1, 140))
		self.texto.SetHelpText(_("Texto completo del comentario elegido."))
		raiz.Add(self.texto, 1, wx.EXPAND | wx.ALL, 6)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		boton_nuevo = wx.Button(self, label=_("&Nuevo comentario…"))
		boton_nuevo.Bind(wx.EVT_BUTTON, lambda _e: self.comentar())
		boton_borrar = wx.Button(self, label=_("&Borrar el comentario"))
		boton_borrar.Bind(wx.EVT_BUTTON, lambda _e: self.borrar())
		fila.Add(boton_nuevo, 0, wx.RIGHT, 6)
		fila.Add(boton_borrar, 0, wx.RIGHT, 6)
		fila.AddStretchSpacer()
		fila.Add(crear_botonera(self, wx.CLOSE), 0)
		raiz.Add(fila, 0, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(raiz)
		self.FindWindow(wx.ID_CLOSE).Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE))
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda e: (e.Skip(), self._mostrar_texto()))
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_pulsar)
		self._pintar()
		preparar_dialogo(self, id_escape=wx.ID_CLOSE, foco_inicial=self.lista if self.comentarios else boton_nuevo)
		self.CentreOnParent()

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and not evento.HasAnyModifiers():
			self.borrar()
			return
		evento.Skip()

	def _pintar(self) -> None:
		self.lista.reemplazar_filas([[f.login(c.get("user")), f.fecha(c.get("created_at"), self.ctx.relativas()),
			f.primera_linea(c.get("body"))] for c in self.comentarios], conservar_foco=True)
		if self.comentarios and self.lista.fila_actual() == wx.NOT_FOUND:
			self.lista.enfocar_fila(0, anunciar=False)
		self._mostrar_texto()

	def _mostrar_texto(self) -> None:
		fila = self.lista.fila_actual()
		self.texto.SetValue(self.comentarios[fila].get("body") or "" if 0 <= fila < len(self.comentarios) else "")

	def comentar(self) -> None:
		api = self.ctx.api()
		nuevo = editar(self, self.ctx, _("Comentar el gist"), lambda valores: api.comentar_gist(self.id_gist, valores["cuerpo"]),
			etiqueta_cuerpo=_("Te&xto del comentario (Markdown):"), etiqueta_enviar=_("C&omentar"),
			con_adjuntos=True)
		if nuevo:
			self.comentarios.append(nuevo)
			self._pintar()
			self.lista.enfocar_fila(len(self.comentarios) - 1, anunciar=False)
			self.lista.SetFocus()

	def borrar(self) -> None:
		fila = self.lista.fila_actual()
		if not 0 <= fila < len(self.comentarios):
			return
		comentario = self.comentarios[fila]
		if not confirmar_peligro(self, _("¿Borrar el comentario de {a}?").format(a=f.login(comentario.get("user"))), _("Borrar comentario")):
			return
		api = self.ctx.api()

		def hecho(_r: Any) -> None:
			if comentario in self.comentarios:
				self.comentarios.remove(comentario)
			self._pintar()

		en_segundo_plano(self, self.ctx, lambda: api.borrar_comentario_gist(self.id_gist, comentario["id"]),
			exito=_("Comentario borrado."), al_terminar=hecho)


def abrir_gist(ctx: Any, padre: wx.Window | None, id_gist: str) -> wx.Frame:
	"""Abre (o trae al frente) la ventana de un gist y lo carga en segundo plano."""
	clave = f"gist:{id_gist}"
	if VentanaDetalle.abrir_existente(clave):
		return VentanaDetalle._abiertas[clave]
	ventana = VentanaGist(ctx, padre, id_gist)
	ventana.mostrar(ventana.lista)
	ventana.cargar()
	return ventana


# ════════════════════════════════════════════════════════════════════════════
# Nuevo gist
# ════════════════════════════════════════════════════════════════════════════


class DialogoNuevoGist(wx.Dialog):
	"""Descripción, visibilidad y uno o varios archivos. No se cierra si GitHub rechaza la creación."""

	def __init__(self, padre: wx.Window | None, ctx: Any) -> None:
		super().__init__(padre, title=_("Nuevo gist"), size=(760, 640), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = ctx
		self.archivos: list[list[str]] = [["", ""]]
		self.actual = 0
		self.resultado: dict | None = None
		self._creando = False
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=_("&Descripción:")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_descripcion = wx.TextCtrl(self)
		self.campo_descripcion.SetHelpText(_("Descripción breve del gist (opcional)."))
		raiz.Add(self.campo_descripcion, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Visibilidad:")), 0, wx.LEFT | wx.TOP, 6)
		self.selector_visibilidad = wx.Choice(self, choices=[_("Secreto (solo con el enlace)"), _("Público")])
		self.selector_visibilidad.SetSelection(0)
		self.selector_visibilidad.SetHelpText(_("Un gist secreto no aparece en las búsquedas, pero cualquiera con el enlace lo ve."))
		raiz.Add(self.selector_visibilidad, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Archivos del gist:")), 0, wx.LEFT | wx.TOP, 6)
		self.lista_archivos = wx.ListBox(self, choices=[_("(sin nombre)")], style=wx.LB_SINGLE, size=(-1, 90))
		self.lista_archivos.SetSelection(0)
		self.lista_archivos.SetHelpText(_("Archivos que tendrá el gist. Al elegir uno, su nombre y su contenido aparecen debajo."))
		self.lista_archivos.Bind(wx.EVT_LISTBOX, self._al_elegir_archivo)
		raiz.Add(self.lista_archivos, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Nombre del archivo:")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_nombre = wx.TextCtrl(self)
		self.campo_nombre.SetHelpText(_("Con extensión (notas.md, script.py): GitHub la usa para colorear el código."))
		self.campo_nombre.Bind(wx.EVT_TEXT, self._al_cambiar_nombre)
		raiz.Add(self.campo_nombre, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("Con&tenido:")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_contenido = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH2 | wx.TE_DONTWRAP | wx.HSCROLL)
		self.campo_contenido.SetHelpText(_("Contenido del archivo. Control+Intro crea el gist."))
		raiz.Add(self.campo_contenido, 1, wx.EXPAND | wx.ALL, 6)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		for etiqueta, accion, ayuda in (
			(_("Añadir &otro archivo"), self.anadir_archivo, _("Añade un archivo vacío y pone el foco en su nombre.")),
			(_("Car&gar desde disco…"), self.cargar_desde_disco, _("Añade uno o varios archivos de texto del ordenador.")),
			(_("&Quitar este archivo"), self.quitar_archivo, _("Quita del gist el archivo elegido en la lista.")),
		):
			boton = wx.Button(self, label=etiqueta)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, lambda _e, a=accion: a())
			fila.Add(boton, 0, wx.RIGHT, 6)
		raiz.Add(fila, 0, wx.ALL, 6)
		botones = crear_botonera(self, wx.OK | wx.CANCEL)
		self.boton_crear = self.FindWindow(wx.ID_OK)
		self.boton_crear.SetLabel(_("C&rear el gist"))
		raiz.Add(botones, 0, wx.EXPAND | wx.ALL, 8)
		self.estado = wx.StaticText(self, label="")
		raiz.Add(self.estado, 0, wx.LEFT | wx.BOTTOM, 6)
		self.SetSizer(raiz)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.crear(), id=wx.ID_OK)
		preparar_dialogo(self, foco_inicial=self.campo_descripcion)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.CentreOnParent()

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and evento.ControlDown():
			self.crear()
			return
		evento.Skip()

	# ── Archivos en edición ───────────────────────────────────────────────────

	def _guardar_actual(self) -> None:
		if 0 <= self.actual < len(self.archivos):
			self.archivos[self.actual] = [self.campo_nombre.GetValue().strip(), self.campo_contenido.GetValue()]

	def _cargar_actual(self) -> None:
		nombre, contenido = self.archivos[self.actual]
		self.campo_nombre.ChangeValue(nombre)
		self.campo_contenido.SetValue(contenido)
		self.lista_archivos.SetSelection(self.actual)

	def _al_elegir_archivo(self, _evento: wx.CommandEvent | None = None) -> None:
		indice = self.lista_archivos.GetSelection()
		if indice < 0 or indice == self.actual:
			return
		self._guardar_actual()
		self.actual = indice
		self._cargar_actual()

	def _al_cambiar_nombre(self, _evento: wx.CommandEvent) -> None:
		if 0 <= self.actual < self.lista_archivos.GetCount():
			self.lista_archivos.SetString(self.actual, self.campo_nombre.GetValue().strip() or _("(sin nombre)"))

	def anadir_archivo(self, nombre: str = "", contenido: str = "", enfocar: bool = True) -> None:
		self._guardar_actual()
		if len(self.archivos) == 1 and not any(self.archivos[0]):
			self.archivos[0] = [nombre, contenido]
			self.actual = 0
			self.lista_archivos.SetString(0, nombre or _("(sin nombre)"))
		else:
			self.archivos.append([nombre, contenido])
			self.lista_archivos.Append(nombre or _("(sin nombre)"))
			self.actual = len(self.archivos) - 1
		self._cargar_actual()
		if enfocar:
			self.campo_nombre.SetFocus()
			self.ctx.avisar(_("Archivo {n} de {t}.").format(n=self.actual + 1, t=len(self.archivos)))

	def cargar_desde_disco(self, rutas: list[str] | None = None) -> None:
		rutas = rutas if rutas is not None else elegir_archivos(self, _("Elija los archivos de texto que añadir al gist"))
		errores = []
		for ruta in rutas:
			try:
				contenido = leer_archivo_texto(ruta)
			except (OSError, ValueError) as error:
				log.warning("No se pudo cargar %s en el gist: %s", ruta, error)
				errores.append(str(error))
				continue
			self.anadir_archivo(Path(ruta).name, contenido, enfocar=False)
		if errores:
			mostrar_error(self, "\n".join(errores), _("Algunos archivos no se cargaron"))
		if rutas and len(errores) < len(rutas):
			self.ctx.avisar(_("{n} archivos cargados. El gist tiene {t}.").format(n=len(rutas) - len(errores), t=len(self.archivos)))
			self.lista_archivos.SetFocus()

	def quitar_archivo(self) -> None:
		if len(self.archivos) <= 1:
			self.archivos = [["", ""]]
			self.actual = 0
			self.lista_archivos.SetString(0, _("(sin nombre)"))
			self._cargar_actual()
			self.ctx.avisar(_("Archivo vaciado: un gist necesita al menos uno."))
			return
		indice = self.actual
		self.archivos.pop(indice)
		self.lista_archivos.Delete(indice)
		self.actual = min(indice, len(self.archivos) - 1)
		self._cargar_actual()
		self.ctx.avisar(_("Archivo quitado. Quedan {n}.").format(n=len(self.archivos)))

	def comprobar(self) -> tuple[str, int | None]:
		"""Mensaje del primer problema y el índice del archivo afectado («», None si está bien)."""
		self._guardar_actual()
		vistos: set[str] = set()
		for indice, (nombre, contenido) in enumerate(self.archivos):
			if not nombre:
				return _("El archivo {n} no tiene nombre.").format(n=indice + 1), indice
			if nombre in vistos:
				return _("Hay dos archivos llamados {n}.").format(n=nombre), indice
			vistos.add(nombre)
			if not contenido.strip():
				return _("El archivo {n} está vacío: GitHub no admite archivos vacíos en un gist.").format(n=nombre), indice
		return "", None

	def datos(self) -> tuple[dict[str, str], str, bool]:
		self._guardar_actual()
		return ({n: c for n, c in self.archivos}, self.campo_descripcion.GetValue().strip(),
			self.selector_visibilidad.GetSelection() == 1)

	def crear(self) -> None:
		if self._creando:
			return
		mensaje, indice = self.comprobar()
		if mensaje:
			mostrar_error(self, mensaje, _("No se puede crear el gist"))
			if indice is not None:
				self.actual = indice
				self._cargar_actual()
				self.campo_nombre.SetFocus()
			return
		archivos, descripcion, publico = self.datos()
		self._creando = True
		self.boton_crear.Disable()
		self.estado.SetLabel(_("Creando el gist…"))
		api = self.ctx.api()

		def listo(gist: dict) -> None:
			self._creando = False
			self.resultado = dict(gist or {})
			self.ctx.sonar("enviado")
			self.ctx.avisar(_("Gist creado."), interrumpir=False)
			if self and self.IsModal():
				self.EndModal(wx.ID_OK)

		def fallo(error: BaseException) -> None:
			self._creando = False
			if not self:
				return
			self.boton_crear.Enable()
			self.estado.SetLabel("")
			self.ctx.sonar("error")
			mostrar_error(self, mensaje_error(error), _("No se pudo crear el gist"))

		self.ctx.tareas.enviar(lambda tarea: api.crear_gist(archivos, descripcion, publico), al_terminar=listo, al_fallar=fallo,
			nombre="crear_gist", duplicadas="permitir")


def nuevo_gist(padre: wx.Window | None, ctx: Any, al_crear: Callable[[dict], None] | None = None) -> dict | None:
	"""Diálogo para crear un gist. Devuelve el gist creado (o ``None``) y llama a ``al_crear``."""
	dialogo = DialogoNuevoGist(padre, ctx)
	try:
		dialogo.ShowModal()
		gist = dialogo.resultado
	finally:
		dialogo.Destroy()
	if gist and al_crear is not None:
		al_crear(gist)
	return gist
