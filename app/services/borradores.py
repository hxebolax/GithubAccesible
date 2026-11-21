"""Borradores del editor y notificaciones ya avisadas, en SQLite (``data/db/app.db``).

Por qué: lo escrito en un comentario, una issue o una revisión no debe perderse
nunca, ni si falla la red, ni si se cierra el editor por error, ni si se cierra
la aplicación. El editor guarda el texto al cerrarse sin enviar y lo ofrece al
volver a abrirlo para lo mismo. Las notificaciones avisadas se recuerdan entre
sesiones para no volver a anunciar al arrancar lo que ya se anunció.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from app.core.base_datos import BaseDatos

log = logging.getLogger(__name__)

MAXIMO_AVISADAS = 2000


class Almacen:
	"""Acceso a borradores y avisos. Seguro entre hilos (lo garantiza ``BaseDatos``)."""

	def __init__(self, ruta: Path | str | None = None) -> None:
		from app.core.migraciones import MIGRACIONES

		self.bd = BaseDatos(ruta, MIGRACIONES)

	# ── Borradores ────────────────────────────────────────────────────────────

	def guardar_borrador(self, clave: str, titulo: str, cuerpo: str) -> None:
		if not (titulo.strip() or cuerpo.strip()):
			self.borrar_borrador(clave)
			return
		self.bd.ejecutar(
			"INSERT INTO borradores (clave, titulo, cuerpo, actualizado_en) VALUES (?, ?, ?, ?) "
			"ON CONFLICT(clave) DO UPDATE SET titulo = excluded.titulo, cuerpo = excluded.cuerpo, actualizado_en = excluded.actualizado_en",
			(clave, titulo, cuerpo, datetime.now(UTC).isoformat(timespec="seconds")),
		)

	def borrador(self, clave: str) -> tuple[str, str, str] | None:
		"""``(titulo, cuerpo, fecha ISO)`` o ``None``."""
		fila = self.bd.consultar_uno("SELECT titulo, cuerpo, actualizado_en FROM borradores WHERE clave = ?", (clave,))
		return (fila["titulo"], fila["cuerpo"], fila["actualizado_en"]) if fila else None

	def borrar_borrador(self, clave: str) -> None:
		self.bd.ejecutar("DELETE FROM borradores WHERE clave = ?", (clave,))

	def borradores(self) -> list[tuple[str, str, str, str]]:
		filas = self.bd.consultar("SELECT clave, titulo, cuerpo, actualizado_en FROM borradores ORDER BY actualizado_en DESC")
		return [(f["clave"], f["titulo"], f["cuerpo"], f["actualizado_en"]) for f in filas]

	# ── Notificaciones avisadas ───────────────────────────────────────────────

	def avisadas(self, cuenta: str) -> dict[str, str]:
		filas = self.bd.consultar("SELECT id, actualizada_en FROM notificaciones_avisadas WHERE cuenta = ?", (cuenta,))
		return {f["id"]: f["actualizada_en"] for f in filas}

	def marcar_avisadas(self, cuenta: str, notificaciones: list[tuple[str, str]]) -> None:
		if not notificaciones:
			return
		self.bd.ejecutar_lote(
			"INSERT INTO notificaciones_avisadas (cuenta, id, actualizada_en) VALUES (?, ?, ?) "
			"ON CONFLICT(cuenta, id) DO UPDATE SET actualizada_en = excluded.actualizada_en",
			[(cuenta, i, f) for i, f in notificaciones],
		)
		# Se conservan solo las más recientes: la tabla no crece sin límite.
		self.bd.ejecutar(
			"DELETE FROM notificaciones_avisadas WHERE cuenta = ? AND id NOT IN ("
			"SELECT id FROM notificaciones_avisadas WHERE cuenta = ? ORDER BY actualizada_en DESC LIMIT ?)",
			(cuenta, cuenta, MAXIMO_AVISADAS),
		)

	def cerrar(self) -> None:
		self.bd.cerrar()
