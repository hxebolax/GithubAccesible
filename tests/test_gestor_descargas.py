"""Gestor de descargas: varias a la vez, pausa, reanudación, cancelación, errores y persistencia.

Descargas de verdad contra el servidor local de servidor_http_prueba.py (nunca Internet).
"""

from __future__ import annotations

import hashlib
import json
import time

import pytest

from app.core.red import ConfiguracionRed, crear_sesion
from app.services import gestor_descargas as gd
from tests.servidor_http_prueba import CONTENIDO, servidor  # noqa: F401 - fixture

SHA = hashlib.sha256(CONTENIDO).hexdigest()


def _sesion_para(cuenta: str, aceptar: str):
	return crear_sesion(ConfiguracionRed(proxy="ninguno", reintentos=0, tiempo_lectura=5))


def _esperar(condicion, segundos: float = 15.0) -> None:
	limite = time.monotonic() + segundos
	while time.monotonic() < limite:
		if condicion():
			return
		time.sleep(0.02)
	raise AssertionError("No se cumplió la condición a tiempo")


@pytest.fixture
def gestor(tmp_path):
	gestor = gd.GestorDescargas(tmp_path / "config", _sesion_para, simultaneas=lambda: 3)
	yield gestor
	gestor.detener(espera=2)


def test_descarga_completa_verificada_y_guardada(servidor, gestor, tmp_path):
	eventos = []
	gestor.suscribir(lambda evento, d: eventos.append((evento, d.estado)))
	d = gestor.anadir(servidor.url("/archivo.bin?id=g1"), tmp_path / "bajadas" / "archivo.bin", sha256=SHA, origen="Release 1.0")
	_esperar(lambda: d.estado == gd.COMPLETADA)
	assert (tmp_path / "bajadas" / "archivo.bin").read_bytes() == CONTENIDO
	assert d.porcentaje == 100 and d.hecho == d.total == len(CONTENIDO) and d.ruta_final.endswith("archivo.bin")
	assert ("anadida", gd.PENDIENTE) in eventos and ("estado", gd.COMPLETADA) in eventos
	guardado = json.loads((tmp_path / "config" / gd.ARCHIVO).read_text(encoding="utf-8"))
	assert guardado["descargas"][0]["estado"] == gd.COMPLETADA and guardado["descargas"][0]["origen"] == "Release 1.0"


def test_pausar_y_reanudar_sigue_donde_se_quedo(servidor, gestor, tmp_path):
	d = gestor.anadir(servidor.url("/goteo-rangos.bin?id=g2"), tmp_path / "goteo.bin")
	_esperar(lambda: d.hecho > 50_000)
	assert gestor.pausar(d.id)
	_esperar(lambda: d.estado == gd.PAUSADA)
	bajado = d.ruta_parcial().stat().st_size
	assert bajado > 0 and not (tmp_path / "goteo.bin").exists()
	assert gestor.reanudar(d.id)
	_esperar(lambda: d.estado == gd.COMPLETADA, 30)
	assert (tmp_path / "goteo.bin").read_bytes() == CONTENIDO
	rangos = [c.get("Range") for c in servidor.cabeceras_de("/goteo-rangos.bin?id=g2")]
	assert rangos[0] is None and rangos[-1] == f"bytes={bajado}-", "la segunda petición pide solo lo que faltaba"


def test_cancelar_borra_lo_bajado_y_se_puede_volver_a_descargar(servidor, gestor, tmp_path):
	d = gestor.anadir(servidor.url("/goteo-rangos.bin?id=g3"), tmp_path / "goteo.bin")
	_esperar(lambda: d.hecho > 20_000)
	assert gestor.cancelar(d.id)
	_esperar(lambda: d.estado == gd.CANCELADA)
	assert not d.ruta_parcial().exists() and d.hecho == 0
	assert gestor.reanudar(d.id), "una cancelada se puede volver a descargar"
	_esperar(lambda: d.estado == gd.COMPLETADA, 30)


def test_error_con_explicacion_y_reintento(servidor, gestor, tmp_path):
	d = gestor.anadir(servidor.url("/404?id=g4"), tmp_path / "nada.bin")
	_esperar(lambda: d.estado == gd.ERROR)
	assert d.error, "el error se explica en la lista"
	assert gestor.reanudar(d.id)
	_esperar(lambda: d.estado == gd.ERROR)
	assert servidor.veces("/404?id=g4") == 2


def test_cola_con_limite_de_simultaneas(servidor, tmp_path):
	gestor = gd.GestorDescargas(tmp_path / "config", _sesion_para, simultaneas=lambda: 1)
	try:
		primera = gestor.anadir(servidor.url("/goteo-rangos.bin?id=g5"), tmp_path / "uno.bin")
		segunda = gestor.anadir(servidor.url("/archivo.bin?id=g5b"), tmp_path / "dos.bin")
		assert primera.estado == gd.DESCARGANDO and segunda.estado == gd.PENDIENTE
		_esperar(lambda: segunda.estado == gd.COMPLETADA, 30)
		assert primera.estado == gd.COMPLETADA, "la segunda empieza al terminar la primera"
		assert gestor.anadir(servidor.url("/archivo.bin?id=g5b"), tmp_path / "dos.bin") is not segunda, \
			"una ya completada se puede pedir de nuevo"
	finally:
		gestor.detener(espera=2)


def test_al_cerrar_se_pausan_y_siguen_al_abrir(servidor, tmp_path):
	primera = gd.GestorDescargas(tmp_path / "config", _sesion_para)
	d = primera.anadir(servidor.url("/goteo-rangos.bin?id=g6"), tmp_path / "goteo.bin")
	_esperar(lambda: d.hecho > 20_000)
	primera.detener(espera=5)
	guardada = json.loads((tmp_path / "config" / gd.ARCHIVO).read_text(encoding="utf-8"))["descargas"][0]
	assert guardada["estado"] == gd.PAUSADA and guardada["interrumpida"]

	sin_reanudar = gd.GestorDescargas(tmp_path / "config", _sesion_para)
	sin_reanudar.cargar(reanudar_interrumpidas=False)
	assert sin_reanudar.descargas()[0].estado == gd.PAUSADA
	sin_reanudar.detener(espera=1)

	segunda = gd.GestorDescargas(tmp_path / "config", _sesion_para)
	try:
		segunda.cargar(reanudar_interrumpidas=True)
		recuperada = segunda.descargas()[0]
		_esperar(lambda: recuperada.estado == gd.COMPLETADA, 30)
		assert (tmp_path / "goteo.bin").read_bytes() == CONTENIDO
	finally:
		segunda.detener(espera=2)


def test_quitar_y_quitar_terminadas(servidor, gestor, tmp_path):
	hecha = gestor.anadir(servidor.url("/archivo.bin?id=g7"), tmp_path / "a.bin")
	_esperar(lambda: hecha.estado == gd.COMPLETADA)
	lenta = gestor.anadir(servidor.url("/goteo-rangos.bin?id=g7b"), tmp_path / "b.bin")
	_esperar(lambda: lenta.hecho > 10_000)
	assert gestor.quitar_terminadas() == 1 and [d.id for d in gestor.descargas()] == [lenta.id]
	assert (tmp_path / "a.bin").exists(), "quitar de la lista no borra el archivo"
	assert gestor.quitar(lenta.id) and not gestor.descargas()
	assert not lenta.ruta_parcial().exists(), "quitar una a medias la cancela y borra lo bajado"
