"""Traductor de la aplicación (incidencia #13): leer traducido y escribir en otro idioma.

- ``VentanaTraductor``: texto original, idioma de origen y de destino, motor, el
  texto traducido y sus órdenes. Se abre vacía desde Herramientas, «Traductor»
  (Control+Mayúsculas+Y) o ya traduciendo lo que se pide desde una conversación
  (Control+T traduce el elemento elegido; Control+Mayúsculas+T, toda la conversación).
- ``revisar_y_enviar``: lo que usa el editor (y el formulario de issue) para enviar
  en otro idioma: traduce el título y el texto, los enseña para revisarlos y
  corregirlos, y entonces envía.
- Solo se traduce lo que se pide, nunca la interfaz; todo en segundo plano.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import wx

from app.services import traduccion as tr
from app.ui.accesibilidad.dialogos import crear_botonera, mostrar_error, preparar_dialogo
from app.ui.accesibilidad.foco import enfocar

log = logging.getLogger(__name__)

_ventana: VentanaTraductor | None = None


# ════════════════════════════════════════════════════════════════════════════
# Idiomas y motores en desplegables
# ════════════════════════════════════════════════════════════════════════════


def idiomas_ordenados() -> list[tuple[str, str]]:
	"""(código, nombre en el idioma de la interfaz), por orden alfabético del nombre."""
	return sorted(((codigo, _(nombre)) for codigo, nombre, _ingles in tr.IDIOMAS), key=lambda par: par[1].casefold())


def crear_selector_idioma(padre: wx.Window, sizer: wx.Sizer, etiqueta: str, valor: str, con_auto: bool = False,
	con_ninguno: str = "") -> tuple[wx.Choice, list[str]]:
	"""Etiqueta y desplegable de idiomas. Devuelve el control y los códigos en el orden mostrado."""
	codigos: list[str] = []
	nombres: list[str] = []
	if con_ninguno:
		codigos.append("")
		nombres.append(con_ninguno)
	if con_auto:
		codigos.append(tr.AUTO)
		nombres.append(tr.nombre_idioma(tr.AUTO))
	for codigo, nombre in idiomas_ordenados():
		codigos.append(codigo)
		nombres.append(nombre)
	sizer.Add(wx.StaticText(padre, label=etiqueta), 0, wx.LEFT | wx.TOP, 6)
	control = wx.Choice(padre, choices=nombres)
	control.SetSelection(codigos.index(valor) if valor in codigos else 0)
	sizer.Add(control, 0, wx.EXPAND | wx.ALL, 6)
	return control, codigos


def destino_lectura(ctx: Any) -> str:
	return str(ctx.config.obtener("traduccion.destino_lectura", "") or "") or tr.idioma_de_la_interfaz()


def ajustes(ctx: Any, motor: str | None = None) -> tr.Ajustes:
	return tr.ajustes_desde(ctx.config, getattr(ctx, "secretos", None), motor)


def traducir_en_fondo(ctx: Any, texto: str, destino: str, origen: str, al_terminar: Callable[[tr.Resultado], None],
	al_fallar: Callable[[BaseException], None], motor: str | None = None) -> Any:
	"""Traduce en el gestor de tareas (nunca en el hilo de la interfaz)."""
	datos = ajustes(ctx, motor)
	return ctx.tareas.enviar(lambda _tarea: tr.traducir(texto, destino, origen, datos), al_terminar=al_terminar,
		al_fallar=al_fallar, nombre="traducir", duplicadas="permitir")


def en_frase(codigo: str) -> str:
	"""Nombre del idioma dentro de una frase: en español va en minúscula («del inglés»), en inglés no («from English»)."""
	nombre = tr.nombre_idioma(codigo)
	return nombre.lower() if tr.idioma_de_la_interfaz() == "es" else nombre


def texto_resultado(resultado: tr.Resultado) -> str:
	return _("Traducido del {o} al {d} con {m}.").format(o=en_frase(resultado.origen),
		d=en_frase(resultado.destino), m=tr.nombre_motor_corto(resultado.motor))


# ════════════════════════════════════════════════════════════════════════════
# Ventana «Traductor»
# ════════════════════════════════════════════════════════════════════════════


def abrir_traductor(ctx: Any, padre: wx.Window | None = None, texto: str = "", titulo: str = "",
	traducir_ya: bool = False) -> VentanaTraductor:
	"""Abre el traductor (o lo trae al frente). Con ``traducir_ya`` traduce ``texto`` al idioma de lectura."""
	global _ventana
	if _ventana is None or not _ventana:
		_ventana = VentanaTraductor(ctx)
	if texto:
		_ventana.poner_texto(texto, titulo)
	_ventana.Show()
	_ventana.Raise()
	if texto and traducir_ya:
		_ventana.traducir()
	else:
		enfocar(_ventana.campo_original)
	return _ventana


class VentanaTraductor(wx.Frame):
	"""Traduce cualquier texto con el motor y los idiomas que se elijan."""

	def __init__(self, ctx: Any) -> None:
		super().__init__(None, title=_("Traductor"), size=(900, 640))
		self.ctx = ctx
		self._traduciendo = False
		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)

		raiz.Add(wx.StaticText(panel, label=_("Texto &original:")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_original = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_RICH2, size=(-1, self.FromDIP(150)))
		self.campo_original.SetHelpText(_("Escriba o pegue el texto. Control+Intro traduce."))
		raiz.Add(self.campo_original, 1, wx.EXPAND | wx.ALL, 6)

		fila = wx.BoxSizer(wx.HORIZONTAL)
		columna = wx.BoxSizer(wx.VERTICAL)
		self.origen, self._codigos_origen = crear_selector_idioma(panel, columna, _("&De:"),
			str(ctx.config.obtener("traduccion.origen_lectura", tr.AUTO) or tr.AUTO), con_auto=True)
		fila.Add(columna, 1, wx.EXPAND)
		columna = wx.BoxSizer(wx.VERTICAL)
		self.destino, self._codigos_destino = crear_selector_idioma(panel, columna, _("&A:"), destino_lectura(ctx))
		fila.Add(columna, 1, wx.EXPAND)
		columna = wx.BoxSizer(wx.VERTICAL)
		columna.Add(wx.StaticText(panel, label=_("&Motor:")), 0, wx.LEFT | wx.TOP, 6)
		self._motores = [m for m, _n, _c in tr.MOTORES]
		self.motor = wx.Choice(panel, choices=[_(n) for _m, n, _c in tr.MOTORES])
		actual = str(ctx.config.obtener("traduccion.motor", tr.MOTOR_POR_DEFECTO))
		self.motor.SetSelection(self._motores.index(actual) if actual in self._motores else 0)
		self.motor.SetHelpText(_("Las claves de los motores que las piden se escriben en Preferencias, Claves de traducción."))
		columna.Add(self.motor, 0, wx.EXPAND | wx.ALL, 6)
		fila.Add(columna, 1, wx.EXPAND)
		raiz.Add(fila, 0, wx.EXPAND)

		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_traducir = wx.Button(panel, label=_("&Traducir"))
		self.boton_traducir.SetHelpText(_("Traduce el texto original (también con Control+Intro)."))
		self.boton_traducir.Bind(wx.EVT_BUTTON, lambda _e: self.traducir())
		self.boton_intercambiar = wx.Button(panel, label=_("&Intercambiar los idiomas"))
		self.boton_intercambiar.SetHelpText(_("Pone el destino como origen y al revés, y la traducción como texto original."))
		self.boton_intercambiar.Bind(wx.EVT_BUTTON, lambda _e: self.intercambiar())
		for boton in (self.boton_traducir, self.boton_intercambiar):
			botones.Add(boton, 0, wx.ALL, 4)
		raiz.Add(botones, 0)

		raiz.Add(wx.StaticText(panel, label=_("Te&xto traducido:")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_traducido = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=(-1, self.FromDIP(200)))
		self.campo_traducido.SetHelpText(_("La traducción. Solo lectura: se puede copiar o ver formateada."))
		raiz.Add(self.campo_traducido, 2, wx.EXPAND | wx.ALL, 6)
		self.estado = wx.StaticText(panel, label="")
		raiz.Add(self.estado, 0, wx.LEFT | wx.RIGHT, 6)

		otros = wx.BoxSizer(wx.HORIZONTAL)
		for etiqueta, ayuda, funcion in (
			(_("&Copiar la traducción"), _("Copia el texto traducido."), self.copiar),
			(_("&Ver formateada"), _("Abre la traducción como página, con encabezados y enlaces navegables."), self.ver_formateada),
			(_("C&errar"), _("Cierra el traductor."), self.Close),
		):
			boton = wx.Button(panel, label=etiqueta)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, lambda _e, fn=funcion: fn())
			otros.Add(boton, 0, wx.ALL, 4)
		raiz.Add(otros, 0)
		panel.SetSizer(raiz)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)

	def poner_texto(self, texto: str, titulo: str = "") -> None:
		self.campo_original.ChangeValue(texto)
		self.campo_traducido.ChangeValue("")
		self.SetTitle(_("Traductor: {t}").format(t=titulo) if titulo else _("Traductor"))
		self.estado.SetLabel("")

	@property
	def codigo_origen(self) -> str:
		return self._codigos_origen[max(0, self.origen.GetSelection())]

	@property
	def codigo_destino(self) -> str:
		return self._codigos_destino[max(0, self.destino.GetSelection())]

	@property
	def codigo_motor(self) -> str:
		return self._motores[max(0, self.motor.GetSelection())]

	def traducir(self) -> None:
		texto = self.campo_original.GetValue()
		if not texto.strip():
			self.ctx.avisar(_("No hay texto que traducir."))
			enfocar(self.campo_original)
			return
		if self._traduciendo:
			return
		self._traduciendo = True
		self.estado.SetLabel(_("Traduciendo…"))
		self.ctx.avisar(_("Traduciendo…"))

		def listo(resultado: tr.Resultado) -> None:
			self._traduciendo = False
			if not self:
				return
			self.campo_traducido.ChangeValue(resultado.texto)
			self.estado.SetLabel(texto_resultado(resultado))
			self.ctx.sonar("listo")
			# La traducción se lee entera al llegar al campo: es lo que se ha pedido.
			enfocar(self.campo_traducido)
			self.campo_traducido.SetInsertionPoint(0)

		def fallo(error: BaseException) -> None:
			self._traduciendo = False
			if not self:
				return
			self.estado.SetLabel(_("No se pudo traducir."))
			self.ctx.sonar("error")
			mostrar_error(self, getattr(error, "mensaje_usuario", None) or str(error), _("No se pudo traducir"))

		traducir_en_fondo(self.ctx, texto, self.codigo_destino, self.codigo_origen, listo, fallo, self.codigo_motor)

	def intercambiar(self) -> None:
		origen, destino = self.codigo_origen, self.codigo_destino
		nuevo_origen = destino
		nuevo_destino = origen if origen != tr.AUTO else tr.idioma_de_la_interfaz()
		self.origen.SetSelection(self._codigos_origen.index(nuevo_origen))
		self.destino.SetSelection(self._codigos_destino.index(nuevo_destino))
		if self.campo_traducido.GetValue().strip():
			self.campo_original.ChangeValue(self.campo_traducido.GetValue())
			self.campo_traducido.ChangeValue("")
		self.ctx.avisar(_("Del {o} al {d}.").format(o=en_frase(nuevo_origen), d=en_frase(nuevo_destino)))

	def copiar(self) -> None:
		from app.ui.accesibilidad.teclado import copiar_texto

		texto = self.campo_traducido.GetValue()
		if texto and copiar_texto(texto):
			self.ctx.sonar("copiado")
			self.ctx.avisar(_("Traducción copiada."))
		else:
			self.ctx.avisar(_("Todavía no hay traducción."))

	def ver_formateada(self) -> None:
		texto = self.campo_traducido.GetValue()
		if not texto.strip():
			self.ctx.avisar(_("Todavía no hay traducción."))
			return
		from app.ui import visor_ayuda

		visor_ayuda.mostrar_documento(self, _("Traducción"), texto)

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla = evento.GetKeyCode()
		if tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and evento.ControlDown():
			self.traducir()
			return
		if tecla == wx.WXK_ESCAPE and not evento.HasAnyModifiers():
			self.Close()
			return
		evento.Skip()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		global _ventana
		if _ventana is self:
			_ventana = None
		evento.Skip()


# ════════════════════════════════════════════════════════════════════════════
# Enviar en otro idioma
# ════════════════════════════════════════════════════════════════════════════


class DialogoRevisarTraduccion(wx.Dialog):
	"""Título y texto ya traducidos, editables, para revisarlos antes de enviar."""

	def __init__(self, padre: wx.Window | None, titulo: str | None, cuerpo: str, original: str, resultado: tr.Resultado) -> None:
		super().__init__(padre, title=_("Revisar la traducción antes de enviar"), size=(820, 620),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=texto_resultado(resultado) + " " + _("Puede corregirla antes de enviar.")),
			0, wx.ALL, 6)
		self.campo_titulo: wx.TextCtrl | None = None
		if titulo is not None:
			raiz.Add(wx.StaticText(self, label=_("&Título traducido:")), 0, wx.LEFT | wx.TOP, 6)
			self.campo_titulo = wx.TextCtrl(self, value=titulo)
			raiz.Add(self.campo_titulo, 0, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("Te&xto traducido:")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_cuerpo = wx.TextCtrl(self, value=cuerpo, style=wx.TE_MULTILINE | wx.TE_RICH2)
		raiz.Add(self.campo_cuerpo, 2, wx.EXPAND | wx.ALL, 6)
		raiz.Add(wx.StaticText(self, label=_("Texto &original (solo lectura):")), 0, wx.LEFT | wx.TOP, 6)
		campo_original = wx.TextCtrl(self, value=original, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
		raiz.Add(campo_original, 1, wx.EXPAND | wx.ALL, 6)
		self.casilla_original = wx.CheckBox(self, label=_("&Añadir el original plegado al final"))
		self.casilla_original.SetHelpText(_("Añade el texto original al final, plegado («Original»), para quien lo entienda."))
		raiz.Add(self.casilla_original, 0, wx.ALL, 6)
		botones = crear_botonera(self, wx.OK | wx.CANCEL)
		self.FindWindow(wx.ID_OK).SetLabel(_("&Enviar la traducción"))
		self.FindWindow(wx.ID_CANCEL).SetLabel(_("&Volver a editar"))
		raiz.Add(botones, 0, wx.EXPAND | wx.ALL, 6)
		self.SetSizer(raiz)
		preparar_dialogo(self, foco_inicial=self.campo_titulo or self.campo_cuerpo)


def revisar_y_enviar(padre: wx.Window, ctx: Any, titulo: str | None, cuerpo: str, destino: str,
	enviar: Callable[[str | None, str], None], al_cancelar: Callable[[], None] | None = None) -> None:
	"""Traduce título y cuerpo a ``destino``, los enseña para revisarlos y llama a ``enviar(titulo, cuerpo)``.

	El título se traduce aparte (es corto y no lleva Markdown). Si la persona vuelve a editar
	o la traducción falla, no se envía nada (``al_cancelar``).
	"""
	ctx.avisar(_("Traduciendo al {i} antes de enviar…").format(i=en_frase(destino)))
	datos = ajustes(ctx)

	def trabajo(_tarea: Any) -> tuple[str | None, tr.Resultado]:
		titulo_traducido = tr.traducir(titulo, destino, tr.AUTO, datos).texto if titulo else titulo
		return titulo_traducido, tr.traducir(cuerpo, destino, tr.AUTO, datos)

	def listo(resultado: tuple[str | None, tr.Resultado]) -> None:
		if not padre:
			return
		titulo_traducido, cuerpo_traducido = resultado
		dialogo = DialogoRevisarTraduccion(padre, titulo_traducido, cuerpo_traducido.texto, cuerpo, cuerpo_traducido)
		dialogo.casilla_original.SetValue(bool(ctx.config.obtener("traduccion.incluir_original", False)))
		try:
			if dialogo.ShowModal() != wx.ID_OK:
				if al_cancelar is not None:
					al_cancelar()
				return
			titulo_final = dialogo.campo_titulo.GetValue().strip() if dialogo.campo_titulo is not None else None
			cuerpo_final = dialogo.campo_cuerpo.GetValue()
			if dialogo.casilla_original.GetValue() and cuerpo.strip():
				cuerpo_final = tr.con_original(cuerpo_final, cuerpo, cuerpo_traducido.origen)
			ctx.config.establecer("traduccion.incluir_original", dialogo.casilla_original.GetValue())
		finally:
			dialogo.Destroy()
		enviar(titulo_final, cuerpo_final)

	def fallo(error: BaseException) -> None:
		ctx.sonar("error")
		mostrar_error(padre if padre else None, getattr(error, "mensaje_usuario", None) or str(error), _("No se pudo traducir"))
		if al_cancelar is not None:
			al_cancelar()

	ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre="traducir:envio", duplicadas="permitir")
