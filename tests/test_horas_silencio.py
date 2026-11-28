"""Horas de silencio de los avisos en segundo plano (incidencia #15)."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.configuracion import ErrorValidacion, validar_valor
from app.services import horas_silencio as hs
from app.services import vigilancia_actions as va
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto
from tests.apoyo_app import crear_contexto


class Reloj:
	"""Reloj que la prueba pone a la hora que quiere."""

	def __init__(self, hora: int, minuto: int = 0) -> None:
		self.poner(hora, minuto)

	def poner(self, hora: int, minuto: int = 0) -> None:
		self.ahora = datetime(2026, 11, 28, hora, minuto)

	def __call__(self) -> datetime:
		return self.ahora


def _silencio(ctx, reloj: Reloj) -> hs.HorasSilencio:
	ctx.extra["horas_silencio"] = silencio = hs.HorasSilencio(ctx.config, reloj=reloj)
	return silencio


@pytest.mark.parametrize(("texto", "minutos"), [
	("23:00", 23 * 60), ("7:05", 7 * 60 + 5), ("07.30", 7 * 60 + 30), ("7h30", 7 * 60 + 30), ("7h", 7 * 60),
	("7", 7 * 60), (" 0:00 ", 0), ("23:59", 23 * 60 + 59),
])
def test_horas_que_se_entienden(texto, minutos):
	assert hs.interpretar_hora(texto) == minutos
	validar_valor("notificaciones.silencio_desde", texto)


@pytest.mark.parametrize("texto", ["", "24:00", "7:60", "7:5", "siete", "-1", "12:00:00"])
def test_horas_que_no_valen(texto):
	assert hs.interpretar_hora(texto) is None
	with pytest.raises(ErrorValidacion, match="23:30"):
		validar_valor("notificaciones.silencio_hasta", texto)


def test_periodo_normal_cruzando_la_medianoche_y_horas_iguales():
	assert hs.formatear_hora(7 * 60) == "07:00"
	# De 23:00 a 7:00 cruza la medianoche: a las 7:00 ya se avisa.
	assert [hs.dentro(23 * 60, 7 * 60, h * 60) for h in (22, 23, 0, 3, 6, 7, 12)] == [False, True, True, True, True, False, False]
	# De 13:00 a 15:30, dentro del mismo día.
	assert [hs.dentro(13 * 60, 15 * 60 + 30, m) for m in (12 * 60 + 59, 13 * 60, 15 * 60 + 29, 15 * 60 + 30)] == [False, True, True, False]
	assert not any(hs.dentro(8 * 60, 8 * 60, m) for m in range(0, 24 * 60, 30)), "con las dos horas iguales no se calla nada"


def test_solo_si_estan_activadas_y_cuenta_lo_callado():
	ctx, _api, _a = crear_contexto()
	reloj = Reloj(2)
	silencio = _silencio(ctx, reloj)
	assert not silencio.activas() and not silencio.silenciar(), "de fábrica están desactivadas"
	ctx.config.establecer("notificaciones.silencio_activado", True)
	assert silencio.activas() and silencio.hasta() == "07:00"
	assert silencio.silenciar(cantidad=3) and silencio.silenciar(hs.OTRO)
	ctx.config.establecer("notificaciones.silencio_actions", False)
	assert not silencio.silenciar(hs.OTRO), "Actions y descargas solo se callan si se pide"
	assert silencio.revisar() is None, "mientras dura no hay resumen"
	reloj.poner(7)
	recuento = silencio.revisar()
	assert (recuento.notificaciones, recuento.otros) == (3, 1)
	assert silencio.revisar() is None, "el resumen se da una sola vez"
	# Una noche en la que no llega nada no da resumen.
	reloj.poner(23, 30)
	assert silencio.revisar() is None
	reloj.poner(8)
	assert silencio.revisar() is None


def _ventana(ctx):
	from app.ui.ventana_principal import VentanaPrincipal

	return VentanaPrincipal(ctx)


NUEVA = {"id": "1", "unread": True, "reason": "mention", "updated_at": "x",
	"repository": {"full_name": "ana/repo"}, "subject": {"title": "Fallo al abrir"}}


def test_la_ventana_calla_los_avisos_y_resume_al_terminar(app_wx):
	ctx, _api, anuncios = crear_contexto()
	ctx.config.establecer_varias({"notificaciones.silencio_activado": True, "notificaciones.silencio_desde": "23",
		"notificaciones.silencio_hasta": "7:30", "acciones.notificacion_windows": False})
	reloj = Reloj(1)
	_silencio(ctx, reloj)
	ventana = _ventana(ctx)
	try:
		ctx.sonidos.eventos.clear()
		anuncios.clear()
		ventana._avisar_nuevas([NUEVA, dict(NUEVA, id="2")])
		ventana._avisar_ejecucion(va.Aviso("ana/repo", 1, "CI", "failure", "main"))
		assert ctx.sonidos.eventos == [] and anuncios == [], "de noche no suena ni se dice nada"
		ventana._actualizar_estado()
		assert "Avisos en silencio hasta las 07:30" in ventana.GetStatusBar().GetStatusText(0)
		assert anuncios == []

		reloj.poner(7, 30)
		ventana.marcar_contador_notificaciones(2)
		ventana._ultimas_notificaciones = [NUEVA]
		ventana._actualizar_estado()
		assert ctx.sonidos.eventos == ["notificacion"]
		assert len(anuncios) == 1
		resumen = anuncios[0]
		assert resumen.startswith("Terminan las horas de silencio. Mientras tanto llegaron 2 notificaciones nuevas. "
			"Se calló 1 aviso de Actions o de descargas. 2 notificaciones sin leer.")
		assert "silencio" not in ventana.GetStatusBar().GetStatusText(0)

		# Fuera de las horas de silencio, los avisos vuelven a ser los de siempre.
		ventana._avisar_nuevas([NUEVA])
		assert anuncios[-1] == "Notificación nueva de ana/repo: Fallo al abrir"
	finally:
		ventana.Destroy()


def test_sin_resumen_si_no_se_quiere(app_wx):
	ctx, _api, anuncios = crear_contexto()
	ctx.config.establecer_varias({"notificaciones.silencio_activado": True, "notificaciones.silencio_resumen": False})
	reloj = Reloj(3)
	_silencio(ctx, reloj)
	ventana = _ventana(ctx)
	try:
		ventana._avisar_nuevas([NUEVA])
		reloj.poner(9)
		anuncios.clear()
		ventana._revisar_fin_silencio()
		assert anuncios == []
	finally:
		ventana.Destroy()


def test_pagina_de_preferencias(app_wx, monkeypatch):
	from app.ui import dialogo_preferencias
	from app.ui.preferencias import TITULO_HORAS_SILENCIO, DialogoPreferenciasGitHub

	avisos: list[str] = []
	monkeypatch.setattr(dialogo_preferencias, "mostrar_aviso", lambda padre, texto, titulo: avisos.append(texto))

	ctx, _api, _a = crear_contexto()
	dialogo = DialogoPreferenciasGitHub(None, ctx, [])
	try:
		titulos = [dialogo.libro.GetPageText(i) for i in range(dialogo.libro.GetPageCount())]
		indice = titulos.index(TITULO_HORAS_SILENCIO)
		dialogo.libro.SetSelection(indice)
		afirmar_teclado_correcto(dialogo.libro.GetPage(indice))
		dialogo.control_de("notificaciones.silencio_activado").SetValue(True)
		dialogo.control_de("notificaciones.silencio_desde").ChangeValue("25:00")
		assert not dialogo.aplicar(), "una hora que no existe no se guarda"
		assert avisos == ["Desde las (HH:MM)\n\nEscriba una hora entre 0:00 y 23:59, por ejemplo 23:30 o 7:00."]
		assert not ctx.config.obtener("notificaciones.silencio_activado")
		dialogo.control_de("notificaciones.silencio_desde").ChangeValue("22:30")
		assert dialogo.aplicar()
		assert ctx.config.obtener("notificaciones.silencio_activado")
		assert ctx.config.obtener("notificaciones.silencio_desde") == "22:30"
	finally:
		dialogo.Destroy()
