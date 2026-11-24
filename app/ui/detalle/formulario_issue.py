"""Nueva issue con las plantillas del repositorio: elegir plantilla y rellenar formularios.

- ``nueva_issue`` carga en segundo plano las plantillas de
  ``.github/ISSUE_TEMPLATE`` y su ``config.yml``, deja elegir con
  ``elegir_uno`` (nombre y descripción de cada una, «Issue en blanco» si el
  repositorio lo permite y los enlaces de contacto, que abren el navegador) y
  abre el editor Markdown de siempre o el formulario.
- ``DialogoFormularioIssue`` muestra un formulario YAML como controles
  nativos: un campo por ``input``, un campo multilínea por ``textarea``, un
  desplegable (o una lista de casillas si es múltiple) por ``dropdown`` y una
  casilla por opción de ``checkboxes``. Los textos ``markdown`` van en campos de
  solo lectura, en su sitio, para leerlos con las flechas.
- Las etiquetas, asignados y tipo de la plantilla se envían con la issue; si
  GitHub no los acepta por falta de permiso, la issue se crea sin ellos y se
  avisa (``ApiGitHub.crear_issue_con_plantilla``).

Teclado del formulario: Control+Intro crea la issue, F7 muestra la vista
previa del cuerpo y Escape cancela (pregunta antes si hay algo escrito). Las
letras de acceso se reparten solas entre los campos sin repetirse.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable
from typing import Any

import wx
from wx.lib.scrolledpanel import ScrolledPanel

from app.services import plantillas as pl
from app.ui.accesibilidad import foco as foco_ui
from app.ui.accesibilidad.ayuda import texto_ayuda
from app.ui.accesibilidad.dialogos import confirmar, desplegable_abierto, mostrar_error, mostrar_mensaje, preparar_dialogo
from app.ui.comunes import ListaCasillas, abrir_url, elegir_uno, en_segundo_plano, mensaje_error

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Letras de acceso fijas del formulario: «&Título», «&Crear la issue», «&Vista previa» y «Ca&ncelar».
LETRAS_FIJAS = "tcvn"


def letras_fijas() -> set[str]:
	"""Las de ``LETRAS_FIJAS`` en el idioma de la interfaz (en inglés «&Title», «&Preview»...)."""
	textos = (_("&Título:"), _("&Vista previa"), _("&Crear la issue"), _("Ca&ncelar"), _("Tra&ducir al enviar a:"))
	return {t[t.index("&") + 1].lower() for t in textos if "&" in t[:-1]}


def _es_letra_valida(caracter: str) -> bool:
	return (caracter.isascii() and caracter.isalnum()) or caracter == "ñ"


def poner_letra(texto: str, ocupadas: set[str]) -> str:
	"""Pone la letra de acceso en el primer carácter libre (antes, en el inicio de una palabra).

	Los textos vienen del formulario del repositorio: hay que repartir las
	letras sin repetirlas. La letra elegida se añade a ``ocupadas``; si no
	queda ninguna libre, el texto se devuelve sin letra.
	"""
	limpio = texto.replace("&", "&&")
	iniciales = [i for i, c in enumerate(limpio) if i == 0 or not limpio[i - 1].isalnum()]
	for posicion in iniciales + list(range(len(limpio))):
		caracter = limpio[posicion].lower()
		if _es_letra_valida(caracter) and caracter not in ocupadas:
			ocupadas.add(caracter)
			return limpio[:posicion] + "&" + limpio[posicion:]
	return limpio


class DialogoFormularioIssue(wx.Dialog):
	"""Formulario de issue (YAML) con controles nativos.

	:param enviar: ``(valores) -> resultado``; se ejecuta en un hilo con
		``titulo`` y ``cuerpo`` (ya compuesto como en la web).
	:param al_enviar: se llama en el hilo de la interfaz con el resultado, tras cerrar.
	"""

	def __init__(
		self,
		padre: wx.Window | None,
		contexto: Any,
		titulo_ventana: str,
		plantilla: pl.Plantilla,
		enviar: Callable[[dict], Any],
		al_enviar: Callable[[Any], None] | None = None,
	) -> None:
		super().__init__(padre, title=titulo_ventana, size=(780, 640), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = contexto
		self.plantilla = plantilla
		self._enviar = enviar
		self._al_enviar = al_enviar
		self._enviando = False
		self.resultado: Any = None
		#: Control de cada pregunta por ``Elemento.clave`` (lista de casillas en ``checkboxes``).
		self.controles: dict[str, Any] = {}
		self._letras = letras_fijas()
		raiz = wx.BoxSizer(wx.VERTICAL)

		# Panel con barra de desplazamiento: un formulario puede tener muchos campos
		# y ScrolledPanel lleva a la vista el control que recibe el foco.
		self.panel = ScrolledPanel(self)
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		cuerpo.Add(wx.StaticText(self.panel, label=_("&Título:")), 0, wx.LEFT | wx.TOP, 6)
		self.campo_titulo = wx.TextCtrl(self.panel, value=plantilla.titulo)
		self.campo_titulo.SetHelpText(_("Título breve y descriptivo. La plantilla puede traer el principio ya escrito."))
		cuerpo.Add(self.campo_titulo, 0, wx.EXPAND | wx.ALL, 6)
		for elemento in plantilla.elementos:
			self._crear_elemento(elemento, cuerpo)
		self.panel.SetSizer(cuerpo)
		self.panel.SetupScrolling(scroll_x=False)
		raiz.Add(self.panel, 1, wx.EXPAND)

		# Escribir en un idioma y crear la issue en otro (incidencia #13).
		from app.ui.traductor import crear_selector_idioma

		self.selector_traduccion, self._codigos_traduccion = crear_selector_idioma(
			self, raiz, _("Tra&ducir al enviar a:"), str(contexto.config.obtener("traduccion.destino_envio", "") or ""),
			con_ninguno=_("No traducir"))
		self.selector_traduccion.SetHelpText(_(
			"Escriba en su idioma y elija aquí en cuál se creará la issue: se traducen el título y el texto, se le "
			"enseñan para revisarlos y solo entonces se crea."))

		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_vista = wx.Button(self, label=_("&Vista previa"))
		self.boton_vista.SetHelpText(_("Muestra el texto de la issue tal y como se enviará (también con F7)."))
		self.boton_vista.Bind(wx.EVT_BUTTON, lambda _e: self.vista_previa())
		fila.Add(self.boton_vista, 0, wx.RIGHT, 6)
		fila.AddStretchSpacer()
		self.boton_crear = wx.Button(self, wx.ID_OK, _("&Crear la issue"))
		self.boton_crear.SetHelpText(_("Crea la issue en GitHub (también con Control+Intro)."))
		self.boton_crear.SetDefault()
		fila.Add(self.boton_crear, 0, wx.RIGHT, 6)
		self.boton_cancelar = wx.Button(self, wx.ID_CANCEL, _("Ca&ncelar"))
		fila.Add(self.boton_cancelar, 0)
		raiz.Add(fila, 0, wx.EXPAND | wx.ALL, 6)
		self.estado = wx.StaticText(self, label="")
		raiz.Add(self.estado, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
		self.SetSizer(raiz)

		self._inicial = self._instantanea()
		self.Bind(wx.EVT_BUTTON, lambda _e: self.enviar(), id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.cancelar(), id=wx.ID_CANCEL)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		preparar_dialogo(self)
		# El título suele traer un prefijo («[Fallo]: »): el cursor va al final para
		# seguir escribiendo (el foco inicial de preparar_dialogo lo seleccionaría todo).
		self.Bind(wx.EVT_INIT_DIALOG, self._al_iniciar)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.CentreOnParent()

	# ── Construcción ──────────────────────────────────────────────────────────

	def _etiqueta(self, elemento: pl.Elemento) -> str:
		texto = elemento.etiqueta or elemento.clave
		if elemento.obligatorio:
			texto = _("{e} (obligatorio)").format(e=texto)
		return poner_letra(texto, self._letras) + ":"

	def _ayuda(self, elemento: pl.Elemento) -> str:
		partes = [elemento.descripcion] if elemento.descripcion else []
		if elemento.marcador:
			partes.append(_("Ejemplo: {e}").format(e=elemento.marcador))
		if elemento.obligatorio:
			partes.append(_("Es obligatorio."))
		return " ".join(partes)

	def _crear_elemento(self, elemento: pl.Elemento, sizer: wx.Sizer) -> None:
		panel = self.panel
		if elemento.tipo == "markdown":
			sizer.Add(wx.StaticText(panel, label=poner_letra(_("Información del formulario"), self._letras) + ":"),
				0, wx.LEFT | wx.TOP, 6)
			texto = wx.TextCtrl(panel, value=elemento.valor, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
				size=(-1, self.FromDIP(min(160, 40 + 18 * elemento.valor.count("\n")))))
			texto.SetHelpText(_("Texto del formulario, de solo lectura. No se incluye en la issue."))
			sizer.Add(texto, 0, wx.EXPAND | wx.ALL, 6)
			return
		ayuda = self._ayuda(elemento)
		if elemento.tipo == "checkboxes":
			# Un grupo con el nombre del elemento: el lector lo dice al entrar en la primera casilla.
			nombre_grupo = (elemento.etiqueta or elemento.clave) + (_(" (obligatorio)") if elemento.obligatorio else "")
			grupo = wx.StaticBox(panel, label=nombre_grupo.replace("&", "&&"))
			caja = wx.StaticBoxSizer(grupo, wx.VERTICAL)
			casillas = []
			for casilla in elemento.casillas:
				texto = casilla.etiqueta + (_(" (obligatoria)") if casilla.obligatoria else "")
				control = wx.CheckBox(grupo, label=poner_letra(texto, self._letras))
				if ayuda:
					control.SetHelpText(ayuda)
				caja.Add(control, 0, wx.ALL, 4)
				casillas.append(control)
			sizer.Add(caja, 0, wx.EXPAND | wx.ALL, 6)
			self.controles[elemento.clave] = casillas
			return
		sizer.Add(wx.StaticText(panel, label=self._etiqueta(elemento)), 0, wx.LEFT | wx.TOP, 6)
		if elemento.tipo == "input":
			control = wx.TextCtrl(panel, value=elemento.valor)
			if elemento.marcador:
				control.SetHint(elemento.marcador)
		elif elemento.tipo == "textarea":
			control = wx.TextCtrl(panel, value=elemento.valor, style=wx.TE_MULTILINE, size=(-1, self.FromDIP(110)))
		elif elemento.multiple:
			nombre = (elemento.etiqueta or elemento.clave).replace("&", "")
			control = ListaCasillas(panel, nombre, elemento.opciones, config=getattr(self.ctx, "config", None),
				size=(-1, self.FromDIP(min(160, 30 + 22 * len(elemento.opciones)))))
			if elemento.por_defecto is not None:
				wx.CheckListBox.Check(control, elemento.por_defecto, True)
			ayuda = " ".join(p for p in (ayuda, texto_ayuda(control)) if p)
		else:
			# Primera opción vacía: GitHub tampoco elige nada si el formulario no da «default».
			vacia = _("(sin elegir)") if elemento.obligatorio else _("(ninguna)")
			control = wx.Choice(panel, choices=[vacia, *elemento.opciones])
			control.SetSelection(elemento.por_defecto + 1 if elemento.por_defecto is not None else 0)
		if ayuda:
			control.SetHelpText(ayuda)
		sizer.Add(control, 1 if elemento.tipo == "textarea" else 0, wx.EXPAND | wx.ALL, 6)
		self.controles[elemento.clave] = control

	# ── Valores ───────────────────────────────────────────────────────────────

	def respuestas(self) -> dict[str, Any]:
		"""Respuestas por ``Elemento.clave`` en el formato de ``plantillas.componer_cuerpo``."""
		resultado: dict[str, Any] = {}
		for elemento in self.plantilla.preguntas:
			control = self.controles.get(elemento.clave)
			if control is None:
				continue
			if elemento.tipo == "checkboxes":
				resultado[elemento.clave] = [c.GetValue() for c in control]
			elif elemento.tipo == "dropdown" and elemento.multiple:
				resultado[elemento.clave] = [elemento.opciones[i] for i in control.GetCheckedItems()]
			elif elemento.tipo == "dropdown":
				indice = control.GetSelection()
				resultado[elemento.clave] = [elemento.opciones[indice - 1]] if indice > 0 else []
			else:
				resultado[elemento.clave] = control.GetValue()
		return resultado

	def cuerpo(self) -> str:
		return pl.componer_cuerpo(self.plantilla, self.respuestas())

	def _instantanea(self) -> tuple[str, str]:
		return self.campo_titulo.GetValue(), repr(self.respuestas())

	def modificado(self) -> bool:
		return self._instantanea() != self._inicial

	def control_de(self, falta: pl.Falta) -> wx.Window | None:
		"""Control donde hay que escribir o marcar lo que falta."""
		control = self.controles.get(falta.elemento.clave)
		if isinstance(control, list):
			return control[falta.opcion] if 0 <= falta.opcion < len(control) else (control[0] if control else None)
		return control

	# ── Acciones ──────────────────────────────────────────────────────────────

	def vista_previa(self) -> None:
		from app.ui import visor_ayuda

		titulo = self.campo_titulo.GetValue().strip() or self.plantilla.nombre
		visor_ayuda.mostrar_documento(self, _("Vista previa: {t}").format(t=titulo), self.cuerpo())

	def enviar(self) -> None:
		"""Comprueba título y obligatorios y crea la issue en segundo plano (el diálogo sigue abierto si falla)."""
		if self._enviando:
			self.ctx.avisar(_("Espere a que termine el envío."))
			return
		titulo = self.campo_titulo.GetValue().strip()
		if not titulo:
			mostrar_error(self, _("Escriba un título."), _("Falta el título"))
			# Respuesta a «Crear»: aquí sí se lleva el foco al campo que falta.
			foco_ui.enfocar(self.campo_titulo)
			self.campo_titulo.SetInsertionPointEnd()
			return
		faltas = pl.faltan_obligatorios(self.plantilla, self.respuestas())
		if faltas:
			mostrar_error(self, pl.describir_faltas(faltas), _("Faltan campos obligatorios"))
			foco_ui.enfocar(self.control_de(faltas[0]))
			return
		valores = {"titulo": titulo, "cuerpo": self.cuerpo()}
		destino = self.idioma_envio
		self.ctx.config.establecer("traduccion.destino_envio", destino)
		if destino:
			# Escribir en un idioma y crear la issue en otro (incidencia #13): se revisa antes de enviar.
			from app.ui.traductor import revisar_y_enviar

			self._enviando = True
			self.boton_crear.Disable()

			def con_traduccion(titulo_traducido: str | None, cuerpo: str) -> None:
				self._enviando = False
				self._crear({"titulo": titulo_traducido or titulo, "cuerpo": cuerpo})

			def volver() -> None:
				self._enviando = False
				if self:
					self.boton_crear.Enable()

			revisar_y_enviar(self, self.ctx, titulo, valores["cuerpo"], destino, con_traduccion, volver)
			return
		self._crear(valores)

	@property
	def idioma_envio(self) -> str:
		return self._codigos_traduccion[max(0, self.selector_traduccion.GetSelection())]

	def _crear(self, valores: dict) -> None:
		self._enviando = True
		self.boton_crear.Disable()
		self.estado.SetLabel(_("Creando la issue…"))
		self.ctx.avisar(_("Creando la issue…"))

		def al_terminar(resultado: Any) -> None:
			self._enviando = False
			self.resultado = resultado
			self.ctx.sonar("enviado")
			if self.IsModal():
				self.EndModal(wx.ID_OK)
			else:
				self.Destroy()
			if self._al_enviar:
				self._al_enviar(resultado)

		def al_fallar(error: BaseException) -> None:
			if not self:
				return
			self._enviando = False
			self.boton_crear.Enable()
			self.estado.SetLabel("")
			self.ctx.sonar("error")
			mostrar_error(self, mensaje_error(error), _("No se pudo crear la issue"))

		self.ctx.tareas.enviar(lambda _tarea: self._enviar(valores), al_terminar=al_terminar, al_fallar=al_fallar,
			nombre="formulario_issue:enviar", duplicadas="permitir")

	def _puede_cerrar(self) -> bool:
		if self._enviando:
			self.ctx.avisar(_("Espere a que termine el envío."))
			return False
		if not self.modificado():
			return True
		return confirmar(self, _("¿Descartar lo escrito en el formulario?"), _("Descartar cambios"), peligroso=True) == wx.ID_YES

	def cancelar(self) -> None:
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

	def _al_iniciar(self, evento: wx.InitDialogEvent) -> None:
		if foco_ui.enfocar(self.campo_titulo):
			self.campo_titulo.SetInsertionPointEnd()
		evento.Skip()

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla = evento.GetKeyCode()
		if tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and evento.ControlDown():
			self.enviar()
			return
		if tecla == wx.WXK_F7 and not evento.HasAnyModifiers():
			self.vista_previa()
			return
		if tecla == wx.WXK_ESCAPE and not evento.HasAnyModifiers() and not desplegable_abierto(wx.Window.FindFocus()):
			# Escape pasa por la misma pregunta que «Cancelar»: no se pierde lo escrito sin querer.
			self.cancelar()
			return
		evento.Skip()


def abrir_formulario(padre: wx.Window | None, contexto: Any, titulo_ventana: str, plantilla: pl.Plantilla,
	enviar: Callable[[dict], Any], al_enviar: Callable[[Any], None] | None = None) -> Any:
	"""Abre el formulario de forma modal. Devuelve el resultado del envío o ``None`` si se canceló."""
	dialogo = DialogoFormularioIssue(padre, contexto, titulo_ventana, plantilla, enviar, al_enviar)
	try:
		respuesta = dialogo.ShowModal()
		return dialogo.resultado if respuesta == wx.ID_OK and dialogo else None
	finally:
		if dialogo:
			dialogo.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Flujo «Nueva issue»
# ════════════════════════════════════════════════════════════════════════════


def nueva_issue(padre: wx.Window, contexto: Any, repositorio: str, al_crear: Callable[[dict], None] | None = None) -> None:
	"""Crea una issue en ``repositorio`` con sus plantillas y formularios.

	:param al_crear: se llama con la issue creada (para recargar la lista, anunciarla...).
	"""
	api = contexto.api()

	def cargar() -> tuple[list[pl.Plantilla], list[str], pl.ConfigIssues]:
		archivos, config = api.leer_plantillas_issue(repositorio)
		plantillas, errores = pl.leer_plantillas(archivos)
		return plantillas, errores, pl.leer_config(config)

	def creada(resultado: Any) -> None:
		issue, descartados = resultado if isinstance(resultado, tuple) else (resultado, [])
		if al_crear and isinstance(issue, dict):
			al_crear(issue)
		if descartados:
			mostrar_mensaje(padre, pl.describir_descartados(descartados), _("Issue creada sin todo lo de la plantilla"),
				icono=wx.ICON_WARNING)

	def crear(valores: dict, plantilla: pl.Plantilla | None) -> Any:
		if plantilla is None:
			return api.crear_issue_con_plantilla(repositorio, valores["titulo"], valores["cuerpo"])
		return api.crear_issue_con_plantilla(repositorio, valores["titulo"], valores["cuerpo"], plantilla.etiquetas,
			plantilla.asignados, plantilla.tipo)

	def en_blanco() -> None:
		from app.ui.editor import editar

		editar(padre, contexto, _("Nueva issue en {n}").format(n=repositorio), lambda v: crear(v, None), con_titulo=True,
			al_enviar=creada, con_adjuntos=True)

	def con_plantilla(plantilla: pl.Plantilla) -> None:
		titulo_ventana = _("Nueva issue en {n}: {p}").format(n=repositorio, p=plantilla.nombre)
		if plantilla.formulario:
			abrir_formulario(padre, contexto, titulo_ventana, plantilla, lambda v: crear(v, plantilla), al_enviar=creada)
			return
		from app.ui.editor import editar

		editar(padre, contexto, titulo_ventana, lambda v: crear(v, plantilla), con_titulo=True, titulo=plantilla.titulo,
			cuerpo=plantilla.cuerpo, al_enviar=creada, con_adjuntos=True,
			clave_borrador=f"editor:issue:{repositorio.lower()}:{plantilla.archivo}")

	def contacto(enlace: pl.EnlaceContacto) -> None:
		abrir_url(enlace.url)
		contexto.avisar(_("Abriendo «{n}» en el navegador.").format(n=enlace.nombre))

	def elegir(datos: tuple[list[pl.Plantilla], list[str], pl.ConfigIssues]) -> None:
		plantillas, errores, config = datos
		if not plantillas:
			if errores:
				mostrar_error(padre, "\n\n".join(errores) + "\n\n" + _("Se abre una issue en blanco."),
					_("Plantillas de issue con errores"))
			en_blanco()
			return
		opciones: list[tuple[str, Callable[[], None]]] = [
			(pl.describir_plantilla(p), lambda p=p: con_plantilla(p)) for p in plantillas]
		if config.en_blanco:
			opciones.append((_("Issue en blanco: sin plantilla"), en_blanco))
		for enlace in config.enlaces:
			texto = _("{n} (abre el navegador)").format(n=enlace.nombre)
			opciones.append((f"{texto}: {enlace.descripcion}" if enlace.descripcion else texto, lambda e=enlace: contacto(e)))
		ayuda = _("Plantillas y formularios del repositorio. Los formularios piden cada dato en su campo; "
			"los enlaces llevan a otros sitios (foros, avisos de seguridad).")
		if errores:
			ayuda += " " + _("No se han podido leer: {e}").format(e=" ".join(errores))
		eleccion = elegir_uno(padre, _("Nueva issue en {n}").format(n=repositorio), _("&Plantilla para la issue:"),
			[texto for texto, _accion in opciones], ayuda=ayuda)
		if eleccion is not None:
			opciones[eleccion][1]()

	def sin_plantillas(error: BaseException) -> None:
		log.warning("No se pudieron cargar las plantillas de issue de %s: %s", repositorio, mensaje_error(error))
		en_blanco()

	en_segundo_plano(padre, contexto, cargar, al_terminar=elegir, al_fallar=sin_plantillas, sonido="",
		inicio=_("Cargando las plantillas…"))
