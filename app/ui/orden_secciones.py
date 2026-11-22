"""Orden y secciones visibles de las ventanas (principal y de repositorio), elegidos por la persona.

Por qué: la ventana de un repositorio tiene más de veinte secciones y
Alt+1 a Alt+9 solo llegan a las nueve primeras. Quien nunca usa Webhooks
o Claves de despliegue las recorre siempre al bajar con las flechas. En
Preferencias, Secciones, se ocultan y se ordenan; las Alt+número siguen
el orden elegido.

Se guarda el orden completo y la lista de ocultas por separado (no solo las
visibles): así una sección NUEVA de una versión posterior aparece sola, al
final, en vez de quedar oculta porque no estaba en la lista guardada.

Funciones puras (sin wx) para poder probarlas.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

#: Ventanas configurables: clave → (prefijo en la configuración, secciones que no se pueden ocultar).
VENTANAS: dict[str, tuple[str, tuple[str, ...]]] = {
	"principal": ("secciones.principal", ("busqueda",)),
	"repositorio": ("secciones.repositorio", ("resumen",)),
}


def ordenar(fabrica: Sequence[str], orden: Sequence[str] = (), ocultas: Sequence[str] = (),
	obligatorias: Sequence[str] = ()) -> list[str]:
	"""Secciones visibles en el orden elegido.

	:param fabrica: todas las secciones en su orden de fábrica.
	:param orden: orden guardado (puede tener secciones que ya no existen o faltarle las nuevas).
	:param ocultas: secciones que la persona ha ocultado.
	:param obligatorias: secciones que nunca se ocultan (aunque estén en ``ocultas``).
	"""
	existentes = set(fabrica)
	completo = [s for s in dict.fromkeys(orden) if s in existentes]
	completo += [s for s in fabrica if s not in completo]
	ocultas_validas = set(ocultas) - set(obligatorias)
	visibles = [s for s in completo if s not in ocultas_validas]
	return visibles or list(fabrica[:1])


def orden_completo(fabrica: Sequence[str], orden: Sequence[str] = ()) -> list[str]:
	"""Todas las secciones (también las ocultas) en el orden elegido, para Preferencias."""
	existentes = set(fabrica)
	completo = [s for s in dict.fromkeys(orden) if s in existentes]
	return completo + [s for s in fabrica if s not in completo]


def de_configuracion(config: Any, ventana: str, fabrica: Sequence[str]) -> list[str]:
	"""Secciones visibles de ``ventana`` («principal» o «repositorio») según la configuración."""
	prefijo, obligatorias = VENTANAS[ventana]
	orden = list(config.obtener(f"{prefijo}_orden", []) or [])
	ocultas = list(config.obtener(f"{prefijo}_ocultas", []) or [])
	return ordenar(fabrica, orden, ocultas, obligatorias)
