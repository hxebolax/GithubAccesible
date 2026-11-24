"""Punto de entrada de GitHub Accesible.

El ORDEN de arranque importa:

1. ``multiprocessing.freeze_support()`` lo primero (versión compilada).
2. Registro (solo biblioteca estándar) antes de importar wx: así hasta un
   fallo de importación queda escrito en ``data/logs``.
3. Configuración (valores por defecto en código; un archivo dañado no impide
   arrancar) y traducción (``_``).
4. ``wx.App`` → ``wx.HelpProvider`` (Ctrl+H) → ``wx.Locale`` en español
   (guardando la referencia) → instancia única.
5. Anuncio de arranque por voz, SIN ventana de espera.
6. Contexto (cuentas, secretos cifrados, tareas, sonidos), ventana principal
   y bucle de eventos.

Argumentos:

- ``--comprobar-arranque``: arranca sin mostrar la ventana y sale con código 0
  si todo fue bien (pruebas y comprobación del ``.exe`` recién compilado).
- ``--tras-actualizar``: lo añade el actualizador al relanzar.
- Cualquier otro argumento: una carpeta de repositorio local o un enlace de
  GitHub que abrir.
"""

from __future__ import annotations

import builtins
import logging
import sys
import time

# Con hilos de fondo trabajando, el hilo de la interfaz tardaba en recuperar el
# GIL y el lector de pantalla se quedaba mudo. Con 1 ms responde enseguida.
sys.setswitchinterval(0.001)

log = logging.getLogger("app.main")

ARGUMENTO_COMPROBAR = "--comprobar-arranque"

# Objetos que deben vivir toda la sesión (idioma de wx, mutex de instancia única).
_VIVOS: dict[str, object] = {}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _mostrar_error_arranque(mensaje: str) -> None:
	"""Cartel de error aunque wx no esté disponible (último recurso)."""
	titulo = _("Error al iniciar")
	try:
		import wx

		if wx.GetApp() is None:
			wx.App(False)
		dialogo = wx.MessageDialog(None, mensaje, titulo, wx.OK | wx.ICON_ERROR)
		dialogo.SetOKLabel(_("&Aceptar"))
		try:
			dialogo.ShowModal()
		finally:
			dialogo.Destroy()
		return
	except Exception:  # noqa: BLE001 - si wx falla, se prueba el cartel nativo
		log.debug("No se pudo mostrar el cartel con wx", exc_info=True)
	try:
		import ctypes

		ctypes.windll.user32.MessageBoxW(0, mensaje, titulo, 0x10)
	except Exception:  # noqa: BLE001 - ya no queda dónde avisar salvo la consola
		if sys.__stderr__ is not None:
			print(mensaje, file=sys.__stderr__)


def _configurar_voz(config) -> None:
	from app.ui.accesibilidad import voz as voz_ui

	voz_ui.configurar(
		activada=bool(config.obtener("accesibilidad.voz_activada", True)),
		retraso_ms=int(config.obtener("accesibilidad.retardo_voz_ms", 120)),
		braille=bool(config.obtener("accesibilidad.braille", True)),
	)


def crear_contexto(config):
	"""Construye el contexto compartido (cuentas, secretos, tareas, sonidos, voz)."""
	from app.core import paths
	from app.core.contexto import Contexto
	from app.core.secretos import obtener_secretos
	from app.core.tareas import GestorTareas
	from app.services import git_local, sonidos
	from app.services.github.autenticacion import GestorCuentas
	from app.ui.accesibilidad import voz as voz_ui

	secretos = obtener_secretos()
	cuentas = GestorCuentas(config, secretos)
	tareas = GestorTareas(max_hilos=8, nombre="GitHub")
	reproductor = sonidos.Sonidos(paths.ruta_sonidos(), sonidos.preferencias_desde_config(config))
	reproductor.preparar()
	sonidos.establecer(reproductor)
	git_local.establecer_ruta_git(str(config.obtener("git.ruta", "") or ""))

	def anunciar(texto: str, interrumpir: bool = True, **_opciones) -> None:
		voz_ui.hablar(texto, interrumpir=interrumpir, canal=voz_ui.AVISOS)

	contexto = Contexto(config, secretos, cuentas, tareas, reproductor, anunciar=anunciar)
	contexto.descargas = crear_gestor_descargas(config, cuentas)
	try:
		from app.services.borradores import Almacen

		contexto.almacen = Almacen()
	except Exception:  # noqa: BLE001 - sin base de datos la aplicación funciona igual (sin borradores)
		log.exception("No se pudo abrir la base de datos de borradores")

	def al_cambiar(clave: str, _anterior, _nuevo) -> None:
		if clave.startswith("accesibilidad."):
			_configurar_voz(config)
		elif clave == "git.ruta":
			git_local.establecer_ruta_git(str(config.obtener("git.ruta", "") or ""))
		elif clave == "registro.nivel":
			from app.core import registro

			registro.cambiar_nivel(str(config.obtener("registro.nivel", "INFO")))

	config.suscribir(al_cambiar)
	_VIVOS["al_cambiar_config"] = al_cambiar  # referencia fuerte: la configuración guarda referencias débiles
	return contexto


def crear_gestor_descargas(config, cuentas):
	"""Gestor de descargas de la aplicación. Cada descarga usa el token de la cuenta que la pidió."""
	from app.core import paths
	from app.services.gestor_descargas import GestorDescargas

	def sesion_para(clave_cuenta: str, aceptar: str):
		from app.core import red

		cuenta = next((c for c in cuentas.cuentas() if c.clave == clave_cuenta), None)
		sesion = red.sesion_de_hilo()
		sesion.headers.update(cuentas.cliente(cuenta).cabeceras_base(aceptar or None))
		return sesion

	return GestorDescargas(paths.ruta_configuracion(), sesion_para,
		simultaneas=lambda: int(config.obtener("descargas.simultaneas", 3)))


def _principal(argumentos: list[str]) -> int:
	inicio = time.perf_counter()
	comprobar = ARGUMENTO_COMPROBAR in argumentos
	abrir = [a for a in argumentos if not a.startswith("--")]

	# 2. Registro (solo biblioteca estándar).
	from app.core import registro
	from app.core.version import APP_VERSION, ID_APLICACION, NOMBRE_APLICACION

	registro.configurar_registro(nombre_app=NOMBRE_APLICACION, version=APP_VERSION, nivel="INFO")

	# 3. Configuración y traducción.
	from app.core import i18n
	from app.core.configuracion import obtener_configuracion

	config = obtener_configuracion()
	nivel = str(config.obtener("registro.nivel", "INFO")).upper()
	if nivel != "INFO":
		registro.cambiar_nivel(nivel)
	i18n.inicializar(config.obtener("general.idioma", "auto"))

	# 4. wx, ayuda contextual, idioma e instancia única.
	import wx

	registro.registrar_version_wx()
	aplicacion = wx.App(False)
	aplicacion.SetAppName(ID_APLICACION)
	# Proveedor propio: Control+H dice siempre la ayuda; el lector solo la oye si se configura así.
	from app.ui.accesibilidad.ayuda import instalar_proveedor_ayuda

	instalar_proveedor_ayuda(config)
	# Botones y diálogos estándar de wx (Aceptar, Cancelar, Sí...) en el idioma elegido.
	_VIVOS["idioma"] = i18n.configurar_wx()

	from app.core.instancia_unica import InstanciaUnica

	instancia = InstanciaUnica(ID_APLICACION)
	_VIVOS["instancia"] = instancia
	if instancia.hay_otra():
		log.info("Ya hay otra instancia en marcha; se le pide que se muestre.")
		if not instancia.pedir_mostrar(abrir):
			from app.ui.accesibilidad.dialogos import mostrar_mensaje

			mostrar_mensaje(None, _("{nombre} ya está en ejecución.").format(nombre=NOMBRE_APLICACION), NOMBRE_APLICACION)
		return 0

	# 5. Aviso por voz antes de lo pesado.
	_configurar_voz(config)
	if not comprobar and config.obtener("general.anunciar_arranque", True):
		from app.ui.accesibilidad import voz as voz_ui

		voz_ui.hablar(_("Iniciando {nombre}").format(nombre=NOMBRE_APLICACION), interrumpir=True, sincrono=True)

	# 6. Errores no controlados a la vista, vigilante de congelaciones, contexto y ventana.
	from app.core import vigilante_ui
	from app.ui import dialogo_error

	if not comprobar:
		dialogo_error.instalar(nombre_app=NOMBRE_APLICACION)
		vigilante_ui.iniciar()

	contexto = crear_contexto(config)
	_VIVOS["contexto"] = contexto

	from app.ui.ventana_principal import VentanaPrincipal

	ventana = VentanaPrincipal(contexto, instancia)
	if comprobar:
		wx.CallAfter(ventana.salir)
	else:
		instancia.registrar_ventana(ventana.GetHandle())
		if not (config.obtener("general.iniciar_en_bandeja", False) and ventana.ocultar_en_bandeja()):
			ventana.mostrar()
		contexto.sonar("inicio")
		from app.ui.descargas import instalar_avisos

		instalar_avisos(contexto)
		wx.CallAfter(ventana.preparar_actualizaciones)
		# Las descargas que quedaron a medias siguen (o quedan en pausa, según Preferencias).
		wx.CallAfter(contexto.descargas.cargar, bool(config.obtener("descargas.reanudar_al_iniciar", True)))
		wx.CallLater(800, ventana.pedir_sesion_si_falta)
		wx.CallLater(1200, ventana.programar_notificaciones)
		for argumento in abrir:
			wx.CallLater(1500, ventana.abrir_argumento, argumento)
		from app.ui import visor_ayuda

		wx.CallLater(2500, lambda: visor_ayuda.mostrar_novedades_si_procede(ventana, APP_VERSION))

	log.info("Arranque completado en %.2f s.", time.perf_counter() - inicio)
	aplicacion.MainLoop()

	vigilante_ui.detener()
	from app.ui.accesibilidad import sapi

	sapi.detener()
	# Lo que se está descargando se pausa conservando lo bajado, para seguir al volver a abrir.
	contexto.descargas.detener()
	contexto.tareas.apagar(espera=3.0)
	if contexto.sonidos is not None:
		contexto.sonidos.detener()
	if contexto.almacen is not None:
		contexto.almacen.cerrar()
	try:
		config.guardar_pendiente()
	except Exception:  # noqa: BLE001
		log.exception("No se pudo guardar la configuración pendiente al salir")
	instancia.liberar()
	log.info("Cierre normal.")
	from app.core import reinicio

	# Después de liberar la instancia única: si no, la nueva vería a esta viva y se cerraría.
	reinicio.relanzar_si_procede()
	return 0


def principal(argumentos: list[str] | None = None) -> int:
	"""Arranca la aplicación y garantiza que ningún fallo quede sin explicación."""
	import multiprocessing

	multiprocessing.freeze_support()
	try:
		return _principal(sys.argv[1:] if argumentos is None else argumentos)
	except SystemExit:
		raise
	except BaseException as error:  # noqa: BLE001 - red de seguridad del arranque
		log.critical("Fallo no controlado al iniciar la aplicación.", exc_info=True)
		ruta = None
		try:
			from app.core import registro

			ruta = registro.registrar_fallo_de_arranque(error)
		except Exception:  # noqa: BLE001 - el propio registro puede ser lo que falla
			log.debug("No se pudo escribir arranque_fallido.log", exc_info=True)
		detalle = (
			_("Los detalles están en {ruta}.").format(ruta=ruta)
			if ruta
			else _("Compruebe que la carpeta «data» existe y no es de solo lectura.")
		)
		_mostrar_error_arranque(_("No se pudo iniciar la aplicación.") + f"\n\n{type(error).__name__}: {error}\n\n" + detalle)
		return 1


if __name__ == "__main__":
	sys.exit(principal())
