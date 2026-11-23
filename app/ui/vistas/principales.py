"""Secciones de la ventana principal: definiciones de vista y sus acciones.

Teclas de las listas (las atiende la propia lista, no la ventana, para no
chocar con los cuadros de texto): Intro abre, F2 edita, Supr borra o quita,
F4 cambia el filtro de GitHub, Ctrl+N crea, Ctrl+K clona, Ctrl+S pone o
quita la estrella, Ctrl+L marca como leída, Ctrl+Mayús+R va al repositorio,
Ctrl+Mayús+E abre la carpeta. Las comunes (F5, Ctrl+F, Ctrl+C...) están en
``base.PanelLista.acciones_comunes``.
"""

from __future__ import annotations

import builtins
import logging
import os
import webbrowser
from typing import Any

import wx

from app.services import formato as f
from app.services.github.api_extra import MOTIVOS_NOTIFICACION, TIPOS_SUJETO
from app.ui import abrir
from app.ui.comunes import confirmar_peligro, elegir_uno, en_segundo_plano, mostrar_mensaje
from app.ui.vistas.base import Accion, Columna, DefinicionVista, etiqueta_lista, url_html

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _por_pagina(panel: Any) -> int:
	return int(panel.ctx.config.obtener("listas.por_pagina", 50))


# ════════════════════════════════════════════════════════════════════════════
# Columnas reutilizables
# ════════════════════════════════════════════════════════════════════════════


def columnas_repositorio() -> list[Columna]:
	return [
		Columna("nombre", _("Nombre"), lambda r, c: r.get("full_name", ""), 220),
		Columna("descripcion", _("Descripción"), lambda r, c: r.get("description") or "", 300),
		Columna("visibilidad", _("Visibilidad"), lambda r, c: f.estado(r.get("visibility") or ("private" if r.get("private") else "public")), 90),
		Columna("lenguaje", _("Lenguaje"), lambda r, c: r.get("language") or "", 100),
		Columna("estrellas", _("Estrellas"), lambda r, c: f.numero(r.get("stargazers_count")), 80),
		Columna("bifurcaciones", _("Bifurcaciones"), lambda r, c: f.numero(r.get("forks_count")), 80, visible=False),
		Columna("issues", _("Issues abiertas"), lambda r, c: f.numero(r.get("open_issues_count")), 80, visible=False),
		Columna("actualizado", _("Actualizado"), lambda r, c: f.fecha(r.get("pushed_at") or r.get("updated_at"), c.relativas()), 120),
		Columna("rama", _("Rama principal"), lambda r, c: r.get("default_branch", ""), 100, visible=False),
		Columna("tipo", _("Tipo"), lambda r, c: ", ".join(t for t, s in ((_("bifurcación"), r.get("fork")), (_("archivado"), r.get("archived")), (_("plantilla"), r.get("is_template"))) if s), 120, visible=False),
	]


def detalle_repositorio(r: dict, ctx: Any) -> str:
	lineas = [
		_("Repositorio: {n}").format(n=r.get("full_name", "")),
		_("Descripción: {d}").format(d=r.get("description") or _("(sin descripción)")),
		_("Visibilidad: {v}").format(v=f.estado(r.get("visibility"))),
		_("Lenguaje: {l}").format(l=r.get("language") or "-"),
		_("Estrellas: {e}; bifurcaciones: {b}; observadores: {o}; issues abiertas: {i}").format(
			e=r.get("stargazers_count", 0), b=r.get("forks_count", 0), o=r.get("watchers_count", 0), i=r.get("open_issues_count", 0)),
		_("Rama principal: {r}").format(r=r.get("default_branch", "")),
		_("Tamaño: {t}").format(t=f.tamano((r.get("size") or 0) * 1024)),
		_("Licencia: {l}").format(l=(r.get("license") or {}).get("name") or "-"),
		_("Temas: {t}").format(t=", ".join(r.get("topics") or []) or "-"),
		_("Creado: {c}; último envío: {p}").format(c=f.fecha_completa(r.get("created_at")), p=f.fecha_completa(r.get("pushed_at"))),
		_("Web: {u}").format(u=r.get("homepage") or "-"),
		_("Enlace: {u}").format(u=r.get("html_url", "")),
		_("Clonar por HTTPS: {u}").format(u=r.get("clone_url", "")),
		_("Clonar por SSH: {u}").format(u=r.get("ssh_url", "")),
	]
	if r.get("fork") and r.get("parent"):
		lineas.append(_("Bifurcación de: {p}").format(p=r["parent"].get("full_name")))
	if r.get("archived"):
		lineas.append(_("Archivado (solo lectura)."))
	return "\n".join(lineas)


def columnas_issue(con_repo: bool = True) -> list[Columna]:
	columnas = [
		Columna("numero", _("Número"), lambda i, c: f"#{i.get('number', '')}", 70),
		Columna("titulo", _("Título"), lambda i, c: i.get("title", ""), 360),
	]
	if con_repo:
		columnas.append(Columna("repositorio", _("Repositorio"), lambda i, c: abrir.nombre_repo_de(i), 180))
	columnas += [
		Columna("estado", _("Estado"), lambda i, c: f.estado_issue(i), 90),
		Columna("autor", _("Autor"), lambda i, c: f.login(i.get("user")), 120),
		Columna("comentarios", _("Comentarios"), lambda i, c: str(i.get("comments", 0)), 80),
		Columna("etiquetas", _("Etiquetas"), lambda i, c: f.etiquetas(i), 160),
		Columna("asignados", _("Asignados"), lambda i, c: f.asignados(i), 140, visible=False),
		Columna("hito", _("Hito"), lambda i, c: (i.get("milestone") or {}).get("title", ""), 120, visible=False),
		Columna("actualizado", _("Actualizado"), lambda i, c: f.fecha(i.get("updated_at"), c.relativas()), 120),
		Columna("creado", _("Creado"), lambda i, c: f.fecha(i.get("created_at"), c.relativas()), 120, visible=False),
	]
	return columnas


def detalle_issue(i: dict, ctx: Any) -> str:
	es_pr = bool(i.get("pull_request") or i.get("head"))
	lineas = [
		(_("Pull request #{n}: {t}") if es_pr else _("Issue #{n}: {t}")).format(n=i.get("number"), t=i.get("title", "")),
		_("Repositorio: {r}").format(r=abrir.nombre_repo_de(i)),
		_("Estado: {e}").format(e=f.estado_issue(i)),
		_("Autor: {a}").format(a=f.login(i.get("user"))),
		_("Etiquetas: {e}").format(e=f.etiquetas(i) or "-"),
		_("Asignados: {a}").format(a=f.asignados(i) or "-"),
		_("Hito: {h}").format(h=(i.get("milestone") or {}).get("title") or "-"),
		_("Comentarios: {c}").format(c=i.get("comments", 0)),
		_("Reacciones: {r}").format(r=f.reacciones(i.get("reactions")) or "-"),
		_("Creada: {c}; actualizada: {a}").format(c=f.fecha_completa(i.get("created_at")), a=f.fecha_completa(i.get("updated_at"))),
		_("Enlace: {u}").format(u=i.get("html_url", "")),
		"",
		i.get("body") or _("(sin descripción)"),
	]
	return "\n".join(lineas)


# ════════════════════════════════════════════════════════════════════════════
# Acciones comunes a repositorios
# ════════════════════════════════════════════════════════════════════════════


def _abrir_repo(panel: Any, repo: dict) -> None:
	abrir.repositorio(panel.ctx, repo.get("full_name", ""))


def _clonar(panel: Any, repo: dict) -> None:
	from app.ui.git.clonar import dialogo_clonar

	dialogo_clonar(panel, panel.ctx, repo.get("clone_url", ""), repo.get("full_name", ""))


def _estrella(panel: Any, repo: dict) -> None:
	nombre = repo.get("full_name", "")
	api = panel.ctx.api()

	def trabajo():
		if api.tiene_estrella(nombre):
			api.quitar_estrella(nombre)
			return False
		api.dar_estrella(nombre)
		return True

	en_segundo_plano(panel, panel.ctx, trabajo, sonido="estrella",
		exito=lambda puesta: (_("Estrella puesta a {n}.") if puesta else _("Estrella quitada a {n}.")).format(n=nombre))


def _bifurcar(panel: Any, repo: dict) -> None:
	nombre = repo.get("full_name", "")
	en_segundo_plano(panel, panel.ctx, lambda: panel.ctx.api().bifurcar(nombre), inicio=_("Creando la bifurcación…"),
		exito=lambda r: _("Bifurcación creada: {n}.").format(n=(r or {}).get("full_name", "")))


def _vigilar(panel: Any, repo: dict) -> None:
	from app.ui.repositorio.dialogos import dialogo_vigilancia

	dialogo_vigilancia(panel, panel.ctx, repo.get("full_name", ""))


def _descargar_zip(panel: Any, repo: dict) -> None:
	from app.ui.descarga_codigo import descargar_codigo

	descargar_codigo(panel, panel.ctx, repo.get("full_name", ""), repo.get("default_branch", "") or "")


def acciones_repositorio() -> list[Accion]:
	return [
		Accion(_("A&brir"), _abrir_repo, "Intro"),
		Accion(_("C&lonar…"), _clonar, "Ctrl+K"),
		Accion(_("Poner o quitar la e&strella"), _estrella, "Ctrl+S"),
		Accion(_("Vi&gilar…"), _vigilar),
		Accion(_("Bifurcar (for&k)"), _bifurcar),
		Accion(_("Descargar el código en &zip…"), _descargar_zip,
			ayuda=_("Guarda el código de la rama principal en un archivo zip, sin necesidad de git.")),
		Accion(_("Ver &issues"), lambda p, r: abrir.repositorio(p.ctx, r["full_name"], "issues"), separador_antes=True),
		Accion(_("Ver &pull requests"), lambda p, r: abrir.repositorio(p.ctx, r["full_name"], "prs")),
		Accion(_("Ver Ac&tions"), lambda p, r: abrir.repositorio(p.ctx, r["full_name"], "acciones")),
		Accion(_("Ver &releases"), lambda p, r: abrir.repositorio(p.ctx, r["full_name"], "releases")),
		Accion(_("Ver la &wiki"), lambda p, r: abrir.repositorio(p.ctx, r["full_name"], "wiki"), disponible=lambda p, r: r.get("has_wiki", True)),
		Accion(_("&Ver el propietario"), lambda p, r: abrir.usuario(p.ctx, p, (r.get("owner") or {}).get("login", "")), "Ctrl+Shift+P",
			ayuda=_("Abre el perfil de la persona u organización dueña del repositorio: sus repositorios y el botón Seguir.")),
	]


# ════════════════════════════════════════════════════════════════════════════
# Secciones
# ════════════════════════════════════════════════════════════════════════════


def vista_inicio() -> DefinicionVista:
	def cargar(api, pagina, panel):
		if not panel.ctx.usuario:
			return []
		return api.eventos_recibidos(panel.ctx.usuario, pagina)

	def activar(panel, evento):
		carga = evento.get("payload") or {}
		nombre = (evento.get("repo") or {}).get("name", "")
		objeto = carga.get("issue") or carga.get("pull_request")
		if objeto and objeto.get("number"):
			if carga.get("pull_request") or objeto.get("pull_request"):
				abrir.pull_request(panel.ctx, panel, nombre, objeto["number"])
			else:
				abrir.issue(panel.ctx, panel, nombre, objeto["number"])
		elif evento.get("type") == "ReleaseEvent":
			abrir.repositorio(panel.ctx, nombre, "releases")
		elif nombre:
			abrir.repositorio(panel.ctx, nombre)

	return DefinicionVista(
		"inicio", _("Inicio: actividad de quienes sigue"),
		[
			Columna("descripcion", _("Actividad"), lambda e, c: f.describir_evento(e), 520),
			Columna("fecha", _("Fecha"), lambda e, c: f.fecha(e.get("created_at"), c.relativas()), 120),
			Columna("actor", _("Persona"), lambda e, c: f.login(e.get("actor")), 120, visible=False),
			Columna("repo", _("Repositorio"), lambda e, c: (e.get("repo") or {}).get("name", ""), 180, visible=False),
		],
		cargar, activar,
		[
			Accion(_("Ir al &repositorio"), lambda p, e: abrir.repositorio(p.ctx, (e.get("repo") or {}).get("name", "")), "Ctrl+Shift+R"),
			Accion(_("Ver a la &persona"), lambda p, e: abrir.usuario(p.ctx, p, (e.get("actor") or {}).get("login", ""))),
		],
		texto_vacio=_("No hay actividad reciente de las personas y repositorios que sigue."),
		url=lambda e: f"https://github.com/{(e.get('repo') or {}).get('name', '')}",
	)


def _texto_notificacion(n: dict) -> str:
	return (n.get("subject") or {}).get("title", "")


def vista_notificaciones() -> DefinicionVista:
	def cargar(api, pagina, panel):
		todas = panel.datos.get("todas", False)
		participando = panel.ctx.config.obtener("notificaciones.solo_participando", False)
		return api.notificaciones(todas=todas, participando=participando, numero=pagina)

	def activar(panel, notif):
		abrir.notificacion(panel.ctx, panel, notif)
		if notif.get("unread") and panel.ctx.config.obtener("notificaciones.marcar_leida_al_abrir", True):
			_marcar_leida(panel, notif, anunciar=False)

	def _marcar_leida(panel, notif, anunciar=True):
		api = panel.ctx.api()

		def hecho(_r):
			nueva = dict(notif, unread=False)
			panel.sustituir(notif, nueva)

		en_segundo_plano(panel, panel.ctx, lambda: api.marcar_leida(notif["id"]), al_terminar=hecho,
			sonido="", exito=_("Marcada como leída.") if anunciar else "")

	def marcar_hecha(panel, notif):
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.marcar_hecha(notif["id"]), sonido="",
			al_terminar=lambda _r: panel.quitar(notif), exito=_("Marcada como hecha."))

	def marcar_todas(panel, _e):
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, api.marcar_todas_leidas, exito=_("Todas las notificaciones marcadas como leídas."),
			al_terminar=lambda _r: panel.cargar(anunciar=False))

	def silenciar(panel, notif):
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.silenciar_hilo(notif["id"]), sonido="",
			exito=_("Conversación silenciada: ya no recibirá avisos de ella."))

	def marcar_repo(panel, notif):
		nombre = (notif.get("repository") or {}).get("full_name", "")
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.marcar_repo_leidas(nombre),
			exito=_("Notificaciones de {n} marcadas como leídas.").format(n=nombre), al_terminar=lambda _r: panel.cargar(anunciar=False))

	def al_cambiar(panel):
		# El contador de la lista de secciones («Notificaciones (2)») sigue a lo que se ve
		# aquí al momento, sin esperar al siguiente sondeo. Si quedan páginas sin cargar,
		# lo cargado no basta para contar: se pide un sondeo nuevo.
		ventana = panel.ctx.ventana_principal
		if ventana is None or not hasattr(ventana, "marcar_contador_notificaciones"):
			return
		if panel.hay_mas:
			ventana.comprobar_notificaciones()
		else:
			ventana.marcar_contador_notificaciones(sum(1 for n in panel.elementos if n.get("unread")))

	def cambiar_filtro(panel, _e):
		opciones = [_("Solo no leídas"), _("Todas, también las leídas")]
		eleccion = elegir_uno(panel, _("Filtro de notificaciones"), _("&Mostrar:"), opciones, 1 if panel.datos.get("todas") else 0)
		if eleccion is not None:
			panel.datos["todas"] = eleccion == 1
			panel.cargar()

	return DefinicionVista(
		"notificaciones", _("Notificaciones"),
		[
			Columna("titulo", _("Título"), lambda n, c: _texto_notificacion(n), 380),
			Columna("leida", _("Estado"), lambda n, c: _("No leída") if n.get("unread") else _("Leída"), 80),
			Columna("tipo", _("Tipo"), lambda n, c: _(TIPOS_SUJETO.get((n.get("subject") or {}).get("type", ""), (n.get("subject") or {}).get("type", ""))), 110),
			Columna("repositorio", _("Repositorio"), lambda n, c: (n.get("repository") or {}).get("full_name", ""), 180),
			Columna("motivo", _("Motivo"), lambda n, c: _(MOTIVOS_NOTIFICACION.get(n.get("reason", ""), n.get("reason", ""))), 140),
			Columna("fecha", _("Fecha"), lambda n, c: f.fecha(n.get("updated_at"), c.relativas()), 110),
		],
		cargar, activar,
		[
			Accion(_("Marcar como &leída"), lambda p, n: _marcar_leida(p, n), "Ctrl+L", disponible=lambda p, n: bool(n.get("unread"))),
			Accion(_("Marcar como &hecha (quitar de la bandeja)"), marcar_hecha, "Supr"),
			Accion(_("&Silenciar esta conversación"), silenciar, "Ctrl+Shift+S"),
			Accion(_("Marcar como leídas las de este &repositorio"), marcar_repo),
			Accion(_("Marcar &todas como leídas"), marcar_todas, "Ctrl+Shift+A", requiere_elemento=False, separador_antes=True),
			Accion(_("Cambiar el f&iltro…"), cambiar_filtro, "F4", requiere_elemento=False),
			Accion(_("Ir al re&positorio"), lambda p, n: abrir.repositorio(p.ctx, (n.get("repository") or {}).get("full_name", "")), "Ctrl+Shift+R"),
		],
		texto_vacio=_("No tiene notificaciones pendientes."),
		url=lambda n: f.url_web_de_api((n.get("subject") or {}).get("url")) or "https://github.com/notifications",
		al_cambiar=al_cambiar,
	)


def vista_mis_repositorios() -> DefinicionVista:
	tipos = [("owner", _("Míos")), ("all", _("Todos a los que tengo acceso")), ("member", _("De los que soy miembro")),
		("public", _("Públicos")), ("private", _("Privados"))]

	def cargar(api, pagina, panel):
		if not panel.ctx.usuario:
			return []
		return api.mis_repositorios(pagina, tipo=panel.datos.get("tipo", "owner"))

	def cambiar_filtro(panel, _e):
		actual = [t for t, _n in tipos].index(panel.datos.get("tipo", "owner"))
		eleccion = elegir_uno(panel, _("Filtro de repositorios"), _("&Mostrar:"), [n for _t, n in tipos], actual)
		if eleccion is not None:
			panel.datos["tipo"] = tipos[eleccion][0]
			panel.cargar()

	def nuevo(panel, _e):
		from app.ui.repositorio.dialogos import dialogo_crear_repositorio

		dialogo_crear_repositorio(panel, panel.ctx, al_crear=lambda r: panel.cargar())

	def borrar(panel, repo):
		nombre = repo.get("full_name", "")
		if not confirmar_peligro(panel, _("¿Borrar DEFINITIVAMENTE el repositorio {n}? Se perderá todo: código, issues, "
			"pull requests, wiki y releases. No se puede deshacer.").format(n=nombre), _("Borrar repositorio"), nombre):
			return
		en_segundo_plano(panel, panel.ctx, lambda: panel.ctx.api().borrar_repositorio(nombre),
			exito=_("Repositorio {n} borrado.").format(n=nombre), al_terminar=lambda _r: panel.quitar(repo))

	acciones = acciones_repositorio() + [
		Accion(_("N&uevo repositorio…"), nuevo, "Ctrl+N", requiere_elemento=False, separador_antes=True),
		Accion(_("A&justes y configuración del repositorio…"), lambda p, r: abrir.repositorio(p.ctx, r["full_name"], "configuracion")),
		# Sin letra de acceso a propósito: borrar un repositorio no debe estar a una tecla de distancia.
		Accion(_("Borrar el repositorio…"), borrar, "Supr", disponible=lambda p, r: (r.get("permissions") or {}).get("admin", False)),
		Accion(_("&Cambiar el filtro…"), cambiar_filtro, "F4", requiere_elemento=False),
	]
	return DefinicionVista("repositorios", _("Mis repositorios"), columnas_repositorio(), cargar, _abrir_repo, acciones,
		_("No tiene repositorios. Cree uno con Control+N."), url_html, detalle_repositorio)


def vista_estrellas() -> DefinicionVista:
	return DefinicionVista("estrellas", _("Repositorios con estrella"), columnas_repositorio(),
		lambda api, pagina, panel: api.con_estrella(None, pagina) if panel.ctx.usuario else [],
		_abrir_repo, acciones_repositorio(), _("No ha puesto estrella a ningún repositorio."), url_html, detalle_repositorio)


def vista_vigilados() -> DefinicionVista:
	return DefinicionVista("vigilados", _("Repositorios vigilados"), columnas_repositorio(),
		lambda api, pagina, panel: api.vigilados(pagina) if panel.ctx.usuario else [],
		_abrir_repo, acciones_repositorio(), _("No vigila ningún repositorio."), url_html, detalle_repositorio)


FILTROS_ISSUES = [
	("assigned", N_("Asignadas a mí")), ("created", N_("Creadas por mí")), ("mentioned", N_("Donde me mencionan")),
	("subscribed", N_("A las que estoy suscrito")), ("repos", N_("De mis repositorios")), ("all", N_("Todas las que me afectan")),
]
ESTADOS = [("open", N_("Abiertas")), ("closed", N_("Cerradas")), ("all", N_("Todas"))]


def _elegir_filtro_y_estado(panel: Any, filtros: list[tuple[str, str]], clave_filtro: str) -> bool:
	actual = [c for c, _n in filtros].index(panel.datos.get(clave_filtro, filtros[0][0]))
	eleccion = elegir_uno(panel, _("Filtro"), _("&Mostrar:"), [_(n) for _c, n in filtros], actual)
	if eleccion is None:
		return False
	estado_actual = [c for c, _n in ESTADOS].index(panel.datos.get("estado", "open"))
	estado = elegir_uno(panel, _("Estado"), _("&Estado:"), [_(n) for _c, n in ESTADOS], estado_actual)
	if estado is None:
		return False
	panel.datos[clave_filtro] = filtros[eleccion][0]
	panel.datos["estado"] = ESTADOS[estado][0]
	panel.etiqueta.SetLabel(etiqueta_lista(panel.definicion.titulo, f"{_(filtros[eleccion][1]).lower()}, {_(ESTADOS[estado][1]).lower()}"))
	return True


def vista_mis_issues() -> DefinicionVista:
	def cargar(api, pagina, panel):
		if not panel.ctx.usuario:
			return []
		return api.mis_issues(pagina, panel.datos.get("filtro", "assigned"), panel.datos.get("estado", "open"))

	def cambiar(panel, _e):
		if _elegir_filtro_y_estado(panel, FILTROS_ISSUES, "filtro"):
			panel.cargar()

	return DefinicionVista(
		"mis_issues", _("Mis issues"), columnas_issue(), cargar, lambda p, i: abrir.issue_o_pr(p.ctx, p, i),
		[
			Accion(_("A&brir"), lambda p, i: abrir.issue_o_pr(p.ctx, p, i), "Intro"),
			Accion(_("Cambiar el f&iltro…"), cambiar, "F4", requiere_elemento=False),
			Accion(_("Ir al re&positorio"), lambda p, i: abrir.repositorio(p.ctx, abrir.nombre_repo_de(i)), "Ctrl+Shift+R"),
		],
		_("No hay issues con este filtro."), url_html, detalle_issue,
	)


FILTROS_PR = [
	("review-requested:@me", N_("Me piden revisión")), ("author:@me", N_("Creados por mí")), ("assignee:@me", N_("Asignados a mí")),
	("mentions:@me", N_("Donde me mencionan")), ("involves:@me", N_("Todos en los que participo")), ("reviewed-by:@me", N_("Revisados por mí")),
]


def vista_mis_prs() -> DefinicionVista:
	def cargar(api, pagina, panel):
		if not panel.ctx.usuario:
			return []
		estado = panel.datos.get("estado", "open")
		consulta = f"is:pr {panel.datos.get('filtro', 'review-requested:@me')} archived:false"
		if estado != "all":
			consulta += f" is:{estado}"
		return api.buscar("issues", consulta, pagina, "updated", por_pagina=_por_pagina(panel))

	def cambiar(panel, _e):
		if _elegir_filtro_y_estado(panel, FILTROS_PR, "filtro"):
			panel.cargar()

	return DefinicionVista(
		"mis_prs", _("Mis pull requests"), columnas_issue(), cargar, lambda p, i: abrir.issue_o_pr(p.ctx, p, i),
		[
			Accion(_("A&brir"), lambda p, i: abrir.issue_o_pr(p.ctx, p, i), "Intro"),
			Accion(_("Cambiar el f&iltro…"), cambiar, "F4", requiere_elemento=False),
			Accion(_("Ir al re&positorio"), lambda p, i: abrir.repositorio(p.ctx, abrir.nombre_repo_de(i)), "Ctrl+Shift+R"),
		],
		_("No hay pull requests con este filtro."), url_html, detalle_issue,
	)


def vista_gists() -> DefinicionVista:
	def cargar(api, pagina, panel):
		origen = panel.datos.get("origen", "mios")
		if origen == "estrella":
			return api.gists_con_estrella(pagina)
		if origen == "publicos":
			return api.gists_publicos(pagina)
		return api.mis_gists(pagina) if panel.ctx.usuario else []

	def cambiar(panel, _e):
		opciones = [("mios", _("Mis gists")), ("estrella", _("Gists con estrella")), ("publicos", _("Gists públicos recientes"))]
		actual = [c for c, _n in opciones].index(panel.datos.get("origen", "mios"))
		eleccion = elegir_uno(panel, _("Gists"), _("&Mostrar:"), [n for _c, n in opciones], actual)
		if eleccion is not None:
			panel.datos["origen"] = opciones[eleccion][0]
			panel.cargar()

	def nuevo(panel, _e):
		from app.ui.detalle.gist import nuevo_gist

		nuevo_gist(panel, panel.ctx, al_crear=lambda g: panel.cargar())

	def borrar(panel, gist):
		if not confirmar_peligro(panel, _("¿Borrar el gist «{d}»? No se puede deshacer.").format(d=gist.get("description") or gist["id"]), _("Borrar gist")):
			return
		en_segundo_plano(panel, panel.ctx, lambda: panel.ctx.api().borrar_gist(gist["id"]), exito=_("Gist borrado."),
			al_terminar=lambda _r: panel.quitar(gist))

	return DefinicionVista(
		"gists", _("Gists"),
		[
			Columna("descripcion", _("Descripción"), lambda g, c: g.get("description") or _("(sin descripción)"), 300),
			Columna("archivos", _("Archivos"), lambda g, c: ", ".join((g.get("files") or {}).keys()), 220),
			Columna("visibilidad", _("Visibilidad"), lambda g, c: _("Público") if g.get("public") else _("Secreto"), 80),
			Columna("autor", _("Autor"), lambda g, c: f.login(g.get("owner")), 120, visible=False),
			Columna("comentarios", _("Comentarios"), lambda g, c: str(g.get("comments", 0)), 80, visible=False),
			Columna("actualizado", _("Actualizado"), lambda g, c: f.fecha(g.get("updated_at"), c.relativas()), 120),
		],
		cargar, lambda p, g: abrir.gist(p.ctx, p, g["id"]),
		[
			Accion(_("A&brir"), lambda p, g: abrir.gist(p.ctx, p, g["id"]), "Intro"),
			Accion(_("N&uevo gist…"), nuevo, "Ctrl+N", requiere_elemento=False),
			Accion(_("Borra&r…"), borrar, "Supr", disponible=lambda p, g: (g.get("owner") or {}).get("login") == p.ctx.usuario),
			Accion(_("Cambiar el f&iltro…"), cambiar, "F4", requiere_elemento=False),
		],
		_("No hay gists."), url_html,
	)


def vista_organizaciones() -> DefinicionVista:
	return DefinicionVista(
		"organizaciones", _("Organizaciones"),
		[
			Columna("nombre", _("Organización"), lambda o, c: o.get("login", ""), 200),
			Columna("descripcion", _("Descripción"), lambda o, c: o.get("description") or "", 360),
		],
		lambda api, pagina, panel: api.mis_organizaciones() if panel.ctx.usuario else [],
		lambda p, o: _abrir_organizacion(p, o),
		[Accion(_("A&brir"), lambda p, o: _abrir_organizacion(p, o), "Intro")],
		_("No pertenece a ninguna organización."),
		url=lambda o: f"https://github.com/{o.get('login', '')}",
	)


def _abrir_organizacion(panel: Any, org: dict) -> None:
	from app.ui.detalle.organizacion import abrir_organizacion

	abrir_organizacion(panel.ctx, panel, org.get("login", ""))


def vista_proyectos() -> DefinicionVista:
	return DefinicionVista(
		"proyectos", _("Proyectos"),
		[
			Columna("titulo", _("Proyecto"), lambda p, c: p.get("title", ""), 260),
			Columna("numero", _("Número"), lambda p, c: str(p.get("number", "")), 70),
			Columna("elementos", _("Elementos"), lambda p, c: str((p.get("items") or {}).get("totalCount", "")), 80),
			Columna("estado", _("Estado"), lambda p, c: _("Cerrado") if p.get("closed") else _("Abierto"), 80),
			Columna("descripcion", _("Descripción"), lambda p, c: p.get("shortDescription") or "", 260),
			Columna("actualizado", _("Actualizado"), lambda p, c: f.fecha(p.get("updatedAt"), c.relativas()), 120),
		],
		lambda api, pagina, panel: api.proyectos(panel.ctx.usuario) if panel.ctx.usuario else [],
		lambda p, pr: abrir.proyecto(p.ctx, p, pr),
		[Accion(_("A&brir"), lambda p, pr: abrir.proyecto(p.ctx, p, pr), "Intro")],
		_("No tiene proyectos."), url=lambda p: p.get("url", ""), paginada=False,
	)


def vista_personas(seguidores: bool) -> DefinicionVista:
	def cargar(api, pagina, panel):
		if not panel.ctx.usuario:
			return []
		return api.seguidores(None, pagina) if seguidores else api.seguidos(None, pagina)

	return DefinicionVista(
		"seguidores" if seguidores else "seguidos", _("Seguidores") if seguidores else _("Personas que sigo"),
		[Columna("login", _("Usuario"), lambda u, c: u.get("login", ""), 220), Columna("tipo", _("Tipo"), lambda u, c: _("Organización") if u.get("type") == "Organization" else _("Persona"), 120)],
		cargar, lambda p, u: abrir.usuario(p.ctx, p, u["login"]),
		[Accion(_("&Ver perfil"), lambda p, u: abrir.usuario(p.ctx, p, u["login"]), "Intro")],
		_("La lista está vacía."), url_html,
	)


def vista_codespaces() -> DefinicionVista:
	def accion(nombre_metodo: str, texto: str):
		def ejecutar(panel, cs):
			en_segundo_plano(panel, panel.ctx, lambda: getattr(panel.ctx.api(), nombre_metodo)(cs["name"]), exito=texto,
				al_terminar=lambda _r: panel.cargar(anunciar=False))

		return ejecutar

	def borrar(panel, cs):
		if confirmar_peligro(panel, _("¿Borrar el codespace {n}? Se perderán los cambios no enviados.").format(n=cs.get("display_name") or cs["name"]), _("Borrar codespace")):
			accion("borrar_codespace", _("Codespace borrado."))(panel, cs)

	return DefinicionVista(
		"codespaces", _("Codespaces"),
		[
			Columna("nombre", _("Nombre"), lambda c, x: c.get("display_name") or c.get("name", ""), 220),
			Columna("repositorio", _("Repositorio"), lambda c, x: (c.get("repository") or {}).get("full_name", ""), 200),
			Columna("estado", _("Estado"), lambda c, x: f.estado(c.get("state")), 100),
			Columna("rama", _("Rama"), lambda c, x: (c.get("git_status") or {}).get("ref", ""), 120),
			Columna("maquina", _("Máquina"), lambda c, x: (c.get("machine") or {}).get("display_name", ""), 160),
			Columna("uso", _("Último uso"), lambda c, x: f.fecha(c.get("last_used_at"), x.relativas()), 120),
		],
		lambda api, pagina, panel: api.codespaces() if panel.ctx.usuario else [],
		lambda p, c: webbrowser.open(c.get("web_url", "")),
		[
			Accion(_("Abrir el codespace en el na&vegador"), lambda p, c: webbrowser.open(c.get("web_url", "")), "Intro"),
			Accion(_("&Iniciar"), accion("iniciar_codespace", _("Codespace iniciándose."))),
			Accion(_("De&tener"), accion("detener_codespace", _("Codespace detenido."))),
			Accion(_("&Borrar…"), borrar, "Supr"),
		],
		_("No tiene codespaces."), url=lambda c: c.get("web_url", ""), paginada=False,
	)


def vista_locales() -> DefinicionVista:
	def cargar(api, pagina, panel):
		from app.services import git_local

		filas = []
		for carpeta in panel.ctx.config.obtener("git.repos_locales", []) or []:
			fila = {"carpeta": carpeta, "nombre": os.path.basename(carpeta.rstrip("\\/")), "resumen": "", "existe": os.path.isdir(carpeta)}
			if fila["existe"] and git_local.git_disponible():
				try:
					fila["resumen"] = git_local.RepositorioLocal(carpeta).estado().resumen()
				except git_local.ErrorGit as error:
					fila["resumen"] = error.mensaje_usuario.splitlines()[0]
			elif not fila["existe"]:
				fila["resumen"] = _("La carpeta ya no existe.")
			filas.append(fila)
		return filas

	def anadir(panel, _e):
		from app.services import git_local

		dialogo = wx.DirDialog(panel, _("Elija la carpeta de un repositorio de git"), style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
		try:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			carpeta = dialogo.GetPath()
		finally:
			dialogo.Destroy()
		if not git_local.RepositorioLocal.es_repositorio(carpeta):
			from app.ui.comunes import confirmar

			if confirmar(panel, _("La carpeta no es un repositorio de git. ¿Crear uno nuevo en ella (git init)?"), _("Repositorio local")) != wx.ID_YES:
				return
			git_local.iniciar(carpeta)
		anadir_repo_local(panel.ctx, carpeta)
		panel.cargar()

	def quitar(panel, fila):
		lista = [c for c in panel.ctx.config.obtener("git.repos_locales", []) if c != fila["carpeta"]]
		panel.ctx.config.establecer("git.repos_locales", lista)
		panel.quitar(fila)
		panel.ctx.avisar(_("Quitado de la lista. La carpeta no se ha borrado."))

	def clonar(panel, _e):
		from app.ui.git.clonar import dialogo_clonar

		dialogo_clonar(panel, panel.ctx, "", "", al_clonar=lambda carpeta: panel.cargar())

	return DefinicionVista(
		"locales", _("Repositorios locales"),
		[
			Columna("nombre", _("Nombre"), lambda r, c: r["nombre"], 180),
			Columna("estado", _("Estado"), lambda r, c: r["resumen"], 380),
			Columna("carpeta", _("Carpeta"), lambda r, c: r["carpeta"], 300),
		],
		cargar, lambda p, r: abrir.repositorio_local(p.ctx, r["carpeta"]),
		[
			Accion(_("A&brir"), lambda p, r: abrir.repositorio_local(p.ctx, r["carpeta"]), "Intro"),
			Accion(_("Añadir una &carpeta…"), anadir, "Ctrl+N", requiere_elemento=False),
			Accion(_("C&lonar un repositorio…"), clonar, "Ctrl+K", requiere_elemento=False),
			Accion(_("Abrir la carpeta en el &Explorador"), lambda p, r: os.startfile(r["carpeta"]) if r["existe"] else None, "Ctrl+Shift+E"),  # noqa: S606
			Accion(_("Quitar de la lis&ta"), quitar, "Supr"),
		],
		_("No hay repositorios locales. Añada una carpeta con Control+N o clone uno con Control+K."), paginada=False,
		sonido_carga=False, requiere_sesion=False,
	)


def anadir_repo_local(ctx: Any, carpeta: str) -> None:
	lista = list(ctx.config.obtener("git.repos_locales", []) or [])
	carpeta = os.path.normpath(carpeta)
	if carpeta not in lista:
		lista.insert(0, carpeta)
		ctx.config.establecer("git.repos_locales", lista)


# ════════════════════════════════════════════════════════════════════════════
# Resultados de búsqueda: de quién es cada cosa (funciones puras, con pruebas)
# ════════════════════════════════════════════════════════════════════════════


def repo_del_resultado(elemento: dict, datos: dict | None = None) -> str:
	"""«dueño/repo» de un resultado de búsqueda de cualquier tipo, o «» si no tiene."""
	tipo = elemento.get("_tipo")
	if tipo == "tendencia_dev" or elemento.get("type") in ("User", "Organization", "Bot") and "login" in elemento:
		return ""
	if elemento.get("full_name") and "/" in str(elemento["full_name"]):
		return str(elemento["full_name"])
	if "color" in elemento and "default" in elemento:  # una etiqueta (label): es del repositorio buscado
		return str((datos or {}).get("repositorio", ""))
	return abrir.nombre_repo_de(elemento)


def propietario_del_resultado(elemento: dict, datos: dict | None = None) -> str:
	"""Cuenta (persona u organización) dueña del repositorio del resultado."""
	dueno = (elemento.get("owner") or {}).get("login") if isinstance(elemento.get("owner"), dict) else ""
	if dueno:
		return str(dueno)
	repo = repo_del_resultado(elemento, datos)
	return repo.split("/", 1)[0] if "/" in repo else ""


def autor_del_resultado(elemento: dict) -> str:
	"""Quién escribió la issue, el PR, la discusión o el commit (solo si tiene cuenta en GitHub)."""
	if elemento.get("_tipo") == "discusion":
		return str((elemento.get("author") or {}).get("login", ""))
	if "commit" in elemento:
		return f.login(elemento.get("author"))
	if "number" in elemento:
		return f.login(elemento.get("user"))
	return ""


def cuenta_del_resultado(elemento: dict) -> str:
	"""El propio usuario u organización cuando el resultado ES una cuenta."""
	if elemento.get("_tipo") == "tendencia_dev":
		return str(elemento.get("login", ""))
	if "login" in elemento and "full_name" not in elemento and "number" not in elemento:
		return str(elemento.get("login", ""))
	return ""


def persona_del_elemento(elemento: Any, datos: dict | None = None) -> str:
	"""Cuenta más relacionada con una fila de cualquier lista (para proponerla en «Ver un perfil»).

	Por orden: quien hizo la actividad, la propia cuenta si la fila es una
	persona, quien escribió la issue o el commit, y si no, el dueño del repositorio.
	"""
	if not isinstance(elemento, dict):
		return ""
	actor = elemento.get("actor")
	if isinstance(actor, dict) and actor.get("login"):
		return str(actor["login"])
	return (cuenta_del_resultado(elemento) or autor_del_resultado(elemento) or propietario_del_resultado(elemento, datos)
		or str(((elemento.get("repository") or {}).get("owner") or {}).get("login") or ""))


def es_repositorio_resultado(elemento: dict) -> bool:
	"""El resultado es un repositorio (búsqueda de repositorios o tendencias de repositorios)."""
	if elemento.get("_tipo") == "tendencia_repo":
		return True
	return bool(elemento.get("full_name")) and "number" not in elemento and "path" not in elemento and "commit" not in elemento


def _seguir_cuenta(panel: Any, login: str) -> None:
	"""Sigue a la cuenta o deja de seguirla (pregunta antes a GitHub cómo está)."""
	if not login:
		return
	api = panel.ctx.api()

	def trabajo() -> bool:
		if api.sigo_a(login):
			api.dejar_de_seguir(login)
			return False
		api.seguir(login)
		return True

	en_segundo_plano(panel, panel.ctx, trabajo,
		exito=lambda sigue: (_("Ahora sigue a {l}.") if sigue else _("Ha dejado de seguir a {l}.")).format(l=login))


def acciones_resultado() -> list[Accion]:
	"""Acciones de un resultado de búsqueda según lo que sea (repositorio, issue, cuenta, código...).

	Letras: las comunes de la lista ya usan A, M, F, Q, O, E, N y D, y la vista
	de búsqueda B, V, W, G y T; por eso aquí van P, U, R, J, L, S, I, C y Z.
	"""
	def propietario(p: Any, e: dict) -> str:
		return propietario_del_resultado(e, p.datos)

	def repositorio(p: Any, e: dict) -> str:
		return repo_del_resultado(e, p.datos)

	def como_repo(p: Any, e: dict) -> dict:
		# Las tendencias leídas de la web no traen «clone_url»: se compone con el host de la cuenta.
		host = getattr(p.ctx, "host", "") or "github.com"
		return {**e, "clone_url": e.get("clone_url") or f"https://{host}/{e.get('full_name', '')}.git"}

	return [
		Accion(_("Ver el &propietario (perfil, repositorios, seguir)"), lambda p, e: abrir.usuario(p.ctx, p, propietario(p, e)),
			"Ctrl+Shift+P", disponible=lambda p, e: bool(propietario(p, e)), separador_antes=True,
			ayuda=_("Abre el perfil de la persona u organización dueña del repositorio: sus datos, repositorios y el botón Seguir.")),
		Accion(_("Ver al a&utor"), lambda p, e: abrir.usuario(p.ctx, p, autor_del_resultado(e)),
			disponible=lambda p, e: bool(autor_del_resultado(e)) and autor_del_resultado(e) != propietario(p, e),
			ayuda=_("Abre el perfil de quien escribió la issue, el pull request, la discusión o el commit.")),
		Accion(_("Ir al &repositorio"), lambda p, e: abrir.repositorio(p.ctx, repositorio(p, e)), "Ctrl+Shift+R",
			disponible=lambda p, e: bool(repositorio(p, e)) and not es_repositorio_resultado(e),
			ayuda=_("Abre la ventana del repositorio al que pertenece el resultado.")),
		Accion(_("Seguir o de&jar de seguir"), lambda p, e: _seguir_cuenta(p, cuenta_del_resultado(e)),
			disponible=lambda p, e: bool(cuenta_del_resultado(e)), ayuda=_("Sigue a esta cuenta, o deja de seguirla.")),
		Accion(_("C&lonar…"), lambda p, e: _clonar(p, como_repo(p, e)), "Ctrl+K", disponible=lambda p, e: es_repositorio_resultado(e)),
		Accion(_("Poner o quitar la e&strella"), lambda p, e: _estrella(p, e), "Ctrl+S",
			disponible=lambda p, e: es_repositorio_resultado(e)),
		Accion(_("V&igilar…"), lambda p, e: _vigilar(p, e), disponible=lambda p, e: es_repositorio_resultado(e)),
		Accion(_("Bifur&car (fork)"), lambda p, e: _bifurcar(p, e), disponible=lambda p, e: es_repositorio_resultado(e)),
		Accion(_("Descargar el código en &zip…"), lambda p, e: _descargar_zip(p, e), disponible=lambda p, e: es_repositorio_resultado(e),
			ayuda=_("Guarda el código de la rama principal en un archivo zip, sin necesidad de git.")),
	]


def vista_busqueda() -> DefinicionVista:
	"""Resultados de la última búsqueda (la rellena el diálogo de búsqueda).

	- Columnas según el tipo (repositorios, issues, código, usuarios, commits,
	  temas, etiquetas, discusiones y tendencias), con «Coincidencias» (los
	  fragmentos de text-match). En Preferencias se eligen las de «busqueda» y
	  aquí se muestran las que tienen sentido para el tipo buscado.
	- La etiqueta de la lista avisa del tope de 1000 resultados de GitHub y de
	  los resultados incompletos (``incomplete_results``).
	- Acciones propias: abrir la búsqueda en el navegador, guardarla y «Traer
	  todos», que parte el intervalo de fechas para pasar de 1000 resultados.
	"""
	from app.services import busqueda as b
	from app.services.github.cliente import Pagina

	clave_tarea_todos = "busqueda:traer_todos"

	def fecha_de(e: dict, ctx: Any) -> str:
		commit = e.get("commit") or {}
		valor = (e.get("pushed_at") or e.get("updated_at") or e.get("updatedAt") or (commit.get("author") or {}).get("date")
			or e.get("created_at") or e.get("createdAt"))
		return f.fecha(valor, ctx.relativas()) if valor else ""

	def autor_de(e: dict) -> str:
		if e.get("_tipo") == "discusion":
			return (e.get("author") or {}).get("login", "")
		if "commit" in e:
			return f.login(e.get("author")) or ((e.get("commit") or {}).get("author") or {}).get("name", "")
		return f.login(e.get("user"))

	def comentarios_de(e: dict) -> str:
		valor = e.get("comments")
		if isinstance(valor, dict):
			valor = valor.get("totalCount")
		return str(valor) if valor is not None else ""

	def estado_de(e: dict) -> str:
		if e.get("_tipo") == "discusion":
			estado = _("cerrada") if e.get("closed") else _("abierta")
			return estado + (", " + _("respondida") if e.get("isAnswered") else "")
		return f.estado_issue(e) if "number" in e else ""

	def tipo_cuenta(e: dict) -> str:
		return {"User": _("Persona"), "Organization": _("Organización"), "Bot": _("Bot")}.get(e.get("type", ""), e.get("type", ""))

	def principal(e: dict, ctx: Any) -> str:
		if e.get("_tipo") == "tendencia_dev":
			return e.get("login", "")
		return (e.get("full_name") or e.get("title") or e.get("login") or e.get("path")
			or (e.get("commit") or {}).get("message", "").split("\n")[0] or e.get("display_name") or e.get("name") or "")

	columnas = [
		Columna("nombre", _("Resultado"), principal, 320),
		Columna("numero", _("Número"), lambda e, c: f"#{e['number']}" if e.get("number") else "", 70),
		Columna("descripcion", _("Descripción"), _descripcion_resultado, 280),
		Columna("coincidencias", _("Coincidencias"), lambda e, c: b.resumen_coincidencias(e), 320),
		Columna("repositorio", _("Repositorio"), lambda e, c: abrir.nombre_repo_de(e) if not e.get("full_name") else "", 180),
		Columna("estado", _("Estado"), lambda e, c: estado_de(e), 110),
		Columna("autor", _("Autor"), lambda e, c: autor_de(e), 120),
		Columna("comentarios", _("Comentarios"), lambda e, c: comentarios_de(e), 80),
		Columna("etiquetas", _("Etiquetas"), lambda e, c: f.etiquetas(e) if e.get("labels") and isinstance(e["labels"], list) else
			", ".join(n.get("name", "") for n in ((e.get("labels") or {}).get("nodes") or []) if isinstance(e.get("labels"), dict)), 140),
		Columna("categoria", _("Categoría"), lambda e, c: (e.get("category") or {}).get("name", ""), 120),
		Columna("votos", _("Votos"), lambda e, c: str(e["upvoteCount"]) if "upvoteCount" in e else "", 60),
		Columna("lenguaje", _("Lenguaje"), lambda e, c: e.get("language") or "", 100),
		Columna("estrellas", _("Estrellas"), lambda e, c: f.numero(e.get("stargazers_count")) if e.get("stargazers_count") is not None else "", 80),
		Columna("estrellas_periodo", _("Estrellas en el periodo"), lambda e, c: e.get("periodo_texto") or "", 140),
		Columna("bifurcaciones", _("Bifurcaciones"), lambda e, c: f.numero(e.get("forks_count")) if e.get("forks_count") is not None else "", 80),
		Columna("construido", _("Construido por"), lambda e, c: ", ".join(e.get("construido_por") or []), 160),
		Columna("nombre_completo", _("Nombre"), lambda e, c: (e.get("name") or "") if e.get("_tipo") == "tendencia_dev" else "", 160),
		Columna("repo_popular", _("Repositorio popular"), lambda e, c: e.get("repo_popular") or "", 200),
		Columna("cuenta", _("Tipo de cuenta"), lambda e, c: tipo_cuenta(e), 110),
		Columna("sha", _("Commit"), lambda e, c: str(e.get("sha") or "")[:7], 80),
		Columna("destacado", _("Destacado"), lambda e, c: ", ".join(t for t, s in ((_("destacado"), e.get("featured")),
			(_("seleccionado"), e.get("curated"))) if s), 120),
		Columna("color", _("Color"), lambda e, c: f"#{e['color']}" if e.get("color") else "", 80),
		Columna("actualizado", _("Fecha"), fecha_de, 120),
	]

	por_tipo = {
		"repositories": ["nombre", "descripcion", "coincidencias", "lenguaje", "estrellas", "actualizado"],
		"issues": ["numero", "nombre", "repositorio", "estado", "autor", "comentarios", "etiquetas", "coincidencias", "actualizado"],
		"code": ["nombre", "repositorio", "coincidencias"],
		"users": ["nombre", "cuenta", "coincidencias"],
		"commits": ["nombre", "repositorio", "autor", "sha", "coincidencias", "actualizado"],
		"topics": ["nombre", "descripcion", "destacado", "coincidencias"],
		"labels": ["nombre", "descripcion", "color", "coincidencias"],
		"discussions": ["numero", "nombre", "repositorio", "categoria", "estado", "autor", "comentarios", "votos", "coincidencias", "actualizado"],
		"trending_repos": ["nombre", "descripcion", "lenguaje", "estrellas_periodo", "estrellas", "bifurcaciones", "construido"],
		"trending_devs": ["nombre", "nombre_completo", "repo_popular", "descripcion"],
	}

	def clave_columnas(datos: dict) -> str:
		tipo = datos.get("tipo", "repositories")
		if tipo == "trending":
			fuente = datos.get("fuente") or "api"
			return {"web_repos": "trending_repos", "web_devs": "trending_devs"}.get(fuente, "repositories")
		return tipo if tipo in por_tipo else "repositories"

	class DefinicionBusqueda(DefinicionVista):
		"""Columnas que dependen del tipo buscado (``clave_columnas``)."""

		clave_columnas = "repositories"

		def columnas_visibles(self, config: Any) -> list[Columna]:
			ids = por_tipo.get(self.clave_columnas, por_tipo["repositories"])
			por_id = {c.id: c for c in self.columnas}
			elegidas = (config.obtener("listas.columnas", {}) or {}).get(self.id) if config else None
			if elegidas:
				lista = [por_id[i] for i in elegidas if i in por_id and i in ids]
				if lista:
					return lista
			return [por_id[i] for i in ids if i in por_id]

	def preparar_panel(panel: Any, clave: str, resultado: Any) -> None:
		"""En el hilo de la interfaz: columnas del tipo y avisos en la etiqueta de la lista."""
		if not panel:
			return
		definicion = panel.definicion
		if getattr(definicion, "clave_columnas", clave) != clave:
			definicion.clave_columnas = clave
			panel.rehacer_columnas()
		total = getattr(resultado, "total", None)
		incompleto = getattr(resultado, "incompleto", None)
		avisos = b.avisos_resultado(total, incompleto)
		datos = panel.datos
		detalle = "; ".join([datos.get("nombre_tipo", ""), *avisos]).strip("; ")
		panel.etiqueta.SetLabel(etiqueta_lista(_("resultados de «{q}»").format(q=datos.get("consulta", "")), detalle))
		if incompleto:
			panel.ctx.avisar(_("Puede que falten resultados: GitHub cortó la búsqueda por tiempo. Puede repetirla con F5 o acotarla."),
				interrumpir=False)

	def cargar(api, pagina, panel):
		datos = panel.datos
		consulta = datos.get("consulta", "")
		tipo = datos.get("tipo", "repositories")
		if not consulta:
			return []
		por_pagina = _por_pagina(panel)
		if tipo == "discussions":
			if pagina == 1 or "_cursores" not in datos:
				datos["_cursores"] = {}
			cursores = datos["_cursores"]
			resultado = api.buscar_discusiones(consulta, por_pagina, cursores.get(pagina) if pagina > 1 else None)
			if resultado.siguiente:
				cursores[pagina + 1] = resultado.siguiente
		elif tipo == "trending" and datos.get("fuente") in ("web_repos", "web_devs"):
			resultado = b.filtrar_local(api.tendencias(datos["fuente"], datos.get("periodo", "daily"), datos.get("lenguaje", ""),
				datos.get("idioma", "")), datos.get("texto", ""))
		else:
			resultado = api.buscar("repositories" if tipo == "trending" else tipo, consulta, pagina, datos.get("orden", ""),
				datos.get("direccion", "desc"), por_pagina=por_pagina, repositorio=datos.get("repositorio", "") if tipo == "labels" else "",
				search_type=datos.get("search_type", "") if tipo == "issues" else "")
			# Semántica e híbrida: una sola página. Y nunca se pide más allá del resultado 1000 (GitHub da 422).
			if isinstance(resultado, Pagina) and (datos.get("search_type") or pagina * por_pagina >= b.MAXIMO_RESULTADOS):
				resultado = Pagina(resultado.elementos, "", resultado.ultima, resultado.total, resultado.numero, resultado.incompleto)
		if pagina == 1:
			wx.CallAfter(preparar_panel, panel, clave_columnas(datos), resultado)
		return resultado

	def activar(panel, elemento):
		tipo = panel.datos.get("tipo", "repositories")
		if elemento.get("_tipo") == "discusion":
			abrir.discusion(panel.ctx, panel, abrir.nombre_repo_de(elemento), int(elemento.get("number") or 0))
		elif elemento.get("_tipo") == "tendencia_dev":
			abrir.usuario(panel.ctx, panel, elemento.get("login", ""))
		elif tipo in ("repositories", "trending") or elemento.get("_tipo") == "tendencia_repo":
			abrir.repositorio(panel.ctx, elemento.get("full_name", ""))
		elif tipo == "issues":
			abrir.issue_o_pr(panel.ctx, panel, elemento)
		elif tipo == "users":
			abrir.usuario(panel.ctx, panel, elemento.get("login", ""))
		elif tipo == "code":
			from app.ui.detalle.archivos import abrir_archivo

			abrir_archivo(panel.ctx, panel, (elemento.get("repository") or {}).get("full_name", ""), elemento.get("path", ""))
		elif tipo == "commits":
			abrir.commit(panel.ctx, panel, (elemento.get("repository") or {}).get("full_name", ""), elemento.get("sha", ""))
		elif tipo == "topics":
			nueva_consulta(panel, "repositories", f"topic:{elemento.get('name', '')}")
		elif tipo == "labels":
			nueva_consulta(panel, "issues", f"repo:{panel.datos.get('repositorio', '')} label:{b.citar(elemento.get('name', ''))}")
		else:
			mostrar_mensaje(panel, str(elemento), _("Resultado"))

	def nueva_consulta(panel: Any, tipo: str, consulta: str) -> None:
		datos = b.preparar_busqueda(tipo, consulta, {}, host=getattr(panel.ctx, "host", b.HOST_GITHUB) or b.HOST_GITHUB)
		panel.datos.clear()
		panel.datos.update(datos)
		panel.etiqueta.SetLabel(etiqueta_lista(_("resultados de «{q}»").format(q=consulta), datos["nombre_tipo"]))
		panel.cargar()

	def detalle(elemento, ctx):
		if elemento.get("_tipo") == "discusion":
			texto = "\n".join([
				_("Discusión #{n}: {t}").format(n=elemento.get("number"), t=elemento.get("title", "")),
				_("Repositorio: {r}").format(r=abrir.nombre_repo_de(elemento)),
				_("Categoría: {c}").format(c=(elemento.get("category") or {}).get("name", "")),
				_("Estado: {e}").format(e=estado_de(elemento)),
				_("Autor: {a}").format(a=autor_de(elemento)),
				_("Comentarios: {c}; votos: {v}").format(c=comentarios_de(elemento), v=elemento.get("upvoteCount", 0)),
				_("Enlace: {u}").format(u=elemento.get("html_url", "")),
			])
		elif elemento.get("_tipo") in ("tendencia_repo", "tendencia_dev"):
			texto = "\n".join(f"{c.titulo}: {v}" for c in columnas if (v := str(c.valor(elemento, ctx) or "")))
		elif "full_name" in elemento:
			texto = detalle_repositorio(elemento, ctx)
		elif "number" in elemento:
			texto = detalle_issue(elemento, ctx)
		elif "path" in elemento:
			texto = _("Archivo: {p}\nRepositorio: {r}").format(p=elemento.get("path"), r=(elemento.get("repository") or {}).get("full_name"))
		else:
			texto = "\n".join(f"{k}: {v}" for k, v in elemento.items() if isinstance(v, (str, int, float)) and v not in ("", None))
		fragmentos = [" ".join(str(m.get("fragment") or "").split()) for m in elemento.get("text_matches") or [] if isinstance(m, dict)]
		if any(fragmentos):
			texto += "\n\n" + _("Coincidencias:") + "\n" + "\n\n".join(x for x in fragmentos if x)
		return texto

	def abrir_web(panel, _e):
		datos = panel.datos
		url = datos.get("url_web") or b.url_navegador(datos.get("tipo", ""), datos.get("consulta", ""),
			getattr(panel.ctx, "host", b.HOST_GITHUB) or b.HOST_GITHUB, datos.get("orden", ""), datos.get("direccion", "desc"), datos)
		if url:
			webbrowser.open(url)
		else:
			panel.ctx.avisar(_("No hay ninguna búsqueda que abrir."))

	def guardar(panel, _e):
		from app.ui.busqueda import guardar_busqueda

		guardar_busqueda(panel, panel.ctx, panel.datos)

	def puede_traer_todos(panel, _e) -> bool:
		datos = panel.datos
		return (bool(datos.get("consulta")) and datos.get("tipo") in b.CAMPOS_FECHA_TODOS and not datos.get("search_type")
			and (panel.total or 0) > b.MAXIMO_RESULTADOS and not panel.ctx.tareas.activa(clave_tarea_todos))

	def traer_todos(panel, _e):
		from app.ui.comunes import confirmar

		datos = dict(panel.datos)
		total = panel.total or 0
		peticiones = b.estimar_peticiones(total)
		if confirmar(panel, _(
			"GitHub dice que hay {t} resultados y solo deja ver 1000 por búsqueda. «Traer todos» parte el intervalo de fechas "
			"en trozos de menos de 1000 y necesitará unas {p} peticiones; la búsqueda admite 30 por minuto (10 en código), "
			"así que puede tardar varios minutos. Puede detenerlo desde este mismo menú. ¿Continuar?"
		).format(t=f"{total:,}".replace(",", "."), p=peticiones), _("Traer todos los resultados")) != wx.ID_YES:
			return
		api = panel.ctx.api()
		tipo = datos.get("tipo", "repositories")

		def buscar_trozo(consulta, numero):
			return api.buscar(tipo, consulta, numero, datos.get("orden", ""), datos.get("direccion", "desc"), por_pagina=b.POR_PAGINA_TODOS)

		def trabajo(tarea):
			return b.traer_todos(buscar_trozo, datos.get("consulta", ""), b.CAMPOS_FECHA_TODOS[tipo],
				cancelado=lambda: tarea.cancelado, progreso=lambda n, p: tarea.progresar(n, total, _("{n} resultados").format(n=n)))

		def al_terminar(resultado):
			if not panel:
				return
			panel.elementos = list(resultado.elementos)
			panel.hay_mas = False
			panel.refrescar_filas()
			partes = [_("{n} resultados traídos con {p} peticiones.").format(n=len(resultado.elementos), p=resultado.peticiones)]
			if resultado.cancelado:
				partes.insert(0, _("Detenido."))
			partes += resultado.avisos
			panel.ctx.sonar("completado")
			panel.ctx.avisar(" ".join(partes))

		def al_fallar(error):
			if panel:
				panel.ctx.sonar("error")
				panel.ctx.avisar(_("No se pudieron traer todos: {m}").format(m=getattr(error, "mensaje_usuario", None) or str(error)))

		panel.ctx.avisar(_("Trayendo todos los resultados…"))
		panel.ctx.tareas.enviar(trabajo, al_terminar=al_terminar, al_fallar=al_fallar, clave_unica=clave_tarea_todos,
			nombre=clave_tarea_todos)

	def detener(panel, _e):
		if panel.ctx.tareas.cancelar(clave_tarea_todos):
			panel.ctx.avisar(_("Deteniendo «Traer todos»…"))

	definicion = DefinicionBusqueda(
		"busqueda", _("Resultados de la búsqueda"), columnas,
		cargar, activar,
		[
			Accion(_("A&brir"), activar, "Intro"),
			*acciones_resultado(),
			Accion(_("Nue&va búsqueda…"), lambda p, e: _nueva_busqueda(p), "F4", requiere_elemento=False, separador_antes=True),
			Accion(_("Abrir la búsqueda en la &web"), abrir_web, "Ctrl+Shift+B", requiere_elemento=False,
				disponible=lambda p, e: bool(p.datos.get("consulta")), ayuda=_("Abre la misma búsqueda en github.com.")),
			Accion(_("&Guardar esta búsqueda…"), guardar, requiere_elemento=False, disponible=lambda p, e: bool(p.datos.get("consulta")),
				ayuda=_("Guarda la búsqueda con un nombre para repetirla desde el diálogo de búsqueda.")),
			Accion(_("&Traer todos los resultados (más de 1000)…"), traer_todos, requiere_elemento=False, disponible=puede_traer_todos,
				ayuda=_("Parte el intervalo de fechas para pasar del tope de 1000 resultados de GitHub.")),
			Accion(_("De&tener «Traer todos»"), detener, requiere_elemento=False,
				disponible=lambda p, e: p.ctx.tareas.activa(clave_tarea_todos)),
		],
		_("Sin resultados."), url_html, detalle, requiere_sesion=False,
	)
	definicion.preparar_panel = preparar_panel  # type: ignore[attr-defined] - para las pruebas
	definicion.clave_columnas_de = clave_columnas  # type: ignore[attr-defined]
	return definicion


def _descripcion_resultado(elemento: dict, ctx: Any) -> str:
	tipo = elemento.get("_tipo")
	if tipo == "discusion":
		return f"{abrir.nombre_repo_de(elemento)}, {(elemento.get('category') or {}).get('name', '')}".strip(", ")
	if tipo == "tendencia_dev":
		return elemento.get("descripcion_repo") or ""
	if "number" in elemento:
		return f"{abrir.nombre_repo_de(elemento)}, {f.estado_issue(elemento)}"
	if "commit" in elemento:
		return (elemento.get("repository") or {}).get("full_name", "")
	return (elemento.get("description") or elemento.get("short_description") or (elemento.get("repository") or {}).get("full_name", "")
		or "")


def _nueva_busqueda(panel: Any) -> None:
	ventana = panel.ctx.ventana_principal
	if ventana is not None:
		ventana.buscar()


SECCIONES = [
	("inicio", vista_inicio),
	("notificaciones", vista_notificaciones),
	("repositorios", vista_mis_repositorios),
	("estrellas", vista_estrellas),
	("issues", vista_mis_issues),
	("prs", vista_mis_prs),
	("gists", vista_gists),
	("organizaciones", vista_organizaciones),
	("proyectos", vista_proyectos),
	("locales", vista_locales),
	("vigilados", vista_vigilados),
	("seguidores", lambda: vista_personas(True)),
	("seguidos", lambda: vista_personas(False)),
	("codespaces", vista_codespaces),
	("busqueda", vista_busqueda),
]
