"""Configuración GLOBAL de git (``git config --global``) y ruta de git.exe.

- Muestra la versión de git o, si no está instalado, explica cómo instalarlo.
- La ruta de git.exe se guarda en la configuración de la aplicación
  (``git.ruta``) y se aplica al momento con ``git_local.establecer_ruta_git``.
- Los valores se leen y se escriben en segundo plano; solo se escriben los que
  cambian. Un campo vacío (o «(sin configurar)») quita la clave
  (``git config --global --unset``, que no está en ``git_local``: se usa
  ``operaciones.quitar_config_global``).
"""

from __future__ import annotations

import builtins
import logging
from typing import Any

import wx

from app.services import git_local
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_selector_ruta
from app.ui.comunes import en_segundo_plano
from app.ui.git import operaciones as op

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


SIN_CONFIGURAR = ""

#: (valor, texto) de cada desplegable; «» = sin configurar.
OPCIONES = {
	"core.autocrlf": [
		(SIN_CONFIGURAR, N_("(sin configurar)")),
		("true", N_("true: convertir a CRLF de Windows al extraer y a LF al guardar")),
		("input", N_("input: convertir a LF solo al guardar")),
		("false", N_("false: no convertir nunca")),
	],
	"pull.rebase": [
		(SIN_CONFIGURAR, N_("(sin configurar)")),
		("false", N_("false: fusionar (merge)")),
		("true", N_("true: reorganizar (rebase)")),
		("merges", N_("merges: reorganizar conservando las fusiones")),
	],
	"gpg.format": [
		(SIN_CONFIGURAR, N_("(sin configurar: openpgp)")),
		("openpgp", N_("openpgp: claves GPG")),
		("ssh", N_("ssh: claves SSH")),
		("x509", N_("x509: certificados S/MIME")),
	],
}

CLAVES = ("user.name", "user.email", "init.defaultBranch", "core.autocrlf", "pull.rebase", "commit.gpgsign", "gpg.format",
	"user.signingkey", "credential.helper")

TEXTO_SIN_GIT = N_(
	"Git no está instalado o no se encuentra.\n"
	"Instale Git for Windows desde https://git-scm.com/download/win (o con «winget install --id Git.Git -e»). "
	"Si lo tiene en otra carpeta, escriba abajo la ruta de git.exe."
)


class DialogoConfiguracionGit(wx.Dialog):
	def __init__(self, padre: wx.Window | None, contexto: Any) -> None:
		super().__init__(padre, title=_("Configuración de git"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = contexto
		self.iniciales: dict[str, str] = {}
		self.codigo_salida = wx.ID_NONE
		self.cargado = False
		raiz = wx.BoxSizer(wx.VERTICAL)

		raiz.Add(wx.StaticText(self, label=_("&Versión de git:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
		self.campo_version = wx.TextCtrl(self, value=_("Comprobando…"), style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
			size=(self.FromDIP(520), self.FromDIP(60)))
		self.campo_version.SetHelpText(_("Versión de git que usa la aplicación o cómo instalarlo."))
		raiz.Add(self.campo_version, 0, wx.EXPAND | wx.ALL, 6)

		_e, self.campo_ruta, self.boton_ruta = crear_selector_ruta(
			self, _("R&uta de git.exe (vacía = detectar):"), carpeta=False, valor=str(contexto.config.obtener("git.ruta", "") or ""),
			comodin=_("git.exe|git.exe|Programas (*.exe)|*.exe"), ayuda=_("Solo hace falta si git no está en el PATH."), sizer=raiz)

		self.campos: dict[str, wx.Window] = {}
		self._texto("user.name", _("&Nombre (user.name):"), _("Nombre que aparece como autor de sus commits."), raiz)
		self._texto("user.email", _("C&orreo (user.email):"), _(
			"Correo de sus commits. Para no publicarlo, use el correo noreply de GitHub (ID+usuario@users.noreply.github.com)."), raiz)
		self._texto("init.defaultBranch", _("&Rama inicial de los repositorios nuevos (init.defaultBranch):"),
			_("Nombre de la primera rama al crear un repositorio, por ejemplo main."), raiz)
		self._opcion("core.autocrlf", _("Fina&les de línea (core.autocrlf):"), _("Cómo convierte git los finales de línea en Windows."), raiz)
		self._opcion("pull.rebase", _("Al &tirar (pull.rebase):"), _("Qué hace git al tirar si su rama y la remota han divergido."), raiz)
		self.casilla_firmar = wx.CheckBox(self, label=_("F&irmar siempre los commits (commit.gpgsign)"))
		self.casilla_firmar.SetHelpText(_("Firma todos los commits con su clave GPG o SSH."))
		raiz.Add(self.casilla_firmar, 0, wx.ALL, 6)
		self._opcion("gpg.format", _("&Formato de la firma (gpg.format):"), _("Tipo de clave con la que se firma."), raiz)
		self._texto("user.signingkey", _("Clave de fir&ma (user.signingkey):"), _(
			"Identificador de la clave GPG o ruta del archivo .pub de la clave SSH con la que firmar."), raiz)
		self._texto("credential.helper", _("Ayudante de cr&edenciales (credential.helper):"), _(
			"Programa que guarda sus contraseñas de git; con Git for Windows suele ser «manager»."), raiz)

		raiz.Add(crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		self.SetSizerAndFit(raiz)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.guardar(), id=wx.ID_OK)
		preparar_dialogo(self, foco_inicial=self.campos["user.name"])
		self.CentreOnParent()
		self.cargar()

	def _texto(self, clave: str, etiqueta: str, ayuda: str, sizer: wx.Sizer) -> None:
		sizer.Add(wx.StaticText(self, label=etiqueta), 0, wx.LEFT | wx.RIGHT, 6)
		control = wx.TextCtrl(self)
		control.SetHelpText(ayuda)
		sizer.Add(control, 0, wx.EXPAND | wx.ALL, 6)
		self.campos[clave] = control

	def _opcion(self, clave: str, etiqueta: str, ayuda: str, sizer: wx.Sizer) -> None:
		sizer.Add(wx.StaticText(self, label=etiqueta), 0, wx.LEFT | wx.RIGHT, 6)
		control = wx.Choice(self, choices=[_(texto) for _v, texto in OPCIONES[clave]])
		control.SetSelection(0)
		control.SetHelpText(ayuda)
		sizer.Add(control, 0, wx.EXPAND | wx.ALL, 6)
		self.campos[clave] = control

	# ── Datos ─────────────────────────────────────────────────────────────────

	def cargar(self) -> None:
		def trabajo() -> tuple[str, dict[str, str]]:
			ruta = str(self.ctx.config.obtener("git.ruta", "") or "")
			if ruta:
				git_local.establecer_ruta_git(ruta)
			if not git_local.git_disponible():
				return "", {}
			return git_local.version_git(), {clave: git_local.config_global(clave) for clave in CLAVES}

		en_segundo_plano(self, self.ctx, trabajo, al_terminar=self._mostrar, sonido="")

	def _mostrar(self, resultado: tuple[str, dict[str, str]]) -> None:
		if not self:
			return
		version, valores = resultado
		self.cargado = True
		if not version:
			self.campo_version.SetValue(_(TEXTO_SIN_GIT))
			for control in [*self.campos.values(), self.casilla_firmar]:
				control.Disable()
			return
		ruta = git_local.buscar_git(str(self.ctx.config.obtener("git.ruta", "") or "")) or ""
		self.campo_version.SetValue(_("{v}\nEn {r}").format(v=version, r=ruta))
		self.iniciales = dict(valores)
		for clave, control in self.campos.items():
			valor = valores.get(clave, "")
			if isinstance(control, wx.Choice):
				opciones = [v for v, _t in OPCIONES[clave]]
				control.SetSelection(opciones.index(valor.lower()) if valor.lower() in opciones else 0)
			else:
				control.SetValue(valor)
		self.casilla_firmar.SetValue(valores.get("commit.gpgsign", "").lower() == "true")

	def valores(self) -> dict[str, str]:
		resultado: dict[str, str] = {}
		for clave, control in self.campos.items():
			if isinstance(control, wx.Choice):
				resultado[clave] = OPCIONES[clave][max(0, control.GetSelection())][0]
			else:
				resultado[clave] = control.GetValue().strip()
		inicial_firma = self.iniciales.get("commit.gpgsign", "")
		marcada = self.casilla_firmar.GetValue()
		# Sin tocar la casilla, una clave ausente sigue ausente.
		resultado["commit.gpgsign"] = inicial_firma if (inicial_firma.lower() == "true") == marcada else ("true" if marcada else "false")
		return resultado

	def guardar(self) -> None:
		ruta = self.campo_ruta.GetValue().strip()
		self.ctx.config.establecer("git.ruta", ruta)
		git_local.establecer_ruta_git(ruta)
		cambios = {k: v for k, v in self.valores().items() if v != self.iniciales.get(k, "")} if self.cargado and self.iniciales else {}

		def trabajo() -> None:
			for clave, valor in cambios.items():
				if valor:
					git_local.establecer_config_global(clave, valor)
				else:
					op.quitar_config_global(clave)

		def listo(_r: Any) -> None:
			if self:
				self.codigo_salida = wx.ID_OK
				if self.IsModal():
					self.EndModal(wx.ID_OK)

		en_segundo_plano(self, self.ctx, trabajo, al_terminar=listo,
			exito=_("Configuración de git guardada ({n} cambios).").format(n=len(cambios)) if cambios else _("Configuración guardada."),
			titulo_error=_("No se pudo guardar la configuración de git"))


def abrir_configuracion_git(ctx: Any, padre: wx.Window | None) -> int:
	"""Abre el diálogo de forma modal y devuelve ``wx.ID_OK`` o ``wx.ID_CANCEL``."""
	dialogo = DialogoConfiguracionGit(padre, ctx)
	try:
		return dialogo.ShowModal()
	finally:
		dialogo.Destroy()
