"""Pruebas de los adjuntos de texto del editor (issue n.º 1: adjuntar registros .log).

La lógica (leer, plegar, enlazar) se prueba sin ventanas; el editor, con la API
simulada y las tareas en el acto. Ningún diálogo se muestra en pantalla.
"""

from __future__ import annotations

import pytest

from app.services import adjuntos
from app.services.adjuntos import ErrorAdjunto

# ── Lógica sin interfaz ─────────────────────────────────────────────────────


def test_leer_texto_utf8_windows1252_y_utf16(tmp_path):
	utf8 = tmp_path / "a.log"
	utf8.write_bytes("Línea uno\r\nLínea dos\r\n".encode("utf-8-sig"))
	assert adjuntos.leer_texto(str(utf8)) == "Línea uno\nLínea dos\n"

	ansi = tmp_path / "b.log"
	ansi.write_bytes("Configuración aplicada\n".encode("cp1252"))
	assert adjuntos.leer_texto(str(ansi)) == "Configuración aplicada\n"

	utf16 = tmp_path / "c.txt"
	utf16.write_bytes("Año\n".encode("utf-16"))
	assert adjuntos.leer_texto(str(utf16)) == "Año\n"


def test_leer_texto_rechaza_binarios_y_vacios(tmp_path):
	imagen = tmp_path / "foto.png"
	imagen.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
	with pytest.raises(ErrorAdjunto, match="No es un archivo de texto"):
		adjuntos.leer_texto(str(imagen))
	vacio = tmp_path / "vacio.log"
	vacio.write_bytes(b"  \r\n")
	with pytest.raises(ErrorAdjunto, match="vacío"):
		adjuntos.leer_texto(str(vacio))


def test_leer_texto_rechaza_archivos_enormes(tmp_path, monkeypatch):
	grande = tmp_path / "grande.log"
	grande.write_text("x" * 50)
	monkeypatch.setattr(adjuntos, "LIMITE_ARCHIVO", 10)
	with pytest.raises(ErrorAdjunto, match="10 MB"):
		adjuntos.leer_texto(str(grande))


def test_bloque_plegado_escapa_el_nombre_y_alarga_la_valla():
	bloque = adjuntos.bloque_plegado("<raro>.log", "texto con ```` dentro", "1,0 KB")
	assert bloque.startswith("<details>\n<summary>&lt;raro&gt;.log (1,0 KB)</summary>\n\n`````text\n")
	assert bloque.endswith("\n`````\n\n</details>\n")
	assert adjuntos.bloque_plegado("x.py", "print()\n").count("```python\nprint()\n```") == 1


def test_cabe_en_cuerpo_respeta_el_limite_de_github():
	assert adjuntos.cabe_en_cuerpo("hola", "x" * 1000)
	assert not adjuntos.cabe_en_cuerpo("", "x" * adjuntos.LIMITE_CUERPO)


def test_insertar_deja_el_bloque_en_lineas_propias():
	texto, cursor = adjuntos.insertar("Pasos:abc", 6, "BLOQUE\n")
	assert texto == "Pasos:\n\nBLOQUE\n\nabc"
	assert texto[cursor:] == "abc"
	assert adjuntos.insertar("", 0, "B\n") == ("B\n", 2)


def test_enlaces_del_gist():
	gist = {"html_url": "https://gist.github.com/ana/abc"}
	assert adjuntos.url_archivo_gist(gist, "Registro.log") == "https://gist.github.com/ana/abc#file-registro-log"
	assert adjuntos.enlace_gist("a[1].log", "https://g/x") == "Archivo adjunto: [a\\[1\\].log](https://g/x)\n"
	with pytest.raises(ErrorAdjunto):
		adjuntos.url_archivo_gist({}, "a.log")


# ── Editor ──────────────────────────────────────────────────────────────────


def _editor(marco, **opciones):
	from app.ui.editor import DialogoEditor
	from tests.apoyo_app import crear_contexto

	ctx, api, anuncios = crear_contexto()
	dialogo = DialogoEditor(marco, ctx, "Comentar", lambda valores: valores, **opciones)
	return dialogo, api, anuncios


def test_el_boton_solo_sale_cuando_se_pide_y_el_teclado_es_correcto(app_wx, marco):
	from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto

	sin, _api, _a = _editor(marco)
	assert sin.boton_adjuntar is None
	con, _api, _a = _editor(marco, con_adjuntos=True, con_titulo=True)
	assert con.boton_adjuntar.GetLabel() == "Ad&juntar archivo…"
	afirmar_teclado_correcto(con)


def test_adjuntar_dentro_del_texto(app_wx, marco, monkeypatch):
	dialogo, api, anuncios = _editor(marco, con_adjuntos=True, cuerpo="Me falla al abrir.")
	preguntas = []
	monkeypatch.setattr("app.ui.editor.elegir_opcion", lambda _p, mensaje, _t, opciones: preguntas.append((mensaje, opciones)) or 0)
	dialogo.campo_cuerpo.SetInsertionPointEnd()
	dialogo._adjuntar_texto("app.log", "ERROR algo\n", 11)
	mensaje, opciones = preguntas[0]
	assert "«app.log»: 11 bytes, 1 línea." in mensaje and "tokens" in mensaje
	assert opciones[0] == "&Dentro del texto, plegado"
	cuerpo = dialogo.campo_cuerpo.GetValue()
	assert cuerpo.startswith("Me falla al abrir.\n\n<details>\n<summary>app.log (11 bytes)</summary>")
	assert "```text\nERROR algo\n```" in cuerpo
	assert anuncios[-1] == "Adjuntado «app.log» dentro del texto, plegado."
	api.crear_gist.assert_not_called()


def test_adjuntar_como_gist_secreto(app_wx, marco, monkeypatch):
	dialogo, api, anuncios = _editor(marco, con_adjuntos=True)
	api.crear_gist.return_value = {"html_url": "https://gist.github.com/ana/abc"}
	monkeypatch.setattr("app.ui.editor.elegir_opcion", lambda _p, _m, _t, opciones: 1)
	dialogo._adjuntar_texto("app.log", "ERROR\n", 6)
	archivos = api.crear_gist.call_args.args[0]
	assert archivos == {"app.log": "ERROR\n"}
	assert api.crear_gist.call_args.kwargs["publico"] is False
	assert dialogo.campo_cuerpo.GetValue() == "Archivo adjunto: [app.log](https://gist.github.com/ana/abc#file-app-log)\n"
	assert dialogo._subiendo == 0
	assert anuncios[-1] == "Subido «app.log»; su enlace está en el texto."


def test_un_registro_demasiado_largo_solo_se_ofrece_como_gist(app_wx, marco, monkeypatch):
	dialogo, api, _a = _editor(marco, con_adjuntos=True)
	ofrecidas = []
	monkeypatch.setattr("app.ui.editor.elegir_opcion", lambda _p, mensaje, _t, opciones: ofrecidas.append(opciones) or None)
	dialogo._adjuntar_texto("enorme.log", "x" * adjuntos.LIMITE_CUERPO, adjuntos.LIMITE_CUERPO)
	assert ofrecidas == [["Como &gist secreto, con su enlace", "&Cancelar"]]
	assert dialogo.campo_cuerpo.GetValue() == ""
	api.crear_gist.assert_not_called()


def test_un_archivo_binario_avisa_sin_tocar_el_texto(app_wx, marco, monkeypatch):
	dialogo, _api, _a = _editor(marco, con_adjuntos=True)
	errores = []
	monkeypatch.setattr("app.ui.editor.mostrar_error", lambda _p, mensaje, _t="": errores.append(mensaje))
	dialogo._adjuntar_leidos([("C:/x/foto.png", ErrorAdjunto("No es un archivo de texto."), 0)])
	assert errores == ["«foto.png»: No es un archivo de texto."]
	assert dialogo.campo_cuerpo.GetValue() == ""


def test_no_se_envia_mientras_se_sube_un_adjunto(app_wx, marco):
	dialogo, _api, anuncios = _editor(marco, con_adjuntos=True, cuerpo="Hola")
	dialogo._subiendo = 1
	dialogo._al_aceptar(None)
	assert not dialogo._enviando and dialogo.resultado is None
	assert anuncios[-1] == "Espere a que termine de subirse el adjunto."
