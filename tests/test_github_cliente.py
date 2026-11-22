"""Pruebas del cliente de la API de GitHub, sin red (sesión falsa)."""

from __future__ import annotations

import io
import json
import time

import pytest
import requests

from app.services.github import ApiGitHub
from app.services.github.cliente import (
	ClienteGitHub,
	ErrorGraphQL,
	ErrorValidacion,
	LimiteAlcanzado,
	NoAutorizado,
	NoEncontrado,
	SinPermiso,
	aceptar_para_descarga,
	analizar_link,
	normalizar_host,
	numero_ultima_pagina,
	urls_api,
)


def respuesta(codigo=200, cuerpo=None, cabeceras=None, url="https://api.github.com/x"):
	r = requests.Response()
	r.status_code = codigo
	r._content = b"" if cuerpo is None else (cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode())
	r.headers.update(cabeceras or {})
	r.url = url
	r.encoding = "utf-8"
	return r


class SesionFalsa:
	"""Devuelve respuestas programadas y guarda las peticiones."""

	def __init__(self, respuestas):
		self.respuestas = list(respuestas)
		self.peticiones = []

	def request(self, metodo, url, **opciones):
		self.peticiones.append((metodo, url, opciones))
		siguiente = self.respuestas.pop(0)
		return siguiente(metodo, url, opciones) if callable(siguiente) else siguiente


def cliente_con(*respuestas, token="ghp_prueba1234"):
	sesion = SesionFalsa(respuestas)
	return ClienteGitHub(token, crear_sesion=lambda: sesion), sesion


def test_urls_de_cada_host():
	assert urls_api("github.com") == ("https://api.github.com", "https://api.github.com/graphql")
	assert urls_api("https://git.empresa.es/") == ("https://git.empresa.es/api/v3", "https://git.empresa.es/api/graphql")
	assert urls_api("miempresa.ghe.com")[0] == "https://api.miempresa.ghe.com"
	assert normalizar_host("") == "github.com"


def test_cabeceras_y_autenticacion():
	cliente, sesion = cliente_con(respuesta(200, {"login": "ana"}, {"X-OAuth-Scopes": "repo, gist"}))
	assert cliente.get("/user")["login"] == "ana"
	_metodo, url, opciones = sesion.peticiones[0]
	assert url == "https://api.github.com/user"
	assert opciones["headers"]["Authorization"] == "Bearer ghp_prueba1234"
	assert opciones["headers"]["X-GitHub-Api-Version"] == "2026-03-10"
	assert opciones["headers"]["Accept"] == "application/vnd.github+json"
	assert cliente.ambitos == ["repo", "gist"]


def test_enlaces_de_paginacion():
	cabecera = '<https://api.github.com/r?page=2>; rel="next", <https://api.github.com/r?page=7>; rel="last"'
	assert analizar_link(cabecera)["next"].endswith("page=2")
	assert numero_ultima_pagina(cabecera) == 7
	assert analizar_link(None) == {}


def test_paginar_sigue_las_paginas_y_respeta_el_maximo():
	enlace = {"Link": '<https://api.github.com/r?page=2>; rel="next"'}
	cliente, sesion = cliente_con(
		respuesta(200, [{"id": 1}, {"id": 2}], enlace),
		respuesta(200, [{"id": 3}]),
	)
	assert [e["id"] for e in cliente.paginar("/r")] == [1, 2, 3]
	assert sesion.peticiones[0][2]["params"]["per_page"] == 100
	cliente2, _s = cliente_con(respuesta(200, [{"id": 1}, {"id": 2}], enlace))
	assert [e["id"] for e in cliente2.paginar("/r", maximo=1)] == [1]


def test_pagina_de_busqueda_extrae_items_y_total():
	cliente, _s = cliente_con(respuesta(200, {"total_count": 42, "items": [{"id": 9}]}))
	pagina = cliente.pagina("/search/repositories", {"q": "wx"})
	assert pagina.total == 42 and pagina.elementos == [{"id": 9}] and not pagina.hay_mas


def test_etag_respuesta_304_devuelve_lo_guardado():
	cliente, sesion = cliente_con(
		respuesta(200, [{"id": 1}], {"ETag": '"abc"'}),
		respuesta(304),
	)
	assert cliente.get("/notifications") == [{"id": 1}]
	assert cliente.get("/notifications") == [{"id": 1}]
	assert sesion.peticiones[1][2]["headers"]["If-None-Match"] == '"abc"'


def test_escribir_vacia_la_cache_y_no_devuelve_datos_viejos():
	# Tras marcar una notificación como leída, la lista no debe salir de la caché.
	cliente, sesion = cliente_con(
		respuesta(200, [{"id": 1, "unread": True}], {"ETag": '"abc"'}),
		respuesta(205),
		respuesta(200, [], {"ETag": '"def"'}),
	)
	assert cliente.get("/notifications") == [{"id": 1, "unread": True}]
	cliente.patch("/notifications/threads/1")
	assert cliente.get("/notifications") == []
	assert "If-None-Match" not in sesion.peticiones[2][2]["headers"]


@pytest.mark.parametrize(("codigo", "clase"), [(401, NoAutorizado), (404, NoEncontrado), (422, ErrorValidacion), (403, SinPermiso)])
def test_errores_con_mensaje_en_espanol(codigo, clase):
	cliente, _s = cliente_con(respuesta(codigo, {"message": "x", "errors": [{"message": "el nombre ya existe"}]}))
	with pytest.raises(clase) as error:
		cliente.get("/repos/a/b")
	assert error.value.codigo_http == codigo
	assert error.value.mensaje_usuario  # siempre hay texto para la persona
	if codigo == 422:
		assert "el nombre ya existe" in error.value.mensaje_usuario


def test_limite_primario_agotado():
	reinicio = int(time.time()) + 600
	cliente, _s = cliente_con(respuesta(403, {"message": "API rate limit exceeded"},
		{"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reinicio), "X-RateLimit-Limit": "5000"}))
	with pytest.raises(LimiteAlcanzado) as error:
		cliente.get("/user")
	assert 500 < error.value.segundos_restantes <= 600
	assert "límite" in error.value.mensaje_usuario


def test_limite_secundario_con_retry_after():
	cliente, _s = cliente_con(respuesta(403, {"message": "You have exceeded a secondary rate limit"}, {"Retry-After": "30"}))
	with pytest.raises(LimiteAlcanzado) as error:
		cliente.get("/user")
	assert "30" in error.value.mensaje_usuario


def test_existe_no_lanza_con_404():
	cliente, _s = cliente_con(respuesta(204), respuesta(404, {"message": "Not Found"}))
	assert cliente.existe("/user/starred/a/b") is True
	assert cliente.existe("/user/starred/a/b") is False


def test_graphql_datos_y_errores():
	cliente, sesion = cliente_con(
		respuesta(200, {"data": {"viewer": {"login": "ana"}}}),
		respuesta(200, {"data": None, "errors": [{"message": "campo desconocido"}]}),
	)
	assert cliente.graphql("query { viewer { login } }")["viewer"]["login"] == "ana"
	assert sesion.peticiones[0][1] == "https://api.github.com/graphql"
	with pytest.raises(ErrorGraphQL, match="campo desconocido"):
		cliente.graphql("query { x }")


def test_fachada_construye_rutas_escapadas():
	cliente, sesion = cliente_con(respuesta(200, {"number": 5}), respuesta(201, {"id": 1}))
	api = ApiGitHub(cliente)
	assert api.issue("dueño/repo", 5)["number"] == 5
	assert sesion.peticiones[0][1] == "https://api.github.com/repos/due%C3%B1o/repo/issues/5"
	api.comentar("a/b", 5, "hola")
	metodo, url, opciones = sesion.peticiones[1]
	assert metodo == "POST" and url.endswith("/repos/a/b/issues/5/comments") and opciones["json"] == {"body": "hola"}


def test_ruta_repo_invalida():
	from app.services.github.api import ruta_repo

	with pytest.raises(ValueError):
		ruta_repo("sinbarra")


def test_sin_conexion_da_error_claro():
	def falla(metodo, url, opciones):
		raise requests.ConnectionError("sin red")

	cliente, _s = cliente_con(falla)
	from app.services.github.cliente import ErrorGitHub

	with pytest.raises(ErrorGitHub, match="conexión"):
		cliente.get("/user")


def test_limpiar_registro_de_actions():
	from app.services.github.api_extra import limpiar_registro

	texto = "2024-05-01T10:00:00.1234567Z \x1b[36;1m##[group]Run pytest\x1b[0m\n2024-05-01T10:00:01.0000000Z ##[error]falló"
	limpio = limpiar_registro(texto)
	assert limpio.splitlines() == ["▸ Run pytest", "ERROR: falló"]


def test_cifrado_de_secretos_de_actions():
	nacl = pytest.importorskip("nacl.public")
	import base64

	from app.services.github.api_extra import cifrar_secreto

	clave = nacl.PrivateKey.generate()
	cifrado = cifrar_secreto(base64.b64encode(bytes(clave.public_key)).decode(), "valor ñ")
	assert nacl.SealedBox(clave).decrypt(base64.b64decode(cifrado)).decode() == "valor ñ"


def test_enterprise_usa_la_version_compatible():
	sesion = SesionFalsa([respuesta(200, {})])
	cliente = ClienteGitHub("t", host="git.empresa.es", crear_sesion=lambda: sesion)
	cliente.get("/user")
	assert sesion.peticiones[0][2]["headers"]["X-GitHub-Api-Version"] == "2022-11-28"


def test_aviso_de_sso():
	cliente, _s = cliente_con(respuesta(403, {"message": "Resource protected by organization SAML enforcement"},
		{"X-GitHub-SSO": "required; url=https://github.com/orgs/x/sso?authorization_request=1"}))
	with pytest.raises(SinPermiso, match="SSO"):
		cliente.get("/orgs/x/repos")


def test_descarga_en_zip_pide_json_y_la_de_releases_octet_stream(tmp_path):
	"""Regresión: «zipball» con «Accept: application/octet-stream» da 415 en GitHub."""
	zip_ = "https://api.github.com/repos/ana/proyecto/zipball/main"
	asset = "https://api.github.com/repos/ana/proyecto/releases/assets/7"
	assert aceptar_para_descarga(zip_) == "application/vnd.github+json"
	assert aceptar_para_descarga("https://api.github.com/repos/ana/p/actions/artifacts/3/zip") == "application/vnd.github+json"
	assert aceptar_para_descarga(asset) == "application/octet-stream"
	respuestas = [respuesta(200, b"PK datos"), respuesta(200, b"binario")]
	for r in respuestas:
		r.raw = io.BytesIO(r._content)
	cliente, sesion = cliente_con(*respuestas)
	destino = cliente.descargar(zip_, tmp_path / "proyecto.zip")
	assert destino.read_bytes() == b"PK datos"
	assert sesion.peticiones[0][2]["headers"]["Accept"] == "application/vnd.github+json"
	cliente.descargar(asset, tmp_path / "programa.exe")
	assert sesion.peticiones[1][2]["headers"]["Accept"] == "application/octet-stream"
	assert not list(tmp_path.glob("*.parcial"))
