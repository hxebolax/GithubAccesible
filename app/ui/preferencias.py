"""Preferencias de GitHub Accesible (diálogo del agente de configuración, ampliado).

Además de las páginas declarativas, tiene dos páginas propias, como en SocialRSS:

- **Sonidos**: activar, silenciar, volumen, paquete y una lista de casillas
  con cada evento (marcado = suena) y un botón para probar el sonido.
- **Columnas de las listas**: para cada lista de la aplicación, qué columnas
  se ven y en qué orden (y por tanto qué y en qué orden lee el lector al
  moverse por las filas y por las columnas).

Todo se aplica al momento en las ventanas abiertas (las listas se suscriben a
la configuración) y Cancelar no guarda nada.
"""

from __future__ import annotations

import builtins
import logging
from typing import Any

import wx

from app.services import sonidos as sonidos_servicio
from app.ui.comunes import ListaCasillas
from app.ui.dialogo_preferencias import (
	BOOL,
	CARPETA,
	ENTERO,
	OPCION,
	TEXTO,
	DialogoPreferencias,
	Opcion,
	Pagina,
)

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def N_(texto: str) -> str:  # noqa: N802
	return texto


TITULO_SONIDOS = N_("Sonidos")
TITULO_COLUMNAS = N_("Columnas de las listas")


def paginas(paquetes: list[str]) -> tuple[Pagina, ...]:
	"""Páginas declarativas. Las letras de acceso no repiten dentro de cada página ni usan
	A, C, P ni R (botones Aceptar, Cancelar, Aplicar y Restablecer)."""
	return (
		Pagina(N_("General"), (
			Opcion("general.seccion_inicial", N_("&Sección al abrir:"), OPCION,
				N_("Qué sección se muestra al abrir la aplicación."),
				opciones=(("notificaciones", N_("Notificaciones")), ("inicio", N_("Inicio")), ("repositorios", N_("Mis repositorios")),
					("issues", N_("Mis issues")), ("prs", N_("Mis pull requests")), ("locales", N_("Repositorios locales")))),
			Opcion("general.anunciar_arranque", N_("Anunciar el arranque por &voz"), BOOL,
				N_("Dice «Iniciando GitHub Accesible» mientras se carga.")),
			Opcion("general.minimizar_a_bandeja", N_("&Minimizar a la bandeja del sistema"), BOOL,
				N_("Al minimizar, la ventana se oculta y queda un icono junto al reloj.")),
			Opcion("general.iniciar_en_bandeja", N_("&Iniciar oculta en la bandeja"), BOOL,
				N_("Al arrancar, la ventana queda en la bandeja del sistema (útil para recibir notificaciones).")),
			Opcion("general.confirmar_salida", N_("Con&firmar antes de salir"), BOOL,
				N_("Pregunta antes de cerrar la aplicación.")),
			Opcion("general.carpeta_descargas", N_("Carpeta de &descargas:"), CARPETA,
				N_("Dónde se guardan las descargas (releases, artefactos, archivos). Vacío: preguntar cada vez.")),
		)),
		Pagina(N_("Actualizaciones"), (
			Opcion("general.buscar_actualizaciones", N_("&Buscar actualizaciones al arrancar y una vez al día"), BOOL,
				N_("Comprueba si hay una versión nueva al abrir la aplicación y después cada 24 horas.")),
			Opcion("actualizaciones.origen", N_("&Origen de las actualizaciones:"), OPCION,
				N_("De dónde se descargan las versiones nuevas. Todas van firmadas: una versión que no lleve la firma del autor se rechaza."),
				opciones=(("ambos", N_("Servidor del autor y, si no responde, GitHub")), ("servidor", N_("Solo el servidor del autor")),
					("github", N_("Solo las releases de GitHub")), ("personalizada", N_("Una dirección personalizada")))),
			Opcion("actualizaciones.url_personalizada", N_("&Dirección personalizada del version.json:"), TEXTO,
				N_("Solo con el origen «Una dirección personalizada». Debe ser https y apuntar a un version.json firmado.")),
		)),
		Pagina(N_("Cuentas"), (
			Opcion("cuentas.id_cliente_oauth", N_("&Identificador de la aplicación OAuth (Client ID):"), TEXTO,
				N_("Necesario para iniciar sesión con el navegador. Regístrelo una vez en GitHub, Settings, Developer settings, "
					"OAuth Apps, con «Enable Device Flow» marcado. Es un dato público (no es una contraseña).")),
			Opcion("cuentas.ambitos", N_("Á&mbitos que se piden por defecto:"), OPCION,
				N_("Permisos que se piden al iniciar sesión con el navegador."),
				opciones=(("completos", N_("Completos")), ("basicos", N_("Básicos")))),
		)),
		Pagina(N_("Accesibilidad"), (
			Opcion("accesibilidad.avisos_voz", N_("Anunciar los a&visos por voz"), BOOL,
				N_("Dice por el lector los avisos breves: listas cargadas, acciones terminadas, errores.")),
			Opcion("accesibilidad.retardo_voz_ms", N_("Retar&do de los avisos (milisegundos):"), ENTERO,
				N_("Espera antes de hablar para no pisar lo que el lector anuncia al mover el foco.")),
			Opcion("accesibilidad.braille", N_("Enviar los avisos también a la línea &braille"), BOOL,
				N_("Muestra en la línea braille el mismo texto de los avisos.")),
			Opcion("accesibilidad.anunciar_total", N_("Decir el número de &elementos al cargar una lista"), BOOL,
				N_("Al terminar de cargar, anuncia cuántos elementos hay.")),
			Opcion("accesibilidad.leer_numero_fila", N_("Columnas: decir el &número de fila"), BOOL,
				N_("Al recorrer las columnas con izquierda y derecha, dice «Fila 3». Si desactiva las tres, se dice igualmente el contenido.")),
			Opcion("accesibilidad.leer_cabecera", N_("Columnas: decir el nombre de la col&umna"), BOOL,
				N_("Al recorrer las columnas, dice su nombre (Estado, Autor...).")),
			Opcion("accesibilidad.leer_contenido", N_("Columnas: decir el con&tenido de la celda"), BOOL,
				N_("Al recorrer las columnas, dice su contenido.")),
			Opcion("accesibilidad.casillas_decir_estado", N_("Casillas: anunciar el estado al marcar o des&marcar"), BOOL,
				N_("En las listas de casillas, dice «marcada» o «no marcada» al pulsar Espacio. Desactívelo si su lector ya lo dice dos veces.")),
			Opcion("accesibilidad.casillas_estado_primero", N_("Casillas: decir el estado antes del te&xto"), BOOL,
				N_("Dice «marcada, Etiqueta» en lugar de «Etiqueta, marcada».")),
			Opcion("accesibilidad.casillas_decir_posicion", N_("Casillas: decir la posición (&3 de 10)"), BOOL,
				N_("Añade «3 de 10» al anuncio de la casilla.")),
			Opcion("accesibilidad.diff_decir_tipo", N_("Diferencias: mostrar la columna del t&ipo de línea"), BOOL,
				N_("Columna «Añadida», «Eliminada» o «Sin cambios» en el visor de diferencias (el lector la lee al moverse).")),
			Opcion("accesibilidad.diff_decir_numero", N_("Diferencias: mostrar el número de &línea"), BOOL,
				N_("Columna con el número de línea del archivo en el visor de diferencias.")),
			Opcion("accesibilidad.diff_sonidos", N_("Diferencias: s&onido según el tipo de línea"), BOOL,
				N_("Un sonido distinto al llegar a una línea añadida, eliminada o a un bloque.")),
			Opcion("accesibilidad.usar_html", N_("Mostrar README, manual y textos largos con formato (&HTML)"), BOOL,
				N_("Con formato se navega por encabezados, listas y tablas en modo exploración. Sin él, se usa texto plano.")),
		)),
		Pagina(TITULO_SONIDOS, (
			Opcion("sonidos.activados", N_("Activar los &sonidos"), BOOL, N_("Sonidos de la aplicación para los eventos de la lista de debajo.")),
			Opcion("sonidos.silencio", N_("Si&lenciar temporalmente"), BOOL, N_("Sin sonidos, pero conservando la configuración.")),
			Opcion("sonidos.volumen", N_("&Volumen (0 a 100):"), ENTERO, N_("Volumen de los sonidos. Se aplica al momento.")),
			Opcion("sonidos.paquete", N_("Pa&quete de sonidos:"), OPCION,
				N_("Carpeta de data/sounds con los sonidos. Los que falten se toman del predeterminado."),
				opciones=tuple((p, p) for p in paquetes)),
		)),
		Pagina(N_("Listas"), (
			Opcion("listas.por_pagina", N_("&Elementos por página al cargar (10 a 100):"), ENTERO,
				N_("Cuántos elementos se piden cada vez. Al llegar al final de la lista se cargan más.")),
			Opcion("listas.fechas_relativas", N_("&Fechas relativas («hace 3 días»)"), BOOL,
				N_("Desactivado muestra la fecha y la hora completas.")),
		)),
		Pagina(N_("Notificaciones"), (
			Opcion("notificaciones.comprobar", N_("C&omprobar notificaciones nuevas en segundo plano"), BOOL,
				N_("Mira cada cierto tiempo si hay notificaciones nuevas y avisa.")),
			Opcion("notificaciones.intervalo_s", N_("&Intervalo en segundos (mínimo 30):"), ENTERO,
				N_("GitHub puede pedir un intervalo mayor; se respeta siempre el suyo.")),
			Opcion("notificaciones.solo_participando", N_("&Solo las de conversaciones en las que participo"), BOOL,
				N_("Ignora las notificaciones de repositorios que solo vigila.")),
			Opcion("notificaciones.voz", N_("Anunciar por &voz las notificaciones nuevas"), BOOL, N_("Lee el título de las nuevas.")),
			Opcion("notificaciones.sonido", N_("So&nido al llegar notificaciones nuevas"), BOOL, N_("Un sonido distinto si le mencionan o le piden revisión.")),
			Opcion("notificaciones.notificacion_windows", N_("Mostrar también una notificación de &Windows"), BOOL,
				N_("Aviso emergente del sistema, útil con la aplicación en la bandeja.")),
			Opcion("notificaciones.marcar_leida_al_abrir", N_("&Marcar como leída al abrir una notificación"), BOOL,
				N_("Al pulsar Intro sobre una notificación, se marca como leída en GitHub.")),
		)),
		Pagina(N_("Git"), (
			Opcion("git.ruta", N_("Ruta de &git.exe (vacío: detectar):"), TEXTO,
				N_("Normalmente se encuentra solo. Indíquela si instaló Git en un sitio poco habitual.")),
			Opcion("git.usar_token", N_("Usar el &token de la cuenta para clonar, traer y enviar por HTTPS"), BOOL,
				N_("El token se pasa a git solo durante la operación, sin guardarlo en disco. Desactívelo para usar sus propias credenciales de Git.")),
			Opcion("git.carpeta_clonado", N_("Carpeta para c&lonar repositorios:"), CARPETA,
				N_("Carpeta donde se proponen los clones nuevos.")),
			Opcion("git.tirar_con_reorganizacion", N_("Al traer cambios (pull), r&eorganizar en lugar de fusionar"), BOOL,
				N_("Equivale a git pull --rebase.")),
			Opcion("git.firmar_commits", N_("&Firmar los commits"), BOOL, N_("Equivale a git commit -S. Requiere tener configurada una clave GPG o SSH de firma.")),
		)),
		Pagina(N_("Editor"), (
			Opcion("editor.confirmar_descartar", N_("Confirmar antes de &descartar un texto escrito"), BOOL,
				N_("Al cerrar el editor con texto sin enviar, pregunta antes de perderlo.")),
			Opcion("editor.firma", N_("&Firma que se añade al final de los comentarios:"), TEXTO,
				N_("Opcional. Se añade al final de cada comentario nuevo.")),
		)),
		Pagina(N_("Red y registro"), (
			Opcion("red.proxy", N_("Pro&xy («sistema», «ninguno» o una dirección):"), TEXTO,
				N_("«sistema» usa la configuración de Windows; «ninguno» conecta directamente; o escriba http://servidor:puerto.")),
			Opcion("red.tiempo_espera_s", N_("&Tiempo máximo de espera (segundos):"), ENTERO, N_("Tiempo de espera de las peticiones a GitHub.")),
			Opcion("registro.nivel", N_("&Nivel del registro de errores:"), OPCION,
				N_("DEBUG guarda mucho detalle para diagnosticar problemas."),
				opciones=(("INFO", N_("Normal")), ("DEBUG", N_("Detallado (depuración)")), ("WARNING", N_("Solo avisos")), ("ERROR", N_("Solo errores")))),
		)),
	)


class DialogoPreferenciasGitHub(DialogoPreferencias):
	"""Diálogo de preferencias con las páginas propias de sonidos y columnas."""

	def __init__(self, padre: wx.Window | None, ctx: Any, vistas: list[Any] | None = None) -> None:
		self.ctx = ctx
		self._vistas = vistas or []
		self._sonidos = ctx.sonidos
		paquetes = self._sonidos.paquetes() if self._sonidos is not None and hasattr(self._sonidos, "paquetes") else [sonidos_servicio.PAQUETE_PREDETERMINADO]
		self._eventos = list(sonidos_servicio.EVENTOS)
		self._columnas_elegidas: dict[str, list[str]] = dict(ctx.config.obtener("listas.columnas", {}) or {})
		super().__init__(padre, ctx.config, paginas(paquetes), secretos=None, anunciar=lambda t: ctx.avisar(t))
		self._crear_pagina_columnas()

	# ── Página de sonidos: se añade la lista de eventos ───────────────────────

	def _crear_pagina(self, pagina: Pagina, indice: int) -> wx.Window:
		panel = super()._crear_pagina(pagina, indice)
		if pagina.titulo == TITULO_SONIDOS:
			sizer = panel.GetSizer()
			sizer.Add(wx.StaticText(panel, label=_("&Eventos con sonido (marcados = suenan):")), 0, wx.LEFT | wx.TOP, 6)
			self.lista_eventos = ListaCasillas(panel, _("Eventos con sonido"),
				[sonidos_servicio.descripcion(e) for e in self._eventos], config=self.ctx.config)
			desactivados = set(self.ctx.config.obtener("sonidos.desactivados", []) or [])
			for indice_evento, evento in enumerate(self._eventos):
				wx.CheckListBox.Check(self.lista_eventos, indice_evento, evento not in desactivados)
			self.lista_eventos.SetMinSize(self.FromDIP(wx.Size(-1, 200)))
			sizer.Add(self.lista_eventos, 1, wx.EXPAND | wx.ALL, 6)
			self.boton_probar = wx.Button(panel, label=_("Pro&bar el sonido elegido"))
			self.boton_probar.SetHelpText(_("Reproduce el sonido del evento elegido en la lista, aunque esté desmarcado."))
			self.boton_probar.Bind(wx.EVT_BUTTON, self._al_probar)
			sizer.Add(self.boton_probar, 0, wx.ALL, 6)
			panel.Layout()
		return panel

	def _al_probar(self, _evento: wx.CommandEvent) -> None:
		indice = self.lista_eventos.GetSelection()
		if indice >= 0 and self._sonidos is not None:
			self._sonidos.probar(self._eventos[indice])

	# ── Página de columnas ────────────────────────────────────────────────────

	def _crear_pagina_columnas(self) -> None:
		if not self._vistas:
			return
		panel = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		texto = wx.StaticText(panel, label=_(
			"Elija una lista y marque las columnas que quiere ver. El orden de arriba abajo es el orden de las columnas "
			"(el lector lee la fila en ese orden)."))
		texto.Wrap(self.FromDIP(560))
		sizer.Add(texto, 0, wx.ALL, 6)
		sizer.Add(wx.StaticText(panel, label=_("&Lista:")), 0, wx.LEFT | wx.TOP, 6)
		self.selector_vista = wx.Choice(panel, choices=[v.titulo for v in self._vistas])
		self.selector_vista.SetHelpText(_("Lista de la aplicación cuyas columnas quiere configurar."))
		self.selector_vista.Bind(wx.EVT_CHOICE, lambda _e: self._mostrar_columnas())
		sizer.Add(self.selector_vista, 0, wx.EXPAND | wx.ALL, 6)
		sizer.Add(wx.StaticText(panel, label=_("Columnas &visibles y su orden:")), 0, wx.LEFT | wx.TOP, 6)
		self.lista_columnas = ListaCasillas(panel, _("Columnas visibles y su orden"), [], config=self.ctx.config)
		self.lista_columnas.Bind(wx.EVT_CHECKLISTBOX, self._al_marcar_columna)
		sizer.Add(self.lista_columnas, 1, wx.EXPAND | wx.ALL, 6)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		for etiqueta, manejador, ayuda in (
			(_("S&ubir"), lambda _e: self._mover(-1), _("Sube la columna elegida un puesto.")),
			(_("Ba&jar"), lambda _e: self._mover(1), _("Baja la columna elegida un puesto.")),
			(_("&Original de esta lista"), lambda _e: self._original(), _("Vuelve a las columnas de fábrica de esta lista.")),
		):
			boton = wx.Button(panel, label=etiqueta)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, manejador)
			fila.Add(boton, 0, wx.RIGHT, 6)
		sizer.Add(fila, 0, wx.ALL, 6)
		panel.SetSizer(sizer)
		self.libro.AddPage(panel, _(TITULO_COLUMNAS))
		self.selector_vista.SetSelection(0)
		self._orden_actual: list[str] = []
		self._mostrar_columnas()

	def _vista(self):
		return self._vistas[self.selector_vista.GetSelection()]

	def _mostrar_columnas(self, seleccion: int = 0) -> None:
		vista = self._vista()
		por_id = {c.id: c for c in vista.columnas}
		elegidas = self._columnas_elegidas.get(vista.id) or [c.id for c in vista.columnas if c.visible]
		resto = [c.id for c in vista.columnas if c.id not in elegidas]
		self._orden_actual = [i for i in elegidas if i in por_id] + resto
		self.lista_columnas.Set([por_id[i].titulo for i in self._orden_actual])
		for indice, identificador in enumerate(self._orden_actual):
			wx.CheckListBox.Check(self.lista_columnas, indice, identificador in elegidas)
		if self._orden_actual:
			self.lista_columnas.SetSelection(max(0, min(seleccion, len(self._orden_actual) - 1)))

	def _guardar_columnas_en_memoria(self) -> None:
		marcadas = [self._orden_actual[i] for i in range(len(self._orden_actual)) if self.lista_columnas.IsChecked(i)]
		if not marcadas:
			marcadas = self._orden_actual[:1]
		self._columnas_elegidas[self._vista().id] = marcadas

	def _al_marcar_columna(self, evento: wx.CommandEvent) -> None:
		evento.Skip()
		wx.CallAfter(self._guardar_columnas_en_memoria)

	def _mover(self, paso: int) -> None:
		indice = self.lista_columnas.GetSelection()
		destino = indice + paso
		if indice < 0 or not 0 <= destino < len(self._orden_actual):
			self.ctx.anunciar(_("No se puede mover más."))
			return
		marcadas = {self._orden_actual[i] for i in range(len(self._orden_actual)) if self.lista_columnas.IsChecked(i)}
		self._orden_actual[indice], self._orden_actual[destino] = self._orden_actual[destino], self._orden_actual[indice]
		self._columnas_elegidas[self._vista().id] = [i for i in self._orden_actual if i in marcadas]
		self._mostrar_columnas(destino)
		self.lista_columnas.SetFocus()
		self.ctx.anunciar(_("{c}, posición {p}").format(c=self.lista_columnas.GetString(destino), p=destino + 1))

	def _original(self) -> None:
		self._columnas_elegidas.pop(self._vista().id, None)
		self._mostrar_columnas()
		self.ctx.anunciar(_("Columnas de fábrica."))

	# ── Guardar ───────────────────────────────────────────────────────────────

	def aplicar(self) -> bool:
		if not super().aplicar():
			return False
		cambios: dict[str, Any] = {}
		if hasattr(self, "lista_eventos"):
			desactivados = [e for i, e in enumerate(self._eventos) if not self.lista_eventos.IsChecked(i)]
			if desactivados != list(self.ctx.config.obtener("sonidos.desactivados", []) or []):
				cambios["sonidos.desactivados"] = desactivados
		if self._vistas:
			self._guardar_columnas_en_memoria()
			if self._columnas_elegidas != (self.ctx.config.obtener("listas.columnas", {}) or {}):
				cambios["listas.columnas"] = dict(self._columnas_elegidas)
		if cambios:
			self.ctx.config.establecer_varias(cambios)
		return True

	def restablecer_controles(self) -> None:
		super().restablecer_controles()
		if hasattr(self, "lista_eventos"):
			for indice in range(self.lista_eventos.GetCount()):
				wx.CheckListBox.Check(self.lista_eventos, indice, True)
		if self._vistas:
			self._columnas_elegidas = {}
			self._mostrar_columnas()


def mostrar_preferencias(padre: wx.Window | None, ctx: Any, vistas: list[Any] | None = None) -> bool:
	dialogo = DialogoPreferenciasGitHub(padre, ctx, vistas)
	try:
		return dialogo.ShowModal() == wx.ID_OK
	finally:
		dialogo.Destroy()
