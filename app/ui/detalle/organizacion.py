"""Ventana de una organización: repositorios, miembros, equipos, invitaciones, proyectos y ajustes.

Pestañas (Ctrl+Tab): Resumen (datos y «Editar la configuración»),
Repositorios, Miembros (cambiar rol, quitar), Equipos (crear, miembros,
repositorios, borrar), Invitaciones (invitar por correo, cancelar), Proyectos,
Webhooks, Secretos de Actions, Variables de Actions y Registro de auditoría
(solo si la cuenta tiene permiso; si no, la lista lo dice).

Cada lista tiene sus acciones en el menú contextual (Aplicaciones o
Mayús+F10) con sus atajos: Intro abre, Ctrl+N crea, F2 edita, Supr borra o
quita. Menú «Acciones» (Alt+A): navegador, actualizar (F5), cerrar (Ctrl+W).
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from typing import Any

import wx

from app.services import formato as f
from app.ui import abrir
from app.ui.comunes import confirmar_peligro, elegir_uno, en_segundo_plano, mensaje_error, pedir_texto
from app.ui.detalle.conversacion import (
	Campo,
	DialogoLista,
	VentanaDetalle,
	como_dict,
	como_lista,
	crear_boton,
	crear_menu_acciones,
	crear_texto,
	pedir_formulario,
)
from app.ui.vistas.base import Accion, Columna, DefinicionVista, PanelLista, url_html

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def clave_organizacion(login: str) -> str:
	return f"organizacion:{login.lower()}"


ROLES_MIEMBRO = [("member", N_("Miembro")), ("admin", N_("Propietario (administración)"))]
ROLES_INVITACION = [("direct_member", N_("Miembro")), ("admin", N_("Propietario")), ("billing_manager", N_("Gestor de facturación"))]
PRIVACIDAD_EQUIPO = [("closed", N_("Visible para toda la organización")), ("secret", N_("Secreto: solo sus miembros"))]
PERMISOS_REPO = [("pull", N_("Lectura")), ("triage", N_("Clasificación")), ("push", N_("Escritura")), ("maintain", N_("Mantenimiento")),
	("admin", N_("Administración"))]
VISIBILIDAD_ACTIONS = [("all", N_("Todos los repositorios")), ("private", N_("Repositorios privados")), ("selected", N_("Repositorios elegidos"))]


def texto_visibilidad(valor: str) -> str:
	"""Nombre traducido de la visibilidad de un secreto o variable de Actions (la clave tal cual si es desconocida)."""
	texto = dict(VISIBILIDAD_ACTIONS).get(valor, valor)
	# _("") devolvería la cabecera del catálogo: una celda vacía se queda vacía.
	return _(texto) if texto else ""


def texto_organizacion(org: dict) -> str:
	lineas = [
		_("{l} ({n})").format(l=org.get("login", ""), n=org.get("name")) if org.get("name") else org.get("login", ""),
	]
	for clave, etiqueta in (("description", _("Descripción")), ("location", _("Ubicación")), ("email", _("Correo")),
		("blog", _("Web")), ("twitter_username", _("Twitter o X"))):
		if org.get(clave):
			lineas.append(f"{etiqueta}: {org[clave]}")
	lineas.append(_("Repositorios públicos: {p}; privados: {r}").format(p=org.get("public_repos", 0),
		r=org.get("total_private_repos", "-") if "total_private_repos" in org else "-"))
	lineas.append(_("Seguidores: {s}").format(s=org.get("followers", 0)))
	if como_dict(org.get("plan")).get("name"):
		lineas.append(_("Plan: {p}").format(p=org["plan"]["name"]))
	if "two_factor_requirement_enabled" in org:
		lineas.append(_("Exige verificación en dos pasos: {v}").format(v=f.si_no(org.get("two_factor_requirement_enabled"))))
	lineas.append(_("Creada: {c}").format(c=f.fecha_completa(org.get("created_at"))))
	lineas.append(_("Enlace: {u}").format(u=org.get("html_url", "")))
	return "\n".join(lineas)


# ════════════════════════════════════════════════════════════════════════════
# Vistas
# ════════════════════════════════════════════════════════════════════════════


def _org(panel: Any) -> str:
	return panel.datos["org"]


def _vista_repositorios() -> DefinicionVista:
	from app.ui.vistas.principales import acciones_repositorio, columnas_repositorio, detalle_repositorio

	return DefinicionVista("org_repositorios", _("Repositorios"), columnas_repositorio(),
		lambda api, pagina, panel: api.repositorios_org(_org(panel), pagina),
		lambda p, r: abrir.repositorio(p.ctx, r.get("full_name", "")), acciones_repositorio(),
		_("La organización no tiene repositorios visibles."), url_html, detalle_repositorio)


def _vista_miembros() -> DefinicionVista:
	def cargar(api, pagina, panel):
		if pagina == 1:
			try:
				panel.datos["admins"] = {como_dict(u).get("login") for u in como_lista(api.miembros(_org(panel), 1, "admin"))}
			except Exception:  # noqa: BLE001 - sin permiso para ver roles: la columna queda vacía
				log.debug("No se pudieron leer los propietarios de %s", _org(panel), exc_info=True)
				panel.datos["admins"] = set()
		resultado = api.miembros(_org(panel), pagina)
		for usuario in como_lista(resultado):
			if isinstance(usuario, dict):
				usuario["_rol"] = _("Propietario") if usuario.get("login") in panel.datos["admins"] else _("Miembro")
		return resultado

	def cambiar_rol(panel, miembro):
		eleccion = elegir_uno(panel, _("Rol de {l}").format(l=miembro.get("login", "")), _("&Rol en la organización:"),
			[_(t) for _v, t in ROLES_MIEMBRO])
		if eleccion is None:
			return
		valor = ROLES_MIEMBRO[eleccion][0]
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.poner_membresia(_org(panel), miembro["login"], valor),
			exito=_("Rol cambiado."), al_terminar=lambda _r: panel.cargar())

	def quitar(panel, miembro):
		if not confirmar_peligro(panel, _("¿Quitar a {l} de la organización {o}? Perderá el acceso a sus repositorios.").format(
			l=miembro.get("login", ""), o=_org(panel)), _("Quitar miembro")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.quitar_miembro(_org(panel), miembro["login"]), exito=_("Miembro quitado."),
			al_terminar=lambda _r: panel.quitar(miembro))

	return DefinicionVista(
		"org_miembros", _("Miembros"),
		[Columna("login", _("Usuario"), lambda u, c: u.get("login", ""), 220), Columna("rol", _("Rol"), lambda u, c: u.get("_rol", ""), 140)],
		cargar, lambda p, u: abrir.usuario(p.ctx, p, u.get("login", "")),
		[
			Accion(_("&Ver perfil"), lambda p, u: abrir.usuario(p.ctx, p, u.get("login", "")), "Intro"),
			Accion(_("Cambiar el &rol…"), cambiar_rol, "F2"),
			Accion(_("&Quitar de la organización…"), quitar, "Supr"),
		],
		_("No hay miembros visibles."), url_html,
	)


def _vista_equipos() -> DefinicionVista:
	def crear(panel, _e):
		valores = pedir_formulario(panel, _("Crear equipo"), [
			Campo("nombre", _("&Nombre del equipo:")),
			Campo("descripcion", _("&Descripción:")),
			Campo("privacidad", _("&Privacidad:"), "opcion", "closed", [(v, _(t)) for v, t in PRIVACIDAD_EQUIPO]),
		], _("C&rear"))
		if not valores or not valores["nombre"].strip():
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.crear_equipo(_org(panel), valores["nombre"].strip(), valores["descripcion"],
			valores["privacidad"]), exito=_("Equipo creado."), al_terminar=lambda _r: panel.cargar())

	def borrar(panel, equipo):
		if not confirmar_peligro(panel, _("¿Borrar el equipo {e}? No se puede deshacer.").format(e=equipo.get("name", "")),
			_("Borrar equipo"), equipo.get("slug", "")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.borrar_equipo(_org(panel), equipo["slug"]), exito=_("Equipo borrado."),
			al_terminar=lambda _r: panel.quitar(equipo))

	def miembros(panel, equipo):
		org, slug = _org(panel), equipo.get("slug", "")
		api = panel.ctx.api()

		def anadir(dialogo, _x):
			login = pedir_texto(dialogo, _("&Usuario que añadir:"), _("Añadir al equipo"))
			if not login or not login.strip():
				return
			eleccion = elegir_uno(dialogo, _("Rol en el equipo"), _("&Rol:"), [_("Miembro"), _("Mantenedor")])
			if eleccion is None:
				return
			en_segundo_plano(dialogo, panel.ctx, lambda: api.anadir_a_equipo(org, slug, login.strip(), ("member", "maintainer")[eleccion]),
				exito=_("Añadido al equipo."), al_terminar=lambda _r: dialogo and dialogo.recargar())

		def quitar(dialogo, usuario):
			if confirmar_peligro(dialogo, _("¿Quitar a {l} del equipo?").format(l=usuario.get("login", "")), _("Quitar del equipo")):
				en_segundo_plano(dialogo, panel.ctx, lambda: api.quitar_de_equipo(org, slug, usuario["login"]), exito=_("Quitado del equipo."),
					al_terminar=lambda _r: dialogo and dialogo.recargar())

		def mostrar(lista):
			DialogoLista(panel, panel.ctx, _("Miembros del equipo {e}").format(e=equipo.get("name", "")), _("&Miembros del equipo:"),
				[(_("Usuario"), 260)], lambda u: [u.get("login", "")], [como_dict(u) for u in como_lista(lista)],
				al_activar=lambda u: abrir.usuario(panel.ctx, panel, u.get("login", "")),
				botones=[(_("&Añadir…"), anadir, False), (_("&Quitar"), quitar, True)],
				recargar=lambda: api.miembros_equipo(org, slug)).mostrar()

		en_segundo_plano(panel, panel.ctx, lambda: api.miembros_equipo(org, slug), sonido="", al_terminar=mostrar)

	def repositorios(panel, equipo):
		org, slug = _org(panel), equipo.get("slug", "")
		api = panel.ctx.api()

		def anadir(dialogo, _x):
			nombre = pedir_texto(dialogo, _("&Repositorio (dueño/nombre):"), _("Dar acceso al equipo"), f"{org}/")
			if not nombre or "/" not in nombre:
				return
			eleccion = elegir_uno(dialogo, _("Permiso del equipo"), _("&Permiso:"), [_(t) for _v, t in PERMISOS_REPO], 2)
			if eleccion is None:
				return
			en_segundo_plano(dialogo, panel.ctx, lambda: api.dar_repo_a_equipo(org, slug, nombre.strip(), PERMISOS_REPO[eleccion][0]),
				exito=_("Acceso dado."), al_terminar=lambda _r: dialogo and dialogo.recargar())

		def quitar(dialogo, repo):
			if confirmar_peligro(dialogo, _("¿Quitar al equipo el acceso a {r}?").format(r=repo.get("full_name", "")), _("Quitar acceso")):
				en_segundo_plano(dialogo, panel.ctx, lambda: api.quitar_repo_a_equipo(org, slug, repo["full_name"]),
					exito=_("Acceso quitado."), al_terminar=lambda _r: dialogo and dialogo.recargar())

		def permiso(r: dict) -> str:
			permisos = como_dict(r.get("permissions"))
			for clave in ("admin", "maintain", "push", "triage", "pull"):
				if permisos.get(clave):
					return f.estado(clave)
			return ""

		def mostrar(lista):
			DialogoLista(panel, panel.ctx, _("Repositorios del equipo {e}").format(e=equipo.get("name", "")), _("&Repositorios del equipo:"),
				[(_("Repositorio"), 300), (_("Permiso"), 140)], lambda r: [r.get("full_name", ""), permiso(r)],
				[como_dict(r) for r in como_lista(lista)],
				al_activar=lambda r: abrir.repositorio(panel.ctx, r.get("full_name", "")),
				botones=[(_("&Dar acceso…"), anadir, False), (_("&Quitar el acceso"), quitar, True)],
				recargar=lambda: api.repos_equipo(org, slug)).mostrar()

		en_segundo_plano(panel, panel.ctx, lambda: api.repos_equipo(org, slug), sonido="", al_terminar=mostrar)

	return DefinicionVista(
		"org_equipos", _("Equipos"),
		[
			Columna("nombre", _("Equipo"), lambda e, c: e.get("name", ""), 220),
			Columna("descripcion", _("Descripción"), lambda e, c: e.get("description") or "", 300),
			Columna("privacidad", _("Privacidad"), lambda e, c: _("Secreto") if e.get("privacy") == "secret" else _("Visible"), 100),
			Columna("permiso", _("Permiso"), lambda e, c: f.estado(e.get("permission")), 100),
		],
		lambda api, pagina, panel: api.equipos(_org(panel)), miembros,
		[
			Accion(_("&Miembros del equipo…"), miembros, "Intro"),
			Accion(_("&Repositorios del equipo…"), repositorios, "Ctrl+R"),
			Accion(_("&Crear equipo…"), crear, "Ctrl+N", requiere_elemento=False),
			Accion(_("&Borrar el equipo…"), borrar, "Supr"),
		],
		_("La organización no tiene equipos visibles."), url_html, paginada=False,
	)


def _vista_invitaciones() -> DefinicionVista:
	def invitar(panel, _e):
		valores = pedir_formulario(panel, _("Invitar a la organización"), [
			Campo("correo", _("&Correo o identificador numérico de la persona:")),
			Campo("rol", _("&Rol:"), "opcion", "direct_member", [(v, _(t)) for v, t in ROLES_INVITACION]),
		], _("&Invitar"))
		if not valores or not valores["correo"].strip():
			return
		correo = valores["correo"].strip()
		if "@" not in correo and not correo.isdigit():
			panel.ctx.avisar(_("Escriba un correo o el número de identificador de la cuenta."))
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.invitar(_org(panel), correo, valores["rol"]), exito=_("Invitación enviada."),
			al_terminar=lambda _r: panel.cargar())

	def cancelar(panel, invitacion):
		quien = invitacion.get("email") or invitacion.get("login") or ""
		if not confirmar_peligro(panel, _("¿Cancelar la invitación a {q}?").format(q=quien), _("Cancelar invitación")):
			return
		api = panel.ctx.api()
		# Cliente crudo: la fachada no tiene «cancelar invitación de organización».
		en_segundo_plano(panel, panel.ctx, lambda: api.c.delete(f"/orgs/{_org(panel)}/invitations/{int(invitacion['id'])}"),
			exito=_("Invitación cancelada."), al_terminar=lambda _r: panel.quitar(invitacion))

	return DefinicionVista(
		"org_invitaciones", _("Invitaciones pendientes"),
		[
			Columna("quien", _("Persona"), lambda i, c: i.get("login") or i.get("email") or "", 240),
			Columna("rol", _("Rol"), lambda i, c: i.get("role", ""), 120),
			Columna("invita", _("Invitada por"), lambda i, c: f.login(i.get("inviter")), 140),
			Columna("fecha", _("Fecha"), lambda i, c: f.fecha(i.get("created_at"), c.relativas()), 120),
		],
		lambda api, pagina, panel: api.invitaciones_pendientes(_org(panel)), None,
		[
			Accion(_("&Invitar por correo…"), invitar, "Ctrl+N", requiere_elemento=False),
			Accion(_("&Cancelar la invitación…"), cancelar, "Supr"),
		],
		_("No hay invitaciones pendientes."), paginada=False,
	)


def _vista_proyectos() -> DefinicionVista:
	return DefinicionVista(
		"org_proyectos", _("Proyectos"),
		[
			Columna("titulo", _("Proyecto"), lambda p, c: p.get("title", ""), 260),
			Columna("numero", _("Número"), lambda p, c: str(p.get("number", "")), 70),
			Columna("elementos", _("Elementos"), lambda p, c: str(como_dict(p.get("items")).get("totalCount", "")), 80),
			Columna("estado", _("Estado"), lambda p, c: _("Cerrado") if p.get("closed") else _("Abierto"), 80),
			Columna("actualizado", _("Actualizado"), lambda p, c: f.fecha(p.get("updatedAt"), c.relativas()), 120),
		],
		lambda api, pagina, panel: api.proyectos(_org(panel), es_org=True),
		lambda p, pr: abrir.proyecto(p.ctx, p, pr),
		[Accion(_("&Abrir"), lambda p, pr: abrir.proyecto(p.ctx, p, pr), "Intro")],
		_("La organización no tiene proyectos."), url=lambda p: p.get("url", ""), paginada=False,
	)


def _vista_webhooks() -> DefinicionVista:
	def crear(panel, _e):
		valores = pedir_formulario(panel, _("Crear webhook de la organización"), [
			Campo("url", _("&URL que recibe los avisos:")),
			Campo("eventos", _("&Eventos (separados por comas; * para todos):"), valor="push"),
			Campo("secreto", _("&Secreto (opcional):"), "secreto"),
		], _("C&rear"))
		if not valores or not valores["url"].strip():
			return
		eventos = [e.strip() for e in valores["eventos"].split(",") if e.strip()] or ["push"]
		datos = {"name": "web", "active": True, "events": eventos,
			"config": {"url": valores["url"].strip(), "content_type": "json", "insecure_ssl": "0", **({"secret": valores["secreto"]} if valores["secreto"] else {})}}
		api = panel.ctx.api()
		# Cliente crudo: la fachada solo crea webhooks de repositorio.
		en_segundo_plano(panel, panel.ctx, lambda: api.c.post(f"/orgs/{_org(panel)}/hooks", datos), exito=_("Webhook creado."),
			al_terminar=lambda _r: panel.cargar())

	def borrar(panel, hook):
		if not confirmar_peligro(panel, _("¿Borrar el webhook {u}?").format(u=como_dict(hook.get("config")).get("url", "")), _("Borrar webhook")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.c.delete(f"/orgs/{_org(panel)}/hooks/{int(hook['id'])}"), exito=_("Webhook borrado."),
			al_terminar=lambda _r: panel.quitar(hook))

	def probar(panel, hook):
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.c.post(f"/orgs/{_org(panel)}/hooks/{int(hook['id'])}/pings"),
			exito=_("Aviso de prueba (ping) enviado."))

	return DefinicionVista(
		"org_webhooks", _("Webhooks"),
		[
			Columna("url", _("URL"), lambda h, c: como_dict(h.get("config")).get("url", ""), 320),
			Columna("eventos", _("Eventos"), lambda h, c: ", ".join(h.get("events") or []), 240),
			Columna("activo", _("Activo"), lambda h, c: f.si_no(h.get("active")), 70),
		],
		lambda api, pagina, panel: api.webhooks_org(_org(panel)), None,
		[
			Accion(_("&Crear webhook…"), crear, "Ctrl+N", requiere_elemento=False),
			Accion(_("&Probar (ping)"), probar, "Ctrl+P"),
			Accion(_("&Borrar el webhook…"), borrar, "Supr"),
		],
		_("No hay webhooks o no tiene permiso para verlos."), paginada=False,
	)


def _vista_secretos() -> DefinicionVista:
	def guardar(panel, secreto):
		from app.services.github.api_extra import cifrar_secreto

		valores = pedir_formulario(panel, _("Secreto de Actions"), [
			Campo("nombre", _("&Nombre:"), valor=(secreto or {}).get("name", "")),
			Campo("valor", _("&Valor:"), "secreto", ayuda=_("El valor se cifra antes de enviarlo; GitHub nunca lo vuelve a mostrar.")),
			Campo("visibilidad", _("&Disponible para:"), "opcion", (secreto or {}).get("visibility", "private"),
				[(v, _(t)) for v, t in VISIBILIDAD_ACTIONS]),
		], _("&Guardar"))
		if not valores or not valores["nombre"].strip():
			return
		org, nombre = _org(panel), valores["nombre"].strip().upper()
		api = panel.ctx.api()

		def trabajo():
			clave = como_dict(api.clave_publica_secretos("", org=org))
			# Cliente crudo: la fachada no guarda secretos de organización.
			api.c.put(f"/orgs/{org}/actions/secrets/{nombre}", {"encrypted_value": cifrar_secreto(clave["key"], valores["valor"]),
				"key_id": clave["key_id"], "visibility": valores["visibilidad"]})

		en_segundo_plano(panel, panel.ctx, trabajo, exito=_("Secreto {n} guardado.").format(n=nombre), al_terminar=lambda _r: panel.cargar())

	def borrar(panel, secreto):
		if not confirmar_peligro(panel, _("¿Borrar el secreto {n}? Los flujos que lo usen fallarán.").format(n=secreto.get("name", "")),
			_("Borrar secreto")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.c.delete(f"/orgs/{_org(panel)}/actions/secrets/{secreto['name']}"),
			exito=_("Secreto borrado."), al_terminar=lambda _r: panel.quitar(secreto))

	return DefinicionVista(
		"org_secretos", _("Secretos de Actions"),
		[
			Columna("nombre", _("Nombre"), lambda s, c: s.get("name", ""), 260),
			Columna("visibilidad", _("Disponible para"), lambda s, c: texto_visibilidad(s.get("visibility", "")), 180),
			Columna("actualizado", _("Actualizado"), lambda s, c: f.fecha(s.get("updated_at"), c.relativas()), 120),
		],
		lambda api, pagina, panel: api.secretos_org(_org(panel)), None,
		[
			Accion(_("&Nuevo secreto…"), lambda p, e: guardar(p, None), "Ctrl+N", requiere_elemento=False),
			Accion(_("Cambiar el &valor…"), guardar, "F2"),
			Accion(_("&Borrar el secreto…"), borrar, "Supr"),
		],
		_("No hay secretos o no tiene permiso para verlos."), paginada=False,
	)


def _vista_variables() -> DefinicionVista:
	def guardar(panel, variable):
		nueva = variable is None
		valores = pedir_formulario(panel, _("Variable de Actions"), [
			Campo("nombre", _("&Nombre:"), valor=(variable or {}).get("name", "")),
			Campo("valor", _("&Valor:"), valor=(variable or {}).get("value", "")),
			Campo("visibilidad", _("&Disponible para:"), "opcion", (variable or {}).get("visibility", "private"),
				[(v, _(t)) for v, t in VISIBILIDAD_ACTIONS]),
		], _("&Guardar"))
		if not valores or not valores["nombre"].strip():
			return
		org = _org(panel)
		datos = {"name": valores["nombre"].strip().upper(), "value": valores["valor"], "visibility": valores["visibilidad"]}
		api = panel.ctx.api()
		# Cliente crudo: la fachada no crea ni cambia variables de organización.
		if nueva:
			trabajo = lambda: api.c.post(f"/orgs/{org}/actions/variables", datos)  # noqa: E731
		else:
			trabajo = lambda: api.c.patch(f"/orgs/{org}/actions/variables/{variable['name']}", datos)  # noqa: E731
		en_segundo_plano(panel, panel.ctx, trabajo, exito=_("Variable guardada."), al_terminar=lambda _r: panel.cargar())

	def borrar(panel, variable):
		if not confirmar_peligro(panel, _("¿Borrar la variable {n}?").format(n=variable.get("name", "")), _("Borrar variable")):
			return
		api = panel.ctx.api()
		en_segundo_plano(panel, panel.ctx, lambda: api.c.delete(f"/orgs/{_org(panel)}/actions/variables/{variable['name']}"),
			exito=_("Variable borrada."), al_terminar=lambda _r: panel.quitar(variable))

	return DefinicionVista(
		"org_variables", _("Variables de Actions"),
		[
			Columna("nombre", _("Nombre"), lambda v, c: v.get("name", ""), 240),
			Columna("valor", _("Valor"), lambda v, c: v.get("value", ""), 280),
			Columna("visibilidad", _("Disponible para"), lambda v, c: texto_visibilidad(v.get("visibility", "")), 180),
		],
		lambda api, pagina, panel: api.variables_org(_org(panel)), None,
		[
			Accion(_("&Nueva variable…"), lambda p, e: guardar(p, None), "Ctrl+N", requiere_elemento=False),
			Accion(_("&Editar la variable…"), guardar, "F2"),
			Accion(_("&Borrar la variable…"), borrar, "Supr"),
		],
		_("No hay variables o no tiene permiso para verlas."), paginada=False,
	)


def _vista_auditoria() -> DefinicionVista:
	def filtrar(panel, _e):
		frase = pedir_texto(panel, _("&Frase de búsqueda (por ejemplo, action:repo.create):"), _("Filtrar el registro"),
			panel.datos.get("frase", ""))
		if frase is not None:
			panel.datos["frase"] = frase.strip()
			panel.cargar()

	return DefinicionVista(
		"org_auditoria", _("Registro de auditoría"),
		[
			Columna("accion", _("Acción"), lambda e, c: e.get("action", ""), 220),
			Columna("actor", _("Actor"), lambda e, c: e.get("actor", ""), 140),
			Columna("fecha", _("Fecha"), lambda e, c: _ts(e.get("@timestamp")) if e.get("@timestamp") else f.fecha_completa(e.get("created_at")), 140),
			Columna("detalle", _("Detalle"), lambda e, c: e.get("repo") or e.get("user") or e.get("team") or "", 260),
		],
		lambda api, pagina, panel: api.registro_auditoria(_org(panel), panel.datos.get("frase", "")), None,
		[Accion(_("&Buscar en el registro…"), filtrar, "F4", requiere_elemento=False)],
		_("El registro está vacío."), paginada=False,
	)


def _ts(milisegundos: Any) -> str:
	"""El registro de auditoría da la fecha en milisegundos desde 1970."""
	from datetime import UTC, datetime

	try:
		return f.fecha_completa(datetime.fromtimestamp(int(milisegundos) / 1000, UTC))
	except (TypeError, ValueError, OSError):
		return str(milisegundos)


# ════════════════════════════════════════════════════════════════════════════
# Ventana
# ════════════════════════════════════════════════════════════════════════════


class VentanaOrganizacion(VentanaDetalle):
	def __init__(self, padre: wx.Window | None, contexto: Any, login: str) -> None:
		super().__init__(padre, contexto, clave_organizacion(login), _("Organización {l}").format(l=login), (1050, 740))
		self.login = login
		self.org: dict = {}
		crear_menu_acciones(self, _("&Acciones"), [
			("configuracion", _("&Editar la configuración…"), self.editar_configuracion),
			("navegador", _("Abrir en el &navegador\tCtrl+Shift+B"), self.abrir_navegador),
			None,
			("actualizar", _("Act&ualizar\tF5"), self.actualizar),
			("cerrar", _("Cerrar la &ventana\tCtrl+W"), self.Close),
		])
		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.libro = wx.Notebook(panel)
		self.libro.SetHelpText(_("Pestañas de la organización. Control+Tabulador pasa a la siguiente."))
		self.libro.AddPage(self._crear_resumen(), _("Resumen"))
		self.paneles: dict[int, PanelLista] = {}
		for definicion, etiqueta in (
			(_vista_repositorios(), _("&Repositorios:")),
			(_vista_miembros(), _("&Miembros:")),
			(_vista_equipos(), _("&Equipos:")),
			(_vista_invitaciones(), _("&Invitaciones pendientes:")),
			(_vista_proyectos(), _("&Proyectos:")),
			(_vista_webhooks(), _("&Webhooks:")),
			(_vista_secretos(), _("&Secretos de Actions:")),
			(_vista_variables(), _("&Variables de Actions:")),
			(_vista_auditoria(), _("Registro de a&uditoría:")),
		):
			lista = PanelLista(self.libro, contexto, definicion, {"org": login}, etiqueta=etiqueta)
			self.paneles[self.libro.GetPageCount()] = lista
			self.libro.AddPage(lista, definicion.titulo)
		self.libro.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._al_cambiar_pagina)
		raiz.Add(self.libro, 1, wx.EXPAND | wx.ALL, 2)
		panel.SetSizer(raiz)

	def _crear_resumen(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.datos = crear_texto(pagina, _("&Datos:"), sizer, alto=240, proporcion=1, ayuda=_("Datos de la organización. Solo lectura."))
		botones = wx.BoxSizer(wx.HORIZONTAL)
		crear_boton(pagina, _("&Editar la configuración…"), self.editar_configuracion,
			_("Cambia el nombre, la descripción, el correo, la web y la ubicación de la organización."), botones)
		sizer.Add(botones, 0, wx.ALL, 2)
		pagina.SetSizer(sizer)
		return pagina

	def enfocar_inicio(self) -> None:
		self.datos.SetFocus()

	def cargar(self) -> None:
		api = self.ctx.api()

		def recibido(org: Any) -> None:
			if not self:
				return
			self.org = como_dict(org)
			self.SetTitle(_("Organización {l}").format(l=self.org.get("login") or self.login)
				+ (f" ({self.org['name']})" if self.org.get("name") else ""))
			self.datos.ChangeValue(texto_organizacion(self.org))
			self.datos.SetInsertionPoint(0)
			self.ctx.sonar("listo")

		def fallo(error: BaseException) -> None:
			if self:
				self.datos.ChangeValue(_("No se pudo cargar la organización: {m}").format(m=mensaje_error(error)))
				self.ctx.avisar(self.datos.GetValue())

		en_segundo_plano(self, self.ctx, lambda: api.organizacion(self.login), sonido="", al_terminar=recibido, al_fallar=fallo)
		self._cargar_pagina(self.libro.GetSelection())

	def _al_cambiar_pagina(self, evento: wx.BookCtrlEvent) -> None:
		evento.Skip()
		self._cargar_pagina(evento.GetSelection())

	def _cargar_pagina(self, indice: int) -> None:
		panel = self.paneles.get(indice)
		if panel is not None:
			panel.cargar_si_hace_falta()

	def actualizar(self) -> None:
		panel = self.paneles.get(self.libro.GetSelection())
		if panel is not None:
			panel.cargar()
		else:
			self.cargar()

	def editar_configuracion(self) -> None:
		o = self.org
		valores = pedir_formulario(self, _("Configuración de {l}").format(l=self.login), [
			Campo("name", _("&Nombre visible:"), valor=o.get("name") or ""),
			Campo("description", _("&Descripción:"), valor=o.get("description") or ""),
			Campo("email", _("Correo &público:"), valor=o.get("email") or ""),
			Campo("billing_email", _("Correo de &facturación:"), valor=o.get("billing_email") or "",
				ayuda=_("Solo lo ven las personas propietarias.")),
			Campo("blog", _("&Web:"), valor=o.get("blog") or ""),
			Campo("location", _("&Ubicación:"), valor=o.get("location") or ""),
			Campo("twitter_username", _("&Twitter o X:"), valor=o.get("twitter_username") or ""),
		], _("&Guardar"))
		if valores is None:
			return
		if not valores.get("billing_email"):
			valores.pop("billing_email", None)
		api = self.ctx.api()
		en_segundo_plano(self, self.ctx, lambda: api.editar_organizacion(self.login, **valores), exito=_("Configuración guardada."),
			al_terminar=lambda _r: self and self.cargar())

	def abrir_navegador(self) -> None:
		webbrowser.open(self.org.get("html_url") or f"https://{self.ctx.host}/{self.login}")


def abrir_organizacion(ctx: Any, padre: wx.Window | None, login: str) -> None:
	"""Abre la ventana de una organización (o trae al frente la que ya esté abierta)."""
	login = (login or "").strip()
	if not login:
		return
	if VentanaDetalle.traer_al_frente(clave_organizacion(login)):
		return
	ventana = VentanaOrganizacion(padre, ctx, login)
	ventana.mostrar()
	ventana.cargar()
