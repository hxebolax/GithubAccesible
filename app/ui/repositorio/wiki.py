"""Sección «Wiki» de la ventana de un repositorio.

La lista enseña las páginas de la wiki (la portada primero y la barra lateral
y el pie al final). Intro abre la página en el visor accesible, con los
enlaces a otras páginas de la misma wiki abriéndose también aquí. Desde las
acciones se crean, editan (con el editor Markdown y sus borradores),
renombran y borran páginas, se consulta el historial de cada una (ver una
versión antigua o sus cambios) y se busca texto en todas.

Todo pasa por ``app.services.wiki``: la wiki es un repositorio git aparte
(``<repo>.wiki.git``) que se guarda en ``data/cache/wikis``. Si la wiki está
desactivada, si aún no tiene páginas o si falta git, la lista lo dice en su
etiqueta y ofrece lo que se puede hacer (activarla, crear la primera página en
el navegador, instalar git).

Letras de acceso: las comunes de la lista usan A, M, F, Q, O, E, N y D.
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from typing import Any

import wx

from app.services import formato as f
from app.services import git_local
from app.services import wiki as w
from app.ui.comunes import confirmar_peligro, copiar, elegir_uno, en_segundo_plano, mostrar_mensaje, pedir_texto
from app.ui.repositorio.vistas import VistaRepo, _en_fondo, _hacer, _info, rotular
from app.ui.vistas.base import Accion, Columna

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Qué se dice cuando la lista está vacía, según el estado de la wiki.
TEXTOS_ESTADO = {
	"activa": N_("La wiki no tiene páginas."),
	"desactivada": N_("La wiki de este repositorio está desactivada. Puede activarla desde las acciones (Aplicaciones) si es suyo."),
	"vacia": N_("La wiki está activada pero no tiene páginas todavía. GitHub solo la crea al guardar la primera página "
		"desde la web: use «Crear la primera página en el navegador» en las acciones y luego actualice con F5."),
	"sin_git": N_("Para leer y editar la wiki hace falta Git for Windows (la API de GitHub no da acceso a las wikis). "
		"Instálelo desde https://git-scm.com o ábrala en el navegador."),
}
ETIQUETAS_ESTADO = {
	"activa": N_("Wiki"),
	"desactivada": N_("Wiki (desactivada)"),
	"vacia": N_("Wiki (sin páginas todavía)"),
	"sin_git": N_("Wiki (necesita Git)"),
}
#: Formatos que se ofrecen al crear una página (el primero, Markdown, es el de siempre).
FORMATOS_NUEVA = [(".md", "Markdown"), (".mediawiki", "MediaWiki"), (".asciidoc", "AsciiDoc"), (".rst", "reStructuredText"),
	(".textile", "Textile"), (".org", "Org"), (".creole", "Creole"), (".rdoc", "RDoc")]


def como_fila(pagina: w.PaginaWiki) -> dict:
	"""La lista trabaja con diccionarios (filtro, copiar fila, detalles...)."""
	tipo = {"_sidebar": _("Barra lateral"), "_footer": _("Pie de página")}.get(pagina.especial, "")
	if not tipo:
		tipo = _("Portada") if pagina.nombre == w.PORTADA and "/" not in pagina.archivo else _("Página")
	return {"titulo": pagina.titulo, "archivo": pagina.archivo, "formato": pagina.formato, "tamano": pagina.tamano,
		"tipo": tipo, "nombre": pagina.nombre, "_pagina": pagina}


def wiki_del_panel(panel: Any) -> w.WikiLocal:
	"""La copia de la wiki de esta sección (se crea la primera vez; sirve desde cualquier hilo)."""
	existente = panel.datos.get("wiki")
	if isinstance(existente, w.WikiLocal):
		return existente
	from app.core.paths import subcarpeta

	ctx = panel.ctx
	host = getattr(ctx, "host", "") or "github.com"
	nombre = panel.datos.get("nombre", "")
	login = getattr(ctx, "usuario", "") or "github-accesible"
	dominio = "users.noreply.github.com" if host == "github.com" else f"users.noreply.{host}"
	wiki = w.WikiLocal(w.carpeta_cache(subcarpeta("cache") / "wikis", host, nombre), host, nombre,
		token=ctx.token if ctx.config.obtener("git.usar_token", True) else None, identidad=(login, f"{login}@{dominio}"))
	panel.datos["wiki"] = wiki
	return wiki


def crear_vista_wiki(nombre: str, host: str = "github.com") -> VistaRepo:
	def estado(panel: Any) -> str:
		return panel.datos.get("estado_wiki", "")

	def poner_estado(panel: Any, valor: str) -> None:
		"""Se llama desde el hilo de carga: el texto vacío se lee luego en la interfaz y la etiqueta se cambia allí."""
		panel.datos["estado_wiki"] = valor
		panel.definicion.texto_vacio = _(TEXTOS_ESTADO[valor])
		wx.CallAfter(lambda: rotular(panel) if panel else None)

	def cargar(api: Any, pagina: int, panel: Any) -> list:
		info = _info(panel)
		if "has_wiki" not in info:
			info = api.repositorio(nombre)
			if isinstance(info, dict):
				panel.datos["info"] = info
		if not (info or {}).get("has_wiki"):
			poner_estado(panel, "desactivada")
			return []
		if not git_local.git_disponible():
			poner_estado(panel, "sin_git")
			return []
		try:
			paginas = wiki_del_panel(panel).sincronizar()
		except w.WikiSinPaginas:
			poner_estado(panel, "vacia")
			return []
		poner_estado(panel, "activa")
		return [como_fila(p) for p in paginas]

	def etiqueta(panel: Any) -> str:
		return _(ETIQUETAS_ESTADO.get(estado(panel), "Wiki"))

	def paginas_de(panel: Any) -> list[w.PaginaWiki]:
		return [e["_pagina"] for e in panel.elementos if isinstance(e, dict) and "_pagina" in e]

	def titulo_visor(pagina: w.PaginaWiki) -> str:
		return _("{t} — wiki de {n}").format(t=pagina.titulo, n=nombre)

	def mostrar_pagina(panel: Any, pagina: w.PaginaWiki, texto: str, titulo: str = "") -> None:
		from app.ui import visor_ayuda

		def al_enlace(direccion: str) -> bool:
			# Un enlace a otra página de esta wiki se abre aquí; lo demás, en el navegador.
			destino = w.pagina_de_enlace(direccion, host, nombre)
			encontrada = w.buscar_pagina(paginas_de(panel), destino) if destino and panel else None
			if encontrada is None:
				return False
			abrir_pagina(panel, encontrada)
			return True

		visor_ayuda.mostrar_documento(panel, titulo or titulo_visor(pagina), w.documento_para_visor(pagina, texto, host, nombre),
			al_enlace=al_enlace, ayuda=_(
				"Página de la wiki. Los enlaces a otras páginas de la wiki se abren aquí mismo. Escape o Alt+C cierran; "
				"Control+F busca. Para editarla, vuelva a la lista y pulse F2."))

	def abrir_pagina(panel: Any, pagina: w.PaginaWiki) -> None:
		wiki = wiki_del_panel(panel)
		_en_fondo(panel, lambda: wiki.leer(pagina.archivo), lambda texto: mostrar_pagina(panel, pagina, texto), "")

	def activar(panel: Any, elemento: dict) -> None:
		abrir_pagina(panel, elemento["_pagina"])

	def editar_pagina(panel: Any, elemento: dict) -> None:
		from app.ui.editor import CampoExtra, editar

		pagina: w.PaginaWiki = elemento["_pagina"]
		wiki = wiki_del_panel(panel)

		def abrir_editor(texto: str) -> None:
			def enviar(valores: dict) -> Any:
				return wiki.guardar(pagina.archivo, valores["cuerpo"], str(valores.get("mensaje", "")).strip())

			editar(panel, panel.ctx, _("Editar «{t}» de la wiki de {n}").format(t=pagina.titulo, n=nombre), enviar,
				cuerpo=texto, etiqueta_cuerpo=_("Con&tenido de la página ({f}):").format(f=pagina.formato),
				etiqueta_enviar=_("&Guardar en la wiki"), clave_borrador=f"wiki:{host}:{nombre}:{pagina.archivo}",
				extras=[CampoExtra("mensaje", _("&Mensaje del cambio:"), "texto", valor="",
					ayuda=_("Opcional. Vacío: «Actualizar» y el título de la página."))],
				al_enviar=lambda _r: hecho(panel, _("Página «{t}» guardada.").format(t=pagina.titulo)))

		_en_fondo(panel, lambda: wiki.leer(pagina.archivo), abrir_editor, _("Abriendo la página…"))

	def hecho(panel: Any, texto: str) -> None:
		# El editor ya ha sonado «enviado»; aquí solo se dice qué ha pasado y se recarga.
		if panel:
			panel.ctx.avisar(texto)
			panel.cargar(anunciar=False)

	def nueva_pagina(panel: Any, _e: Any) -> None:
		from app.ui.editor import CampoExtra, editar

		wiki = wiki_del_panel(panel)

		def enviar(valores: dict) -> Any:
			archivo = w.archivo_para_titulo(str(valores.get("titulo", "")), str(valores.get("formato") or ".md"))
			return wiki.guardar(archivo, valores["cuerpo"], str(valores.get("mensaje", "")).strip(), nueva=True)

		editar(panel, panel.ctx, _("Nueva página en la wiki de {n}").format(n=nombre), enviar, con_titulo=True,
			etiqueta_cuerpo=_("Con&tenido de la página:"), etiqueta_enviar=_("&Crear la página"),
			clave_borrador=f"wiki:{host}:{nombre}:nueva",
			extras=[
				CampoExtra("formato", _("&Formato:"), "opcion", valor=".md", opciones=FORMATOS_NUEVA,
					ayuda=_("Markdown es el formato habitual de las wikis de GitHub.")),
				CampoExtra("mensaje", _("&Mensaje del cambio:"), "texto", valor="", ayuda=_("Opcional. Vacío: «Crear» y el título.")),
			],
			al_enviar=lambda r: hecho(panel, _("Página «{t}» creada.").format(t=getattr(r, "titulo", ""))))

	def renombrar(panel: Any, elemento: dict) -> None:
		pagina: w.PaginaWiki = elemento["_pagina"]
		titulo = pedir_texto(panel, _("&Título nuevo:"), _("Cambiar el título de la página"), pagina.titulo)
		if not titulo or not titulo.strip() or titulo.strip() == pagina.titulo:
			return
		wiki = wiki_del_panel(panel)
		_hacer(panel, lambda: wiki.renombrar(pagina.archivo, titulo.strip()),
			_("Página renombrada a «{t}».").format(t=titulo.strip()), inicio=_("Renombrando la página…"))

	def borrar(panel: Any, elemento: dict) -> None:
		pagina: w.PaginaWiki = elemento["_pagina"]
		if not confirmar_peligro(panel, _("¿Borrar la página «{t}» de la wiki? Seguirá en el historial de la wiki.").format(
			t=pagina.titulo), _("Borrar la página")):
			return
		wiki = wiki_del_panel(panel)
		_hacer(panel, lambda: wiki.borrar(pagina.archivo), _("Página «{t}» borrada.").format(t=pagina.titulo),
			inicio=_("Borrando la página…"))

	def historial(panel: Any, elemento: dict) -> None:
		pagina: w.PaginaWiki = elemento["_pagina"]
		wiki = wiki_del_panel(panel)

		def elegir(commits: list) -> None:
			if not commits:
				mostrar_mensaje(panel, _("Esta página no tiene historial."), _("Historial de la página"))
				return
			filas = [_("{f}, {a}: {m}").format(f=f.fecha_completa(c.fecha), a=c.autor, m=c.asunto) for c in commits]
			eleccion = elegir_uno(panel, _("Historial de «{t}»").format(t=pagina.titulo),
				_("{n} &cambios (el más reciente primero):").format(n=len(commits)), filas)
			if eleccion is None:
				return
			commit = commits[eleccion]
			que = elegir_uno(panel, _("Historial de «{t}»").format(t=pagina.titulo), _("&Qué quiere ver:"),
				[_("La página tal como quedó en ese cambio"), _("Las diferencias de ese cambio")])
			if que == 0:
				_en_fondo(panel, lambda: wiki.version(pagina.archivo, commit.sha),
					lambda texto: mostrar_pagina(panel, pagina, texto, _("{t} ({c}, {f}) — wiki de {n}").format(
						t=pagina.titulo, c=commit.sha_corto, f=f.fecha_completa(commit.fecha), n=nombre)),
					_("Cargando la versión…"))
			elif que == 1:
				from app.ui.detalle.diferencias import abrir_diff

				abrir_diff(panel.ctx, panel, _("Cambios en «{t}»: {m}").format(t=pagina.titulo, m=commit.asunto),
					lambda: wiki.diferencias(pagina.archivo, commit.sha),
					cabecera=_("{a}, {f}").format(a=commit.autor, f=f.fecha_completa(commit.fecha)))

		_en_fondo(panel, lambda: wiki.historial(pagina.archivo), elegir, _("Cargando el historial…"))

	def buscar(panel: Any, _e: Any) -> None:
		texto = pedir_texto(panel, _("&Texto que busca:"), _("Buscar en todas las páginas"))
		if not texto or not texto.strip():
			return
		buscado = texto.strip()
		wiki = wiki_del_panel(panel)
		paginas = paginas_de(panel)

		def trabajo() -> list[tuple[w.PaginaWiki, str]]:
			resultados = []
			for pagina in paginas:
				try:
					contenido = wiki.leer(pagina.archivo)
				except OSError:
					continue
				lineas = [linea.strip() for linea in contenido.splitlines() if buscado.casefold() in linea.casefold()]
				if lineas or buscado.casefold() in pagina.titulo.casefold():
					resultados.append((pagina, lineas[0] if lineas else ""))
			return resultados

		def elegir(resultados: list[tuple[w.PaginaWiki, str]]) -> None:
			if not resultados:
				panel.ctx.sonar("vacio")
				mostrar_mensaje(panel, _("Ninguna página contiene «{t}».").format(t=buscado), _("Buscar en todas las páginas"))
				return
			filas = [f"{p.titulo}: {linea[:160]}" if linea else p.titulo for p, linea in resultados]
			eleccion = elegir_uno(panel, _("Buscar en todas las páginas"),
				_("{n} &páginas con «{t}»:").format(n=len(resultados), t=buscado), filas)
			if eleccion is not None:
				abrir_pagina(panel, resultados[eleccion][0])

		_en_fondo(panel, trabajo, elegir, _("Buscando en la wiki…"))

	def copiar_texto(panel: Any, elemento: dict) -> None:
		wiki = wiki_del_panel(panel)
		_en_fondo(panel, lambda: wiki.leer(elemento["archivo"]),
			lambda texto: copiar(panel.ctx, texto, _("Texto de la página copiado.")), "")

	def activar_wiki(panel: Any, _e: Any) -> None:
		api = panel.ctx.api()

		def listo(repo: Any) -> None:
			if not panel:
				return
			if isinstance(repo, dict):
				panel.datos["info"] = repo
			panel.cargar(anunciar=False)

		en_segundo_plano(panel, panel.ctx, lambda: api.editar_repositorio(nombre, has_wiki=True),
			exito=_("Wiki activada. Cree la primera página en el navegador para empezar."), al_terminar=listo)

	def clonar(panel: Any, _e: Any) -> None:
		from app.ui.git.clonar import dialogo_clonar

		dialogo_clonar(panel, panel.ctx, w.url_clonado(host, nombre), f"{nombre}.wiki")

	def descargar_de_nuevo(panel: Any, _e: Any) -> None:
		wiki = wiki_del_panel(panel)
		_hacer(panel, wiki.olvidar, _("Copia local borrada; se descarga de nuevo."), inicio=_("Borrando la copia local…"))

	def url(elemento: dict) -> str:
		return w.url_web(host, nombre, elemento.get("nombre", ""))

	def detalle(elemento: dict, ctx: Any) -> str:
		return "\n".join([
			_("Página: {t}").format(t=elemento.get("titulo", "")),
			_("Tipo: {t}").format(t=elemento.get("tipo", "")),
			_("Formato: {f}").format(f=elemento.get("formato", "")),
			_("Tamaño: {t}").format(t=f.tamano(elemento.get("tamano"))),
			_("Archivo: {a}").format(a=elemento.get("archivo", "")),
			_("Enlace: {u}").format(u=url(elemento)),
		])

	def con(*estados: str):
		return lambda p, e: estado(p) in estados

	return VistaRepo(
		"repo_wiki", _("Wiki"),
		[
			Columna("titulo", _("Página"), lambda e, c: e.get("titulo", ""), 300),
			Columna("tipo", _("Tipo"), lambda e, c: e.get("tipo", ""), 110),
			Columna("formato", _("Formato"), lambda e, c: e.get("formato", ""), 110),
			Columna("tamano", _("Tamaño"), lambda e, c: f.tamano(e.get("tamano")), 90),
			Columna("archivo", _("Archivo"), lambda e, c: e.get("archivo", ""), 220, visible=False),
		],
		cargar, activar,
		[
			Accion(_("A&brir la página"), activar, "Intro"),
			Accion(_("Ed&itar la página…"), editar_pagina, "F2"),
			Accion(_("Nue&va página…"), nueva_pagina, "Ctrl+N", requiere_elemento=False, disponible=con("activa")),
			Accion(_("Cambiar el &título…"), renombrar),
			Accion(_("Borrar la pá&gina…"), borrar, "Supr"),
			Accion(_("&Historial de la página…"), historial, separador_antes=True),
			Accion(_("B&uscar en todas las páginas…"), buscar, "Ctrl+P", requiere_elemento=False, disponible=con("activa")),
			Accion(_("Copiar el te&xto de la página"), copiar_texto),
			Accion(_("Abrir la &wiki en el navegador"), lambda p, e: webbrowser.open(w.url_web(host, nombre)), requiere_elemento=False,
				separador_antes=True),
			Accion(_("Crear la &primera página en el navegador"), lambda p, e: webbrowser.open(w.url_nueva_pagina(host, nombre)),
				requiere_elemento=False, disponible=con("vacia")),
			Accion(_("Activar la wi&ki…"), activar_wiki, requiere_elemento=False, disponible=con("desactivada"),
				ayuda=_("Activa la wiki del repositorio (necesita permiso de administración).")),
			Accion(_("C&lonar la wiki en una carpeta…"), clonar, requiere_elemento=False, disponible=con("activa"),
				ayuda=_("Descarga la wiki con git a una carpeta suya para trabajar con ella como con cualquier repositorio.")),
			Accion(_("&Copiar la dirección git de la wiki"), lambda p, e: copiar(p.ctx, w.url_clonado(host, nombre),
				_("Copiada: {u}").format(u=w.url_clonado(host, nombre))), requiere_elemento=False, disponible=con("activa", "vacia")),
			Accion(_("Volver a desca&rgar la wiki entera"), descargar_de_nuevo, requiere_elemento=False, disponible=con("activa"),
				ayuda=_("Borra la copia guardada en data/cache y la descarga otra vez (por si se ha estropeado).")),
		],
		_("Cargando la wiki…"), url, detalle, paginada=False, sonido_carga=False, etiqueta_de=etiqueta,
	)

