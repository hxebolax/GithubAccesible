"""Visor accesible de diferencias (diff): línea a línea, con tipo, número y sonidos.

Es la pieza que más se echa en falta en la web de GitHub con lector de
pantalla. Aquí cada línea es una fila de una lista nativa:

- Columnas: Tipo («Añadida», «Eliminada», «Sin cambios», «Bloque», «Archivo»),
  Línea (número en el archivo) y Texto. Tipo y número se pueden ocultar en
  Preferencias, Accesibilidad (el lector solo lee las columnas que hay).
- Sonido distinto al llegar a una línea añadida, eliminada o a un bloque.
- Saltos: F8 / Mayús+F8 al siguiente / anterior grupo de cambios; Ctrl+F8 /
  Ctrl+Mayús+F8 al siguiente / anterior bloque; F7 / Mayús+F7 al siguiente /
  anterior archivo; Ctrl+G a una línea por número; Ctrl+T todo como texto.
- Comentarios en línea (pull requests): columna «Comentarios», Intro comenta
  la línea, Ctrl+Intro lee los comentarios que ya tiene.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable
from typing import Any

import wx

from app.services import diferencias as d
from app.ui.accesibilidad.composicion import PreferenciasLectura
from app.ui.accesibilidad.dialogos import mostrar_mensaje, pedir_texto
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.teclado import cerrar_con_escape, copiar_texto, vincular_menu_contextual
from app.ui.vistas.base import preferencias_lectura

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


ComentarLinea = Callable[[d.LineaDiff], None]


class PanelDiferencias(wx.Panel):
	"""Lista de líneas de un diff con navegación por cambios, bloques y archivos.

	:param contexto: ``Contexto`` (configuración, sonidos, voz).
	:param al_comentar: si se da, Intro sobre una línea llama a esta función.
	:param comentarios: ``{(ruta, lado, línea): [textos]}`` para marcar líneas comentadas
		(lado «RIGHT» para añadidas y sin cambios, «LEFT» para eliminadas).
	"""

	def __init__(self, padre: wx.Window, contexto: Any, etiqueta: str = "", al_comentar: ComentarLinea | None = None,
		comentarios: dict | None = None) -> None:
		super().__init__(padre)
		self.ctx = contexto
		self.archivos: list[d.ArchivoDiff] = []
		self.lineas: list[d.LineaDiff] = []
		self.al_comentar = al_comentar
		self.comentarios: dict = comentarios or {}
		self._ultima_fila = -1
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.etiqueta = wx.StaticText(self, label=etiqueta or _("&Diferencias:"))
		raiz.Add(self.etiqueta, 0, wx.LEFT | wx.TOP, 4)
		self._crear_lista()
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 4)
		self.resumen = wx.StaticText(self, label="")
		raiz.Add(self.resumen, 0, wx.LEFT | wx.BOTTOM, 4)
		self.SetSizer(raiz)

	# ── Construcción ──────────────────────────────────────────────────────────

	def _columnas(self) -> list[tuple[str, str, int]]:
		config = self.ctx.config
		columnas = []
		if config.obtener("accesibilidad.diff_decir_tipo", True):
			columnas.append(("tipo", _("Tipo"), 90))
		if config.obtener("accesibilidad.diff_decir_numero", True):
			columnas.append(("numero", _("Línea"), 60))
		columnas.append(("texto", _("Texto"), 640))
		if self.comentarios:
			columnas.append(("comentarios", _("Comentarios"), 90))
		return columnas

	def _crear_lista(self) -> None:
		self._ids_columnas = [c[0] for c in self._columnas()]
		self.lista = ListaAccesible(
			self, nombre=_("Diferencias"),
			columnas=[(titulo, self.FromDIP(ancho)) for _i, titulo, ancho in self._columnas()],
			virtual=True, leer_preferencias=preferencias_lectura(self.ctx.config),
			preferencias_locales=PreferenciasLectura(numero_fila=False),
		)
		self.lista.SetHelpText(_(
			"Diferencias línea a línea. F8 y Mayúsculas+F8: siguiente y anterior cambio. Control+F8: siguiente bloque. "
			"F7 y Mayúsculas+F7: siguiente y anterior archivo. Control+G: ir a una línea. Control+T: ver como texto. "
			"Intro: comentar la línea (si se puede). Control+Intro: leer sus comentarios."
		))
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_pulsar)
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, self._al_enfocar)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.comentar_actual())
		vincular_menu_contextual(self.lista, self._menu)

	def _fila(self, linea: d.LineaDiff) -> list[str]:
		valores = []
		for columna in self._ids_columnas:
			if columna == "tipo":
				valores.append(linea.nombre_tipo())
			elif columna == "numero":
				valores.append(linea.numero() if linea.tipo not in (d.ARCHIVO, d.BLOQUE) else "")
			elif columna == "texto":
				valores.append(linea.texto if linea.texto.strip() else _("(línea en blanco)"))
			elif columna == "comentarios":
				cantidad = len(self.comentarios_de(linea))
				valores.append(str(cantidad) if cantidad else "")
		return valores

	def mostrar(self, texto_diff: str, archivo_por_defecto: str = "") -> None:
		"""Analiza y muestra un diff unificado."""
		self.mostrar_archivos(d.analizar(texto_diff, archivo_por_defecto))

	def mostrar_archivos(self, archivos: list[d.ArchivoDiff]) -> None:
		self.archivos = archivos
		self.lineas = d.aplanar(archivos)
		if [c[0] for c in self._columnas()] != self._ids_columnas:
			# Cambió una preferencia de columnas: se rehace la lista.
			vieja = self.lista
			self._crear_lista()
			self.GetSizer().Replace(vieja, self.lista)
			vieja.Destroy()
			self.Layout()
		self.lista.reemplazar_filas([self._fila(linea) for linea in self.lineas], conservar_foco=False)
		self.resumen.SetLabel(d.resumen_total(archivos) if archivos else _("No hay diferencias."))
		if self.lineas:
			self.lista.enfocar_fila(0, anunciar=False)

	def comentarios_de(self, linea: d.LineaDiff) -> list[str]:
		if not self.comentarios or linea.tipo not in (d.AÑADIDA, d.ELIMINADA, d.CONTEXTO):
			return []
		lado = "LEFT" if linea.tipo == d.ELIMINADA else "RIGHT"
		numero = linea.antigua if lado == "LEFT" else linea.nueva
		return self.comentarios.get((linea.archivo, lado, numero), [])

	def actualizar_comentarios(self, comentarios: dict) -> None:
		self.comentarios = comentarios
		self.mostrar_archivos(self.archivos)

	# ── Navegación ────────────────────────────────────────────────────────────

	@property
	def actual(self) -> int:
		fila = self.lista.fila_actual()
		return 0 if fila == wx.NOT_FOUND else fila

	def linea_actual(self) -> d.LineaDiff | None:
		return self.lineas[self.actual] if self.lineas else None

	def _ir(self, indice: int | None, sin_mas: str) -> None:
		if indice is None:
			self.ctx.sonar("vacio")
			self.ctx.anunciar(sin_mas)
			return
		self.lista.enfocar_fila(indice)

	def siguiente_cambio(self, atras: bool = False) -> None:
		self._ir(d.siguiente_cambio(self.lineas, self.actual, atras), _("No hay más cambios."))

	def siguiente_bloque(self, atras: bool = False) -> None:
		self._ir(d.siguiente(self.lineas, self.actual, lambda l: l.tipo == d.BLOQUE, atras), _("No hay más bloques."))

	def siguiente_archivo(self, atras: bool = False) -> None:
		self._ir(d.siguiente(self.lineas, self.actual, lambda l: l.tipo == d.ARCHIVO, atras), _("No hay más archivos."))

	def ir_a_linea(self) -> None:
		texto = pedir_texto(self, _("&Número de línea del archivo:"), _("Ir a la línea"))
		if not texto or not texto.strip().isdigit():
			return
		numero = int(texto.strip())
		archivo = self.linea_actual().archivo if self.linea_actual() else ""
		for indice, linea in enumerate(self.lineas):
			if linea.archivo == archivo and (linea.nueva == numero or (linea.tipo == d.ELIMINADA and linea.antigua == numero)):
				self.lista.enfocar_fila(indice)
				return
		self.ctx.anunciar(_("La línea {n} no aparece en las diferencias de este archivo.").format(n=numero))

	def ver_como_texto(self) -> None:
		from app.ui.dialogo_texto import DialogoTexto

		dialogo = DialogoTexto(self, _("Diferencias como texto"), _("&Diferencias:"), d.texto_legible(self.archivos), copiable=True)
		dialogo.ShowModal()
		dialogo.Destroy()

	def comentar_actual(self) -> None:
		linea = self.linea_actual()
		if linea is None:
			return
		if self.al_comentar and linea.tipo in (d.AÑADIDA, d.ELIMINADA, d.CONTEXTO):
			self.al_comentar(linea)
		elif linea.tipo in (d.AÑADIDA, d.ELIMINADA, d.CONTEXTO):
			mostrar_mensaje(self, linea.texto or _("(línea en blanco)"), _("Línea {n}").format(n=linea.numero()))

	def leer_comentarios(self) -> None:
		linea = self.linea_actual()
		textos = self.comentarios_de(linea) if linea else []
		if not textos:
			self.ctx.anunciar(_("Esta línea no tiene comentarios."))
			return
		from app.ui.dialogo_texto import DialogoTexto

		dialogo = DialogoTexto(self, _("Comentarios de la línea"), _("&Comentarios:"), "\n\n".join(textos), copiable=True)
		dialogo.ShowModal()
		dialogo.Destroy()

	def copiar_linea(self) -> None:
		linea = self.linea_actual()
		if linea and copiar_texto(linea.texto):
			self.ctx.sonar("copiado")
			self.ctx.anunciar(_("Línea copiada."))

	def _menu(self) -> wx.Menu:
		from app.ui.accesibilidad.teclado import menu_de_acciones

		acciones: list = [
			(_("Siguiente cambio\tF8"), lambda: self.siguiente_cambio()),
			(_("Cambio anterior\tShift+F8"), lambda: self.siguiente_cambio(True)),
			(_("Siguiente bloque\tCtrl+F8"), lambda: self.siguiente_bloque()),
			(_("Siguiente archivo\tF7"), lambda: self.siguiente_archivo()),
			(_("Archivo anterior\tShift+F7"), lambda: self.siguiente_archivo(True)),
			(_("Ir a la línea…\tCtrl+G"), self.ir_a_linea),
			None,
			(_("Copiar la línea\tCtrl+C"), self.copiar_linea),
			(_("Ver todo como texto\tCtrl+T"), self.ver_como_texto),
		]
		if self.al_comentar:
			acciones += [None, (_("Comentar esta línea…\tIntro"), self.comentar_actual)]
		if self.comentarios:
			acciones.append((_("Leer los comentarios de la línea\tCtrl+Intro"), self.leer_comentarios))
		return menu_de_acciones(self.lista, acciones)

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		tecla = evento.GetKeyCode()
		ctrl, mayus = evento.ControlDown(), evento.ShiftDown()
		if tecla == wx.WXK_F8:
			(self.siguiente_bloque if ctrl else self.siguiente_cambio)(mayus)
		elif tecla == wx.WXK_F7 and not ctrl:
			self.siguiente_archivo(mayus)
		elif ctrl and tecla == ord("G"):
			self.ir_a_linea()
		elif ctrl and tecla == ord("T"):
			self.ver_como_texto()
		elif ctrl and tecla == ord("C") and not mayus:
			self.copiar_linea()
		elif ctrl and tecla in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
			self.leer_comentarios()
		else:
			evento.Skip()

	def _al_enfocar(self, evento: wx.ListEvent) -> None:
		evento.Skip()
		fila = evento.GetIndex()
		if fila == self._ultima_fila or not (0 <= fila < len(self.lineas)):
			return
		self._ultima_fila = fila
		if not self.ctx.config.obtener("accesibilidad.diff_sonidos", True):
			return
		tipo = self.lineas[fila].tipo
		if tipo == d.AÑADIDA:
			self.ctx.sonar("linea_anadida")
		elif tipo == d.ELIMINADA:
			self.ctx.sonar("linea_eliminada")
		elif tipo in (d.BLOQUE, d.ARCHIVO):
			self.ctx.sonar("bloque")
		if self.comentarios_de(self.lineas[fila]):
			self.ctx.sonar("aviso")


class VentanaDiferencias(wx.Frame):
	"""Ventana independiente para ver unas diferencias (commit, comparación, stash...)."""

	def __init__(self, padre: wx.Window | None, contexto: Any, titulo: str, cabecera: str = "") -> None:
		super().__init__(padre, title=titulo, size=(1000, 700))
		self.ctx = contexto
		panel = wx.Panel(self)
		raiz = wx.BoxSizer(wx.VERTICAL)
		if cabecera:
			raiz.Add(wx.StaticText(panel, label=_("&Información:")), 0, wx.LEFT | wx.TOP, 4)
			self.info = wx.TextCtrl(panel, value=cabecera, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
				size=(-1, self.FromDIP(120)))
			raiz.Add(self.info, 0, wx.EXPAND | wx.ALL, 4)
		self.diferencias = PanelDiferencias(panel, contexto)
		raiz.Add(self.diferencias, 1, wx.EXPAND)
		boton = wx.Button(panel, wx.ID_CLOSE, _("C&errar"))
		boton.Bind(wx.EVT_BUTTON, lambda _e: self.Close())
		raiz.Add(boton, 0, wx.ALL | wx.ALIGN_RIGHT, 4)
		panel.SetSizer(raiz)
		cerrar_con_escape(self)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		self.ctx.sonar("cerrar")
		evento.Skip()

	def mostrar(self, texto_diff: str) -> None:
		self.diferencias.mostrar(texto_diff)
		self.Show()
		self.ctx.sonar("abrir")
		self.diferencias.lista.SetFocus()


def abrir_diff(contexto: Any, padre: wx.Window | None, titulo: str, obtener: Callable[[], str], cabecera: str = "") -> None:
	"""Abre una ventana de diferencias; ``obtener`` se ejecuta en segundo plano."""
	from app.ui.comunes import en_segundo_plano

	def listo(texto: str) -> None:
		VentanaDiferencias(padre, contexto, titulo, cabecera).mostrar(texto)

	en_segundo_plano(padre, contexto, obtener, al_terminar=listo, sonido="", inicio=_("Cargando las diferencias…"))


def abrir_commit(contexto: Any, padre: wx.Window | None, nombre: str, sha: str) -> None:
	"""Muestra un commit de GitHub: mensaje, autor, archivos y diferencias."""
	from app.services import formato as f

	api = contexto.api()

	def obtener() -> tuple[dict, str]:
		return api.commit(nombre, sha), api.diff_commit(nombre, sha)

	def listo(resultado: tuple[dict, str]) -> None:
		datos, texto = resultado
		commit = datos.get("commit") or {}
		autor = commit.get("author") or {}
		estadisticas = datos.get("stats") or {}
		cabecera = "\n".join([
			_("Commit {s}").format(s=datos.get("sha", sha)[:12]),
			_("Autor: {a} <{c}>, {f}").format(a=autor.get("name", ""), c=autor.get("email", ""), f=f.fecha_completa(autor.get("date"))),
			_("Cambios: {t} líneas ({a} añadidas, {e} eliminadas) en {n} archivos").format(
				t=estadisticas.get("total", 0), a=estadisticas.get("additions", 0), e=estadisticas.get("deletions", 0),
				n=len(datos.get("files") or [])),
			_("Verificado: {v}").format(v=f.si_no((commit.get("verification") or {}).get("verified"))),
			"",
			commit.get("message", ""),
		])
		VentanaDiferencias(padre, contexto, _("Commit {s} de {n}").format(s=sha[:7], n=nombre), cabecera).mostrar(texto)

	from app.ui.comunes import en_segundo_plano

	en_segundo_plano(padre, contexto, obtener, al_terminar=listo, sonido="", inicio=_("Cargando el commit…"))
