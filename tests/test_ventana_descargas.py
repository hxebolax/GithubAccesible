"""Ventana «Descargas»: teclado accesible, filas al día y órdenes (sin red)."""

from __future__ import annotations

import wx

from app.services import gestor_descargas as gd
from app.ui import descargas as ud
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto
from tests.apoyo_app import crear_contexto


def _contexto(tmp_path):
	ctx, _api, anuncios = crear_contexto()
	ctx.descargas = gd.GestorDescargas(tmp_path, lambda cuenta, aceptar: None)
	completa = gd.Descarga("https://x/a", str(tmp_path / "a.zip"), "a.zip", estado=gd.COMPLETADA, hecho=10, total=10,
		ruta_final=str(tmp_path / "a.zip"), origen="Release 1.0 de ana/repo")
	(tmp_path / "a.zip").write_bytes(b"0123456789")
	pausada = gd.Descarga("https://x/b", str(tmp_path / "b.zip"), "b.zip", estado=gd.PAUSADA, hecho=2048, total=4096)
	fallida = gd.Descarga("https://x/c", str(tmp_path / "c.zip"), "c.zip", estado=gd.ERROR, error="No se ha encontrado.")
	ctx.descargas._descargas = [completa, pausada, fallida]
	return ctx, anuncios


def test_teclado_filas_y_estado(app_wx, tmp_path):
	ctx, _anuncios = _contexto(tmp_path)
	ventana = ud.VentanaDescargas(ctx)
	try:
		afirmar_teclado_correcto(ventana)
		# La más reciente arriba.
		assert [ventana.lista.texto_celda(i, 0) for i in range(3)] == ["c.zip", "b.zip", "a.zip"]
		assert ventana.lista.texto_celda(1, 1) == "En pausa" and ventana.lista.texto_celda(1, 2) == "50 %"
		assert ventana.lista.texto_celda(0, 8) == "No se ha encontrado."
		assert "1 en pausa" in ventana.estado.GetLabel() and "1 error" in ventana.estado.GetLabel()
	finally:
		ventana.Destroy()


def test_ordenes_sobre_la_elegida(app_wx, tmp_path, dialogo_modal):
	ctx, anuncios = _contexto(tmp_path)
	ventana = ud.VentanaDescargas(ctx)
	try:
		ventana.lista.enfocar_fila(1, anunciar=False)  # b.zip, en pausa
		assert ventana.botones["reanudar"].IsEnabled() and not ventana.botones["pausar"].IsEnabled()
		ventana.decir_estado()
		assert anuncios[-1].startswith("b.zip. En pausa. 2,0 KB de 4,0 KB (50 %)")
		ctx.descargas._sesion_para = lambda cuenta, aceptar: (_ for _ in ()).throw(RuntimeError("sin red"))
		ventana.reanudar()
		assert anuncios[-1] == "Reanudada: b.zip."
		ventana.lista.enfocar_fila(2, anunciar=False)  # a.zip, completada
		dialogo_modal.responder(lambda d: wx.ID_YES)
		ventana.quitar_terminadas()
		assert "a.zip" not in [d.nombre for d in ctx.descargas.descargas()]
		assert (tmp_path / "a.zip").exists(), "quitar de la lista no borra el archivo"
	finally:
		ventana.Destroy()


def test_iniciar_descarga_avisa_y_la_ventana_se_abre_una_vez(app_wx, tmp_path):
	ctx, _api, anuncios = crear_contexto()
	descarga = ud.iniciar_descarga(None, ctx, "https://api.github.com/repos/a/b/releases/assets/1", tmp_path / "x.zip",
		origen="Release de a/b")
	assert descarga.aceptar == "application/octet-stream", "la cabecera adecuada para un recurso de release"
	assert descarga.cuenta and "Puede cerrar esta ventana" in anuncios[-1]
	ctx.descargas = gd.GestorDescargas(tmp_path, lambda cuenta, aceptar: None)
	primera = ud.abrir_gestor(ctx)
	try:
		assert ud.abrir_gestor(ctx) is primera
	finally:
		primera.Close()
		primera.Destroy()
