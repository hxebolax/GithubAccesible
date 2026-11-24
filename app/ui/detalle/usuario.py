"""Ventana del perfil de una persona: datos, fijados, contribuciones, repositorios, seguidores...

Pestañas (Ctrl+Tab): Resumen (datos, elementos fijados y contribuciones),
Repositorios, Con estrella, Actividad, Seguidores, Seguidos, Gists y
Organizaciones. Las listas son
las mismas de toda la aplicación (Intro abre, F5 actualiza, Ctrl+F filtra,
Aplicaciones muestra las acciones).

Botones: Seguir o dejar de seguir (Alt+S), Bloquear o desbloquear (Alt+B),
Leer el README del perfil (Alt+M), Abrir en el navegador (Alt+N). En el perfil propio, en su lugar: Editar mi
perfil (Alt+E) y Correos (Alt+C). Menú «Acciones» (Alt+A) con lo mismo, F5
para actualizar y Ctrl+W para cerrar.

Si el «usuario» resulta ser una organización, se abre su ventana propia.
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from typing import Any

import wx

from app.services import formato as f
from app.ui import abrir
from app.ui.comunes import confirmar, confirmar_peligro, elegir_uno, en_segundo_plano, mensaje_error, pedir_texto
from app.ui.detalle.conversacion import (
	Campo,
	DialogoLista,
	VentanaDetalle,
	cambiar_etiqueta,
	como_dict,
	como_lista,
	crear_boton,
	crear_lista,
	crear_menu_acciones,
	crear_texto,
	ejecutar_seguro,
	pedir_formulario,
)
from app.ui.vistas.base import Accion, Columna, DefinicionVista, PanelLista, url_html

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def clave_usuario(login: str) -> str:
	return f"usuario:{login.lower()}"


# ════════════════════════════════════════════════════════════════════════════
# Funciones puras
# ════════════════════════════════════════════════════════════════════════════


def texto_perfil(usuario: dict, contribuciones: dict | None = None) -> str:
	"""Datos del perfil y resumen de contribuciones, en líneas fáciles de escuchar."""
	lineas = [
		_("{l} ({n})").format(l=usuario.get("login", ""), n=usuario.get("name")) if usuario.get("name") else usuario.get("login", ""),
		_("Tipo: {t}").format(t=_("Organización") if usuario.get("type") == "Organization" else _("Persona")),
	]
	for clave, etiqueta in (("bio", _("Biografía")), ("company", _("Empresa")), ("location", _("Ubicación")),
		("email", _("Correo")), ("blog", _("Web")), ("twitter_username", _("Twitter o X"))):
		if usuario.get(clave):
			lineas.append(f"{etiqueta}: {usuario[clave]}")
	if usuario.get("hireable"):
		lineas.append(_("Disponible para contratar."))
	lineas.append(_("Repositorios públicos: {r}; gists públicos: {g}").format(r=usuario.get("public_repos", 0), g=usuario.get("public_gists", 0)))
	lineas.append(_("Seguidores: {s}; sigue a: {g}").format(s=usuario.get("followers", 0), g=usuario.get("following", 0)))
	lineas.append(_("En GitHub desde: {f}").format(f=f.fecha_completa(usuario.get("created_at"))))
	contribuciones = contribuciones or {}
	if contribuciones:
		total = como_dict(contribuciones.get("contributionCalendar")).get("totalContributions", 0)
		lineas.append(_("Contribuciones del último año: {t} (commits: {c}; issues: {i}; pull requests: {p}; revisiones: {r}; "
			"repositorios creados: {n})").format(
			t=total, c=contribuciones.get("totalCommitContributions", 0), i=contribuciones.get("totalIssueContributions", 0),
			p=contribuciones.get("totalPullRequestContributions", 0), r=contribuciones.get("totalPullRequestReviewContributions", 0),
			n=contribuciones.get("totalRepositoryContributions", 0)))
	lineas.append(_("Enlace: {u}").format(u=usuario.get("html_url", "")))
	return "\n".join(lineas)


# ════════════════════════════════════════════════════════════════════════════
# Vistas de lista del perfil
# ════════════════════════════════════════════════════════════════════════════


def _vista_repositorios() -> DefinicionVista:
	from app.ui.vistas.principales import acciones_repositorio, columnas_repositorio, completar_repositorios, detalle_repositorio

	def cargar(api, pagina, panel):
		login = panel.datos["login"]
		if login == panel.ctx.usuario:
			return api.mis_repositorios(pagina, tipo="owner")
		return api.repositorios_de(login, pagina)

	return DefinicionVista("perfil_repositorios", _("Repositorios"), columnas_repositorio(), cargar,
		lambda p, r: abrir.repositorio(p.ctx, r.get("full_name", "")), acciones_repositorio(), _("No tiene repositorios públicos."),
		url_html, detalle_repositorio, completar=completar_repositorios)


def _vista_estrellas() -> DefinicionVista:
	from app.ui.vistas.principales import acciones_repositorio, columnas_repositorio, completar_repositorios, detalle_repositorio

	return DefinicionVista("perfil_estrellas", _("Con estrella"), columnas_repositorio(),
		lambda api, pagina, panel: api.con_estrella(panel.datos["login"], pagina),
		lambda p, r: abrir.repositorio(p.ctx, r.get("full_name", "")), acciones_repositorio(),
		_("No ha dado estrella a ningún repositorio público."), url_html, detalle_repositorio, completar=completar_repositorios)


def _vista_actividad() -> DefinicionVista:
	"""Actividad pública de la persona: las mismas filas y acciones que «Inicio»."""
	from dataclasses import replace

	from app.ui.vistas.principales import vista_inicio

	return replace(vista_inicio(), id="perfil_actividad", titulo=_("Actividad"),
		cargar=lambda api, pagina, panel: api.eventos_de(panel.datos["login"], pagina),
		texto_vacio=_("No hay actividad pública reciente."))


def _vista_personas(seguidores: bool) -> DefinicionVista:
	def cargar(api, pagina, panel):
		login = panel.datos["login"]
		return api.seguidores(login, pagina) if seguidores else api.seguidos(login, pagina)

	return DefinicionVista(
		"perfil_seguidores" if seguidores else "perfil_seguidos", _("Seguidores") if seguidores else _("Seguidos"),
		[Columna("login", _("Usuario"), lambda u, c: u.get("login", ""), 220),
			Columna("tipo", _("Tipo"), lambda u, c: _("Organización") if u.get("type") == "Organization" else _("Persona"), 120)],
		cargar, lambda p, u: abrir.usuario(p.ctx, p, u.get("login", "")),
		[Accion(_("&Ver perfil"), lambda p, u: abrir.usuario(p.ctx, p, u.get("login", "")), "Intro")],
		_("La lista está vacía."), url_html,
	)


def _vista_gists() -> DefinicionVista:
	return DefinicionVista(
		"perfil_gists", _("Gists"),
		[
			Columna("descripcion", _("Descripción"), lambda g, c: g.get("description") or _("(sin descripción)"), 300),
			Columna("archivos", _("Archivos"), lambda g, c: ", ".join((g.get("files") or {}).keys()), 220),
			Columna("visibilidad", _("Visibilidad"), lambda g, c: _("Público") if g.get("public") else _("Secreto"), 80),
			Columna("actualizado", _("Actualizado"), lambda g, c: f.fecha(g.get("updated_at"), c.relativas()), 120),
		],
		lambda api, pagina, panel: api.gists_de(panel.datos["login"], pagina),
		lambda p, g: abrir.gist(p.ctx, p, g.get("id", "")),
		[Accion(_("&Abrir"), lambda p, g: abrir.gist(p.ctx, p, g.get("id", "")), "Intro")],
		_("No tiene gists públicos."), url_html,
	)


def _abrir_org(panel: Any, org: dict) -> None:
	from app.ui.detalle.organizacion import abrir_organizacion

	abrir_organizacion(panel.ctx, panel, org.get("login", ""))


def _vista_organizaciones() -> DefinicionVista:
	return DefinicionVista(
		"perfil_organizaciones", _("Organizaciones"),
		[Columna("nombre", _("Organización"), lambda o, c: o.get("login", ""), 200),
			Columna("descripcion", _("Descripción"), lambda o, c: o.get("description") or "", 360)],
		lambda api, pagina, panel: api.organizaciones_de(panel.datos["login"]),
		_abrir_org, [Accion(_("&Abrir"), _abrir_org, "Intro")],
		_("No pertenece a ninguna organización pública."), url=lambda o: f"https://github.com/{o.get('login', '')}", paginada=False,
	)


# ════════════════════════════════════════════════════════════════════════════
# Ventana
# ════════════════════════════════════════════════════════════════════════════


class VentanaUsuario(VentanaDetalle):
	def __init__(self, padre: wx.Window | None, contexto: Any, login: str) -> None:
		super().__init__(padre, contexto, clave_usuario(login), _("Perfil de {l}").format(l=login), (1000, 720))
		self.login = login
		self.propio = bool(contexto.usuario) and login.lower() == contexto.usuario.lower()
		self.usuario: dict = {}
		self.fijados: list[dict] = []
		self.sigo = False
		self.bloqueado = False
		elementos: list = []
		if not self.propio:
			elementos += [("seguir", _("&Seguir"), self.seguir), ("bloquear", _("&Bloquear…"), self.bloquear)]
		else:
			elementos += [("perfil", _("&Editar mi perfil…"), self.editar_perfil), ("correos", _("&Correos…"), self.correos)]
		elementos += [
			("readme", _("Leer el READ&ME del perfil"), self.leer_readme),
			("navegador",_("Abrir en el &navegador\tCtrl+Shift+B"), self.abrir_navegador),
			None,
			("actualizar", _("Act&ualizar\tF5"), self.actualizar),
			("cerrar", _("Cerrar la &ventana\tCtrl+W"), self.Close),
		]
		self.menu = crear_menu_acciones(self, _("&Acciones"), elementos)
		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.libro = wx.Notebook(panel)
		self.libro.SetHelpText(_("Pestañas del perfil. Control+Tabulador pasa a la siguiente."))
		self.libro.AddPage(self._crear_resumen(), _("Resumen"))
		self.paneles: dict[int, PanelLista] = {}
		for definicion, etiqueta, titulo in (
			(_vista_repositorios(), _("&Repositorios:"), _("Repositorios")),
			(_vista_estrellas(), _("Con es&trella:"), _("Con estrella")),
			(_vista_actividad(), _("Acti&vidad:"), _("Actividad")),
			(_vista_personas(True), _("Se&guidores:"), _("Seguidores")),
			(_vista_personas(False), _("Segui&dos:"), _("Seguidos")),
			(_vista_gists(), _("G&ists:"), _("Gists")),
			(_vista_organizaciones(), _("&Organizaciones:"), _("Organizaciones")),
		):
			lista = PanelLista(self.libro, contexto, definicion, {"login": login}, etiqueta=etiqueta)
			self.paneles[self.libro.GetPageCount()] = lista
			self.libro.AddPage(lista, titulo)
		self.libro.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._al_cambiar_pagina)
		raiz.Add(self.libro, 1, wx.EXPAND | wx.ALL, 2)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_seguir = self.boton_bloquear = None
		if not self.propio:
			self.boton_seguir = crear_boton(panel, _("&Seguir"), self.seguir, _("Sigue o deja de seguir a esta persona."), botones)
			self.boton_bloquear = crear_boton(panel, _("&Bloquear…"), self.bloquear,
				_("Bloquea o desbloquea a esta persona: no podrá interactuar con sus repositorios."), botones)
		else:
			crear_boton(panel, _("&Editar mi perfil…"), self.editar_perfil, _("Cambia nombre, biografía, web, empresa y ubicación."), botones)
			crear_boton(panel, _("&Correos…"), self.correos, _("Correos de la cuenta: añadir, quitar y visibilidad."), botones)
		crear_boton(panel, _("Leer el READ&ME del perfil"), self.leer_readme,
			_("Abre con formato la presentación que la persona tiene en su perfil (el README del repositorio con su nombre)."), botones)
		crear_boton(panel, _("Abrir en el &navegador"), self.abrir_navegador, _("Abre el perfil en la web de GitHub."), botones)
		raiz.Add(botones, 0, wx.ALL, 2)
		panel.SetSizer(raiz)

	def _crear_resumen(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.datos = crear_texto(pagina, _("&Datos:"), sizer, alto=200, proporcion=1,
			ayuda=_("Datos del perfil y contribuciones del último año. Solo lectura."))
		self.lista_fijados = crear_lista(pagina, self.ctx, _("&Fijados:"), [(_("Nombre"), 260), (_("Descripción"), 420), (_("Estrellas"), 80)],
			sizer, ayuda=_("Repositorios y gists fijados en el perfil. Intro los abre."))
		self.lista_fijados.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: ejecutar_seguro(self, self.abrir_fijado))
		pagina.SetSizer(sizer)
		return pagina

	def enfocar_inicio(self) -> None:
		self.datos.SetFocus()

	# ── Carga ─────────────────────────────────────────────────────────────────

	def cargar(self) -> None:
		api = self.ctx.api()
		login = self.login
		propio = self.propio

		def trabajo() -> dict:
			resultado: dict[str, Any] = {"usuario": como_dict(api.usuario(login)), "fijados": [], "contribuciones": {},
				"sigo": False, "bloqueado": False}
			if resultado["usuario"].get("type") == "Organization":
				return resultado
			for clave, funcion in (("fijados", lambda: como_lista(api.fijados(login))),
				("contribuciones", lambda: como_dict(api.contribuciones(login)))):
				try:
					resultado[clave] = funcion()
				except Exception:  # noqa: BLE001 - lo de GraphQL es complementario: el perfil se ve igual
					log.warning("No se pudo leer %s de %s", clave, login, exc_info=True)
			if not propio:
				try:
					resultado["sigo"] = bool(api.sigo_a(login))
					resultado["bloqueado"] = any(como_dict(b).get("login") == login for b in como_lista(api.bloqueados()))
				except Exception:  # noqa: BLE001 - sin permiso para ver bloqueados: se asume que no
					log.warning("No se pudo saber si se sigue o se bloquea a %s", login, exc_info=True)
			return resultado

		def fallo(error: BaseException) -> None:
			if self:
				self.datos.ChangeValue(_("No se pudo cargar el perfil: {m}").format(m=mensaje_error(error)))
				self.ctx.avisar(self.datos.GetValue())

		en_segundo_plano(self, self.ctx, trabajo, sonido="", al_terminar=self._recibir, al_fallar=fallo)
		self._cargar_pagina(self.libro.GetSelection())

	def _recibir(self, resultado: dict) -> None:
		if not self:
			return
		self.usuario = resultado["usuario"]
		if self.usuario.get("type") == "Organization":
			from app.ui.detalle.organizacion import abrir_organizacion

			padre = self.padre_original
			wx.CallAfter(self.Close)
			wx.CallAfter(abrir_organizacion, self.ctx, padre, self.login)
			return
		self.fijados = [como_dict(x) for x in resultado["fijados"]]
		self.sigo, self.bloqueado = resultado["sigo"], resultado["bloqueado"]
		self.SetTitle(_("Perfil de {l}").format(l=self.usuario.get("login") or self.login)
			+ (f" ({self.usuario['name']})" if self.usuario.get("name") else ""))
		self.datos.ChangeValue(texto_perfil(self.usuario, resultado["contribuciones"]))
		self.datos.SetInsertionPoint(0)
		self.lista_fijados.reemplazar_filas([
			[x.get("nameWithOwner") or x.get("name", ""), x.get("description") or "",
				str(x.get("stargazerCount", "")) if "stargazerCount" in x else _("(gist)")] for x in self.fijados
		])
		self._actualizar_botones()
		self.ctx.sonar("listo")

	def leer_readme(self) -> None:
		"""El README del perfil es el del repositorio «login/login»: lo primero que se ve en la web."""
		from app.ui import visor_ayuda

		api = self.ctx.api()
		login = self.usuario.get("login") or self.login

		def mostrar(texto: str) -> None:
			if not texto or not texto.strip():
				self.ctx.avisar(_("El README del perfil está vacío."))
				return
			visor_ayuda.mostrar_documento(self, _("Presentación de {l}").format(l=login), texto)

		def fallo(error: BaseException) -> None:
			if getattr(error, "codigo_http", None) == 404:
				self.ctx.avisar(_("{l} no tiene README en su perfil.").format(l=login))
			else:
				self.ctx.sonar("error")
				self.ctx.avisar(_("No se pudo leer el README del perfil: {m}").format(m=mensaje_error(error)))

		en_segundo_plano(self, self.ctx, lambda: api.readme(f"{login}/{login}"), al_terminar=mostrar, al_fallar=fallo, sonido="")

	def _actualizar_botones(self) -> None:
		if self.propio:
			return
		seguir = _("Dejar de &seguir") if self.sigo else _("&Seguir")
		bloquear = _("Des&bloquear") if self.bloqueado else _("&Bloquear…")
		self.boton_seguir.SetLabel(seguir)
		self.boton_bloquear.SetLabel(bloquear)
		cambiar_etiqueta(self.menu.get("seguir"), seguir)
		cambiar_etiqueta(self.menu.get("bloquear"), bloquear)

	def _al_cambiar_pagina(self, evento: wx.BookCtrlEvent) -> None:
		evento.Skip()
		self._cargar_pagina(evento.GetSelection())

	def _cargar_pagina(self, indice: int) -> None:
		panel = self.paneles.get(indice)
		if panel is not None:
			panel.cargar_si_hace_falta()

	def actualizar(self) -> None:
		"""F5: el perfil y la lista de la pestaña visible."""
		panel = self.paneles.get(self.libro.GetSelection())
		if panel is not None:
			panel.cargar()
		self.cargar()

	# ── Acciones ──────────────────────────────────────────────────────────────

	def abrir_fijado(self) -> None:
		fila = self.lista_fijados.fila_actual()
		if not 0 <= fila < len(self.fijados):
			return
		fijado = self.fijados[fila]
		if fijado.get("nameWithOwner"):
			abrir.repositorio(self.ctx, fijado["nameWithOwner"])
		elif fijado.get("url"):
			webbrowser.open(fijado["url"])

	def seguir(self) -> None:
		api = self.ctx.api()
		dejar = self.sigo

		def hecho(_r: Any) -> None:
			self.sigo = not dejar
			self._actualizar_botones()

		en_segundo_plano(self, self.ctx, lambda: api.dejar_de_seguir(self.login) if dejar else api.seguir(self.login),
			exito=(_("Ha dejado de seguir a {l}.") if dejar else _("Ahora sigue a {l}.")).format(l=self.login), al_terminar=hecho)

	def bloquear(self) -> None:
		api = self.ctx.api()
		desbloquear = self.bloqueado
		if not desbloquear and not confirmar_peligro(self, _(
			"¿Bloquear a {l}? No podrá seguirle, comentar en sus repositorios ni mencionarle.").format(l=self.login), _("Bloquear")):
			return

		def hecho(_r: Any) -> None:
			self.bloqueado = not desbloquear
			self._actualizar_botones()

		en_segundo_plano(self, self.ctx, lambda: api.desbloquear(self.login) if desbloquear else api.bloquear(self.login),
			exito=(_("{l} desbloqueado.") if desbloquear else _("{l} bloqueado.")).format(l=self.login), al_terminar=hecho)

	def abrir_navegador(self) -> None:
		webbrowser.open(self.usuario.get("html_url") or f"https://{self.ctx.host}/{self.login}")

	def editar_perfil(self) -> None:
		u = self.usuario
		valores = pedir_formulario(self, _("Editar mi perfil"), [
			Campo("name", _("&Nombre:"), valor=u.get("name") or ""),
			Campo("email", _("Correo &público:"), valor=u.get("email") or "",
				ayuda=_("Debe ser uno de sus correos verificados; vacío para no mostrar ninguno.")),
			Campo("blog", _("&Web o blog:"), valor=u.get("blog") or ""),
			Campo("twitter_username", _("&Twitter o X:"), valor=u.get("twitter_username") or ""),
			Campo("company", _("&Empresa:"), valor=u.get("company") or ""),
			Campo("location", _("&Ubicación:"), valor=u.get("location") or ""),
			Campo("bio", _("&Biografía:"), "multilinea", u.get("bio") or ""),
			Campo("hireable", _("&Disponible para contratar"), "bool", bool(u.get("hireable"))),
		], _("&Guardar"))
		if valores is None:
			return
		api = self.ctx.api()
		en_segundo_plano(self, self.ctx, lambda: api.actualizar_perfil(**valores), exito=_("Perfil guardado."),
			al_terminar=lambda _r: self and self.cargar())

	def correos(self) -> None:
		api = self.ctx.api()

		def anadir(dialogo: DialogoLista, _elemento: Any) -> None:
			correo = pedir_texto(dialogo, _("&Correo nuevo:"), _("Añadir correo"))
			if correo and "@" in correo:
				en_segundo_plano(dialogo, self.ctx, lambda: api.anadir_correos([correo.strip()]),
					exito=_("Correo añadido. GitHub le enviará un mensaje para verificarlo."), al_terminar=lambda _r: dialogo and dialogo.recargar())

		def quitar(dialogo: DialogoLista, correo: dict) -> None:
			if correo.get("primary"):
				self.ctx.avisar(_("No se puede quitar el correo principal."))
				return
			if confirmar(dialogo, _("¿Quitar el correo {c} de la cuenta?").format(c=correo.get("email", "")), _("Quitar correo"),
				peligroso=True) != wx.ID_YES:
				return
			en_segundo_plano(dialogo, self.ctx, lambda: api.borrar_correos([correo.get("email", "")]), exito=_("Correo quitado."),
				al_terminar=lambda _r: dialogo and dialogo.recargar())

		def visibilidad(dialogo: DialogoLista, _elemento: Any) -> None:
			opciones = [("public", _("Público: el correo principal se puede ver")), ("private", _("Privado: no se muestra"))]
			eleccion = elegir_uno(dialogo, _("Visibilidad del correo"), _("&Visibilidad del correo principal:"), [t for _v, t in opciones])
			if eleccion is not None:
				en_segundo_plano(dialogo, self.ctx, lambda: api.visibilidad_correo(opciones[eleccion][0]), exito=_("Visibilidad cambiada."),
					al_terminar=lambda _r: dialogo and dialogo.recargar())

		def mostrar(lista: Any) -> None:
			DialogoLista(
				self, self.ctx, _("Correos de la cuenta"), _("C&orreos:"),
				[(_("Correo"), 300), (_("Principal"), 90), (_("Verificado"), 90), (_("Visibilidad"), 100)],
				lambda c: [c.get("email", ""), f.si_no(c.get("primary")), f.si_no(c.get("verified")), f.estado(c.get("visibility")) or "-"],
				[como_dict(c) for c in como_lista(lista)],
				botones=[(_("&Añadir…"), anadir, False), (_("&Quitar"), quitar, True), (_("Cambiar la &visibilidad…"), visibilidad, False)],
				recargar=api.correos,
			).mostrar()

		en_segundo_plano(self, self.ctx, api.correos, sonido="", al_terminar=mostrar)


def abrir_usuario(ctx: Any, padre: wx.Window | None, login: str) -> None:
	"""Abre la ventana del perfil de ``login`` (o trae al frente la que ya esté abierta)."""
	login = (login or "").strip()
	if not login:
		return
	if VentanaDetalle.traer_al_frente(clave_usuario(login)):
		return
	ventana = VentanaUsuario(padre, ctx, login)
	ventana.mostrar()
	ventana.cargar()
