"""Sonidos de la interfaz: eventos, paquetes, volumen y generación de los de fábrica (sin wx).

Diseño (inspirado en el de SocialRSS, sin dependencias nativas):

- Cada **evento** («notificación nueva», «línea añadida»...) tiene un archivo
  WAV en ``data/sounds/<paquete>/<evento>.wav``. Si el paquete elegido no
  tiene ese archivo, se usa el del paquete ``predeterminado``.
- Los de fábrica se **generan** con el módulo ``wave`` (tonos y barridos cortos
  y distinguibles), así no hay que distribuir audio con licencia ajena.
- Se reproduce con ``winsound`` (biblioteca estándar de Windows) en **un único
  hilo** con cola: la interfaz nunca espera, y el volumen se aplica escalando
  las muestras en memoria (``winsound`` no tiene control de volumen).
- Las preferencias se leen **en cada sonido** (activados, silencio, volumen,
  eventos desactivados): un cambio en Preferencias se oye al momento.
"""

from __future__ import annotations

import array
import builtins
import io
import logging
import math
import queue
import sys
import threading
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PAQUETE_PREDETERMINADO = "predeterminado"
FRECUENCIA = 44100


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	return texto


# Evento → (descripción para Preferencias, receta del sonido de fábrica).
# Receta: lista de (frecuencia inicial, frecuencia final, milisegundos, forma).
EVENTOS: dict[str, tuple[str, list[tuple[float, float, int, str]]]] = {
	"inicio": (N_("Inicio de la aplicación"), [(523, 523, 70, "s"), (659, 659, 70, "s"), (784, 784, 110, "s")]),
	"listo": (N_("Lista cargada"), [(880, 1100, 60, "s")]),
	"vacio": (N_("Lista vacía o sin resultados"), [(330, 260, 120, "s")]),
	"error": (N_("Error"), [(220, 180, 180, "c"), (180, 150, 160, "c")]),
	"aviso": (N_("Aviso"), [(600, 600, 90, "t"), (600, 600, 90, "t")]),
	"notificacion": (N_("Notificación nueva de GitHub"), [(784, 784, 80, "s"), (1046, 1046, 120, "s")]),
	"mencion": (N_("Le mencionan o le piden revisión"), [(1046, 784, 90, "s"), (1046, 1318, 140, "s")]),
	"enviado": (N_("Comentario, issue o cambio enviado"), [(500, 1000, 110, "s")]),
	"completado": (N_("Tarea en segundo plano terminada"), [(660, 660, 60, "s"), (990, 990, 90, "s")]),
	"accion_exito": (N_("Flujo de Actions terminado con éxito"), [(523, 659, 80, "s"), (659, 1046, 130, "s")]),
	"accion_fallo": (N_("Flujo de Actions fallido"), [(440, 330, 150, "t"), (330, 220, 200, "t")]),
	"linea_anadida": (N_("Diferencias: línea añadida"), [(1200, 1200, 35, "s")]),
	"linea_eliminada": (N_("Diferencias: línea eliminada"), [(400, 400, 35, "t")]),
	"bloque": (N_("Diferencias: cambio de bloque o de archivo"), [(700, 900, 45, "s")]),
	"fusionado": (N_("Pull request fusionado"), [(392, 392, 70, "s"), (523, 523, 70, "s"), (659, 659, 70, "s"), (1046, 1046, 160, "s")]),
	"conflicto": (N_("Conflicto de git"), [(300, 300, 100, "c"), (250, 250, 100, "c"), (300, 300, 120, "c")]),
	"descargado": (N_("Descarga terminada"), [(800, 1200, 120, "s")]),
	"estrella": (N_("Estrella puesta o quitada"), [(1318, 1568, 80, "s")]),
	"abrir": (N_("Abrir ventana o detalle"), [(600, 750, 40, "s")]),
	"cerrar": (N_("Cerrar ventana o detalle"), [(750, 600, 40, "s")]),
	"pagina": (N_("Más resultados cargados"), [(900, 900, 30, "s"), (1100, 1100, 30, "s")]),
	"copiado": (N_("Copiado al portapapeles"), [(1500, 1500, 30, "s")]),
}


# ════════════════════════════════════════════════════════════════════════════
# Generación de los sonidos de fábrica
# ════════════════════════════════════════════════════════════════════════════


def _muestra(forma: str, fase: float) -> float:
	if forma == "t":  # triangular: más suave que la cuadrada, distinta del seno
		return 2 * abs(2 * (fase / (2 * math.pi) % 1) - 1) - 1
	if forma == "c":  # cuadrada atenuada: «áspera», para errores
		return 0.6 if math.sin(fase) >= 0 else -0.6
	return math.sin(fase)


def generar_wav(receta: list[tuple[float, float, int, str]], volumen: float = 0.5) -> bytes:
	"""WAV mono de 16 bits a 44,1 kHz a partir de una receta de tonos."""
	muestras = array.array("h")
	for inicio, fin, milisegundos, forma in receta:
		total = max(1, int(FRECUENCIA * milisegundos / 1000))
		fase = 0.0
		ataque = max(1, int(total * 0.08))
		caida = max(1, int(total * 0.25))
		for i in range(total):
			frecuencia = inicio + (fin - inicio) * i / total
			fase += 2 * math.pi * frecuencia / FRECUENCIA
			envolvente = min(1.0, i / ataque, (total - i) / caida)
			muestras.append(int(32767 * volumen * envolvente * _muestra(forma, fase)))
		muestras.extend([0] * int(FRECUENCIA * 0.012))
	if sys.byteorder != "little":
		muestras.byteswap()
	salida = io.BytesIO()
	with wave.open(salida, "wb") as archivo:
		archivo.setnchannels(1)
		archivo.setsampwidth(2)
		archivo.setframerate(FRECUENCIA)
		archivo.writeframes(muestras.tobytes())
	return salida.getvalue()


def generar_paquete(carpeta: Path, sobrescribir: bool = False) -> list[Path]:
	"""Escribe los WAV de fábrica en ``carpeta`` (los que falten). Devuelve los creados."""
	carpeta.mkdir(parents=True, exist_ok=True)
	creados = []
	for evento, (_descripcion, receta) in EVENTOS.items():
		ruta = carpeta / f"{evento}.wav"
		if ruta.exists() and not sobrescribir:
			continue
		ruta.write_bytes(generar_wav(receta))
		creados.append(ruta)
	return creados


def escalar_volumen(datos_wav: bytes, volumen: float) -> bytes:
	"""Devuelve el WAV con las muestras multiplicadas por ``volumen`` (0 a 1). Solo PCM de 16 bits."""
	volumen = max(0.0, min(1.0, float(volumen)))
	if volumen >= 0.999:
		return datos_wav
	with wave.open(io.BytesIO(datos_wav), "rb") as entrada:
		parametros = entrada.getparams()
		marcos = entrada.readframes(parametros.nframes)
	if parametros.sampwidth != 2:
		return datos_wav
	muestras = array.array("h")
	muestras.frombytes(marcos)
	if sys.byteorder != "little":
		muestras.byteswap()
	for i in range(len(muestras)):
		muestras[i] = int(muestras[i] * volumen)
	if sys.byteorder != "little":
		muestras.byteswap()
	salida = io.BytesIO()
	with wave.open(salida, "wb") as archivo:
		archivo.setparams(parametros)
		archivo.writeframes(muestras.tobytes())
	return salida.getvalue()


# ════════════════════════════════════════════════════════════════════════════
# Reproductor
# ════════════════════════════════════════════════════════════════════════════


def _reproducir_winsound(datos: bytes) -> None:
	import winsound

	# SND_MEMORY no admite SND_ASYNC: se reproduce de forma síncrona, pero en el
	# hilo de sonidos, así que la interfaz nunca espera.
	winsound.PlaySound(datos, winsound.SND_MEMORY | winsound.SND_NODEFAULT)


class Sonidos:
	"""Reproductor de sonidos de eventos.

	:param carpeta: carpeta ``data/sounds``.
	:param preferencias: función que devuelve ``(activados, silencio, volumen,
		paquete, eventos_desactivados)``; se llama en cada sonido.
	:param reproducir: función que reproduce un WAV en memoria (sustituible en pruebas).
	"""

	def __init__(
		self,
		carpeta: Path,
		preferencias: Callable[[], tuple[bool, bool, float, str, list[str]]],
		reproducir: Callable[[bytes], None] | None = None,
	) -> None:
		self.carpeta = Path(carpeta)
		self._preferencias = preferencias
		self._reproducir = reproducir or (_reproducir_winsound if sys.platform == "win32" else (lambda datos: None))
		self._cola: queue.Queue[tuple[str, Path | None] | None] = queue.Queue(maxsize=16)
		self._hilo: threading.Thread | None = None
		self._candado = threading.Lock()
		self._cache: dict[tuple[Path, float], bytes] = {}

	def preparar(self) -> None:
		"""Genera el paquete de fábrica si falta algún archivo."""
		try:
			generar_paquete(self.carpeta / PAQUETE_PREDETERMINADO)
		except OSError:
			log.warning("No se pudieron generar los sonidos de fábrica en %s", self.carpeta, exc_info=True)

	def paquetes(self) -> list[str]:
		if not self.carpeta.is_dir():
			return [PAQUETE_PREDETERMINADO]
		nombres = sorted(p.name for p in self.carpeta.iterdir() if p.is_dir())
		if PAQUETE_PREDETERMINADO in nombres:
			nombres.remove(PAQUETE_PREDETERMINADO)
		return [PAQUETE_PREDETERMINADO, *nombres]

	def ruta(self, evento: str, paquete: str) -> Path | None:
		for carpeta in (self.carpeta / paquete, self.carpeta / PAQUETE_PREDETERMINADO):
			for extension in (".wav", ".WAV"):
				candidato = carpeta / f"{evento}{extension}"
				if candidato.is_file():
					return candidato
		return None

	def reproducir(self, evento: str, forzar: bool = False) -> bool:
		"""Encola el sonido del evento si las preferencias lo permiten. Nunca bloquea."""
		try:
			activados, silencio, _volumen, paquete, desactivados = self._preferencias()
		except Exception:  # noqa: BLE001 - sin preferencias no se suena
			log.debug("No se pudieron leer las preferencias de sonido", exc_info=True)
			return False
		if not forzar and (not activados or silencio or evento in (desactivados or [])):
			return False
		ruta = self.ruta(evento, paquete)
		if ruta is None:
			log.debug("Sin archivo de sonido para el evento %s", evento)
			return False
		self._asegurar_hilo()
		try:
			# Si la cola está llena (muchos sonidos seguidos), se descarta el nuevo:
			# mejor perder un sonido que acumular retraso.
			self._cola.put_nowait((evento, ruta))
		except queue.Full:
			log.debug("Cola de sonidos llena; se descarta %s", evento)
			return False
		return True

	def probar(self, evento: str) -> bool:
		return self.reproducir(evento, forzar=True)

	def _datos(self, ruta: Path, volumen: float) -> bytes:
		clave = (ruta, round(volumen, 2))
		datos = self._cache.get(clave)
		if datos is None:
			datos = escalar_volumen(ruta.read_bytes(), volumen)
			if len(self._cache) > 128:
				self._cache.clear()
			self._cache[clave] = datos
		return datos

	def _asegurar_hilo(self) -> None:
		with self._candado:
			if self._hilo is None or not self._hilo.is_alive():
				self._hilo = threading.Thread(target=self._trabajar, name="Sonidos", daemon=True)
				self._hilo.start()

	def _trabajar(self) -> None:
		while True:
			elemento = self._cola.get()
			if elemento is None:
				return
			_evento, ruta = elemento
			try:
				_activados, _silencio, volumen, _paquete, _desactivados = self._preferencias()
				if ruta is not None and volumen > 0:
					self._reproducir(self._datos(ruta, volumen))
			except Exception:  # noqa: BLE001 - un WAV dañado no debe tumbar el hilo
				log.warning("No se pudo reproducir %s", ruta, exc_info=True)

	def detener(self) -> None:
		if self._hilo and self._hilo.is_alive():
			try:
				self._cola.put_nowait(None)
			except queue.Full:
				log.debug("Cola llena al detener los sonidos")


_instancia: Sonidos | None = None


def establecer(sonidos: Sonidos | None) -> None:
	global _instancia
	_instancia = sonidos


def sonar(evento: str) -> None:
	"""Atajo global: reproduce un evento si hay reproductor configurado."""
	if _instancia is not None:
		_instancia.reproducir(evento)


def descripcion(evento: str) -> str:
	return _(EVENTOS.get(evento, (evento, []))[0])


def preferencias_desde_config(config: Any) -> Callable[[], tuple[bool, bool, float, str, list[str]]]:
	def leer() -> tuple[bool, bool, float, str, list[str]]:
		return (
			bool(config.obtener("sonidos.activados")),
			bool(config.obtener("sonidos.silencio")),
			float(config.obtener("sonidos.volumen")) / 100.0,
			str(config.obtener("sonidos.paquete")),
			list(config.obtener("sonidos.desactivados") or []),
		)

	return leer
