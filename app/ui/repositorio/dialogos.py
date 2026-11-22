"""Diálogos del repositorio: crear, vigilar, configurar y formularios auxiliares.

Todos siguen las mismas reglas de accesibilidad:

- Etiqueta (``wx.StaticText``) creada JUSTO ANTES de cada campo, con el mismo
  padre (``crear_campo``), y ayuda contextual (Ctrl+H) en cada control.
- Letras de acceso sin repetir en cada pantalla, contando «&Aceptar» y
  «&Cancelar» (y, con pestañas, cada página junto con lo que queda fuera).
- Escape cierra, foco inicial en el primer campo útil (``preparar_dialogo``).
- Las llamadas a GitHub van en segundo plano (``en_segundo_plano``). Si el
  envío falla, el formulario se vuelve a abrir con lo escrito: nada se pierde
  por un error de red.
"""

from __future__ import annotations

import builtins
import colorsys
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import wx

from app.services import formato as f
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.comunes import (
	ListaCasillas,
	confirmar,
	confirmar_peligro,
	en_segundo_plano,
	mensaje_error,
	mostrar_error,
	pedir_texto,
)

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _vivo(ventana: wx.Window | None) -> wx.Window | None:
	"""La ventana si sigue existiendo; ``None`` si ya se destruyó (un resultado puede llegar tarde)."""
	try:
		return ventana if ventana and not ventana.IsBeingDeleted() else None
	except RuntimeError:
		log.debug("La ventana padre ya no existe", exc_info=True)
		return None


# ════════════════════════════════════════════════════════════════════════════
# Base de los formularios
# ════════════════════════════════════════════════════════════════════════════


class Formulario(wx.Dialog):
	"""Diálogo con campos, «Aceptar» que valida antes de cerrar y «Cancelar».

	Las subclases crean sus campos con ``campo`` y ``casilla`` (en orden: la
	etiqueta siempre antes de su control), y definen ``valores`` y ``comprobar``.
	"""

	def __init__(self, padre: wx.Window | None, titulo: str) -> None:
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.raiz = wx.BoxSizer(wx.VERTICAL)

	def campo(self, etiqueta: str, fabrica: Callable[..., Any], ayuda: str, padre: wx.Window | None = None,
		sizer: wx.Sizer | None = None, **kwargs: Any) -> Any:
		_texto, control = crear_campo(padre or self, etiqueta, fabrica, ayuda=ayuda, sizer=sizer or self.raiz, **kwargs)
		return control

	def casilla(self, etiqueta: str, valor: Any, ayuda: str, padre: wx.Window | None = None,
		sizer: wx.Sizer | None = None) -> wx.CheckBox:
		control = wx.CheckBox(padre or self, label=etiqueta)
		control.SetValue(bool(valor))
		control.SetHelpText(ayuda)
		(sizer or self.raiz).Add(control, 0, wx.ALL, 5)
		return control

	def terminar(self, foco: wx.Window | None, ancho: int = 460) -> None:
		self.raiz.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self.SetSizer(self.raiz)
		self.raiz.SetMinSize(self.FromDIP(wx.Size(ancho, -1)))
		self.Fit()
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		preparar_dialogo(self, foco_inicial=foco)
		self.CentreOnParent()

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		error, control = self.comprobar()
		if error:
			mostrar_error(self, error, _("Revise los datos"))
			if control is not None:
				control.SetFocus()
			return
		evento.Skip()

	def comprobar(self) -> tuple[str, wx.Window | None]:
		"""Devuelve ``(mensaje de error, control que lo tiene)`` o ``("", None)`` si todo está bien."""
		return "", None

	def valores(self) -> dict:
		raise NotImplementedError


def formulario_modal(
	padre: wx.Window | None,
	ctx: Any,
	crear: Callable[[dict | None], Formulario],
	enviar: Callable[[dict], Any],
	*,
	exito: str | Callable[[Any], str] = "",
	al_terminar: Callable[[Any], None] | None = None,
	inicio: str = "",
	titulo_error: str = "",
	valores: dict | None = None,
) -> bool:
	"""Muestra un formulario y envía sus valores en segundo plano.

	Si GitHub rechaza el envío, se explica el error y el formulario se vuelve a
	abrir con lo que había escrito. Devuelve ``False`` si se canceló.
	"""
	dialogo = crear(valores)
	try:
		if dialogo.ShowModal() != wx.ID_OK:
			return False
		datos = dialogo.valores()
		error, _control = dialogo.comprobar()
	finally:
		dialogo.Destroy()

	def repetir() -> None:
		formulario_modal(padre, ctx, crear, enviar, exito=exito, al_terminar=al_terminar, inicio=inicio,
			titulo_error=titulo_error, valores=datos)

	if error:
		mostrar_error(_vivo(padre), error, _("Revise los datos"))
		repetir()
		return True

	def fallo(problema: BaseException) -> None:
		log.warning("Falló el envío de un formulario: %s", mensaje_error(problema))
		mostrar_error(_vivo(padre), mensaje_error(problema), titulo_error or _("No se pudo completar"))
		repetir()

	en_segundo_plano(padre, ctx, lambda: enviar(datos), exito=exito, al_terminar=al_terminar, al_fallar=fallo, inicio=inicio)
	return True


def _indice(valores: list, valor: Any, defecto: int = 0) -> int:
	return valores.index(valor) if valor in valores else defecto


# ════════════════════════════════════════════════════════════════════════════
# Crear repositorio
# ════════════════════════════════════════════════════════════════════════════


class DialogoCrearRepositorio(Formulario):
	"""Nombre, descripción, visibilidad, propietario, README, .gitignore, licencia y plantilla."""

	def __init__(self, padre: wx.Window | None, usuario: str, organizaciones: list[str], gitignores: list[str],
		licencias: list[tuple[str, str]], valores: dict | None = None) -> None:
		super().__init__(padre, _("Nuevo repositorio"))
		v = valores or {}
		self.duenos = [usuario] + [o for o in organizaciones if o and o != usuario]
		self.gitignores = [""] + list(gitignores)
		self.licencias = [("", _("(ninguna)"))] + list(licencias)

		self.dueno = self.campo(_("&Propietario:"), wx.Choice, _("Su cuenta o una de sus organizaciones."),
			choices=[d or _("(su cuenta)") for d in self.duenos])
		self.dueno.SetSelection(_indice(self.duenos, v.get("dueno", usuario)))
		self.nombre = self.campo(_("&Nombre del repositorio:"), wx.TextCtrl,
			_("Nombre corto, sin espacios: letras, números, guiones, puntos y guiones bajos."), value=v.get("nombre", ""))
		self.descripcion = self.campo(_("&Descripción (opcional):"), wx.TextCtrl, _("Una frase que explique de qué trata."),
			value=v.get("descripcion", ""))
		self.visibilidad = self.campo(_("&Visibilidad:"), wx.Choice,
			_("Público: lo ve cualquiera. Privado: solo usted y quien invite."), choices=[_("Público"), _("Privado")])
		self.visibilidad.SetSelection(1 if v.get("privado") else 0)
		self.readme = self.casilla(_("&Inicializar con un archivo README"), v.get("readme", True),
			_("Crea el repositorio con un primer commit que contiene un README.md."))
		self.gitignore = self.campo(_("Plantilla .&gitignore:"), wx.Choice,
			_("Archivos que git debe ignorar según el lenguaje o la herramienta."),
			choices=[g or _("(ninguna)") for g in self.gitignores])
		self.gitignore.SetSelection(_indice(self.gitignores, v.get("gitignore", "")))
		self.licencia = self.campo(_("&Licencia:"), wx.Choice, _("Licencia de uso del código."),
			choices=[n for _c, n in self.licencias])
		self.licencia.SetSelection(_indice([c for c, _n in self.licencias], v.get("licencia", "")))
		self.plantilla = self.campo(_("Crear a partir de la plan&tilla (dueño/nombre; opcional):"), wx.TextCtrl,
			_("Si escribe un repositorio plantilla, el nuevo se crea copiándolo; README, .gitignore y licencia se ignoran."),
			value=v.get("plantilla", ""))
		self.todas_ramas = self.casilla(_("Copiar todas las &ramas de la plantilla"), v.get("todas_ramas", False),
			_("Solo con plantilla: copia todas sus ramas y no solo la principal."))
		self.terminar(self.nombre)

	def valores(self) -> dict:
		indice_lic = self.licencia.GetSelection()
		return {
			"dueno": self.duenos[max(0, self.dueno.GetSelection())],
			"nombre": self.nombre.GetValue().strip(),
			"descripcion": self.descripcion.GetValue().strip(),
			"privado": self.visibilidad.GetSelection() == 1,
			"readme": self.readme.GetValue(),
			"gitignore": self.gitignores[max(0, self.gitignore.GetSelection())],
			"licencia": self.licencias[max(0, indice_lic)][0],
			"plantilla": self.plantilla.GetValue().strip().strip("/"),
			"todas_ramas": self.todas_ramas.GetValue(),
		}

	def comprobar(self) -> tuple[str, wx.Window | None]:
		datos = self.valores()
		if not datos["nombre"]:
			return _("Escriba el nombre del repositorio."), self.nombre
		if not re.fullmatch(r"[A-Za-z0-9._-]+", datos["nombre"]):
			return _("El nombre solo puede tener letras sin tilde, números, guiones, puntos y guiones bajos."), self.nombre
		if datos["plantilla"] and "/" not in datos["plantilla"]:
			return _("La plantilla debe tener la forma «dueño/nombre»."), self.plantilla
		return "", None


def dialogo_crear_repositorio(padre: wx.Window | None, ctx: Any, al_crear: Callable[[dict], None] | None = None) -> None:
	"""Pide los datos de un repositorio nuevo y lo crea en GitHub.

	Primero carga (en segundo plano) las organizaciones, las plantillas de
	.gitignore y las licencias; si alguna falla, el diálogo se abre igual sin ella.
	"""
	api = ctx.api()
	usuario = ctx.usuario

	def cargar() -> dict:
		datos: dict[str, list] = {}
		for clave, funcion in (("orgs", api.mis_organizaciones), ("gitignore", api.plantillas_gitignore),
			("licencias", api.licencias)):
			try:
				datos[clave] = list(funcion() or [])
			except Exception:  # noqa: BLE001 - sin esa lista el diálogo sigue siendo útil
				log.warning("No se pudo cargar %s para el diálogo de nuevo repositorio", clave, exc_info=True)
				datos[clave] = []
		return datos

	def mostrar(datos: dict) -> None:
		organizaciones = [o.get("login", "") for o in datos["orgs"] if isinstance(o, dict)]
		gitignores = [g for g in datos["gitignore"] if isinstance(g, str)]
		licencias = [(l.get("key", ""), f"{l.get('name', '')} ({l.get('spdx_id') or l.get('key', '')})")
			for l in datos["licencias"] if isinstance(l, dict)]

		def crear(valores: dict | None) -> Formulario:
			return DialogoCrearRepositorio(_vivo(padre), usuario, organizaciones, gitignores, licencias, valores)

		def enviar(v: dict) -> dict:
			if v["plantilla"]:
				return api.crear_desde_plantilla(v["plantilla"], v["dueno"], v["nombre"], v["descripcion"], v["privado"],
					v["todas_ramas"])
			return api.crear_repositorio(
				v["nombre"], v["descripcion"], v["privado"], org="" if v["dueno"] == usuario else v["dueno"],
				auto_init=v["readme"], gitignore=v["gitignore"], licencia=v["licencia"],
			)

		def creado(repo: Any) -> None:
			if al_crear is not None:
				al_crear(repo)

		formulario_modal(padre, ctx, crear, enviar, inicio=_("Creando el repositorio…"), al_terminar=creado,
			exito=lambda r: _("Repositorio {n} creado.").format(n=(r or {}).get("full_name", "") if isinstance(r, dict) else ""),
			titulo_error=_("No se pudo crear el repositorio"))

	en_segundo_plano(padre, ctx, cargar, al_terminar=mostrar, sonido="", inicio=_("Preparando el formulario…"))


# ════════════════════════════════════════════════════════════════════════════
# Vigilancia
# ════════════════════════════════════════════════════════════════════════════

OPCIONES_VIGILANCIA = [
	("no", N_("&No vigilar"),
		N_("No recibe avisos de la actividad general. En GitHub equivale a «solo participando»: le seguirán llegando "
		"los avisos de lo que usted abra, comente o donde le mencionen.")),
	("participando", N_("Solo cuando &participe o me mencionen"),
		N_("Solo recibe avisos de las conversaciones en las que participa o le mencionan (lo normal en GitHub).")),
	("todo", N_("&Toda la actividad"), N_("Recibe avisos de todas las issues, pull requests, releases y discusiones.")),
	("ignorar", N_("&Ignorar (ningún aviso)"), N_("No recibe ningún aviso de este repositorio, ni siquiera si le mencionan.")),
]


def estado_vigilancia(suscripcion: dict | None) -> str:
	"""Traduce la respuesta de ``api.suscripcion`` a una clave de ``OPCIONES_VIGILANCIA``."""
	if not suscripcion:
		return "participando"
	if suscripcion.get("ignored"):
		return "ignorar"
	if suscripcion.get("subscribed"):
		return "todo"
	return "participando"


class DialogoVigilancia(Formulario):
	def __init__(self, padre: wx.Window | None, nombre: str, actual: str) -> None:
		super().__init__(padre, _("Vigilar {n}").format(n=nombre))
		caja = wx.StaticBoxSizer(wx.VERTICAL, self, _("Avisos que quiere recibir de {n}").format(n=nombre))
		grupo = caja.GetStaticBox()
		self.botones: list[tuple[str, wx.RadioButton]] = []
		for posicion, (clave, etiqueta, ayuda) in enumerate(OPCIONES_VIGILANCIA):
			boton = wx.RadioButton(grupo, label=_(etiqueta), style=wx.RB_GROUP if posicion == 0 else 0)
			boton.SetHelpText(_(ayuda))
			boton.SetValue(clave == actual)
			caja.Add(boton, 0, wx.ALL, 4)
			self.botones.append((clave, boton))
		self.raiz.Add(caja, 0, wx.EXPAND | wx.ALL, 8)
		elegido = next((b for c, b in self.botones if c == actual), self.botones[0][1])
		self.terminar(elegido)

	def valores(self) -> dict:
		return {"opcion": next((c for c, b in self.botones if b.GetValue()), "participando")}


def aplicar_vigilancia(api: Any, nombre: str, opcion: str) -> None:
	"""Llama a la API según la opción elegida."""
	if opcion == "todo":
		api.vigilar(nombre, suscrito=True, ignorado=False)
	elif opcion == "ignorar":
		api.vigilar(nombre, suscrito=False, ignorado=True)
	else:
		api.dejar_de_vigilar(nombre)


def dialogo_vigilancia(padre: wx.Window | None, ctx: Any, nombre: str) -> None:
	"""Pregunta cómo vigilar el repositorio (con la opción actual marcada) y lo aplica."""
	api = ctx.api()
	textos = {"no": _("Ya no vigila {n}."), "participando": _("Solo recibirá avisos de {n} cuando participe o le mencionen."),
		"todo": _("Vigila toda la actividad de {n}."), "ignorar": _("Ignora {n}: no recibirá avisos.")}

	def mostrar(suscripcion: Any) -> None:
		actual = estado_vigilancia(suscripcion if isinstance(suscripcion, dict) else None)
		elegida: dict[str, str] = {}

		def enviar(v: dict) -> None:
			# El aviso final depende de la opción elegida: se guarda aquí.
			elegida["opcion"] = v["opcion"]
			aplicar_vigilancia(api, nombre, v["opcion"])

		formulario_modal(
			padre, ctx, lambda v: DialogoVigilancia(_vivo(padre), nombre, (v or {}).get("opcion", actual)), enviar,
			exito=lambda _r: textos.get(elegida.get("opcion", ""), "").format(n=nombre),
			titulo_error=_("No se pudo cambiar la vigilancia"),
		)

	def fallo(error: BaseException) -> None:
		# Sin saber el estado actual se puede elegir igual: se parte de «solo participando».
		log.warning("No se pudo leer la suscripción de %s: %s", nombre, mensaje_error(error))
		mostrar(None)

	en_segundo_plano(padre, ctx, lambda: api.suscripcion(nombre), al_terminar=mostrar, al_fallar=fallo, sonido="")


# ════════════════════════════════════════════════════════════════════════════
# Configuración del repositorio
# ════════════════════════════════════════════════════════════════════════════

CAMPOS_GENERALES = ("name", "description", "homepage", "default_branch", "has_issues", "has_wiki", "has_projects",
	"has_discussions", "is_template")
CAMPOS_FUSION = ("allow_merge_commit", "allow_squash_merge", "allow_rebase_merge", "allow_auto_merge",
	"delete_branch_on_merge", "allow_update_branch")


def _temas(texto: str) -> list[str]:
	"""«Python, wx  accesibilidad» → ["python", "wx", "accesibilidad"] (GitHub los quiere en minúsculas)."""
	return [t.strip().lower().replace(" ", "-") for t in re.split(r"[,;\s]+", texto) if t.strip()]


class DialogoConfiguracion(wx.Dialog):
	"""Configuración del repositorio en tres pestañas: General, Fusiones y Zona peligrosa.

	Los botones de la zona peligrosa actúan al momento (cada uno con su
	confirmación); «Aceptar» guarda solo lo que haya cambiado en las otras dos.
	"""

	def __init__(self, padre: wx.Window | None, ctx: Any, nombre: str, repo: dict, ramas: list[str],
		al_desaparecer: Callable[[str], None] | None = None) -> None:
		super().__init__(padre, title=_("Configuración de {n}").format(n=nombre),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = ctx
		self.nombre = nombre
		self.repo = dict(repo or {})
		self.al_desaparecer = al_desaparecer
		self.desaparecido = ""
		self.ramas = list(ramas) or [self.repo.get("default_branch", "") or "main"]
		if self.repo.get("default_branch") and self.repo["default_branch"] not in self.ramas:
			self.ramas.insert(0, self.repo["default_branch"])
		raiz = wx.BoxSizer(wx.VERTICAL)
		# La etiqueta de las pestañas: sin letra (Control+Tabulador cambia de pestaña).
		raiz.Add(wx.StaticText(self, label=_("Pestañas de la configuración (Control+Tabulador cambia de pestaña):")),
			0, wx.LEFT | wx.TOP, 8)
		self.libro = wx.Notebook(self)
		self.libro.AddPage(self._pagina_general(), _("General"))
		self.libro.AddPage(self._pagina_fusiones(), _("Fusiones"))
		self.libro.AddPage(self._pagina_peligro(), _("Zona peligrosa"))
		self._iniciales = self.leer()
		raiz.Add(self.libro, 1, wx.EXPAND | wx.ALL, 8)
		raiz.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self.SetSizer(raiz)
		raiz.SetMinSize(self.FromDIP(wx.Size(560, -1)))
		self.Fit()
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		preparar_dialogo(self, foco_inicial=self.campo_nombre)
		self.CentreOnParent()

	# ── Páginas ───────────────────────────────────────────────────────────────

	def _pagina_general(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		r = self.repo

		def campo(etiqueta: str, fabrica: Any, ayuda: str, **kwargs: Any) -> Any:
			return crear_campo(pagina, etiqueta, fabrica, ayuda=ayuda, sizer=sizer, **kwargs)[1]

		def casilla(etiqueta: str, valor: Any, ayuda: str) -> wx.CheckBox:
			control = wx.CheckBox(pagina, label=etiqueta)
			control.SetValue(bool(valor))
			control.SetHelpText(ayuda)
			sizer.Add(control, 0, wx.ALL, 4)
			return control

		self.campo_nombre = campo(_("&Nombre:"), wx.TextCtrl, _("Cambiar el nombre cambia la dirección del repositorio; "
			"GitHub redirige la antigua."), value=r.get("name", ""))
		self.campo_descripcion = campo(_("&Descripción:"), wx.TextCtrl, _("Frase que describe el repositorio."),
			value=r.get("description") or "")
		self.campo_web = campo(_("Sitio &web:"), wx.TextCtrl, _("Dirección de la página del proyecto (opcional)."),
			value=r.get("homepage") or "")
		self.campo_temas = campo(_("&Temas (separados por comas):"), wx.TextCtrl,
			_("Palabras clave para encontrar el repositorio, en minúsculas y sin espacios."),
			value=", ".join(r.get("topics") or []))
		self.visibilidades = ["public", "private"] + (["internal"] if r.get("visibility") == "internal" else [])
		self.campo_visibilidad = campo(_("&Visibilidad:"), wx.Choice, _("Quién puede ver el repositorio."),
			choices=[f.estado(v) for v in self.visibilidades])
		self.campo_visibilidad.SetSelection(_indice(self.visibilidades, r.get("visibility") or
			("private" if r.get("private") else "public")))
		self.campo_rama = campo(_("&Rama por defecto:"), wx.Choice,
			_("Rama que se muestra al entrar y contra la que se abren los pull requests."), choices=self.ramas)
		self.campo_rama.SetSelection(_indice(self.ramas, r.get("default_branch", "")))
		self.casilla_issues = casilla(_("&Issues"), r.get("has_issues", True), _("Activa la pestaña de issues."))
		self.casilla_wiki = casilla(_("Wi&ki"), r.get("has_wiki", False), _("Activa la wiki del repositorio."))
		self.casilla_proyectos = casilla(_("&Proyectos"), r.get("has_projects", False), _("Activa los proyectos del repositorio."))
		self.casilla_discusiones = casilla(_("Discusi&ones"), r.get("has_discussions", False),
			_("Activa el foro de discusiones."))
		self.casilla_plantilla = casilla(_("Es una p&lantilla"), r.get("is_template", False),
			_("Permite crear repositorios nuevos copiando este."))
		pagina.SetSizer(sizer)
		return pagina

	def _pagina_fusiones(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		r = self.repo
		sizer.Add(wx.StaticText(pagina, label=_("Cómo se pueden fusionar los pull requests:")), 0, wx.ALL, 6)
		self.casillas_fusion: dict[str, wx.CheckBox] = {}
		for clave, etiqueta, ayuda, defecto in (
			("allow_merge_commit", _("Permitir commits de &fusión (merge)"), _("Une las ramas con un commit de fusión."), True),
			("allow_squash_merge", _("Permitir fusión con &squash"), _("Junta todos los commits del pull request en uno."), True),
			("allow_rebase_merge", _("Permitir &rebase"), _("Reaplica los commits sobre la rama base sin commit de fusión."), True),
			("allow_auto_merge", _("Permitir la fusión au&tomática"),
				_("Los pull requests pueden fusionarse solos cuando pasen las comprobaciones."), False),
			("delete_branch_on_merge", _("&Borrar la rama al fusionar"), _("Borra la rama del pull request al fusionarlo."), False),
			("allow_update_branch", _("Sugerir actuali&zar la rama de los pull requests"),
				_("Ofrece actualizar la rama cuando la base ha avanzado."), False),
		):
			control = wx.CheckBox(pagina, label=etiqueta)
			control.SetValue(bool(r.get(clave, defecto)))
			control.SetHelpText(ayuda)
			sizer.Add(control, 0, wx.ALL, 4)
			self.casillas_fusion[clave] = control
		pagina.SetSizer(sizer)
		return pagina

	def _pagina_peligro(self) -> wx.Panel:
		pagina = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(wx.StaticText(pagina, label=_("Estas acciones se aplican al momento y piden confirmación.")), 0, wx.ALL, 6)
		self.boton_archivar = wx.Button(pagina, label=self._etiqueta_archivar())
		self.boton_archivar.SetHelpText(_("Un repositorio archivado queda en solo lectura; se puede desarchivar después."))
		self.boton_archivar.Bind(wx.EVT_BUTTON, lambda _e: self.archivar())
		self.boton_transferir = wx.Button(pagina, label=_("&Transferir a otra cuenta…"))
		self.boton_transferir.SetHelpText(_("Pasa el repositorio a otra persona u organización."))
		self.boton_transferir.Bind(wx.EVT_BUTTON, lambda _e: self.transferir())
		self.boton_borrar = wx.Button(pagina, label=_("&Borrar el repositorio…"))
		self.boton_borrar.SetHelpText(_("Borra el repositorio para siempre. Pide escribir su nombre para confirmar."))
		self.boton_borrar.Bind(wx.EVT_BUTTON, lambda _e: self.borrar())
		for boton in (self.boton_archivar, self.boton_transferir, self.boton_borrar):
			sizer.Add(boton, 0, wx.ALL, 6)
		pagina.SetSizer(sizer)
		return pagina

	def _etiqueta_archivar(self) -> str:
		return _("Desarc&hivar el repositorio…") if self.repo.get("archived") else _("Arc&hivar el repositorio…")

	# ── Valores ───────────────────────────────────────────────────────────────

	def leer(self) -> dict:
		"""Valores actuales de todos los controles, con las claves de la API."""
		valores: dict[str, Any] = {
			"name": self.campo_nombre.GetValue().strip(),
			"description": self.campo_descripcion.GetValue().strip(),
			"homepage": self.campo_web.GetValue().strip(),
			"topics": _temas(self.campo_temas.GetValue()),
			"visibility": self.visibilidades[max(0, self.campo_visibilidad.GetSelection())],
			"default_branch": self.ramas[max(0, self.campo_rama.GetSelection())],
			"has_issues": self.casilla_issues.GetValue(),
			"has_wiki": self.casilla_wiki.GetValue(),
			"has_projects": self.casilla_proyectos.GetValue(),
			"has_discussions": self.casilla_discusiones.GetValue(),
			"is_template": self.casilla_plantilla.GetValue(),
		}
		for clave, control in self.casillas_fusion.items():
			valores[clave] = control.GetValue()
		return valores

	def cambios(self) -> dict:
		"""Solo lo que la persona ha cambiado respecto a como se abrió el diálogo.

		Se compara con los valores iniciales de los controles (no con la respuesta
		de GitHub): si GitHub no envía un campo, no se manda «cambiado» por error.
		"""
		return {clave: valor for clave, valor in self.leer().items() if valor != self._iniciales.get(clave)}

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		cambios = self.cambios()
		if "name" in cambios and not re.fullmatch(r"[A-Za-z0-9._-]+", cambios["name"] or ""):
			mostrar_error(self, _("El nombre solo puede tener letras sin tilde, números, guiones, puntos y guiones bajos."),
				_("Revise los datos"))
			self.libro.SetSelection(0)
			self.campo_nombre.SetFocus()
			return
		if "visibility" in cambios and confirmar(
			self, _("¿Cambiar la visibilidad a «{v}»? Si lo hace privado, se pierden las estrellas y observadores públicos.").format(
				v=f.estado(cambios["visibility"])), _("Cambiar la visibilidad"), peligroso=True) != wx.ID_YES:
			return
		evento.Skip()

	# ── Zona peligrosa ────────────────────────────────────────────────────────

	def _cerrar(self, codigo: int) -> None:
		if self.IsModal():
			self.EndModal(codigo)
		else:
			self.SetReturnCode(codigo)

	def archivar(self) -> None:
		archivar = not self.repo.get("archived")
		pregunta = (_("¿Archivar {n}? Quedará en solo lectura: no se podrán enviar commits, abrir issues ni comentar.")
			if archivar else _("¿Desarchivar {n}? Volverá a admitir cambios."))
		if confirmar(self, pregunta.format(n=self.nombre), _("Archivar"), peligroso=True) != wx.ID_YES:
			return
		api = self.ctx.api()

		def hecho(repo: Any) -> None:
			self.repo["archived"] = archivar
			if self:
				self.boton_archivar.SetLabel(self._etiqueta_archivar())

		en_segundo_plano(self, self.ctx, lambda: api.editar_repositorio(self.nombre, archived=archivar), al_terminar=hecho,
			exito=(_("Repositorio archivado.") if archivar else _("Repositorio desarchivado.")))

	def transferir(self) -> None:
		destino = pedir_texto(self, _("&Nueva cuenta propietaria (usuario u organización):"), _("Transferir el repositorio"))
		if not destino or not destino.strip():
			return
		destino = destino.strip()
		if not confirmar_peligro(self, _("¿Transferir {n} a {d}? Perderá el control si no tiene permisos allí.").format(
			n=self.nombre, d=destino), _("Transferir el repositorio"), self.nombre):
			return
		api = self.ctx.api()

		def hecho(_r: Any) -> None:
			self.desaparecido = _("transferido a {d}").format(d=destino)
			self._cerrar(wx.ID_CANCEL)
			if self.al_desaparecer:
				self.al_desaparecer(self.desaparecido)

		en_segundo_plano(self, self.ctx, lambda: api.transferir(self.nombre, destino), al_terminar=hecho,
			exito=_("Transferencia pedida. GitHub puede pedir a la otra cuenta que la acepte."))

	def borrar(self) -> None:
		if not confirmar_peligro(self, _("¿Borrar DEFINITIVAMENTE el repositorio {n}? Se perderá todo: código, issues, "
			"pull requests, wiki y releases. No se puede deshacer.").format(n=self.nombre), _("Borrar el repositorio"), self.nombre):
			return
		api = self.ctx.api()

		def hecho(_r: Any) -> None:
			self.desaparecido = _("borrado")
			self._cerrar(wx.ID_CANCEL)
			if self.al_desaparecer:
				self.al_desaparecer(self.desaparecido)

		en_segundo_plano(self, self.ctx, lambda: api.borrar_repositorio(self.nombre), al_terminar=hecho,
			exito=_("Repositorio {n} borrado.").format(n=self.nombre))


def guardar_configuracion(api: Any, nombre: str, cambios: dict) -> dict:
	"""Aplica los cambios (los temas van por otra ruta de la API). Devuelve el repositorio actualizado."""
	cambios = dict(cambios)
	temas = cambios.pop("topics", None)
	repo: Any = None
	if cambios:
		repo = api.editar_repositorio(nombre, **cambios)
	nombre_actual = (repo or {}).get("full_name", nombre) if isinstance(repo, dict) else nombre
	if temas is not None:
		api.poner_temas(nombre_actual, temas)
	if not isinstance(repo, dict):
		repo = api.repositorio(nombre_actual)
	if temas is not None and isinstance(repo, dict):
		repo = dict(repo, topics=temas)
	return repo if isinstance(repo, dict) else {}


def dialogo_configuracion(padre: wx.Window | None, ctx: Any, nombre: str, al_guardar: Callable[[dict], None] | None = None,
	al_desaparecer: Callable[[str], None] | None = None) -> None:
	"""Abre la configuración del repositorio (carga primero sus datos y sus ramas).

	:param al_guardar: recibe el repositorio actualizado tras guardar.
	:param al_desaparecer: se llama si el repositorio se transfiere o se borra
		(la ventana del repositorio debe cerrarse).
	"""
	api = ctx.api()

	def cargar() -> tuple[dict, list[str]]:
		repo = api.repositorio(nombre)
		try:
			ramas = [r.get("name", "") for r in api.todas_las_ramas(nombre) or [] if isinstance(r, dict)]
		except Exception:  # noqa: BLE001 - sin ramas solo se ofrece la actual
			log.warning("No se pudieron cargar las ramas de %s", nombre, exc_info=True)
			ramas = []
		return repo if isinstance(repo, dict) else {}, ramas

	def mostrar(resultado: tuple[dict, list[str]]) -> None:
		repo, ramas = resultado
		dialogo = DialogoConfiguracion(_vivo(padre), ctx, nombre, repo, ramas, al_desaparecer)
		try:
			if dialogo.ShowModal() != wx.ID_OK or dialogo.desaparecido:
				return
			cambios = dialogo.cambios()
		finally:
			dialogo.Destroy()
		if not cambios:
			ctx.avisar(_("No había cambios que guardar."))
			return
		en_segundo_plano(padre, ctx, lambda: guardar_configuracion(api, nombre, cambios),
			al_terminar=lambda r: al_guardar(r) if al_guardar else None, exito=_("Configuración guardada."),
			titulo_error=_("No se pudo guardar la configuración"))

	en_segundo_plano(padre, ctx, cargar, al_terminar=mostrar, sonido="", inicio=_("Cargando la configuración…"))


# ════════════════════════════════════════════════════════════════════════════
# Formularios auxiliares
# ════════════════════════════════════════════════════════════════════════════


class DialogoProteccion(Formulario):
	"""Reglas de protección de una rama (las que admite ``api.proteger``)."""

	def __init__(self, padre: wx.Window | None, rama: str, actual: dict | None = None, valores: dict | None = None) -> None:
		super().__init__(padre, _("Proteger la rama {r}").format(r=rama))
		v = valores or proteccion_a_valores(actual)
		self.revisiones = self.campo(_("&Revisiones aprobadas necesarias (0 = no hace falta pull request):"), wx.SpinCtrl,
			_("Cuántas aprobaciones necesita un pull request para fusionarse en esta rama."), min=0, max=6,
			initial=int(v.get("revisiones", 1)))
		self.checks = self.campo(_("Compro&baciones de estado obligatorias (separadas por comas):"), wx.TextCtrl,
			_("Nombres de las comprobaciones (por ejemplo, de Actions) que deben pasar antes de fusionar. Vacío = ninguna."),
			value=", ".join(v.get("checks") or []))
		self.admins = self.casilla(_("Aplicar también a los a&dministradores"), v.get("admins"),
			_("Si no se marca, quien administra el repositorio puede saltarse las reglas."))
		self.lineal = self.casilla(_("Exigir historial &lineal"), v.get("historial_lineal"),
			_("Prohíbe los commits de fusión en esta rama."))
		self.forzar = self.casilla(_("Permitir envíos &forzados"), v.get("forzar"), _("Permite git push --force a la rama."))
		self.borrar = self.casilla(_("Permitir b&orrar la rama"), v.get("borrar"), _("Permite borrar la rama protegida."))
		self.conversaciones = self.casilla(_("Exigir resolver las con&versaciones"), v.get("conversaciones"),
			_("Todas las conversaciones de revisión deben estar resueltas para fusionar."))
		self.firmas = self.casilla(_("Exigir commits fir&mados"), v.get("firmas"), _("Solo admite commits con firma verificada."))
		self.terminar(self.revisiones)

	def valores(self) -> dict:
		return {
			"revisiones": self.revisiones.GetValue(),
			"checks": [c.strip() for c in self.checks.GetValue().split(",") if c.strip()],
			"admins": self.admins.GetValue(),
			"historial_lineal": self.lineal.GetValue(),
			"forzar": self.forzar.GetValue(),
			"borrar": self.borrar.GetValue(),
			"conversaciones": self.conversaciones.GetValue(),
			"firmas": self.firmas.GetValue(),
		}


def proteccion_a_valores(proteccion: dict | None) -> dict:
	"""Convierte la protección que devuelve GitHub en los valores del formulario."""
	if not proteccion:
		return {"revisiones": 1, "checks": []}

	def activo(clave: str) -> bool:
		valor = proteccion.get(clave)
		return bool(valor.get("enabled")) if isinstance(valor, dict) else bool(valor)

	revisiones = proteccion.get("required_pull_request_reviews") or {}
	checks = proteccion.get("required_status_checks") or {}
	return {
		"revisiones": int(revisiones.get("required_approving_review_count", 0) or 0) if revisiones else 0,
		"checks": list(checks.get("contexts") or []),
		"admins": activo("enforce_admins"),
		"historial_lineal": activo("required_linear_history"),
		"forzar": activo("allow_force_pushes"),
		"borrar": activo("allow_deletions"),
		"conversaciones": activo("required_conversation_resolution"),
		"firmas": activo("required_signatures"),
	}


EVENTOS_WEBHOOK = [
	("push", N_("push (envíos de commits)")), ("pull_request", N_("pull_request (pull requests)")), ("issues", "issues"),
	("issue_comment", N_("issue_comment (comentarios)")), ("release", "release"), ("workflow_run", N_("workflow_run (Actions)")),
	("create", N_("create (ramas o etiquetas creadas)")), ("delete", N_("delete (ramas o etiquetas borradas)")),
	("pull_request_review", N_("pull_request_review (revisiones)")), ("discussion", N_("discussion (discusiones)")),
	("star", N_("star (estrellas)")), ("fork", N_("fork (bifurcaciones)")), ("deployment", N_("deployment (despliegues)")),
	("status", N_("status (estados de commits)")), ("*", N_("* (todos los eventos)")),
]


class DialogoWebhook(Formulario):
	def __init__(self, padre: wx.Window | None, config: Any, webhook: dict | None = None, valores: dict | None = None) -> None:
		super().__init__(padre, _("Cambiar el webhook") if webhook else _("Nuevo webhook"))
		self.editando = webhook is not None
		w = webhook or {}
		v = valores or {
			"url": (w.get("config") or {}).get("url", ""), "tipo": (w.get("config") or {}).get("content_type", "json"),
			"secreto": "", "eventos": list(w.get("events") or ["push"]), "activo": w.get("active", True),
		}
		self.url = self.campo(_("&URL de destino:"), wx.TextCtrl, _("Dirección https que recibirá los avisos de GitHub."),
			value=v.get("url", ""))
		self.tipos = ["json", "form"]
		self.tipo = self.campo(_("&Tipo de contenido:"), wx.Choice, _("Formato en que GitHub envía los datos."),
			choices=[_("JSON (application/json)"), _("Formulario (application/x-www-form-urlencoded)")])
		self.tipo.SetSelection(_indice(self.tipos, v.get("tipo", "json")))
		self.secreto = self.campo(
			_("&Secreto (déjelo vacío para no cambiarlo):") if self.editando else _("&Secreto (opcional):"), wx.TextCtrl,
			_("Clave para firmar los avisos y comprobar que vienen de GitHub."), value=v.get("secreto", ""),
			style=wx.TE_PASSWORD)
		self.claves_eventos = [c for c, _n in EVENTOS_WEBHOOK]
		# ListaCasillas recibe su nombre como parámetro: no pasa por crear_campo (que añadiría otro «name»).
		self.raiz.Add(wx.StaticText(self, label=_("&Eventos:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		self.eventos = ListaCasillas(self, _("Eventos"), [_(n) for _c, n in EVENTOS_WEBHOOK], config=config,
			size=self.FromDIP(wx.Size(-1, 180)))
		self.eventos.SetHelpText(_("Marque con Espacio los eventos que quiere recibir.") + " " + self.eventos.GetHelpText())
		self.raiz.Add(self.eventos, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
		for clave in v.get("eventos") or []:
			if clave in self.claves_eventos:
				wx.CheckListBox.Check(self.eventos, self.claves_eventos.index(clave), True)
		if self.eventos.GetCount():
			self.eventos.SetSelection(0)
		self.activo = self.casilla(_("Act&ivo"), v.get("activo", True), _("Si no se marca, GitHub no envía nada."))
		self.terminar(self.url)

	def valores(self) -> dict:
		return {
			"url": self.url.GetValue().strip(),
			"tipo": self.tipos[max(0, self.tipo.GetSelection())],
			"secreto": self.secreto.GetValue(),
			"eventos": [self.claves_eventos[i] for i in self.eventos.GetCheckedItems()],
			"activo": self.activo.GetValue(),
		}

	def comprobar(self) -> tuple[str, wx.Window | None]:
		datos = self.valores()
		if not re.match(r"https?://", datos["url"]):
			return _("Escriba una URL que empiece por https://."), self.url
		if not datos["eventos"]:
			return _("Marque al menos un evento."), self.eventos
		return "", None


class DialogoSecreto(Formulario):
	"""Secreto (cifrado, no se puede leer después) o variable de Actions."""

	def __init__(self, padre: wx.Window | None, tipo: str = "secreto", nombre: str = "", valor: str = "",
		editando: bool = False, valores: dict | None = None) -> None:
		v = valores or {"tipo": tipo, "nombre": nombre, "valor": valor}
		super().__init__(padre, _("Cambiar {n}").format(n=nombre) if editando else _("Nuevo secreto o variable"))
		self.tipos = ["secreto", "variable"]
		self.tipo = self.campo(_("&Tipo:"), wx.Choice,
			_("Secreto: cifrado, nadie puede leerlo después. Variable: visible para quien tenga acceso."),
			choices=[_("Secreto (cifrado)"), _("Variable (visible)")])
		self.tipo.SetSelection(_indice(self.tipos, v.get("tipo", "secreto")))
		self.tipo.Enable(not editando)
		self.nombre = self.campo(_("&Nombre:"), wx.TextCtrl, _("En mayúsculas, con letras, números y guiones bajos."),
			value=v.get("nombre", ""))
		self.nombre.SetEditable(not editando)
		self.valor = self.campo(
			_("&Valor (no se mostrará después):") if v.get("tipo") == "secreto" else _("&Valor:"), wx.TextCtrl,
			_("Contenido. Puede tener varias líneas (por ejemplo, una clave privada)."), value=v.get("valor", ""),
			style=wx.TE_MULTILINE, size=self.FromDIP(wx.Size(-1, 110)))
		self.terminar(self.valor if editando else self.nombre)

	def valores(self) -> dict:
		return {"tipo": self.tipos[max(0, self.tipo.GetSelection())], "nombre": self.nombre.GetValue().strip().upper(),
			"valor": self.valor.GetValue()}

	def comprobar(self) -> tuple[str, wx.Window | None]:
		datos = self.valores()
		if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", datos["nombre"]) or datos["nombre"].startswith("GITHUB_"):
			return _("El nombre solo puede tener letras sin tilde, números y guiones bajos, no puede empezar por un número "
				"ni por GITHUB_."), self.nombre
		if not datos["valor"]:
			return _("Escriba el valor."), self.valor
		return "", None


class DialogoClaveDespliegue(Formulario):
	def __init__(self, padre: wx.Window | None, valores: dict | None = None) -> None:
		super().__init__(padre, _("Nueva clave de despliegue"))
		v = valores or {}
		self.titulo = self.campo(_("&Título:"), wx.TextCtrl, _("Nombre para reconocer la clave (por ejemplo, el servidor)."),
			value=v.get("titulo", ""))
		self.clave = self.campo(_("Clave &pública (por ejemplo, ssh-ed25519 AAAA…):"), wx.TextCtrl,
			_("Contenido del archivo .pub de la clave SSH."), value=v.get("clave", ""), style=wx.TE_MULTILINE,
			size=self.FromDIP(wx.Size(-1, 90)))
		self.escritura = self.casilla(_("Permitir &escritura (envíos)"), v.get("escritura", False),
			_("Si no se marca, la clave solo puede leer (clonar)."))
		self.terminar(self.titulo)

	def valores(self) -> dict:
		return {"titulo": self.titulo.GetValue().strip(), "clave": self.clave.GetValue().strip(),
			"escritura": self.escritura.GetValue()}

	def comprobar(self) -> tuple[str, wx.Window | None]:
		datos = self.valores()
		if not datos["titulo"]:
			return _("Escriba un título."), self.titulo
		if not datos["clave"].startswith(("ssh-", "ecdsa-", "sk-")):
			return _("Pegue una clave pública SSH (empieza por ssh-ed25519, ssh-rsa, ecdsa-…)."), self.clave
		return "", None


def nombre_color(hexadecimal: str) -> str:
	"""Nombre aproximado de un color («d73a4a» → «rojo»): el código solo no dice nada a quien no ve."""
	texto = (hexadecimal or "").strip().lstrip("#")
	if not re.fullmatch(r"[0-9a-fA-F]{6}", texto):
		return ""
	r, g, b = (int(texto[i:i + 2], 16) / 255 for i in (0, 2, 4))
	tono, luz, saturacion = colorsys.rgb_to_hls(r, g, b)
	if luz > 0.93:
		return _("blanco")
	if luz < 0.12:
		return _("negro")
	if saturacion < 0.15:
		return _("gris claro") if luz > 0.6 else _("gris oscuro") if luz < 0.35 else _("gris")
	grados = tono * 360
	nombres = ((15, N_("rojo")), (40, N_("naranja")), (65, N_("amarillo")), (160, N_("verde")), (195, N_("turquesa")), (255, N_("azul")),
		(290, N_("morado")), (335, N_("rosa")), (360, N_("rojo")))
	base = next(_(n) for limite, n in nombres if grados < limite)
	if luz > 0.75:
		return _("{c} claro").format(c=base)
	if luz < 0.3:
		return _("{c} oscuro").format(c=base)
	return base


class DialogoLabel(Formulario):
	"""Etiqueta de issues (label): nombre, color y descripción."""

	def __init__(self, padre: wx.Window | None, label: dict | None = None, valores: dict | None = None) -> None:
		super().__init__(padre, _("Cambiar la etiqueta") if label else _("Nueva etiqueta"))
		l = label or {}
		v = valores or {"nombre": l.get("name", ""), "color": l.get("color", "ededed"), "descripcion": l.get("description") or ""}
		self.nombre = self.campo(_("&Nombre:"), wx.TextCtrl, _("Texto de la etiqueta (puede tener espacios y emojis)."),
			value=v.get("nombre", ""))
		self.color = self.campo(_("C&olor (hexadecimal, por ejemplo d73a4a):"), wx.TextCtrl,
			_("Seis cifras hexadecimales. Debajo se dice el nombre aproximado del color."), value=v.get("color", ""))
		self.boton_color = wx.Button(self, label=_("&Elegir el color…"))
		self.boton_color.SetHelpText(_("Abre el selector de colores de Windows."))
		self.boton_color.Bind(wx.EVT_BUTTON, lambda _e: self._elegir_color())
		self.raiz.Add(self.boton_color, 0, wx.ALL, 5)
		self.nombre_del_color = wx.StaticText(self, label="")
		self.raiz.Add(self.nombre_del_color, 0, wx.ALL, 5)
		self.descripcion = self.campo(_("&Descripción:"), wx.TextCtrl, _("Para qué sirve la etiqueta (opcional)."),
			value=v.get("descripcion", ""))
		self.color.Bind(wx.EVT_TEXT, lambda _e: self._actualizar_nombre())
		self._actualizar_nombre()
		self.terminar(self.nombre)

	def _actualizar_nombre(self) -> None:
		nombre = nombre_color(self.color.GetValue())
		self.nombre_del_color.SetLabel(_("Color: {c}.").format(c=nombre) if nombre else _("Color no válido."))

	def _elegir_color(self) -> None:
		datos = wx.ColourData()
		texto = self.color.GetValue().strip().lstrip("#")
		if re.fullmatch(r"[0-9a-fA-F]{6}", texto):
			datos.SetColour(wx.Colour(f"#{texto}"))
		dialogo = wx.ColourDialog(self, datos)
		try:
			if dialogo.ShowModal() == wx.ID_OK:
				color = dialogo.GetColourData().GetColour()
				self.color.SetValue(f"{color.Red():02x}{color.Green():02x}{color.Blue():02x}")
		finally:
			dialogo.Destroy()
		self.color.SetFocus()

	def valores(self) -> dict:
		return {"nombre": self.nombre.GetValue().strip(), "color": self.color.GetValue().strip().lstrip("#").lower(),
			"descripcion": self.descripcion.GetValue().strip()}

	def comprobar(self) -> tuple[str, wx.Window | None]:
		datos = self.valores()
		if not datos["nombre"]:
			return _("Escriba el nombre de la etiqueta."), self.nombre
		if not re.fullmatch(r"[0-9a-f]{6}", datos["color"]):
			return _("El color debe tener seis cifras hexadecimales, por ejemplo d73a4a."), self.color
		return "", None


def fecha_a_iso(texto: str) -> str | None:
	"""«31/12/2025» o «2025-12-31» → «2025-12-31T12:00:00Z». ``""`` si está vacío; ``None`` si no es válida.

	Se usa el mediodía UTC para que GitHub no muestre el día anterior por la zona horaria.
	"""
	texto = (texto or "").strip()
	if not texto:
		return ""
	for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
		try:
			return datetime.strptime(texto, formato).strftime("%Y-%m-%dT12:00:00Z")
		except ValueError:
			continue
	return None


class DialogoHito(Formulario):
	def __init__(self, padre: wx.Window | None, hito: dict | None = None, valores: dict | None = None) -> None:
		super().__init__(padre, _("Cambiar el hito") if hito else _("Nuevo hito"))
		h = hito or {}
		fecha = h.get("due_on") or ""
		v = valores or {"titulo": h.get("title", ""), "descripcion": h.get("description") or "",
			"fecha": f.fecha_completa(fecha).split(" ")[0] if fecha else "", "estado": h.get("state", "open")}
		self.titulo = self.campo(_("&Título:"), wx.TextCtrl, _("Nombre del hito (por ejemplo, «Versión 2.0»)."),
			value=v.get("titulo", ""))
		self.descripcion = self.campo(_("&Descripción:"), wx.TextCtrl, _("Explicación del hito (opcional)."),
			value=v.get("descripcion", ""), style=wx.TE_MULTILINE, size=self.FromDIP(wx.Size(-1, 80)))
		self.fecha = self.campo(_("&Fecha límite (DD/MM/AAAA; opcional):"), wx.TextCtrl,
			_("Día en que debería estar terminado. Déjelo vacío si no tiene fecha."), value=v.get("fecha", ""))
		self.estados = ["open", "closed"]
		self.estado = self.campo(_("&Estado:"), wx.Choice, _("Un hito cerrado ya no se ofrece al asignar issues."),
			choices=[_("Abierto"), _("Cerrado")])
		self.estado.SetSelection(_indice(self.estados, v.get("estado", "open")))
		self.terminar(self.titulo)

	def valores(self) -> dict:
		return {"titulo": self.titulo.GetValue().strip(), "descripcion": self.descripcion.GetValue().strip(),
			"fecha": self.fecha.GetValue().strip(), "estado": self.estados[max(0, self.estado.GetSelection())]}

	def comprobar(self) -> tuple[str, wx.Window | None]:
		datos = self.valores()
		if not datos["titulo"]:
			return _("Escriba el título del hito."), self.titulo
		if fecha_a_iso(datos["fecha"]) is None:
			return _("La fecha debe tener la forma DD/MM/AAAA, por ejemplo 31/12/2025."), self.fecha
		return "", None


class DialogoEntorno(Formulario):
	def __init__(self, padre: wx.Window | None, entorno: dict | None = None, valores: dict | None = None) -> None:
		super().__init__(padre, _("Cambiar el entorno") if entorno else _("Nuevo entorno"))
		e = entorno or {}
		espera = next((r.get("wait_timer", 0) for r in e.get("protection_rules") or [] if r.get("type") == "wait_timer"), 0)
		politica = e.get("deployment_branch_policy") or {}
		v = valores or {"nombre": e.get("name", ""), "espera": espera, "protegidas": bool(politica.get("protected_branches"))}
		self.nombre = self.campo(_("&Nombre:"), wx.TextCtrl, _("Por ejemplo: production, staging, github-pages."),
			value=v.get("nombre", ""))
		self.nombre.SetEditable(entorno is None)
		self.espera = self.campo(_("&Tiempo de espera antes de desplegar (minutos):"), wx.SpinCtrl,
			_("Minutos que espera un trabajo antes de desplegar en este entorno (0 = sin espera)."), min=0, max=43200,
			initial=int(v.get("espera", 0) or 0))
		self.protegidas = self.casilla(_("Solo pueden desplegar las ramas &protegidas"), v.get("protegidas"),
			_("Limita los despliegues a las ramas con reglas de protección."))
		self.terminar(self.nombre if entorno is None else self.espera)

	def valores(self) -> dict:
		return {"nombre": self.nombre.GetValue().strip(), "espera": self.espera.GetValue(), "protegidas": self.protegidas.GetValue()}

	def comprobar(self) -> tuple[str, wx.Window | None]:
		if not self.valores()["nombre"]:
			return _("Escriba el nombre del entorno."), self.nombre
		return "", None

	@staticmethod
	def reglas(valores: dict) -> dict:
		"""Parámetros para ``api.crear_entorno``."""
		politica = {"protected_branches": True, "custom_branch_policies": False} if valores.get("protegidas") else None
		return {"wait_timer": int(valores.get("espera") or 0), "deployment_branch_policy": politica}
