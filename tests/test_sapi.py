"""Pruebas de la voz SAPI 5 para los avisos en segundo plano (incidencia #5).

No hablan de verdad: el objeto COM se sustituye por uno simulado.
"""

from __future__ import annotations

import threading

import pytest

from app.ui.accesibilidad import sapi
from tests.apoyo_app import crear_contexto


class _Token:
	def __init__(self, nombre):
		self.nombre = nombre

	def GetDescription(self):  # noqa: N802 - API COM
		return self.nombre


class _Tokens:
	def __init__(self, nombres):
		self._tokens = [_Token(n) for n in nombres]
		self.Count = len(self._tokens)  # noqa: N815 - API COM

	def Item(self, indice):  # noqa: N802 - API COM
		return self._tokens[indice]


class _VozFalsa:
	def __init__(self):
		self.Voice = None  # noqa: N815 - API COM
		self.Rate = 0  # noqa: N815
		self.Volume = 100  # noqa: N815
		self.dichos = []
		self.listo = threading.Event()

	def GetVoices(self):  # noqa: N802
		return _Tokens(["Helena", "Zira"])

	def Speak(self, texto, banderas):  # noqa: N802
		self.dichos.append((texto, self.Voice.nombre if self.Voice else "", self.Rate, self.Volume))
		self.listo.set()


@pytest.fixture
def voz_falsa(monkeypatch):
	voz = _VozFalsa()
	sapi.detener()
	monkeypatch.setattr(sapi, "_disponible", None)
	monkeypatch.setattr(sapi, "_crear_voz", lambda: voz)
	yield voz
	sapi.detener()


def test_habla_con_la_voz_velocidad_y_volumen_elegidos(voz_falsa):
	assert sapi.hablar("Notificación nueva", "Zira", 15, 40)
	assert voz_falsa.listo.wait(5)
	assert voz_falsa.dichos == [("Notificación nueva", "Zira", 10, 40)], "la velocidad se limita a -10..10"
	assert sapi.voces() == ["Helena", "Zira"]
	assert not sapi.hablar("   "), "un texto vacío no se dice"


def test_sin_sapi_devuelve_false_para_usar_el_lector(monkeypatch):
	sapi.detener()
	monkeypatch.setattr(sapi, "_disponible", False)
	assert sapi.hablar("hola") is False


def test_los_avisos_en_segundo_plano_van_a_la_voz_elegida(monkeypatch):
	ctx, _api, anuncios = crear_contexto()
	dichos = []
	monkeypatch.setattr(sapi, "hablar", lambda texto, voz, velocidad, volumen: dichos.append((texto, voz, velocidad, volumen)) or True)
	ctx.avisar_en_segundo_plano("Primero")
	assert anuncios[-1] == "Primero" and not dichos, "de fábrica, el lector"
	ctx.config.establecer_varias({"notificaciones.lectura": "sapi5", "notificaciones.sapi_voz": "Helena",
		"notificaciones.sapi_velocidad": -3, "notificaciones.sapi_volumen": 70})
	ctx.avisar_en_segundo_plano("Segundo")
	assert dichos == [("Segundo", "Helena", -3, 70)] and anuncios[-1] == "Primero"
	# Si SAPI falla, el aviso no se pierde: lo dice el lector.
	monkeypatch.setattr(sapi, "hablar", lambda *a: False)
	ctx.avisar_en_segundo_plano("Tercero")
	assert anuncios[-1] == "Tercero"
