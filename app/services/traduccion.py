"""Traducción de textos de GitHub (issues, comentarios, discusiones...) con varios motores (incidencia #13).

Solo se traduce lo que la persona pide (un comentario, una conversación, lo que
va a enviar), nunca la interfaz. Solo servicios conocidos; la persona elige el
motor en Preferencias, Traducción:

- ``google`` (por defecto): Google Translate gratis y sin clave, el mismo acceso
  que usan las bibliotecas libres más conocidas (``translate_a/single`` con
  ``client=gtx``). NO es una API oficial: Google puede responder 429 (demasiadas
  peticiones) a ratos. Se pide con educación: una petición cada vez, trozos
  pequeños, la identificación real de la aplicación, reintentos con espera
  (respetando ``Retry-After``) y, si sigue fallando, se explica y se sugiere otro
  motor. Nunca se finge ser un navegador ni se rodean los bloqueos.
- ``mymemory``: MyMemory, API pública y gratuita sin clave (con un correo, el
  límite diario sube a 50.000 caracteres).
- ``libretranslate``: LibreTranslate, libre; un servidor propio o el público con clave.
- ``google_cloud``: Google Cloud Translation (oficial) con la clave de la persona.
- ``microsoft``: Microsoft Translator de Azure con su clave (y la región si la pide).
- ``deepl``: DeepL con su clave (la gratuita termina en «:fx»).
- ``gemini``, ``openai``, ``deepseek`` y ``claude``: inteligencias artificiales
  con la clave de la persona; traducen de forma más natural. ``openai`` admite
  otra dirección compatible (OpenRouter, un servidor local...).

Detalles:

- Los bloques de código Markdown (``` y ~~~) no se envían a los traductores
  automáticos: se dejan tal cual. Las IA reciben el texto entero con la orden de
  conservar el Markdown, el código, los enlaces, las @menciones y las #referencias.
- Los textos largos se parten por párrafos.
- Caché en memoria: volver a traducir lo mismo no gasta otra petición.
- Respaldo: si el motor elegido falla, se prueban los gratuitos (Google y MyMemory).
- Errores con explicación para la persona (clave no válida, límite agotado...).
- Sin wx; se llama SIEMPRE fuera del hilo de la interfaz.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from typing import Any

import requests

from app.core import i18n  # noqa: F401 - instala _ y N_ aunque se importe suelto (pruebas)

log = logging.getLogger(__name__)

AUTO = "auto"

#: (código, nombre visible, nombre en inglés para las instrucciones a las IA). El código es el de Google.
IDIOMAS: list[tuple[str, str, str]] = [
	("af", N_("Afrikáans"), "Afrikaans"), ("sq", N_("Albanés"), "Albanian"), ("de", N_("Alemán"), "German"),
	("am", N_("Amárico"), "Amharic"), ("ar", N_("Árabe"), "Arabic"), ("hy", N_("Armenio"), "Armenian"),
	("az", N_("Azerí"), "Azerbaijani"), ("bn", N_("Bengalí"), "Bengali"), ("be", N_("Bielorruso"), "Belarusian"),
	("my", N_("Birmano"), "Burmese"), ("bs", N_("Bosnio"), "Bosnian"), ("bg", N_("Búlgaro"), "Bulgarian"),
	("km", N_("Camboyano (jemer)"), "Khmer"), ("kn", N_("Canarés"), "Kannada"), ("ca", N_("Catalán"), "Catalan"),
	("ceb", N_("Cebuano"), "Cebuano"), ("cs", N_("Checo"), "Czech"), ("zh-CN", N_("Chino simplificado"), "Simplified Chinese"),
	("zh-TW", N_("Chino tradicional"), "Traditional Chinese"), ("si", N_("Cingalés"), "Sinhala"), ("ko", N_("Coreano"), "Korean"),
	("co", N_("Corso"), "Corsican"), ("ht", N_("Criollo haitiano"), "Haitian Creole"), ("hr", N_("Croata"), "Croatian"),
	("da", N_("Danés"), "Danish"), ("sk", N_("Eslovaco"), "Slovak"), ("sl", N_("Esloveno"), "Slovenian"),
	("es", N_("Español"), "Spanish"), ("eo", N_("Esperanto"), "Esperanto"), ("et", N_("Estonio"), "Estonian"),
	("eu", N_("Euskera"), "Basque"), ("fi", N_("Finés"), "Finnish"), ("fr", N_("Francés"), "French"),
	("fy", N_("Frisón"), "Frisian"), ("gd", N_("Gaélico escocés"), "Scottish Gaelic"), ("cy", N_("Galés"), "Welsh"),
	("gl", N_("Gallego"), "Galician"), ("ka", N_("Georgiano"), "Georgian"), ("el", N_("Griego"), "Greek"),
	("gu", N_("Guyaratí"), "Gujarati"), ("ha", N_("Hausa"), "Hausa"), ("haw", N_("Hawaiano"), "Hawaiian"),
	("he", N_("Hebreo"), "Hebrew"), ("hi", N_("Hindi"), "Hindi"), ("hmn", N_("Hmong"), "Hmong"),
	("nl", N_("Neerlandés"), "Dutch"), ("hu", N_("Húngaro"), "Hungarian"), ("ig", N_("Igbo"), "Igbo"),
	("id", N_("Indonesio"), "Indonesian"), ("en", N_("Inglés"), "English"), ("ga", N_("Irlandés"), "Irish"),
	("is", N_("Islandés"), "Icelandic"), ("it", N_("Italiano"), "Italian"), ("ja", N_("Japonés"), "Japanese"),
	("jv", N_("Javanés"), "Javanese"), ("kk", N_("Kazajo"), "Kazakh"), ("rw", N_("Kinyarwanda"), "Kinyarwanda"),
	("ky", N_("Kirguís"), "Kyrgyz"), ("ku", N_("Kurdo"), "Kurdish"), ("lo", N_("Lao"), "Lao"),
	("la", N_("Latín"), "Latin"), ("lv", N_("Letón"), "Latvian"), ("lt", N_("Lituano"), "Lithuanian"),
	("lb", N_("Luxemburgués"), "Luxembourgish"), ("mk", N_("Macedonio"), "Macedonian"), ("ml", N_("Malayalam"), "Malayalam"),
	("ms", N_("Malayo"), "Malay"), ("mg", N_("Malgache"), "Malagasy"), ("mt", N_("Maltés"), "Maltese"),
	("mi", N_("Maorí"), "Maori"), ("mr", N_("Maratí"), "Marathi"), ("mn", N_("Mongol"), "Mongolian"),
	("ne", N_("Nepalí"), "Nepali"), ("no", N_("Noruego"), "Norwegian"), ("ny", N_("Nyanja"), "Chichewa"),
	("or", N_("Oriya"), "Odia"), ("pa", N_("Panyabí"), "Punjabi"), ("ps", N_("Pastún"), "Pashto"),
	("fa", N_("Persa"), "Persian"), ("pl", N_("Polaco"), "Polish"), ("pt", N_("Portugués"), "Portuguese"),
	("ro", N_("Rumano"), "Romanian"), ("ru", N_("Ruso"), "Russian"), ("sm", N_("Samoano"), "Samoan"),
	("sr", N_("Serbio"), "Serbian"), ("st", N_("Sesoto"), "Sesotho"), ("sn", N_("Shona"), "Shona"),
	("sd", N_("Sindi"), "Sindhi"), ("so", N_("Somalí"), "Somali"), ("sw", N_("Suajili"), "Swahili"),
	("sv", N_("Sueco"), "Swedish"), ("su", N_("Sundanés"), "Sundanese"), ("tl", N_("Tagalo (filipino)"), "Filipino"),
	("th", N_("Tailandés"), "Thai"), ("ta", N_("Tamil"), "Tamil"), ("tt", N_("Tártaro"), "Tatar"),
	("tg", N_("Tayiko"), "Tajik"), ("te", N_("Telugu"), "Telugu"), ("tr", N_("Turco"), "Turkish"),
	("tk", N_("Turcomano"), "Turkmen"), ("uk", N_("Ucraniano"), "Ukrainian"), ("ug", N_("Uigur"), "Uyghur"),
	("ur", N_("Urdu"), "Urdu"), ("uz", N_("Uzbeko"), "Uzbek"), ("vi", N_("Vietnamita"), "Vietnamese"),
	("xh", N_("Xhosa"), "Xhosa"), ("yi", N_("Yidis"), "Yiddish"), ("yo", N_("Yoruba"), "Yoruba"),
	("zu", N_("Zulú"), "Zulu"),
]
_POR_CODIGO = {codigo: (nombre, ingles) for codigo, nombre, ingles in IDIOMAS}

#: Motores: (identificador, nombre visible, ¿necesita clave?).
MOTORES: list[tuple[str, str, bool]] = [
	("google", N_("Google Translate (gratis, sin clave; no oficial, puede fallar a ratos)"), False),
	("mymemory", N_("MyMemory (gratis, sin clave; con límite diario)"), False),
	("libretranslate", N_("LibreTranslate (libre: su propio servidor o el público con clave)"), False),
	("google_cloud", N_("Google Translate con su clave (Google Cloud Translation, oficial)"), True),
	("microsoft", N_("Microsoft Translator de Azure (con su clave)"), True),
	("deepl", N_("DeepL con su clave (API oficial; la clave gratuita sirve)"), True),
	("gemini", N_("Google Gemini, inteligencia artificial (con su clave, tiene plan gratuito)"), True),
	("openai", N_("OpenAI ChatGPT, inteligencia artificial (con su clave)"), True),
	("deepseek", N_("DeepSeek, inteligencia artificial (con su clave)"), True),
	("claude", N_("Anthropic Claude, inteligencia artificial (con su clave)"), True),
]
MOTOR_POR_DEFECTO = "google"
#: Claves cifradas de cada motor (la de LibreTranslate es opcional: un servidor propio no la pide).
CLAVES_SECRETAS = {motor: f"traduccion.clave_{motor}" for motor, _nombre, con_clave in MOTORES if con_clave}
CLAVES_SECRETAS["libretranslate"] = "traduccion.clave_libretranslate"
#: Motores gratuitos que se prueban, por orden, si falla el elegido (con «respaldo»).
RESPALDOS = ("google", "mymemory")
#: Modelos por defecto: los más baratos que traducen bien (noviembre de 2026); se cambian en Preferencias.
MODELO_GEMINI = "gemini-3.5-flash-lite"
MODELO_OPENAI = "gpt-5-nano"
MODELO_DEEPSEEK = "deepseek-flash"
MODELO_CLAUDE = "claude-haiku-5-5"

#: Caracteres por petición a los traductores oficiales (admiten 5.000 o más).
MAXIMO_TROZO = 4500
#: Google gratis va por GET: el texto va en la dirección, que no puede ser muy larga.
MAXIMO_GOOGLE = 1800
#: MyMemory admite 500 bytes por petición.
MAXIMO_MYMEMORY = 480
#: Esperas (segundos) antes de reintentar Google gratis tras un 429 o un 503.
ESPERAS_GOOGLE = (2.0, 4.0, 8.0)
TIEMPO = (10.0, 60.0)
TIEMPO_IA = (10.0, 180.0)


def nombre_idioma(codigo: str) -> str:
	"""Nombre visible (traducido) de un código; «Detectar el idioma» para ``auto``."""
	if not codigo or codigo == AUTO:
		return _("Detectar el idioma")
	codigo_base = codigo if codigo in _POR_CODIGO else codigo.split("-")[0].lower()
	datos = _POR_CODIGO.get(codigo_base)
	return _(datos[0]) if datos else codigo


def nombre_motor(motor: str) -> str:
	return next((_(nombre) for clave, nombre, _clave in MOTORES if clave == motor), motor)


def idioma_de_la_interfaz() -> str:
	"""El idioma de la interfaz como destino de lo que se lee (``es`` o ``en``)."""
	return i18n.idioma_corto() or "es"


class ErrorTraduccion(Exception):
	"""Fallo al traducir, con un mensaje para la persona."""

	def __init__(self, mensaje: str, detalle: str = "") -> None:
		super().__init__(mensaje)
		self.mensaje_usuario = mensaje
		self.detalle = detalle


@dataclass
class Resultado:
	texto: str
	origen: str  # código detectado o el pedido («auto» si el motor no lo dice)
	destino: str
	motor: str
	del_cache: bool = False


@dataclass
class Ajustes:
	"""Lo que necesita un motor (de Preferencias y de los secretos)."""

	motor: str = MOTOR_POR_DEFECTO
	claves: dict[str, str] = field(default_factory=dict)
	#: Región del recurso de Azure (vacío si el recurso es global).
	region_microsoft: str = ""
	#: Correo para MyMemory (opcional; sube el límite diario).
	correo_mymemory: str = ""
	url_libretranslate: str = "https://libretranslate.com"
	modelo_gemini: str = MODELO_GEMINI
	modelo_openai: str = MODELO_OPENAI
	url_openai: str = "https://api.openai.com/v1"
	modelo_deepseek: str = MODELO_DEEPSEEK
	modelo_claude: str = MODELO_CLAUDE
	#: Si el motor elegido falla, probar con los gratuitos (``RESPALDOS``) en vez de dar el error.
	respaldo: bool = True
	#: Para las pruebas: cómo se espera entre reintentos (``time.sleep``).
	esperar: Callable[[float], None] | None = None


# ════════════════════════════════════════════════════════════════════════════
# Trocear y proteger el Markdown
# ════════════════════════════════════════════════════════════════════════════

_RE_BLOQUE = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[ \t]*$", re.MULTILINE | re.DOTALL)


def segmentos(texto: str) -> list[tuple[bool, str]]:
	"""Parte el Markdown en ``(traducible, texto)``: los bloques de código no se traducen."""
	partes: list[tuple[bool, str]] = []
	posicion = 0
	for bloque in _RE_BLOQUE.finditer(texto):
		if bloque.start() > posicion:
			partes.append((True, texto[posicion:bloque.start()]))
		partes.append((False, bloque.group(0)))
		posicion = bloque.end()
	if posicion < len(texto):
		partes.append((True, texto[posicion:]))
	return partes


def _bytes(texto: str) -> int:
	return len(texto.encode("utf-8"))


def trozos(texto: str, maximo: int = MAXIMO_TROZO, medida: Callable[[str], int] = len) -> list[str]:
	"""Parte un texto largo por párrafos (y, si hace falta, por líneas, frases o palabras) sin pasar de ``maximo``.

	:param medida: cómo se mide un trozo (``len`` en caracteres; ``_bytes`` para MyMemory).
	"""
	if medida(texto) <= maximo:
		return [texto]
	resultado: list[str] = []
	actual = ""
	for parrafo in re.split(r"(\n\s*\n)", texto):
		if medida(actual + parrafo) <= maximo:
			actual += parrafo
			continue
		if actual:
			resultado.append(actual)
			actual = ""
		while medida(parrafo) > maximo:
			# El corte más natural que quepa: fin de línea, fin de frase o espacio.
			limite = len(parrafo)
			while medida(parrafo[:limite]) > maximo:
				limite = int(limite * 0.9)
			corte = max(parrafo.rfind("\n", 0, limite), parrafo.rfind(". ", 0, limite) + 1)
			corte = corte if corte > limite // 3 else parrafo.rfind(" ", 0, limite)
			corte = corte if corte > 0 else limite
			resultado.append(parrafo[:corte])
			parrafo = parrafo[corte:]
		actual = parrafo
	if actual:
		resultado.append(actual)
	return resultado


def _espacios(original: str, traducido: str) -> str:
	"""Conserva los saltos de línea y espacios de los bordes (los traductores los comen)."""
	inicio = original[: len(original) - len(original.lstrip())]
	final = original[len(original.rstrip()):]
	return inicio + traducido.strip() + final


# ════════════════════════════════════════════════════════════════════════════
# Motores
# ════════════════════════════════════════════════════════════════════════════

_local = threading.local()


def _sesion() -> requests.Session:
	"""Sesión propia del traductor (una por hilo), SIN los reintentos automáticos de la red general.

	La sesión general reintenta los 429 y respeta ``Retry-After`` hasta dos minutos
	por intento: con un traductor eso deja la ventana esperando varios minutos
	(MyMemory pide esperar horas al agotar el cupo diario) y repite peticiones a un
	servicio que ya ha dicho «basta». Aquí cada fallo se ve al momento y lo decide
	el traductor: los reintentos educados de Google o pasar al motor de respaldo.
	"""
	from dataclasses import replace

	from app.core import red

	general = red._configuracion_global
	if getattr(_local, "base", None) is not general:
		anterior = getattr(_local, "sesion", None)
		if anterior is not None:
			anterior.close()
		_local.sesion = red.crear_sesion(replace(general, reintentos=0, espera_maxima_servidor=30.0))
		_local.base = general
	return _local.sesion


def _comprobar(respuesta: requests.Response, servicio: str) -> None:
	if respuesta.status_code < 400:
		return
	if respuesta.status_code in (401, 403):
		raise ErrorTraduccion(_("{s} no acepta la clave: compruébela en Preferencias, Claves de traducción.").format(s=servicio),
			f"{respuesta.status_code}: {respuesta.text[:300]}")
	if respuesta.status_code == 429:
		raise ErrorTraduccion(_("{s} dice que se han hecho demasiadas traducciones seguidas. Espere un poco o cambie de motor.").format(
			s=servicio), respuesta.text[:300])
	if respuesta.status_code == 456:
		raise ErrorTraduccion(_("Se ha agotado la cuota de caracteres de {s} de este mes.").format(s=servicio), respuesta.text[:300])
	raise ErrorTraduccion(_("{s} ha respondido con el error {c}.").format(s=servicio, c=respuesta.status_code), respuesta.text[:300])


def _google(texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	"""Google Translate gratis (no oficial). Reintenta con espera si Google pide calma (429/503)."""
	import time

	codigo = {"he": "iw", "jv": "jw"}
	parametros = {"client": "gtx", "sl": codigo.get(origen, origen), "tl": codigo.get(destino, destino), "dt": "t", "dj": "1",
		"q": texto}
	esperar = ajustes.esperar or time.sleep
	respuesta = None
	for espera in (*ESPERAS_GOOGLE, None):
		respuesta = _sesion().get("https://translate.googleapis.com/translate_a/single", params=parametros, timeout=TIEMPO)
		if respuesta.status_code not in (429, 503) or espera is None:
			break
		indicado = respuesta.headers.get("Retry-After", "")
		segundos = float(indicado) if indicado.isdigit() else espera
		if segundos > 30:
			break  # Google pide esperar demasiado: mejor decirlo que dejar la ventana esperando.
		log.info("Google Translate ha respondido %s; se reintenta dentro de %.0f s", respuesta.status_code, segundos)
		esperar(segundos)
	if respuesta.status_code in (429, 503):
		raise ErrorTraduccion(_("Google Translate gratis no atiende ahora (demasiadas peticiones desde su conexión). "
			"Pruebe dentro de un rato o elija en Preferencias, Traducción, otro motor: MyMemory es gratis y, con clave, "
			"Gemini y DeepL tienen plan gratuito."), f"{respuesta.status_code}: {respuesta.text[:200]}")
	_comprobar(respuesta, "Google Translate")
	datos = respuesta.json()
	traducido = "".join(frase.get("trans", "") for frase in datos.get("sentences") or [] if isinstance(frase, dict))
	detectado = {"iw": "he", "jw": "jv"}.get(datos.get("src") or "", datos.get("src") or origen)
	return traducido, detectado


def _mymemory(texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	"""MyMemory (Translated): API pública y gratuita, sin clave. Con un correo, el límite diario sube."""
	parametros = {"q": texto, "langpair": f"{'autodetect' if origen == AUTO else origen}|{destino}"}
	if ajustes.correo_mymemory:
		parametros["de"] = ajustes.correo_mymemory
	respuesta = _sesion().get("https://api.mymemory.translated.net/get", params=parametros, timeout=TIEMPO)
	try:
		datos = respuesta.json()
	except ValueError:
		_comprobar(respuesta, "MyMemory")
		raise
	# Con el cupo diario agotado responde 429 con la explicación en el JSON.
	estado = int(datos.get("responseStatus") or 200)
	traducido = (datos.get("responseData") or {}).get("translatedText") or ""
	if datos.get("quotaFinished") or estado in (403, 429) or "MYMEMORY WARNING" in traducido:
		raise ErrorTraduccion(_("Se ha agotado lo que MyMemory traduce gratis hoy. Escriba su correo en Preferencias, "
			"Claves de traducción (sube el límite a 50.000 caracteres al día) o use otro motor."), str(datos.get("responseDetails")))
	_comprobar(respuesta, "MyMemory")
	if estado >= 400:
		raise ErrorTraduccion(_("MyMemory no ha podido traducir: {m}").format(m=datos.get("responseDetails") or estado))
	detectado = (datos.get("responseData") or {}).get("detectedLanguage") or origen
	return traducido, str(detectado).split("-")[0] if detectado not in ("zh-CN", "zh-TW") else detectado


def _libretranslate(texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	"""LibreTranslate: libre; un servidor propio o libretranslate.com (que pide clave)."""
	url = (ajustes.url_libretranslate or "").rstrip("/")
	if not url:
		raise ErrorTraduccion(_("Falta la dirección del servidor LibreTranslate: escríbala en Preferencias, Claves de traducción."))
	codigo = {"zh-CN": "zh", "zh-TW": "zt"}
	cuerpo = {"q": texto, "source": codigo.get(origen, origen), "target": codigo.get(destino, destino), "format": "text"}
	if ajustes.claves.get("libretranslate"):
		cuerpo["api_key"] = ajustes.claves["libretranslate"]
	respuesta = _sesion().post(f"{url}/translate", json=cuerpo, timeout=TIEMPO)
	_comprobar(respuesta, "LibreTranslate")
	datos = respuesta.json()
	return datos.get("translatedText", ""), ((datos.get("detectedLanguage") or {}).get("language") or origen)


def _google_cloud(texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	clave = ajustes.claves.get("google_cloud", "")
	if not clave:
		raise ErrorTraduccion(_("Falta la clave de Google Cloud Translation: escríbala en Preferencias, Claves de traducción."))
	cuerpo = {"q": texto, "target": destino, "format": "text"}
	if origen != AUTO:
		cuerpo["source"] = origen
	respuesta = _sesion().post("https://translation.googleapis.com/language/translate/v2", params={"key": clave}, json=cuerpo,
		timeout=TIEMPO)
	_comprobar(respuesta, "Google Cloud Translation")
	traduccion = respuesta.json()["data"]["translations"][0]
	return traduccion["translatedText"], traduccion.get("detectedSourceLanguage") or origen


def _microsoft(texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	clave = ajustes.claves.get("microsoft", "")
	if not clave:
		raise ErrorTraduccion(_("Falta la clave de Microsoft Translator: escríbala en Preferencias, Claves de traducción."))
	codigo = {"zh-CN": "zh-Hans", "zh-TW": "zh-Hant", "tl": "fil", "sr": "sr-Cyrl", "ku": "kmr", "mn": "mn-Cyrl", "no": "nb"}
	parametros = {"api-version": "3.0", "to": codigo.get(destino, destino)}
	if origen != AUTO:
		parametros["from"] = codigo.get(origen, origen)
	cabeceras = {"Ocp-Apim-Subscription-Key": clave}
	if ajustes.region_microsoft:
		cabeceras["Ocp-Apim-Subscription-Region"] = ajustes.region_microsoft
	respuesta = _sesion().post("https://api.cognitive.microsofttranslator.com/translate", params=parametros,
		json=[{"Text": texto}], headers=cabeceras, timeout=TIEMPO)
	_comprobar(respuesta, "Microsoft Translator")
	datos = respuesta.json()[0]
	detectado = (datos.get("detectedLanguage") or {}).get("language") or origen
	inverso = {v: k for k, v in codigo.items()}
	return datos["translations"][0]["text"], inverso.get(detectado, detectado)


def _deepl(texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	clave = ajustes.claves.get("deepl", "")
	if not clave:
		raise ErrorTraduccion(_("Falta la clave de DeepL: escríbala en Preferencias, Claves de traducción."))
	destinos = {"en": "EN-US", "pt": "PT-PT", "zh-CN": "ZH-HANS", "zh-TW": "ZH-HANT"}
	datos = {"text": texto, "target_lang": destinos.get(destino, destino.upper()), "preserve_formatting": "1"}
	if origen != AUTO:
		datos["source_lang"] = origen.split("-")[0].upper()
	base = "https://api-free.deepl.com" if clave.endswith(":fx") else "https://api.deepl.com"
	respuesta = _sesion().post(f"{base}/v2/translate", data=datos, headers={"Authorization": f"DeepL-Auth-Key {clave}"},
		timeout=TIEMPO)
	_comprobar(respuesta, "DeepL")
	traduccion = respuesta.json()["translations"][0]
	return traduccion["text"], (traduccion.get("detected_source_language") or origen).lower()


def instrucciones_ia(origen: str, destino: str) -> str:
	"""Orden para las IA: traducir y nada más, conservando el Markdown de GitHub."""
	nombre_destino = _POR_CODIGO.get(destino, ("", destino))[1]
	de = f"from {_POR_CODIGO.get(origen, ('', origen))[1]} " if origen != AUTO else ""
	return (
		f"You are a professional translator for GitHub conversations. Translate the user's text {de}into {nombre_destino}. "
		"Keep the meaning and tone, and write natural, fluent text, not a literal translation. Preserve the Markdown "
		"formatting exactly, and do not translate code blocks, inline code, URLs, file names, @mentions, #references or "
		"commit hashes. Reply with the translation only, without explanations, notes or quotation marks."
	)


def _gemini(texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	clave = ajustes.claves.get("gemini", "")
	if not clave:
		raise ErrorTraduccion(_("Falta la clave de Gemini: escríbala en Preferencias, Claves de traducción."))
	modelo = ajustes.modelo_gemini or MODELO_GEMINI
	respuesta = _sesion().post(
		f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
		headers={"x-goog-api-key": clave}, timeout=TIEMPO_IA,
		json={"systemInstruction": {"parts": [{"text": instrucciones_ia(origen, destino)}]},
			"contents": [{"role": "user", "parts": [{"text": texto}]}]},
	)
	_comprobar(respuesta, "Gemini")
	candidatos = respuesta.json().get("candidates") or []
	partes = ((candidatos[0].get("content") or {}).get("parts") or []) if candidatos else []
	# Las partes de razonamiento («thought») no son la traducción.
	return "".join(p.get("text", "") for p in partes if not p.get("thought")), origen


def _chat_compatible(texto: str, origen: str, destino: str, url: str, clave: str, modelo: str, servicio: str) -> tuple[str, str]:
	"""API de chat compatible con OpenAI (OpenAI, DeepSeek...). Sin «temperature»: los modelos de
	razonamiento (gpt-5-nano) solo admiten el valor por defecto y la rechazan con un 400."""
	respuesta = _sesion().post(
		f"{url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {clave}"} if clave else {}, timeout=TIEMPO_IA,
		json={"model": modelo, "messages": [
			{"role": "system", "content": instrucciones_ia(origen, destino)}, {"role": "user", "content": texto}]},
	)
	_comprobar(respuesta, servicio)
	return respuesta.json()["choices"][0]["message"]["content"], origen


def _openai(texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	clave = ajustes.claves.get("openai", "")
	url = ajustes.url_openai or "https://api.openai.com/v1"
	if not clave and "localhost" not in url and "127.0.0.1" not in url:
		raise ErrorTraduccion(_("Falta la clave de OpenAI: escríbala en Preferencias, Claves de traducción."))
	return _chat_compatible(texto, origen, destino, url, clave, ajustes.modelo_openai or MODELO_OPENAI, "OpenAI")


def _deepseek(texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	clave = ajustes.claves.get("deepseek", "")
	if not clave:
		raise ErrorTraduccion(_("Falta la clave de DeepSeek: escríbala en Preferencias, Claves de traducción."))
	return _chat_compatible(texto, origen, destino, "https://api.deepseek.com", clave, ajustes.modelo_deepseek or MODELO_DEEPSEEK,
		"DeepSeek")


def _claude(texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	"""API de mensajes de Anthropic. Con Claude Haiku 5.5 el razonamiento va siempre activo: «effort» bajo
	para traducir rápido y barato, y sin «temperature» (un valor distinto del de fábrica da un 400)."""
	clave = ajustes.claves.get("claude", "")
	if not clave:
		raise ErrorTraduccion(_("Falta la clave de Claude: escríbala en Preferencias, Claves de traducción."))
	respuesta = _sesion().post(
		"https://api.anthropic.com/v1/messages", timeout=TIEMPO_IA,
		headers={"x-api-key": clave, "anthropic-version": "2023-06-01"},
		json={"model": ajustes.modelo_claude or MODELO_CLAUDE, "max_tokens": 16000, "output_config": {"effort": "low"},
			"system": instrucciones_ia(origen, destino), "messages": [{"role": "user", "content": texto}]},
	)
	_comprobar(respuesta, "Claude")
	datos = respuesta.json()
	if datos.get("stop_reason") == "refusal":
		raise ErrorTraduccion(_("Claude no ha querido traducir este texto. Pruebe con otro motor."))
	# Solo los bloques de texto: los de razonamiento («thinking») no son la traducción.
	return "".join(b.get("text", "") for b in datos.get("content") or [] if b.get("type") == "text"), origen


#: motor → (función, ¿recibe el texto entero con el Markdown?). Los automáticos van por trozos sin bloques de código.
_FUNCIONES: dict[str, tuple[Callable[[str, str, str, Ajustes], tuple[str, str]], bool]] = {
	"google": (_google, False), "mymemory": (_mymemory, False), "libretranslate": (_libretranslate, False),
	"google_cloud": (_google_cloud, False), "microsoft": (_microsoft, False),
	"deepl": (_deepl, False), "gemini": (_gemini, True), "openai": (_openai, True), "deepseek": (_deepseek, True),
	"claude": (_claude, True),
}


# ════════════════════════════════════════════════════════════════════════════
# Traductor
# ════════════════════════════════════════════════════════════════════════════

_cache: OrderedDict[tuple, Resultado] = OrderedDict()
_candado_cache = threading.Lock()
MAXIMO_CACHE = 300


def _traducir_con(motor: str, texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	funcion, entero = _FUNCIONES[motor]
	if entero:
		traducido, detectado = funcion(texto, origen, destino, ajustes)
		return _espacios(texto, traducido), detectado
	salida: list[str] = []
	detectado = origen
	for traducible, parte in segmentos(texto):
		if not traducible or not parte.strip():
			salida.append(parte)
			continue
		if motor == "mymemory":
			partes_texto = trozos(parte, MAXIMO_MYMEMORY, _bytes)
		else:
			partes_texto = trozos(parte, MAXIMO_GOOGLE if motor == "google" else MAXIMO_TROZO)
		for trozo in partes_texto:
			if not trozo.strip():
				salida.append(trozo)
				continue
			traducido, detectado_trozo = funcion(trozo, origen, destino, ajustes)
			if detectado == AUTO:
				detectado = detectado_trozo or AUTO
			salida.append(_espacios(trozo, traducido))
	return "".join(salida), detectado


def _intentar(motor: str, texto: str, origen: str, destino: str, ajustes: Ajustes) -> tuple[str, str]:
	"""Un motor, con los fallos convertidos en ``ErrorTraduccion`` explicados."""
	from app.core.red import ErrorRed

	try:
		traducido, detectado = _traducir_con(motor, texto, origen, destino, ajustes)
	except ErrorRed as error:
		# El servicio pidió antes esperar mucho (cupo agotado, Retry-After largo): no se insiste.
		raise ErrorTraduccion(_("{m} ha pedido que no se le hagan más peticiones durante un rato ({e}). Pruebe con otro "
			"motor.").format(m=nombre_motor_corto(motor), e=error), getattr(error, "detalle", "")) from error
	except requests.RequestException as error:
		raise ErrorTraduccion(_("No se ha podido conectar con {m}. Compruebe la conexión.").format(m=nombre_motor_corto(motor)),
			str(error)) from error
	except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
		raise ErrorTraduccion(_("{m} ha respondido algo que no se entiende. Pruebe con otro motor.").format(
			m=nombre_motor_corto(motor)), repr(error)) from error
	if not traducido.strip():
		raise ErrorTraduccion(_("{m} no ha devuelto ningún texto. Pruebe con otro motor.").format(m=nombre_motor_corto(motor)))
	return traducido, detectado


def nombre_motor_corto(motor: str) -> str:
	"""Nombre del servicio para los mensajes (sin las explicaciones del desplegable)."""
	return {"google": "Google Translate", "mymemory": "MyMemory", "libretranslate": "LibreTranslate",
		"google_cloud": "Google Cloud Translation", "microsoft": "Microsoft Translator", "deepl": "DeepL", "gemini": "Gemini",
		"openai": "OpenAI", "deepseek": "DeepSeek", "claude": "Claude"}.get(motor, motor)


def traducir(texto: str, destino: str, origen: str = AUTO, ajustes: Ajustes | None = None) -> Resultado:
	"""Traduce ``texto`` a ``destino``. Lanza ``ErrorTraduccion`` con un mensaje para la persona."""
	ajustes = ajustes or Ajustes()
	motor = ajustes.motor if ajustes.motor in _FUNCIONES else MOTOR_POR_DEFECTO
	if not (texto or "").strip():
		return Resultado(texto or "", origen, destino, motor)
	# Todos los ajustes de texto (modelos, direcciones...) cuentan: otro modelo da otra traducción.
	clave = (motor, origen, destino, texto, _ajustes_de_texto(ajustes))
	with _candado_cache:
		if clave in _cache:
			_cache.move_to_end(clave)
			anterior = _cache[clave]
			return Resultado(anterior.texto, anterior.origen, anterior.destino, anterior.motor, del_cache=True)
	motores = [motor] + ([m for m in RESPALDOS if m != motor] if ajustes.respaldo else [])
	primer_error: ErrorTraduccion | None = None
	for intento in motores:
		try:
			traducido, detectado = _intentar(intento, texto, origen, destino, ajustes)
			motor = intento
			break
		except ErrorTraduccion as error:
			primer_error = primer_error or error
			if intento != motores[-1]:
				log.warning("El motor %s ha fallado (%s); se prueba con %s", intento, error.detalle or error, motores[motores.index(intento) + 1])
	else:
		# Se da el error del motor elegido: es el que la persona puede arreglar (clave, cuota...).
		raise primer_error or ErrorTraduccion(_("No se ha podido traducir."))
	resultado = Resultado(traducido, detectado or origen, destino, motor)
	with _candado_cache:
		_cache[clave] = resultado
		while len(_cache) > MAXIMO_CACHE:
			_cache.popitem(last=False)
	return resultado


def _ajustes_de_texto(ajustes: Ajustes) -> tuple[tuple[str, str], ...]:
	return tuple((campo.name, getattr(ajustes, campo.name)) for campo in fields(ajustes) if campo.type == "str")


def ajustes_desde(config: Any, secretos: Any = None, motor: str | None = None) -> Ajustes:
	"""Ajustes del motor (de Preferencias) con sus claves (de los secretos cifrados).

	Cada campo de texto de ``Ajustes`` se lee de «traduccion.<campo>»; si falta o está vacío,
	vale el de fábrica del propio ``Ajustes``. Así, un motor nuevo solo añade su campo aquí
	y su valor en ``configuracion.py``. ``config`` y ``secretos`` solo necesitan ``obtener``:
	Preferencias pasa unos que leen lo escrito en el diálogo, para probar sin guardar.
	"""
	claves = {}
	if secretos is not None:
		for nombre, clave_secreta in CLAVES_SECRETAS.items():
			try:
				claves[nombre] = str(secretos.obtener(clave_secreta) or "").strip()
			except Exception:  # noqa: BLE001 - sin clave, el motor lo explicará
				log.debug("No se pudo leer el secreto %s", clave_secreta, exc_info=True)
	textos = {}
	for campo in fields(Ajustes):
		if campo.type == "str" and campo.name != "motor":
			valor = str(config.obtener(f"traduccion.{campo.name}", campo.default) or "").strip()
			textos[campo.name] = valor or campo.default
	return Ajustes(
		motor=motor or str(config.obtener("traduccion.motor", MOTOR_POR_DEFECTO) or MOTOR_POR_DEFECTO),
		claves=claves,
		respaldo=bool(config.obtener("traduccion.respaldo", True)),
		**textos,
	)


def con_original(traducido: str, original: str, origen: str) -> str:
	"""El texto traducido con el original plegado al final (``<details>`` de GitHub)."""
	# En inglés y no en el idioma de la interfaz: lo leen las personas del repositorio.
	idioma = _POR_CODIGO.get(origen, ("", ""))[1]
	resumen = f"Original ({idioma})" if idioma else "Original"
	return f"{traducido.rstrip()}\n\n<details>\n<summary>{resumen}</summary>\n\n{original.strip()}\n\n</details>\n"
