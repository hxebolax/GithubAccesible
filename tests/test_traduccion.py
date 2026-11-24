"""Traductor (incidencia #13): motores, Markdown, respaldo, caché y las pantallas que lo usan.

Sin red: la sesión HTTP se sustituye por una que responde lo programado y apunta
cada petición, para comprobar que a cada servicio se le pide lo que documenta.
"""

from __future__ import annotations

from unittest import mock

import pytest
import wx

from app.services import traduccion as tr
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto
from tests.apoyo_app import crear_contexto


class Respuesta:
	def __init__(self, datos=None, estado: int = 200, cabeceras: dict | None = None, texto: str = "") -> None:
		self._datos = datos
		self.status_code = estado
		self.headers = cabeceras or {}
		self.text = texto or (str(datos) if datos is not None else "")

	def json(self):
		return self._datos


class SesionFalsa:
	"""Devuelve las respuestas en orden (o lo que calcule ``responder``) y apunta las peticiones."""

	def __init__(self, *respuestas, responder=None) -> None:
		self.respuestas = list(respuestas)
		self.responder = responder
		self.peticiones: list[tuple[str, str, dict]] = []

	def _pedir(self, metodo: str, url: str, **opciones):
		self.peticiones.append((metodo, url, opciones))
		if self.responder is not None:
			return self.responder(metodo, url, opciones)
		return self.respuestas.pop(0)

	def get(self, url, **opciones):
		return self._pedir("GET", url, **opciones)

	def post(self, url, **opciones):
		return self._pedir("POST", url, **opciones)


@pytest.fixture(autouse=True)
def _cache_vacia():
	tr._cache.clear()
	yield
	tr._cache.clear()


def _con_sesion(sesion: SesionFalsa):
	return mock.patch.object(tr, "_sesion", return_value=sesion)


def _google(texto: str, origen: str = "es") -> Respuesta:
	return Respuesta({"sentences": [{"trans": texto, "orig": "x"}], "src": origen})


# ════════════════════════════════════════════════════════════════════════════
# Markdown y troceado
# ════════════════════════════════════════════════════════════════════════════


def test_los_bloques_de_codigo_no_se_traducen():
	texto = "Hola\n\n```python\nprint('hola')\n```\n\nAdiós\n~~~\ncódigo\n~~~\n"
	partes = tr.segmentos(texto)
	assert [traducible for traducible, _t in partes] == [True, False, True, False, True]
	assert "".join(t for _t2, t in partes) == texto

	sesion = SesionFalsa(responder=lambda _m, _u, o: _google(o["params"]["q"].upper()))
	with _con_sesion(sesion):
		resultado = tr.traducir(texto, "en", ajustes=tr.Ajustes(motor="google", respaldo=False))
	assert "print('hola')" in resultado.texto and "código" in resultado.texto
	assert "HOLA" in resultado.texto and "ADIÓS" in resultado.texto
	assert all("print" not in o["params"]["q"] for _m, _u, o in sesion.peticiones)
	assert resultado.texto.endswith("~~~\n"), "se conservan los saltos de línea de los bordes"


def test_trozos_por_parrafos_sin_pasar_del_maximo():
	texto = ("Una frase de prueba. " * 30 + "\n\n") * 5
	partes = tr.trozos(texto, 300)
	assert "".join(partes) == texto
	assert all(len(p) <= 300 for p in partes)
	assert tr.trozos("corto", 300) == ["corto"]
	en_bytes = tr.trozos("ñ" * 600, tr.MAXIMO_MYMEMORY, tr._bytes)
	assert all(tr._bytes(p) <= tr.MAXIMO_MYMEMORY for p in en_bytes) and "".join(en_bytes) == "ñ" * 600


# ════════════════════════════════════════════════════════════════════════════
# Google gratis: reintentos educados y error explicado
# ════════════════════════════════════════════════════════════════════════════


def test_google_reintenta_con_espera_tras_un_429():
	esperas: list[float] = []
	sesion = SesionFalsa(Respuesta(estado=429, cabeceras={"Retry-After": "3"}), _google("Thanks"))
	with _con_sesion(sesion):
		resultado = tr.traducir("Gracias", "en", ajustes=tr.Ajustes(respaldo=False, esperar=esperas.append))
	assert resultado.texto == "Thanks" and resultado.origen == "es" and resultado.motor == "google"
	assert esperas == [3.0], "respeta el Retry-After"
	metodo, url, opciones = sesion.peticiones[0]
	assert metodo == "GET" and url.endswith("/translate_a/single")
	assert opciones["params"]["client"] == "gtx" and opciones["params"]["sl"] == "auto" and opciones["params"]["tl"] == "en"


def test_google_bloqueado_da_un_error_que_se_entiende():
	esperas: list[float] = []
	sesion = SesionFalsa(responder=lambda *_a: Respuesta(estado=429, texto="Sorry..."))
	with _con_sesion(sesion), pytest.raises(tr.ErrorTraduccion) as error:
		tr.traducir("Gracias", "en", ajustes=tr.Ajustes(respaldo=False, esperar=esperas.append))
	assert esperas == list(tr.ESPERAS_GOOGLE) and len(sesion.peticiones) == len(tr.ESPERAS_GOOGLE) + 1
	assert "MyMemory" in error.value.mensaje_usuario
	# Si Google pide esperar demasiado, no se deja a la persona esperando.
	sesion = SesionFalsa(responder=lambda *_a: Respuesta(estado=429, cabeceras={"Retry-After": "600"}))
	with _con_sesion(sesion), pytest.raises(tr.ErrorTraduccion):
		tr.traducir("Hola", "en", ajustes=tr.Ajustes(respaldo=False, esperar=esperas.append))
	assert len(sesion.peticiones) == 1


def test_codigos_especiales_de_google():
	sesion = SesionFalsa(Respuesta({"sentences": [{"trans": "שלום"}], "src": "iw"}))
	with _con_sesion(sesion):
		resultado = tr.traducir("Hola", "he", ajustes=tr.Ajustes(respaldo=False))
	assert sesion.peticiones[0][2]["params"]["tl"] == "iw" and resultado.origen == "he"


def test_la_sesion_del_traductor_no_reintenta_sola():
	"""Ni insiste ante un 429 ni duerme lo que pida el servidor: lo decide el traductor."""
	sesion = tr._sesion()
	reintentos = sesion.get_adapter("https://translate.googleapis.com").max_retries
	assert reintentos.total == 0 and reintentos.status == 0
	assert tr._sesion() is sesion, "una por hilo, reutilizada"


# ════════════════════════════════════════════════════════════════════════════
# Respaldo y caché
# ════════════════════════════════════════════════════════════════════════════


def test_si_google_falla_se_traduce_con_mymemory():
	def responder(_metodo, url, _opciones):
		if "googleapis" in url:
			return Respuesta(estado=429)
		return Respuesta({"responseStatus": 200, "responseData": {"translatedText": "Thanks", "detectedLanguage": "es-ES"}})

	sesion = SesionFalsa(responder=responder)
	with _con_sesion(sesion):
		resultado = tr.traducir("Gracias", "en", ajustes=tr.Ajustes(esperar=lambda _s: None))
	assert resultado.motor == "mymemory" and resultado.texto == "Thanks" and resultado.origen == "es"


def test_motor_con_clave_que_falla_usa_los_gratuitos_o_da_su_error():
	def responder(_metodo, url, _opciones):
		if "deepl" in url:
			return Respuesta(estado=403, texto="Forbidden")
		return _google("Thanks")

	with _con_sesion(SesionFalsa(responder=responder)):
		resultado = tr.traducir("Gracias", "en", ajustes=tr.Ajustes(motor="deepl", claves={"deepl": "x:fx"}))
	assert resultado.motor == "google"
	tr._cache.clear()
	with _con_sesion(SesionFalsa(responder=responder)), pytest.raises(tr.ErrorTraduccion) as error:
		tr.traducir("Gracias", "en", ajustes=tr.Ajustes(motor="deepl", claves={"deepl": "x:fx"}, respaldo=False))
	assert "clave" in error.value.mensaje_usuario and "DeepL" in error.value.mensaje_usuario
	# Sin clave se dice dónde escribirla.
	with _con_sesion(SesionFalsa()), pytest.raises(tr.ErrorTraduccion) as error:
		tr.traducir("Gracias", "en", ajustes=tr.Ajustes(motor="gemini", respaldo=False))
	assert "Claves de traducción" in error.value.mensaje_usuario


def test_la_segunda_vez_sale_de_la_cache():
	sesion = SesionFalsa(_google("Thanks"))
	with _con_sesion(sesion):
		primera = tr.traducir("Gracias", "en")
		segunda = tr.traducir("Gracias", "en")
	assert not primera.del_cache and segunda.del_cache and segunda.texto == "Thanks"
	assert len(sesion.peticiones) == 1


def test_texto_vacio_no_hace_peticiones():
	with _con_sesion(SesionFalsa()):
		assert tr.traducir("  ", "en").texto == "  "


# ════════════════════════════════════════════════════════════════════════════
# Lo que se pide a cada servicio
# ════════════════════════════════════════════════════════════════════════════


def test_peticiones_de_los_traductores_con_clave():
	casos = {
		"google_cloud": Respuesta({"data": {"translations": [{"translatedText": "Thanks", "detectedSourceLanguage": "es"}]}}),
		"microsoft": Respuesta([{"detectedLanguage": {"language": "es"}, "translations": [{"text": "Thanks"}]}]),
		"deepl": Respuesta({"translations": [{"text": "Thanks", "detected_source_language": "ES"}]}),
		"libretranslate": Respuesta({"translatedText": "Thanks", "detectedLanguage": {"language": "es"}}),
	}
	claves = {"google_cloud": "g", "microsoft": "m", "deepl": "d:fx", "libretranslate": "l"}
	for motor, respuesta in casos.items():
		sesion = SesionFalsa(respuesta)
		with _con_sesion(sesion):
			resultado = tr.traducir("Gracias", "en", ajustes=tr.Ajustes(motor=motor, claves=claves, respaldo=False,
				region_microsoft="westeurope", url_libretranslate="http://localhost:5000/"))
		assert (resultado.texto, resultado.origen, resultado.motor) == ("Thanks", "es", motor)
		metodo, url, opciones = sesion.peticiones[0]
		assert metodo == "POST"
		if motor == "google_cloud":
			assert opciones["params"] == {"key": "g"} and opciones["json"]["target"] == "en" and "source" not in opciones["json"]
		elif motor == "microsoft":
			assert opciones["headers"] == {"Ocp-Apim-Subscription-Key": "m", "Ocp-Apim-Subscription-Region": "westeurope"}
			assert opciones["params"]["to"] == "en" and opciones["json"] == [{"Text": "Gracias"}]
		elif motor == "deepl":
			assert url.startswith("https://api-free.deepl.com") and opciones["data"]["target_lang"] == "EN-US"
			assert opciones["headers"] == {"Authorization": "DeepL-Auth-Key d:fx"}
		else:
			assert url == "http://localhost:5000/translate" and opciones["json"]["api_key"] == "l"


def test_peticiones_de_las_inteligencias_artificiales():
	casos = {
		"gemini": Respuesta({"candidates": [{"content": {"parts": [{"text": "pensando", "thought": True}, {"text": "Thanks"}]}}]}),
		"openai": Respuesta({"choices": [{"message": {"content": "Thanks"}}]}),
		"deepseek": Respuesta({"choices": [{"message": {"content": "Thanks"}}]}),
		"claude": Respuesta({"stop_reason": "end_turn", "content": [{"type": "thinking", "thinking": "..."},
			{"type": "text", "text": "Thanks"}]}),
	}
	claves = {motor: f"clave-{motor}" for motor in casos}
	texto = "Gracias\n\n```\ncódigo\n```"
	for motor, respuesta in casos.items():
		sesion = SesionFalsa(respuesta)
		with _con_sesion(sesion):
			resultado = tr.traducir(texto, "en", "es", tr.Ajustes(motor=motor, claves=claves, respaldo=False))
		assert resultado.texto == "Thanks" and resultado.motor == motor, motor
		_metodo, url, opciones = sesion.peticiones[0]
		cuerpo = str(opciones["json"])
		assert "código" in cuerpo, "las IA reciben el texto entero, con el Markdown"
		assert "into English" in cuerpo and "from Spanish" in cuerpo
		assert "temperature" not in opciones["json"]
		if motor == "gemini":
			assert tr.MODELO_GEMINI in url and opciones["headers"] == {"x-goog-api-key": "clave-gemini"}
		elif motor in ("openai", "deepseek"):
			assert url.endswith("/chat/completions") and opciones["headers"] == {"Authorization": f"Bearer clave-{motor}"}
			assert opciones["json"]["model"] == (tr.MODELO_OPENAI if motor == "openai" else tr.MODELO_DEEPSEEK)
		else:
			assert url == "https://api.anthropic.com/v1/messages"
			assert opciones["headers"]["x-api-key"] == "clave-claude" and opciones["headers"]["anthropic-version"] == "2023-06-01"
			assert opciones["json"]["model"] == tr.MODELO_CLAUDE and opciones["json"]["output_config"] == {"effort": "low"}


def test_claude_que_se_niega_da_un_error_explicado():
	sesion = SesionFalsa(Respuesta({"stop_reason": "refusal", "content": []}))
	with _con_sesion(sesion), pytest.raises(tr.ErrorTraduccion) as error:
		tr.traducir("Hola", "en", ajustes=tr.Ajustes(motor="claude", claves={"claude": "x"}, respaldo=False))
	assert "Claude" in error.value.mensaje_usuario


def test_mymemory_con_correo_y_cuota_agotada():
	sesion = SesionFalsa(Respuesta({"responseStatus": 429, "quotaFinished": None, "responseData": {"translatedText":
		"MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY."}}, estado=429, cabeceras={"Retry-After": "12848"}))
	with _con_sesion(sesion), pytest.raises(tr.ErrorTraduccion) as error:
		tr.traducir("Hola", "en", "es", tr.Ajustes(motor="mymemory", correo_mymemory="yo@example.org", respaldo=False))
	assert "correo" in error.value.mensaje_usuario
	parametros = sesion.peticiones[0][2]["params"]
	assert parametros["langpair"] == "es|en" and parametros["de"] == "yo@example.org"


def test_ajustes_desde_la_configuracion_y_los_secretos():
	ctx, _api, _a = crear_contexto()
	ctx.config.establecer("traduccion.motor", "deepl")
	ctx.secretos.guardar("traduccion.clave_deepl", "abc:fx")
	ajustes = tr.ajustes_desde(ctx.config, ctx.secretos)
	assert ajustes.motor == "deepl" and ajustes.claves["deepl"] == "abc:fx" and ajustes.claves["gemini"] == ""
	assert ajustes.modelo_gemini == tr.MODELO_GEMINI and ajustes.respaldo is True


def test_original_plegado_al_final():
	texto = tr.con_original("Thanks", "Gracias", "es")
	assert texto.startswith("Thanks\n\n<details>") and "<summary>Original (Spanish)</summary>" in texto and "Gracias" in texto


def test_nombres_de_idiomas_y_motores():
	assert tr.nombre_idioma("es") == "Español" and tr.nombre_idioma("zh-CN") == "Chino simplificado"
	assert tr.nombre_idioma(tr.AUTO) == "Detectar el idioma"
	codigos = [codigo for codigo, _n, _i in tr.IDIOMAS]
	assert len(codigos) == len(set(codigos)) > 100
	assert {m for m, _n, _c in tr.MOTORES} == set(tr._FUNCIONES)


# ════════════════════════════════════════════════════════════════════════════
# Pantallas
# ════════════════════════════════════════════════════════════════════════════


def test_ventana_del_traductor(app_wx):
	from app.ui import traductor

	ctx, _api, anuncios = crear_contexto()
	sesion = SesionFalsa(_google("Thanks, I will check it tomorrow."))
	with _con_sesion(sesion):
		ventana = traductor.abrir_traductor(ctx, None, "Gracias, lo miro mañana.", "ana, comentario", traducir_ya=True)
	try:
		afirmar_teclado_correcto(ventana)
		assert ventana.GetTitle() == "Traductor: ana, comentario"
		assert ventana.codigo_destino == "es" and ventana.codigo_origen == tr.AUTO and ventana.codigo_motor == "google"
		assert ventana.campo_traducido.GetValue() == "Thanks, I will check it tomorrow."
		assert "Traducido del español al español con Google Translate" in ventana.estado.GetLabel()
		ventana.intercambiar()
		assert ventana.codigo_origen == "es" and ventana.codigo_destino == "es"
		assert ventana.campo_original.GetValue() == "Thanks, I will check it tomorrow." and ventana.campo_traducido.GetValue() == ""
		assert traductor.abrir_traductor(ctx) is ventana, "una sola ventana"
	finally:
		ventana.Destroy()
	assert "Traduciendo…" in anuncios


def test_editor_traduce_antes_de_enviar(app_wx, marco, dialogo_modal):
	from app.ui.editor import DialogoEditor

	ctx, _api, _a = crear_contexto()
	enviados: list[dict] = []
	dialogo = DialogoEditor(marco, ctx, "Nueva issue", lambda valores: enviados.append(valores) or valores, con_titulo=True,
		titulo="Falla la descarga", cuerpo="Se cancela al cerrar la ventana.")
	afirmar_teclado_correcto(dialogo)
	assert dialogo.idioma_envio == "" and dialogo.selector_traduccion.GetString(0) == "No traducir"
	dialogo.selector_traduccion.SetSelection(dialogo._codigos_traduccion.index("en"))

	def responder(_metodo, _url, opciones):
		return _google({"Falla la descarga": "Download fails"}.get(opciones["params"]["q"], "It is cancelled when closing the window."))

	dialogo_modal.responder(wx.ID_OK)
	with _con_sesion(SesionFalsa(responder=responder)):
		dialogo._al_aceptar(None)
	assert enviados == [{"titulo": "Download fails", "cuerpo": "It is cancelled when closing the window."}]
	assert ctx.config.obtener("traduccion.destino_envio") == "en", "se recuerda el último idioma elegido"


def test_volver_a_editar_no_envia(app_wx, marco, dialogo_modal):
	from app.ui.editor import DialogoEditor

	ctx, _api, _a = crear_contexto()
	ctx.config.establecer("traduccion.destino_envio", "fr")
	enviados: list[dict] = []
	dialogo = DialogoEditor(marco, ctx, "Comentar", lambda valores: enviados.append(valores), cuerpo="Hola")
	assert dialogo.idioma_envio == "fr"
	dialogo_modal.responder(wx.ID_CANCEL)
	with _con_sesion(SesionFalsa(_google("Bonjour"))):
		dialogo._al_aceptar(None)
	assert enviados == [] and dialogo.boton_enviar.IsEnabled()


def test_original_plegado_al_enviar(app_wx, marco, dialogo_modal, monkeypatch):
	from app.ui import traductor

	ctx, _api, _a = crear_contexto()
	ctx.config.establecer("traduccion.incluir_original", True)
	recibido: list = []
	dialogo_modal.responder(wx.ID_OK)
	with _con_sesion(SesionFalsa(_google("Thanks"))):
		traductor.revisar_y_enviar(marco, ctx, None, "Gracias", "en", lambda titulo, cuerpo: recibido.append((titulo, cuerpo)))
	titulo, cuerpo = recibido[0]
	assert titulo is None and cuerpo.startswith("Thanks") and "<details>" in cuerpo and "Gracias" in cuerpo


def test_teclado_de_revisar_la_traduccion(app_wx):
	from app.ui.traductor import DialogoRevisarTraduccion

	resultado = tr.Resultado("Thanks", "es", "en", "google")
	dialogo = DialogoRevisarTraduccion(None, "Title", "Thanks", "Gracias", resultado)
	try:
		afirmar_teclado_correcto(dialogo)
	finally:
		dialogo.Destroy()


def test_preferencias_de_traduccion(app_wx, dialogo_modal):
	from app.ui.preferencias import TITULO_CLAVES_TRADUCCION, TITULO_TRADUCCION, DialogoPreferenciasGitHub

	ctx, _api, _a = crear_contexto()
	dialogo = DialogoPreferenciasGitHub(None, ctx, [])
	try:
		titulos = [dialogo.libro.GetPageText(i) for i in range(dialogo.libro.GetPageCount())]
		for titulo in (TITULO_TRADUCCION, TITULO_CLAVES_TRADUCCION):
			indice = titulos.index(titulo)
			dialogo.libro.SetSelection(indice)
			afirmar_teclado_correcto(dialogo.libro.GetPage(indice))
		motor = dialogo.control_de("traduccion.motor")
		motor.SetSelection([m for m, _n, _c in tr.MOTORES].index("deepl"))
		dialogo.control_de("traduccion.clave_deepl").SetValue("secreta:fx")
		ajustes = dialogo.ajustes_traduccion()
		assert ajustes.motor == "deepl" and ajustes.claves["deepl"] == "secreta:fx" and ajustes.respaldo is False
		with _con_sesion(SesionFalsa(Respuesta({"translations": [{"text": "Thanks for letting me know"}]}))):
			dialogo._al_probar_traduccion(None)
		assert dialogo_modal.ultimo.mensaje.startswith("DeepL funciona") and "Thanks for letting me know" in dialogo_modal.ultimo.mensaje
		assert dialogo.aplicar()
		assert ctx.config.obtener("traduccion.motor") == "deepl"
		assert ctx.secretos.obtener("traduccion.clave_deepl") == "secreta:fx", "la clave va a los secretos cifrados"
		assert "clave_deepl" not in str(ctx.config.obtener("traduccion")), "y no a la configuración"
	finally:
		dialogo.Destroy()


def test_formulario_de_issue_se_crea_traducido(app_wx, dialogo_modal):
	from tests.test_formulario_issue import _contexto, _formulario

	ctx, _api, _a = _contexto()
	enviados: list = []
	dialogo = _formulario(ctx, enviados)
	try:
		afirmar_teclado_correcto(dialogo)
		dialogo.campo_titulo.SetValue("[Fallo]: no abre")
		dialogo.controles["version"].SetValue("1.0.4")
		dialogo.controles["lector"].SetSelection(1)
		dialogo.controles["normas"][0].SetValue(True)
		dialogo.selector_traduccion.SetSelection(dialogo._codigos_traduccion.index("en"))
		dialogo_modal.responder(wx.ID_OK)

		def responder(_metodo, _url, opciones):
			texto = opciones["params"]["q"]
			return _google("[Bug]: does not open" if texto == "[Fallo]: no abre" else texto.replace("no abre", "does not open"))

		with _con_sesion(SesionFalsa(responder=responder)):
			dialogo.enviar()
		assert enviados and enviados[0]["titulo"] == "[Bug]: does not open"
		assert ctx.config.obtener("traduccion.destino_envio") == "en"
	finally:
		dialogo.Destroy()


def test_conversacion_traduce_con_control_t(app_wx, monkeypatch):
	from app.ui import traductor
	from app.ui.detalle import conversacion

	abiertos: list = []
	monkeypatch.setattr(traductor, "abrir_traductor", lambda ctx, padre, texto, titulo, traducir_ya=False: abiertos.append(
		(texto, titulo, traducir_ya)))
	elementos = [mock.Mock(tiene_texto=True, texto="Hola", autor="ana", tipo="descripción", fecha="hoy"),
		mock.Mock(tiene_texto=True, texto="Gracias", autor="luis", tipo="comentario", fecha="ayer")]
	panel = mock.Mock(elementos=elementos, issue={"title": "Falla"}, ctx=mock.Mock())
	panel._requiere.return_value = elementos[1]
	conversacion.PanelConversacion.traducir(panel)
	conversacion.PanelConversacion.traducir_conversacion(panel)
	assert abiertos[0] == ("Gracias", "luis, comentario", True)
	assert abiertos[1][0] == "### ana (descripción, hoy)\n\nHola\n\n### luis (comentario, ayer)\n\nGracias" and abiertos[1][1] == "Falla"
