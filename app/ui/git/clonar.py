"""Diálogo accesible para clonar un repositorio con progreso hablado y cancelable.

- Acepta una URL completa, una carpeta local o «dueño/repo» (que se convierte
  en ``https://HOST/dueño/repo.git`` o ``git@HOST:dueño/repo.git`` según el
  protocolo elegido).
- Carpeta de destino con el selector accesible (campo + «Examinar…»); por
  defecto la de Preferencias (``git.carpeta_clonado``) o Documentos.
- El clonado va en segundo plano: el progreso se puede consultar en
  «Pro&greso:» y se anuncia por hitos; «Cancelar» lo detiene (y borra la
  carpeta a medio clonar si la creó este diálogo).
- Al terminar: se añade a «Repositorios locales», se llama a ``al_clonar`` y se
  ofrece abrir la ventana de git.
- Sin git instalado explica cómo instalar Git for Windows y ofrece descargar
  el código en zip con la API de GitHub.
"""

from __future__ import annotations

import builtins
import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx

from app.services import git_local
from app.ui.accesibilidad.dialogos import crear_botonera, elegir_opcion, preparar_dialogo
from app.ui.accesibilidad.nombres import crear_selector_ruta
from app.ui.comunes import confirmar, en_segundo_plano, mensaje_error, mostrar_error, pedir_texto
from app.ui.git import operaciones as op
from app.ui.git.progreso_red import PanelProgresoGit

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


PROTOCOLOS = ("https", "ssh")

MENSAJE_SIN_GIT = N_(
	"Para clonar hace falta Git, y no está instalado (o no se encuentra).\n\n"
	"Cómo instalarlo:\n"
	"1. Descargue Git for Windows desde https://git-scm.com/download/win, o en una consola escriba: "
	"winget install --id Git.Git -e\n"
	"2. Instálelo con las opciones por defecto y vuelva a abrir la aplicación.\n"
	"3. Si lo tiene en otra carpeta, indique la ruta de git.exe en Herramientas, Configuración de git.\n\n"
	"Mientras tanto puede descargar el código en un archivo zip (sin historial ni ramas)."
)


def carpeta_por_defecto(ctx: Any) -> str:
	configurada = str(ctx.config.obtener("git.carpeta_clonado", "") or "")
	if configurada:
		return configurada
	try:
		return wx.StandardPaths.Get().GetDocumentsDir()
	except Exception:  # noqa: BLE001 - sin wx.App no hay rutas estándar
		log.debug("Sin carpeta de Documentos", exc_info=True)
		return str(Path.home() / "Documents")


class DialogoClonar(wx.Dialog):
	def __init__(self, padre: wx.Window | None, contexto: Any, url: str = "", nombre: str = "",
		al_clonar: Callable[[str], None] | None = None) -> None:
		super().__init__(padre, title=_("Clonar un repositorio"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = contexto
		self.al_clonar = al_clonar
		self.clonando = False
		self.carpeta_clonada = ""
		self.abrir_despues = False
		self.codigo_salida = wx.ID_NONE
		self._nombre_tocado = False

		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=_("&URL o dueño/repositorio:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
		self.campo_url = wx.TextCtrl(self, value=url or nombre, size=(self.FromDIP(460), -1))
		self.campo_url.SetHelpText(_(
			"Dirección del repositorio (https://… o git@…), una carpeta local o simplemente «dueño/repositorio»."))
		raiz.Add(self.campo_url, 0, wx.EXPAND | wx.ALL, 6)

		raiz.Add(wx.StaticText(self, label=_("&Protocolo:")), 0, wx.LEFT | wx.RIGHT, 6)
		self.selector_protocolo = wx.Choice(self, choices=[_("HTTPS (con el token de su cuenta)"), _("SSH (con su clave SSH)")])
		self.selector_protocolo.SetSelection(1 if (url or "").startswith(("git@", "ssh://")) else 0)
		self.selector_protocolo.SetHelpText(_("Cómo se conecta git con GitHub cuando escribe «dueño/repositorio»."))
		raiz.Add(self.selector_protocolo, 0, wx.EXPAND | wx.ALL, 6)

		_etiqueta, self.campo_carpeta, self.boton_examinar = crear_selector_ruta(
			self, _("Carpeta de &destino:"), carpeta=True, valor=carpeta_por_defecto(contexto),
			ayuda=_("Carpeta en la que se creará la carpeta del repositorio."), sizer=raiz)

		raiz.Add(wx.StaticText(self, label=_("&Nombre de la carpeta nueva:")), 0, wx.LEFT | wx.RIGHT, 6)
		self.campo_nombre = wx.TextCtrl(self, value=op.nombre_carpeta(url or nombre))
		self.campo_nombre.SetHelpText(_("Nombre de la carpeta del repositorio dentro de la carpeta de destino."))
		raiz.Add(self.campo_nombre, 0, wx.EXPAND | wx.ALL, 6)

		raiz.Add(wx.StaticText(self, label=_("&Rama (vacía = la principal):")), 0, wx.LEFT | wx.RIGHT, 6)
		self.campo_rama = wx.TextCtrl(self)
		self.campo_rama.SetHelpText(_("Rama o etiqueta que se extrae al clonar."))
		raiz.Add(self.campo_rama, 0, wx.EXPAND | wx.ALL, 6)

		raiz.Add(wx.StaticText(self, label=_("Pro&fundidad (0 = historial completo):")), 0, wx.LEFT | wx.RIGHT, 6)
		self.campo_profundidad = wx.SpinCtrl(self, min=0, max=1000000, initial=0)
		self.campo_profundidad.SetHelpText(_("Número de commits recientes que se descargan (clon superficial). 0 descarga todo el historial."))
		raiz.Add(self.campo_profundidad, 0, wx.ALL, 6)

		self.casilla_submodulos = wx.CheckBox(self, label=_("Incluir los &submódulos"))
		self.casilla_submodulos.SetValue(True)
		self.casilla_submodulos.SetHelpText(_("Clona también los repositorios incluidos como submódulos."))
		raiz.Add(self.casilla_submodulos, 0, wx.ALL, 6)

		self.progreso = PanelProgresoGit(self, contexto, _("Pro&greso:"))
		self.progreso.campo.SetValue(_("Escriba la dirección y pulse Clonar."))
		raiz.Add(self.progreso, 0, wx.EXPAND | wx.ALL, 2)

		botones = crear_botonera(self, wx.OK | wx.CANCEL)
		self.boton_clonar = self.FindWindow(wx.ID_OK)
		self.boton_clonar.SetLabel(_("C&lonar"))
		self.boton_clonar.SetHelpText(_("Empieza a clonar. Puede seguir el progreso en el campo Progreso."))
		self.boton_cancelar = self.FindWindow(wx.ID_CANCEL)
		self.boton_cancelar.SetHelpText(_("Cierra el cuadro o, si está clonando, cancela el clonado."))
		raiz.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 6)
		self.SetSizerAndFit(raiz)

		self.campo_url.Bind(wx.EVT_TEXT, self._al_cambiar_url)
		self.campo_nombre.Bind(wx.EVT_TEXT, lambda _e: setattr(self, "_nombre_tocado", self.campo_nombre.HasFocus() or self._nombre_tocado))
		self.Bind(wx.EVT_BUTTON, lambda _e: self.clonar(), id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.cancelar(), id=wx.ID_CANCEL)
		preparar_dialogo(self, foco_inicial=self.campo_url)
		self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.CentreOnParent()

	# ── Campos ────────────────────────────────────────────────────────────────

	def _al_cambiar_url(self, _evento: wx.CommandEvent) -> None:
		if not self._nombre_tocado:
			self.campo_nombre.ChangeValue(op.nombre_carpeta(self.campo_url.GetValue()))

	@property
	def protocolo(self) -> str:
		return PROTOCOLOS[max(0, self.selector_protocolo.GetSelection())]

	def url(self) -> str:
		return op.normalizar_url(self.campo_url.GetValue(), self.protocolo, self.ctx.host)

	def destino(self) -> Path:
		nombre = self.campo_nombre.GetValue().strip() or op.nombre_carpeta(self.url())
		return Path(self.campo_carpeta.GetValue().strip()) / nombre

	def _habilitar(self, activo: bool) -> None:
		for control in (self.campo_url, self.selector_protocolo, self.campo_carpeta, self.boton_examinar, self.campo_nombre,
			self.campo_rama, self.campo_profundidad, self.casilla_submodulos, self.boton_clonar):
			control.Enable(activo)

	# ── Clonar ────────────────────────────────────────────────────────────────

	def clonar(self) -> None:
		if self.clonando:
			return
		if not self.campo_url.GetValue().strip():
			mostrar_error(self, _("Escriba la dirección del repositorio o «dueño/repositorio»."), _("Falta la dirección"))
			self.campo_url.SetFocus()
			return
		if not self.campo_carpeta.GetValue().strip():
			mostrar_error(self, _("Elija la carpeta de destino."), _("Falta la carpeta"))
			self.campo_carpeta.SetFocus()
			return
		url = self.url()
		destino = self.destino()
		if destino.exists() and any(destino.iterdir()):
			mostrar_error(self, _("La carpeta {c} ya existe y no está vacía. Elija otro nombre.").format(c=destino), _("Carpeta ocupada"))
			self.campo_nombre.SetFocus()
			return
		existia = destino.exists()
		rama = self.campo_rama.GetValue().strip()
		profundidad = int(self.campo_profundidad.GetValue())
		submodulos = self.casilla_submodulos.GetValue()
		token = self.ctx.token() if self.ctx.config.obtener("git.usar_token", True) and url.startswith("https://") else None
		self.ctx.config.establecer("git.carpeta_clonado", self.campo_carpeta.GetValue().strip())
		self.clonando = True
		self._habilitar(False)
		self.progreso.empezar(_("Clonando {u}…").format(u=url))

		def trabajo() -> Path:
			try:
				return git_local.clonar(url, destino, token=token, rama=rama, profundidad=profundidad, submodulos=submodulos,
					al_linea=self.progreso.recibir_linea, cancelado=self.progreso.cancelado)
			except Exception:
				# Una carpeta a medio clonar estorba al reintentar: se borra si la creó este clonado.
				if not existia and destino.exists():
					shutil.rmtree(destino, ignore_errors=True)
				raise

		en_segundo_plano(self, self.ctx, trabajo, al_terminar=self._al_terminar, al_fallar=self._al_fallar,
			exito=_("Repositorio clonado en {c}.").format(c=destino))

	def _al_terminar(self, carpeta: Path) -> None:
		from app.ui.vistas.principales import anadir_repo_local

		self.clonando = False
		self.carpeta_clonada = str(carpeta)
		anadir_repo_local(self.ctx, self.carpeta_clonada)
		if not self:
			return
		self.progreso.terminar(_("Clonado en {c}.").format(c=carpeta))
		if self.al_clonar:
			try:
				self.al_clonar(self.carpeta_clonada)
			except Exception:  # noqa: BLE001 - un fallo de quien llamó no deshace el clonado
				log.exception("Fallo en al_clonar")
		self.abrir_despues = confirmar(self, _("Repositorio clonado en {c}. ¿Abrir su ventana de git?").format(c=carpeta),
			_("Clonado")) == wx.ID_YES
		self._terminar(wx.ID_OK)

	def _al_fallar(self, error: BaseException) -> None:
		self.clonando = False
		if not self:
			return
		texto = mensaje_error(error)
		self.progreso.terminar(_("No se pudo clonar: {m}").format(m=texto.splitlines()[0] if texto else ""), correcto=False)
		self._habilitar(True)
		if texto == _("Operación cancelada."):
			self.ctx.avisar(_("Clonado cancelado."))
		else:
			mostrar_error(self, texto, _("No se pudo clonar"))
		self.campo_url.SetFocus()

	def cancelar(self) -> None:
		if self.clonando:
			self.progreso.cancelar()
			return
		self._terminar(wx.ID_CANCEL)

	def _terminar(self, codigo: int) -> None:
		self.codigo_salida = codigo
		if self.IsModal():
			self.EndModal(codigo)

	def _al_pulsar(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_ESCAPE and not evento.HasAnyModifiers():
			from app.ui.accesibilidad.dialogos import desplegable_abierto

			if not desplegable_abierto(wx.Window.FindFocus()):
				self.cancelar()
				return
		evento.Skip()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if self.clonando and evento.CanVeto():
			self.progreso.cancelar()
			evento.Veto()
			return
		evento.Skip()


def nombre_repo_de(url: str, nombre: str, host: str) -> str:
	"""«dueño/repo» a partir del nombre recibido o de la URL (para la descarga en zip)."""
	for candidato in (nombre, url):
		candidato = (candidato or "").strip()
		if not candidato:
			continue
		completo = op.nombre_github(candidato, host)
		if completo:
			return completo
		corto = op.normalizar_url(candidato, "https", host)
		completo = op.nombre_github(corto, host)
		if completo:
			return completo
	return ""


def descargar_zip(padre: wx.Window | None, ctx: Any, nombre: str) -> None:
	"""Descarga el código de ``nombre`` (dueño/repo) en zip con la API, sin git."""
	if not nombre:
		nombre = (pedir_texto(padre, _("&Repositorio (dueño/nombre):"), _("Descargar el código en zip")) or "").strip()
		if not nombre:
			return
	propuesta = str(Path(carpeta_por_defecto(ctx)) / (nombre.split("/")[-1] + ".zip"))
	ruta = pedir_texto(padre, _("&Archivo zip de destino:"), _("Descargar el código en zip"), propuesta)
	if not ruta or not ruta.strip():
		return
	destino = Path(ruta.strip())
	from app.ui.descargas import iniciar_descarga

	# En el gestor de descargas: sigue aunque se cierre la ventana, con pausa y reanudación.
	iniciar_descarga(padre, ctx, ctx.api().archivo_zip(nombre), destino, destino.name,
		origen=_("Código de {n}").format(n=nombre), sobrescribir=True)


def dialogo_clonar(padre: wx.Window | None, ctx: Any, url: str = "", nombre: str = "",
	al_clonar: Callable[[str], None] | None = None) -> str | None:
	"""Pide los datos, clona con progreso accesible y devuelve la carpeta clonada (o ``None``)."""
	if not git_local.git_disponible():
		indice = elegir_opcion(padre, _(MENSAJE_SIN_GIT), _("Git no está instalado"),
			[_("&Descargar el código en zip"), _("&Cerrar")])
		if indice == 0:
			descargar_zip(padre, ctx, nombre_repo_de(url, nombre, ctx.host))
		return None
	dialogo = DialogoClonar(padre, ctx, url, nombre, al_clonar)
	try:
		dialogo.ShowModal()
		carpeta = dialogo.carpeta_clonada
		abrir_despues = dialogo.abrir_despues
	finally:
		dialogo.Destroy()
	if carpeta and abrir_despues:
		from app.ui.git.ventana_git import abrir_ventana_git

		abrir_ventana_git(ctx, carpeta)
	return carpeta or None
