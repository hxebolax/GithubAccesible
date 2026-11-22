"""Ayuda contextual con Ctrl+H: «¿qué es y para qué sirve el control enfocado?».

- ``describir_control_enfocado``: anuncia el nombre y la ayuda del control con
  el foco. El nombre sale del ``name=`` propio; si es genérico de wx
  («text», «button»...), de su etiqueta visible; y si no tiene, de la
  ``StaticText`` anterior entre sus hermanos (la misma heurística que usan
  los lectores de pantalla).
- ``ayuda_efectiva``: la ayuda propia (``SetHelpText``), la del padre (campo
  interno de un selector), el tooltip o, como último recurso, una ayuda
  genérica según el tipo de control (y, en botones, según su etiqueta).
- ``asegurar_ayudas``: rellena la ayuda de los controles que no la tengan,
  sin pisar las escritas a mano.

- ``ProveedorAyuda``: guarda las ayudas y decide cuáles ve el lector de pantalla.
  wxPython 4.3 entrega la ayuda de ``SetHelpText`` al lector como «descripción»
  del control (botones, casillas) y, en las listas de casillas, de CADA fila,
  que el lector repite al moverse. Con ``accesibilidad.explicacion_controles`` y
  ``accesibilidad.explicacion_filas`` la persona elige si quiere oírlas; Control+H
  usa ``texto_ayuda`` y la dice siempre.

Requisito: instalar un proveedor al arrancar (``instalar_proveedor_ayuda``); sin
él, ``SetHelpText`` no guarda nada.

PLANTILLA del agente «accesibilidad-wx».
"""

from __future__ import annotations

import builtins
import unicodedata

import wx
import wx.adv

import app.core.i18n  # noqa: F401 - instala N_ en builtins antes de usarlo al importar
from app.ui.accesibilidad import voz


def _(texto: str) -> str:
	"""Traduce con gettext si está instalado en builtins; si no, devuelve el texto."""
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# Nombres que wx pone por defecto y que no dicen nada al usuario.
_NOMBRES_GENERICOS = {
	"", "check", "checkbox", "button", "text", "textctrl", "choice", "combobox", "combo", "listctrl",
	"listbox", "list", "panel", "statictext", "slider", "radiobutton", "radiobox", "notebook", "treectrl",
	"spinctrl", "wxspinctrl", "toggle", "groupbox", "scrolledpanel", "dialog", "frame", "gauge",
	"datectrl", "timectrl", "filepicker", "dirpicker", "htmlwindow", "grid", "staticbitmap",
}

# Ayuda por palabra clave de la etiqueta de un botón (lo más específico primero).
# Las palabras clave se comparan con etiquetas en español y no se traducen; la
# ayuda sí (N_ aquí, _() al devolverla en ``_ayuda_por_etiqueta``).
_AYUDA_POR_ETIQUETA: tuple[tuple[tuple[str, ...], str], ...] = (
	(("seleccionar todo", "marcar todo", "marcar todas", "marcar todos"), N_("Marca todos los elementos de la lista.")),
	(("desmarcar", "ninguno", "ninguna"), N_("Desmarca todos los elementos de la lista.")),
	(("examinar", "seleccionar...", "elegir"), N_("Abre un cuadro para elegir un archivo o una carpeta.")),
	(("vista previa", "previsualizar"), N_("Muestra una vista previa antes de aplicar los cambios.")),
	(("restablecer", "restaurar"), N_("Vuelve a los valores de fábrica.")),
	(("comprobar", "probar", "verificar", "detectar"), N_("Comprueba el estado y muestra el resultado, sin cambiar nada.")),
	(("actualizar", "refrescar", "recargar"), N_("Vuelve a cargar la información más reciente.")),
	(("copiar",), N_("Copia la información al portapapeles.")),
	(("exportar",), N_("Guarda la información en un archivo.")),
	(("importar",), N_("Carga información desde un archivo.")),
	(("abrir carpeta", "abrir la carpeta"), N_("Abre la carpeta en el Explorador de Windows.")),
	(("abrir",), N_("Abre el elemento seleccionado.")),
	(("detalles", "propiedades", "ficha"), N_("Muestra la información completa del elemento seleccionado.")),
	(("agregar", "añadir", "nuevo", "nueva"), N_("Crea un elemento nuevo.")),
	(("editar", "modificar"), N_("Edita el elemento seleccionado.")),
	(("eliminar", "borrar", "quitar"), N_("Elimina el elemento seleccionado; pide confirmación.")),
	(("buscar",), N_("Busca con el texto y los filtros indicados.")),
	(("guardar", "aplicar"), N_("Guarda los cambios realizados.")),
	(("aceptar",), N_("Acepta los cambios y cierra la ventana.")),
	(("cancelar",), N_("Cierra la ventana sin guardar los cambios.")),
	(("cerrar",), N_("Cierra esta ventana.")),
	(("ayuda",), N_("Muestra la ayuda.")),
)


def _normalizar(texto: str) -> str:
	"""Minúsculas, sin «&», sin acentos y sin puntos suspensivos."""
	limpio = texto.replace("&", "").replace("…", "").replace("...", "").strip().lower()
	return "".join(c for c in unicodedata.normalize("NFD", limpio) if unicodedata.category(c) != "Mn")


def _ayuda_por_etiqueta(control: wx.Window) -> str:
	etiqueta = _normalizar(control.GetLabel())
	for claves, ayuda in _AYUDA_POR_ETIQUETA:
		if any(_normalizar(clave) in etiqueta for clave in claves):
			return _(ayuda)
	return ""


def ayuda_generica(control: wx.Window) -> str:
	"""Ayuda de reserva según el tipo de control (el orden importa: subclases primero)."""
	if isinstance(control, wx.Button):
		return _ayuda_por_etiqueta(control) or _("Botón. Actívelo con la barra espaciadora o Intro.")
	if isinstance(control, wx.CheckListBox):
		return _("Lista de casillas. Muévase con las flechas y marque o desmarque con la barra espaciadora.")
	if isinstance(control, wx.CheckBox):
		return _("Casilla de verificación. Márquela o desmárquela con la barra espaciadora.")
	if isinstance(control, wx.RadioButton):
		return _("Botón de opción. Elija entre las opciones del grupo con las flechas.")
	if isinstance(control, (wx.SpinCtrl, wx.SpinCtrlDouble)):
		return _("Campo numérico. Escriba un número o cámbielo con las flechas arriba y abajo.")
	if isinstance(control, (wx.Choice, wx.ComboBox)):
		return _("Lista desplegable. Ábrala con Alt+flecha abajo y elija con las flechas.")
	if isinstance(control, wx.TextCtrl):
		if not control.IsEditable():
			return _("Texto de solo lectura. Recórralo con las flechas y cópielo si lo necesita.")
		return _("Campo de texto. Escriba aquí el valor.")
	if isinstance(control, wx.ListCtrl):
		return _(
			"Lista. Arriba y abajo cambian de elemento; izquierda y derecha recorren las columnas; "
			"Control más un número lee esa columna; Intro abre el elemento."
		)
	if isinstance(control, wx.ListBox):
		return _("Lista de opciones. Elija con las flechas.")
	if isinstance(control, wx.TreeCtrl):
		return _("Árbol. Muévase con las flechas; derecha despliega una rama e izquierda la pliega.")
	if isinstance(control, (wx.DirPickerCtrl, wx.FilePickerCtrl)):
		return _("Selector de ruta. Escriba la ruta o use el botón Seleccionar.")
	if isinstance(control, wx.adv.DatePickerCtrl):
		return _("Selector de fecha. Cambie día, mes y año con las flechas.")
	if isinstance(control, wx.adv.TimePickerCtrl):
		return _("Selector de hora. Cambie horas y minutos con las flechas.")
	if isinstance(control, wx.Slider):
		return _("Control deslizante. Cambie el valor con las flechas; Re Pág y Av Pág dan saltos mayores.")
	if isinstance(control, wx.Gauge):
		return _("Barra de progreso. Indica cuánto se ha completado.")
	if isinstance(control, wx.Notebook):
		return _("Pestañas. Cambie de pestaña con Control+Tab o con las flechas.")
	return ""


class ProveedorAyuda(wx.SimpleHelpProvider):
	"""Guarda las ayudas de ``SetHelpText`` y filtra las que llegan al lector de pantalla.

	``GetHelp`` es lo que consulta wx para la «descripción» accesible (y también
	``GetHelpText``): devuelve la ayuda solo si la preferencia lo permite. El texto
	completo, para Control+H, se obtiene siempre con ``texto_ayuda``.

	:param config: objeto con ``obtener(clave, defecto)``; sin él, no se filtra nada.
	"""

	def __init__(self, config: object | None = None) -> None:
		super().__init__()
		self.config = config

	def _permitida(self, ventana: wx.Window) -> bool:
		if self.config is None:
			return True
		if isinstance(ventana, wx.CheckListBox):
			return bool(self.config.obtener("accesibilidad.explicacion_filas", False))
		return bool(self.config.obtener("accesibilidad.explicacion_controles", True))

	def GetHelp(self, ventana: wx.Window) -> str:  # noqa: N802 - API de wx
		if ventana is None or self._permitida(ventana):
			return wx.SimpleHelpProvider.GetHelp(self, ventana)
		return ""

	def texto_completo(self, ventana: wx.Window) -> str:
		return wx.SimpleHelpProvider.GetHelp(self, ventana)


_proveedor: ProveedorAyuda | None = None


def instalar_proveedor_ayuda(config: object | None = None) -> ProveedorAyuda:
	"""Instala (una vez) el proveedor de ayudas; con ``config``, aplica sus preferencias."""
	global _proveedor
	if _proveedor is None:
		_proveedor = ProveedorAyuda(config)
		wx.HelpProvider.Set(_proveedor)
	elif config is not None:
		_proveedor.config = config
	return _proveedor


def texto_ayuda(control: wx.Window | None) -> str:
	"""La ayuda escrita con ``SetHelpText``, aunque no se entregue al lector (para Control+H)."""
	if not control:
		return ""
	proveedor = wx.HelpProvider.Get()
	if isinstance(proveedor, ProveedorAyuda):
		return proveedor.texto_completo(control) or ""
	return control.GetHelpText() or ""


def ayuda_efectiva(control: wx.Window) -> str:
	"""La ayuda más específica disponible para ``control``."""
	ayuda = (getattr(control, "ayuda_texto", "") or "").strip()
	if not ayuda:
		ayuda = texto_ayuda(control).strip()
	if not ayuda:
		padre = control.GetParent()
		if padre is not None and isinstance(padre, (wx.DirPickerCtrl, wx.FilePickerCtrl, wx.SpinCtrl)):
			ayuda = texto_ayuda(padre).strip()
	if not ayuda:
		consejo = control.GetToolTip()
		ayuda = (consejo.GetTip() if consejo else "").strip()
	return ayuda or ayuda_generica(control)


def nombre_para_anunciar(control: wx.Window) -> str:
	"""Nombre del control tal y como lo presentaría un lector de pantalla."""
	nombre = (control.GetName() or "").strip()
	if nombre.lower() in _NOMBRES_GENERICOS:
		nombre = (control.GetLabel() or "").replace("&", "").strip()
	if nombre.lower() in _NOMBRES_GENERICOS and control.GetParent() is not None:
		hermanos = list(control.GetParent().GetChildren())
		if control in hermanos:
			for previo in reversed(hermanos[: hermanos.index(control)]):
				if isinstance(previo, wx.StaticText):
					nombre = previo.GetLabel().replace("&", "").strip().rstrip(":")
					break
	return "" if nombre.lower() in _NOMBRES_GENERICOS else nombre


def describir_control_enfocado(ventana: wx.Window | None = None) -> None:
	"""Acción de Ctrl+H: dice el nombre y la ayuda del control con el foco."""
	control = wx.Window.FindFocus()
	if control is None:
		_decir(_("No hay ningún control con el foco."), ventana)
		return
	nombre = nombre_para_anunciar(control) or _("Este control")
	ayuda = ayuda_efectiva(control)
	if ayuda:
		_decir(_("{nombre}. {ayuda}").format(nombre=nombre, ayuda=ayuda), ventana)
	else:
		_decir(_("{nombre}. No hay ayuda para este control.").format(nombre=nombre), ventana)


def _decir(texto: str, ventana: wx.Window | None) -> None:
	"""Lo dice o, con la voz de Windows apagada y sin lector, lo enseña en un cuadro."""
	if voz.sin_voz_por_no_haber_lector():
		from app.ui.accesibilidad.dialogos import mostrar_mensaje

		mostrar_mensaje(ventana, texto, _("Ayuda"))
		return
	voz.hablar(texto, canal=voz.NAVEGACION)


_INTERACTIVOS = (
	wx.TextCtrl, wx.Choice, wx.ComboBox, wx.SpinCtrl, wx.SpinCtrlDouble, wx.CheckBox, wx.RadioButton,
	wx.ListBox, wx.ListCtrl, wx.TreeCtrl, wx.Slider, wx.Button, wx.DirPickerCtrl, wx.FilePickerCtrl,
	wx.adv.DatePickerCtrl, wx.adv.TimePickerCtrl, wx.Notebook,
)


def _descendientes(ventana: wx.Window):
	for hijo in ventana.GetChildren():
		yield hijo
		yield from _descendientes(hijo)


def asegurar_ayudas(ventana: wx.Window) -> None:
	"""Pone ayuda genérica a los controles interactivos que no tengan ninguna."""
	for control in _descendientes(ventana):
		if isinstance(control, _INTERACTIVOS) and not texto_ayuda(control):
			generica = ayuda_generica(control)
			if generica:
				control.SetHelpText(generica)


def habilitar_ayuda_contextual(ventana: wx.Window) -> None:
	"""Instala Ctrl+H en una ventana principal (en diálogos lo hace ``preparar_dialogo``)."""

	def al_pulsar(evento: wx.KeyEvent) -> None:
		if evento.GetModifiers() == wx.MOD_CONTROL and evento.GetKeyCode() == ord("H"):
			describir_control_enfocado(ventana)
			return
		evento.Skip()

	ventana.Bind(wx.EVT_CHAR_HOOK, al_pulsar)
