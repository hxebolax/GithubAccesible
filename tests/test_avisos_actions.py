"""Opciones generales del aviso al terminar una ejecución de Actions vigilada (incidencia #8)."""

from __future__ import annotations

from app.services import vigilancia_actions as va
from tests.apoyo_app import crear_contexto

BIEN = va.Aviso("ana/repo", 1, "CI", "success", "main")
MAL = va.Aviso("ana/repo", 2, "CI", "failure", "main")
CANCELADA = va.Aviso("ana/repo", 3, "CI", "cancelled", "main")


def test_que_resultados_se_avisan():
	assert all(va.hay_que_avisar(a) for a in (BIEN, MAL, CANCELADA))
	assert [va.hay_que_avisar(a, "fallidas") for a in (BIEN, MAL, CANCELADA)] == [False, True, True]
	assert [va.hay_que_avisar(a, "correctas") for a in (BIEN, MAL, CANCELADA)] == [True, False, False]


def _ventana(ctx):
	from app.ui.ventana_principal import VentanaPrincipal

	return VentanaPrincipal(ctx)


def test_sonido_voz_y_resultados_segun_preferencias(app_wx):
	ctx, _api, anuncios = crear_contexto()
	ctx.config.establecer("acciones.notificacion_windows", False)
	ventana = _ventana(ctx)
	try:
		# De fábrica: sonido y voz con cualquier resultado.
		ctx.sonidos.eventos.clear()
		ventana._avisar_ejecucion(BIEN)
		assert ctx.sonidos.eventos == ["accion_exito"] and anuncios[-1] == BIEN.texto
		# Sin sonido: solo la voz.
		ctx.config.establecer("acciones.sonido_al_terminar", False)
		ctx.sonidos.eventos.clear()
		ventana._avisar_ejecucion(MAL)
		assert ctx.sonidos.eventos == [] and anuncios[-1] == MAL.texto
		# Sin voz y con sonido: solo el sonido.
		ctx.config.establecer_varias({"acciones.sonido_al_terminar": True, "acciones.voz_al_terminar": False})
		antes = list(anuncios)
		ventana._avisar_ejecucion(CANCELADA)
		assert ctx.sonidos.eventos == ["accion_fallo"] and anuncios == antes
		# Solo las que fallan: de las correctas no se dice ni suena nada.
		ctx.config.establecer_varias({"acciones.voz_al_terminar": True, "acciones.avisar_resultados": "fallidas"})
		ctx.sonidos.eventos.clear()
		antes = list(anuncios)
		ventana._avisar_ejecucion(BIEN)
		assert ctx.sonidos.eventos == [] and anuncios == antes
		ventana._avisar_ejecucion(MAL)
		assert ctx.sonidos.eventos == ["accion_fallo"] and anuncios[-1] == MAL.texto
	finally:
		ventana.Destroy()
