"""Inicio de sesión en GitHub (todas las formas) y gestión de cuentas.

Formas de entrar (ver ``app/services/github/autenticacion.py``):

1. **Navegador con código de dispositivo** (recomendada): la aplicación
   muestra un código de 8 caracteres, lo copia al portapapeles, lo deletrea
   por voz y abre ``github.com/login/device``; la persona lo pega allí (donde
   ya tiene su sesión, doble factor o llave de acceso) y la aplicación recibe
   el permiso sola. No se escribe ninguna contraseña en la aplicación.
2. **Token de acceso personal** pegado (clásico o de grano fino), con
   botones que abren la página de GitHub para crearlo con los permisos
   adecuados ya marcados.
3. **Importar la sesión de GitHub CLI** (``gh auth token``).
4. **Credenciales de Git** (Git Credential Manager, ``git credential fill``).

Todas sirven también para **GitHub Enterprise Server** cambiando el servidor.
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from typing import Any

import wx

from app.services.github import autenticacion as auth
from app.ui.accesibilidad.dialogos import crear_botonera, preparar_dialogo
from app.ui.accesibilidad.teclado import copiar_texto
from app.ui.comunes import confirmar, en_segundo_plano, mensaje_error, mostrar_error, mostrar_mensaje

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


METODOS = [auth.METODO_DISPOSITIVO, auth.METODO_TOKEN, auth.METODO_GH, auth.METODO_GIT]


def id_cliente(ctx: Any) -> str:
	return (ctx.config.obtener("cuentas.id_cliente_oauth", "") or auth.ID_CLIENTE_OAUTH).strip()


class DialogoInicioSesion(wx.Dialog):
	"""Diálogo de inicio de sesión. Tras ``ShowModal() == wx.ID_OK``, ``self.cuenta`` es la cuenta añadida."""

	def __init__(self, padre: wx.Window | None, ctx: Any, host: str = "github.com") -> None:
		super().__init__(padre, title=_("Iniciar sesión en GitHub"), size=(640, 600), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = ctx
		self.cuenta: auth.Cuenta | None = None
		self._tarea = None
		self._cancelado = False
		self._flujo: auth.FlujoDispositivo | None = None
		raiz = wx.BoxSizer(wx.VERTICAL)

		raiz.Add(wx.StaticText(self, label=_("&Servidor (github.com o el de su empresa):")), 0, wx.LEFT | wx.TOP, 8)
		self.campo_host = wx.TextCtrl(self, value=host)
		self.campo_host.SetHelpText(_("Deje github.com salvo que use GitHub Enterprise Server; en ese caso escriba su dirección, por ejemplo github.miempresa.com."))
		raiz.Add(self.campo_host, 0, wx.EXPAND | wx.ALL, 8)

		nombres = [
			_("Con el &navegador y un código (recomendado)"),
			_("Con un token de acceso pe&rsonal"),
			_("Importar la sesión de Git&Hub CLI (gh)"),
			_("Usar las credenciales guardadas de Git (&Git Credential Manager)"),
		]
		self.metodo = wx.RadioBox(self, label=_("&Método de inicio de sesión"), choices=nombres, majorDimension=1, style=wx.RA_SPECIFY_COLS)
		self.metodo.SetHelpText(_(
			"Navegador: la forma más segura; GitHub le pedirá su contraseña, doble factor o llave en su navegador. "
			"Token: pegue un token creado en la web de GitHub. GitHub CLI y Git: reutilizan una sesión que ya tenga en este equipo."
		))
		raiz.Add(self.metodo, 0, wx.EXPAND | wx.ALL, 8)

		raiz.Add(wx.StaticText(self, label=_("Ám&bitos que se piden:")), 0, wx.LEFT | wx.TOP, 8)
		self.ambitos = wx.Choice(self, choices=[
			_("Básicos: repositorios, issues, pull requests, Actions, gists, notificaciones y proyectos"),
			_("Completos: además borrar repositorios, administrar organizaciones, claves, webhooks y paquetes"),
		])
		self.ambitos.SetSelection(1 if ctx.config.obtener("cuentas.ambitos", "completos") == "completos" else 0)
		self.ambitos.SetHelpText(_("Permisos que se piden a GitHub en el inicio con navegador. Se pueden ampliar más tarde volviendo a iniciar sesión."))
		raiz.Add(self.ambitos, 0, wx.EXPAND | wx.ALL, 8)

		raiz.Add(wx.StaticText(self, label=_("&Token de acceso personal:")), 0, wx.LEFT | wx.TOP, 8)
		self.campo_token = wx.TextCtrl(self, style=wx.TE_PASSWORD)
		self.campo_token.SetHelpText(_("Pegue aquí el token (empieza por ghp_ o github_pat_). Se guarda cifrado con su usuario de Windows."))
		raiz.Add(self.campo_token, 0, wx.EXPAND | wx.ALL, 8)
		fila_token = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_clasico = wx.Button(self, label=_("Crear un token clásico en la &web"))
		self.boton_clasico.SetHelpText(_("Abre GitHub con los permisos ya marcados para crear un token clásico."))
		self.boton_clasico.Bind(wx.EVT_BUTTON, self._al_crear_clasico)
		self.boton_fino = wx.Button(self, label=_("Crear un token de grano &fino"))
		self.boton_fino.SetHelpText(_("Abre GitHub para crear un token de grano fino, limitado a los repositorios que elija."))
		self.boton_fino.Bind(wx.EVT_BUTTON, lambda _e: webbrowser.open(f"https://{self._host()}/settings/personal-access-tokens/new"))
		fila_token.Add(self.boton_clasico, 0, wx.RIGHT, 6)
		fila_token.Add(self.boton_fino, 0)
		raiz.Add(fila_token, 0, wx.LEFT | wx.RIGHT, 8)

		raiz.Add(wx.StaticText(self, label=_("Có&digo para el navegador:")), 0, wx.LEFT | wx.TOP, 8)
		self.campo_codigo = wx.TextCtrl(self, style=wx.TE_READONLY)
		self.campo_codigo.SetHelpText(_("Código que debe escribir en la página de GitHub. Ya está copiado al portapapeles."))
		raiz.Add(self.campo_codigo, 0, wx.EXPAND | wx.ALL, 8)
		fila_codigo = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_copiar = wx.Button(self, label=_("Co&piar el código"))
		self.boton_copiar.Bind(wx.EVT_BUTTON, self._al_copiar_codigo)
		self.boton_pagina = wx.Button(self, label=_("&Abrir la página de verificación"))
		self.boton_pagina.Bind(wx.EVT_BUTTON, self._al_abrir_pagina)
		fila_codigo.Add(self.boton_copiar, 0, wx.RIGHT, 6)
		fila_codigo.Add(self.boton_pagina, 0)
		raiz.Add(fila_codigo, 0, wx.LEFT | wx.RIGHT, 8)

		raiz.Add(wx.StaticText(self, label=_("&Estado:")), 0, wx.LEFT | wx.TOP, 8)
		self.estado = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=(-1, self.FromDIP(70)))
		raiz.Add(self.estado, 0, wx.EXPAND | wx.ALL, 8)

		botones = crear_botonera(self, wx.OK | wx.CANCEL)
		self.boton_iniciar = self.FindWindow(wx.ID_OK)
		self.boton_iniciar.SetLabel(_("&Iniciar sesión"))
		raiz.Add(botones, 0, wx.EXPAND | wx.ALL, 8)
		self.SetSizer(raiz)

		self._url_verificacion = ""
		self._codigo = ""
		self._elegir_metodo_inicial()
		self.metodo.Bind(wx.EVT_RADIOBOX, lambda _e: self._actualizar_controles())
		self.Bind(wx.EVT_BUTTON, self._al_iniciar, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self._al_cancelar, id=wx.ID_CANCEL)
		preparar_dialogo(self, foco_inicial=self.metodo)
		self._actualizar_controles()
		self.CentreOnParent()

	# ── Estado de los controles ───────────────────────────────────────────────

	def _host(self) -> str:
		from app.services.github.cliente import normalizar_host

		return normalizar_host(self.campo_host.GetValue())

	def _metodo(self) -> str:
		return METODOS[self.metodo.GetSelection()]

	def _elegir_metodo_inicial(self) -> None:
		if id_cliente(self.ctx):
			self.metodo.SetSelection(0)
		elif auth.ruta_gh():
			self.metodo.SetSelection(2)
		else:
			self.metodo.SetSelection(1)

	def _actualizar_controles(self) -> None:
		metodo = self._metodo()
		es_token = metodo == auth.METODO_TOKEN
		es_dispositivo = metodo == auth.METODO_DISPOSITIVO
		for control in (self.campo_token, self.boton_clasico, self.boton_fino):
			control.Enable(es_token)
		self.ambitos.Enable(es_dispositivo)
		hay_codigo = bool(self._codigo)
		self.campo_codigo.Enable(es_dispositivo and hay_codigo)
		self.boton_copiar.Enable(es_dispositivo and hay_codigo)
		self.boton_pagina.Enable(es_dispositivo and hay_codigo)
		explicaciones = {
			auth.METODO_DISPOSITIVO: _("Pulse Iniciar sesión: se abrirá GitHub en el navegador y el código quedará copiado. Péguelo allí y autorice la aplicación."),
			auth.METODO_TOKEN: _("Pegue un token y pulse Iniciar sesión. Si no tiene uno, créelo con los botones de debajo del campo."),
			auth.METODO_GH: _("Se usará la sesión de GitHub CLI de este equipo.") if auth.ruta_gh() else _("GitHub CLI no está instalado en este equipo."),
			auth.METODO_GIT: _("Se pedirá a Git la credencial guardada para el servidor. Git Credential Manager puede abrir su propia ventana."),
		}
		if es_dispositivo and not id_cliente(self.ctx):
			explicaciones[metodo] = _(
				"Para entrar con el navegador falta el identificador de la aplicación OAuth. Regístrela una vez en "
				"GitHub (Configuración, Developer settings, OAuth Apps, con «Enable Device Flow» marcado) y escriba su "
				"Client ID en Preferencias, Cuentas. Mientras tanto, use un token o la sesión de GitHub CLI."
			)
		self._poner_estado(explicaciones[metodo])

	def _poner_estado(self, texto: str) -> None:
		self.estado.SetValue(texto)

	# ── Botones auxiliares ────────────────────────────────────────────────────

	def _al_crear_clasico(self, _evento: wx.CommandEvent) -> None:
		ambitos = auth.AMBITOS_COMPLETOS if self.ambitos.GetSelection() == 1 else auth.AMBITOS_BASICOS
		webbrowser.open(f"https://{self._host()}/settings/tokens/new?description=GitHub%20Accesible&scopes={','.join(ambitos)}")
		self.ctx.avisar(_("Página de GitHub abierta en el navegador. Cree el token, cópielo y péguelo en el campo Token."))

	def _al_copiar_codigo(self, _evento: wx.CommandEvent | None) -> None:
		if self._codigo and copiar_texto(self._codigo):
			self.ctx.sonar("copiado")
			self.ctx.avisar(_("Código copiado."))

	def _al_abrir_pagina(self, _evento: wx.CommandEvent | None) -> None:
		if self._url_verificacion:
			webbrowser.open(self._url_verificacion)

	# ── Inicio de sesión ──────────────────────────────────────────────────────

	def _al_iniciar(self, _evento: wx.CommandEvent) -> None:
		metodo = self._metodo()
		host = self._host()
		self._cancelado = False
		if metodo == auth.METODO_TOKEN:
			token = self.campo_token.GetValue().strip()
			if not token:
				mostrar_error(self, _("Pegue primero el token."), _("Falta el token"))
				self.campo_token.SetFocus()
				return
			self._validar(lambda: token, metodo, host)
		elif metodo == auth.METODO_GH:
			self._validar(lambda: auth.token_de_gh(host), metodo, host)
		elif metodo == auth.METODO_GIT:
			self._validar(lambda: auth.token_de_git(host), metodo, host)
		else:
			if not id_cliente(self.ctx):
				mostrar_error(self, self.estado.GetValue(), _("Falta la aplicación OAuth"))
				return
			self._flujo_dispositivo(host)

	def _validar(self, obtener_token, metodo: str, host: str) -> None:
		self.boton_iniciar.Disable()
		self._poner_estado(_("Comprobando con GitHub…"))
		self.ctx.avisar(_("Comprobando con GitHub…"))

		def trabajo():
			token = obtener_token()
			return auth.validar_token(token, host, metodo), token

		en_segundo_plano(self, self.ctx, trabajo, sonido="", al_terminar=self._terminado, al_fallar=self._fallado)

	def _flujo_dispositivo(self, host: str) -> None:
		ambitos = auth.AMBITOS_COMPLETOS if self.ambitos.GetSelection() == 1 else auth.AMBITOS_BASICOS
		flujo = auth.FlujoDispositivo(id_cliente(self.ctx), ambitos, host)
		self._flujo = flujo
		self.boton_iniciar.Disable()
		self._poner_estado(_("Pidiendo un código a GitHub…"))

		def pedir():
			return flujo.pedir_codigo()

		def con_codigo(codigo: auth.CodigoDispositivo) -> None:
			self._codigo = codigo.codigo_usuario
			self._url_verificacion = codigo.url_verificacion
			self.campo_codigo.SetValue(codigo.codigo_usuario)
			self._actualizar_controles()
			copiar_texto(codigo.codigo_usuario)
			self._poner_estado(_(
				"Su código es {c}. Ya está copiado. Se ha abierto {u} en el navegador: pegue el código, pulse Continuar y "
				"autorice la aplicación. Esta ventana se completará sola. El código caduca en {m} minutos."
			).format(c=codigo.codigo_usuario, u=codigo.url_verificacion, m=codigo.caduca_en // 60))
			self.ctx.avisar(_("Código copiado: {c}. Péguelo en la página de GitHub que se ha abierto.").format(c=codigo.codigo_deletreado))
			webbrowser.open(codigo.url_verificacion)
			self.campo_codigo.SetFocus()

			def esperar():
				token = flujo.esperar_token(codigo, cancelado=lambda: self._cancelado)
				return auth.validar_token(token, host, auth.METODO_DISPOSITIVO), token

			en_segundo_plano(self, self.ctx, esperar, sonido="", al_terminar=self._terminado, al_fallar=self._fallado)

		en_segundo_plano(self, self.ctx, pedir, sonido="", al_terminar=con_codigo, al_fallar=self._fallado)

	def _terminado(self, resultado: tuple[auth.Cuenta, str]) -> None:
		cuenta, token = resultado
		self.ctx.cuentas.anadir(cuenta, token)
		# Solo el flujo de dispositivo da token de renovación; con otro método se borra el viejo.
		flujo = getattr(self, "_flujo", None)
		renovacion = flujo.renovacion if flujo is not None and cuenta.metodo == auth.METODO_DISPOSITIVO else None
		self.ctx.cuentas.guardar_renovacion(cuenta, renovacion)
		self.cuenta = cuenta
		self.ctx.sonar("completado")
		self.ctx.avisar(_("Sesión iniciada como {u}.").format(u=cuenta.descripcion()))
		if self and self.IsModal():
			self.EndModal(wx.ID_OK)

	def _fallado(self, error: BaseException) -> None:
		if not self:
			return
		self.boton_iniciar.Enable()
		if self._cancelado:
			return
		self._poner_estado(mensaje_error(error))
		self.ctx.sonar("error")
		mostrar_error(self, mensaje_error(error), _("No se pudo iniciar sesión"))

	def _al_cancelar(self, _evento: wx.CommandEvent) -> None:
		self._cancelado = True
		self.EndModal(wx.ID_CANCEL)


def iniciar_sesion(padre: wx.Window | None, ctx: Any, host: str = "github.com") -> auth.Cuenta | None:
	dialogo = DialogoInicioSesion(padre, ctx, host)
	try:
		dialogo.ShowModal()
		return dialogo.cuenta
	finally:
		dialogo._cancelado = True
		dialogo.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Cuentas
# ════════════════════════════════════════════════════════════════════════════


class DialogoCuentas(wx.Dialog):
	"""Lista de cuentas guardadas: añadir, activar, comprobar y quitar."""

	def __init__(self, padre: wx.Window | None, ctx: Any) -> None:
		super().__init__(padre, title=_("Cuentas de GitHub"), size=(720, 420), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ctx = ctx
		from app.ui.accesibilidad.lista import ListaAccesible
		from app.ui.vistas.base import preferencias_lectura

		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=_("C&uentas guardadas:")), 0, wx.LEFT | wx.TOP, 8)
		self.lista = ListaAccesible(self, _("Cuentas guardadas"), [(_("Cuenta"), 220), (_("Servidor"), 160), (_("Método"), 180),
			(_("Activa"), 70), (_("Ámbitos"), 260)], leer_preferencias=preferencias_lectura(ctx.config))
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		for etiqueta, manejador, ayuda in (
			(_("&Añadir cuenta…"), self._al_anadir, _("Inicia sesión con otra cuenta o en otro servidor.")),
			(_("Usar &esta cuenta"), self._al_activar, _("Hace activa la cuenta elegida en toda la aplicación.")),
			(_("Com&probar"), self._al_comprobar, _("Comprueba con GitHub que el token sigue siendo válido y qué ámbitos tiene.")),
			(_("&Quitar…"), self._al_quitar, _("Olvida la cuenta y borra su token de este equipo.")),
		):
			boton = wx.Button(self, label=etiqueta)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, manejador)
			fila.Add(boton, 0, wx.RIGHT, 6)
		raiz.Add(fila, 0, wx.LEFT | wx.RIGHT, 8)
		cerrar = wx.Button(self, wx.ID_CANCEL, _("&Cerrar"))
		raiz.Add(cerrar, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
		self.SetSizer(raiz)
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._al_activar)
		self._rellenar()
		preparar_dialogo(self, foco_inicial=self.lista)
		self.CentreOnParent()

	def _rellenar(self) -> None:
		activa = self.ctx.cuentas.activa()
		self.cuentas = self.ctx.cuentas.cuentas()
		filas = [[c.descripcion(), c.host, _(auth.NOMBRES_METODO.get(c.metodo, c.metodo)),
			_("Sí") if activa and c.clave == activa.clave else _("No"), ", ".join(c.ambitos) or _("(no informados)")] for c in self.cuentas]
		self.lista.reemplazar_filas(filas)
		if filas and self.lista.fila_actual() == wx.NOT_FOUND:
			self.lista.enfocar_fila(0, anunciar=False)

	def _elegida(self) -> auth.Cuenta | None:
		fila = self.lista.fila_actual()
		return self.cuentas[fila] if 0 <= fila < len(self.cuentas) else None

	def _al_anadir(self, _evento: wx.CommandEvent) -> None:
		if iniciar_sesion(self, self.ctx):
			self._rellenar()

	def _al_activar(self, _evento: wx.CommandEvent) -> None:
		cuenta = self._elegida()
		if cuenta:
			self.ctx.cuentas.activar(cuenta)
			self._rellenar()
			self.ctx.avisar(_("Cuenta activa: {c}.").format(c=cuenta.descripcion()))

	def _al_comprobar(self, _evento: wx.CommandEvent) -> None:
		cuenta = self._elegida()
		if not cuenta:
			return
		token = self.ctx.cuentas.token(cuenta)

		def hecho(nueva: auth.Cuenta) -> None:
			nueva.metodo = cuenta.metodo
			self.ctx.cuentas.anadir(nueva, token, activar=False)
			self._rellenar()
			mostrar_mensaje(self, _("El token es válido. Cuenta: {u}. Ámbitos: {a}.").format(
				u=nueva.descripcion(), a=", ".join(nueva.ambitos) or _("los del token de grano fino")), _("Comprobación"))

		en_segundo_plano(self, self.ctx, lambda: auth.validar_token(token or "", cuenta.host, cuenta.metodo), al_terminar=hecho, sonido="")

	def _al_quitar(self, _evento: wx.CommandEvent) -> None:
		cuenta = self._elegida()
		if cuenta and confirmar(self, _("¿Quitar la cuenta {c} de este equipo? El token se borrará (en GitHub seguirá existiendo hasta que lo revoque).").format(
			c=cuenta.descripcion()), _("Quitar cuenta"), peligroso=True) == wx.ID_YES:
			self.ctx.cuentas.eliminar(cuenta)
			self._rellenar()


def gestionar_cuentas(padre: wx.Window | None, ctx: Any) -> None:
	dialogo = DialogoCuentas(padre, ctx)
	try:
		dialogo.ShowModal()
	finally:
		dialogo.Destroy()
