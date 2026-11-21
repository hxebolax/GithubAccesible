"""Pruebas de los sonidos: generación de fábrica, volumen, paquetes y preferencias."""

from __future__ import annotations

import io
import time
import wave

from app.services import sonidos as s


def test_generar_paquete_completo(tmp_path):
	creados = s.generar_paquete(tmp_path / "predeterminado")
	assert len(creados) == len(s.EVENTOS)
	with wave.open(str(tmp_path / "predeterminado" / "error.wav")) as archivo:
		assert archivo.getnchannels() == 1 and archivo.getsampwidth() == 2 and archivo.getframerate() == 44100
	assert s.generar_paquete(tmp_path / "predeterminado") == [], "no se sobrescribe lo que ya existe"


def test_escalar_volumen_reduce_las_muestras():
	original = s.generar_wav([(440, 440, 50, "s")], volumen=0.8)
	mitad = s.escalar_volumen(original, 0.5)
	with wave.open(io.BytesIO(original)) as a, wave.open(io.BytesIO(mitad)) as b:
		marcos_a, marcos_b = a.readframes(a.getnframes()), b.readframes(b.getnframes())
	assert len(marcos_a) == len(marcos_b)
	pico = lambda datos: max(abs(int.from_bytes(datos[i:i + 2], "little", signed=True)) for i in range(0, len(datos), 2))  # noqa: E731
	assert abs(pico(marcos_b) - pico(marcos_a) / 2) < 50


def _reproductor(tmp_path, activados=True, silencio=False, volumen=1.0, desactivados=()):
	tocados = []
	sonidos = s.Sonidos(tmp_path / "sounds", lambda: (activados, silencio, volumen, "propio", list(desactivados)), reproducir=tocados.append)
	sonidos.preparar()
	return sonidos, tocados


def test_respeta_las_preferencias(tmp_path):
	sonidos, tocados = _reproductor(tmp_path, desactivados=["error"])
	assert sonidos.reproducir("listo")
	assert not sonidos.reproducir("error"), "evento desactivado"
	assert sonidos.probar("error"), "probar suena aunque esté desactivado"
	limite = time.monotonic() + 3
	while len(tocados) < 2 and time.monotonic() < limite:
		time.sleep(0.05)
	assert len(tocados) == 2
	silenciado, _t = _reproductor(tmp_path, silencio=True)
	assert not silenciado.reproducir("listo")


def test_paquete_propio_con_respaldo(tmp_path):
	sonidos, _t = _reproductor(tmp_path)
	(tmp_path / "sounds" / "propio").mkdir()
	(tmp_path / "sounds" / "propio" / "listo.wav").write_bytes(s.generar_wav([(300, 300, 20, "s")]))
	assert sonidos.ruta("listo", "propio").parent.name == "propio"
	assert sonidos.ruta("error", "propio").parent.name == s.PAQUETE_PREDETERMINADO
	assert sonidos.paquetes() == [s.PAQUETE_PREDETERMINADO, "propio"]
