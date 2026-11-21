"""Secciones de la ventana del repositorio que no son una lista: resumen, estadísticas y Pages.

Tienen la misma interfaz que ``PanelLista`` para la ventana (``cargar``,
``cargar_si_hace_falta``, ``acciones_disponibles``, ``ejecutar``,
``crear_menu``, ``control_foco``), así que el menú «Acciones», F5 y F6
funcionan igual en todas las secciones.

Los textos largos van en un ``TextCtrl`` de solo lectura (``TE_RICH2``): el
lector lo recorre línea a línea y se puede copiar.
"""

from __future__ import annotations

import builtins
import logging
import time
import webbrowser
from collections.abc import Callable
from typing import Any

import wx

from app.services import formato as f
from app.ui.accesibilidad.dialogos import mostrar_error
from app.ui.accesibilidad.teclado import copiar_texto, vincular_menu_contextual
from app.ui.comunes import confirmar_peligro, elegir_uno, en_segundo_plano, mensaje_error, mostrar_mensaje
from app.ui.vistas.base import Accion
from app.ui.vistas.principales import detalle_repositorio

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


ESTILO_TEXTO = wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2


class PanelSeccion(wx.Panel):
	"""Base de las secciones de texto: carga en segundo plano y acciones como ``PanelLista``."""

	titulo = ""

	def __init__(self, padre: wx.Window, ctx: Any, datos: dict) -> None:
		super().__init__(padre)
		self.ctx = ctx
		self.datos = dict(datos)
		self.cargado = False
		self.cargando = False
		self._version = 0
		self.texto: wx.TextCtrl | None = None

	@property
	def nombre(self) -> str:
		return self.datos.get("nombre", "")

	def crear_texto(self, sizer: wx.Sizer, etiqueta: str, ayuda: str) -> wx.TextCtrl:
		"""Etiqueta y, justo después, el campo de solo lectura con el menú de acciones."""
		sizer.Add(wx.StaticText(self, label=etiqueta), 0, wx.LEFT | wx.TOP | wx.RIGHT, 4)
		texto = wx.TextCtrl(self, value=_("Cargando…"), style=ESTILO_TEXTO)
		texto.SetHelpText(ayuda + " " + _("Texto de solo lectura: recórralo con las flechas. Aplicaciones abre las acciones."))
		vincular_menu_contextual(texto, self.crear_menu)
		sizer.Add(texto, 1, wx.EXPAND | wx.ALL, 4)
		self.texto = texto
		return texto

	def poner_texto(self, texto: str) -> None:
		if self.texto is not None:
			self.texto.SetValue(texto)
			self.texto.SetInsertionPoint(0)

	# ── Interfaz común con PanelLista ─────────────────────────────────────────

	def control_foco(self) -> wx.Window:
		return self.texto or self

	def acciones(self) -> list[Accion]:
		return [
			Accion(_("&Actualizar"), lambda p, e: p.cargar(), "F5", requiere_elemento=False),
			Accion(_("C&opiar todo el texto"), lambda p, e: p.copiar_todo(), requiere_elemento=False),
		]

	def acciones_disponibles(self) -> list[Accion]:
		resultado = []
		for accion in self.acciones():
			try:
				if accion.disponible is None or accion.disponible(self, None):
					resultado.append(accion)
			except Exception:  # noqa: BLE001 - una condición rota oculta la acción, no la ventana
				log.debug("Condición de acción falló", exc_info=True)
		return resultado

	def ejecutar(self, accion: Accion) -> None:
		try:
			accion.funcion(self, None)
		except Exception as error:  # noqa: BLE001 - se informa y se registra, la ventana sigue viva
			log.exception("Fallo en la acción %s", accion.etiqueta)
			mostrar_error(self, mensaje_error(error), _("Error"))

	def crear_menu(self, acciones: list[Accion] | None = None, en_barra: bool = False) -> wx.Menu:
		menu = wx.Menu()
		for accion in acciones if acciones is not None else self.acciones_disponibles():
			etiqueta = accion.etiqueta
			if accion.atajo:
				etiqueta += f" ({accion.atajo})" if en_barra else f"\t{accion.atajo}"
			item = menu.Append(wx.ID_ANY, etiqueta, accion.ayuda)
			menu.Bind(wx.EVT_MENU, lambda _e, a=accion: wx.CallAfter(self.ejecutar, a), item)
		return menu

	def copiar_todo(self) -> None:
		if self.texto is not None and copiar_texto(self.texto.GetValue()):
			self.ctx.sonar("copiado")
			self.ctx.avisar(_("Texto copiado."))

	# ── Carga ─────────────────────────────────────────────────────────────────

	def cargar_si_hace_falta(self) -> None:
		if not self.cargado and not self.cargando:
			self.cargar()

	def cargar(self, anunciar: bool = True) -> None:
		self._version += 1
		version = self._version
		self.cargando = True
		api = self.ctx.api()

		def al_terminar(resultado: Any) -> None:
			if not self or version != self._version:
				return
			self.cargando = False
			self.cargado = True
			self.mostrar(resultado)
			if anunciar:
				self.ctx.sonar("listo")

		def al_fallar(error: BaseException) -> None:
			if not self or version != self._version:
				return
			self.cargando = False
			self.ctx.sonar("error")
			self.poner_texto(_("No se pudo cargar: {m}").format(m=mensaje_error(error)))
			self.ctx.avisar(_("Error al cargar {t}: {m}").format(t=self.titulo, m=mensaje_error(error)))

		self.ctx.tareas.enviar(lambda tarea: self.obtener(api), al_terminar=al_terminar, al_fallar=al_fallar,
			nombre=f"repositorio:{type(self).__name__}", duplicadas="permitir")

	def obtener(self, api: Any) -> Any:  # pragma: no cover - lo definen las subclases
		"""Se ejecuta en un hilo: solo red y cálculos, nunca controles."""
		raise NotImplementedError

	def mostrar(self, datos: Any) -> None:  # pragma: no cover - lo definen las subclases
		raise NotImplementedError


def _intentar(funcion: Callable[[], Any], defecto: Any = None) -> Any:
	"""Llama a la API; si falla (403, 404...) devuelve ``defecto`` y lo registra."""
	try:
		return funcion()
	except Exception as error:  # noqa: BLE001 - un dato que falta no impide mostrar el resto
		log.info("Dato no disponible: %s", mensaje_error(error))
		return defecto


# ════════════════════════════════════════════════════════════════════════════
# Resumen
# ════════════════════════════════════════════════════════════════════════════


def porcentajes_lenguajes(lenguajes: dict | None) -> list[str]:
	"""{"Python": 900, "C": 100} → ["Python: 90,0 %", "C: 10,0 %"] (de más a menos)."""
	if not lenguajes:
		return []
	total = sum(int(v or 0) for v in lenguajes.values()) or 1
	return [f"{nombre}: {int(octetos or 0) * 100 / total:.1f} %".replace(".", ",")
		for nombre, octetos in sorted(lenguajes.items(), key=lambda par: -int(par[1] or 0))]


class PanelResumen(PanelSeccion):
	titulo = "Resumen"

	def __init__(self, padre: wx.Window, ctx: Any, datos: dict) -> None:
		super().__init__(padre, ctx, datos)
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.crear_texto(raiz, _("In&formación del repositorio:"), _("Datos del repositorio."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		columna = wx.BoxSizer(wx.VERTICAL)
		columna.Add(wx.StaticText(self, label=_("Len&guajes:")), 0, wx.ALL, 4)
		self.lenguajes = wx.ListBox(self, choices=[], style=wx.LB_SINGLE)
		self.lenguajes.SetHelpText(_("Lenguajes del código, con el porcentaje de cada uno."))
		columna.Add(self.lenguajes, 1, wx.EXPAND | wx.ALL, 4)
		fila.Add(columna, 1, wx.EXPAND)
		columna = wx.BoxSizer(wx.VERTICAL)
		columna.Add(wx.StaticText(self, label=_("&Temas:")), 0, wx.ALL, 4)
		self.temas = wx.ListBox(self, choices=[], style=wx.LB_SINGLE)
		self.temas.SetHelpText(_("Temas (topics) del repositorio. Se cambian en Repositorio, Configuración."))
		columna.Add(self.temas, 1, wx.EXPAND | wx.ALL, 4)
		fila.Add(columna, 1, wx.EXPAND)
		raiz.Add(fila, 0, wx.EXPAND)
		self.boton_readme = wx.Button(self, label=_("Leer el R&EADME"))
		self.boton_readme.SetHelpText(_("Abre el README con formato (encabezados, listas y enlaces) en el visor accesible."))
		self.boton_readme.Bind(wx.EVT_BUTTON, lambda _e: self.leer_readme())
		raiz.Add(self.boton_readme, 0, wx.ALL, 4)
		self.SetSizer(raiz)

	def acciones(self) -> list[Accion]:
		return [
			Accion(_("Leer el R&EADME"), lambda p, e: p.leer_readme(), requiere_elemento=False),
			*super().acciones(),
		]

	def obtener(self, api: Any) -> dict:
		repo = api.repositorio(self.nombre)
		return {
			"repo": repo if isinstance(repo, dict) else {},
			"lenguajes": _intentar(lambda: api.lenguajes(self.nombre), {}),
			"release": _intentar(lambda: api.ultima_release(self.nombre), None),
		}

	def mostrar(self, datos: dict) -> None:
		repo = datos.get("repo") or {}
		self.datos["info"] = repo
		lineas = [detalle_repositorio(repo, self.ctx)]
		lineas.append(_("Observadores (watch): {n}").format(n=f.numero(repo.get("subscribers_count"))))
		release = datos.get("release")
		if isinstance(release, dict) and release.get("tag_name"):
			lineas.append(_("Última release: {n} ({t}), {f}").format(n=release.get("name") or release["tag_name"],
				t=release["tag_name"], f=f.fecha_completa(release.get("published_at"))))
		permisos = repo.get("permissions") or {}
		if permisos:
			nivel = next((p for p in ("admin", "maintain", "push", "triage", "pull") if permisos.get(p)), "")
			lineas.append(_("Su permiso: {p}").format(p=f.estado(nivel) or "-"))
		self.poner_texto("\n".join(lineas))
		lenguajes = porcentajes_lenguajes(datos.get("lenguajes") if isinstance(datos.get("lenguajes"), dict) else {})
		self.lenguajes.Set(lenguajes or [_("(sin datos)")])
		self.temas.Set(list(repo.get("topics") or []) or [_("(ninguno)")])
		for lista in (self.lenguajes, self.temas):
			lista.SetSelection(0)

	def leer_readme(self) -> None:
		from app.ui import visor_ayuda

		api = self.ctx.api()
		nombre = self.nombre

		def mostrar(texto: str) -> None:
			if not texto or not texto.strip():
				mostrar_mensaje(self, _("El README está vacío."), _("README"))
				return
			visor_ayuda.mostrar_documento(self, _("README de {n}").format(n=nombre), texto)

		def fallo(error: BaseException) -> None:
			if getattr(error, "codigo_http", None) == 404:
				mostrar_mensaje(self, _("Este repositorio no tiene README."), _("README"))
			else:
				mostrar_error(self, mensaje_error(error), _("No se pudo leer el README"))

		en_segundo_plano(self, self.ctx, lambda: api.readme(nombre), al_terminar=mostrar, al_fallar=fallo, sonido="",
			inicio=_("Cargando el README…"))


# ════════════════════════════════════════════════════════════════════════════
# Estadísticas
# ════════════════════════════════════════════════════════════════════════════

#: GitHub calcula algunas estadísticas en segundo plano y responde 202 sin datos
#: la primera vez: se reintenta unas cuantas veces con esta espera (segundos).
ESPERA_ESTADISTICAS = 2.0
REINTENTOS_ESTADISTICAS = 4


def pedir_estadistica(funcion: Callable[[], Any], reintentos: int | None = None, espera: float | None = None) -> Any:
	"""Llama a un punto de /stats reintentando mientras GitHub conteste vacío (202 «calculando»).

	Devuelve ``None`` si tras los reintentos sigue sin datos. Se ejecuta en un hilo.
	"""
	veces = REINTENTOS_ESTADISTICAS if reintentos is None else reintentos
	pausa = ESPERA_ESTADISTICAS if espera is None else espera
	for intento in range(max(1, veces)):
		datos = funcion()
		if datos:
			return datos
		if intento < veces - 1:
			time.sleep(pausa)
	return None


def _no_disponible(error: BaseException) -> str:
	return _("no disponible ({m})").format(m=mensaje_error(error))


def componer_estadisticas(datos: dict) -> str:
	"""Texto legible de todas las estadísticas (función pura: se prueba sin wx ni red)."""
	lineas: list[str] = []
	calculando = _("GitHub aún las está calculando o no hay datos. Pulse F5 dentro de unos segundos.")

	for clave, titulo, unidad in (("visitas", _("Visitas en los últimos 14 días"), "views"),
		("clonados", _("Clonados en los últimos 14 días"), "clones")):
		valor = datos.get(clave)
		lineas.append(titulo + ":")
		if isinstance(valor, BaseException):
			lineas.append("\t" + _no_disponible(valor))
		elif isinstance(valor, dict):
			lineas.append("\t" + _("{n} en total, {u} personas distintas.").format(n=valor.get("count", 0), u=valor.get("uniques", 0)))
			for dia in valor.get(unidad) or []:
				if dia.get("count"):
					lineas.append("\t" + _("{f}: {n} ({u} distintas)").format(f=f.fecha_completa(dia.get("timestamp")).split(" ")[0],
						n=dia.get("count", 0), u=dia.get("uniques", 0)))
		lineas.append("")

	for clave, titulo in (("referentes", _("Sitios que más visitas traen")), ("rutas", _("Páginas más vistas"))):
		valor = datos.get(clave)
		lineas.append(titulo + ":")
		if isinstance(valor, BaseException):
			lineas.append("\t" + _no_disponible(valor))
		elif not valor:
			lineas.append("\t" + _("Sin datos."))
		else:
			for elemento in valor:
				nombre = elemento.get("referrer") or elemento.get("title") or elemento.get("path", "")
				lineas.append("\t" + _("{n}: {c} visitas ({u} distintas)").format(n=nombre, c=elemento.get("count", 0),
					u=elemento.get("uniques", 0)))
		lineas.append("")

	lineas.append(_("Commits por semana (último año):"))
	participacion = datos.get("participacion")
	if isinstance(participacion, BaseException):
		lineas.append("\t" + _no_disponible(participacion))
	elif not participacion:
		lineas.append("\t" + calculando)
	else:
		todos = participacion.get("all") or []
		propios = participacion.get("owner") or []
		lineas.append("\t" + _("{t} commits en 52 semanas; {p} del propietario.").format(t=sum(todos), p=sum(propios)))
		lineas.append("\t" + _("Últimas 4 semanas: {s}.").format(s=", ".join(str(n) for n in todos[-4:]) or "-"))
	lineas.append("")

	lineas.append(_("Personas que más contribuyen:"))
	contribuyentes = datos.get("contribuyentes")
	if isinstance(contribuyentes, BaseException):
		lineas.append("\t" + _no_disponible(contribuyentes))
	elif not contribuyentes:
		lineas.append("\t" + calculando)
	else:
		for c in sorted(contribuyentes, key=lambda c: -int(c.get("total") or 0))[:25]:
			anadidas = sum(int(s.get("a") or 0) for s in c.get("weeks") or [])
			borradas = sum(int(s.get("d") or 0) for s in c.get("weeks") or [])
			lineas.append("\t" + _("{l}: {n} commits, {a} líneas añadidas y {b} borradas").format(
				l=f.login(c.get("author")), n=c.get("total", 0), a=f.numero(anadidas), b=f.numero(borradas)))
	return "\n".join(lineas).rstrip()


class PanelEstadisticas(PanelSeccion):
	titulo = "Estadísticas"

	def __init__(self, padre: wx.Window, ctx: Any, datos: dict) -> None:
		super().__init__(padre, ctx, datos)
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.crear_texto(raiz, _("Es&tadísticas:"), _("Tráfico, clonados, referentes, participación y contribuyentes. "
			"El tráfico solo lo ven quienes tienen permiso de escritura."))
		self.SetSizer(raiz)

	def obtener(self, api: Any) -> dict:
		nombre = self.nombre
		datos: dict[str, Any] = {}
		for clave, funcion, es_estadistica in (
			("visitas", lambda: api.visitas(nombre), False), ("clonados", lambda: api.clonados(nombre), False),
			("referentes", lambda: api.referentes(nombre), False), ("rutas", lambda: api.rutas_populares(nombre), False),
			("participacion", lambda: api.participacion(nombre), True),
			("contribuyentes", lambda: api.estadisticas_contribuyentes(nombre), True),
		):
			try:
				datos[clave] = pedir_estadistica(funcion) if es_estadistica else funcion()
			except Exception as error:  # noqa: BLE001 - cada bloque muestra su propio motivo
				log.info("Estadística %s de %s no disponible: %s", clave, nombre, mensaje_error(error))
				datos[clave] = error
		return datos

	def mostrar(self, datos: dict) -> None:
		self.poner_texto(componer_estadisticas(datos))


# ════════════════════════════════════════════════════════════════════════════
# GitHub Pages
# ════════════════════════════════════════════════════════════════════════════


def componer_pages(pages: dict | None, compilaciones: list | None) -> str:
	if not pages:
		return _("GitHub Pages no está activado en este repositorio. Actívelo con el botón «Activar Pages».")
	origen = pages.get("source") or {}
	lineas = [
		_("Estado: {e}").format(e={"built": _("publicado"), "building": _("compilando"), "errored": _("con errores")}.get(
			pages.get("status") or "", pages.get("status") or _("desconocido"))),
		_("Dirección del sitio: {u}").format(u=pages.get("html_url", "")),
		_("Se publica: {t}").format(t=_("con GitHub Actions") if pages.get("build_type") == "workflow" else
			_("desde la rama {r}, carpeta {c}").format(r=origen.get("branch", ""), c=origen.get("path", "/"))),
		_("Dominio propio: {d}").format(d=pages.get("cname") or _("ninguno")),
		_("HTTPS obligatorio: {h}").format(h=f.si_no(pages.get("https_enforced"))),
		_("Público: {p}").format(p=f.si_no(pages.get("public", True))),
	]
	if compilaciones:
		ultima = compilaciones[0]
		lineas.append(_("Última compilación: {e}, {f}, {d}").format(e=ultima.get("status", ""),
			f=f.fecha_completa(ultima.get("created_at")), d=f.duracion((ultima.get("duration") or 0) / 1000)))
		if (ultima.get("error") or {}).get("message"):
			lineas.append(_("Error: {m}").format(m=ultima["error"]["message"]))
	return "\n".join(lineas)


class PanelPages(PanelSeccion):
	titulo = "Pages"

	def __init__(self, padre: wx.Window, ctx: Any, datos: dict) -> None:
		super().__init__(padre, ctx, datos)
		self.pages: dict | None = None
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.crear_texto(raiz, _("&Estado de GitHub Pages:"), _("Situación del sitio web publicado con GitHub Pages."))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.botones: dict[str, wx.Button] = {}
		for clave, etiqueta, ayuda, funcion in (
			("activar", _("&Activar Pages…"), _("Publica un sitio desde una rama o con GitHub Actions."), self.activar),
			("desactivar", _("&Desactivar Pages…"), _("Retira el sitio publicado."), self.desactivar),
			("recompilar", _("Recompi&lar ahora"), _("Vuelve a publicar el sitio desde la rama."), self.recompilar),
			("navegador", _("Abrir el sitio en el &navegador"), _("Abre la dirección del sitio."), self.abrir_sitio),
		):
			boton = wx.Button(self, label=etiqueta)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, lambda _e, fn=funcion: fn())
			fila.Add(boton, 0, wx.ALL, 4)
			self.botones[clave] = boton
		raiz.Add(fila, 0)
		self.SetSizer(raiz)
		self._habilitar()

	def _habilitar(self) -> None:
		activo = bool(self.pages)
		self.botones["activar"].Enable(not activo)
		for clave in ("desactivar", "recompilar", "navegador"):
			self.botones[clave].Enable(activo)

	def acciones(self) -> list[Accion]:
		return [
			Accion(_("&Actualizar"), lambda p, e: p.cargar(), "F5", requiere_elemento=False),
			Accion(_("Ac&tivar Pages…"), lambda p, e: p.activar(), requiere_elemento=False, disponible=lambda p, e: not p.pages),
			Accion(_("&Desactivar Pages…"), lambda p, e: p.desactivar(), requiere_elemento=False, disponible=lambda p, e: bool(p.pages)),
			Accion(_("Recompi&lar ahora"), lambda p, e: p.recompilar(), requiere_elemento=False, disponible=lambda p, e: bool(p.pages)),
			Accion(_("Abrir el sitio en el &navegador"), lambda p, e: p.abrir_sitio(), requiere_elemento=False,
				disponible=lambda p, e: bool(p.pages)),
			Accion(_("C&opiar todo el texto"), lambda p, e: p.copiar_todo(), requiere_elemento=False),
		]

	def obtener(self, api: Any) -> tuple[dict | None, list]:
		pages = api.pages(self.nombre)
		compilaciones = _intentar(lambda: api.compilaciones_pages(self.nombre), []) if pages else []
		return (pages if isinstance(pages, dict) else None), list(compilaciones or [])

	def mostrar(self, datos: tuple[dict | None, list]) -> None:
		self.pages, compilaciones = datos
		self.poner_texto(componer_pages(self.pages, compilaciones))
		self._habilitar()

	def _hecho(self, texto: str) -> Callable[[Any], None]:
		def recargar(_r: Any) -> None:
			if self:
				self.cargar(anunciar=False)

		return recargar

	def activar(self) -> None:
		tipo = elegir_uno(self, _("Activar GitHub Pages"), _("&Cómo se publica el sitio:"),
			[_("Desde una rama (sin compilar o con Jekyll)"), _("Con un flujo de GitHub Actions")])
		if tipo is None:
			return
		api = self.ctx.api()
		nombre = self.nombre
		if tipo == 1:
			en_segundo_plano(self, self.ctx, lambda: api.activar_pages(nombre, "", "/", "workflow"),
				exito=_("Pages activado con GitHub Actions. Añada un flujo que publique el sitio."), al_terminar=self._hecho(""))
			return

		def elegir(ramas: list) -> None:
			nombres = [r.get("name", "") for r in ramas or [] if isinstance(r, dict)]
			if not nombres:
				mostrar_mensaje(self, _("El repositorio no tiene ramas."), _("Activar GitHub Pages"))
				return
			defecto = (self.datos.get("info") or {}).get("default_branch", "")
			rama = elegir_uno(self, _("Activar GitHub Pages"), _("&Rama:"), nombres, nombres.index(defecto) if defecto in nombres else 0)
			if rama is None:
				return
			carpetas = ["/", "/docs"]
			carpeta = elegir_uno(self, _("Activar GitHub Pages"), _("Carpeta de la ra&ma:"), [_("/ (raíz)"), "/docs"])
			if carpeta is None:
				return
			en_segundo_plano(self, self.ctx, lambda: api.activar_pages(nombre, nombres[rama], carpetas[carpeta]),
				exito=_("Pages activado. El sitio tardará unos minutos en publicarse."), al_terminar=self._hecho(""))

		en_segundo_plano(self, self.ctx, lambda: api.todas_las_ramas(nombre), al_terminar=elegir, sonido="")

	def desactivar(self) -> None:
		if not confirmar_peligro(self, _("¿Desactivar GitHub Pages? El sitio dejará de estar publicado."), _("Desactivar Pages")):
			return
		api = self.ctx.api()
		en_segundo_plano(self, self.ctx, lambda: api.desactivar_pages(self.nombre), exito=_("Pages desactivado."),
			al_terminar=self._hecho(""))

	def recompilar(self) -> None:
		api = self.ctx.api()
		en_segundo_plano(self, self.ctx, lambda: api.compilar_pages(self.nombre), exito=_("Compilación pedida."),
			al_terminar=self._hecho(""))

	def abrir_sitio(self) -> None:
		if self.pages and self.pages.get("html_url"):
			webbrowser.open(self.pages["html_url"])


#: Secciones que no son listas: ``(padre, ctx, datos) -> PanelSeccion``.
PANELES: dict[str, type[PanelSeccion]] = {
	"resumen": PanelResumen,
	"estadisticas": PanelEstadisticas,
	"pages": PanelPages,
}
