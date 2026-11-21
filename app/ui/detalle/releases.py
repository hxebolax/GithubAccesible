"""Releases: ventana de una release y diálogo para crear una nueva.

Ventana de una release (``abrir_release``):

- «Información»: etiqueta, estado (borrador, prelanzamiento, la última), destino,
  autor, fechas y enlaces.
- «Notas de la versión» en texto y, con F7, formateadas en el visor accesible
  (encabezados y enlaces reales para el modo exploración del lector).
- «Recursos» (archivos adjuntos): nombre, tamaño, descargas y fecha. Intro
  descarga a la carpeta de Preferencias (o la que se elija) con progreso por
  hitos; Mayús+Intro pregunta la carpeta; F2 renombra; Supr borra.
- Subir recursos (Ctrl+U, varios a la vez), editar la release (Ctrl+E),
  borrarla, copiar el enlace (Ctrl+Mayús+C), abrir en el navegador (Ctrl+B).

Nueva release (``nueva_release``): etiqueta nueva o existente, destino, título,
notas con «Generar las notas automáticamente», borrador, prelanzamiento y «la
última»; al crearla ofrece subir archivos.
"""

from __future__ import annotations

import builtins
import logging
import mimetypes
import webbrowser
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import wx

from app.core.descargas import nombre_seguro
from app.services import formato as f
from app.ui.accesibilidad.dialogos import confirmar, crear_botonera, preparar_dialogo
from app.ui.comunes import confirmar_peligro, copiar, en_segundo_plano, mensaje_error, mostrar_error, pedir_texto
from app.ui.detalle.comun_detalle import VentanaDetalle, carpeta_de_descargas, elegir_archivos, entrada_cerrar
from app.ui.editor import CampoExtra, editar

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ════════════════════════════════════════════════════════════════════════════
# Funciones puras
# ════════════════════════════════════════════════════════════════════════════


def estado_release(release: dict, es_ultima: bool = False) -> str:
	partes = []
	if release.get("draft"):
		partes.append(_("Borrador (no publicada)"))
	elif release.get("prerelease"):
		partes.append(_("Prelanzamiento"))
	else:
		partes.append(_("Publicada"))
	if es_ultima:
		partes.append(_("es la última release"))
	return ", ".join(partes)


def texto_informacion(release: dict, es_ultima: bool = False) -> str:
	lineas = [
		_("Release: {n}").format(n=release.get("name") or release.get("tag_name") or ""),
		_("Etiqueta: {e}").format(e=release.get("tag_name") or "-"),
		_("Estado: {e}").format(e=estado_release(release, es_ultima)),
		_("Destino: {d}").format(d=release.get("target_commitish") or "-"),
		_("Autor: {a}").format(a=f.login(release.get("author"))),
		_("Creada: {c}").format(c=f.fecha_completa(release.get("created_at"))),
		_("Publicada: {p}").format(p=f.fecha_completa(release.get("published_at")) if release.get("published_at") else "-"),
		_("Recursos: {n}").format(n=len(release.get("assets") or [])),
		_("Enlace: {u}").format(u=release.get("html_url") or ""),
		_("Código fuente en zip: {u}").format(u=release.get("zipball_url") or "-"),
	]
	return "\n".join(lineas)


def clave_release(nombre: str, release: dict) -> str:
	return f"release:{nombre}:{release.get('id') or release.get('tag_name') or release.get('name') or ''}"


def fila_recurso(recurso: dict, relativas: bool = True) -> list[str]:
	return [
		recurso.get("name", ""),
		f.tamano(recurso.get("size")),
		f.numero(recurso.get("download_count", 0)),
		f.fecha(recurso.get("updated_at") or recurso.get("created_at"), relativas),
	]


# ════════════════════════════════════════════════════════════════════════════
# Subida de recursos (la usan la ventana y el diálogo de nueva release)
# ════════════════════════════════════════════════════════════════════════════


def subir_recursos(ctx: Any, padre: wx.Window | None, release: dict, rutas: Sequence[str],
	al_terminar: Callable[[list], None] | None = None, estado: Callable[[str], None] | None = None) -> Any:
	"""Sube varios archivos a una release con progreso por hitos (por número de archivos)."""
	from app.core.tareas import HitosProgreso

	url_subida = release.get("upload_url") or ""
	if not url_subida:
		mostrar_error(padre, _("Esta release no admite subir archivos (falta su dirección de subida)."), _("Subir recursos"))
		return None
	rutas = [str(r) for r in rutas]
	if not rutas:
		return None
	cliente = ctx.api().c
	total = len(rutas)
	hitos = HitosProgreso(25)
	ctx.avisar(_("Subiendo {n} archivos…").format(n=total))

	def trabajo(tarea: Any) -> list:
		subidos = []
		for indice, ruta in enumerate(rutas):
			tarea.comprobar()
			tarea.progresar(indice, total, Path(ruta).name)
			tipo = mimetypes.guess_type(ruta)[0] or "application/octet-stream"
			subidos.append(cliente.subir(url_subida, Path(ruta), tipo=tipo))
		tarea.progresar(total, total, "")
		return subidos

	def al_progresar(progreso: Any) -> None:
		if estado is not None and progreso.texto:
			estado(_("Subiendo {i} de {t}: {n}").format(i=int(progreso.hecho) + 1, t=total, n=progreso.texto))
		hito = hitos.nuevo_hito(progreso.porcentaje)
		if hito is not None and hito < 100 and total > 1:
			ctx.avisar(_("{p} por ciento").format(p=hito), interrumpir=False)

	def terminado(subidos: list) -> None:
		ctx.sonar("completado")
		texto = _("{n} archivos subidos.").format(n=len(subidos)) if len(subidos) != 1 else _("Archivo subido.")
		ctx.avisar(texto, interrumpir=False)
		if estado is not None:
			estado(texto)
		if al_terminar is not None:
			al_terminar(subidos)

	def fallado(error: BaseException) -> None:
		ctx.sonar("error")
		if estado is not None:
			estado(_("La subida falló."))
		ventana = padre if padre and not padre.IsBeingDeleted() else None
		mostrar_error(ventana, mensaje_error(error), _("No se pudo subir"))
		if al_terminar is not None:
			al_terminar([])

	return ctx.tareas.enviar(trabajo, al_terminar=terminado, al_fallar=fallado, al_progresar=al_progresar,
		nombre="subir_recursos", duplicadas="permitir")


# ════════════════════════════════════════════════════════════════════════════
# Ventana de una release
# ════════════════════════════════════════════════════════════════════════════


class VentanaRelease(VentanaDetalle):
	"""Datos, notas y recursos de una release."""

	def __init__(self, ctx: Any, padre: wx.Window | None, nombre: str, elemento: dict) -> None:
		datos = dict(elemento or {})
		titulo = datos.get("name") or datos.get("tag_name") or _("Release")
		super().__init__(padre, ctx, _("Release {t} de {n}").format(t=titulo, n=nombre),
			clave=clave_release(nombre, datos), tamano=(980, 720))
		self.nombre = nombre
		self.release: dict = datos
		self.recursos: list[dict] = list(datos.get("assets") or [])
		self.es_ultima = False
		self._construir()
		self._pintar()

	def _construir(self) -> None:
		self.info = self.crear_texto(_("&Información:"), alto=130)
		self.notas = self.crear_texto(_("&Notas de la versión:"), alto=200, proporcion=1,
			ayuda=_("Notas en Markdown. F7 las muestra formateadas, con encabezados y enlaces."))
		self.lista = self.crear_lista(_("&Recursos:"), _("Recursos"),
			[(_("Nombre"), 300), (_("Tamaño"), 100), (_("Descargas"), 90), (_("Fecha"), 140)],
			ayuda=_("Archivos de la release. Intro descarga; Mayúsculas+Intro pregunta la carpeta; F2 renombra; Supr borra."))
		self.teclas_de_lista(self.lista, {
			"F2": self.renombrar_recurso, "Supr": self.borrar_recurso, "Shift+Intro": lambda: self.descargar_recurso(True),
		}, al_activar=self.descargar_recurso)
		self.menu_contextual(self.lista, self._entradas_recursos)
		self.poner_menus([(_("&Acciones"), [
			(_("&Ver las notas formateadas\tF7"), self.ver_formateado),
			None,
			*self._entradas_recursos(),
			(_("Descargar &todos los recursos"), self.descargar_todos),
			(_("&Subir recursos…\tCtrl+U"), self.subir),
			None,
			(_("&Editar la release…\tCtrl+E"), self.editar),
			(_("Borrar la re&lease…"), self.borrar_release),
			None,
			(_("&Copiar el enlace\tCtrl+Shift+C"), self.copiar_enlace),
			(_("Abrir en el nave&gador\tCtrl+B"), self.abrir_navegador),
			(_("&Actualizar\tF5"), lambda: self.cargar()),
			entrada_cerrar(self, _("Ce&rrar la ventana\tCtrl+W")),
		])])

	def _entradas_recursos(self) -> list:
		return [
			(_("&Descargar el recurso (Intro)"), self.descargar_recurso),
			(_("Descargar en &otra carpeta… (Mayús+Intro)"), lambda: self.descargar_recurso(True)),
			(_("Re&nombrar el recurso… (F2)"), self.renombrar_recurso),
			(_("&Borrar el recurso… (Supr)"), self.borrar_recurso),
		]

	# ── Datos ─────────────────────────────────────────────────────────────────

	def _pintar(self) -> None:
		self.info.SetValue(texto_informacion(dict(self.release, assets=self.recursos), self.es_ultima))
		self.notas.SetValue(self.release.get("body") or _("(sin notas)"))
		self.lista.reemplazar_filas([fila_recurso(r, self.ctx.relativas()) for r in self.recursos], conservar_foco=True)
		if self.recursos and self.lista.fila_actual() == wx.NOT_FOUND:
			self.lista.enfocar_fila(0, anunciar=False)
		titulo = self.release.get("name") or self.release.get("tag_name") or _("Release")
		self.SetTitle(_("Release {t} de {n}").format(t=titulo, n=self.nombre))
		self.estado(_("{n} recursos.").format(n=len(self.recursos)))

	def cargar(self, anunciar: bool = True) -> None:
		id_release = self.release.get("id")
		if not id_release:
			return
		api = self.ctx.api()

		def obtener() -> tuple[dict, list, bool]:
			release = api.release(self.nombre, id_release)
			recursos = api.recursos(self.nombre, id_release)
			try:
				ultima = (api.ultima_release(self.nombre) or {}).get("id") == id_release
			except Exception:  # noqa: BLE001 - un repositorio sin releases publicadas responde 404
				log.debug("No se pudo saber cuál es la última release de %s", self.nombre, exc_info=True)
				ultima = False
			return release, recursos, ultima

		def listo(datos: tuple[dict, list, bool]) -> None:
			self.release, self.recursos, self.es_ultima = dict(datos[0] or {}), list(datos[1] or []), bool(datos[2])
			self._pintar()
			if anunciar:
				self.ctx.sonar("listo")

		self.en_fondo(obtener, al_terminar=listo, sonido="")

	@property
	def recurso(self) -> dict | None:
		fila = self.lista.fila_actual()
		return self.recursos[fila] if 0 <= fila < len(self.recursos) else None

	# ── Acciones ──────────────────────────────────────────────────────────────

	def ver_formateado(self) -> None:
		from app.ui import visor_ayuda

		texto = self.release.get("body") or ""
		if not texto.strip():
			self.ctx.avisar(_("Esta release no tiene notas."))
			return
		titulo = self.release.get("name") or self.release.get("tag_name") or _("Release")
		visor_ayuda.mostrar_documento(self, _("Notas de {t}").format(t=titulo), texto)

	def descargar_recurso(self, preguntar: bool = False, recurso: dict | None = None, carpeta: str | None = None) -> None:
		recurso = recurso or self.recurso
		if recurso is None:
			self.ctx.avisar(_("No hay ningún recurso elegido."))
			return
		carpeta = carpeta or carpeta_de_descargas(self, self.ctx, preguntar)
		if not carpeta:
			return
		url = self.ctx.api().url_descarga_recurso(self.nombre, recurso["id"])
		destino = Path(carpeta) / nombre_seguro(recurso.get("name"), "recurso")
		self.descargar(url, destino, aceptar="application/octet-stream", descripcion=recurso.get("name", ""))

	def descargar_todos(self) -> None:
		if not self.recursos:
			self.ctx.avisar(_("Esta release no tiene recursos."))
			return
		carpeta = carpeta_de_descargas(self, self.ctx)
		if not carpeta:
			return
		for recurso in list(self.recursos):
			self.descargar_recurso(recurso=recurso, carpeta=carpeta)

	def subir(self, rutas: Sequence[str] | None = None) -> None:
		rutas = list(rutas) if rutas is not None else elegir_archivos(self, _("Elija los archivos que subir a la release"))
		if not rutas:
			return
		subir_recursos(self.ctx, self, self.release, rutas, al_terminar=lambda _s: self.viva() and self.cargar(anunciar=False),
			estado=self.estado)

	def renombrar_recurso(self) -> None:
		recurso = self.recurso
		if recurso is None:
			return
		nuevo = pedir_texto(self, _("&Nuevo nombre del archivo:"), _("Renombrar recurso"), recurso.get("name", ""))
		if not nuevo or not nuevo.strip() or nuevo.strip() == recurso.get("name"):
			return
		api = self.ctx.api()

		def hecho(actualizado: dict) -> None:
			if recurso in self.recursos:
				self.recursos[self.recursos.index(recurso)] = dict(recurso, **(actualizado or {"name": nuevo.strip()}))
			self._pintar()

		self.en_fondo(lambda: api.editar_recurso(self.nombre, recurso["id"], nombre_archivo=nuevo.strip()),
			exito=_("Recurso renombrado."), al_terminar=hecho)

	def borrar_recurso(self) -> None:
		recurso = self.recurso
		if recurso is None:
			return
		if not confirmar_peligro(self, _("¿Borrar el archivo {n} de la release? No se puede deshacer.").format(n=recurso.get("name", "")),
			_("Borrar recurso")):
			return
		api = self.ctx.api()

		def hecho(_r: Any) -> None:
			if recurso in self.recursos:
				self.recursos.remove(recurso)
			self._pintar()

		self.en_fondo(lambda: api.borrar_recurso(self.nombre, recurso["id"]), exito=_("Recurso borrado."), al_terminar=hecho)

	def editar(self) -> None:
		api = self.ctx.api()
		release = self.release
		era_ultima = self.es_ultima

		def enviar(valores: dict) -> dict:
			campos: dict[str, Any] = {
				"name": valores.get("titulo") or release.get("tag_name"),
				"body": valores.get("cuerpo", ""),
				"draft": bool(valores.get("borrador")),
				"prerelease": bool(valores.get("prelanzamiento")),
			}
			etiqueta = (valores.get("etiqueta") or "").strip()
			if etiqueta and etiqueta != release.get("tag_name"):
				campos["tag_name"] = etiqueta
			if bool(valores.get("ultima")) != era_ultima:
				puede = valores.get("ultima") and not campos["draft"] and not campos["prerelease"]
				campos["make_latest"] = "true" if puede else "false"
			return api.editar_release(self.nombre, release["id"], **campos)

		resultado = editar(
			self, self.ctx, _("Editar la release"), enviar, con_titulo=True,
			titulo=release.get("name") or "", cuerpo=release.get("body") or "",
			etiqueta_cuerpo=_("&Notas de la versión (Markdown):"), etiqueta_enviar=_("&Guardar"),
			extras=[
				CampoExtra("etiqueta", _("Eti&queta:"), "texto", release.get("tag_name", ""),
					ayuda=_("Cambiarla mueve la release a otra etiqueta.")),
				CampoExtra("borrador", _("&Borrador (no publicada)"), "bool", bool(release.get("draft"))),
				CampoExtra("prelanzamiento", _("&Prelanzamiento"), "bool", bool(release.get("prerelease"))),
				CampoExtra("ultima", _("Marcar como la más &reciente (la última)"), "bool", era_ultima,
					ayuda=_("Un borrador o un prelanzamiento no pueden ser la última release.")),
			],
		)
		if resultado is not None and self.viva():
			self.release = dict(resultado)
			self._pintar()
			self.cargar(anunciar=False)

	def borrar_release(self) -> None:
		etiqueta = self.release.get("tag_name") or ""
		if not confirmar_peligro(self, _("¿Borrar la release {n} y sus archivos? No se puede deshacer.").format(
			n=self.release.get("name") or etiqueta), _("Borrar release")):
			return
		borrar_etiqueta = bool(etiqueta) and confirmar(
			self, _("¿Borrar también la etiqueta git «{e}»? Si no, la etiqueta seguirá en el repositorio.").format(e=etiqueta),
			_("Borrar release"), peligroso=True) == wx.ID_YES
		api = self.ctx.api()

		def trabajo() -> None:
			api.borrar_release(self.nombre, self.release["id"])
			if borrar_etiqueta:
				api.borrar_etiqueta_git(self.nombre, etiqueta)

		self.en_fondo(trabajo, exito=_("Release borrada."), al_terminar=lambda _r: self.Close())

	def copiar_enlace(self) -> None:
		url = self.release.get("html_url") or ""
		if url:
			copiar(self.ctx, url, _("Enlace copiado."))

	def abrir_navegador(self) -> None:
		url = self.release.get("html_url") or ""
		if url:
			webbrowser.open(url)


def abrir_release(ctx: Any, padre: wx.Window | None, nombre: str, elemento: dict) -> wx.Frame:
	"""Abre (o trae al frente) la ventana de una release y la actualiza en segundo plano."""
	clave = clave_release(nombre, elemento or {})
	if VentanaDetalle.abrir_existente(clave):
		return VentanaDetalle._abiertas[clave]
	ventana = VentanaRelease(ctx, padre, nombre, elemento)
	ventana.mostrar(ventana.info)
	ventana.cargar(anunciar=False)
	return ventana


# ════════════════════════════════════════════════════════════════════════════
# Nueva release
# ════════════════════════════════════════════════════════════════════════════


class DialogoNuevaRelease(wx.Dialog):
	"""Etiqueta, destino, título, notas y opciones de una release nueva.

	El diálogo NO se cierra si GitHub rechaza la creación: lo escrito no se pierde.
	"""

	def __init__(self, padre: wx.Window | None, ctx: Any, nombre: str, etiquetas: Sequence[str] = (),
		ramas: Sequence[str] = (), rama_defecto: str = "") -> None:
		super().__init__(padre, title=_("Nueva release en {n}").format(n=nombre), size=(720, 640),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = ctx
		self.nombre = nombre
		self.etiquetas = list(etiquetas)
		self.resultado: dict | None = None
		self._creando = False
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=_("&Etiqueta (nueva o existente):")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_etiqueta = wx.ComboBox(self, choices=self.etiquetas, style=wx.CB_DROPDOWN)
		self.campo_etiqueta.SetHelpText(_("Escriba una etiqueta nueva (por ejemplo, v1.2.0) o elija una existente con las flechas."))
		raiz.Add(self.campo_etiqueta, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Destino de una etiqueta nueva (rama o commit):")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_destino = wx.ComboBox(self, value=rama_defecto, choices=list(ramas), style=wx.CB_DROPDOWN)
		self.campo_destino.SetHelpText(_("Rama o SHA de commit donde se crea la etiqueta si aún no existe."))
		raiz.Add(self.campo_destino, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Título:")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_titulo = wx.TextCtrl(self)
		self.campo_titulo.SetHelpText(_("Título de la release. Si se deja vacío se usa la etiqueta."))
		raiz.Add(self.campo_titulo, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Notas (Markdown):")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_notas = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH2)
		self.campo_notas.SetHelpText(_("Notas de la versión en Markdown. Control+Intro crea la release; F7 muestra la vista previa."))
		raiz.Add(self.campo_notas, 1, wx.EXPAND | wx.ALL, 6)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_generar = wx.Button(self, label=_("&Generar las notas automáticamente"))
		self.boton_generar.SetHelpText(_("GitHub escribe las notas a partir de los pull requests desde la etiqueta anterior."))
		self.boton_generar.Bind(wx.EVT_BUTTON, lambda _e: self.generar_notas())
		fila.Add(self.boton_generar, 0, wx.RIGHT, 6)
		self.boton_vista = wx.Button(self, label=_("&Vista previa (F7)"))
		self.boton_vista.Bind(wx.EVT_BUTTON, lambda _e: self.vista_previa())
		fila.Add(self.boton_vista, 0)
		raiz.Add(fila, 0, wx.ALL, 6)
		self.casilla_borrador = wx.CheckBox(self, label=_("&Borrador (no se publica todavía)"))
		self.casilla_prelanzamiento = wx.CheckBox(self, label=_("&Prelanzamiento"))
		self.casilla_ultima = wx.CheckBox(self, label=_("&Marcar como la última release"))
		self.casilla_ultima.SetValue(True)
		self.casilla_ultima.SetHelpText(_("Un borrador o un prelanzamiento no se marcan nunca como la última."))
		for casilla in (self.casilla_borrador, self.casilla_prelanzamiento, self.casilla_ultima):
			raiz.Add(casilla, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
		botones = crear_botonera(self, wx.OK | wx.CANCEL)
		self.boton_crear = self.FindWindow(wx.ID_OK)
		self.boton_crear.SetLabel(_("C&rear la release"))
		raiz.Add(botones, 0, wx.EXPAND | wx.ALL, 8)
		self.estado = wx.StaticText(self, label="")
		raiz.Add(self.estado, 0, wx.LEFT | wx.BOTTOM, 6)
		self.SetSizer(raiz)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.crear(), id=wx.ID_OK)
		preparar_dialogo(self, foco_inicial=self.campo_etiqueta)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.CentreOnParent()

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla = evento.GetKeyCode()
		if tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and evento.ControlDown():
			self.crear()
			return
		if tecla == wx.WXK_F7 and not evento.HasAnyModifiers():
			self.vista_previa()
			return
		evento.Skip()

	def valores(self) -> dict[str, Any]:
		etiqueta = self.campo_etiqueta.GetValue().strip()
		borrador, prelanzamiento = self.casilla_borrador.GetValue(), self.casilla_prelanzamiento.GetValue()
		return {
			"etiqueta": etiqueta,
			"titulo": self.campo_titulo.GetValue().strip() or etiqueta,
			"cuerpo": self.campo_notas.GetValue(),
			"rama": "" if etiqueta in self.etiquetas else self.campo_destino.GetValue().strip(),
			"borrador": borrador,
			"prelanzamiento": prelanzamiento,
			"ultima": "true" if self.casilla_ultima.GetValue() and not borrador and not prelanzamiento else "false",
		}

	def vista_previa(self) -> None:
		from app.ui import visor_ayuda

		texto = self.campo_notas.GetValue()
		if not texto.strip():
			self.ctx.avisar(_("No hay notas que mostrar."))
			return
		visor_ayuda.mostrar_documento(self, _("Vista previa de las notas"), texto)

	def generar_notas(self) -> None:
		valores = self.valores()
		if not valores["etiqueta"]:
			mostrar_error(self, _("Escriba primero la etiqueta: las notas se generan desde la etiqueta anterior hasta ella."),
				_("Falta la etiqueta"))
			self.campo_etiqueta.SetFocus()
			return
		api = self.ctx.api()

		def listo(datos: dict) -> None:
			if not self:
				return
			cuerpo = (datos or {}).get("body") or ""
			if self.campo_notas.GetValue().strip() and confirmar(
				self, _("¿Sustituir las notas escritas por las generadas?"), _("Generar notas"), peligroso=True) != wx.ID_YES:
				return
			self.campo_notas.SetValue(cuerpo)
			if not self.campo_titulo.GetValue().strip() and (datos or {}).get("name"):
				self.campo_titulo.SetValue(datos["name"])
			self.campo_notas.SetFocus()
			self.campo_notas.SetInsertionPoint(0)

		en_segundo_plano(self, self.ctx, lambda: api.generar_notas(self.nombre, valores["etiqueta"], rama=valores["rama"]),
			al_terminar=listo, sonido="completado", inicio=_("Generando las notas…"), exito=_("Notas generadas."))

	def crear(self) -> None:
		if self._creando:
			return
		valores = self.valores()
		if not valores["etiqueta"]:
			mostrar_error(self, _("Escriba la etiqueta de la release."), _("Falta la etiqueta"))
			self.campo_etiqueta.SetFocus()
			return
		self._creando = True
		self.boton_crear.Disable()
		self.estado.SetLabel(_("Creando la release…"))
		api = self.ctx.api()

		def listo(release: dict) -> None:
			self._creando = False
			self.resultado = dict(release or {})
			self.ctx.sonar("enviado")
			self.ctx.avisar(_("Release {e} creada.").format(e=valores["etiqueta"]), interrumpir=False)
			if self and self.IsModal():
				self.EndModal(wx.ID_OK)

		def fallo(error: BaseException) -> None:
			self._creando = False
			if not self:
				return
			self.boton_crear.Enable()
			self.estado.SetLabel("")
			self.ctx.sonar("error")
			mostrar_error(self, mensaje_error(error), _("No se pudo crear la release"))
			self.campo_etiqueta.SetFocus()

		self.ctx.tareas.enviar(
			lambda tarea: api.crear_release(self.nombre, valores["etiqueta"], valores["titulo"], valores["cuerpo"], valores["rama"],
				valores["borrador"], valores["prelanzamiento"], ultima=valores["ultima"]),
			al_terminar=listo, al_fallar=fallo, nombre="crear_release", duplicadas="permitir")


def nueva_release(padre: wx.Window | None, ctx: Any, nombre: str, al_crear: Callable[[dict], None] | None = None) -> None:
	"""Pide los datos de una release nueva, la crea y ofrece subir archivos."""
	api = ctx.api()

	def obtener() -> tuple[list[str], list[str], str]:
		try:
			pagina = api.etiquetas_git(nombre, 1)
			etiquetas = [e.get("name", "") for e in (getattr(pagina, "elementos", pagina) or []) if e.get("name")]
		except Exception:  # noqa: BLE001 - sin la lista de etiquetas se puede escribir una a mano
			log.warning("No se pudieron leer las etiquetas de %s", nombre, exc_info=True)
			etiquetas = []
		ramas = [r.get("name", "") for r in api.todas_las_ramas(nombre) or [] if r.get("name")]
		defecto = (api.repositorio(nombre) or {}).get("default_branch", "")
		return etiquetas, ramas, defecto

	def mostrar(datos: tuple[list[str], list[str], str]) -> None:
		etiquetas, ramas, defecto = datos
		dialogo = DialogoNuevaRelease(padre, ctx, nombre, etiquetas, ramas, defecto)
		try:
			dialogo.ShowModal()
			release = dialogo.resultado
		finally:
			dialogo.Destroy()
		if not release:
			return
		if confirmar(padre, _("Release creada. ¿Quiere subirle archivos ahora?"), _("Subir recursos")) == wx.ID_YES:
			rutas = elegir_archivos(padre, _("Elija los archivos que subir a la release"))
			if rutas:
				subir_recursos(ctx, padre, release, rutas)
		if al_crear is not None:
			al_crear(release)

	en_segundo_plano(padre, ctx, obtener, al_terminar=mostrar, sonido="", inicio=_("Preparando la nueva release…"))
