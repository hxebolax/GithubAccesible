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
