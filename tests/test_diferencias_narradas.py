"""Pruebas de las «diferencias narradas»: resumen, parejas, qué cambia en una línea e invisibles.

Las funciones puras se prueban sin wx; el visor (``PanelDiferencias``) con la
ventana sin mostrar, la voz recogida en una lista y los diálogos simulados.
"""

from __future__ import annotations

import pytest
import wx

from app.services import diferencias as d
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto
from tests.apoyo_app import crear_contexto
from tests.test_git_y_diff import DIFF

#: Teclas que la lista de diferencias atiende a mano.
TECLAS_DIFF = ["F8", "Mayús+F8", "Ctrl+F8", "Ctrl+Mayús+F8", "F7", "Mayús+F7", "Ctrl+G", "Ctrl+T", "Ctrl+Mayús+T",
	"Ctrl+D", "Ctrl+Shift+D", "Ctrl+C", "Ctrl+Intro"]

DIFF_VARIADO = """diff --git a/viejo.py b/nuevo.py
similarity index 90%
rename from viejo.py
rename to nuevo.py
--- a/viejo.py
+++ b/nuevo.py
@@ -1,3 +1,3 @@
 import os
-TIEMPO = conectar(timeout=30)
+TIEMPO = conectar(timeout=60)
 fin()
diff --git a/borrado.txt b/borrado.txt
deleted file mode 100644
--- a/borrado.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-uno
-dos
diff --git a/logo.png b/logo.png
Binary files a/logo.png and b/logo.png differ
"""


# ════════════════════════════════════════════════════════════════════════════
# Resumen
# ════════════════════════════════════════════════════════════════════════════


def test_resumen_total_y_por_archivo():
	resumen = d.resumen_diff(d.analizar(DIFF))
	assert resumen[0] == "2 archivos cambiados con 3 cambios: 4 líneas añadidas y 2 eliminadas."
	assert resumen[1] == "Archivo 1 de 2: app/uno.py. Modificado. 3 añadidas y 2 eliminadas."
	assert resumen[2] == "Archivo 2 de 2: nuevo.txt. Nuevo. 1 añadida."


def test_resumen_renombrado_borrado_y_binario():
	archivos = d.analizar(DIFF_VARIADO)
	resumen = d.resumen_diff(archivos)
	assert resumen[0].startswith("3 archivos cambiados con 2 cambios: 1 línea añadida y 3 eliminadas")
	assert resumen[1] == "Archivo 1 de 3: nuevo.py. Renombrado desde viejo.py. 1 añadida y 1 eliminada."
	assert resumen[2] == "Archivo 2 de 3: borrado.txt. Borrado. 2 eliminadas."
	assert resumen[3] == "Archivo 3 de 3: logo.png. Modificado. Archivo binario."
	assert d.resumen_diff([]) == ["No hay diferencias."]


def test_archivo_nuevo_sin_cabecera_de_git():
	archivo = d.analizar("--- /dev/null\n+++ b/nota.md\n@@ -0,0 +1 @@\n+hola\n")[0]
	assert archivo.estado == "añadido" and archivo.ruta == "nota.md"


# ════════════════════════════════════════════════════════════════════════════
# Grupos y parejas
# ════════════════════════════════════════════════════════════════════════════


def test_grupos_numerados_coinciden_con_los_saltos_de_f8():
	lineas = d.aplanar(d.analizar(DIFF))
	grupos = d.grupos_de_cambios(lineas)
	assert [g.numero for g in grupos] == [1, 2, 3]
	indice, inicios = 0, []
	while (indice := d.siguiente_cambio(lineas, indice)) is not None:
		inicios.append(indice)
	assert inicios == [g.inicio for g in grupos]
	assert d.nombre_cambio(grupos[1], len(grupos)) == "Cambio 2 de 3"
	assert d.grupo_de(grupos, grupos[0].fin) is grupos[0]
	assert d.grupo_de(grupos, 0) is None, "la fila del archivo no está en ningún cambio"


def test_emparejar_por_parecido_y_lineas_reescritas():
	# La borrada no se empareja con la cambiada aunque vaya primero.
	assert d.emparejar(["línea borrada del todo", "b = 2"], ["b = 3"]) == [(1, 0)]
	# Una a una, aunque no se parezcan: son líneas reescritas.
	assert d.emparejar(["alfa", "beta"], ["uno", "dos"]) == [(0, 0), (1, 1)]
	assert d.emparejar(["a = 1", "zzz", "c = 3"], ["a = 2", "c = 4"]) == [(0, 0), (2, 1)]
	assert d.emparejar(["solo"], []) == []


def test_emparejar_grupos_enormes_no_compara_todo():
	eliminadas = [f"valor_{i} = {i}" for i in range(50)]
	añadidas = [f"valor_{i} = {i + 1}" for i in range(50)]
	assert d.emparejar(eliminadas, añadidas) == [(i, i) for i in range(50)]


def test_aviso_sin_salto_final_no_corta_el_grupo():
	texto = "@@ -1 +1 @@\n-viejo final\n\\ No newline at end of file\n+nuevo final\n\\ No newline at end of file\n"
	lineas = d.aplanar(d.analizar(texto, "a.txt"))
	grupos = d.grupos_de_cambios(lineas)
	assert len(grupos) == 1
	eliminada = next(i for i, linea in enumerate(lineas) if linea.tipo == d.ELIMINADA)
	assert lineas[d.pareja_de(grupos, lineas, eliminada)].texto == "nuevo final"


# ════════════════════════════════════════════════════════════════════════════
# Qué cambia dentro de una línea
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(("antes", "despues", "esperado"), [
	("x = conectar(timeout=30)", "x = conectar(timeout=60)", "Cambia «conectar(timeout=30)» por «conectar(timeout=60)»."),
	("b = 2", "b = 3", "Cambia «2» por «3»."),
	("return total", "return total + 1", "Añade «+ 1» al final."),
	("a b c", "z a b c", "Añade «z» al principio."),
	("a b c", "a x b c", "Añade «x» después de «a»."),
	("import os, sys", "import sys", "Quita «os,»."),
	("hola mundo", "adiós amigos", "Línea reescrita."),
	("    return a", "\treturn a", "Solo cambian espacios: cambia la sangría de 4 espacios a 1 tabulador."),
	("x = 1", "x = 1  ", "Solo cambian espacios: cambian los espacios del final de la línea."),
	("x = 1", "    x = 2", "Cambia «1» por «2»; añade una sangría de 4 espacios."),
])
def test_describir_cambio(antes, despues, esperado):
	assert d.describir_cambio(antes, despues) == esperado


def test_describir_cambio_limita_la_enumeracion():
	texto = d.describir_cambio("1 igual 2 igual 3 igual 4 igual 5 igual 6", "a igual b igual c igual d igual e igual f")
	assert texto.lower().count("cambia «") == 4 and texto.endswith("; y 2 cambios más.")


def test_describir_cambio_ensena_el_invisible_añadido():
	texto = d.describir_cambio("if acceso:", "if acceso:‮")
	assert texto == "Cambia «acceso:» por «acceso:<U+202E RIGHT-TO-LEFT OVERRIDE>»."


def test_explicar_linea_en_cada_tipo():
	lineas = d.aplanar(d.analizar(DIFF))
	grupos = d.grupos_de_cambios(lineas)
	por_texto = {(linea.tipo, linea.texto): i for i, linea in enumerate(lineas)}
	assert d.explicar_linea(lineas, grupos, por_texto[(d.ELIMINADA, "b = 2")]) == "La sustituye la nueva línea 2. Cambia «2» por «3»."
	assert d.explicar_linea(lineas, grupos, por_texto[(d.AÑADIDA, "b = 3")]) == "Sustituye a la antigua línea 2. Cambia «2» por «3»."
	assert d.explicar_linea(lineas, grupos, por_texto[(d.AÑADIDA, "c = 4")]).startswith("Línea nueva: no sustituye")
	assert d.explicar_linea(lineas, grupos, por_texto[(d.AÑADIDA, "z")]).endswith("Línea reescrita.")
	assert d.explicar_linea(lineas, grupos, por_texto[(d.CONTEXTO, "a = 1")]) == "Esta línea no ha cambiado."
	assert d.explicar_linea(lineas, grupos, 0).startswith("Sitúese en una línea añadida o eliminada")
	borradas = d.aplanar(d.analizar(DIFF_VARIADO))
	uno = next(i for i, linea in enumerate(borradas) if linea.texto == "uno")
	assert d.explicar_linea(borradas, d.grupos_de_cambios(borradas), uno).startswith("Línea eliminada sin sustituta")


# ════════════════════════════════════════════════════════════════════════════
# Invisibles
# ════════════════════════════════════════════════════════════════════════════


def test_hacer_visibles_controles_espacios_y_bidireccionales():
	texto = "a‮b\x1bc d​\x85\t"
	assert d.hacer_visibles(texto) == (
		"a<U+202E RIGHT-TO-LEFT OVERRIDE>b<U+001B ESCAPE>c<U+00A0 NO-BREAK SPACE>d<U+200B ZERO WIDTH SPACE>"
		"<U+0085 NEXT LINE>\t")
	assert d.hacer_visibles("normal con tabulador\t y acentos: ñandú") == "normal con tabulador\t y acentos: ñandú"
	assert d.invisibles("x⁦y⁦") == ["U+2066 LEFT-TO-RIGHT ISOLATE"]
	assert d.tiene_invisibles("﻿hola") and not d.tiene_invisibles("a\tb")


def test_aviso_breve_de_invisibles():
	assert d.aviso_invisibles("a‮b") == "Contiene caracteres invisibles que cambian la dirección del texto."
	assert d.aviso_invisibles("a​b") == "Contiene caracteres invisibles."
	assert d.aviso_invisibles("a\tb") == ""


def test_texto_visible_no_deja_filas_mudas():
	assert d.texto_visible("   ") == "(línea en blanco)"
	assert d.texto_visible(" ") == "<U+00A0 NO-BREAK SPACE>", "strip() quitaría el espacio no separable"


def test_separadores_unicode_no_parten_la_linea():
	texto = "@@ -1 +1 @@\n-a = 1\n+a = 1  # x\r\n"
	archivo = d.analizar(texto, "a.py")[0]
	assert (archivo.añadidas, archivo.eliminadas) == (1, 1)
	añadida = archivo.lineas[-1]
	assert añadida.texto == "a = 1  # x" and d.tiene_invisibles(añadida.texto)
	assert "<U+2028 LINE SEPARATOR>" in d.texto_legible([archivo])


# ════════════════════════════════════════════════════════════════════════════
# Vista narrada y resumen de la posición
# ════════════════════════════════════════════════════════════════════════════


def test_texto_narrado():
	texto = d.texto_narrado(d.analizar(DIFF))
	assert texto.startswith("2 archivos cambiados con 3 cambios")
	assert "Cambio 1 de 3, antes línea 2, ahora líneas 2 a 3:" in texto
	assert "  Cambió la línea 2: b = 2\n  Por: b = 3\n  Cambia «2» por «3».\n  Añadida la línea 3: c = 4" in texto
	assert "  Cambió la línea 11 (ahora 12): y\n  Por: z\n  Línea reescrita." in texto
	assert "Cambio 3 de 3, ahora línea 1:\n  Añadida la línea 1: hola" in texto
	assert "Eliminada la línea 1: uno" in d.texto_narrado(d.analizar(DIFF_VARIADO))
	assert d.texto_narrado([]) == "No hay diferencias."


def test_resumen_en_la_posicion():
	archivos = d.analizar(DIFF)
	lineas = d.aplanar(archivos)
	grupos = d.grupos_de_cambios(lineas)
	texto = d.resumen_en(archivos, lineas, grupos, grupos[2].inicio)
	assert texto.startswith("2 archivos cambiados con 3 cambios")
	assert "Archivo 2 de 2: nuevo.txt. Nuevo. 1 añadida." in texto and texto.endswith("Cambio 3 de 3.")


# ════════════════════════════════════════════════════════════════════════════
# Visor
# ════════════════════════════════════════════════════════════════════════════


def _ventana(texto=DIFF):
	from app.ui.detalle.diferencias import VentanaDiferencias

	ctx, _api, anuncios = crear_contexto()
	ventana = VentanaDiferencias(None, ctx, "Diferencias de prueba")
	ventana.diferencias.mostrar(texto)
	return ventana, ventana.diferencias, anuncios


def _tecla(panel, codigo, ctrl=False, mayus=False):
	evento = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
	evento.SetKeyCode(codigo)
	evento.SetControlDown(ctrl)
	evento.SetShiftDown(mayus)
	panel._al_pulsar(evento)


def test_teclado_del_visor(app_wx, marco):
	ventana, _panel, _a = _ventana()
	try:
		afirmar_teclado_correcto(ventana, teclas_propias=TECLAS_DIFF)
	finally:
		ventana.Destroy()


def test_teclas_nuevas_libres_en_la_ventana_del_pull_request(app_wx, marco):
	"""Ctrl+D, Ctrl+Mayús+D y Ctrl+Mayús+T no chocan con nada en la ventana de diferencias ni en la del pull request."""
	from app.ui.detalle.conversacion import VentanaDetalle
	from tests.test_detalle import TECLAS_CONVERSACION, _contexto_pr, _sin_errores, _ventana_pr

	VentanaDetalle._abiertas.clear()
	ctx, _api, _a = _contexto_pr()
	ventana = _ventana_pr(ctx)
	try:
		_sin_errores(ventana, [*TECLAS_CONVERSACION, "Ctrl+D", "Ctrl+Mayús+D", "Ctrl+Mayús+T", "F8", "F7", "Ctrl+G", "Ctrl+T"])
	finally:
		ventana.Destroy()
		VentanaDetalle._abiertas.clear()


def test_f8_dice_el_numero_de_cambio_y_el_archivo(app_wx, marco):
	ventana, panel, anuncios = _ventana()
	try:
		_tecla(panel, wx.WXK_F8)
		panel._decir_pendiente()
		assert anuncios[-1] == "Cambio 1 de 3."
		_tecla(panel, wx.WXK_F8)
		_tecla(panel, wx.WXK_F8)
		panel._decir_pendiente()
		assert anuncios[-1] == "Cambio 3 de 3, en nuevo.txt."
		assert panel.linea_actual().texto == "hola"
		_tecla(panel, wx.WXK_F8, mayus=True)
		panel._decir_pendiente()
		assert anuncios[-1] == "Cambio 2 de 3, en app/uno.py."
	finally:
		ventana.Destroy()


def test_ctrl_d_y_ctrl_r(app_wx, marco):
	ventana, panel, anuncios = _ventana()
	try:
		_tecla(panel, wx.WXK_F8)
		_tecla(panel, ord("D"), ctrl=True)
		assert anuncios[-1] == "La sustituye la nueva línea 2. Cambia «2» por «3»."
		_tecla(panel, ord("D"), ctrl=True, mayus=True)
		assert anuncios[-1].endswith("Archivo 1 de 2: app/uno.py. Modificado. 3 añadidas y 2 eliminadas. Cambio 1 de 3.")
	finally:
		ventana.Destroy()


def test_invisibles_en_la_fila_y_aviso_al_llegar(app_wx, marco):
	ventana, panel, anuncios = _ventana("@@ -1 +1 @@\n-ok = True\n+ok = True‮\n")
	try:
		indice = next(i for i, linea in enumerate(panel.lineas) if linea.tipo == d.AÑADIDA)
		assert "<U+202E RIGHT-TO-LEFT OVERRIDE>" in panel.lista.texto_celda(indice, panel._ids_columnas.index("texto"))
		assert panel._pendiente == "", "cargar el diff no avisa de nada"
		panel.lista.enfocar_fila(indice)
		panel._al_enfocar(_evento_foco(indice))
		panel._decir_pendiente()
		assert anuncios[-1] == "Contiene caracteres invisibles que cambian la dirección del texto."
		panel.explicar_linea()
		assert "Caracteres invisibles: U+202E RIGHT-TO-LEFT OVERRIDE." in anuncios[-1]
	finally:
		ventana.Destroy()


def _evento_foco(fila):
	evento = wx.ListEvent(wx.wxEVT_LIST_ITEM_FOCUSED)
	evento.SetIndex(fila)
	return evento


def test_ctrl_mayus_t_abre_la_vista_narrada(app_wx, marco, dialogo_modal):
	ventana, panel, _a = _ventana()
	try:
		_tecla(panel, ord("T"), ctrl=True, mayus=True)
		assert dialogo_modal.ultimo.titulo == "Diferencias narradas"
		assert any("Cambio 1 de 3" in texto for texto in dialogo_modal.ultimo.textos)
		_tecla(panel, ord("T"), ctrl=True)
		assert dialogo_modal.ultimo.titulo == "Diferencias como texto"
	finally:
		ventana.Destroy()
