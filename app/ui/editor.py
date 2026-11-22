"""Editor accesible de texto Markdown para issues, comentarios, pull requests, releases...

- Etiquetas antes de cada campo y letras de acceso sin repetir.
- Vista previa (F7 o botón): muestra el Markdown ya formateado en el visor HTML
  (encabezados, listas y enlaces reales para el modo exploración del lector).
- Ctrl+Intro envía. El envío va en segundo plano y el diálogo **no se cierra
  si falla**: el texto escrito nunca se pierde por un error de red.
- Al cancelar con cambios, pregunta antes de descartar (configurable).
- Campos extra opcionales (casillas, desplegables) declarados por quien lo abre.
- Con ``con_adjuntos``, «Adjuntar archivo…» añade archivos de texto (registros)
  plegados en el texto o subidos a un gist secreto (``app.services.adjuntos``).
"""

from __future__ import annotations

import builtins
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import wx

from app.services import adjuntos
from app.ui.accesibilidad.dialogos import confirmar, crear_botonera, elegir_opcion, mostrar_error, preparar_dialogo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class CampoExtra:
	"""Un control adicional del editor.

	:param clave: nombre con el que llega el valor a la función de envío.
	:param etiqueta: texto con ``&``.
	:param tipo: ``bool``, ``opcion`` o ``texto``.
	:param opciones: para ``opcion``, pares ``(valor, etiqueta)``.
	"""

	clave: str
	etiqueta: str
	tipo: str = "bool"
	valor: Any = None
	opciones: list[tuple[Any, str]] = field(default_factory=list)
	ayuda: str = ""


class DialogoEditor(wx.Dialog):
	"""Diálogo para escribir un título opcional y un texto en Markdown.

	:param enviar: ``(valores) -> resultado``; se ejecuta en un hilo. ``valores``
		tiene ``titulo``, ``cuerpo`` y las claves de los campos extra.
	:param al_enviar: se llama en el hilo de la interfaz con el resultado, tras cerrar.
	:param con_adjuntos: muestra «Adjuntar archivo…» (para textos que van a GitHub:
		issues, pull requests, discusiones y comentarios).
	"""

	def __init__(
		self,
		padre: wx.Window | None,
		contexto: Any,
		titulo_ventana: str,
		enviar: Callable[[dict], Any],
		*,
		con_titulo: bool = False,
		titulo: str = "",
		cuerpo: str = "",
		etiqueta_cuerpo: str = "",
		etiqueta_enviar: str = "",
		extras: list[CampoExtra] | None = None,
		al_enviar: Callable[[Any], None] | None = None,
		plantillas: list[tuple[str, str]] | None = None,
		texto_contexto: str = "",
		clave_borrador: str | None = None,
		con_adjuntos: bool = False,
	) -> None:
		super().__init__(padre, title=titulo_ventana, size=(760, 560), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = contexto
		self._enviar = enviar
		self._al_enviar = al_enviar
		self._enviando = False
		#: Gists de adjuntos que se están subiendo (no se envía hasta que terminen).
		self._subiendo = 0
		self.resultado: Any = None
		self.controles_extra: dict[str, wx.Window] = {}
		self._plantillas = plantillas or []
		# Borrador: lo escrito y no enviado se guarda en data/db y se ofrece al volver.
		self._clave_borrador = clave_borrador or f"editor:{titulo_ventana}"
		self._almacen = getattr(contexto, "almacen", None)
		raiz = wx.BoxSizer(wx.VERTICAL)

		if texto_contexto:
			# Contexto de lo que se responde (comentario citado, línea de código...).
			raiz.Add(wx.StaticText(self, label=_("En &respuesta a:")), 0, wx.LEFT | wx.TOP, 6)
			self.campo_contexto = wx.TextCtrl(self, value=texto_contexto, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
				size=(-1, self.FromDIP(90)))
			raiz.Add(self.campo_contexto, 0, wx.EXPAND | wx.ALL, 6)

		self.campo_titulo: wx.TextCtrl | None = None
		if con_titulo:
			raiz.Add(wx.StaticText(self, label=_("&Título:")), 0, wx.LEFT | wx.TOP, 6)
			self.campo_titulo = wx.TextCtrl(self, value=titulo)
			self.campo_titulo.SetHelpText(_("Título breve y descriptivo."))
			raiz.Add(self.campo_titulo, 0, wx.EXPAND | wx.ALL, 6)

		if self._plantillas:
			raiz.Add(wx.StaticText(self, label=_("P&lantilla:")), 0, wx.LEFT | wx.TOP, 6)
			self.selector_plantilla = wx.Choice(self, choices=[_("(ninguna)")] + [n for n, _c in self._plantillas])
			self.selector_plantilla.SetSelection(0)
			self.selector_plantilla.SetHelpText(_("Al elegir una plantilla, su texto sustituye al cuerpo si está vacío."))
			self.selector_plantilla.Bind(wx.EVT_CHOICE, self._al_elegir_plantilla)
			raiz.Add(self.selector_plantilla, 0, wx.EXPAND | wx.ALL, 6)

		raiz.Add(wx.StaticText(self, label=etiqueta_cuerpo or _("Te&xto (Markdown):")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_cuerpo = wx.TextCtrl(self, value=cuerpo, style=wx.TE_MULTILINE | wx.TE_RICH2 | wx.TE_PROCESS_TAB)
		self.campo_cuerpo.SetHelpText(_(
			"Texto en Markdown. Control+Intro envía; F7 muestra la vista previa. "
			"Tabulador escribe una tabulación; Control+Tabulador pasa al control siguiente."
		))
		raiz.Add(self.campo_cuerpo, 1, wx.EXPAND | wx.ALL, 6)

		for extra in extras or []:
			control = self._crear_extra(extra, raiz)
			self.controles_extra[extra.clave] = control

		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_vista = wx.Button(self, label=_("&Vista previa (F7)"))
		self.boton_vista.Bind(wx.EVT_BUTTON, lambda _e: self.vista_previa())
		fila.Add(self.boton_vista, 0, wx.RIGHT, 6)
		self.boton_adjuntar: wx.Button | None = None
		if con_adjuntos:
			self.boton_adjuntar = wx.Button(self, label=_("Ad&juntar archivo…"))
			self.boton_adjuntar.SetHelpText(_(
				"Añade archivos de texto, como registros .log: dentro del texto en un bloque plegado o, si son "
				"largos, subidos a un gist secreto con su enlace. GitHub no deja subir imágenes desde aplicaciones."
			))
			self.boton_adjuntar.Bind(wx.EVT_BUTTON, lambda _e: self.adjuntar())
			fila.Add(self.boton_adjuntar, 0, wx.RIGHT, 6)
		fila.AddStretchSpacer()
		botones = crear_botonera(self, wx.OK | wx.CANCEL)
		self.boton_enviar = self.FindWindow(wx.ID_OK)
		self.boton_enviar.SetLabel(etiqueta_enviar or _("&Enviar"))
		fila.Add(botones, 0)
		raiz.Add(fila, 0, wx.EXPAND | wx.ALL, 6)
		self.estado = wx.StaticText(self, label="")
		raiz.Add(self.estado, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
		self.SetSizer(raiz)

		self._inicial = (titulo, cuerpo)
		self._ofrecer_borrador()
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self._al_cancelar, id=wx.ID_CANCEL)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		preparar_dialogo(self, foco_inicial=self.campo_titulo if con_titulo and not titulo else self.campo_cuerpo)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.CentreOnParent()

	def _crear_extra(self, extra: CampoExtra, raiz: wx.Sizer) -> wx.Window:
		if extra.tipo == "bool":
			control = wx.CheckBox(self, label=extra.etiqueta)
			control.SetValue(bool(extra.valor))
			raiz.Add(control, 0, wx.ALL, 6)
		elif extra.tipo == "opcion":
			raiz.Add(wx.StaticText(self, label=extra.etiqueta), 0, wx.LEFT | wx.TOP, 6)
			control = wx.Choice(self, choices=[e for _v, e in extra.opciones])
			valores = [v for v, _e in extra.opciones]
			control.SetSelection(valores.index(extra.valor) if extra.valor in valores else 0)
			control._valores = valores
			raiz.Add(control, 0, wx.EXPAND | wx.ALL, 6)
		else:
			raiz.Add(wx.StaticText(self, label=extra.etiqueta), 0, wx.LEFT | wx.TOP, 6)
			control = wx.TextCtrl(self, value=str(extra.valor or ""))
			raiz.Add(control, 0, wx.EXPAND | wx.ALL, 6)
		if extra.ayuda:
			control.SetHelpText(extra.ayuda)
		return control

	# ── Borradores ────────────────────────────────────────────────────────────

	def _ofrecer_borrador(self) -> None:
		if self._almacen is None:
			return
		try:
			guardado = self._almacen.borrador(self._clave_borrador)
		except Exception:  # noqa: BLE001 - sin base de datos se sigue sin borradores
			log.warning("No se pudo leer el borrador %s", self._clave_borrador, exc_info=True)
			return
		if not guardado:
			return
		titulo, cuerpo, fecha = guardado
		from app.services.formato import fecha_relativa

		if confirmar(self.GetParent(), _("Hay un borrador sin enviar de {f}. ¿Recuperarlo?").format(f=fecha_relativa(fecha)),
			_("Borrador guardado")) == wx.ID_YES:
			if self.campo_titulo is not None and titulo:
				self.campo_titulo.SetValue(titulo)
			self.campo_cuerpo.SetValue(cuerpo)
		else:
			self._borrar_borrador()

	def guardar_borrador(self) -> None:
		if self._almacen is None:
			return
		titulo = self.campo_titulo.GetValue() if self.campo_titulo is not None else ""
		try:
			self._almacen.guardar_borrador(self._clave_borrador, titulo, self.campo_cuerpo.GetValue())
		except Exception:  # noqa: BLE001
			log.warning("No se pudo guardar el borrador %s", self._clave_borrador, exc_info=True)

	def _borrar_borrador(self) -> None:
		if self._almacen is None:
			return
		try:
			self._almacen.borrar_borrador(self._clave_borrador)
		except Exception:  # noqa: BLE001
			log.warning("No se pudo borrar el borrador %s", self._clave_borrador, exc_info=True)

	# ── Valores ───────────────────────────────────────────────────────────────

	def valores(self) -> dict:
		datos: dict[str, Any] = {"cuerpo": self.campo_cuerpo.GetValue()}
		if self.campo_titulo is not None:
			datos["titulo"] = self.campo_titulo.GetValue().strip()
		for clave, control in self.controles_extra.items():
			if isinstance(control, wx.CheckBox):
				datos[clave] = control.GetValue()
			elif isinstance(control, wx.Choice):
				indice = control.GetSelection()
				datos[clave] = control._valores[indice] if indice >= 0 else None
			else:
				datos[clave] = control.GetValue()
		return datos

	def modificado(self) -> bool:
		titulo = self.campo_titulo.GetValue() if self.campo_titulo is not None else self._inicial[0]
		return (titulo, self.campo_cuerpo.GetValue()) != self._inicial

	# ── Acciones ──────────────────────────────────────────────────────────────

	def vista_previa(self) -> None:
		from app.ui import visor_ayuda

		texto = self.campo_cuerpo.GetValue()
		if not texto.strip():
			self.ctx.avisar(_("No hay texto que mostrar."))
			return
		titulo = self.campo_titulo.GetValue().strip() if self.campo_titulo is not None else ""
		visor_ayuda.mostrar_documento(self, _("Vista previa: {t}").format(t=titulo or self.GetTitle()), texto)

	# ── Adjuntos ──────────────────────────────────────────────────────────────

	def adjuntar(self) -> None:
		"""Elige archivos de texto y los añade al texto, plegados o como gist secreto."""
		with wx.FileDialog(self, _("Adjuntar archivos de texto"),
			wildcard=_("Todos los archivos (*.*)|*.*|Registros y texto (*.log;*.txt)|*.log;*.txt"),
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as dialogo:
			if dialogo.ShowModal() != wx.ID_OK:
				return
			rutas = dialogo.GetPaths()
		if not rutas:
			return

		def leer(_tarea: Any) -> list[tuple[str, str | BaseException, int]]:
			leidos: list[tuple[str, str | BaseException, int]] = []
			for ruta in rutas:
				try:
					leidos.append((ruta, adjuntos.leer_texto(ruta), os.path.getsize(ruta)))
				except (adjuntos.ErrorAdjunto, OSError) as error:
					leidos.append((ruta, error, 0))
			return leidos

		def al_fallar(error: BaseException) -> None:
			if self:
				mostrar_error(self, str(error), _("No se pudo leer el archivo"))

		self.ctx.tareas.enviar(leer, al_terminar=self._adjuntar_leidos, al_fallar=al_fallar, nombre="editor:adjuntar",
			duplicadas="permitir")

	def _adjuntar_leidos(self, leidos: list[tuple[str, str | BaseException, int]]) -> None:
		if not self:
			return
		for ruta, texto, octetos in leidos:
			nombre = os.path.basename(ruta)
			if isinstance(texto, BaseException):
				motivo = getattr(texto, "mensaje_usuario", None) or getattr(texto, "strerror", None) or str(texto)
				mostrar_error(self, _("«{n}»: {m}").format(n=nombre, m=motivo), _("No se puede adjuntar"))
				continue
			self._adjuntar_texto(nombre, texto, octetos)

	def _adjuntar_texto(self, nombre: str, texto: str, octetos: int) -> None:
		"""Pregunta cómo adjuntar un archivo ya leído y lo hace."""
		from app.services.formato import ngettext_, tamano

		bloque = adjuntos.bloque_plegado(nombre, texto, tamano(octetos))
		cabe = adjuntos.cabe_en_cuerpo(self.campo_cuerpo.GetValue(), bloque)
		lineas = texto.count("\n") + (0 if texto.endswith("\n") else 1)
		descripcion = _("«{n}»: {t}, {l}.").format(n=nombre, t=tamano(octetos),
			l=ngettext_("{n} línea", "{n} líneas", lineas).format(n=lineas))
		aviso = _(
			"Antes, revise que no lleve contraseñas, tokens ni datos personales: lo leerá cualquiera que vea el texto. "
			"Un gist secreto no sale en los listados, pero lo abre cualquiera que tenga el enlace."
		)
		dentro, gist, cancelar = _("&Dentro del texto, plegado"), _("Como &gist secreto, con su enlace"), _("&Cancelar")
		if cabe:
			opciones = [dentro, gist, cancelar]
			pregunta = _("¿Cómo quiere adjuntarlo?")
		else:
			opciones = [gist, cancelar]
			pregunta = _(
				"Es demasiado largo para ir dentro del texto (GitHub admite {n} caracteres). "
				"¿Subirlo a un gist secreto y añadir su enlace?"
			).format(n=f"{adjuntos.LIMITE_CUERPO:,}".replace(",", " "))
		indice = elegir_opcion(self, f"{descripcion} {pregunta}\n\n{aviso}", _("Adjuntar archivo"), opciones)
		if indice is None or opciones[indice] == cancelar:
			return
		if opciones[indice] == dentro:
			self._insertar_en_cuerpo(bloque)
			self.ctx.avisar(_("Adjuntado «{n}» dentro del texto, plegado.").format(n=nombre))
		else:
			self._subir_gist(nombre, texto)

	def _insertar_en_cuerpo(self, bloque: str) -> None:
		# El foco no se mueve (lo decide la persona); solo cambia el texto y el cursor.
		campo = self.campo_cuerpo
		nuevo, cursor = adjuntos.insertar(campo.GetValue(), campo.GetInsertionPoint(), bloque)
		campo.SetValue(nuevo)
		campo.SetInsertionPoint(cursor)

	def _subir_gist(self, nombre: str, texto: str) -> None:
		self._subiendo += 1
		self.estado.SetLabel(_("Subiendo «{n}» a un gist secreto…").format(n=nombre))
		self.ctx.avisar(_("Subiendo «{n}» a un gist secreto…").format(n=nombre))

		def subir(_tarea: Any) -> str:
			creado = self.ctx.api().crear_gist({nombre: texto}, descripcion=_("Adjunto: {n}").format(n=nombre), publico=False)
			return adjuntos.url_archivo_gist(creado, nombre)

		def al_terminar(url: str) -> None:
			if not self:
				return
			self._subiendo -= 1
			self.estado.SetLabel("")
			self._insertar_en_cuerpo(adjuntos.enlace_gist(nombre, url))
			self.ctx.sonar("enviado")
			self.ctx.avisar(_("Subido «{n}»; su enlace está en el texto.").format(n=nombre))

		def al_fallar(error: BaseException) -> None:
			if not self:
				return
			self._subiendo -= 1
			self.estado.SetLabel("")
			self.ctx.sonar("error")
			motivo = getattr(error, "mensaje_usuario", None) or str(error)
			mostrar_error(self, _(
				"No se pudo subir «{n}» a un gist: {m}\n\nSi la sesión se inició con un token, compruebe que tiene el "
				"permiso «gist»."
			).format(n=nombre, m=motivo), _("No se pudo adjuntar"))

		self.ctx.tareas.enviar(subir, al_terminar=al_terminar, al_fallar=al_fallar, nombre="editor:gist",
			duplicadas="permitir")

	def _al_elegir_plantilla(self, _evento: wx.CommandEvent) -> None:
		indice = self.selector_plantilla.GetSelection() - 1
		if indice < 0:
			return
		_nombre, contenido = self._plantillas[indice]
		if self.campo_cuerpo.GetValue().strip() and confirmar(
			self, _("¿Sustituir el texto escrito por la plantilla?"), _("Plantilla"), peligroso=True
		) != wx.ID_YES:
			return
		self.campo_cuerpo.SetValue(contenido)

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla = evento.GetKeyCode()
		if tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and evento.ControlDown():
			self._al_aceptar(None)
			return
		if tecla == wx.WXK_F7:
			self.vista_previa()
			return
		if tecla == wx.WXK_ESCAPE and not evento.HasAnyModifiers():
			# Escape pasa por la misma confirmación que Cancelar (no se pierde el texto).
			from app.ui.accesibilidad.dialogos import desplegable_abierto

			if not desplegable_abierto(wx.Window.FindFocus()):
				self._al_cancelar(None)
				return
		evento.Skip()

	def _al_aceptar(self, _evento: wx.CommandEvent | None) -> None:
		if self._enviando:
			return
		if self._subiendo:
			self.ctx.avisar(_("Espere a que termine de subirse el adjunto."))
			return
		valores = self.valores()
		if self.campo_titulo is not None and not valores["titulo"]:
			mostrar_error(self, _("Escriba un título."), _("Falta el título"))
			self.campo_titulo.SetFocus()
			return
		self._enviando = True
		self.boton_enviar.Disable()
		self.estado.SetLabel(_("Enviando…"))
		self.ctx.avisar(_("Enviando…"))

		def al_terminar(resultado: Any) -> None:
			self._enviando = False
			self.resultado = resultado
			self._borrar_borrador()
			self.ctx.sonar("enviado")
			self.ctx.avisar(_("Enviado."), interrumpir=False)
			if self.IsModal():
				self.EndModal(wx.ID_OK)
			else:
				self.Destroy()
			if self._al_enviar:
				self._al_enviar(resultado)

		def al_fallar(error: BaseException) -> None:
			self._enviando = False
			self.boton_enviar.Enable()
			self.estado.SetLabel("")
			self.ctx.sonar("error")
			self.guardar_borrador()
			mostrar_error(self, getattr(error, "mensaje_usuario", None) or str(error), _("No se pudo enviar"))
			self.campo_cuerpo.SetFocus()

		self.ctx.tareas.enviar(lambda tarea: self._enviar(valores), al_terminar=al_terminar, al_fallar=al_fallar,
			nombre="editor:enviar", duplicadas="permitir")

	def _puede_cerrar(self) -> bool:
		if self._enviando:
			self.ctx.avisar(_("Espere a que termine el envío."))
			return False
		if not self.modificado():
			return True
		if self._almacen is not None:
			respuesta = confirmar(self, _("¿Guardar lo escrito como borrador para recuperarlo después?"), _("Cerrar el editor"),
				con_cancelar=True)
			if respuesta == wx.ID_CANCEL:
				return False
			if respuesta == wx.ID_YES:
				self.guardar_borrador()
			else:
				self._borrar_borrador()
			return True
		if self.ctx.config.obtener("editor.confirmar_descartar", True):
			return confirmar(self, _("¿Descartar el texto escrito?"), _("Descartar cambios"), peligroso=True) == wx.ID_YES
		return True

	def _al_cancelar(self, _evento: wx.CommandEvent) -> None:
		if self._puede_cerrar():
			if self.IsModal():
				self.EndModal(wx.ID_CANCEL)
			else:
				self.Destroy()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if evento.CanVeto() and not self._puede_cerrar():
			evento.Veto()
			return
		evento.Skip()


def editar(padre: wx.Window | None, contexto: Any, titulo_ventana: str, enviar: Callable[[dict], Any], **opciones) -> Any:
	"""Abre el editor de forma modal. Devuelve el resultado del envío o ``None`` si se canceló."""
	dialogo = DialogoEditor(padre, contexto, titulo_ventana, enviar, **opciones)
	try:
		if dialogo.ShowModal() == wx.ID_OK:
			return dialogo.resultado
		return None
	finally:
		if dialogo:
			dialogo.Destroy()
