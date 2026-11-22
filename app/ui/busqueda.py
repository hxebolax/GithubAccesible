"""Diálogo de búsqueda en GitHub: tipos, filtros guiados, historial y búsquedas guardadas.

Cómo está hecho, y por qué así:

- Los filtros de cada tipo salen de los descriptores de ``app.services.busqueda``
  (sin wx y con pruebas). Al cambiar «Buscar» se rehacen las pestañas de
  filtros (Básico, Personas, Pull requests, Fechas y números, Avanzado) y se
  conservan los valores que sigan teniendo sentido (lenguaje, repositorios...).
- Cada etiqueta se crea JUSTO antes de su control y con el mismo padre (el
  lector de pantalla la toma como nombre). Las letras de acceso se asignan
  solas sin repetirse en cada pestaña ni con los controles y botones de fuera.
- «Consulta resultante» (solo lectura) se actualiza al momento: dice qué se
  enviará a GitHub, el orden y los problemas que impedirían buscar.
- Teclas fijas: Alt+B tipo, Alt+T texto, Alt+L consulta resultante, Alt+U
  Buscar, Alt+N abrir en el navegador, Alt+J ejemplos, Alt+S guardar la
  búsqueda, Alt+C o Escape cancelar, Control+Tabulador cambia de pestaña,
  Control+H describe el control enfocado. En la pestaña «Historial y
  guardadas»: Alt+H historial, Alt+G guardadas, Alt+R renombrar, Alt+O borrar.
"""

from __future__ import annotations

import logging
import webbrowser
from typing import Any

import wx

from app.services import busqueda as b
from app.ui.accesibilidad.dialogos import confirmar, mostrar_error, pedir_texto, preparar_dialogo
from app.ui.accesibilidad.foco import devolver_foco
from app.ui.comunes import ListaCasillas

log = logging.getLogger(__name__)

MAXIMO_HISTORIAL = 20

def letras_fijas() -> frozenset[str]:
	"""Letras de acceso de los controles y botones que están fuera de las pestañas.

	Se calculan de las etiquetas traducidas (en español, «btlunjsc»): en inglés las
	letras son otras y los filtros de las pestañas no deben repetirlas.
	"""
	textos = (_("&Buscar:"), _("&Texto (admite calificadores):"), _("Consulta resu&ltante:"), _("B&uscar"),
		_("Abrir en el &navegador"), _("E&jemplos de calificadores…"), _("Guardar bú&squeda…"), _("&Cancelar"))
	return frozenset(t[t.index("&") + 1].lower() for t in textos if "&" in t[:-1])

# Compatibilidad con la versión anterior (historial antiguo y pruebas).
ORDENES = b.ORDENES
LENGUAJES = b.LENGUAJES
LICENCIAS = b.LICENCIAS

# (clave, nombre, calificador). En el calificador, «{v}» es el valor que escribe la persona.
CATEGORIAS: list[tuple[str, str, str]] = [
	("libre", N_("Búsqueda libre (sin categoría)"), ""),
	("populares", N_("Populares: estrellas mínimas"), "stars:>{v}"),
	("bifurcados", N_("Más bifurcados: bifurcaciones mínimas"), "forks:>{v}"),
	("recientes", N_("Actualizados desde una fecha (AAAA-MM-DD)"), "pushed:>{v}"),
	("desactualizados", N_("Sin actualizar desde una fecha (AAAA-MM-DD)"), "pushed:<{v}"),
	("buenas_primeras", N_("Con issues para empezar a colaborar"), "good-first-issues:>0"),
	("ayuda", N_("Que piden ayuda"), "help-wanted-issues:>0"),
	("awesome", N_("Listas Awesome"), "awesome in:name,description"),
	("nvda", N_("Complementos y programas para NVDA"), "nvda"),
] + [(clave, nombre, f"topic:{valores['temas']}") for clave, nombre, valores in b.ATAJOS_REPOSITORIOS if "temas" in valores]

AYUDA = N_("""Calificadores útiles (se pueden combinar; los filtros de las pestañas los escriben por usted):

Repositorios: language:python, stars:>100, stars:10..50, forks:>=10, topic:accessibility, user:octocat, org:github, archived:false, is:public, pushed:>2025-01-01, created:2024-01-01..2024-12-31, license:mit, good-first-issues:>0, in:name,description, fork:true, is:sponsorable.
Código: repo:dueño/nombre, path:app/ui, filename:setup.py, extension:py, language:python, in:path. Necesita sesión, al menos una palabra (salvo con filename:) y solo busca en la rama principal. La API usa la búsqueda de código antigua: las expresiones regulares (/patrón/), symbol: y los operadores de la web solo funcionan con «Abrir en el navegador».
Issues y pull requests: is:issue o is:pr, is:open o is:closed, repo:dueño/nombre, author:usuario, assignee:@me, label:bug, -label:wontfix, mentions:@me, review-requested:@me, no:assignee, comments:>10, created:>=2026-01-01, reason:completed, linked:pr, type:Bug, field.priority:high. Admite AND, OR y paréntesis: (label:bug OR label:docs) is:open.
Búsqueda semántica o híbrida de issues: elija «Solo issues» y el tipo de búsqueda en la pestaña Básico. Busca por significado en el título y el cuerpo; sin orden, una sola página y como mucho 10 búsquedas por minuto.
Usuarios: type:user o type:org, location:Madrid, followers:>100, repos:>10, language:python, fullname:"Ana López", in:login.
Commits: repo:dueño/nombre, author:usuario, committer-date:>2025-01-01, merge:false, hash:abc1234.
Temas: is:featured, is:curated, repositories:>1000.
Etiquetas: solo palabras y el repositorio (dueño/nombre) en la pestaña Básico.
Discusiones: is:answered, is:unanswered, category:Ideas, answered-by:usuario, repo:dueño/nombre.
Tendencias: «Nuevos y populares» usa la API oficial (repositorios creados en el periodo con más estrellas). Las otras fuentes leen github.com/trending, que no tiene API oficial y puede dejar de funcionar.

Frases entre comillas: "texto exacto". Excluir un calificador con un guion: -language:javascript. Excluir una palabra: NOT palabra.
Límites de GitHub: 256 caracteres de texto, como mucho cinco operadores AND, OR o NOT y solo los 1000 primeros resultados de cada búsqueda.""")


def construir_consulta(texto: str, tipo: str = "repositories", categoria: str = "libre", valor: str = "",
	lenguaje: str = "", licencia: str = "") -> str:
	"""Versión anterior de la búsqueda guiada (categoría con valor, lenguaje y licencia).

	Se conserva para el historial antiguo y por compatibilidad. La consulta nueva
	la construye ``app.services.busqueda.construir_consulta``.
	"""
	partes = [texto.strip()] if texto.strip() else []
	if tipo == "repositories":
		plantilla = next((c for k, _n, c in CATEGORIAS if k == categoria), "")
		if plantilla:
			if "{v}" in plantilla:
				if valor.strip():
					partes.append(plantilla.format(v=valor.strip()))
			else:
				partes.append(plantilla)
		if licencia:
			partes.append(f"license:{licencia}")
	if lenguaje and tipo in ("repositories", "code", "issues", "users"):
		partes.append(f"language:{lenguaje}")
	return " ".join(partes).strip()


def convertir_entrada_antigua(datos: dict) -> dict:
	"""Filtros nuevos a partir de una entrada del historial de la versión anterior."""
	filtros: dict[str, Any] = {}
	if datos.get("lenguaje"):
		filtros["lenguaje"] = datos["lenguaje"]
	if datos.get("licencia"):
		filtros["licencia"] = datos["licencia"]
	categoria, valor = datos.get("categoria") or "", (datos.get("valor") or "").strip()
	con_valor = {"populares": ("estrellas", 0), "bifurcados": ("bifurcaciones", 0), "recientes": ("envio", 0), "desactualizados": ("envio", 1)}
	if categoria in con_valor:
		if valor:
			clave, posicion = con_valor[categoria]
			par = ["", ""]
			par[posicion] = valor
			filtros[clave] = par
	elif categoria and categoria != "libre":
		atajo = b.valores_atajo(categoria)
		atajo.pop("_orden", None)
		texto = atajo.pop("_texto", "")
		filtros.update(atajo)
		if texto and texto not in (datos.get("texto") or ""):
			filtros["_texto"] = texto
	return filtros


def _entrada(valores: dict) -> dict:
	return {k: valores.get(k) for k in ("tipo", "texto", "filtros", "orden", "direccion", "consulta")}


def guardar_busqueda(padre: wx.Window | None, ctx: Any, valores: dict) -> str | None:
	"""Pide un nombre y guarda la búsqueda en «busqueda.guardadas». Devuelve el nombre o ``None``."""
	if getattr(ctx, "config", None) is None:
		return None
	propuesto = (valores.get("consulta") or "")[:60]
	nombre = pedir_texto(padre, _("&Nombre de la búsqueda:"), _("Guardar la búsqueda"), propuesto)
	if nombre is None or not nombre.strip():
		return None
	nombre = nombre.strip()
	guardadas = list(ctx.config.obtener("busqueda.guardadas", []) or [])
	posicion = next((i for i, g in enumerate(guardadas) if str(g.get("nombre", "")).casefold() == nombre.casefold()), None)
	entrada = dict(_entrada(valores), nombre=nombre)
	if posicion is not None:
		if confirmar(padre, _("Ya hay una búsqueda guardada con el nombre «{n}». ¿Sustituirla?").format(n=nombre),
			_("Guardar la búsqueda")) != wx.ID_YES:
			return None
		guardadas[posicion] = entrada
	else:
		guardadas.append(entrada)
	ctx.config.establecer("busqueda.guardadas", guardadas)
	ctx.avisar(_("Búsqueda «{n}» guardada.").format(n=nombre))
	return nombre


def _etiquetas_de(filtro: b.Filtro) -> list[str]:
	nombre = _(filtro.etiqueta)
	if filtro.control == b.NUMERO:
		return [_("{n}, mínimo:").format(n=nombre), _("{n}, máximo:").format(n=nombre)]
	if filtro.control == b.FECHA:
		return [_("{n}, desde (AAAA-MM-DD):").format(n=nombre), _("{n}, hasta (AAAA-MM-DD):").format(n=nombre)]
	if filtro.control == b.CASILLA:
		return [nombre]
	return [nombre + ":"]


class DialogoBusqueda(wx.Dialog):
	def __init__(self, padre: wx.Window | None, ctx: Any) -> None:
		super().__init__(padre, title=_("Buscar en GitHub"), size=(760, 720), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = ctx
		self.tipos = list(b.TIPOS)
		config = getattr(ctx, "config", None)
		self.historial: list[dict] = list(config.obtener("busqueda.historial", []) or []) if config else []
		self.guardadas: list[dict] = list(config.obtener("busqueda.guardadas", []) or []) if config else []
		self.controles: dict[str, tuple[b.Filtro, list[wx.Window]]] = {}
		self.orden: wx.Choice | None = None
		self.direccion: wx.Choice | None = None
		self._construyendo = False
		raiz = wx.BoxSizer(wx.VERTICAL)

		rejilla = wx.FlexGridSizer(2, self.FromDIP(6), self.FromDIP(8))
		rejilla.AddGrowableCol(1)
		rejilla.Add(wx.StaticText(self, label=_("&Buscar:")), 0, wx.ALIGN_CENTER_VERTICAL)
		self.tipo = wx.Choice(self, choices=[_(n) for n in b.TIPOS.values()])
		self.tipo.SetSelection(0)
		self.tipo.SetHelpText(_("Qué se busca: repositorios, código, issues y pull requests, usuarios, commits, temas, etiquetas, "
			"discusiones o tendencias. Al cambiarlo cambian las pestañas de filtros."))
		self.tipo.Bind(wx.EVT_CHOICE, lambda _e: self._al_cambiar_tipo())
		rejilla.Add(self.tipo, 1, wx.EXPAND)
		rejilla.Add(wx.StaticText(self, label=_("&Texto (admite calificadores):")), 0, wx.ALIGN_CENTER_VERTICAL)
		self.consulta = wx.TextCtrl(self)
		self.consulta.SetHelpText(_("Palabras que buscar y, si quiere, calificadores como language:python o repo:dueño/nombre. "
			"Puede dejarlo vacío si elige algún filtro. En las tendencias de la página de GitHub, filtra los resultados en este equipo."))
		self.consulta.Bind(wx.EVT_TEXT, lambda _e: self._actualizar_resultado())
		rejilla.Add(self.consulta, 1, wx.EXPAND)
		raiz.Add(rejilla, 0, wx.EXPAND | wx.ALL, 8)

		self.libro = wx.Notebook(self)
		self.libro.SetHelpText(_("Filtros guiados. Control+Tabulador pasa a la pestaña siguiente."))
		self._crear_pagina_historial()
		raiz.Add(self.libro, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

		raiz.Add(wx.StaticText(self, label=_("Consulta resu&ltante:")), 0, wx.LEFT | wx.TOP, 8)
		self.resultado = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=self.FromDIP(wx.Size(-1, 90)))
		self.resultado.SetHelpText(_("Lo que se enviará a GitHub, el orden y, si los hay, los problemas que impiden buscar. "
			"Se actualiza al cambiar cualquier filtro."))
		raiz.Add(self.resultado, 0, wx.EXPAND | wx.ALL, 8)

		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_buscar = wx.Button(self, wx.ID_OK, _("B&uscar"))
		self.boton_buscar.SetHelpText(_("Comprueba la consulta y muestra los resultados en la sección «Resultados de la búsqueda»."))
		self.boton_buscar.Bind(wx.EVT_BUTTON, self._al_buscar)
		self.boton_navegador = wx.Button(self, label=_("Abrir en el &navegador"))
		self.boton_navegador.SetHelpText(_("Abre esta búsqueda en github.com. Es la única forma de usar expresiones regulares y symbol: en el código."))
		self.boton_navegador.Bind(wx.EVT_BUTTON, self._al_navegador)
		self.boton_ayuda = wx.Button(self, label=_("E&jemplos de calificadores…"))
		self.boton_ayuda.SetHelpText(_("Explica los calificadores de búsqueda de GitHub con ejemplos."))
		self.boton_ayuda.Bind(wx.EVT_BUTTON, self._al_ayuda)
		self.boton_guardar = wx.Button(self, label=_("Guardar bú&squeda…"))
		self.boton_guardar.SetHelpText(_("Guarda esta búsqueda con un nombre para repetirla desde la pestaña «Historial y guardadas»."))
		self.boton_guardar.Bind(wx.EVT_BUTTON, self._al_guardar)
		self.boton_cancelar = wx.Button(self, wx.ID_CANCEL, _("&Cancelar"))
		self.boton_cancelar.SetHelpText(_("Cierra sin buscar (también con Escape)."))
		for boton in (self.boton_buscar, self.boton_navegador, self.boton_ayuda, self.boton_guardar, self.boton_cancelar):
			botones.Add(boton, 0, wx.RIGHT, 6)
		raiz.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self.boton_buscar.SetDefault()
		self.SetSizer(raiz)
		self._al_cambiar_tipo(conservar=False)
		preparar_dialogo(self, foco_inicial=self.consulta)
		self.CentreOnParent()

	# ── Construcción ──────────────────────────────────────────────────────────

	def _crear_pagina_historial(self) -> None:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(wx.StaticText(pagina, label=_("&Historial de búsquedas:")), 0, wx.LEFT | wx.TOP, 8)
		self.selector_historial = wx.Choice(pagina, choices=[_("(búsqueda nueva)")] + [self._describir(h) for h in self.historial])
		self.selector_historial.SetSelection(0)
		self.selector_historial.SetHelpText(_("Elija una búsqueda anterior para repetirla con los mismos filtros."))
		self.selector_historial.Bind(wx.EVT_CHOICE, self._al_elegir_historial)
		sizer.Add(self.selector_historial, 0, wx.EXPAND | wx.ALL, 8)
		sizer.Add(wx.StaticText(pagina, label=_("Búsquedas &guardadas:")), 0, wx.LEFT | wx.TOP, 8)
		self.selector_guardadas = wx.Choice(pagina)
		self.selector_guardadas.SetHelpText(_("Búsquedas que guardó con un nombre. Al elegir una se cargan su tipo, texto y filtros."))
		self.selector_guardadas.Bind(wx.EVT_CHOICE, self._al_elegir_guardada)
		sizer.Add(self.selector_guardadas, 0, wx.EXPAND | wx.ALL, 8)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_renombrar = wx.Button(pagina, label=_("&Renombrar la guardada…"))
		self.boton_renombrar.SetHelpText(_("Cambia el nombre de la búsqueda guardada elegida."))
		self.boton_renombrar.Bind(wx.EVT_BUTTON, self._al_renombrar)
		self.boton_borrar = wx.Button(pagina, label=_("B&orrar la guardada…"))
		self.boton_borrar.SetHelpText(_("Borra la búsqueda guardada elegida (pide confirmación)."))
		self.boton_borrar.Bind(wx.EVT_BUTTON, self._al_borrar)
		fila.Add(self.boton_renombrar, 0, wx.RIGHT, 6)
		fila.Add(self.boton_borrar)
		sizer.Add(fila, 0, wx.ALL, 8)
		pagina.SetSizer(sizer)
		self.libro.AddPage(pagina, _("Historial y guardadas"))
		self._rellenar_guardadas()

	def _rellenar_guardadas(self, seleccion: int = 0) -> None:
		self.selector_guardadas.Set([_("(ninguna)")] + [f"{g.get('nombre', '')} — {self._describir(g)}" for g in self.guardadas])
		self.selector_guardadas.SetSelection(max(0, min(seleccion, len(self.guardadas))))

	@staticmethod
	def _describir(datos: dict) -> str:
		# Sin tipo conocido no se llama a _(""), que devolvería la cabecera del catálogo.
		clave = datos.get("tipo", "")
		tipo = _(b.TIPOS[clave]) if clave in b.TIPOS else _("Repositorios")
		return f"{tipo}: {datos.get('consulta', '')}"

	def tipo_actual(self) -> str:
		indice = self.tipo.GetSelection()
		return self.tipos[indice] if indice >= 0 else self.tipos[0]

	def _al_cambiar_tipo(self, conservar: bool = True) -> None:
		anteriores = self.valores_filtros() if conservar else {}
		self._construir_filtros(self.tipo_actual())
		if anteriores:
			self._poner_filtros(anteriores)
		self._actualizar_estado_controles()
		self._actualizar_resultado()

	def _construir_filtros(self, tipo: str) -> None:
		# Al cambiar «Buscar» (o cargar una búsqueda del historial) se rehacen las pestañas;
		# wx daría el foco a la primera página y la persona perdería su sitio.
		self._construyendo = True
		self.Freeze()
		foco = wx.Window.FindFocus()
		try:
			while self.libro.GetPageCount() > 1:
				self.libro.DeletePage(0)
			self.controles = {}
			self.orden = self.direccion = None
			filtros = b.filtros_de(tipo)
			for indice, clave_pagina in enumerate(b.paginas_de(tipo)):
				pagina = self._crear_pagina(tipo, clave_pagina, [f for f in filtros if f.pagina == clave_pagina])
				self.libro.InsertPage(indice, pagina, _(b.PAGINAS[clave_pagina]))
			self.libro.ChangeSelection(0)
			self.Layout()
		finally:
			self.Thaw()
			self._construyendo = False
			devolver_foco(self, foco)

	def _crear_pagina(self, tipo: str, clave_pagina: str, filtros: list[b.Filtro]) -> wx.Window:
		pagina = wx.ScrolledWindow(self.libro, style=wx.VSCROLL | wx.TAB_TRAVERSAL)
		pagina.SetScrollRate(0, self.FromDIP(20))
		ordenes = b.ORDENES.get(tipo, [])
		con_orden = clave_pagina == "basico" and len(ordenes) > 1
		textos = [t for f in filtros for t in _etiquetas_de(f)]
		if con_orden:
			textos += [_("&Ordenar por:"), _("&Dirección:")]
		etiquetas = iter(b.asignar_letras(textos, letras_fijas()))
		rejilla = wx.FlexGridSizer(2, self.FromDIP(6), self.FromDIP(8))
		rejilla.AddGrowableCol(1)

		def campo(clase: type, ayuda: str, **opciones: Any) -> wx.Window:
			rejilla.Add(wx.StaticText(pagina, label=next(etiquetas)), 0, wx.ALIGN_CENTER_VERTICAL)
			control = clase(pagina, **opciones)
			control.SetHelpText(ayuda)
			rejilla.Add(control, 1, wx.EXPAND)
			return control

		for filtro in filtros:
			# _("") devolvería la cabecera del catálogo, no una cadena vacía.
			ayuda = _(filtro.ayuda) if filtro.ayuda else _(filtro.etiqueta)
			controles: list[wx.Window] = []
			if filtro.control in (b.TEXTO, b.MAYOR_QUE, b.EXCLUIR):
				control = campo(wx.TextCtrl, ayuda)
				control.Bind(wx.EVT_TEXT, lambda _e: self._actualizar_resultado())
				controles.append(control)
			elif filtro.control in (b.NUMERO, b.FECHA):
				for parte in (_("Mínimo o desde. "), _("Máximo o hasta. ")):
					control = campo(wx.TextCtrl, parte + ayuda)
					control.Bind(wx.EVT_TEXT, lambda _e: self._actualizar_resultado())
					controles.append(control)
			elif filtro.control == b.DESPLEGABLE:
				control = campo(wx.Choice, ayuda, choices=[_(n) for _v, n in filtro.opciones])
				control.SetSelection(0)
				control.Bind(wx.EVT_CHOICE, lambda e, f=filtro: self._al_cambiar_desplegable(f, e))
				controles.append(control)
			elif filtro.control == b.EN:
				rejilla.Add(wx.StaticText(pagina, label=next(etiquetas)), 0, wx.ALIGN_TOP | wx.TOP, 4)
				control = ListaCasillas(pagina, _(filtro.etiqueta), [_(n) for _v, n in filtro.opciones],
					config=getattr(self.ctx, "config", None), size=self.FromDIP(wx.Size(-1, 22 * len(filtro.opciones) + 8)))
				control.SetHelpText(ayuda + " " + _("Espacio marca o desmarca."))
				control.Bind(wx.EVT_CHECKLISTBOX, self._al_marcar_en)
				control.Bind(wx.EVT_KEY_UP, self._al_marcar_en)  # Control+A y Control+Mayúsculas+A no lanzan EVT_CHECKLISTBOX
				rejilla.Add(control, 1, wx.EXPAND)
				controles.append(control)
			elif filtro.control == b.CASILLA:
				rejilla.Add((0, 0))
				control = wx.CheckBox(pagina, label=next(etiquetas))
				control.SetHelpText(ayuda)
				control.Bind(wx.EVT_CHECKBOX, lambda _e: self._actualizar_resultado())
				rejilla.Add(control, 1, wx.EXPAND)
				controles.append(control)
			self.controles[filtro.clave] = (filtro, controles)
		if con_orden:
			self.orden = campo(wx.Choice, _("Orden de los resultados. «Mejor coincidencia» es el de GitHub."),
				choices=[_(n) for _c, n in ordenes])
			self.orden.SetSelection(0)
			self.orden.Bind(wx.EVT_CHOICE, lambda _e: (self._actualizar_estado_controles(), self._actualizar_resultado()))
			self.direccion = campo(wx.Choice, _("Sentido del orden. No se aplica a «Mejor coincidencia»."),
				choices=[_("Descendente (de mayor a menor)"), _("Ascendente (de menor a mayor)")])
			self.direccion.SetSelection(0)
			self.direccion.Bind(wx.EVT_CHOICE, lambda _e: self._actualizar_resultado())
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(rejilla, 1, wx.EXPAND | wx.ALL, 8)
		pagina.SetSizer(marco)
		pagina.SetMinSize(self.FromDIP(wx.Size(640, 300)))
		pagina.FitInside()
		return pagina

	# ── Lectura y escritura de los filtros ────────────────────────────────────

	def valores_filtros(self) -> dict[str, Any]:
		"""Valores de los controles (solo los que tienen algo), listos para el historial."""
		valores: dict[str, Any] = {}
		for clave, (filtro, controles) in self.controles.items():
			if not controles or not controles[0]:
				continue
			if filtro.control in (b.NUMERO, b.FECHA):
				par = [controles[0].GetValue().strip(), controles[1].GetValue().strip()]
				if any(par):
					valores[clave] = par
			elif filtro.control == b.DESPLEGABLE:
				indice = controles[0].GetSelection()
				valor = filtro.opciones[indice][0] if 0 <= indice < len(filtro.opciones) else ""
				if valor:
					valores[clave] = valor
			elif filtro.control == b.EN:
				marcados = [filtro.opciones[i][0] for i in controles[0].GetCheckedItems()]
				if marcados:
					valores[clave] = marcados
			elif filtro.control == b.CASILLA:
				if controles[0].GetValue():
					valores[clave] = True
			else:
				texto = controles[0].GetValue().strip()
				if texto:
					valores[clave] = texto
		return valores

	def _poner_filtros(self, valores: dict[str, Any]) -> None:
		self._construyendo = True
		try:
			texto = valores.get("_texto")
			if texto and texto not in self.consulta.GetValue():
				self.consulta.ChangeValue((self.consulta.GetValue().strip() + " " + texto).strip())
			for clave, valor in valores.items():
				if clave not in self.controles:
					continue
				filtro, controles = self.controles[clave]
				if filtro.control in (b.NUMERO, b.FECHA):
					par = list(valor) if isinstance(valor, (list, tuple)) else [str(valor), ""]
					for control, parte in zip(controles, [*par, "", ""][:2], strict=False):
						control.ChangeValue(str(parte or ""))
				elif filtro.control == b.DESPLEGABLE:
					opciones = [v for v, _n in filtro.opciones]
					if valor in opciones:
						controles[0].SetSelection(opciones.index(valor))
				elif filtro.control == b.EN:
					elegidos = set(valor if isinstance(valor, (list, tuple)) else str(valor).split(","))
					for indice, (opcion, _n) in enumerate(filtro.opciones):
						wx.CheckListBox.Check(controles[0], indice, opcion in elegidos)
				elif filtro.control == b.CASILLA:
					controles[0].SetValue(bool(valor))
				else:
					controles[0].ChangeValue(str(valor or ""))
		finally:
			self._construyendo = False

	def _poner_orden(self, orden: str, direccion: str = "desc") -> None:
		if self.orden is None:
			return
		claves = [c for c, _n in b.ORDENES.get(self.tipo_actual(), [])]
		self.orden.SetSelection(claves.index(orden) if orden in claves else 0)
		if self.direccion is not None:
			self.direccion.SetSelection(1 if direccion == "asc" else 0)

	def control_de(self, clave: str) -> wx.Window | None:
		if clave == "texto":
			return self.consulta
		if clave in self.controles and self.controles[clave][1]:
			return self.controles[clave][1][0]
		return None

	def valores(self) -> dict:
		"""Lo que necesita la ventana para buscar (ver ``app.services.busqueda.preparar_busqueda``)."""
		tipo = self.tipo_actual()
		orden = ""
		if self.orden is not None and self.orden.IsEnabled():
			opciones = b.ORDENES.get(tipo, [])
			indice = self.orden.GetSelection()
			orden = opciones[indice][0] if 0 <= indice < len(opciones) else ""
		direccion = "asc" if self.direccion is not None and self.direccion.GetSelection() == 1 else "desc"
		try:
			host = str(getattr(self.ctx, "host", "") or b.HOST_GITHUB)
		except Exception:  # noqa: BLE001 - sin cuenta el host es el de github.com
			log.debug("No se pudo leer el host de la cuenta.", exc_info=True)
			host = b.HOST_GITHUB
		return b.preparar_busqueda(tipo, self.consulta.GetValue(), self.valores_filtros(), orden, direccion, host=host)

	def problemas(self, datos: dict | None = None) -> list[b.Problema]:
		datos = datos or self.valores()
		return b.validar(datos["tipo"], datos["texto"], datos["filtros"], datos)

	# ── Eventos ───────────────────────────────────────────────────────────────

	def _al_marcar_en(self, evento: wx.CommandEvent) -> None:
		evento.Skip()
		self._actualizar_resultado()

	def _al_cambiar_desplegable(self, filtro: b.Filtro, evento: wx.CommandEvent) -> None:
		if filtro.parametro == "atajo" and not self._construyendo:
			indice = evento.GetSelection()
			clave = filtro.opciones[indice][0] if 0 <= indice < len(filtro.opciones) else ""
			if clave:
				datos = b.valores_atajo(clave)
				orden = datos.pop("_orden", "")
				self._poner_filtros(datos)
				if orden:
					self._poner_orden(orden)
		self._actualizar_estado_controles()
		self._actualizar_resultado()

	def _actualizar_estado_controles(self) -> None:
		"""Activa o desactiva lo que no se aplica (orden en la búsqueda semántica, idioma de tendencias...)."""
		valores = self.valores_filtros()
		semantica = bool(valores.get("search_type"))
		if self.orden is not None:
			if semantica:
				self.orden.SetSelection(0)
			self.orden.Enable(not semantica)
			if self.direccion is not None:
				self.direccion.Enable(not semantica and self.orden.GetSelection() > 0)
		if "idioma" in self.controles:
			self.controles["idioma"][1][0].Enable(valores.get("fuente", "api") == "web_repos")

	def _actualizar_resultado(self) -> None:
		if self._construyendo or not hasattr(self, "resultado"):
			return
		datos = self.valores()
		lineas = []
		if datos["tipo"] == "trending" and datos.get("fuente") != "api":
			lineas.append(_("Se leerá la página {u}").format(u=datos["url_web"]))
			if datos["texto"]:
				lineas.append(_("El texto «{t}» filtra los resultados en este equipo.").format(t=datos["texto"]))
		else:
			lineas.append(datos["consulta"] or _("(consulta vacía)"))
		if datos["orden"]:
			nombre = dict(b.ORDENES.get(datos["tipo"], [])).get(datos["orden"], datos["orden"])
			if datos["tipo"] == "trending":
				nombre = _("Estrellas")
			sentido = _("ascendente") if datos["direccion"] == "asc" else _("descendente")
			lineas.append(_("Orden: {o}, {s}.").format(o=_(nombre), s=sentido))
		if datos.get("search_type"):
			lineas.append(_("Búsqueda {t}: solo issues, sin orden, una sola página y como mucho 10 búsquedas por minuto.").format(
				t=_("semántica") if datos["search_type"] == "semantic" else _("híbrida")))
		if datos["tipo"] == "labels" and datos.get("repositorio"):
			lineas.append(_("En el repositorio {r}.").format(r=datos["repositorio"]))
		if datos["tipo"] == "code":
			lineas.append(_("La API usa la búsqueda de código antigua: para expresiones regulares o symbol: use «Abrir en el navegador»."))
		for problema in self.problemas(datos):
			lineas.append(_("Problema: {m}").format(m=problema.mensaje))
		self.resultado.ChangeValue("\n".join(lineas))

	def _enfocar(self, control: wx.Window | None) -> None:
		if control is None:
			return
		ventana = control.GetParent()
		while ventana is not None and ventana.GetParent() is not self.libro and ventana is not self:
			ventana = ventana.GetParent()
		if ventana is not None and ventana.GetParent() is self.libro:
			indice = self.libro.FindPage(ventana)
			if indice >= 0:
				self.libro.SetSelection(indice)
		control.SetFocus()

	def _al_buscar(self, _evento: wx.CommandEvent | None = None) -> None:
		problemas = self.problemas()
		if problemas:
			mostrar_error(self, "\n".join(p.mensaje for p in problemas), _("Buscar en GitHub"))
			self._enfocar(self.control_de(problemas[0].clave) or self.consulta)
			return
		self.EndModal(wx.ID_OK)

	def _al_navegador(self, _evento: wx.CommandEvent) -> None:
		url = self.valores().get("url_web", "")
		if not url:
			mostrar_error(self, _("Escriba algo que buscar (o elija algún filtro) antes de abrirlo en el navegador."), _("Buscar en GitHub"))
			return
		webbrowser.open(url)

	def _al_ayuda(self, _evento: wx.CommandEvent) -> None:
		from app.ui.dialogo_texto import mostrar_texto

		mostrar_texto(self, _("Ejemplos de búsqueda"), _("&Ejemplos:"), _(AYUDA))

	def _al_guardar(self, _evento: wx.CommandEvent) -> None:
		datos = self.valores()
		if not datos.get("consulta"):
			mostrar_error(self, _("No hay nada que guardar: escriba un texto o elija algún filtro."), _("Guardar la búsqueda"))
			return
		nombre = guardar_busqueda(self, self.ctx, datos)
		if nombre:
			self.guardadas = list(self.ctx.config.obtener("busqueda.guardadas", []) or [])
			posicion = next((i for i, g in enumerate(self.guardadas) if g.get("nombre") == nombre), -1)
			self._rellenar_guardadas(posicion + 1)

	def cargar(self, datos: dict) -> None:
		"""Pone en el diálogo una búsqueda del historial o guardada (también las de la versión anterior)."""
		tipo = datos.get("tipo") if datos.get("tipo") in self.tipos else "repositories"
		self.tipo.SetSelection(self.tipos.index(tipo))
		self._construir_filtros(tipo)
		filtros = datos.get("filtros")
		if filtros is None:
			filtros = convertir_entrada_antigua(datos)
		texto = datos.get("texto")
		if texto is None and not filtros:
			texto = datos.get("consulta", "")
		self.consulta.ChangeValue(texto or "")
		self._poner_filtros(dict(filtros))
		self._poner_orden(datos.get("orden") or "", datos.get("direccion") or "desc")
		self._actualizar_estado_controles()
		self._actualizar_resultado()

	def _al_elegir_historial(self, _evento: wx.CommandEvent) -> None:
		indice = self.selector_historial.GetSelection() - 1
		if 0 <= indice < len(self.historial):
			self.cargar(self.historial[indice])

	def _al_elegir_guardada(self, _evento: wx.CommandEvent) -> None:
		indice = self.selector_guardadas.GetSelection() - 1
		if 0 <= indice < len(self.guardadas):
			self.cargar(self.guardadas[indice])

	def _guardada_elegida(self) -> int | None:
		indice = self.selector_guardadas.GetSelection() - 1
		if 0 <= indice < len(self.guardadas):
			return indice
		mostrar_error(self, _("Elija primero una búsqueda en «Búsquedas guardadas»."), _("Búsquedas guardadas"))
		self.selector_guardadas.SetFocus()
		return None

	def _al_renombrar(self, _evento: wx.CommandEvent) -> None:
		indice = self._guardada_elegida()
		if indice is None:
			return
		actual = self.guardadas[indice].get("nombre", "")
		nombre = pedir_texto(self, _("&Nombre nuevo:"), _("Renombrar la búsqueda guardada"), actual)
		if nombre is None or not nombre.strip() or nombre.strip() == actual:
			return
		nombre = nombre.strip()
		if any(i != indice and str(g.get("nombre", "")).casefold() == nombre.casefold() for i, g in enumerate(self.guardadas)):
			mostrar_error(self, _("Ya hay otra búsqueda guardada con el nombre «{n}».").format(n=nombre), _("Renombrar la búsqueda guardada"))
			return
		self.guardadas[indice] = dict(self.guardadas[indice], nombre=nombre)
		self.ctx.config.establecer("busqueda.guardadas", self.guardadas)
		self._rellenar_guardadas(indice + 1)
		self.ctx.avisar(_("Renombrada a «{n}».").format(n=nombre))

	def _al_borrar(self, _evento: wx.CommandEvent) -> None:
		indice = self._guardada_elegida()
		if indice is None:
			return
		nombre = self.guardadas[indice].get("nombre", "")
		if confirmar(self, _("¿Borrar la búsqueda guardada «{n}»? No se puede deshacer.").format(n=nombre),
			_("Borrar la búsqueda guardada"), peligroso=True) != wx.ID_YES:
			return
		del self.guardadas[indice]
		self.ctx.config.establecer("busqueda.guardadas", self.guardadas)
		self._rellenar_guardadas(0)
		self.selector_guardadas.SetFocus()
		self.ctx.avisar(_("Búsqueda «{n}» borrada.").format(n=nombre))

	def guardar_en_historial(self, valores: dict) -> None:
		if getattr(self.ctx, "config", None) is None:
			return
		entrada = _entrada(valores)
		historial = [h for h in self.historial if h.get("consulta") != entrada["consulta"] or h.get("tipo") != entrada["tipo"]]
		historial.insert(0, entrada)
		self.ctx.config.establecer("busqueda.historial", historial[:MAXIMO_HISTORIAL])


def dialogo_busqueda(padre: wx.Window | None, ctx: Any) -> dict | None:
	"""Muestra el diálogo y devuelve los datos de la búsqueda (o ``None`` si se cancela)."""
	dialogo = DialogoBusqueda(padre, ctx)
	try:
		if dialogo.ShowModal() != wx.ID_OK:
			return None
		valores = dialogo.valores()
		dialogo.guardar_en_historial(valores)
		return valores
	finally:
		dialogo.Destroy()
