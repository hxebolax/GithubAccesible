"""Visor de un archivo del repositorio: leer, buscar, ir a una línea, blame, historial y editar.

Teclas (también en el menú «Acciones», Alt+A):

- Ctrl+G: ir a una línea (anuncia «línea N de M»).
- Ctrl+F: buscar; F3 y Mayús+F3: siguiente y anterior coincidencia.
- Ctrl+L: decir la línea actual y el total.
- Ctrl+E: editar y guardar con un commit; Ctrl+S: descargar.
- Ctrl+Mayús+C: copiar el enlace permanente (al commit exacto).
- Ctrl+Mayús+B: abrir en el navegador. F5: volver a cargar. Ctrl+W: cerrar.

Si el archivo es binario o muy grande no se muestra como texto: se ofrece
descargarlo. Los archivos Markdown se pueden ver formateados.
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from pathlib import Path
from typing import Any

import wx

from app.services import formato as f
from app.ui import abrir
from app.ui.accesibilidad.dialogos import confirmar, crear_botonera, preparar_dialogo
from app.ui.comunes import copiar, en_segundo_plano, mostrar_error, pedir_texto
from app.ui.detalle.conversacion import (
	DialogoLista,
	VentanaDetalle,
	como_dict,
	como_lista,
	crear_boton,
	crear_menu_acciones,
	enfocar,
)

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: A partir de este tamaño no se muestra el archivo como texto (se ofrece descargarlo).
LIMITE_TEXTO = 2 * 1024 * 1024

EXTENSIONES_MARKDOWN = (".md", ".markdown", ".mdown", ".mkd")


def clave_archivo(nombre: str, ruta: str, ref: str = "") -> str:
	return f"archivo:{nombre.lower()}:{ref}:{ruta.strip('/')}"


# ════════════════════════════════════════════════════════════════════════════
# Funciones puras
# ════════════════════════════════════════════════════════════════════════════


def es_binario(datos: bytes) -> bool:
	"""Un byte nulo al principio, o que no sea texto UTF-8 ni Latin-1 razonable, delata un binario."""
	muestra = datos[:8000]
	if b"\0" in muestra:
		return True
	try:
		muestra.decode("utf-8")
		return False
	except UnicodeDecodeError as error:
		# Un carácter multibyte cortado al final de la muestra no es un binario.
		return error.start < len(muestra) - 4


def decodificar(datos: bytes) -> str:
	for codificacion in ("utf-8-sig", "utf-8"):
		try:
			return datos.decode(codificacion)
		except UnicodeDecodeError:
			continue
	return datos.decode("latin-1")


def con_numeros(texto: str) -> str:
	"""Cada línea precedida de su número («  12: texto»)."""
	lineas = texto.split("\n")
	ancho = len(str(len(lineas)))
	return "\n".join(f"{i:>{ancho}}: {linea}" for i, linea in enumerate(lineas, start=1))


def linea_de(texto: str, posicion: int) -> int:
	"""Número de línea (desde 1) de una posición del texto."""
	return texto.count("\n", 0, max(0, posicion)) + 1


def buscar_en(texto: str, buscado: str, desde: int, atras: bool = False) -> tuple[int, bool]:
	"""Posición de la siguiente (o anterior) coincidencia sin distinguir mayúsculas, y si dio la vuelta."""
	pajar, aguja = texto.casefold(), buscado.casefold()
	if not aguja:
		return -1, False
	if atras:
		posicion = pajar.rfind(aguja, 0, max(0, desde))
		if posicion < 0:
			posicion = pajar.rfind(aguja)
			return posicion, posicion >= 0
		return posicion, False
	posicion = pajar.find(aguja, desde)
	if posicion < 0:
		posicion = pajar.find(aguja)
		return posicion, posicion >= 0
	return posicion, False


# ════════════════════════════════════════════════════════════════════════════
# Edición
# ════════════════════════════════════════════════════════════════════════════


class DialogoEditarArchivo(wx.Dialog):
	"""Editor de texto plano con el mensaje del commit, la rama y la opción de rama nueva y PR.

	Tabulador escribe una tabulación en el contenido (Control+Tabulador sale del
	campo). Si guardar falla, el diálogo NO se cierra: el texto no se pierde.
	"""

	def __init__(self, padre: wx.Window | None, contexto: Any, nombre: str, ruta: str, texto: str, sha: str, rama: str,
		saltos: str = "\n", al_guardar=None) -> None:
		super().__init__(padre, title=_("Editar {r}").format(r=ruta), size=(980, 720), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = contexto
		self.nombre, self.ruta, self.sha, self.rama_original = nombre, ruta, sha, rama
		self.saltos = saltos
		self.al_guardar = al_guardar
		self.resultado: dict | None = None
		self._enviando = False
		self._inicial = texto
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=_("C&ontenido del archivo:")), 0, wx.LEFT | wx.TOP, 6)
		self.contenido = wx.TextCtrl(self, value=texto, style=wx.TE_MULTILINE | wx.TE_RICH2 | wx.TE_PROCESS_TAB | wx.TE_DONTWRAP)
		self.contenido.SetHelpText(_("Contenido del archivo en texto plano. Tabulador escribe una tabulación; "
			"Control+Tabulador pasa al campo siguiente. Control+Intro guarda."))
		raiz.Add(self.contenido, 1, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Mensaje del commit:")), 0, wx.LEFT | wx.TOP, 6)
		self.mensaje = wx.TextCtrl(self, value=_("Actualizar {r}").format(r=Path(ruta).name))
		self.mensaje.SetHelpText(_("Frase breve que describe el cambio."))
		raiz.Add(self.mensaje, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("&Rama:")), 0, wx.LEFT | wx.TOP, 6)
		self.rama = wx.TextCtrl(self, value=rama)
		self.rama.SetHelpText(_("Rama en la que se guarda el commit (o desde la que se crea la rama nueva)."))
		raiz.Add(self.rama, 0, wx.EXPAND | wx.ALL, 6)
		self.crear_rama = wx.CheckBox(self, label=_("Crear una rama &nueva desde esa rama"))
		self.crear_rama.SetHelpText(_("El commit se hace en una rama nueva; útil para proponer el cambio con un pull request."))
		raiz.Add(self.crear_rama, 0, wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("Nom&bre de la rama nueva:")), 0, wx.LEFT | wx.TOP, 6)
		self.rama_nueva = wx.TextCtrl(self, value=f"editar-{Path(ruta).stem}".lower().replace(" ", "-"))
		self.rama_nueva.SetHelpText(_("Nombre de la rama que se crea si la casilla anterior está marcada."))
		raiz.Add(self.rama_nueva, 0, wx.EXPAND | wx.ALL, 6)
		self.abrir_pr = wx.CheckBox(self, label=_("Abrir un &pull request al terminar"))
		self.abrir_pr.SetHelpText(_("Con rama nueva: crea un pull request hacia la rama original y lo abre."))
		raiz.Add(self.abrir_pr, 0, wx.ALL, 6)
		self.estado = wx.StaticText(self, label="")
		raiz.Add(self.estado, 0, wx.LEFT | wx.RIGHT, 6)
		raiz.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		self.boton_guardar = self.FindWindow(wx.ID_OK)
		self.boton_guardar.SetLabel(_("&Guardar (commit)"))
		self.SetSizer(raiz)
		self.crear_rama.Bind(wx.EVT_CHECKBOX, lambda _e: self._sincronizar())
		self._sincronizar()
		self.Bind(wx.EVT_BUTTON, self._al_guardar, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self._al_cancelar, id=wx.ID_CANCEL)
		preparar_dialogo(self, foco_inicial=self.contenido)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.CentreOnParent()

	def _sincronizar(self) -> None:
		nueva = self.crear_rama.GetValue()
		self.rama_nueva.Enable(nueva)
		self.abrir_pr.Enable(nueva)

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla = evento.GetKeyCode()
		if tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and evento.ControlDown():
			self._al_guardar(None)
			return
		if tecla == wx.WXK_ESCAPE and not evento.HasAnyModifiers():
			self._al_cancelar(None)
			return
		evento.Skip()

	def modificado(self) -> bool:
		return self.contenido.GetValue() != self._inicial

	def _al_cancelar(self, _evento: Any) -> None:
		if self._enviando:
			self.ctx.avisar(_("Espere a que termine el guardado."))
			return
		if self.modificado() and confirmar(self, _("¿Descartar los cambios del archivo?"), _("Descartar cambios"), peligroso=True) != wx.ID_YES:
			return
		if self.IsModal():
			self.EndModal(wx.ID_CANCEL)

	def _al_guardar(self, _evento: Any) -> None:
		if self._enviando:
			return
		mensaje = self.mensaje.GetValue().strip()
		rama = self.rama.GetValue().strip()
		nueva = self.rama_nueva.GetValue().strip() if self.crear_rama.GetValue() else ""
		if not mensaje:
			mostrar_error(self, _("Escriba el mensaje del commit."), _("Falta el mensaje"))
			self.mensaje.SetFocus()
			return
		if self.crear_rama.GetValue() and not nueva:
			mostrar_error(self, _("Escriba el nombre de la rama nueva."), _("Falta la rama"))
			self.rama_nueva.SetFocus()
			return
		contenido = self.contenido.GetValue().replace("\r\n", "\n")
		if self.saltos != "\n":
			contenido = contenido.replace("\n", self.saltos)
		datos = contenido.encode("utf-8")
		crear_pr = nueva and self.abrir_pr.GetValue()
		api = self.ctx.api()
		nombre, ruta, sha = self.nombre, self.ruta, self.sha

		def trabajo() -> dict:
			destino = rama
			if nueva:
				base = como_dict(como_dict(api.rama(nombre, rama)).get("commit")).get("sha", "")
				api.crear_rama(nombre, nueva, base)
				destino = nueva
			guardado = como_dict(api.guardar_archivo(nombre, ruta, datos, mensaje, sha=sha, rama=destino))
			resultado = {"rama": destino, "sha": como_dict(guardado.get("content")).get("sha", ""), "texto": contenido, "pr": None}
			if crear_pr:
				resultado["pr"] = como_dict(api.crear_pr(nombre, mensaje, nueva, rama, _("Cambio en {r} hecho desde GitHub Accesible.").format(r=ruta)))
			return resultado

		def hecho(resultado: dict) -> None:
			self._enviando = False
			self.resultado = resultado
			self.ctx.sonar("enviado")
			self.ctx.avisar(_("Guardado en la rama {r}.").format(r=resultado["rama"]), interrumpir=False)
			if self.IsModal():
				self.EndModal(wx.ID_OK)
			if self.al_guardar:
				self.al_guardar(resultado)

		def fallo(error: BaseException) -> None:
			self._enviando = False
			if not self:
				return
			self.boton_guardar.Enable()
			self.estado.SetLabel("")
			from app.ui.comunes import mensaje_error

			mostrar_error(self, mensaje_error(error), _("No se pudo guardar"))
			self.contenido.SetFocus()

		self._enviando = True
		self.boton_guardar.Disable()
		self.estado.SetLabel(_("Guardando…"))
		en_segundo_plano(self, self.ctx, trabajo, inicio=_("Guardando…"), sonido="", al_terminar=hecho, al_fallar=fallo)


# ════════════════════════════════════════════════════════════════════════════
# Ventana
# ════════════════════════════════════════════════════════════════════════════


class VentanaArchivo(VentanaDetalle):
	numeros_por_defecto = False

	def __init__(self, padre: wx.Window | None, contexto: Any, nombre: str, ruta: str, ref: str = "") -> None:
		ruta = ruta.strip("/")
		titulo = _("{r} de {n}").format(r=ruta, n=nombre) + (f" ({ref})" if ref else "")
		super().__init__(padre, contexto, clave_archivo(nombre, ruta, ref), titulo, (1000, 740))
		self.nombre, self.ruta, self.ref = nombre, ruta, ref
		self.datos = b""
		self.sha = ""
		self.texto = ""
		self.saltos = "\n"
		self.mostrable = False
		self.busqueda = ""
		crear_menu_acciones(self, _("&Acciones"), [
			("ir", _("&Ir a la línea…\tCtrl+G"), self.ir_a_linea),
			("linea", _("&Decir la línea actual\tCtrl+L"), self.decir_linea),
			("buscar", _("&Buscar…\tCtrl+F"), self.buscar),
			("siguiente", _("Buscar &siguiente\tF3"), lambda: self.buscar_siguiente(False)),
			("anterior", _("Buscar a&nterior\tShift+F3"), lambda: self.buscar_siguiente(True)),
			None,
			("blame", _("Bla&me (autoría por líneas)"), self.blame),
			("historial", _("&Historial del archivo"), self.historial),
			("editar", _("&Editar…\tCtrl+E"), self.editar),
			("descargar", _("Desc&argar…\tCtrl+S"), self.descargar),
			("permanente", _("Copiar el enlace &permanente\tCtrl+Shift+C"), self.copiar_permanente),
			("navegador", _("Abrir en el nave&gador\tCtrl+Shift+B"), self.abrir_navegador),
			("formateado", _("&Ver formateado"), self.ver_formateado),
			None,
			("actualizar", _("Act&ualizar\tF5"), self.cargar),
			("cerrar", _("Cerrar la ven&tana\tCtrl+W"), self.Close),
		])
		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(panel, label=_("C&ontenido:")), 0, wx.LEFT | wx.TOP, 4)
		self.contenido = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_DONTWRAP)
		raiz.Add(self.contenido, 1, wx.EXPAND | wx.ALL, 4)
		self.numeros = wx.CheckBox(panel, label=_("Mostrar los &números de línea"))
		self.numeros.SetValue(VentanaArchivo.numeros_por_defecto)
		self.numeros.SetHelpText(_("Pone el número delante de cada línea del contenido."))
		self.numeros.Bind(wx.EVT_CHECKBOX, lambda _e: self._al_cambiar_numeros())
		raiz.Add(self.numeros, 0, wx.ALL, 4)
		self.estado = wx.StaticText(panel, label="")
		raiz.Add(self.estado, 0, wx.LEFT | wx.RIGHT, 4)
		botones = wx.WrapSizer(wx.HORIZONTAL)
		crear_boton(panel, _("&Blame"), self.blame, _("Quién cambió por última vez cada grupo de líneas."), botones)
		crear_boton(panel, _("&Historial"), self.historial, _("Commits que cambiaron este archivo."), botones)
		crear_boton(panel, _("&Editar…"), self.editar, _("Edita el archivo y lo guarda con un commit."), botones)
		crear_boton(panel, _("&Descargar…"), self.descargar, _("Guarda el archivo en una carpeta de este equipo."), botones)
		crear_boton(panel, _("Copiar enlace &permanente"), self.copiar_permanente, _("Enlace al archivo en el commit exacto."), botones)
		crear_boton(panel, _("Abrir en el na&vegador"), self.abrir_navegador, _("Abre el archivo en la web de GitHub."), botones)
		self.boton_formateado = crear_boton(panel, _("Ver &formateado"), self.ver_formateado,
			_("Muestra el Markdown formateado, con encabezados navegables."), botones)
		self.boton_formateado.Show(self.es_markdown)
		crear_boton(panel, _("&Cerrar"), self.Close, _("Cierra esta ventana (también Control+W)."), botones)
		raiz.Add(botones, 0, wx.EXPAND | wx.ALL, 4)
		panel.SetSizer(raiz)
		self.contenido.SetHelpText(_(
			"Contenido del archivo (solo lectura). Control+G va a una línea; Control+F busca; F3 repite la búsqueda; "
			"Control+L dice la línea actual."
		))

	@property
	def es_markdown(self) -> bool:
		return self.ruta.lower().endswith(EXTENSIONES_MARKDOWN)

	@property
	def ref_efectiva(self) -> str:
		return self.ref or "HEAD"

	def enfocar_inicio(self) -> None:
		self.contenido.SetFocus()

	# ── Carga ─────────────────────────────────────────────────────────────────

	def cargar(self) -> None:
		api = self.ctx.api()
		self.estado.SetLabel(_("Cargando…"))

		def fallo(error: BaseException) -> None:
			if not self:
				return
			from app.ui.comunes import mensaje_error

			self.estado.SetLabel(_("No se pudo cargar: {m}").format(m=mensaje_error(error)))
			self.contenido.ChangeValue(self.estado.GetLabel())
			self.ctx.avisar(self.estado.GetLabel())

		en_segundo_plano(self, self.ctx, lambda: api.leer_archivo(self.nombre, self.ruta, self.ref), sonido="",
			al_terminar=self._recibir, al_fallar=fallo)

	def _recibir(self, resultado: tuple[bytes, str]) -> None:
		if not self:
			return
		datos, sha = resultado
		self.datos = datos if isinstance(datos, bytes) else str(datos or "").encode("utf-8")
		self.sha = sha or ""
		tamano = f.tamano(len(self.datos))
		if es_binario(self.datos) or len(self.datos) > LIMITE_TEXTO:
			self.mostrable = False
			self.texto = ""
			motivo = _("es binario") if es_binario(self.datos) else _("es demasiado grande para mostrarlo")
			aviso = _("El archivo {r} ({t}) {m}. Use «Descargar» (Control+S) para guardarlo en el equipo.").format(
				r=self.ruta, t=tamano, m=motivo)
			self.contenido.ChangeValue(aviso)
			self.estado.SetLabel(aviso)
			self.ctx.avisar(aviso)
			return
		self.mostrable = True
		self.saltos = "\r\n" if b"\r\n" in self.datos else "\n"
		self.texto = decodificar(self.datos).replace("\r\n", "\n")
		self._pintar()
		self.estado.SetLabel(_("{n} líneas, {t}.").format(n=self.total_lineas, t=tamano))
		self.ctx.sonar("listo")

	@property
	def total_lineas(self) -> int:
		return self.texto.count("\n") + 1 if self.texto else 0

	def _pintar(self) -> None:
		linea = self.linea_actual() if self.contenido.GetValue() else 1
		visible = con_numeros(self.texto) if self.numeros.GetValue() else self.texto
		self.contenido.ChangeValue(visible)
		self._ir(linea, anunciar=False)

	def _al_cambiar_numeros(self) -> None:
		# Se recuerda durante la sesión para los siguientes archivos que se abran.
		VentanaArchivo.numeros_por_defecto = self.numeros.GetValue()
		if self.mostrable:
			self._pintar()

	# ── Navegación ────────────────────────────────────────────────────────────

	def linea_actual(self) -> int:
		return linea_de(self.contenido.GetValue(), self.contenido.GetInsertionPoint())

	def _posicion_de_linea(self, linea: int) -> int:
		valor = self.contenido.GetValue()
		posicion = 0
		for _i in range(linea - 1):
			siguiente = valor.find("\n", posicion)
			if siguiente < 0:
				break
			posicion = siguiente + 1
		return posicion

	def _ir(self, linea: int, anunciar: bool = True) -> None:
		total = self.total_lineas
		if not total:
			return
		linea = max(1, min(linea, total))
		posicion = self._posicion_de_linea(linea)
		self.contenido.SetInsertionPoint(posicion)
		self.contenido.ShowPosition(posicion)
		if anunciar:
			enfocar(self.contenido)
			self.ctx.anunciar(_("Línea {n} de {t}").format(n=linea, t=total))

	def ir_a_linea(self) -> None:
		if not self.mostrable:
			self.ctx.avisar(_("El archivo no se muestra como texto."))
			return
		texto = pedir_texto(self, _("&Número de línea (de 1 a {t}):").format(t=self.total_lineas), _("Ir a la línea"),
			str(self.linea_actual()))
		if texto is None:
			return
		if not texto.strip().isdigit():
			self.ctx.avisar(_("Escriba un número de línea."))
			return
		self._ir(int(texto.strip()))

	def decir_linea(self) -> None:
		self.ctx.anunciar(_("Línea {n} de {t}").format(n=self.linea_actual(), t=self.total_lineas))

	def buscar(self) -> None:
		texto = pedir_texto(self, _("&Texto que buscar:"), _("Buscar en el archivo"), self.busqueda)
		if texto is None or not texto:
			return
		self.busqueda = texto
		self.buscar_siguiente(False)

	def buscar_siguiente(self, atras: bool = False) -> None:
		if not self.busqueda:
			self.buscar()
			return
		valor = self.contenido.GetValue()
		inicio, fin = self.contenido.GetSelection()
		desde = inicio if atras else (fin if fin > inicio else self.contenido.GetInsertionPoint())
		posicion, vuelta = buscar_en(valor, self.busqueda, desde, atras)
		if posicion < 0:
			self.ctx.sonar("vacio")
			self.ctx.anunciar(_("No se encuentra «{t}».").format(t=self.busqueda))
			return
		enfocar(self.contenido)
		self.contenido.SetSelection(posicion, posicion + len(self.busqueda))
		self.contenido.ShowPosition(posicion)
		numero = linea_de(valor, posicion)
		texto_linea = valor.split("\n")[numero - 1].strip()
		aviso = _("Línea {n}: {t}").format(n=numero, t=texto_linea)
		if vuelta:
			aviso = (_("Se ha vuelto al final. ") if atras else _("Se ha vuelto al principio. ")) + aviso
		self.ctx.anunciar(aviso)

	# ── Acciones ──────────────────────────────────────────────────────────────

	def blame(self) -> None:
		api = self.ctx.api()

		def mostrar(rangos: Any) -> None:
			filas = [como_dict(r) for r in como_lista(rangos)]
			DialogoLista(
				self, self.ctx, _("Blame de {r}").format(r=self.ruta), _("Autoría por &líneas:"),
				[(_("Líneas"), 100), (_("Autor"), 160), (_("Fecha"), 130), (_("Commit"), 420)],
				lambda r: [
					f"{r.get('startingLine', '')}-{r.get('endingLine', '')}" if r.get("startingLine") != r.get("endingLine") else str(r.get("startingLine", "")),
					como_dict(como_dict(como_dict(r.get("commit")).get("author")).get("user")).get("login")
					or como_dict(como_dict(r.get("commit")).get("author")).get("name", ""),
					f.fecha(como_dict(r.get("commit")).get("committedDate"), self.ctx.relativas()),
					f"{como_dict(r.get('commit')).get('abbreviatedOid', '')} {como_dict(r.get('commit')).get('messageHeadline', '')}",
				],
				filas, al_activar=lambda r: abrir.commit(self.ctx, self, self.nombre, como_dict(r.get("commit")).get("abbreviatedOid", "")),
				botones=[(_("&Abrir el commit"), lambda dlg, r: abrir.commit(self.ctx, dlg, self.nombre,
					como_dict(r.get("commit")).get("abbreviatedOid", "")), True),
					(_("&Ir a esas líneas"), lambda dlg, r: (dlg.Close(), self._ir(int(r.get("startingLine") or 1))), True)],
				ayuda=_("Cada fila es un grupo de líneas con el último commit que las cambió. Intro abre el commit."),
			).mostrar()

		en_segundo_plano(self, self.ctx, lambda: api.blame(self.nombre, self.ref_efectiva, self.ruta), inicio=_("Pidiendo el blame…"),
			sonido="", al_terminar=mostrar)

	def historial(self) -> None:
		api = self.ctx.api()

		def fila(c: dict) -> list[str]:
			datos = como_dict(c.get("commit"))
			autor = f.login(c.get("author")) if c.get("author") else como_dict(datos.get("author")).get("name", "")
			return [(c.get("sha") or "")[:7], f.primera_linea(datos.get("message")), autor,
				f.fecha(como_dict(datos.get("author")).get("date"), self.ctx.relativas())]

		def mostrar(pagina: Any) -> None:
			DialogoLista(
				self, self.ctx, _("Historial de {r}").format(r=self.ruta), _("&Commits que cambiaron el archivo:"),
				[(_("Commit"), 80), (_("Mensaje"), 420), (_("Autor"), 140), (_("Fecha"), 130)], fila,
				[c for c in como_lista(pagina) if isinstance(c, dict)],
				al_activar=lambda c: abrir.commit(self.ctx, self, self.nombre, c.get("sha", "")),
				botones=[(_("&Abrir el commit"), lambda dlg, c: abrir.commit(self.ctx, dlg, self.nombre, c.get("sha", "")), True)],
			).mostrar()

		en_segundo_plano(self, self.ctx, lambda: api.commits(self.nombre, 1, rama=self.ref, ruta=self.ruta), sonido="", al_terminar=mostrar)

	def editar(self) -> None:
		if not self.mostrable:
			self.ctx.avisar(_("Este archivo no se puede editar como texto."))
			return
		api = self.ctx.api()

		def abrir_editor(rama: str) -> None:
			dialogo = DialogoEditarArchivo(self, self.ctx, self.nombre, self.ruta, self.texto, self.sha, rama, self.saltos)
			try:
				if dialogo.ShowModal() != wx.ID_OK or not dialogo.resultado:
					return
				resultado = dialogo.resultado
			finally:
				dialogo.Destroy()
			self.despues_de_guardar(resultado, rama)

		if self.ref:
			abrir_editor(self.ref)
			return
		en_segundo_plano(self, self.ctx, lambda: como_dict(api.repositorio(self.nombre)).get("default_branch", "main"), sonido="",
			al_terminar=abrir_editor)

	def despues_de_guardar(self, resultado: dict, rama: str) -> None:
		"""Actualiza el texto y el sha si se guardó en la rama que se ve; abre el PR si se creó."""
		if resultado.get("rama") == rama:
			self.sha = resultado.get("sha") or self.sha
			self.texto = str(resultado.get("texto", self.texto)).replace("\r\n", "\n")
			self.datos = self.texto.replace("\n", self.saltos).encode("utf-8")
			self._pintar()
		pr = como_dict(resultado.get("pr"))
		if pr.get("number"):
			abrir.pull_request(self.ctx, self, self.nombre, int(pr["number"]))

	def descargar(self) -> None:
		if not self.datos:
			self.ctx.avisar(_("El archivo todavía no se ha cargado."))
			return
		dialogo = wx.FileDialog(self, _("Guardar el archivo"), defaultFile=Path(self.ruta).name,
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
		try:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			destino = dialogo.GetPath()
		finally:
			dialogo.Destroy()
		if not destino:
			return
		datos = self.datos
		en_segundo_plano(self, self.ctx, lambda: Path(destino).write_bytes(datos), sonido="descargado",
			exito=_("Archivo guardado en {d}.").format(d=destino))

	def url_web(self, ref: str = "") -> str:
		return f"https://{self.ctx.host}/{self.nombre}/blob/{ref or self.ref_efectiva}/{self.ruta}"

	def copiar_permanente(self) -> None:
		api = self.ctx.api()
		en_segundo_plano(self, self.ctx, lambda: como_dict(api.commit(self.nombre, self.ref_efectiva)).get("sha", ""), sonido="",
			al_terminar=lambda sha: copiar(self.ctx, self.url_web(sha or self.ref_efectiva), _("Enlace permanente copiado.")))

	def abrir_navegador(self) -> None:
		webbrowser.open(self.url_web())

	def ver_formateado(self) -> None:
		if not self.es_markdown:
			self.ctx.avisar(_("Solo los archivos Markdown se pueden ver formateados."))
			return
		from app.ui import visor_ayuda

		visor_ayuda.mostrar_documento(self, _("{r} (formateado)").format(r=self.ruta), self.texto)


def abrir_archivo(ctx: Any, padre: wx.Window | None, nombre: str, ruta: str, ref: str = "") -> None:
	"""Abre el visor de un archivo del repositorio (o trae al frente el que ya esté abierto)."""
	if VentanaDetalle.traer_al_frente(clave_archivo(nombre, ruta, ref)):
		return
	ventana = VentanaArchivo(padre, ctx, nombre, ruta, ref)
	ventana.mostrar()
	ventana.cargar()
