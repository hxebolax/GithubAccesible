"""Claves de la cuenta: SSH de autenticación, SSH de firma y GPG.

- Una pestaña por tipo, cada una con su lista (``PanelLista``: lectura por
  columnas, menú contextual, Supr borra, Ctrl+N añade).
- Añadir: pegar el texto de la clave o elegir el archivo ``.pub`` (por defecto
  en ``%USERPROFILE%\\.ssh``).
- «Generar una clave SSH nueva»: ``ssh-keygen`` crea ``%USERPROFILE%\\.ssh\\id_ed25519``
  con frase opcional y después ofrece subirla. Es la ÚNICA excepción a «todo
  en data/»: ssh y git buscan las claves ahí, así que se avisa a la persona.
- Toda la red y ``ssh-keygen`` en segundo plano.
"""

from __future__ import annotations

import builtins
import logging
import os
from pathlib import Path
from typing import Any

import wx

from app.services import formato as f
from app.services import git_local
from app.ui.accesibilidad.dialogos import crear_botonera, elegir_opcion, preparar_dialogo
from app.ui.comunes import confirmar_peligro, en_segundo_plano, mostrar_error, mostrar_mensaje, pedir_texto
from app.ui.vistas.base import Accion, Columna, DefinicionVista, PanelLista

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


AUTENTICACION = "ssh"
FIRMA = "firma"
GPG = "gpg"


def carpeta_ssh() -> Path:
	"""``%USERPROFILE%\\.ssh`` (donde ssh y git buscan las claves)."""
	return Path(os.environ.get("USERPROFILE") or Path.home()) / ".ssh"


def huella_corta(clave: str) -> str:
	"""«ssh-ed25519 AAAA…» → tipo y los últimos caracteres (para distinguirlas al oído)."""
	partes = (clave or "").split()
	if len(partes) >= 2:
		return f"{partes[0]} …{partes[1][-12:]}"
	return (clave or "")[:40]


def _correos(clave: dict) -> str:
	return ", ".join(e.get("email", "") for e in clave.get("emails") or [] if e.get("email"))


class VentanaClaves(wx.Dialog):
	"""Gestión de las claves de la cuenta (no modal: Escape o «Cerrar» la cierran)."""

	def __init__(self, padre: wx.Window | None, contexto: Any) -> None:
		super().__init__(padre, title=_("Claves SSH y GPG"), size=(900, 600), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = contexto
		raiz = wx.BoxSizer(wx.VERTICAL)
		self.aviso = wx.StaticText(self, label=_(
			"Claves de su cuenta de GitHub. Control+Tabulador cambia de pestaña; en cada lista, Control+N añade y Suprimir borra."))
		raiz.Add(self.aviso, 0, wx.ALL, 6)
		self.libro = wx.Notebook(self)
		self.paneles: dict[str, PanelLista] = {}
		for tipo, titulo in ((AUTENTICACION, _("SSH de autenticación")), (FIRMA, _("SSH de firma")), (GPG, _("GPG"))):
			panel = PanelLista(self.libro, contexto, self._definicion(tipo), {"tipo": tipo}, etiqueta=_("&Lista de claves:"))
			self.paneles[tipo] = panel
			self.libro.AddPage(panel, titulo)
		raiz.Add(self.libro, 1, wx.EXPAND | wx.ALL, 6)

		botones = wx.BoxSizer(wx.HORIZONTAL)
		for etiqueta, ayuda, accion in (
			(_("&Añadir una clave…"), _("Sube una clave pública: pegándola o eligiendo su archivo .pub."), lambda: self.anadir()),
			(_("&Borrar la clave"), _("Quita de su cuenta la clave elegida en la lista."), lambda: self.borrar()),
			(_("&Generar una clave SSH nueva…"), _("Crea una clave ed25519 en su carpeta .ssh y ofrece subirla."), lambda: self.generar()),
		):
			boton = wx.Button(self, label=etiqueta)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, lambda _e, a=accion: a())
			botones.Add(boton, 0, wx.ALL, 3)
		botones.AddStretchSpacer()
		botones.Add(crear_botonera(self, wx.CLOSE), 0)
		raiz.Add(botones, 0, wx.EXPAND | wx.ALL, 6)
		self.SetSizer(raiz)
		self.Bind(wx.EVT_BUTTON, lambda _e: self.Close(), id=wx.ID_CLOSE)
		self.Bind(wx.EVT_CLOSE, self._al_cerrar)
		self.libro.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._al_cambiar_pagina)
		preparar_dialogo(self, id_escape=wx.ID_CLOSE, foco_inicial=self.paneles[AUTENTICACION].lista)
		self.CentreOnParent()
		self.paneles[AUTENTICACION].cargar()

	# ── Listas ────────────────────────────────────────────────────────────────

	def _definicion(self, tipo: str) -> DefinicionVista:
		def cargar(api, _pagina, _panel):
			if tipo == AUTENTICACION:
				return api.claves_ssh()
			if tipo == FIRMA:
				return api.claves_firma_ssh()
			return api.claves_gpg()

		if tipo == GPG:
			columnas = [
				Columna("nombre", _("Nombre"), lambda k, _c: k.get("name") or _("(sin nombre)"), 200),
				Columna("id", _("Identificador"), lambda k, _c: k.get("key_id", ""), 160),
				Columna("correos", _("Correos"), lambda k, _c: _correos(k), 260),
				Columna("caduca", _("Caduca"), lambda k, _c: f.fecha_completa(k.get("expires_at")) if k.get("expires_at") else _("nunca"), 140),
				Columna("creada", _("Creada"), lambda k, _c: f.fecha_completa(k.get("created_at")), 140),
			]
		else:
			columnas = [
				Columna("titulo", _("Título"), lambda k, _c: k.get("title") or _("(sin título)"), 220),
				Columna("clave", _("Clave"), lambda k, _c: huella_corta(k.get("key", "")), 300),
				Columna("creada", _("Creada"), lambda k, _c: f.fecha_completa(k.get("created_at")), 160),
			]
		return DefinicionVista(
			f"claves_{tipo}", _("Claves"), columnas, cargar, None,
			[
				Accion(_("&Nueva clave…"), lambda p, k: self.anadir(), "Ctrl+N", requiere_elemento=False),
				Accion(_("&Borrar la clave…"), lambda p, k: self.borrar(), "Supr"),
			],
			_("No hay claves de este tipo en su cuenta."), paginada=False,
		)

	@property
	def tipo(self) -> str:
		return (AUTENTICACION, FIRMA, GPG)[max(0, self.libro.GetSelection())]

	def _al_cambiar_pagina(self, evento: wx.BookCtrlEvent) -> None:
		evento.Skip()
		panel = self.paneles.get(self.tipo)
		if panel is not None:
			panel.cargar_si_hace_falta()

	def _al_cerrar(self, evento: wx.CloseEvent) -> None:
		if self.IsModal():
			self.EndModal(wx.ID_CLOSE)
		else:
			self.Destroy()

	# ── Acciones ──────────────────────────────────────────────────────────────

	def anadir(self, tipo: str | None = None, texto: str | None = None, titulo: str | None = None) -> None:
		"""Pide la clave (pegada o de un archivo) y la sube a la cuenta."""
		tipo = tipo or self.tipo
		if texto is None:
			texto = self._pedir_clave(tipo)
			if not texto:
				return
		texto = texto.strip()
		if titulo is None:
			sugerido = texto.split()[2] if tipo != GPG and len(texto.split()) > 2 else ""
			titulo = pedir_texto(self, _("&Título para reconocerla (por ejemplo, el nombre del equipo):"), _("Añadir una clave"),
				sugerido or os.environ.get("COMPUTERNAME", ""))
			if titulo is None:
				return
		self.subir(tipo, titulo.strip(), texto)

	def _pedir_clave(self, tipo: str) -> str:
		indice = elegir_opcion(self, _("¿Cómo quiere añadir la clave pública?"), _("Añadir una clave"),
			[_("&Pegar el texto de la clave"), _("Elegir el &archivo")])
		if indice is None:
			return ""
		if indice == 0:
			return pedir_texto(self, _("&Clave pública:"), _("Añadir una clave"), multilinea=True) or ""
		comodin = _("Claves públicas (*.pub)|*.pub|Todos los archivos (*.*)|*.*") if tipo != GPG else \
			_("Claves GPG (*.asc;*.gpg;*.txt)|*.asc;*.gpg;*.txt|Todos los archivos (*.*)|*.*")
		dialogo = wx.FileDialog(self, _("Elija el archivo de la clave pública"), str(carpeta_ssh()), wildcard=comodin,
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
		try:
			if dialogo.ShowModal() != wx.ID_OK:
				return ""
			ruta = Path(dialogo.GetPath())
		finally:
			dialogo.Destroy()
		if tipo != GPG and not ruta.name.endswith(".pub") and confirmar_peligro(self, _(
			"«{n}» no termina en .pub: puede ser su clave PRIVADA, que nunca debe subirse. ¿Seguro que es la pública?"
		).format(n=ruta.name), _("Clave pública")) is False:
			return ""
		try:
			return ruta.read_text(encoding="utf-8", errors="replace")
		except OSError as error:
			mostrar_error(self, _("No se pudo leer {r}: {e}").format(r=ruta, e=error), _("Error"))
			return ""

	def subir(self, tipo: str, titulo: str, texto: str) -> None:
		if tipo != GPG and "PRIVATE KEY" in texto:
			mostrar_error(self, _("Eso es una clave PRIVADA. Suba solo la pública (el archivo .pub)."), _("Clave privada"))
			return
		api = self.ctx.api()

		def trabajo() -> dict:
			if tipo == AUTENTICACION:
				return api.anadir_clave_ssh(titulo, texto)
			if tipo == FIRMA:
				return api.anadir_clave_firma_ssh(titulo, texto)
			return api.anadir_clave_gpg(titulo, texto)

		panel = self.paneles[tipo]
		en_segundo_plano(self, self.ctx, trabajo, inicio=_("Subiendo la clave…"), exito=_("Clave añadida a su cuenta."),
			al_terminar=lambda _r: panel.cargar(anunciar=False) if panel else None, titulo_error=_("No se pudo añadir la clave"))

	def borrar(self) -> None:
		tipo = self.tipo
		panel = self.paneles[tipo]
		clave = panel.elemento
		if clave is None:
			self.ctx.avisar(_("No hay ninguna clave elegida."))
			return
		nombre = clave.get("title") or clave.get("name") or clave.get("key_id") or str(clave.get("id"))
		if not confirmar_peligro(self, _("¿Quitar de su cuenta la clave «{n}»? Los equipos que la usan dejarán de poder conectarse "
			"o de firmar con ella.").format(n=nombre), _("Borrar la clave")):
			return
		api = self.ctx.api()
		metodo = {AUTENTICACION: api.borrar_clave_ssh, FIRMA: api.borrar_clave_firma_ssh, GPG: api.borrar_clave_gpg}[tipo]
		en_segundo_plano(self, self.ctx, lambda: metodo(clave["id"]), exito=_("Clave borrada."),
			al_terminar=lambda _r: panel.quitar(clave) if panel else None, titulo_error=_("No se pudo borrar la clave"))

	def generar(self) -> None:
		"""Crea ``%USERPROFILE%\\.ssh\\id_ed25519`` con ``ssh-keygen`` y ofrece subirla."""
		ruta = carpeta_ssh() / "id_ed25519"
		if ruta.exists():
			mostrar_mensaje(self, _(
				"Ya tiene una clave en {r}. No se sobrescribe. Si quiere usarla en GitHub, súbala con «Añadir una clave» "
				"eligiendo el archivo {r}.pub."
			).format(r=ruta), _("Generar una clave SSH"))
			return
		mostrar_mensaje(self, _(
			"La clave se guardará en {c}, fuera de la carpeta de la aplicación, porque ssh y git la buscan ahí. "
			"Es la única excepción: el resto de datos de la aplicación sigue en su carpeta data."
		).format(c=carpeta_ssh()), _("Generar una clave SSH"))
		en_segundo_plano(self, self.ctx, lambda: git_local.config_global("user.email") if git_local.git_disponible() else "",
			al_terminar=lambda correo: self._pedir_datos_clave(ruta, correo) if self else None, sonido="")

	def _pedir_datos_clave(self, ruta: Path, correo_defecto: str) -> None:
		correo = pedir_texto(self, _("&Correo o comentario de la clave:"), _("Generar una clave SSH"), correo_defecto)
		if correo is None:
			return
		frase = pedir_texto(self, _("&Frase de paso (opcional; vacía = sin frase):"), _("Generar una clave SSH"), contrasena=True)
		if frase is None:
			return
		if frase:
			repetida = pedir_texto(self, _("&Repita la frase de paso:"), _("Generar una clave SSH"), contrasena=True)
			if repetida is None:
				return
			if repetida != frase:
				mostrar_error(self, _("Las frases no coinciden. No se ha creado ninguna clave."), _("Generar una clave SSH"))
				return
		self.generar_en(ruta, correo.strip(), frase)

	def generar_en(self, ruta: Path, correo: str, frase: str = "") -> None:
		def listo(publica: Path) -> None:
			if not self:
				return
			try:
				texto = Path(publica).read_text(encoding="utf-8").strip()
			except OSError as error:
				mostrar_error(self, _("Clave creada, pero no se pudo leer {r}: {e}").format(r=publica, e=error), _("Error"))
				return
			indice = elegir_opcion(self, _(
				"Clave creada:\nPrivada: {p}\nPública: {r}\n\n¿Subir la clave pública a su cuenta de GitHub?"
			).format(p=ruta, r=publica), _("Clave creada"),
				[_("Como clave de &autenticación"), _("Como clave de &firma"), _("Como &las dos"), _("&No subirla")])
			titulo = correo or os.environ.get("COMPUTERNAME", "") or "GitHub Accesible"
			if indice in (0, 2):
				self.subir(AUTENTICACION, titulo, texto)
			if indice in (1, 2):
				self.subir(FIRMA, titulo, texto)

		en_segundo_plano(self, self.ctx, lambda: git_local.generar_clave_ssh(ruta, correo, frase), al_terminar=listo,
			inicio=_("Generando la clave…"), exito=_("Clave SSH creada en {r}.").format(r=ruta),
			titulo_error=_("No se pudo generar la clave"))


def abrir_claves(ctx: Any, padre: wx.Window | None) -> VentanaClaves:
	"""Abre la ventana de claves (no modal) y la devuelve."""
	ventana = VentanaClaves(padre, ctx)
	ventana.Show()
	ctx.sonar("abrir")
	return ventana
