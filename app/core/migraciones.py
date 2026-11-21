"""Migraciones del esquema de la base de datos de GitHub Accesible (``data/db/app.db``).

REGLAS: nunca se modifica ni se reordena una migración publicada; se añade otra
al final. Cada una se ejecuta en su transacción junto con ``PRAGMA user_version``.
"""

from __future__ import annotations

from app.core.base_datos import Migracion

MIGRACIONES: tuple[Migracion, ...] = (
	Migracion(
		"Borradores del editor y notificaciones ya avisadas",
		sql="""
			CREATE TABLE borradores (
				clave TEXT PRIMARY KEY,          -- qué se estaba escribiendo («comentario:dueño/repo#12»)
				titulo TEXT NOT NULL DEFAULT '',
				cuerpo TEXT NOT NULL DEFAULT '',
				actualizado_en TEXT NOT NULL      -- ISO 8601 en UTC
			);
			CREATE TABLE notificaciones_avisadas (
				cuenta TEXT NOT NULL,
				id TEXT NOT NULL,
				actualizada_en TEXT NOT NULL,     -- updated_at de GitHub: si cambia, es novedad otra vez
				PRIMARY KEY (cuenta, id)
			);
		""",
	),
)
