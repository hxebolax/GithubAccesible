"""Mejoras tomadas de otros clientes accesibles: zip desde cualquier sitio, bifurcaciones, Control+U, SHA-256 y perfil."""

from __future__ import annotations

import hashlib
from unittest import mock

import wx

from app.ui import descarga_codigo as dc
from app.ui.detalle import releases as rel
from app.ui.vistas import principales as pr
from tests.apoyo_app import crear_contexto


def test_nombre_del_zip():
	assert dc.nombre_zip("ana/proyecto", "main") == "proyecto-main.zip"
	assert dc.nombre_zip("ana/proyecto", "feature/x") == "proyecto-feature-x.zip"
	assert dc.nombre_zip("ana/proyecto") == "proyecto-principal.zip"


def test_descargar_codigo_usa_la_rama_y_avisa(tmp_path):
	ctx, api, anuncios = crear_contexto()
	destino = tmp_path / "p.zip"
	api.archivo_zip.return_value = "https://api.github.com/repos/ana/p/zipball/dev"
	dc.descargar_codigo(None, ctx, "ana/p", "dev", destino=destino)
	api.archivo_zip.assert_called_once_with("ana/p", "dev")
	# Va al gestor de descargas (sigue aunque se cierre la ventana) con la cabecera que exige zipball.
	pedida = ctx.descargas.pedidas[-1]
	assert pedida.url.endswith("/zipball/dev") and pedida.destino == str(destino) and pedida.sobrescribir
	assert pedida.aceptar == "application/vnd.github+json" and "(dev)" in pedida.origen
	assert any("Puede cerrar esta ventana" in a for a in anuncios)


def test_persona_de_cualquier_fila():
	assert pr.persona_del_elemento({"actor": {"login": "eva"}, "repo": {"name": "a/b"}}) == "eva"
	assert pr.persona_del_elemento({"login": "marta", "type": "User"}) == "marta"
	assert pr.persona_del_elemento({"number": 1, "user": {"login": "luis"}, "repository_url": "x/repos/o/r"}) == "luis"
	assert pr.persona_del_elemento({"full_name": "ana/p", "owner": {"login": "ana"}}) == "ana"
	assert pr.persona_del_elemento(None) == ""


def test_suma_sha256_de_los_recursos(tmp_path):
	suma = hashlib.sha256(b"hola").hexdigest()
	assert rel.sha256_de({"digest": f"sha256:{suma.upper()}"}) == suma
	assert rel.sha256_de({"digest": "md5:abc"}) == "" and rel.sha256_de({}) == ""
	archivo = tmp_path / "a.bin"
	archivo.write_bytes(b"hola")
	assert rel.sha256_archivo(archivo) == suma


def test_menu_de_bifurcacion(app_wx, monkeypatch):
	from app.ui.repositorio import ventana as v

	monkeypatch.setattr(v.VentanaRepositorio, "Show", lambda self, mostrar=True: True)
	monkeypatch.setattr(v, "_VENTANAS", {})
	ctx, api, anuncios = crear_contexto()
	api.repositorio.return_value = {"full_name": "ana/p", "default_branch": "main"}
	ventana = v.abrir_ventana_repositorio(ctx, "ana/p")
	try:
		ventana.aplicar_info({"full_name": "ana/p", "default_branch": "main"})
		assert not ventana.item_original.IsEnabled() and not ventana.item_sincronizar.IsEnabled()
		ventana.aplicar_info({"full_name": "ana/p", "default_branch": "main", "fork": True, "parent": {"full_name": "org/p"}})
		assert ventana.original() == "org/p" and ventana.item_sincronizar.IsEnabled()
		api.sincronizar_bifurcacion.return_value = {"merge_type": "fast-forward", "message": "ok"}
		with mock.patch("app.ui.comunes.pedir_texto", return_value="main"):
			ventana.sincronizar_bifurcacion()
		api.sincronizar_bifurcacion.assert_called_once_with("ana/p", "main")
		assert any("avance rápido" in a for a in anuncios)
		assert ventana.propietario() == "ana"
	finally:
		ventana.Destroy()
		wx.Yield()


def test_perfil_con_estrella_y_actividad(app_wx, monkeypatch):
	from app.ui.detalle import usuario as u

	ctx, api, _a = crear_contexto()
	ventana = u.VentanaUsuario(None, ctx, "eva")
	try:
		titulos = [ventana.libro.GetPageText(i) for i in range(ventana.libro.GetPageCount())]
		assert titulos[:4] == ["Resumen", "Repositorios", "Con estrella", "Actividad"]
		ventana.usuario = {"login": "eva"}
		api.readme.return_value = "# Hola"
		with mock.patch("app.ui.visor_ayuda.mostrar_documento") as mostrar:
			ventana.leer_readme()
		api.readme.assert_called_once_with("eva/eva")
		assert mostrar.call_args.args[1] == "Presentación de eva"
	finally:
		ventana.Destroy()
		wx.Yield()
