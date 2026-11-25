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
	SECRETO,
	TECLA,
	TEXTO,
	DialogoPreferencias,
	Opcion,
	Pagina,
	mostrar_aviso,
)

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def N_(texto: str) -> str:  # noqa: N802
	return texto


# Valores de «general.idioma» cuyo nombre se muestra en su propio idioma.
NOMBRES_IDIOMA = {"es", "en"}

TITULO_SONIDOS = N_("Sonidos")
TITULO_LISTAS = N_("Listas")
TITULO_NOTIFICACIONES = N_("Notificaciones")
TITULO_COLUMNAS = N_("Columnas de las listas")
TITULO_SECCIONES = N_("Secciones")
TITULO_TRADUCCION = N_("Traducción")
TITULO_CLAVES_TRADUCCION = N_("Claves de traducción")


def _idiomas_para_preferencias() -> tuple[tuple[str, str], ...]:
	"""(código, nombre sin traducir) de los idiomas del traductor, en el orden alfabético del idioma de la interfaz."""
	from app.services import traduccion as tr

	return tuple((codigo, nombre) for codigo, nombre, _ingles in sorted(tr.IDIOMAS, key=lambda i: _(i[1]).casefold()))


def _paginas_traduccion() -> tuple[Pagina, ...]:
	"""Traducción (incidencia #13). Letras sin A, C, P ni R (botones del diálogo)."""
	from app.services import traduccion as tr

	idiomas = _idiomas_para_preferencias()
	return (
		Pagina(TITULO_TRADUCCION, (
			Opcion("traduccion.motor", N_("&Motor de traducción:"), OPCION,
				N_("Servicio que traduce. Google Translate gratis funciona sin clave, pero no es una API oficial y a veces "
					"rechaza peticiones durante un rato. MyMemory también es gratis y sin clave, con un límite diario. "
					"LibreTranslate es libre: un servidor propio o el público con clave. Los demás piden una clave "
					"propia: Google Cloud, Microsoft y DeepL "
					"traducen al momento; Gemini, ChatGPT, DeepSeek y Claude son inteligencias artificiales que traducen "
					"de forma más natural. Gemini y DeepL tienen plan gratuito."),
				opciones=tuple((motor, nombre) for motor, nombre, _clave in tr.MOTORES)),
			Opcion("traduccion.destino_lectura", N_("Idioma al que se &traduce lo que lee:"), OPCION,
				N_("Al pulsar Control+T en una conversación, el texto se traduce a este idioma."),
				opciones=(("", N_("El idioma de la interfaz")), *idiomas)),
			Opcion("traduccion.origen_lectura", N_("Idioma de &origen de lo que lee:"), OPCION,
				N_("Normalmente, detectarlo: cada persona escribe en el suyo."),
				opciones=((tr.AUTO, N_("Detectar el idioma")), *idiomas)),
			Opcion("traduccion.destino_envio", N_("Idioma al que se traduce lo que &envía:"), OPCION,
				N_("El que aparece elegido en «Traducir al enviar a» del editor y del formulario de issue. También se "
					"guarda el último que elija allí."),
				opciones=(("", N_("No traducir")), *idiomas)),
			Opcion("traduccion.incluir_original", N_("&Incluir el texto original plegado al final de lo que se envía traducido"),
				BOOL, N_("Añade al final un apartado plegable con el texto original, por si la traducción no se entiende bien.")),
			Opcion("traduccion.respaldo", N_("Si el motor elegido falla, probar con los &gratuitos (Google y MyMemory)"), BOOL,
				N_("Si el motor elegido no responde o da un error, se traduce con Google Translate gratis y, si tampoco "
					"puede, con MyMemory, en vez de dar el error.")),
		)),
		Pagina(TITULO_CLAVES_TRADUCCION, (
			Opcion("traduccion.correo_mymemory", N_("Correo electrónico para MyMemor&y (opcional):"), TEXTO,
				N_("MyMemory traduce sin clave unos 5.000 caracteres al día; con un correo, 50.000. Solo se envía a MyMemory.")),
			Opcion("traduccion.url_libretranslate", N_("Dirección del servidor Libre&Translate:"), TEXTO,
				N_("La de su propio servidor (por ejemplo, http://localhost:5000) o https://libretranslate.com, que pide clave.")),
			Opcion("traduccion.clave_libretranslate", N_("Clave de LibreTranslate (si el ser&vidor la pide):"), SECRETO,
				N_("Solo si el servidor pide clave, como libretranslate.com. Se guarda cifrada.")),
			Opcion("traduccion.clave_google_cloud", N_("Clave de &Google Translate (Google Cloud Translation):"), SECRETO,
				N_("Clave de API de un proyecto de Google Cloud con «Cloud Translation API» activada (los primeros "
					"500.000 caracteres de cada mes son gratis). Se guarda cifrada.")),
			Opcion("traduccion.clave_microsoft", N_("Clave de &Microsoft Translator (Azure):"), SECRETO,
				N_("Clave de un recurso «Translator» de Azure (el plan F0 traduce 2 millones de caracteres al mes gratis). "
					"Se guarda cifrada.")),
			Opcion("traduccion.region_microsoft", N_("Región del recurso de A&zure (vacío si es global):"), TEXTO,
				N_("Por ejemplo, westeurope. Déjelo vacío si el recurso es global.")),
			Opcion("traduccion.clave_deepl", N_("Clave de &DeepL:"), SECRETO,
				N_("Clave de la API de DeepL. La gratuita (termina en «:fx») traduce 500.000 caracteres al mes. "
					"Se guarda cifrada.")),
			Opcion("traduccion.clave_gemini", N_("Clave de G&emini:"), SECRETO,
				N_("Clave de Google AI Studio. Tiene plan gratuito con un límite de peticiones al día. Se guarda cifrada.")),
			Opcion("traduccion.modelo_gemini", N_("Modelo de Gem&ini:"), TEXTO,
				N_("De fábrica, el más barato de Gemini que traduce bien.")),
			Opcion("traduccion.clave_openai", N_("Clave de &OpenAI (ChatGPT):"), SECRETO,
				N_("Clave de la API de OpenAI (de pago por uso). Se guarda cifrada.")),
			Opcion("traduccion.modelo_openai", N_("Modelo de Ope&nAI:"), TEXTO,
				N_("De fábrica, el más barato de OpenAI.")),
			Opcion("traduccion.url_openai", N_("Dirección (&URL) de la API de OpenAI:"), TEXTO,
				N_("Cámbiela para usar otro servicio compatible con la API de OpenAI (OpenRouter, Ollama en este equipo...).")),
			Opcion("traduccion.clave_deepseek", N_("Clave de Deep&Seek:"), SECRETO,
				N_("Clave de la API de DeepSeek (de pago por uso, muy barata). Se guarda cifrada.")),
			Opcion("traduccion.modelo_deepseek", N_("Modelo de DeepSee&k:"), TEXTO,
				N_("De fábrica, el más barato de DeepSeek.")),
			Opcion("traduccion.clave_claude", N_("Clave de Claude (Ant&hropic):"), SECRETO,
				N_("Clave de la API de Anthropic (de pago por uso). Se guarda cifrada.")),
			Opcion("traduccion.modelo_claude", N_("Modelo de C&laude:"), TEXTO,
				N_("De fábrica, el más barato de Claude.")),
		)),
	)


def secciones_de(ventana: str) -> list[tuple[str, str]]:
	"""(identificador, título) de todas las secciones de fábrica de ``ventana`` («principal» o «repositorio»)."""
	if ventana == "principal":
		from app.ui.vistas import principales

		return [(clave, fabrica().titulo) for clave, fabrica in principales.SECCIONES]
	from app.ui.repositorio.ventana import SECCIONES

	return [(s.id, _(s.titulo)) for s in SECCIONES]


def paginas(paquetes: list[str], voces_sapi: list[str] | None = None) -> tuple[Pagina, ...]:
	"""Páginas declarativas. Las letras de acceso no repiten dentro de cada página ni usan
	A, C, P ni R (botones Aceptar, Cancelar, Aplicar y Restablecer)."""
	return (
		Pagina(N_("General"), (
			Opcion("general.idioma", N_("Idioma de la i&nterfaz:"), OPCION,
				N_("Idioma de menús, mensajes, documentación y novedades. «Automático» usa el español si Windows está en "
					"cualquier variante de español y el inglés en los demás casos. Se aplica al reiniciar la aplicación."),
				# Los nombres de los idiomas se escriben en su propio idioma (ver NOMBRES_IDIOMA en el diálogo).
				opciones=(("auto", N_("Automático (el idioma de Windows)")), ("es", "Español"), ("en", "English"))),
			Opcion("general.seccion_inicial", N_("&Sección al abrir:"), OPCION,
				N_("Qué sección se muestra al abrir la aplicación."),
				opciones=(("notificaciones", N_("Notificaciones")), ("inicio", N_("Inicio")), ("repositorios", N_("Mis repositorios")),
					("issues", N_("Mis issues")), ("prs", N_("Mis pull requests")), ("locales", N_("Repositorios locales")))),
			Opcion("general.anunciar_arranque", N_("Anunciar el arranque por &voz"), BOOL,
				N_("Dice «Iniciando GitHub Accesible» mientras se carga.")),
			Opcion("general.minimizar_a_bandeja", N_("&Minimizar a la bandeja del sistema"), BOOL,
				N_("Al minimizar, la ventana se oculta y queda un icono junto al reloj.")),
			Opcion("general.cerrar_a_bandeja", N_("Al cerrar la ventana, dejarla en la &bandeja (Control+Q sale)"), BOOL,
				N_("Alt+F4 o el botón Cerrar ocultan la ventana en la bandeja del sistema en vez de salir; la aplicación sigue "
					"avisando de las notificaciones. Para salir de verdad: Archivo, Salir (Control+Q) o el menú del icono.")),
			Opcion("general.iniciar_en_bandeja", N_("&Iniciar oculta en la bandeja"), BOOL,
				N_("Al arrancar, la ventana queda en la bandeja del sistema (útil para recibir notificaciones).")),
			Opcion("general.icono_bandeja_siempre", N_("Icono en la bandeja &todo el tiempo"), BOOL,
				N_("Deja el icono junto al reloj también con la ventana a la vista. Su texto dice cuántas notificaciones "
					"hay sin leer y su menú (Aplicaciones) ofrece las órdenes más usadas.")),
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
			Opcion("accesibilidad.explicacion_controles", N_("Explicaciones: leerlas al lle&gar a botones y casillas"), BOOL,
				N_("El lector de pantalla lee la explicación del control (la misma de Control+H) al llegar a un botón o una "
					"casilla. Desactívelo si prefiere oírla solo cuando la pida con Control+H.")),
			Opcion("accesibilidad.explicacion_filas", N_("Explicaciones: leerlas también en cada fila de las listas de casilla&s"), BOOL,
				N_("Sin esta opción, al moverse por una lista de casillas solo se oye cada fila y su estado. Con ella, el lector "
					"repite la explicación de la lista en cada fila. Control+H la dice siempre.")),
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
		Pagina(TITULO_LISTAS, (
			Opcion("listas.por_pagina", N_("&Elementos por página al cargar (10 a 100):"), ENTERO,
				N_("Cuántos elementos se piden cada vez. Al llegar al final de la lista se cargan más.")),
			Opcion("listas.fechas_relativas", N_("&Fechas relativas («hace 3 días»)"), BOOL,
				N_("Desactivado muestra la fecha y la hora completas.")),
			Opcion("listas.historial_actividad", N_("En la actividad de un perfil, seg&uir con los años anteriores"), BOOL,
				N_("GitHub solo da los eventos de los últimos 30 días. Activado, al llegar al final de la lista se siguen "
					"cargando las contribuciones de antes (commits, issues y pull requests abiertos, revisiones y repositorios "
					"creados), año a año, hasta el alta en GitHub. Cada año gasta 1 punto de los 5.000 por hora que da GitHub "
					"para estas consultas (algo más en años muy activos, que se piden por partes): poco, pero si se recorre "
					"la historia de muchas personas se nota. Desactivado, solo los 30 días.")),
			Opcion("listas.actualizar_sola", N_("Actuali&zar sola la sección que está a la vista"), BOOL,
				N_("Cada pocos minutos se vuelve a pedir a GitHub la sección que se ve en la ventana principal, si está "
					"marcada en la lista de abajo, y la lista se pone al día sin mover el foco. Solo la sección a la vista "
					"y solo con la ventana a la vista: oculta en la bandeja o minimizada no se pide nada. Cada "
					"actualización gasta 1 petición de las 5.000 por hora que da GitHub (2 o 3 si se ven columnas con "
					"datos extra); si nada ha cambiado, GitHub responde «sin cambios» y no la descuenta. Mis issues y "
					"Mis pull requests usan la búsqueda de GitHub, que permite 30 al minuto. Si ha cargado más páginas "
					"bajando por la lista, no se actualiza sola para no quitarle lo que lee: pulse F5.")),
			Opcion("listas.actualizar_cada_min", N_("Cada cuántos &minutos (1 a 240):"), ENTERO,
				N_("Cada cuánto se pone al día la sección a la vista y cuánto tienen que tener sus datos para "
					"actualizarla al volver a ella. Con 5 minutos, una sección gasta como mucho 12 peticiones por hora.")),
			Opcion("listas.actualizar_al_volver", N_("Al &volver a una sección, actualizarla si han pasado esos minutos"), BOOL,
				N_("Al elegir en la lista de secciones una que se cargó hace más de esos minutos, se pone al día sola. "
					"Solo las secciones marcadas abajo.")),
			Opcion("listas.anunciar_nuevos", N_("Decir cuántos elementos &nuevos llegan al actualizarse sola"), BOOL,
				N_("Suena y dice, por ejemplo, «3 elementos nuevos en Inicio». Desactivado, la lista cambia en silencio.")),
		)),
		Pagina(TITULO_NOTIFICACIONES, (
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
			Opcion("notificaciones.lectura", N_("&Leer los avisos en segundo plano con:"), OPCION,
				N_("Quién dice las notificaciones nuevas y el final de las ejecuciones de Actions vigiladas. El lector de "
					"pantalla corta el aviso en cuanto se pulsa una tecla; una voz SAPI 5 propia lo dice entero aunque siga "
					"escribiendo (puede sonar a la vez que el lector). Lo que se pide con el teclado sigue diciéndolo el lector."),
				opciones=(("lector", N_("El lector de pantalla")), ("sapi5", N_("Una voz SAPI 5 propia (no se corta al pulsar teclas)")))),
			Opcion("notificaciones.sapi_voz", N_("Vo&z SAPI 5:"), OPCION,
				N_("Voz de Windows que dice los avisos cuando se elige la voz SAPI 5."),
				# Los nombres de las voces se enseñan tal cual los da Windows.
				opciones=(("", N_("La predeterminada de Windows")), *((v, v) for v in (voces_sapi or [])))),
			Opcion("notificaciones.sapi_velocidad", N_("Velocida&d de la voz SAPI 5 (-10 a 10):"), ENTERO,
				N_("0 es la velocidad normal; los negativos, más despacio, y los positivos, más deprisa.")),
			Opcion("notificaciones.sapi_volumen", N_("Vol&umen de la voz SAPI 5 (0 a 100):"), ENTERO,
				N_("Volumen de la voz SAPI 5, independiente del lector de pantalla.")),
		)),
		Pagina(N_("Teclas globales"), (
			Opcion("teclas_globales.activadas", N_("Acti&var las teclas globales"), BOOL,
				N_("Combinaciones que funcionan desde cualquier programa, aunque la aplicación esté en la bandeja.")),
			*(Opcion(f"teclas_globales.{clave}", etiqueta, TECLA, N_(
				"Pulse aquí la combinación que quiera: Control, Alt o Windows (y si quiere Mayúsculas) con una letra, un "
				"número o de F1 a F24. Retroceso o Suprimir la quitan. Windows no deja usar una combinación que ya tenga "
				"otro programa: si pasa, la aplicación lo dice al aplicar."))
				for clave, etiqueta in (
					("mostrar_ocultar", N_("&Mostrar u ocultar la aplicación:")),
					("decir_notificaciones", N_("Decir las &notificaciones sin leer:")),
					("abrir_notificaciones", N_("Abrir la sección Notificacione&s:")),
					("buscar", N_("&Buscar en GitHub:")),
					("comprobar_notificaciones", N_("Comprobar a&hora si hay notificaciones nuevas:")),
					("abrir_descargas", N_("Abrir el gestor de &descargas:")),
				)),
		)),
		Pagina(N_("Descargas"), (
			Opcion("descargas.simultaneas", N_("&Descargas a la vez (1 a 10):"), ENTERO,
				N_("Cuántas descargas se bajan al mismo tiempo; las demás esperan en cola y empiezan solas al terminar otra.")),
			Opcion("descargas.reanudar_al_iniciar", N_("Al abrir la aplicación, &seguir con las descargas que quedaron a medias"), BOOL,
				N_("Si se cierra la aplicación con descargas en curso, se pausan conservando lo bajado. Activado, siguen solas al "
					"volver a abrirla; desactivado, quedan en pausa en «Descargas».")),
			Opcion("descargas.abrir_gestor", N_("Abrir la ventana «Descargas» al &empezar una descarga"), BOOL,
				N_("Desactivado, la descarga empieza en segundo plano y se avisa al terminar; la ventana se abre con "
					"Control+Mayúsculas+D.")),
		)),
		Pagina(N_("Actions"), (
			Opcion("acciones.intervalo_vigilancia_s", N_("&Intervalo para vigilar ejecuciones (segundos, mínimo 15):"), ENTERO,
				N_("Cada cuánto se pregunta a GitHub por las ejecuciones que vigila. GitHub limita las peticiones por hora.")),
			Opcion("acciones.vigilar_tras_enviar", N_("Tras en&viar cambios con git, avisar del resultado de sus ejecuciones"), BOOL,
				N_("Después de un push a GitHub desde la ventana de git, vigila las ejecuciones de Actions que lance ese commit "
					"y dice si han ido bien o mal. Si el repositorio no tiene Actions, no dice nada.")),
			Opcion("acciones.avisar_resultados", N_("Avisar de las ejecuciones vigiladas que &terminan:"), OPCION,
				N_("Vale para todo lo vigilado: «Avisarme cuando termine», «Avisar al terminar cada ejecución de Actions» de un repositorio "
					"y lo que lanza un push. Si elige solo las que fallan, de las que van bien no se dice nada."),
				opciones=(("todas", N_("Todas, vayan bien o mal")), ("fallidas", N_("Solo las que fallan, se cancelan o no terminan bien")),
					("correctas", N_("Solo las que van bien")))),
			Opcion("acciones.sonido_al_terminar", N_("&Sonido al terminar una ejecución vigilada"), BOOL,
				N_("Un sonido de éxito o de fallo según el resultado. Cada sonido se puede quitar también en Preferencias, Sonidos.")),
			Opcion("acciones.voz_al_terminar", N_("Decir por vo&z el resultado de una ejecución vigilada"), BOOL,
				N_("Dice el repositorio, el flujo, la rama y el resultado. Lo dice el lector o la voz SAPI 5, según "
					"Preferencias, Notificaciones, «Leer los avisos en segundo plano con».")),
			Opcion("acciones.notificacion_windows", N_("Notificación de &Windows al terminar una ejecución vigilada"), BOOL,
				N_("Además del sonido y el aviso por voz, si están activados, muestra un aviso del sistema.")),
			Opcion("acciones.mostrar_horas", N_("&Mostrar la hora en cada línea de los registros"), BOOL,
				N_("En la ventana de una ejecución, pone al principio de cada línea del registro la hora en que se escribió.")),
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
			Opcion("editor.tabulador_escribe", N_("El &tabulador escribe una tabulación en el texto Markdown"), BOOL,
				N_("Desactivada (de fábrica), Tabulador y Mayúsculas+Tabulador pasan al control siguiente o al anterior, "
					"como en el resto de Windows. Activada, Tabulador escribe una tabulación y Control+Tabulador pasa de control. "
					"Se aplica a los editores que se abran después.")),
		)),
		Pagina(N_("Red y registro"), (
			Opcion("red.proxy", N_("Pro&xy («sistema», «ninguno» o una dirección):"), TEXTO,
				N_("«sistema» usa la configuración de Windows; «ninguno» conecta directamente; o escriba http://servidor:puerto.")),
			Opcion("red.tiempo_espera_s", N_("&Tiempo máximo de espera (segundos):"), ENTERO, N_("Tiempo de espera de las peticiones a GitHub.")),
			Opcion("registro.nivel", N_("&Nivel del registro de errores:"), OPCION,
				N_("DEBUG guarda mucho detalle para diagnosticar problemas."),
				opciones=(("INFO", N_("Normal")), ("DEBUG", N_("Detallado (depuración)")), ("WARNING", N_("Solo avisos")), ("ERROR", N_("Solo errores")))),
		)),
		*_paginas_traduccion(),
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
		from app.ui.accesibilidad import sapi

		self._voces_sapi = sapi.voces()
		super().__init__(padre, ctx.config, paginas(paquetes, self._voces_sapi), secretos=getattr(ctx, "secretos", None), anunciar=lambda t: ctx.avisar(t))
		self._nombres_idioma_propios()
		self._crear_pagina_columnas()
		self._crear_pagina_secciones()

	def _nombres_idioma_propios(self) -> None:
		"""Cada idioma, escrito en ese idioma («Español», «English»), sin traducir.

		El diálogo base pasa por ``_()`` el texto de cada opción, y «Español» se
		traduciría a «Spanish»: quien no entiende el idioma actual debe reconocer el suyo.
		"""
		datos = self._controles.get("general.idioma")
		if datos is None:
			return
		opcion, control, _pagina = datos
		for posicion, (valor, nombre) in enumerate(opcion.opciones):
			if valor in NOMBRES_IDIOMA:
				control.SetString(posicion, nombre)

	def _escribir_control(self, opcion: Opcion, control: wx.Window, valor: Any) -> None:
		if opcion.tipo == TECLA and valor:
			# Las de fábrica se guardan en español («Mayúsculas»): se enseñan en el idioma de la interfaz.
			from app.ui.teclas_globales import normalizar

			valor = normalizar(str(valor)) or valor
		super()._escribir_control(opcion, control, valor)

	# ── Página de sonidos: se añade la lista de eventos ───────────────────────

	def _crear_pagina(self, pagina: Pagina, indice: int) -> wx.Window:
		panel = super()._crear_pagina(pagina, indice)
		if pagina.titulo == TITULO_NOTIFICACIONES:
			self.boton_probar_voz = wx.Button(panel, label=_("Pro&bar la voz SAPI 5"))
			self.boton_probar_voz.SetHelpText(_("Dice una frase de ejemplo con la voz, la velocidad y el volumen elegidos, sin guardarlos."))
			self.boton_probar_voz.Bind(wx.EVT_BUTTON, self._al_probar_voz)
			panel.GetSizer().Add(self.boton_probar_voz, 0, wx.ALL, 6)
			panel.Layout()
		if pagina.titulo == TITULO_LISTAS:
			sizer = panel.GetSizer()
			from app.ui.ventana_principal import SECCIONES_SIN_ACTUALIZACION

			self._secciones_auto = [(c, t) for c, t in secciones_de("principal") if c not in SECCIONES_SIN_ACTUALIZACION]
			sizer.Add(wx.StaticText(panel, label=_("&Secciones que se actualizan solas (marcadas = sí):")), 0, wx.LEFT | wx.TOP, 6)
			self.lista_actualizar = ListaCasillas(panel, _("Secciones que se actualizan solas"),
				[t for _c, t in self._secciones_auto], config=self.ctx.config)
			self.lista_actualizar.SetHelpText(_(
				"Las secciones de la ventana principal que se ponen al día solas cuando están a la vista, y al volver "
				"a ellas. Notificaciones no está porque ya se comprueba sola (Preferencias, Notificaciones), ni Búsqueda."))
			marcadas = set(self.ctx.config.obtener("listas.actualizar_secciones", []) or [])
			for indice_seccion, (clave_seccion, _titulo) in enumerate(self._secciones_auto):
				wx.CheckListBox.Check(self.lista_actualizar, indice_seccion, clave_seccion in marcadas)
			self.lista_actualizar.SetMinSize(self.FromDIP(wx.Size(-1, 160)))
			sizer.Add(self.lista_actualizar, 1, wx.EXPAND | wx.ALL, 6)
			panel.Layout()
		if pagina.titulo == TITULO_TRADUCCION:
			self.boton_probar_traduccion = wx.Button(panel, label=_("Pro&bar el motor elegido"))
			self.boton_probar_traduccion.SetHelpText(_(
				"Traduce una frase de ejemplo con el motor y las claves que hay escritos ahora, sin guardarlos, y dice "
				"si funciona."))
			self.boton_probar_traduccion.Bind(wx.EVT_BUTTON, self._al_probar_traduccion)
			panel.GetSizer().Add(self.boton_probar_traduccion, 0, wx.ALL, 6)
			panel.Layout()
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

	def _al_probar_voz(self, _evento: wx.CommandEvent) -> None:
		from app.ui.accesibilidad import sapi

		valores = {}
		for clave in ("notificaciones.sapi_voz", "notificaciones.sapi_velocidad", "notificaciones.sapi_volumen"):
			opcion, control, _pagina = self._controles[clave]
			valores[clave] = self._leer_control(opcion, control)
		texto = _("Notificación nueva de ana/proyecto: así sonarán los avisos.")
		if not sapi.hablar(texto, valores["notificaciones.sapi_voz"] or "", valores["notificaciones.sapi_velocidad"],
				valores["notificaciones.sapi_volumen"]):
			self.ctx.avisar(_("La voz SAPI 5 no está disponible en este equipo."))

	def ajustes_traduccion(self) -> Any:
		"""Ajustes del traductor con lo que hay escrito ahora en el diálogo (sin guardarlo)."""
		from app.services import traduccion as tr

		dialogo = self

		class LoEscrito:
			"""Lee del diálogo (o, si la opción no está en él, de la configuración); sirve de config y de secretos."""

			def obtener(self, clave: str, por_defecto: Any = None) -> Any:
				datos = dialogo._controles.get(clave)
				if datos is None:
					return dialogo.ctx.config.obtener(clave, por_defecto)
				opcion, control, _pagina = datos
				return dialogo._leer_control(opcion, control)

		ajustes = tr.ajustes_desde(LoEscrito(), LoEscrito())
		ajustes.respaldo = False  # se prueba el motor elegido, no el de respaldo
		return ajustes

	def _al_probar_traduccion(self, _evento: wx.CommandEvent) -> None:
		"""Prueba el motor en segundo plano y dice el resultado (o el error, explicado)."""
		from app.services import traduccion as tr

		ajustes = self.ajustes_traduccion()
		destino = "en" if tr.idioma_de_la_interfaz() == "es" else "es"
		texto = _("Gracias por el aviso: lo reviso mañana y le cuento.")
		nombre = tr.nombre_motor_corto(ajustes.motor)
		self.boton_probar_traduccion.Disable()
		self.ctx.avisar(_("Probando {m}…").format(m=nombre))

		def listo(resultado: Any) -> None:
			if not self:
				return
			self.boton_probar_traduccion.Enable()
			mostrar_aviso(self, _("{m} funciona. «{t}» se traduce como:\n\n{r}").format(m=nombre, t=texto, r=resultado.texto),
				_("Prueba del traductor"))

		def fallo(error: BaseException) -> None:
			if not self:
				return
			self.boton_probar_traduccion.Enable()
			mensaje = getattr(error, "mensaje_usuario", "") or str(error)
			mostrar_aviso(self, _("{m} no ha funcionado: {e}").format(m=nombre, e=mensaje), _("Prueba del traductor"))

		self.ctx.tareas.enviar(lambda _tarea: tr.traducir(texto, destino, tr.AUTO, ajustes), al_terminar=listo, al_fallar=fallo,
			nombre="probar_traduccion", duplicadas="permitir")

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
		# El foco se queda donde estaba (el botón o la lista): se puede seguir pulsando Subir o Bajar.
		self.ctx.anunciar(_("{c}, posición {p}").format(c=self.lista_columnas.GetString(destino), p=destino + 1))

	def _original(self) -> None:
		self._columnas_elegidas.pop(self._vista().id, None)
		self._mostrar_columnas()
		self.ctx.anunciar(_("Columnas de fábrica."))

	# ── Página de secciones ───────────────────────────────────────────────────

	VENTANAS_SECCIONES = (("principal", N_("Ventana principal")), ("repositorio", N_("Ventana de un repositorio")))

	def _crear_pagina_secciones(self) -> None:
		from app.ui import orden_secciones

		# Estado en memoria por ventana: orden completo y ocultas (se guarda al Aplicar o Aceptar).
		self._secciones: dict[str, tuple[list[str], set[str]]] = {}
		self._titulos_secciones: dict[str, dict[str, str]] = {}
		for ventana, _nombre in self.VENTANAS_SECCIONES:
			todas = secciones_de(ventana)
			self._titulos_secciones[ventana] = dict(todas)
			prefijo, obligatorias = orden_secciones.VENTANAS[ventana]
			orden = orden_secciones.orden_completo([c for c, _t in todas], self.ctx.config.obtener(f"{prefijo}_orden", []) or [])
			ocultas = set(self.ctx.config.obtener(f"{prefijo}_ocultas", []) or []) - set(obligatorias)
			self._secciones[ventana] = (orden, ocultas)
		panel = wx.Panel(self.libro)
		sizer = wx.BoxSizer(wx.VERTICAL)
		texto = wx.StaticText(panel, label=_(
			"Elija una ventana y marque las secciones que quiere ver. El orden de arriba abajo es el de la lista de secciones; "
			"Alt+1 a Alt+9 siguen ese orden. «Resultados de la búsqueda» y «Resumen» no se pueden ocultar."))
		texto.Wrap(self.FromDIP(560))
		sizer.Add(texto, 0, wx.ALL, 6)
		sizer.Add(wx.StaticText(panel, label=_("&Ventana:")), 0, wx.LEFT | wx.TOP, 6)
		self.selector_ventana = wx.Choice(panel, choices=[_(n) for _v, n in self.VENTANAS_SECCIONES])
		self.selector_ventana.SetHelpText(_("Ventana cuyas secciones quiere ordenar u ocultar. La del repositorio se aplica "
			"a las ventanas de repositorio que se abran a partir de ahora."))
		self.selector_ventana.Bind(wx.EVT_CHOICE, lambda _e: self._mostrar_secciones())
		sizer.Add(self.selector_ventana, 0, wx.EXPAND | wx.ALL, 6)
		sizer.Add(wx.StaticText(panel, label=_("&Secciones visibles y su orden:")), 0, wx.LEFT | wx.TOP, 6)
		self.lista_secciones_pref = ListaCasillas(panel, _("Secciones visibles y su orden"), [], config=self.ctx.config)
		self.lista_secciones_pref.Bind(wx.EVT_CHECKLISTBOX, self._al_marcar_seccion)
		sizer.Add(self.lista_secciones_pref, 1, wx.EXPAND | wx.ALL, 6)
		fila = wx.BoxSizer(wx.HORIZONTAL)
		for etiqueta, manejador, ayuda in (
			(_("S&ubir"), lambda _e: self._mover_seccion(-1), _("Sube la sección elegida un puesto.")),
			(_("Ba&jar"), lambda _e: self._mover_seccion(1), _("Baja la sección elegida un puesto.")),
			(_("&Orden de fábrica"), lambda _e: self._secciones_de_fabrica(), _("Muestra todas las secciones de esta ventana "
				"en su orden original.")),
		):
			boton = wx.Button(panel, label=etiqueta)
			boton.SetHelpText(ayuda)
			boton.Bind(wx.EVT_BUTTON, manejador)
			fila.Add(boton, 0, wx.RIGHT, 6)
		sizer.Add(fila, 0, wx.ALL, 6)
		panel.SetSizer(sizer)
		self.libro.AddPage(panel, _(TITULO_SECCIONES))
		self.selector_ventana.SetSelection(0)
		self._mostrar_secciones()

	def _ventana_secciones(self) -> str:
		return self.VENTANAS_SECCIONES[max(0, self.selector_ventana.GetSelection())][0]

	def _mostrar_secciones(self, seleccion: int = 0) -> None:
		ventana = self._ventana_secciones()
		orden, ocultas = self._secciones[ventana]
		titulos = self._titulos_secciones[ventana]
		self.lista_secciones_pref.Set([titulos[c] for c in orden])
		for indice, clave in enumerate(orden):
			wx.CheckListBox.Check(self.lista_secciones_pref, indice, clave not in ocultas)
		if orden:
			self.lista_secciones_pref.SetSelection(max(0, min(seleccion, len(orden) - 1)))

	def _al_marcar_seccion(self, evento: wx.CommandEvent) -> None:
		from app.ui import orden_secciones

		evento.Skip()
		ventana = self._ventana_secciones()
		orden, ocultas = self._secciones[ventana]
		indice = evento.GetInt()
		if not 0 <= indice < len(orden):
			return
		clave = orden[indice]
		if self.lista_secciones_pref.IsChecked(indice):
			ocultas.discard(clave)
		elif clave in orden_secciones.VENTANAS[ventana][1]:
			# Obligatoria: se vuelve a marcar y se explica por qué.
			wx.CallAfter(wx.CheckListBox.Check, self.lista_secciones_pref, indice, True)
			self.ctx.anunciar(_("Esta sección no se puede ocultar."))
		else:
			ocultas.add(clave)
			if len(ocultas) >= len(orden):
				ocultas.discard(clave)
				wx.CallAfter(wx.CheckListBox.Check, self.lista_secciones_pref, indice, True)

	def _mover_seccion(self, paso: int) -> None:
		ventana = self._ventana_secciones()
		orden, _ocultas = self._secciones[ventana]
		indice = self.lista_secciones_pref.GetSelection()
		destino = indice + paso
		if indice < 0 or not 0 <= destino < len(orden):
			self.ctx.anunciar(_("No se puede mover más."))
			return
		orden[indice], orden[destino] = orden[destino], orden[indice]
		self._mostrar_secciones(destino)
		# El foco se queda donde estaba (el botón o la lista): se puede seguir pulsando Subir o Bajar.
		self.ctx.anunciar(_("{c}, posición {p}").format(c=self.lista_secciones_pref.GetString(destino), p=destino + 1))

	def _secciones_de_fabrica(self) -> None:
		ventana = self._ventana_secciones()
		self._secciones[ventana] = ([c for c, _t in secciones_de(ventana)], set())
		self._mostrar_secciones()
		self.ctx.anunciar(_("Secciones de fábrica."))

	def cambios_secciones(self) -> dict[str, Any]:
		"""Claves de configuración que cambian con lo elegido en la página Secciones."""
		from app.ui import orden_secciones

		cambios: dict[str, Any] = {}
		for ventana, (orden, ocultas) in getattr(self, "_secciones", {}).items():
			prefijo, _obligatorias = orden_secciones.VENTANAS[ventana]
			fabrica = [c for c, _t in secciones_de(ventana)]
			valor_orden = [] if orden == fabrica else list(orden)
			valor_ocultas = [c for c in orden if c in ocultas]
			if valor_orden != list(self.ctx.config.obtener(f"{prefijo}_orden", []) or []):
				cambios[f"{prefijo}_orden"] = valor_orden
			if valor_ocultas != list(self.ctx.config.obtener(f"{prefijo}_ocultas", []) or []):
				cambios[f"{prefijo}_ocultas"] = valor_ocultas
		return cambios

	# ── Guardar ───────────────────────────────────────────────────────────────

	def teclas_repetidas(self) -> list[str]:
		"""Claves de las teclas globales que repiten la combinación de otra anterior."""
		vistas: set[str] = set()
		repetidas = []
		for clave, (opcion, control, _pagina) in self._controles.items():
			if opcion.tipo != TECLA:
				continue
			valor = control.GetValue().strip()
			if valor and valor in vistas:
				repetidas.append(clave)
			vistas.add(valor)
		return repetidas

	def aplicar(self) -> bool:
		repetidas = self.teclas_repetidas()
		if repetidas:
			# Dos órdenes con la misma tecla: Windows solo daría una y la otra quedaría muerta.
			self._senalar(repetidas[0], _("Esa combinación ya la tiene otra tecla global. Elija otra o quítela con Retroceso."))
			return False
		if not super().aplicar():
			return False
		cambios: dict[str, Any] = {}
		if hasattr(self, "lista_actualizar"):
			elegidas = [c for i, (c, _t) in enumerate(self._secciones_auto) if self.lista_actualizar.IsChecked(i)]
			if elegidas != list(self.ctx.config.obtener("listas.actualizar_secciones", []) or []):
				cambios["listas.actualizar_secciones"] = elegidas
		if hasattr(self, "lista_eventos"):
			desactivados = [e for i, e in enumerate(self._eventos) if not self.lista_eventos.IsChecked(i)]
			if desactivados != list(self.ctx.config.obtener("sonidos.desactivados", []) or []):
				cambios["sonidos.desactivados"] = desactivados
		if self._vistas:
			self._guardar_columnas_en_memoria()
			if self._columnas_elegidas != (self.ctx.config.obtener("listas.columnas", {}) or {}):
				cambios["listas.columnas"] = dict(self._columnas_elegidas)
		cambios.update(self.cambios_secciones())
		if cambios:
			self.ctx.config.establecer_varias(cambios)
		return True

	def restablecer_controles(self) -> None:
		super().restablecer_controles()
		if hasattr(self, "lista_eventos"):
			for indice in range(self.lista_eventos.GetCount()):
				wx.CheckListBox.Check(self.lista_eventos, indice, True)
		if hasattr(self, "lista_actualizar"):
			from app.core.configuracion import VALORES_POR_DEFECTO

			de_fabrica = set(VALORES_POR_DEFECTO["listas"]["actualizar_secciones"])
			for indice, (clave, _t) in enumerate(self._secciones_auto):
				wx.CheckListBox.Check(self.lista_actualizar, indice, clave in de_fabrica)
		if self._vistas:
			self._columnas_elegidas = {}
			self._mostrar_columnas()
		if hasattr(self, "_secciones"):
			for ventana, _nombre in self.VENTANAS_SECCIONES:
				self._secciones[ventana] = ([c for c, _t in secciones_de(ventana)], set())
			self._mostrar_secciones()


def mostrar_preferencias(padre: wx.Window | None, ctx: Any, vistas: list[Any] | None = None) -> bool:
	idioma_antes = ctx.config.obtener("general.idioma", "auto")
	dialogo = DialogoPreferenciasGitHub(padre, ctx, vistas)
	try:
		aceptado = dialogo.ShowModal() == wx.ID_OK
	finally:
		dialogo.Destroy()
	# Aplicar también guarda: se compara con lo que había al abrir, no solo al aceptar.
	if ctx.config.obtener("general.idioma", "auto") != idioma_antes:
		ofrecer_reinicio_idioma(padre)
	return aceptado


def ofrecer_reinicio_idioma(padre: wx.Window | None) -> None:
	"""El idioma se fija al arrancar: ofrece reiniciar ya (o dejarlo para la próxima vez)."""
	from app.core import reinicio
	from app.ui.accesibilidad.dialogos import confirmar

	respuesta = confirmar(padre, _("El idioma nuevo se aplicará al reiniciar la aplicación. ¿Quiere reiniciarla ahora?"),
		_("Cambiar el idioma"))
	if respuesta != wx.ID_YES:
		return
	reinicio.solicitar()
	salir = getattr(padre, "salir", None)
	if callable(salir):
		salir()
