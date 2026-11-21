"""Diálogos de la ventana de git: conflictos bloque a bloque, filtro del historial,
configuración del repositorio, bisección guiada y elección del modo de restablecer.

Todos con etiqueta antes de cada campo, letras de acceso sin repetir,
``preparar_dialogo`` (Escape, Ctrl+H, foco inicial) y el trabajo de git en
segundo plano (``en_segundo_plano``).
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx

from app.services import conflictos as c
from app.services import git_local
from app.ui.accesibilidad.dialogos import crear_botonera, elegir_opcion, preparar_dialogo
from app.ui.comunes import confirmar, en_segundo_plano, mensaje_error, mostrar_error
from app.ui.git import operaciones as op

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _terminar(dialogo: wx.Dialog, codigo: int) -> None:
	"""Cierra el diálogo modal (o lo deja anotado si se usa sin ``ShowModal``, como en las pruebas)."""
	dialogo.codigo_salida = codigo
	if dialogo.IsModal():
		dialogo.EndModal(codigo)


# ════════════════════════════════════════════════════════════════════════════
# Conflictos bloque a bloque
# ════════════════════════════════════════════════════════════════════════════


class DialogoConflictos(wx.Dialog):
	"""Recorre y resuelve los bloques de conflicto de un archivo.

	:param ruta: ruta del archivo relativa a la raíz del repositorio.
	:param operacion: operación en curso (``operacion_en_curso()``): decide qué es «su versión».
	:param al_resolver: se llama con la ruta cuando el archivo queda marcado como resuelto.
	"""

	def __init__(self, padre: wx.Window | None, contexto: Any, repo: git_local.RepositorioLocal, raiz: Path, ruta: str,
		operacion: str = "", al_resolver: Callable[[str], None] | None = None) -> None:
		super().__init__(padre, title=_("Resolver conflictos: {r}").format(r=ruta), size=(900, 720),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = contexto
		self.repo = repo
		self.ruta = ruta
		self.archivo_disco = Path(raiz) / ruta
		self.invertido = c.es_invertido(operacion)
		self.al_resolver = al_resolver
		self.codigo_salida = wx.ID_NONE
		self.modificado = False
		self.actual = 0
		self.archivo = c.analizar(self._leer())

		raiz_sizer = wx.BoxSizer(wx.VERTICAL)
		self.info = wx.StaticText(self, label=_("Archivo {r}. {e}").format(r=ruta, e=c.explicar_lados(operacion)))
		self.info.Wrap(self.FromDIP(860))
		raiz_sizer.Add(self.info, 0, wx.ALL, 6)

		raiz_sizer.Add(wx.StaticText(self, label=_("&Bloque actual:")), 0, wx.LEFT | wx.RIGHT, 6)
		self.campo_bloque = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=(-1, self.FromDIP(220)))
		self.campo_bloque.SetHelpText(_(
			"Texto del bloque de conflicto: su versión, la otra versión y, si la hay, la versión común. "
			"Recórralo con las flechas."))
		raiz_sizer.Add(self.campo_bloque, 1, wx.EXPAND | wx.ALL, 6)

		navegacion = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_anterior = self._boton(_("Bloque &anterior"), _("Muestra y lee el bloque anterior."), lambda: self.ir(-1), navegacion)
		self.boton_siguiente = self._boton(_("Bloque &siguiente"), _("Muestra y lee el bloque siguiente."), lambda: self.ir(1), navegacion)
		raiz_sizer.Add(navegacion, 0, wx.LEFT | wx.RIGHT, 6)

		elecciones = wx.WrapSizer(wx.HORIZONTAL)
		self._boton(_("Quedarse con s&u versión"), _("Deja en el archivo solo su versión de este bloque."),
			lambda: self.elegir(c.PROPIA), elecciones)
		self._boton(_("Quedarse con la &otra"), _("Deja en el archivo solo la otra versión de este bloque."),
			lambda: self.elegir(c.OTRA), elecciones)
		self._boton(_("Ambas, su versión &primero"), _("Deja las dos versiones: primero la suya y después la otra."),
			lambda: self.elegir(c.AMBAS_PROPIA_PRIMERO), elecciones)
		self._boton(_("Ambas, la otra pri&mero"), _("Deja las dos versiones: primero la otra y después la suya."),
			lambda: self.elegir(c.AMBAS_OTRA_PRIMERO), elecciones)
		self._boton(_("Des&hacer este bloque"), _("Vuelve a dejar el bloque pendiente."), self.deshacer, elecciones)
		raiz_sizer.Add(elecciones, 0, wx.ALL, 6)

		raiz_sizer.Add(wx.StaticText(self, label=_("Te&xto para editar a mano:")), 0, wx.LEFT | wx.RIGHT, 6)
		self.campo_manual = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH2, size=(-1, self.FromDIP(120)))
		self.campo_manual.SetHelpText(_(
			"Escriba aquí cómo debe quedar el bloque, sin marcadores. Empieza con su versión y debajo la otra. "
			"Después pulse «Aplicar el texto editado»."))
		raiz_sizer.Add(self.campo_manual, 0, wx.EXPAND | wx.ALL, 6)
		self._boton(_("Aplicar el texto e&ditado"), _("Usa el texto escrito a mano para este bloque."), self.aplicar_manual, raiz_sizer)

		self.resumen = wx.StaticText(self, label="")
		raiz_sizer.Add(self.resumen, 0, wx.ALL, 6)

		final = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_guardar = self._boton(_("&Guardar y marcar como resuelto"),
			_("Escribe el archivo y, si no quedan bloques pendientes, lo marca como resuelto (git add)."), self.guardar, final)
		self.boton_cerrar = wx.Button(self, wx.ID_CANCEL, _("&Cerrar"))
		self.boton_cerrar.SetHelpText(_("Cierra sin guardar (pregunta si hay bloques elegidos)."))
		self.boton_cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.cerrar())
		final.Add(self.boton_cerrar, 0, wx.LEFT, 6)
		raiz_sizer.Add(final, 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		self.SetSizer(raiz_sizer)

		preparar_dialogo(self, foco_inicial=self.campo_bloque)
		# Escape pasa por la misma pregunta que «Cerrar» (no se pierde lo elegido).
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.Bind(wx.EVT_CLOSE, lambda evento: self.cerrar() if evento.CanVeto() else evento.Skip())
		self.mostrar(0, anunciar=False)
		self.CentreOnParent()

	def _boton(self, etiqueta: str, ayuda: str, accion: Callable[[], None], sizer: wx.Sizer) -> wx.Button:
		boton = wx.Button(self, label=etiqueta)
		boton.SetHelpText(ayuda)
		boton.Bind(wx.EVT_BUTTON, lambda _e: accion())
		sizer.Add(boton, 0, wx.ALL, 3)
		return boton

	# ── Archivo ───────────────────────────────────────────────────────────────

	def _leer(self) -> str:
		datos = self.archivo_disco.read_bytes()
		return datos.decode("utf-8", errors="surrogateescape")

	def _escribir(self) -> None:
		self.archivo_disco.write_bytes(self.archivo.componer().encode("utf-8", errors="surrogateescape"))

	# ── Navegación y elección ─────────────────────────────────────────────────

	def mostrar(self, indice: int, anunciar: bool = True) -> None:
		bloques = self.archivo.bloques
		self.resumen.SetLabel(c.resumen(self.archivo))
		if not bloques:
			texto = _("Este archivo no tiene marcadores de conflicto. Puede usar su versión o la otra entera desde la lista, "
				"o marcarlo como resuelto.")
			self.campo_bloque.SetValue(texto)
			self.campo_manual.SetValue("")
			if anunciar:
				self.ctx.anunciar(texto)
			return
		self.actual = max(0, min(indice, len(bloques) - 1))
		bloque = bloques[self.actual]
		texto = c.describir_bloque(self.archivo, self.actual, self.invertido)
		self.campo_bloque.SetValue(texto)
		self.campo_bloque.SetInsertionPoint(0)
		if bloque.eleccion == c.MANUAL and bloque.resolucion is not None:
			self.campo_manual.SetValue(c.texto_lineas(bloque.resolucion) if bloque.resolucion else "")
		else:
			self.campo_manual.SetValue(c.texto_inicial_manual(bloque, self.invertido))
		if anunciar:
			self.ctx.anunciar(texto)

	def ir(self, paso: int) -> None:
		bloques = self.archivo.bloques
		destino = self.actual + paso
		if not bloques or not (0 <= destino < len(bloques)):
			self.ctx.sonar("vacio")
			self.ctx.anunciar(_("No hay más bloques."))
			return
		self.mostrar(destino)

	def elegir(self, eleccion: str) -> None:
		if not self.archivo.bloques:
			self.ctx.anunciar(_("No hay bloques que resolver."))
			return
		c.resolver(self.archivo, self.actual, eleccion, self.invertido)
		self._tras_resolver(eleccion)

	def aplicar_manual(self) -> None:
		if not self.archivo.bloques:
			return
		c.resolver(self.archivo, self.actual, c.MANUAL, self.invertido, texto=self.campo_manual.GetValue())
		self._tras_resolver(c.MANUAL)

	def deshacer(self) -> None:
		if self.archivo.bloques:
			c.deshacer(self.archivo, self.actual)
			self.modificado = True
			self.mostrar(self.actual, anunciar=False)
			self.ctx.anunciar(_("Bloque {n} pendiente otra vez.").format(n=self.actual + 1))

	def _tras_resolver(self, eleccion: str) -> None:
		self.modificado = True
		numero = self.actual + 1
		siguiente = c.siguiente_pendiente(self.archivo, self.actual)
		aviso = _("Bloque {n}: {e}.").format(n=numero, e=c.nombre_eleccion(eleccion))
		if siguiente is None:
			self.mostrar(self.actual, anunciar=False)
			self.ctx.sonar("completado")
			self.ctx.anunciar(aviso + " " + _("Todos los bloques resueltos. Pulse «Guardar y marcar como resuelto»."))
			self.boton_guardar.SetFocus()
			return
		self.ctx.anunciar(aviso, interrumpir=True)
		self.mostrar(siguiente)

	# ── Guardar y cerrar ──────────────────────────────────────────────────────

	def guardar(self) -> None:
		pendientes = len(self.archivo.pendientes)
		if pendientes and confirmar(self, _(
			"Quedan {n} bloques sin resolver. ¿Guardar el archivo con sus marcadores, sin marcarlo como resuelto?"
		).format(n=pendientes), _("Bloques pendientes")) != wx.ID_YES:
			return
		try:
			self._escribir()
		except OSError as error:
			log.exception("No se pudo escribir %s", self.archivo_disco)
			mostrar_error(self, _("No se pudo guardar el archivo: {e}").format(e=error), _("Error"))
			return
		self.modificado = False
		if pendientes:
			self.ctx.avisar(_("Archivo guardado con {n} bloques pendientes.").format(n=pendientes))
			_terminar(self, wx.ID_OK)
			return

		def hecho(_resultado: Any) -> None:
			if self.al_resolver:
				self.al_resolver(self.ruta)
			if self:
				_terminar(self, wx.ID_OK)

		en_segundo_plano(self, self.ctx, lambda: self.repo.marcar_resuelto(self.ruta), al_terminar=hecho,
			exito=_("{r} resuelto y marcado como resuelto.").format(r=self.ruta), titulo_error=_("No se pudo marcar como resuelto"))

	def cerrar(self) -> None:
		if self.modificado and confirmar(self, _("¿Cerrar sin guardar los bloques elegidos?"), _("Cerrar"), peligroso=True) != wx.ID_YES:
			return
		self.modificado = False
		_terminar(self, wx.ID_CANCEL)
		if not self.IsModal():
			self.Destroy()

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_ESCAPE and not evento.HasAnyModifiers():
			self.cerrar()
			return
		evento.Skip()


def resolver_archivo(padre: wx.Window | None, contexto: Any, repo: git_local.RepositorioLocal, raiz: Path, ruta: str,
	operacion: str, al_resolver: Callable[[str], None] | None = None) -> None:
	"""Abre el diálogo de conflictos de forma modal."""
	try:
		dialogo = DialogoConflictos(padre, contexto, repo, raiz, ruta, operacion, al_resolver)
	except OSError as error:
		mostrar_error(padre, _("No se pudo leer el archivo: {e}").format(e=error), _("Error"))
		return
	try:
		dialogo.ShowModal()
	finally:
		if dialogo:
			dialogo.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Filtro del historial
# ════════════════════════════════════════════════════════════════════════════


class DialogoFiltroHistorial(wx.Dialog):
	def __init__(self, padre: wx.Window | None, filtro: dict | None = None) -> None:
		super().__init__(padre, title=_("Filtrar el historial"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		filtro = filtro or {}
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=_("&Texto del mensaje:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
		self.campo_texto = wx.TextCtrl(self, value=filtro.get("buscar", ""), size=(self.FromDIP(380), -1))
		self.campo_texto.SetHelpText(_("Solo los commits cuyo mensaje contiene este texto (sin distinguir mayúsculas)."))
		raiz.Add(self.campo_texto, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("A&utor:")), 0, wx.LEFT | wx.RIGHT, 6)
		self.campo_autor = wx.TextCtrl(self, value=filtro.get("autor", ""))
		self.campo_autor.SetHelpText(_("Nombre o correo (o parte) de quien hizo el commit."))
		raiz.Add(self.campo_autor, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Ruta de un archivo o carpeta:")), 0, wx.LEFT | wx.RIGHT, 6)
		self.campo_ruta = wx.TextCtrl(self, value=filtro.get("ruta", ""))
		self.campo_ruta.SetHelpText(_("Solo los commits que cambian esta ruta, siguiendo los renombrados."))
		raiz.Add(self.campo_ruta, 0, wx.EXPAND | wx.ALL, 6)
		self.casilla_todas = wx.CheckBox(self, label=_("Todas las ra&mas"))
		self.casilla_todas.SetValue(bool(filtro.get("todas")))
		self.casilla_todas.SetHelpText(_("Muestra los commits de todas las ramas, no solo de la actual."))
		raiz.Add(self.casilla_todas, 0, wx.ALL, 6)
		raiz.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		self.SetSizerAndFit(raiz)
		preparar_dialogo(self, foco_inicial=self.campo_texto)
		self.CentreOnParent()

	def valores(self) -> dict:
		return {
			"buscar": self.campo_texto.GetValue().strip(), "autor": self.campo_autor.GetValue().strip(),
			"ruta": self.campo_ruta.GetValue().strip(), "todas": self.casilla_todas.GetValue(),
		}


def pedir_filtro_historial(padre: wx.Window | None, filtro: dict | None) -> dict | None:
	dialogo = DialogoFiltroHistorial(padre, filtro)
	try:
		return dialogo.valores() if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


def describir_filtro(filtro: dict | None) -> str:
	filtro = filtro or {}
	partes = []
	if filtro.get("buscar"):
		partes.append(_("mensaje con «{t}»").format(t=filtro["buscar"]))
	if filtro.get("autor"):
		partes.append(_("autor «{a}»").format(a=filtro["autor"]))
	if filtro.get("ruta"):
		partes.append(_("ruta «{r}»").format(r=filtro["ruta"]))
	if filtro.get("todas"):
		partes.append(_("todas las ramas"))
	return _("Filtro: {f}. Mayúsculas+F4 lo quita.").format(f=", ".join(partes)) if partes else _("Sin filtro. F4 filtra por texto, autor o ruta.")


# ════════════════════════════════════════════════════════════════════════════
# Restablecer (reset)
# ════════════════════════════════════════════════════════════════════════════


def elegir_modo_restablecer(padre: wx.Window | None, descripcion: str) -> str | None:
	"""Pregunta soft/mixed/hard explicando cada uno; el modo duro pide confirmación aparte."""
	opciones = [
		_("&Suave: conservar todo preparado"),
		_("&Mixto: conservar los cambios sin preparar"),
		_("&Duro: descartar todos los cambios"),
	]
	mensaje = _(
		"Restablecer la rama actual a {d}.\n\n"
		"Suave (soft): los commits posteriores se deshacen pero sus cambios quedan preparados.\n"
		"Mixto (mixed): sus cambios quedan en los archivos, sin preparar.\n"
		"Duro (hard): se pierden los commits posteriores y todos los cambios sin confirmar. "
		"Solo se pueden recuperar con el reflog."
	).format(d=descripcion)
	indice = elegir_opcion(padre, mensaje, _("Restablecer"), opciones)
	if indice is None:
		return None
	modo = ("soft", "mixed", "hard")[indice]
	if modo == "hard":
		from app.ui.comunes import confirmar_peligro

		if not confirmar_peligro(padre, _(
			"Se descartarán TODOS los cambios sin confirmar y los commits posteriores a {d}. ¿Continuar?"
		).format(d=descripcion), _("Restablecer en modo duro")):
			return None
	return modo


# ════════════════════════════════════════════════════════════════════════════
# Configuración del repositorio
# ════════════════════════════════════════════════════════════════════════════

_OPCIONES_FIRMA = (("", "(como en la configuración global)"), ("true", "Sí, firmar siempre"), ("false", "No firmar"))


class DialogoConfigRepo(wx.Dialog):
	"""user.name, user.email y firma SOLO de este repositorio (``git config --local``)."""

	CLAVES = ("user.name", "user.email", "commit.gpgsign", "user.signingkey")

	def __init__(self, padre: wx.Window | None, contexto: Any, repo: git_local.RepositorioLocal) -> None:
		super().__init__(padre, title=_("Configuración del repositorio"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = contexto
		self.repo = repo
		self.iniciales: dict[str, str] = {}
		self.codigo_salida = wx.ID_NONE
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.aviso = wx.StaticText(self, label=_(
			"Valores solo para este repositorio. Un campo vacío usa la configuración global de git."))
		raiz.Add(self.aviso, 0, wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Nombre (user.name):")), 0, wx.LEFT | wx.RIGHT, 6)
		self.campo_nombre = wx.TextCtrl(self, size=(self.FromDIP(380), -1))
		self.campo_nombre.SetHelpText(_("Nombre del autor de los commits en este repositorio."))
		raiz.Add(self.campo_nombre, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("C&orreo (user.email):")), 0, wx.LEFT | wx.RIGHT, 6)
		self.campo_correo = wx.TextCtrl(self)
		self.campo_correo.SetHelpText(_("Correo del autor; para ocultarlo use el correo noreply de GitHub."))
		raiz.Add(self.campo_correo, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Firmar los commits (commit.gpgsign):")), 0, wx.LEFT | wx.RIGHT, 6)
		self.selector_firma = wx.Choice(self, choices=[_(t) for _v, t in _OPCIONES_FIRMA])
		self.selector_firma.SetSelection(0)
		self.selector_firma.SetHelpText(_("Si los commits de este repositorio se firman siempre."))
		raiz.Add(self.selector_firma, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("Clave de fir&ma (user.signingkey):")), 0, wx.LEFT | wx.RIGHT, 6)
		self.campo_clave = wx.TextCtrl(self)
		self.campo_clave.SetHelpText(_("Identificador de la clave GPG o ruta de la clave SSH pública con la que firmar."))
		raiz.Add(self.campo_clave, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		self.SetSizerAndFit(raiz)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.guardar(), id=wx.ID_OK)
		preparar_dialogo(self, foco_inicial=self.campo_nombre)
		self.CentreOnParent()
		self.cargar()

	def cargar(self) -> None:
		def trabajo() -> dict[str, str]:
			return {clave: op.config_local(self.repo, clave) for clave in self.CLAVES}

		def listo(valores: dict[str, str]) -> None:
			if not self:
				return
			self.iniciales = valores
			self.campo_nombre.SetValue(valores.get("user.name", ""))
			self.campo_correo.SetValue(valores.get("user.email", ""))
			firma = valores.get("commit.gpgsign", "").lower()
			self.selector_firma.SetSelection({"true": 1, "false": 2}.get(firma, 0))
			self.campo_clave.SetValue(valores.get("user.signingkey", ""))

		en_segundo_plano(self, self.ctx, trabajo, al_terminar=listo, sonido="")

	def valores(self) -> dict[str, str]:
		return {
			"user.name": self.campo_nombre.GetValue().strip(), "user.email": self.campo_correo.GetValue().strip(),
			"commit.gpgsign": _OPCIONES_FIRMA[max(0, self.selector_firma.GetSelection())][0],
			"user.signingkey": self.campo_clave.GetValue().strip(),
		}

	def guardar(self) -> None:
		cambios = {k: v for k, v in self.valores().items() if v != self.iniciales.get(k, "")}

		def trabajo() -> None:
			for clave, valor in cambios.items():
				op.establecer_config_local(self.repo, clave, valor)

		def listo(_r: Any) -> None:
			if self:
				_terminar(self, wx.ID_OK)

		if not cambios:
			_terminar(self, wx.ID_OK)
			return
		en_segundo_plano(self, self.ctx, trabajo, al_terminar=listo, exito=_("Configuración del repositorio guardada."),
			titulo_error=_("No se pudo guardar la configuración"))


# ════════════════════════════════════════════════════════════════════════════
# Bisección guiada
# ════════════════════════════════════════════════════════════════════════════

EXPLICACION_BISECCION = _(
	"La bisección busca el commit que introdujo un fallo probando commits a medio camino.\n\n"
	"1. Indique un commit malo (donde ya falla; normalmente el actual) y uno bueno (donde aún funcionaba).\n"
	"2. Git cambia los archivos a un commit intermedio. Pruebe el programa y diga si ese commit está bien o mal "
	"(o sáltelo si no se puede probar).\n"
	"3. Repita hasta que git anuncie el primer commit malo.\n"
	"4. Termine la bisección para volver a su rama.\n\n"
	"Mientras dure, no haga commits."
)


class DialogoBiseccion(wx.Dialog):
	"""Pasos «bien», «mal», «saltar» y «terminar» con la salida de git en un campo legible."""

	def __init__(self, padre: wx.Window | None, contexto: Any, repo: git_local.RepositorioLocal, texto_inicial: str = "",
		al_cambiar: Callable[[], None] | None = None) -> None:
		super().__init__(padre, title=_("Bisección guiada"), size=(760, 520), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = contexto
		self.repo = repo
		self.al_cambiar = al_cambiar
		self.codigo_salida = wx.ID_NONE
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=_("&Estado de la bisección:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
		self.campo = wx.TextCtrl(self, value=texto_inicial or EXPLICACION_BISECCION,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
		self.campo.SetHelpText(_("Lo que dice git del paso actual: qué commit hay que probar o cuál es el primer commit malo."))
		raiz.Add(self.campo, 1, wx.EXPAND | wx.ALL, 6)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		for etiqueta, orden, ayuda in (
			(_("Este commit está &bien"), "good", _("El fallo no aparece en el commit actual (git bisect good).")),
			(_("Este commit está &mal"), "bad", _("El fallo aparece en el commit actual (git bisect bad).")),
			(_("&Saltar este commit"), "skip", _("No se puede probar este commit (git bisect skip).")),
			(_("&Terminar la bisección"), "reset", _("Vuelve a la rama en la que estaba (git bisect reset).")),
		):
			boton = wx.Button(self, label=etiqueta)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, lambda _e, o=orden: self.paso(o))
			botones.Add(boton, 0, wx.ALL, 3)
		cerrar = wx.Button(self, wx.ID_CANCEL, _("&Cerrar"))
		cerrar.SetHelpText(_("Cierra este cuadro; la bisección sigue en curso hasta que la termine."))
		botones.Add(cerrar, 0, wx.ALL, 3)
		raiz.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		self.SetSizer(raiz)
		preparar_dialogo(self, foco_inicial=self.campo)
		self.CentreOnParent()

	def paso(self, orden: str) -> None:
		def listo(salida: str) -> None:
			if not self:
				return
			texto = (salida or "").strip() or _("Hecho.")
			if orden == "reset":
				texto = _("Bisección terminada. Ha vuelto a su rama.") + "\n\n" + texto
			elif "is the first bad commit" in texto or "es el primer commit malo" in texto:
				texto = _("Encontrado el primer commit malo. Termine la bisección para volver a su rama.") + "\n\n" + texto
				self.ctx.sonar("completado")
			self.campo.SetValue(texto)
			self.campo.SetInsertionPoint(0)
			self.ctx.anunciar(texto.splitlines()[0])
			if self.al_cambiar:
				self.al_cambiar()

		en_segundo_plano(self, self.ctx, lambda: self.repo.bisecar(orden), al_terminar=listo, sonido="",
			titulo_error=_("Error en la bisección"))


def mensaje_de(error: BaseException) -> str:
	return mensaje_error(error)
