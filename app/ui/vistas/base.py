"""Marco común de las vistas de lista: columnas, carga por páginas, acciones y teclas.

Casi todo en GitHub es «una lista de cosas sobre las que hacer algo»:
repositorios, issues, pull requests, ejecuciones de Actions, releases,
ramas, notificaciones... Cada una se describe con una ``DefinicionVista``
(columnas, cómo se carga, qué acciones tiene) y ``PanelLista`` la muestra de
forma idéntica y accesible:

- Etiqueta creada ANTES de la lista (el lector la anuncia como nombre).
- ``ListaAccesible``: lectura por columnas configurable (fila, cabecera,
  contenido) con Izquierda y Derecha o Ctrl+número, texto íntegro de celdas.
- Carga en segundo plano (la interfaz nunca se congela) con anuncio del total.
- Más páginas automáticamente al llegar al final, sin mover el foco.
- Acciones en el menú contextual (Aplicaciones o Mayús+F10) y en el menú
  «Acciones» de la ventana, con sus atajos visibles.
- Filtro rápido (Ctrl+F), copiar fila (Ctrl+C), copiar enlace (Ctrl+Mayús+C),
  abrir en el navegador (Ctrl+B), detalles (Ctrl+I), actualizar (F5).
- Columnas visibles y su orden, configurables por vista en Preferencias.
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import wx

from app.ui.accesibilidad.composicion import PreferenciasLectura
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.teclado import copiar_texto, vincular_menu_contextual

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ════════════════════════════════════════════════════════════════════════════
# Descriptores
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class Columna:
	"""Una columna de una vista.

	:param id: identificador estable (se guarda en Preferencias).
	:param titulo: cabecera visible y lo que se anuncia al leer la columna.
	:param valor: función ``(elemento, contexto) -> str``.
	:param ancho: ancho inicial en píxeles (se escala con el DPI).
	:param visible: si se muestra cuando la persona no ha configurado nada.
	"""

	id: str
	titulo: str
	valor: Callable[[Any, Any], str]
	ancho: int = 150
	visible: bool = True


@dataclass
class Accion:
	"""Una acción sobre la vista o sobre el elemento elegido.

	:param etiqueta: texto del menú con ``&``.
	:param funcion: ``(panel, elemento) -> None``; ``elemento`` es ``None`` si no requiere.
	:param atajo: texto del atajo para el menú («Ctrl+N», «Supr», «F2»...).
	:param requiere_elemento: solo se ofrece si hay un elemento elegido.
	:param disponible: ``(panel, elemento) -> bool`` para ocultarla cuando no procede.
	:param separador_antes: dibuja un separador antes en el menú.
	"""

	etiqueta: str
	funcion: Callable[[Any, Any], None]
	atajo: str = ""
	requiere_elemento: bool = True
	disponible: Callable[[Any, Any], bool] | None = None
	separador_antes: bool = False
	ayuda: str = ""


@dataclass
class DefinicionVista:
	"""Describe una vista de lista.

	:param id: identificador estable (columnas en Preferencias, registro).
	:param titulo: nombre visible de la vista; es también la etiqueta de la lista.
	:param columnas: columnas posibles.
	:param cargar: ``(api, pagina, panel) -> list | Pagina``. Se ejecuta en un hilo.
	:param activar: qué hace Intro sobre un elemento (``(panel, elemento)``).
	:param acciones: acciones propias de la vista.
	:param texto_vacio: lo que se dice si no hay elementos.
	:param url: ``(elemento) -> str`` con el enlace web del elemento.
	:param detalle: ``(elemento, contexto) -> str`` con todos los datos para Ctrl+I.
	:param paginada: si al llegar al final se piden más páginas.
	:param texto_busqueda: ``(elemento) -> str`` para el filtro rápido (por defecto, las columnas).
	:param al_cambiar: ``(panel) -> None`` tras cargar, quitar o sustituir elementos
		(por ejemplo, para que el contador de notificaciones no se quede atrás).
	"""

	id: str
	titulo: str
	columnas: list[Columna]
	cargar: Callable[[Any, int, Any], Any]
	activar: Callable[[Any, Any], None] | None = None
	acciones: list[Accion] = field(default_factory=list)
	texto_vacio: str = ""
	url: Callable[[Any], str] | None = None
	detalle: Callable[[Any, Any], str] | None = None
	paginada: bool = True
	texto_busqueda: Callable[[Any], str] | None = None
	sonido_carga: bool = True
	requiere_sesion: bool = True
	al_cambiar: Callable[[Any], None] | None = None

	def columnas_visibles(self, config: Any) -> list[Columna]:
		"""Columnas según Preferencias (orden y visibilidad) o las de por defecto."""
		elegidas = (config.obtener("listas.columnas", {}) or {}).get(self.id) if config else None
		por_id = {c.id: c for c in self.columnas}
		if elegidas:
			lista = [por_id[i] for i in elegidas if i in por_id]
			if lista:
				return lista
		return [c for c in self.columnas if c.visible] or self.columnas[:1]


def etiqueta_lista(titulo: str, detalle: str = "") -> str:
	"""Etiqueta de la lista de una vista: «&Lista de notificaciones (no leídas):»."""
	texto = titulo[:1].lower() + titulo[1:] if titulo[:2] != titulo[:2].upper() else titulo
	return _("&Lista de {t}").format(t=texto) + (f" ({detalle})" if detalle else "") + ":"


def url_html(elemento: Any) -> str:
	return (elemento or {}).get("html_url", "") if isinstance(elemento, dict) else ""


def preferencias_lectura(config: Any) -> Callable[[], PreferenciasLectura]:
	"""Lee la lectura por columnas de Preferencias EN CADA ANUNCIO (se aplica sin reiniciar)."""

	def leer() -> PreferenciasLectura:
		return PreferenciasLectura(
			numero_fila=bool(config.obtener("accesibilidad.leer_numero_fila", True)),
			cabecera=bool(config.obtener("accesibilidad.leer_cabecera", True)),
			contenido=bool(config.obtener("accesibilidad.leer_contenido", True)),
		)

	return leer


# ════════════════════════════════════════════════════════════════════════════
# Panel
# ════════════════════════════════════════════════════════════════════════════


class PanelLista(wx.Panel):
	"""Muestra una ``DefinicionVista``.

	:param contexto: ``Contexto`` de la aplicación.
	:param definicion: la vista.
	:param datos: diccionario libre con lo que necesite la vista (``repo``, ``filtro``...).
	:param al_cambiar_acciones: avisa a la ventana para que rehaga su menú «Acciones».
	"""

	def __init__(self, padre: wx.Window, contexto: Any, definicion: DefinicionVista, datos: dict | None = None,
		etiqueta: str | None = None) -> None:
		super().__init__(padre)
		self.ctx = contexto
		self.definicion = definicion
		self.datos: dict = dict(datos or {})
		self.elementos: list[Any] = []
		self.visibles: list[Any] = []
		self.filtro = ""
		self.pagina = 0
		self.hay_mas = False
		self.total: int | None = None
		self.cargando = False
		self.cargado = False
		self._tarea = None
		self._version_carga = 0

		sizer = wx.BoxSizer(wx.VERTICAL)
		# Etiqueta ANTES que la lista: el lector la toma como nombre de la lista.
		# Letra de acceso común a todas las listas de contenido (Alt+L): no choca con los
		# menús de las ventanas ni con «Secciones».
		self.etiqueta = wx.StaticText(self, label=etiqueta or etiqueta_lista(definicion.titulo))
		sizer.Add(self.etiqueta, 0, wx.LEFT | wx.TOP | wx.RIGHT, 4)
		self.columnas = definicion.columnas_visibles(contexto.config)
		self.lista = ListaAccesible(
			self,
			nombre=definicion.titulo,
			columnas=[(c.titulo, self.FromDIP(c.ancho)) for c in self.columnas],
			leer_preferencias=preferencias_lectura(contexto.config),
		)
		sizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 4)
		self.estado = wx.StaticText(self, label="")
		sizer.Add(self.estado, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
		self.SetSizer(sizer)

		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._al_activar)
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, self._al_enfocar)
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_pulsar)
		vincular_menu_contextual(self.lista, self.crear_menu)
		self.lista.SetHelpText(_(
			"{titulo}. Intro abre; Aplicaciones o Mayúsculas+F10 muestra las acciones; F5 actualiza; "
			"Control+F filtra; Control+C copia la fila; Control+Mayúsculas+C copia el enlace; "
			"Control+B abre en el navegador; Control+I muestra todos los detalles. Izquierda y derecha "
			"leen las columnas."
		).format(titulo=definicion.titulo))
		# Las columnas elegidas en Preferencias se aplican sin reiniciar. La configuración
		# guarda los métodos con referencia débil: un panel cerrado no recibe avisos.
		suscribir = getattr(contexto.config, "suscribir", None)
		if callable(suscribir):
			suscribir(self._al_cambiar_config, prefijo="listas.")

	def _al_cambiar_config(self, clave: str, _anterior: Any, _nuevo: Any) -> None:
		wx.CallAfter(self._aplicar_config, clave)

	def _aplicar_config(self, clave: str) -> None:
		if not self:
			return
		if clave.startswith("listas.columnas"):
			self.rehacer_columnas()
		elif clave == "listas.fechas_relativas":
			self.refrescar_filas()

	# ── Datos ─────────────────────────────────────────────────────────────────

	@property
	def elemento(self) -> Any:
		"""Elemento enfocado (o ``None``)."""
		fila = self.lista.fila_actual()
		if fila == wx.NOT_FOUND or fila >= len(self.visibles):
			return None
		return self.visibles[fila]

	def fila_de(self, elemento: Any) -> list[str]:
		valores = []
		for columna in self.columnas:
			try:
				valores.append(str(columna.valor(elemento, self.ctx) or ""))
			except Exception:  # noqa: BLE001 - un dato raro de la API no debe romper toda la lista
				log.debug("Columna %s falló con un elemento", columna.id, exc_info=True)
				valores.append("")
		return valores

	def _texto_busqueda(self, elemento: Any) -> str:
		if self.definicion.texto_busqueda:
			return self.definicion.texto_busqueda(elemento)
		return " ".join(self.fila_de(elemento))

	def _aplicar_filtro(self) -> None:
		if self.filtro:
			buscado = self.filtro.casefold()
			self.visibles = [e for e in self.elementos if buscado in self._texto_busqueda(e).casefold()]
		else:
			self.visibles = list(self.elementos)

	def refrescar_filas(self, conservar_foco: bool = True) -> None:
		"""Vuelve a pintar la lista con los datos actuales (sin pedir nada a la red)."""
		self._aplicar_filtro()
		self.lista.reemplazar_filas([self.fila_de(e) for e in self.visibles], conservar_foco=conservar_foco)
		self._actualizar_estado()

	def rehacer_columnas(self) -> None:
		"""Aplica un cambio de columnas de Preferencias en una lista ya abierta."""
		nuevas = self.definicion.columnas_visibles(self.ctx.config)
		if [c.id for c in nuevas] == [c.id for c in self.columnas]:
			return
		self.columnas = nuevas
		self.lista.limpiar()
		self.lista.DeleteAllColumns()
		for indice, columna in enumerate(self.columnas):
			self.lista.InsertColumn(indice, columna.titulo, width=self.FromDIP(columna.ancho))
		self.lista.reiniciar_columna()
		self.refrescar_filas()

	def _actualizar_estado(self) -> None:
		partes = []
		if self.cargando:
			partes.append(_("Cargando…"))
		cantidad = len(self.visibles)
		if self.filtro:
			partes.append(_("{n} de {t} elementos con el filtro «{f}»").format(n=cantidad, t=len(self.elementos), f=self.filtro))
		else:
			partes.append(_("{n} elementos").format(n=cantidad))
		if self.total is not None and self.total > len(self.elementos):
			partes.append(_("de {t} en total").format(t=self.total))
		if self.hay_mas:
			partes.append(_("hay más: se cargan al llegar al final o con Control+M"))
		self.estado.SetLabel(", ".join(partes) + ".")

	# ── Carga ─────────────────────────────────────────────────────────────────

	def cargar(self, reiniciar: bool = True, anunciar: bool = True) -> None:
		"""Pide los datos en segundo plano. Con ``reiniciar`` empieza por la primera página."""
		if self.cargando and not reiniciar:
			return
		if reiniciar:
			self.pagina = 0
			self._version_carga += 1
		version = self._version_carga
		siguiente = self.pagina + 1
		if self.definicion.requiere_sesion and getattr(self.ctx, "cuenta", True) is None:
			# Sin sesión no se pide nada a GitHub: se explica qué hacer.
			self.elementos, self.visibles, self.cargado, self.hay_mas = [], [], True, False
			self.lista.limpiar()
			self.estado.SetLabel(_("Necesita iniciar sesión para ver esta sección. Use Archivo, Iniciar sesión (Control+Mayúsculas+L)."))
			return
		self.cargando = True
		self._actualizar_estado()
		api = self.ctx.api()

		def trabajo(tarea):
			return self.definicion.cargar(api, siguiente, self)

		def al_terminar(resultado):
			if not self or version != self._version_carga:
				return  # una recarga posterior ya sustituyó a esta
			self._recibir(resultado, siguiente, reiniciar, anunciar)

		def al_fallar(error):
			if not self or version != self._version_carga:
				return
			self.cargando = False
			self._actualizar_estado()
			mensaje = getattr(error, "mensaje_usuario", None) or str(error)
			self.estado.SetLabel(_("No se pudo cargar: {m}").format(m=mensaje))
			self.ctx.sonar("error")
			self.ctx.avisar(_("Error al cargar {t}: {m}").format(t=self.definicion.titulo, m=mensaje))

		self._tarea = self.ctx.tareas.enviar(
			trabajo, al_terminar=al_terminar, al_fallar=al_fallar,
			nombre=f"vista:{self.definicion.id}", duplicadas="permitir",
		)

	def _recibir(self, resultado: Any, numero: int, reiniciar: bool, anunciar: bool) -> None:
		from app.services.github.cliente import Pagina

		if isinstance(resultado, Pagina):
			nuevos = list(resultado.elementos)
			self.hay_mas = self.definicion.paginada and resultado.hay_mas
			if resultado.total is not None:
				self.total = resultado.total
		else:
			nuevos = list(resultado or [])
			self.hay_mas = False
		self.pagina = numero
		self.cargando = False
		self.cargado = True
		if reiniciar:
			self.elementos = nuevos
			self._aplicar_filtro()
			self.lista.reemplazar_filas([self.fila_de(e) for e in self.visibles], conservar_foco=True)
			self.lista.reiniciar_columna()
		else:
			self.elementos.extend(nuevos)
			anteriores = len(self.visibles)
			self._aplicar_filtro()
			for elemento in self.visibles[anteriores:]:
				self.lista.agregar_fila(self.fila_de(elemento))
		self._actualizar_estado()
		self._avisar_cambio()
		if self.lista.numero_filas() and self.lista.fila_actual() == wx.NOT_FOUND:
			self.lista.enfocar_fila(0, anunciar=False)
		if not anunciar:
			return
		if not self.elementos:
			self.ctx.sonar("vacio")
			if self.lista.HasFocus() or self.ctx.config.obtener("accesibilidad.anunciar_total", True):
				self.ctx.avisar(self.definicion.texto_vacio or _("No hay elementos."), interrumpir=False)
			return
		if reiniciar:
			if self.definicion.sonido_carga:
				self.ctx.sonar("listo")
			if self.ctx.config.obtener("accesibilidad.anunciar_total", True) and self.lista.HasFocus():
				self.ctx.avisar(self.estado.GetLabel(), interrumpir=False)
		else:
			self.ctx.sonar("pagina")
			self.ctx.avisar(_("{n} elementos más cargados.").format(n=len(nuevos)), interrumpir=False)

	def cargar_mas(self) -> None:
		if self.hay_mas and not self.cargando:
			self.cargar(reiniciar=False)
		elif not self.hay_mas:
			self.ctx.avisar(_("No hay más elementos."))

	def cargar_si_hace_falta(self) -> None:
		if not self.cargado and not self.cargando:
			self.cargar()

	def quitar(self, elemento: Any) -> None:
		"""Quita un elemento de la lista (tras borrarlo) sin recargar."""
		if elemento in self.elementos:
			self.elementos.remove(elemento)
		if elemento in self.visibles:
			fila = self.visibles.index(elemento)
			self.visibles.pop(fila)
			self.lista.eliminar_fila(fila)
		self._actualizar_estado()
		self._avisar_cambio()

	def sustituir(self, antiguo: Any, nuevo: Any) -> None:
		"""Pone ``nuevo`` en lugar de ``antiguo`` (tras editarlo) sin mover el foco."""
		if antiguo in self.elementos:
			self.elementos[self.elementos.index(antiguo)] = nuevo
		if antiguo in self.visibles:
			fila = self.visibles.index(antiguo)
			self.visibles[fila] = nuevo
			self.lista.actualizar_fila(fila, self.fila_de(nuevo))
		self._avisar_cambio()

	def _avisar_cambio(self) -> None:
		if self.definicion.al_cambiar is None:
			return
		try:
			self.definicion.al_cambiar(self)
		except Exception:  # noqa: BLE001 - un aviso fallido no debe romper la lista
			log.warning("Falló el aviso de cambio de la vista %s", self.definicion.id, exc_info=True)

	# ── Acciones ──────────────────────────────────────────────────────────────

	def acciones_comunes(self) -> list[Accion]:
		comunes = [
			Accion(_("&Actualizar"), lambda p, e: p.cargar(), "F5", requiere_elemento=False, separador_antes=True),
			Accion(_("Cargar &más"), lambda p, e: p.cargar_mas(), "Ctrl+M", requiere_elemento=False,
				disponible=lambda p, e: p.hay_mas),
			Accion(_("&Filtrar la lista…"), lambda p, e: p.pedir_filtro(), "Ctrl+F", requiere_elemento=False),
			Accion(_("&Quitar el filtro"), lambda p, e: p.quitar_filtro(), "Ctrl+Shift+F", requiere_elemento=False,
				disponible=lambda p, e: bool(p.filtro)),
			Accion(_("C&opiar la fila"), lambda p, e: p.copiar_fila(), "Ctrl+C"),
		]
		if self.definicion.url:
			comunes += [
				Accion(_("Copiar el &enlace"), lambda p, e: p.copiar_enlace(), "Ctrl+Shift+C"),
				Accion(_("Abrir en el &navegador"), lambda p, e: p.abrir_navegador(), "Ctrl+B"),
			]
		comunes.append(Accion(_("&Detalles completos…"), lambda p, e: p.mostrar_detalles(), "Ctrl+I"))
		return comunes

	def todas_las_acciones(self) -> list[Accion]:
		return list(self.definicion.acciones) + self.acciones_comunes()

	def acciones_disponibles(self) -> list[Accion]:
		elemento = self.elemento
		resultado = []
		for accion in self.todas_las_acciones():
			if accion.requiere_elemento and elemento is None:
				continue
			if accion.disponible is not None:
				try:
					if not accion.disponible(self, elemento):
						continue
				except Exception:  # noqa: BLE001 - una condición rota oculta la acción, no la ventana
					log.debug("Condición de acción falló", exc_info=True)
					continue
			resultado.append(accion)
		return resultado

	def ejecutar(self, accion: Accion) -> None:
		elemento = self.elemento
		if accion.requiere_elemento and elemento is None:
			self.ctx.avisar(_("No hay ningún elemento elegido."))
			return
		try:
			accion.funcion(self, elemento)
		except Exception as error:  # noqa: BLE001 - se informa y se registra, la ventana sigue viva
			log.exception("Fallo en la acción %s", accion.etiqueta)
			from app.ui.accesibilidad.dialogos import mostrar_error

			mostrar_error(self, getattr(error, "mensaje_usuario", None) or str(error), _("Error"))

	def crear_menu(self, acciones: list[Accion] | None = None, en_barra: bool = False) -> wx.Menu:
		"""Menú con las acciones disponibles (contextual y menú «Acciones» de la ventana).

		:param en_barra: en la barra de menús el atajo se escribe entre paréntesis y NO
			con tabulador: con tabulador, wx lo registraría como atajo de toda la ventana
			y Ctrl+C dejaría de copiar en los cuadros de texto. Las teclas las atiende
			la propia lista.
		"""
		menu = wx.Menu()
		primero = True
		for accion in acciones if acciones is not None else self.acciones_disponibles():
			if accion.separador_antes and not primero:
				menu.AppendSeparator()
			if accion.atajo:
				etiqueta = accion.etiqueta + (f" ({accion.atajo})" if en_barra else f"\t{accion.atajo}")
			else:
				etiqueta = accion.etiqueta
			item = menu.Append(wx.ID_ANY, etiqueta, accion.ayuda)
			menu.Bind(wx.EVT_MENU, lambda _evento, a=accion: wx.CallAfter(self.ejecutar, a), item)
			primero = False
		return menu

	def atajo_de(self, evento: wx.KeyEvent) -> Accion | None:
		"""Acción cuyo atajo coincide con la tecla pulsada (las atajos se escriben como en los menús)."""
		texto = texto_tecla(evento)
		if not texto:
			return None
		for accion in self.acciones_disponibles():
			if accion.atajo and normalizar_atajo(accion.atajo) == texto:
				return accion
		return None

	# ── Acciones comunes ──────────────────────────────────────────────────────

	def pedir_filtro(self) -> None:
		from app.ui.accesibilidad.dialogos import pedir_texto

		texto = pedir_texto(self, _("&Texto que deben contener los elementos:"), _("Filtrar la lista"), self.filtro)
		if texto is None:
			return
		self.filtro = texto.strip()
		self.refrescar_filas(conservar_foco=False)
		if self.lista.numero_filas():
			self.lista.enfocar_fila(0, anunciar=False)
		self.lista.SetFocus()
		self.ctx.avisar(self.estado.GetLabel())

	def quitar_filtro(self) -> None:
		self.filtro = ""
		self.refrescar_filas()
		self.ctx.avisar(_("Filtro quitado. ") + self.estado.GetLabel())

	def copiar_fila(self) -> None:
		elemento = self.elemento
		if elemento is None:
			return
		textos = [f"{c.titulo}: {v}" for c, v in zip(self.columnas, self.fila_de(elemento), strict=False) if v]
		if copiar_texto("\n".join(textos)):
			self.ctx.sonar("copiado")
			self.ctx.avisar(_("Copiado."))

	def copiar_enlace(self) -> None:
		url = self.definicion.url(self.elemento) if self.definicion.url and self.elemento is not None else ""
		if url and copiar_texto(url):
			self.ctx.sonar("copiado")
			self.ctx.avisar(_("Enlace copiado."))
		else:
			self.ctx.avisar(_("Este elemento no tiene enlace."))

	def abrir_navegador(self) -> None:
		url = self.definicion.url(self.elemento) if self.definicion.url and self.elemento is not None else ""
		if url:
			webbrowser.open(url)
		else:
			self.ctx.avisar(_("Este elemento no tiene enlace."))

	def mostrar_detalles(self) -> None:
		elemento = self.elemento
		if elemento is None:
			return
		if self.definicion.detalle:
			texto = self.definicion.detalle(elemento, self.ctx)
		else:
			texto = "\n".join(f"{c.titulo}: {v}" for c in self.definicion.columnas if (v := _valor_seguro(c, elemento, self.ctx)))
		from app.ui.dialogo_texto import DialogoTexto

		dialogo = DialogoTexto(self, _("Detalles"), _("&Detalles:"), texto, copiable=True)
		dialogo.ShowModal()
		dialogo.Destroy()

	# ── Eventos ───────────────────────────────────────────────────────────────

	def _al_activar(self, evento: wx.ListEvent) -> None:
		elemento = self.elemento
		if elemento is not None and self.definicion.activar:
			try:
				self.definicion.activar(self, elemento)
			except Exception as error:  # noqa: BLE001
				log.exception("Fallo al abrir un elemento de %s", self.definicion.id)
				from app.ui.accesibilidad.dialogos import mostrar_error

				mostrar_error(self, getattr(error, "mensaje_usuario", None) or str(error), _("Error"))

	def _al_enfocar(self, evento: wx.ListEvent) -> None:
		evento.Skip()
		# Al llegar a la última fila se pide la página siguiente, sin mover el foco.
		if self.hay_mas and not self.cargando and not self.filtro and evento.GetIndex() >= len(self.visibles) - 1:
			self.cargar(reiniciar=False)

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		accion = self.atajo_de(evento)
		if accion is not None:
			self.ejecutar(accion)
			return
		evento.Skip()


def _valor_seguro(columna: Columna, elemento: Any, ctx: Any) -> str:
	try:
		return str(columna.valor(elemento, ctx) or "")
	except Exception:  # noqa: BLE001
		return ""


# ── Teclas ───────────────────────────────────────────────────────────────────

_NOMBRES_TECLA = {
	wx.WXK_F1: "F1", wx.WXK_F2: "F2", wx.WXK_F3: "F3", wx.WXK_F4: "F4", wx.WXK_F5: "F5", wx.WXK_F6: "F6",
	wx.WXK_F7: "F7", wx.WXK_F8: "F8", wx.WXK_F9: "F9", wx.WXK_F11: "F11", wx.WXK_F12: "F12",
	wx.WXK_DELETE: "Supr", wx.WXK_INSERT: "Insert", wx.WXK_BACK: "Retroceso", wx.WXK_RETURN: "Intro",
	wx.WXK_SPACE: "Espacio", wx.WXK_HOME: "Inicio", wx.WXK_END: "Fin",
}


def texto_tecla(evento: wx.KeyEvent) -> str:
	"""«Ctrl+Shift+C», «Supr», «F2»... en el mismo formato que los atajos de las acciones."""
	codigo = evento.GetKeyCode()
	nombre = _NOMBRES_TECLA.get(codigo)
	if nombre is None:
		if 32 < codigo < 127:
			nombre = chr(codigo).upper()
		else:
			return ""
	partes = []
	if evento.ControlDown():
		partes.append("Ctrl")
	if evento.AltDown():
		partes.append("Alt")
	if evento.ShiftDown():
		partes.append("Shift")
	partes.append(nombre)
	return "+".join(partes)


def normalizar_atajo(atajo: str) -> str:
	partes = [p.strip() for p in atajo.replace("Mayús", "Shift").replace("Del", "Supr").split("+")]
	modificadores = [p for p in ("Ctrl", "Alt", "Shift") if p in partes]
	resto = [p.upper() if len(p) == 1 else p for p in partes if p not in ("Ctrl", "Alt", "Shift")]
	return "+".join(modificadores + resto)
