"""Pruebas del inicio de sesión (flujo de dispositivo, tokens) y del gestor de cuentas, sin red."""

from __future__ import annotations

import pytest

from app.services.github import autenticacion as auth
from tests.test_github_cliente import SesionFalsa, respuesta


class SesionPost:
	def __init__(self, cuerpos):
		self.cuerpos = list(cuerpos)
		self.envios = []

	def post(self, url, data=None, headers=None, timeout=None):
		self.envios.append((url, data))
		return respuesta(200, self.cuerpos.pop(0))


def test_flujo_de_dispositivo_completo():
	sesion = SesionPost([
		{"device_code": "D", "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device",
			"expires_in": 900, "interval": 5},
		{"error": "authorization_pending"},
		{"error": "slow_down", "interval": 10},
		{"access_token": "gho_token", "token_type": "bearer", "scope": "repo"},
	])
	flujo = auth.FlujoDispositivo("cliente123", ["repo"], sesion=sesion)
	flujo._dormir = lambda s: None
	codigo = flujo.pedir_codigo()
	assert codigo.codigo_usuario == "ABCD-1234"
	assert codigo.codigo_deletreado == "A B C D 1 2 3 4"
	codigo.intervalo = 0
	assert flujo.esperar_token(codigo) == "gho_token"
	assert codigo.intervalo == 10, "slow_down aumenta el intervalo"
	url, datos = sesion.envios[0]
	assert url == "https://github.com/login/device/code" and datos["scope"] == "repo"
	assert sesion.envios[1][1]["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"


def test_flujo_de_dispositivo_errores_en_espanol():
	sesion = SesionPost([{"error": "access_denied"}])
	flujo = auth.FlujoDispositivo("c", sesion=sesion)
	codigo = auth.CodigoDispositivo("D", "X", "u", 900, 0)
	with pytest.raises(auth.ErrorAutenticacion, match="cancelado la autorización"):
		flujo.comprobar_una_vez(codigo)


def test_flujo_sin_id_de_cliente_lo_explica():
	with pytest.raises(auth.ErrorAutenticacion, match="identificador"):
		auth.FlujoDispositivo("", sesion=SesionPost([])).pedir_codigo()


def test_flujo_con_id_de_cliente_inexistente_lo_explica():
	class Sesion404(SesionPost):
		def post(self, url, data=None, headers=None, timeout=None):
			return respuesta(404, {"error": "Not Found"})

	with pytest.raises(auth.ErrorAutenticacion, match="no es válido"):
		auth.FlujoDispositivo("malo", sesion=Sesion404([])).pedir_codigo()


def test_flujo_device_flow_desactivado_lo_explica():
	flujo = auth.FlujoDispositivo("c", sesion=SesionPost([{"error": "device_flow_disabled"}]))
	with pytest.raises(auth.ErrorAutenticacion, match="Enable Device Flow"):
		flujo.pedir_codigo()


def test_flujo_cancelado():
	flujo = auth.FlujoDispositivo("c", sesion=SesionPost([]))
	codigo = auth.CodigoDispositivo("D", "X", "u", 900, 5)
	with pytest.raises(auth.ErrorAutenticacion, match="cancelado"):
		flujo.esperar_token(codigo, cancelado=lambda: True)


def test_validar_token():
	sesion = SesionFalsa([respuesta(200, {"login": "ana", "id": 7, "name": "Ana"}, {"X-OAuth-Scopes": "repo"})])

	def crear(**opciones):
		from app.services.github.cliente import ClienteGitHub

		return ClienteGitHub(crear_sesion=lambda: sesion, **opciones)

	cuenta = auth.validar_token("ghp_abcdef", crear_cliente=crear)
	assert cuenta.usuario == "ana" and cuenta.ambitos == ["repo"] and cuenta.tipo_token == "token clásico"
	assert cuenta.clave == "github.com:ana"


def test_validar_token_rechazado():
	sesion = SesionFalsa([respuesta(401, {"message": "Bad credentials"})])

	def crear(**opciones):
		from app.services.github.cliente import ClienteGitHub

		return ClienteGitHub(crear_sesion=lambda: sesion, **opciones)

	with pytest.raises(auth.ErrorAutenticacion, match="no acepta"):
		auth.validar_token("ghp_malo", crear_cliente=crear)


class ConfigFalsa:
	def __init__(self):
		self.datos = {}

	def obtener(self, clave, por_defecto=None):
		return self.datos.get(clave, por_defecto)

	def establecer(self, clave, valor, **_):
		self.datos[clave] = valor


class SecretosFalsos(dict):
	def obtener(self, nombre, por_defecto=None):
		return self.get(nombre, por_defecto)

	def guardar(self, nombre, valor):
		self[nombre] = valor

	def borrar(self, nombre):
		self.pop(nombre, None)


def test_gestor_de_cuentas_guarda_el_token_aparte():
	config, secretos = ConfigFalsa(), SecretosFalsos()
	gestor = auth.GestorCuentas(config, secretos)
	avisos = []
	gestor.suscribir(avisos.append)
	ana = auth.Cuenta("ana")
	gestor.anadir(ana, "ghp_secreto")
	luis = auth.Cuenta("luis", host="git.empresa.es")
	gestor.anadir(luis, "ghp_otro", activar=False)
	assert [c.usuario for c in gestor.cuentas()] == ["ana", "luis"]
	assert "ghp_secreto" not in str(config.datos), "el token no va a la configuración"
	assert gestor.token(ana) == "ghp_secreto"
	assert gestor.activa().usuario == "ana"
	assert gestor.cliente().base_rest == "https://api.github.com"
	assert gestor.cliente(luis).base_rest == "https://git.empresa.es/api/v3"
	gestor.activar(luis)
	assert gestor.activa().usuario == "luis"
	gestor.eliminar(luis)
	assert gestor.activa().usuario == "ana" and "token:git.empresa.es:luis" not in secretos
	assert len(avisos) == 4


def test_cliente_anonimo_sin_cuentas():
	gestor = auth.GestorCuentas(ConfigFalsa(), SecretosFalsos())
	assert gestor.activa() is None and not gestor.cliente().autenticado


# ── Tokens que caducan (aplicación OAuth con «Expire user access tokens») ──


def test_flujo_guarda_la_renovacion_si_el_token_caduca():
	sesion = SesionPost([{"access_token": "ghu_a", "refresh_token": "ghr_a", "expires_in": 28800,
		"refresh_token_expires_in": 15897600}])
	flujo = auth.FlujoDispositivo("cliente", sesion=sesion)
	token, estado = flujo.comprobar_una_vez(auth.CodigoDispositivo("D", "X", "u", 900, 0))
	assert (token, estado) == ("ghu_a", "ok")
	assert flujo.renovacion["refresh_token"] == "ghr_a" and flujo.renovacion["id_cliente"] == "cliente"


def test_flujo_sin_caducidad_no_guarda_renovacion():
	flujo = auth.FlujoDispositivo("c", sesion=SesionPost([{"access_token": "gho_a"}]))
	flujo.comprobar_una_vez(auth.CodigoDispositivo("D", "X", "u", 900, 0))
	assert flujo.renovacion is None


def test_renovar_no_envia_secreto_de_cliente():
	sesion = SesionPost([{"access_token": "ghu_b", "refresh_token": "ghr_b", "expires_in": 28800}])
	token, datos = auth.FlujoDispositivo("cliente", sesion=sesion).renovar("ghr_a")
	assert token == "ghu_b" and datos["refresh_token"] == "ghr_b"
	url, enviado = sesion.envios[0]
	assert url == "https://github.com/login/oauth/access_token"
	assert enviado == {"client_id": "cliente", "grant_type": "refresh_token", "refresh_token": "ghr_a"}


def _gestor_con_token_que_caduca(monkeypatch, caduca_en=28800):
	import json
	import time

	config, secretos = ConfigFalsa(), SecretosFalsos()
	gestor = auth.GestorCuentas(config, secretos)
	ana = auth.Cuenta("ana", metodo=auth.METODO_DISPOSITIVO)
	gestor.anadir(ana, "ghu_viejo")
	gestor.guardar_renovacion(ana, {"refresh_token": "ghr_viejo", "caduca": time.time() + caduca_en, "id_cliente": "c"})
	llamadas = []

	def renovar(self, token_renovacion):
		llamadas.append(token_renovacion)
		return "ghu_nuevo", {"refresh_token": "ghr_nuevo", "caduca": time.time() + 28800, "id_cliente": "c"}

	monkeypatch.setattr(auth.FlujoDispositivo, "renovar", renovar)
	return gestor, secretos, ana, llamadas, json


def test_gestor_renueva_y_guarda_los_dos_tokens(monkeypatch):
	gestor, secretos, ana, llamadas, json = _gestor_con_token_que_caduca(monkeypatch)
	cliente = gestor.cliente(ana)
	assert gestor.renovar(ana, "ghu_viejo") == "ghu_nuevo"
	assert secretos[ana.nombre_secreto] == "ghu_nuevo"
	assert json.loads(secretos[f"{ana.nombre_secreto}:renovacion"])["refresh_token"] == "ghr_nuevo"
	assert cliente.token == "ghu_nuevo", "el cliente ya abierto pasa a usar el token nuevo"
	# Otro hilo que tenía el token viejo no gasta otra vez el de renovación.
	assert gestor.renovar(ana, "ghu_viejo") == "ghu_nuevo"
	assert llamadas == ["ghr_viejo"]
	gestor.eliminar(ana)
	assert not secretos, "al quitar la cuenta no queda ni el token ni su renovación"


def test_token_a_punto_de_caducar_se_renueva_antes_de_usarlo(monkeypatch):
	gestor, _s, ana, llamadas, _j = _gestor_con_token_que_caduca(monkeypatch, caduca_en=10)
	assert gestor.token(ana) == "ghu_nuevo"
	assert llamadas == ["ghr_viejo"]


def test_sin_renovacion_el_token_se_usa_tal_cual(monkeypatch):
	gestor, _s, ana, llamadas, _j = _gestor_con_token_que_caduca(monkeypatch)
	gestor.guardar_renovacion(ana, None)
	assert gestor.token(ana) == "ghu_viejo" and gestor.renovar(ana, "ghu_viejo") is None
	assert llamadas == []


def test_cliente_renueva_ante_un_401_y_repite_la_peticion():
	from tests.test_github_cliente import SesionFalsa

	sesion = SesionFalsa([respuesta(401, {"message": "Bad credentials"}), respuesta(200, {"login": "ana"})])
	renovaciones = []

	def renovar(rechazado):
		renovaciones.append(rechazado)
		return "ghu_nuevo"

	from app.services.github.cliente import ClienteGitHub

	cliente = ClienteGitHub("ghu_viejo", crear_sesion=lambda: sesion, renovar=renovar)
	assert cliente.get("/user") == {"login": "ana"}
	assert renovaciones == ["ghu_viejo"]
	assert sesion.peticiones[1][2]["headers"]["Authorization"] == "Bearer ghu_nuevo"


def test_cliente_sin_poder_renovar_avisa_de_volver_a_entrar():
	from app.services.github.cliente import ClienteGitHub, NoAutorizado
	from tests.test_github_cliente import SesionFalsa

	sesion = SesionFalsa([respuesta(401, {"message": "Bad credentials"})])
	cliente = ClienteGitHub("ghu_viejo", crear_sesion=lambda: sesion, renovar=lambda _r: None)
	with pytest.raises(NoAutorizado, match="Vuelva a iniciar sesión"):
		cliente.get("/user")
