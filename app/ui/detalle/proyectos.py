"""Projects (v2): el tablero como una lista de elementos con una columna por campo.

En la web, mover una tarjeta exige arrastrarla; aquí todo es una lista nativa:

- «Elementos»: Título, Tipo, Repositorio y una columna por cada campo del
  proyecto (Estado, Iteración, Prioridad, fechas, números...). Se cargan todas
  las páginas (por cursor) en segundo plano.
- «Mover a…» (Ctrl+M): cambia el campo de selección única elegido (por
  defecto «Status» o «Estado») eligiendo la opción de una lista.
- Cambiar cualquier campo (F2): texto, número, fecha, selección o iteración,
  o vaciarlo.
- Añadir un borrador (Ctrl+N) o una issue o PR por enlace o «dueño/repo#número»
  (Ctrl+Mayús+N); archivar o desarchivar (Ctrl+Mayús+A); borrar del proyecto
  (Supr); abrir el elemento (Intro).
- Filtrar por campo (F4) y agrupar por estado (Ctrl+G, ordena por las opciones
  del campo); con la lista agrupada, Ctrl+Abajo y Ctrl+Arriba saltan de grupo.
"""

from __future__ import annotations

import builtins
import logging
import re
import webbrowser
from datetime import date
from typing import Any

import wx

from app.ui import abrir
from app.ui.comunes import confirmar_peligro, copiar, elegir_uno, mostrar_error, mostrar_mensaje, pedir_texto
from app.ui.detalle.comun_detalle import VentanaDetalle, entrada_cerrar
from app.ui.editor import editar

log = logging.getLogger(__name__)

TIPOS_EDITABLES = ("TEXT", "NUMBER", "DATE", "SINGLE_SELECT", "ITERATION")
TIPOS_ELEMENTO = {"ISSUE": N_("Issue"), "PULL_REQUEST": N_("Pull request"), "DRAFT_ISSUE": N_("Borrador"), "REDACTED": N_("Oculto")}
MAXIMO_ELEMENTOS = 5000
#: Se usa también como valor interno del filtro «sin valor»: se compara sin traducir y se traduce al mostrarlo.
SIN_VALOR = N_("(sin valor)")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ════════════════════════════════════════════════════════════════════════════
# Funciones puras
# ════════════════════════════════════════════════════════════════════════════


def campos_editables(campos: list[dict]) -> list[dict]:
	return [c for c in campos or [] if c.get("dataType") in TIPOS_EDITABLES and c.get("name")]


def _nodos_valor(elemento: dict) -> list[dict]:
	return [n for n in ((elemento.get("fieldValues") or {}).get("nodes") or []) if n]


def valor_campo(elemento: dict, nombre_campo: str) -> str:
	"""Texto del valor de un campo («En curso», «Sprint 3», «2024-05-01», «5»)."""
	for nodo in _nodos_valor(elemento):
		if (nodo.get("field") or {}).get("name") != nombre_campo:
			continue
		for clave in ("name", "title", "text", "date"):
			if nodo.get(clave) not in (None, ""):
				return str(nodo[clave])
		if nodo.get("number") is not None:
			numero = nodo["number"]
			return str(int(numero)) if isinstance(numero, float) and numero.is_integer() else str(numero)
	return ""


def poner_valor(elemento: dict, nombre_campo: str, clave: str, valor: Any) -> None:
	"""Cambia en local el valor de un campo (``valor`` ``None`` lo vacía)."""
	valores = elemento.setdefault("fieldValues", {}).setdefault("nodes", [])
	valores[:] = [n for n in valores if n and (n.get("field") or {}).get("name") != nombre_campo]
	if valor is not None:
		valores.append({clave: valor, "field": {"name": nombre_campo}})


def titulo_elemento(elemento: dict) -> str:
	return ((elemento.get("content") or {}).get("title")) or _("(sin título)")


def tipo_elemento(elemento: dict) -> str:
	tipo = elemento.get("type") or ""
	# Un tipo desconocido se muestra tal cual (y vacío no pasa por _(), que daría la cabecera del catálogo).
	texto = _(TIPOS_ELEMENTO[tipo]) if tipo in TIPOS_ELEMENTO else tipo.title()
	if elemento.get("isArchived"):
		texto += _(" (archivado)")
	return texto


def repo_elemento(elemento: dict) -> str:
	return (((elemento.get("content") or {}).get("repository")) or {}).get("nameWithOwner", "")


def fila_elemento(elemento: dict, campos: list[dict]) -> list[str]:
	return [titulo_elemento(elemento), tipo_elemento(elemento), repo_elemento(elemento)] + [valor_campo(elemento, c["name"]) for c in campos]


def detalle_elemento(elemento: dict, campos: list[dict]) -> str:
	contenido = elemento.get("content") or {}
	lineas = [_("Título: {t}").format(t=titulo_elemento(elemento)), _("Tipo: {t}").format(t=tipo_elemento(elemento))]
	if repo_elemento(elemento):
		lineas.append(_("Repositorio: {r}").format(r=repo_elemento(elemento)))
	if contenido.get("number"):
		lineas.append(_("Número: #{n}").format(n=contenido["number"]))
	if contenido.get("state"):
		lineas.append(_("Estado del contenido: {e}").format(e={"OPEN": _("Abierto"), "CLOSED": _("Cerrado"),
			"MERGED": _("Fusionado")}.get(contenido["state"], contenido["state"])))
	for campo in campos:
		lineas.append(f"{campo['name']}: {valor_campo(elemento, campo['name']) or _(SIN_VALOR)}")
	if contenido.get("url"):
		lineas.append(_("Enlace: {u}").format(u=contenido["url"]))
	if contenido.get("body"):
		lineas += ["", contenido["body"]]
	return "\n".join(lineas)


def campo_de_grupo(campos: list[dict], preferido: str = "") -> dict | None:
	"""Campo de selección única para «Mover a…»: el preferido, «Status»/«Estado» o el primero."""
	unicos = [c for c in campos or [] if c.get("dataType") == "SINGLE_SELECT"]
	for nombre in (preferido, "Status", "Estado"):
		for campo in unicos:
			if nombre and campo.get("name", "").casefold() == nombre.casefold():
				return campo
	return unicos[0] if unicos else None


def ordenar_por_grupo(elementos: list[dict], campo: dict) -> list[dict]:
	"""Ordena por el orden de las opciones del campo; sin valor, al final. Estable."""
	orden = {o.get("name"): i for i, o in enumerate(campo.get("options") or [])}
	return sorted(elementos, key=lambda e: orden.get(valor_campo(e, campo["name"]), len(orden)))


def referencia_issue(texto: str) -> tuple[str, int] | None:
	"""«https://github.com/dueño/repo/issues/12» o «dueño/repo#12» → («dueño/repo», 12)."""
	texto = texto.strip()
	coincidencia = re.match(r"(?:https?://[^/]+/)?([\w.-]+/[\w.-]+)/(?:issues|pull)/(\d+)", texto)
	if coincidencia:
		return coincidencia.group(1), int(coincidencia.group(2))
	coincidencia = re.fullmatch(r"([\w.-]+/[\w.-]+)#(\d+)", texto)
	if coincidencia:
		return coincidencia.group(1), int(coincidencia.group(2))
	return None


def opciones_de(campo: dict) -> list[tuple[str, str]]:
	"""(id, texto) de las opciones de un campo de selección única o de iteración."""
	if campo.get("dataType") == "SINGLE_SELECT":
		return [(o.get("id", ""), o.get("name", "")) for o in campo.get("options") or []]
	if campo.get("dataType") == "ITERATION":
		iteraciones = ((campo.get("configuration") or {}).get("iterations")) or []
		return [(i.get("id", ""), f"{i.get('title', '')} ({i.get('startDate', '')})") for i in iteraciones]
	return []


# ════════════════════════════════════════════════════════════════════════════
# Ventana
# ════════════════════════════════════════════════════════════════════════════


class VentanaProyecto(VentanaDetalle):
	def __init__(self, ctx: Any, padre: wx.Window | None, proyecto: dict) -> None:
		datos = dict(proyecto or {})
		super().__init__(padre, ctx, _("Proyecto: {t}").format(t=datos.get("title", "")), clave=f"proyecto:{datos.get('id', '')}",
			tamano=(1150, 760))
		self.proyecto = datos
		self.campos: list[dict] = []
		self.elementos: list[dict] = []
		self.visibles: list[dict] = []
		self.nombre_grupo = str(ctx.config.obtener("proyectos.campo_mover", "") or "")
		self.agrupado = False
		self.filtro: tuple[str, str] | None = None
		self._construir()

	def _construir(self) -> None:
		self.lista = self.crear_lista(_("&Elementos:"), _("Elementos"), [(_("Título"), 320), (_("Tipo"), 110), (_("Repositorio"), 180)],
			proporcion=3, ayuda=_("Intro abre el elemento; Control+M lo mueve a otro estado; F2 cambia un campo; Supr lo quita "
				"del proyecto; F4 filtra; Control+G agrupa por estado."))
		self.detalle = self.crear_texto(_("&Detalles del elemento:"), alto=160, proporcion=1)
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda e: (e.Skip(), self._mostrar_detalle()))
		self.teclas_de_lista(self.lista, {"Supr": self.borrar}, al_activar=self.abrir_elemento)
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_pulsar_lista)
		self.menu_contextual(self.lista, lambda: [
			(_("A&brir\tIntro"), self.abrir_elemento),
			(_("&Mover a…\tCtrl+M"), self.mover_a),
			(_("&Cambiar un campo…\tF2"), self.cambiar_campo),
			(_("&Archivar o desarchivar\tCtrl+Shift+A"), self.archivar),
			(_("B&orrar del proyecto…\tSupr"), self.borrar),
		])
		self.poner_menus([(_("&Proyecto"), [
			(_("&Mover a…\tCtrl+M"), self.mover_a),
			(_("&Cambiar un campo…\tF2"), self.cambiar_campo),
			(_("Campo q&ue usa «Mover a»…"), self.elegir_campo_grupo),
			None,
			(_("Añadir un &borrador…\tCtrl+N"), self.anadir_borrador),
			(_("Añadir una &issue o un pull request…\tCtrl+Shift+N"), self.anadir_issue),
			(_("&Archivar o desarchivar\tCtrl+Shift+A"), self.archivar),
			(_("B&orrar del proyecto… (Supr)"), self.borrar),
			(_("Abrir el &elemento (Intro)"), self.abrir_elemento),
			None,
			(_("&Filtrar por un campo…\tF4"), self.filtrar),
			(_("&Quitar el filtro\tCtrl+Shift+F"), self.quitar_filtro),
			(_("A&grupar por estado (ordenar)\tCtrl+G"), self.alternar_agrupado),
			None,
			(_("Abrir en el &navegador\tCtrl+B"), self.abrir_navegador),
			(_("Co&piar el enlace del elemento\tCtrl+Shift+C"), self.copiar_enlace),
			(_("Ac&tualizar\tF5"), lambda: self.cargar()),
			entrada_cerrar(self, _("Cerrar la &ventana\tCtrl+W")),
		])])

	# ── Datos ─────────────────────────────────────────────────────────────────

	@property
	def editables(self) -> list[dict]:
		return campos_editables(self.campos)

	@property
	def campo_grupo(self) -> dict | None:
		return campo_de_grupo(self.campos, self.nombre_grupo)

	@property
	def elemento(self) -> dict | None:
		fila = self.lista.fila_actual() if hasattr(self, "lista") else wx.NOT_FOUND
		return self.visibles[fila] if 0 <= fila < len(self.visibles) else None

	def cargar(self, anunciar: bool = True, enfocar_id: str | None = None) -> None:
		api = self.ctx.api()
		id_proyecto = self.proyecto.get("id", "")
		actual = enfocar_id or (self.elemento or {}).get("id")

		def obtener() -> tuple[list, list]:
			campos = api.campos_proyecto(id_proyecto)
			elementos: list[dict] = []
			cursor = None
			while True:
				pagina, cursor = api.elementos_proyecto(id_proyecto, 100, cursor)
				elementos.extend(pagina or [])
				if not cursor or len(elementos) >= MAXIMO_ELEMENTOS:
					break
			return campos, elementos

		def listo(datos: tuple[list, list]) -> None:
			self.poner_datos(datos[0], datos[1], actual)
			if anunciar:
				self.ctx.sonar("listo" if self.elementos else "vacio")
				self.ctx.avisar(self.GetStatusBar().GetStatusText(), interrumpir=False)

		self.estado(_("Cargando el proyecto…"))
		self.en_fondo(obtener, al_terminar=listo, sonido="")

	def poner_datos(self, campos: list, elementos: list, enfocar_id: str | None = None) -> None:
		nuevos = campos_editables(campos)
		if [c.get("name") for c in nuevos] != [c.get("name") for c in self.editables] or not self.campos:
			self.campos = list(campos or [])
			self._rehacer_columnas()
		self.campos = list(campos or [])
		self.elementos = list(elementos or [])
		self.refrescar(enfocar_id)

	def _rehacer_columnas(self) -> None:
		self.lista.limpiar()
		self.lista.DeleteAllColumns()
		columnas = [(_("Título"), 320), (_("Tipo"), 110), (_("Repositorio"), 180)] + [(c["name"], 130) for c in self.editables]
		for indice, (titulo, ancho) in enumerate(columnas):
			self.lista.InsertColumn(indice, titulo, width=self.FromDIP(ancho))
		self.lista.reiniciar_columna()

	def _calcular_visibles(self) -> list[dict]:
		visibles = list(self.elementos)
		if self.filtro is not None:
			campo, valor = self.filtro
			buscado = valor.casefold()
			if campo == "":
				visibles = [e for e in visibles if buscado in titulo_elemento(e).casefold()]
			elif valor == SIN_VALOR:
				visibles = [e for e in visibles if not valor_campo(e, campo)]
			else:
				visibles = [e for e in visibles if buscado in valor_campo(e, campo).casefold()]
		grupo = self.campo_grupo
		if self.agrupado and grupo is not None:
			visibles = ordenar_por_grupo(visibles, grupo)
		return visibles

	def refrescar(self, enfocar_id: str | None = None) -> None:
		"""Vuelve a pintar la lista sin pedir nada a la red; conserva el elemento enfocado."""
		enfocar_id = enfocar_id or (self.elemento or {}).get("id")
		self.visibles = self._calcular_visibles()
		self.lista.reemplazar_filas([fila_elemento(e, self.editables) for e in self.visibles], conservar_foco=False)
		ids = [e.get("id") for e in self.visibles]
		if enfocar_id in ids:
			self.lista.enfocar_fila(ids.index(enfocar_id), anunciar=False)
		elif self.visibles:
			self.lista.enfocar_fila(0, anunciar=False)
		self._mostrar_detalle()
		partes = [_("{n} elementos").format(n=len(self.visibles))]
		if self.filtro is not None:
			partes.append(_("de {t}, con filtro «{c}: {v}»").format(t=len(self.elementos), c=self.filtro[0] or _("Título"),
				v=_(SIN_VALOR) if self.filtro[1] == SIN_VALOR else self.filtro[1]))
		if self.agrupado and self.campo_grupo is not None:
			partes.append(_("agrupados por {c}").format(c=self.campo_grupo["name"]))
		self.estado(", ".join(partes) + ".")
		self.SetTitle(_("Proyecto: {t}").format(t=self.proyecto.get("title", "")))

	def _mostrar_detalle(self) -> None:
		elemento = self.elemento
		self.detalle.SetValue(detalle_elemento(elemento, self.editables) if elemento else "")
		self.detalle.SetInsertionPoint(0)

	def _al_pulsar_lista(self, evento: wx.KeyEvent) -> None:
		tecla = evento.GetKeyCode()
		if evento.GetModifiers() == wx.MOD_CONTROL and tecla in (wx.WXK_DOWN, wx.WXK_UP) and self.agrupado:
			self.saltar_grupo(atras=tecla == wx.WXK_UP)
			return
		evento.Skip()

	def saltar_grupo(self, atras: bool = False) -> None:
		grupo = self.campo_grupo
		fila = self.lista.fila_actual()
		if grupo is None or fila == wx.NOT_FOUND:
			return
		valores = [valor_campo(e, grupo["name"]) for e in self.visibles]
		actual = valores[fila]
		if atras:
			# Principio del grupo anterior: se retrocede hasta otro valor y luego al inicio de ese grupo.
			indice = fila
			while indice > 0 and valores[indice - 1] == actual:
				indice -= 1
			if indice == 0:
				self.ctx.sonar("vacio")
				self.ctx.anunciar(_("No hay grupos antes."))
				return
			anterior = valores[indice - 1]
			indice -= 1
			while indice > 0 and valores[indice - 1] == anterior:
				indice -= 1
		else:
			indice = next((i for i in range(fila + 1, len(valores)) if valores[i] != actual), None)
			if indice is None:
				self.ctx.sonar("vacio")
				self.ctx.anunciar(_("No hay más grupos."))
				return
		self.lista.enfocar_fila(indice, anunciar=False)
		self.ctx.anunciar(_("{g}: {t}").format(g=valores[indice] or _(SIN_VALOR), t=titulo_elemento(self.visibles[indice])))

	# ── Cambiar campos ────────────────────────────────────────────────────────

	def _aplicar_valor(self, elemento: dict, campo: dict, valor_api: dict | None, clave_local: str, valor_local: Any,
		frase: str) -> None:
		"""Cambia un campo en GitHub (o lo vacía con ``valor_api`` ``None``) y en la lista."""
		api = self.ctx.api()
		id_proyecto = self.proyecto.get("id", "")

		def trabajo() -> None:
			if valor_api is None:
				# Sin envoltura en la API: vaciar un campo se hace con el cliente crudo (GraphQL).
				api.c.graphql("mutation($p: ID!, $i: ID!, $f: ID!) { clearProjectV2ItemFieldValue(input: {projectId: $p, "
					"itemId: $i, fieldId: $f}) { projectV2Item { id } } }", {"p": id_proyecto, "i": elemento["id"], "f": campo["id"]})
			else:
				api.cambiar_campo(id_proyecto, elemento["id"], campo["id"], valor_api)

		def hecho(_r: Any) -> None:
			poner_valor(elemento, campo["name"], clave_local, valor_local)
			self.refrescar(elemento.get("id"))

		self.en_fondo(trabajo, exito=frase, al_terminar=hecho)

	def mover_a(self) -> None:
		elemento, campo = self.elemento, self.campo_grupo
		if elemento is None:
			return
		if campo is None:
			mostrar_mensaje(self, _("Este proyecto no tiene ningún campo de selección única (como «Status»)."), _("Mover a"))
			return
		self._elegir_opcion(elemento, campo, _("Mover a"), _("&Mover «{t}» a:").format(t=titulo_elemento(elemento)))

	def _elegir_opcion(self, elemento: dict, campo: dict, titulo: str, etiqueta: str) -> None:
		opciones = opciones_de(campo)
		textos = [t for _i, t in opciones] + [_("(quitar el valor)")]
		actual = valor_campo(elemento, campo["name"])
		nombres = [o.get("name") if campo.get("dataType") == "SINGLE_SELECT" else o.get("title")
			for o in (campo.get("options") or ((campo.get("configuration") or {}).get("iterations")) or [])]
		indice = elegir_uno(self, titulo, etiqueta, textos, nombres.index(actual) if actual in nombres else 0)
		if indice is None:
			return
		if indice == len(opciones):
			self._aplicar_valor(elemento, campo, None, "name", None, _("{c} vaciado.").format(c=campo["name"]))
			return
		id_opcion = opciones[indice][0]
		if campo.get("dataType") == "SINGLE_SELECT":
			self._aplicar_valor(elemento, campo, {"singleSelectOptionId": id_opcion}, "name", nombres[indice],
				_("Movido a {o}.").format(o=nombres[indice]))
		else:
			self._aplicar_valor(elemento, campo, {"iterationId": id_opcion}, "title", nombres[indice],
				_("{c}: {o}.").format(c=campo["name"], o=nombres[indice]))

	def cambiar_campo(self) -> None:
		elemento = self.elemento
		if elemento is None:
			return
		campos = self.editables
		if not campos:
			mostrar_mensaje(self, _("Este proyecto no tiene campos que se puedan cambiar."), _("Cambiar un campo"))
			return
		textos = [f"{c['name']}: {valor_campo(elemento, c['name']) or _(SIN_VALOR)}" for c in campos]
		indice = elegir_uno(self, _("Cambiar un campo"), _("&Campo que cambiar:"), textos)
		if indice is None:
			return
		campo = campos[indice]
		tipo = campo.get("dataType")
		if tipo in ("SINGLE_SELECT", "ITERATION"):
			self._elegir_opcion(elemento, campo, campo["name"], _("&Nuevo valor de {c}:").format(c=campo["name"]))
			return
		actual = valor_campo(elemento, campo["name"])
		ayuda = {"NUMBER": _(" (un número)"), "DATE": _(" (AAAA-MM-DD)")}.get(tipo, "")
		texto = pedir_texto(self, _("&Nuevo valor de {c}{a}; vacío para quitarlo:").format(c=campo["name"], a=ayuda), campo["name"], actual)
		if texto is None:
			return
		texto = texto.strip()
		if not texto:
			self._aplicar_valor(elemento, campo, None, "text", None, _("{c} vaciado.").format(c=campo["name"]))
			return
		if tipo == "NUMBER":
			try:
				numero = float(texto.replace(",", "."))
			except ValueError:
				mostrar_error(self, _("«{t}» no es un número.").format(t=texto), campo["name"])
				return
			self._aplicar_valor(elemento, campo, {"number": numero}, "number", numero, _("{c}: {v}.").format(c=campo["name"], v=texto))
		elif tipo == "DATE":
			try:
				fecha = date.fromisoformat(texto).isoformat()
			except ValueError:
				mostrar_error(self, _("«{t}» no es una fecha. Escríbala como AAAA-MM-DD, por ejemplo 2025-03-31.").format(t=texto), campo["name"])
				return
			self._aplicar_valor(elemento, campo, {"date": fecha}, "date", fecha, _("{c}: {v}.").format(c=campo["name"], v=fecha))
		else:
			self._aplicar_valor(elemento, campo, {"text": texto}, "text", texto, _("{c} cambiado.").format(c=campo["name"]))

	def elegir_campo_grupo(self) -> None:
		unicos = [c for c in self.campos if c.get("dataType") == "SINGLE_SELECT"]
		if not unicos:
			mostrar_mensaje(self, _("Este proyecto no tiene campos de selección única."), _("Mover a"))
			return
		actual = self.campo_grupo
		indice = elegir_uno(self, _("Campo de «Mover a»"), _("&Campo que cambia «Mover a» y por el que se agrupa:"),
			[c["name"] for c in unicos], unicos.index(actual) if actual in unicos else 0)
		if indice is None:
			return
		self.nombre_grupo = unicos[indice]["name"]
		self.ctx.config.establecer("proyectos.campo_mover", self.nombre_grupo)
		self.refrescar()
		self.ctx.avisar(_("«Mover a» cambia ahora {c}.").format(c=self.nombre_grupo))

	# ── Añadir, archivar, borrar ──────────────────────────────────────────────

	def anadir_borrador(self) -> None:
		api = self.ctx.api()
		id_proyecto = self.proyecto.get("id", "")
		datos: dict = {}

		def enviar(valores: dict) -> str:
			datos.update(valores)
			return api.anadir_borrador(id_proyecto, valores["titulo"], valores.get("cuerpo", ""))

		id_nuevo = editar(self, self.ctx, _("Nuevo borrador en el proyecto"), enviar, con_titulo=True,
			etiqueta_cuerpo=_("&Descripción (Markdown):"), etiqueta_enviar=_("&Añadir"))
		if id_nuevo and self.viva():
			self.elementos.append({"id": id_nuevo, "type": "DRAFT_ISSUE", "isArchived": False,
				"content": {"title": datos.get("titulo", ""), "body": datos.get("cuerpo", "")}, "fieldValues": {"nodes": []}})
			self.refrescar(id_nuevo)
			self.lista.SetFocus()

	def anadir_issue(self) -> None:
		texto = pedir_texto(self, _("&Enlace de la issue o del pull request, o dueño/repo#número:"), _("Añadir al proyecto"))
		if not texto or not texto.strip():
			return
		referencia = referencia_issue(texto)
		if referencia is None:
			mostrar_error(self, _("No se entiende «{t}». Escriba un enlace de GitHub o algo como octocat/hola#12.").format(t=texto.strip()),
				_("Añadir al proyecto"))
			return
		nombre, numero = referencia
		api = self.ctx.api()
		id_proyecto = self.proyecto.get("id", "")

		def trabajo() -> str:
			id_nodo = api.id_de_nodo(nombre, numero)
			if not id_nodo:
				raise ValueError(_("No existe la issue o el pull request {n}#{x}.").format(n=nombre, x=numero))
			return api.anadir_a_proyecto(id_proyecto, id_nodo)

		self.en_fondo(trabajo, exito=_("{n}#{x} añadido al proyecto.").format(n=nombre, x=numero),
			al_terminar=lambda id_elemento: self.cargar(anunciar=False, enfocar_id=id_elemento), inicio=_("Añadiendo…"))

	def archivar(self) -> None:
		elemento = self.elemento
		if elemento is None:
			return
		archivar = not elemento.get("isArchived")
		api = self.ctx.api()

		def hecho(_r: Any) -> None:
			elemento["isArchived"] = archivar
			self.refrescar(elemento.get("id"))

		self.en_fondo(lambda: api.archivar_elemento(self.proyecto.get("id", ""), elemento["id"], archivar),
			exito=_("Elemento archivado.") if archivar else _("Elemento desarchivado."), al_terminar=hecho)

	def borrar(self) -> None:
		elemento = self.elemento
		if elemento is None:
			return
		aviso = _(" El borrador se perderá.") if elemento.get("type") == "DRAFT_ISSUE" else _(" La issue o el PR no se borra.")
		if not confirmar_peligro(self, _("¿Quitar «{t}» del proyecto?").format(t=titulo_elemento(elemento)) + aviso, _("Quitar del proyecto")):
			return
		api = self.ctx.api()
		fila = self.lista.fila_actual()

		def hecho(_r: Any) -> None:
			if elemento in self.elementos:
				self.elementos.remove(elemento)
			siguiente = None
			if self.visibles:
				restantes = [e for e in self.visibles if e is not elemento]
				if restantes:
					siguiente = restantes[min(fila, len(restantes) - 1)].get("id")
			self.refrescar(siguiente)

		self.en_fondo(lambda: api.borrar_elemento(self.proyecto.get("id", ""), elemento["id"]), exito=_("Quitado del proyecto."),
			al_terminar=hecho)

	# ── Abrir, filtrar, agrupar ───────────────────────────────────────────────

	def abrir_elemento(self) -> None:
		elemento = self.elemento
		if elemento is None:
			return
		contenido = elemento.get("content") or {}
		tipo = elemento.get("type")
		if tipo == "ISSUE" and repo_elemento(elemento) and contenido.get("number"):
			abrir.issue(self.ctx, self, repo_elemento(elemento), contenido["number"])
		elif tipo == "PULL_REQUEST" and repo_elemento(elemento) and contenido.get("number"):
			abrir.pull_request(self.ctx, self, repo_elemento(elemento), contenido["number"])
		elif tipo == "DRAFT_ISSUE":
			from app.ui.dialogo_texto import DialogoTexto

			dialogo = DialogoTexto(self, _("Borrador: {t}").format(t=titulo_elemento(elemento)), _("&Borrador:"),
				detalle_elemento(elemento, self.editables), copiable=True)
			try:
				dialogo.ShowModal()
			finally:
				dialogo.Destroy()
		else:
			self.ctx.avisar(_("No tiene permiso para ver este elemento."))

	def filtrar(self) -> None:
		campos = self.editables
		opciones = [_("Título (contiene un texto)")] + [c["name"] for c in campos]
		indice = elegir_uno(self, _("Filtrar el proyecto"), _("&Campo por el que filtrar:"), opciones)
		if indice is None:
			return
		if indice == 0:
			texto = pedir_texto(self, _("&Texto que debe contener el título:"), _("Filtrar el proyecto"))
			if not texto or not texto.strip():
				return
			self.filtro = ("", texto.strip())
		else:
			campo = campos[indice - 1]
			valores = sorted({valor_campo(e, campo["name"]) for e in self.elementos} - {""})
			if campo.get("dataType") in ("SINGLE_SELECT", "ITERATION"):
				nombres = [t for _i, t in opciones_de(campo)] if campo.get("dataType") == "SINGLE_SELECT" else valores
				elecciones = nombres + [_(SIN_VALOR)]
				eleccion = elegir_uno(self, _("Filtrar el proyecto"), _("&Valor de {c}:").format(c=campo["name"]), elecciones)
				if eleccion is None:
					return
				valor = SIN_VALOR if eleccion == len(nombres) else nombres[eleccion]
			else:
				texto = pedir_texto(self, _("&Texto que debe contener {c} (vacío: sin valor):").format(c=campo["name"]), _("Filtrar el proyecto"))
				if texto is None:
					return
				valor = texto.strip() or SIN_VALOR
			self.filtro = (campo["name"], valor)
		self.refrescar()
		self.lista.SetFocus()
		self.ctx.avisar(self.GetStatusBar().GetStatusText())

	def quitar_filtro(self) -> None:
		if self.filtro is None:
			self.ctx.avisar(_("No hay ningún filtro."))
			return
		self.filtro = None
		self.refrescar()
		self.ctx.avisar(_("Filtro quitado. ") + self.GetStatusBar().GetStatusText())

	def alternar_agrupado(self) -> None:
		if self.campo_grupo is None:
			mostrar_mensaje(self, _("Este proyecto no tiene ningún campo de selección única por el que agrupar."), _("Agrupar"))
			return
		self.agrupado = not self.agrupado
		self.refrescar()
		if self.agrupado:
			self.ctx.avisar(_("Agrupado por {c}. Control+Abajo y Control+Arriba saltan de grupo.").format(c=self.campo_grupo["name"]))
		else:
			self.ctx.avisar(_("Sin agrupar: orden del proyecto."))

	def _url(self) -> str:
		return ((self.elemento or {}).get("content") or {}).get("url") or self.proyecto.get("url", "")

	def abrir_navegador(self) -> None:
		if self._url():
			webbrowser.open(self._url())

	def copiar_enlace(self) -> None:
		if self._url():
			copiar(self.ctx, self._url(), _("Enlace copiado."))


def abrir_proyecto(ctx: Any, padre: wx.Window | None, proyecto: dict) -> wx.Frame:
	"""Abre (o trae al frente) la ventana de un proyecto y carga sus elementos en segundo plano."""
	clave = f"proyecto:{(proyecto or {}).get('id', '')}"
	if VentanaDetalle.abrir_existente(clave):
		return VentanaDetalle._abiertas[clave]
	ventana = VentanaProyecto(ctx, padre, proyecto)
	ventana.mostrar(ventana.lista)
	ventana.cargar()
	return ventana
