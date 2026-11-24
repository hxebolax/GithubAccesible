"""Pruebas de las ventanas de detalle de Actions, releases, gists, discusiones y proyectos.

Sin red: la API es un ``MagicMock`` (``tests.apoyo_app.crear_contexto``) y las
tareas se ejecutan en el acto. Las ventanas se construyen sin mostrarse y los
diálogos modales se contestan con la fixture ``dialogo_modal``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import wx

from app.ui.accesibilidad.revision_teclado import revisar_teclado
from tests.apoyo_app import crear_contexto

# ════════════════════════════════════════════════════════════════════════════
# Utilidades
# ════════════════════════════════════════════════════════════════════════════


def errores_teclado(ventana, teclas=()) -> list[str]:
	return [str(p) for p in revisar_teclado(ventana, teclas_propias=teclas) if not p.aviso]


def buscar_control(ventana, clase, etiqueta: str | None = None):
	"""Primer control de ``clase`` (con esa etiqueta de StaticText delante, si se da)."""
	pendientes = list(ventana.GetChildren())
	anterior = None
	while pendientes:
		hijo = pendientes.pop(0)
		if isinstance(hijo, clase) and (etiqueta is None or (anterior is not None and etiqueta in anterior.GetLabel())):
			return hijo
		if isinstance(hijo, wx.StaticText):
			anterior = hijo
		pendientes[0:0] = list(hijo.GetChildren())
	return None


@pytest.fixture
def sin_mostrar(monkeypatch):
	"""Las ventanas de detalle no se muestran en las pruebas."""
	from app.ui.detalle import comun_detalle

	mostradas = []
	monkeypatch.setattr(comun_detalle.VentanaDetalle, "mostrar", lambda self, foco=None: mostradas.append(self))
	return mostradas


# ════════════════════════════════════════════════════════════════════════════
# Analizador YAML de workflow_dispatch
# ════════════════════════════════════════════════════════════════════════════

FLUJO_COMPLETO = """\
name: Publicar
# comentario inicial
on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      version:
        description: 'Versión a publicar'
        required: true
        default: "1.0"
      entorno:
        type: choice
        description: Entorno # con comentario
        options:
          - dev
          - "prod"
        default: dev
      depurar:
        type: boolean
        default: false
      notas:
        description: |
          Línea uno
          Línea dos
      destino:
        type: environment
        required: 'true'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          echo "on: esto no es la clave on"
"""


def test_yaml_entradas_completas():
	from app.ui.detalle.acciones import analizar_dispatch

	admite, entradas = analizar_dispatch(FLUJO_COMPLETO)
	assert admite
	assert [e.nombre for e in entradas] == ["version", "entorno", "depurar", "notas", "destino"]
	version, entorno, depurar, notas, destino = entradas
	assert version.descripcion == "Versión a publicar" and version.requerida and version.defecto == "1.0" and version.tipo == "string"
	assert entorno.tipo == "choice" and entorno.opciones == ["dev", "prod"] and entorno.descripcion == "Entorno"
	assert depurar.tipo == "boolean" and depurar.defecto == "false" and not depurar.requerida
	assert notas.descripcion == "Línea uno\nLínea dos"
	assert destino.tipo == "environment" and destino.requerida


@pytest.mark.parametrize("texto, admite", [
	("on: workflow_dispatch\njobs: {}\n", True),
	("on: [push, workflow_dispatch]\n", True),
	("on: [push, pull_request]\n", False),
	("'on':\n  workflow_dispatch:\n", True),
	('"on":\n  workflow_dispatch: {}\n', True),
	("on:\n  push:\n    branches:\n      - main\n", False),
	("name: sin on\njobs:\n  a:\n    runs-on: x\n", False),
	("true:\n  workflow_dispatch:\n", True),
])
def test_yaml_admite_dispatch(texto, admite):
	from app.ui.detalle.acciones import analizar_dispatch

	assert analizar_dispatch(texto) == (admite, [])


def test_yaml_opciones_en_linea_crlf_y_plegado():
	from app.ui.detalle.acciones import entradas_workflow_dispatch

	texto = (
		"on:\r\n"
		"  workflow_dispatch:\r\n"
		"    inputs:\r\n"
		"      nivel:\r\n"
		"        type: choice\r\n"
		"        options: [bajo, 'medio, alto', \"máximo\"]\r\n"
		"        default: bajo\r\n"
		"      explicacion:\r\n"
		"        description: >\r\n"
		"          Texto plegado\r\n"
		"          en dos líneas\r\n"
		"        required: false\r\n"
		"      activo:\r\n"
		"        type: boolean\r\n"
		"        default: true\r\n"
	)
	nivel, explicacion, activo = entradas_workflow_dispatch(texto)
	assert nivel.opciones == ["bajo", "medio, alto", "máximo"]
	assert explicacion.descripcion == "Texto plegado en dos líneas" and not explicacion.requerida
	assert activo.defecto == "true"


def test_yaml_secuencias_de_mapas_y_bloques():
	from app.ui.detalle.acciones import analizar_yaml

	datos = analizar_yaml(FLUJO_COMPLETO)
	pasos = datos["jobs"]["build"]["steps"]
	assert pasos[0] == {"uses": "actions/checkout@v4"}
	assert pasos[1] == {"run": 'echo "on: esto no es la clave on"'}
	assert datos["on"]["push"] == {"branches": ["main"]}


def test_asignar_letras_sin_repetir():
	from app.ui.detalle.acciones import asignar_letras
	from app.ui.accesibilidad.revision_teclado import letra_de_acceso

	etiquetas = asignar_letras(["Rama", "Lista", "Rama larga", "R&D", "123"], {"r", "l", "c"})
	letras = [letra_de_acceso(e) for e in etiquetas]
	assert None not in letras and len(set(letras)) == len(letras)
	assert not {"r", "l", "c"} & set(letras)
	assert "&&" in etiquetas[3], "un «&» del texto se escribe doble para que no sea letra de acceso"


# ════════════════════════════════════════════════════════════════════════════
# Funciones puras del registro
# ════════════════════════════════════════════════════════════════════════════

REGISTRO = (
	"2024-05-01T10:00:00.1000000Z ##[group]Run actions/checkout@v4\n"
	"2024-05-01T10:00:01.0000000Z Syncing repository\n"
	"2024-05-01T10:00:02.0000000Z ##[endgroup]\n"
	"2024-05-01T10:00:03.5000000Z ##[group]Run pytest -q\n"
	"2024-05-01T10:00:04.0000000Z \x1b[31mFAILED tests/test_x.py::test_uno\x1b[0m\n"
	"2024-05-01T10:00:05.0000000Z ##[error]Process completed with exit code 1.\n"
	"2024-05-01T10:00:06.0000000Z ##[warning]Algo raro\n"
	"2024-05-01T10:00:07.0000000Z fin del registro"
)
PASOS = [
	{"number": 1, "name": "Run actions/checkout@v4", "status": "completed", "conclusion": "success",
		"started_at": "2024-05-01T10:00:00Z", "completed_at": "2024-05-01T10:00:02Z"},
	{"number": 2, "name": "Pruebas", "status": "completed", "conclusion": "failure",
		"started_at": "2024-05-01T10:00:03Z", "completed_at": "2024-05-01T10:00:07Z"},
]


def test_marcas_busqueda_y_pasos():
	from app.services.github.api_extra import limpiar_registro
	from app.ui.detalle.acciones import buscar_linea, linea_de_paso, siguiente_marca

	limpias = limpiar_registro(REGISTRO).split("\n")
	crudas = REGISTRO.splitlines()
	assert siguiente_marca(limpias, 0) == 5 and limpias[5].startswith("ERROR:")
	assert siguiente_marca(limpias, 5) == 6
	assert siguiente_marca(limpias, 6) is None
	assert siguiente_marca(limpias, 6, atras=True) == 5
	assert buscar_linea(limpias, "failed", 0) == (4, 0, False)
	assert buscar_linea(limpias, "SYNCING", 5) == (1, 0, True)
	assert buscar_linea(limpias, "no está", 0) is None
	assert linea_de_paso(limpias, crudas, PASOS[0]) == 0, "por el nombre del grupo"
	assert linea_de_paso(limpias, crudas, PASOS[1]) == 3, "por la marca de tiempo del inicio del paso"


def test_cambios_de_estado_e_informacion():
	from app.ui.detalle.acciones import cambios_de_estado, texto_informacion

	antes = [{"id": 1, "name": "build", "status": "in_progress"}]
	despues = [{"id": 1, "name": "build", "status": "completed", "conclusion": "success"},
		{"id": 2, "name": "deploy", "status": "queued"}]
	assert cambios_de_estado(antes, despues) == ["build: En curso → Correcto.", "Nuevo trabajo deploy: En cola."]
	texto = texto_informacion({"name": "CI", "status": "completed", "conclusion": "failure", "event": "push",
		"head_branch": "main", "head_sha": "abcdef1234", "run_number": 7, "run_attempt": 2, "actor": {"login": "ana"},
		"run_started_at": "2024-05-01T10:00:00Z", "updated_at": "2024-05-01T10:02:05Z", "html_url": "https://x"})
	assert "Estado: Fallo" in texto and "Evento: envío (push)" in texto and "abcdef1" in texto
	assert "intento 2" in texto and "Duración: 2 min 5 s" in texto


# ════════════════════════════════════════════════════════════════════════════
# Ventana de una ejecución
# ════════════════════════════════════════════════════════════════════════════


def _api_ejecucion(api, estado="completed", conclusion="failure"):
	api.ejecucion.return_value = {"id": 9, "name": "CI", "status": estado, "conclusion": conclusion, "run_number": 3,
		"event": "push", "head_branch": "main", "head_sha": "abc1234", "html_url": "https://github.com/ana/repo/actions/runs/9"}
	api.trabajos.return_value = [
		{"id": 11, "name": "lint", "status": "completed", "conclusion": "success", "steps": PASOS[:1]},
		{"id": 12, "name": "pruebas", "status": "completed", "conclusion": "failure", "steps": PASOS},
	]
	api.artefactos.return_value = [{"id": 21, "name": "informe", "size_in_bytes": 2048, "expired": False,
		"expires_at": "2030-01-01T00:00:00Z"}]
	api.anotaciones_check.return_value = [{"path": "tests/test_x.py", "start_line": 4, "annotation_level": "failure",
		"message": "assert 1 == 2", "title": "Fallo"}]
	api.registro_trabajo.return_value = REGISTRO


def test_ventana_ejecucion_carga_y_navega(app_wx, marco):
	from app.ui.detalle.acciones import VentanaEjecucion

	ctx, api, anuncios = crear_contexto()
	_api_ejecucion(api)
	ventana = VentanaEjecucion(ctx, marco, "ana/repo", 9)
	ventana.cargar()
	assert ventana.lista_trabajos.numero_filas() == 2
	assert ventana.trabajo["name"] == "pruebas", "empieza en el trabajo fallido"
	assert ventana.lista_pasos.numero_filas() == 2
	assert ventana.lista_artefactos.texto_celda(0, 0) == "informe"
	assert ventana.lista_anotaciones.texto_celda(0, 1) == "tests/test_x.py:4"
	assert ventana.lista_anotaciones.texto_celda(0, 0) == "Error"
	texto = ventana.registro.GetValue()
	assert "\x1b" not in texto and "2024-05-01T" not in texto and "▸ Run pytest -q" in texto
	assert not ventana.temporizador.IsRunning(), "terminada: no se sigue en vivo"

	ventana.registro.SetInsertionPoint(0)
	ventana.saltar_marca()
	assert ventana.linea_actual() == 5 and anuncios[-1].startswith("ERROR: Process completed")
	ventana.saltar_marca()
	assert anuncios[-1] == "AVISO: Algo raro"
	ventana.saltar_marca()
	assert anuncios[-1] == "No hay más errores ni avisos." and "vacio" in ctx.sonidos.eventos
	ventana.saltar_marca(atras=True)
	assert ventana.linea_actual() == 5

	ventana.lista_pasos.enfocar_fila(1, anunciar=False)
	ventana.ir_al_paso()
	assert ventana.linea_actual() == 3 and anuncios[-1] == "▸ Run pytest -q"

	ventana.buscado = "failed"
	ventana.buscar_siguiente()
	assert ventana.linea_actual() == 4
	desde, hasta = ventana.registro.GetSelection()
	assert ventana.registro.GetRange(desde, hasta).lower() == "failed"

	ventana.casilla_horas.SetValue(True)
	ventana._rehacer_registro()
	assert "2024-05-01T10:00:04" in ventana.registro.GetValue()
	assert ctx.config.obtener("acciones.mostrar_horas") is True


def test_ventana_ejecucion_en_vivo_anuncia_y_suena(app_wx, marco):
	from app.ui.detalle.acciones import VentanaEjecucion

	ctx, api, anuncios = crear_contexto()
	_api_ejecucion(api, estado="in_progress", conclusion=None)
	api.trabajos.return_value = [{"id": 12, "name": "pruebas", "status": "in_progress", "steps": []}]
	ventana = VentanaEjecucion(ctx, marco, "ana/repo", 9)
	ventana.cargar()
	assert ventana.casilla_vivo.GetValue() and ventana.temporizador.IsRunning()
	_api_ejecucion(api)  # en el siguiente sondeo ya ha terminado con fallo
	api.trabajos.return_value = [{"id": 12, "name": "pruebas", "status": "completed", "conclusion": "failure", "steps": PASOS}]
	ventana._al_temporizador()
	assert "pruebas: En curso → Fallo." in anuncios
	assert "Ejecución terminada: Fallo." in anuncios
	assert "accion_fallo" in ctx.sonidos.eventos
	assert not ventana.temporizador.IsRunning() and not ventana.casilla_vivo.GetValue()
	ventana.Close()
	assert ventana.cerrada and "cerrar" in ctx.sonidos.eventos


def test_ventana_ejecucion_acciones_y_artefactos(app_wx, marco, dialogo_modal, tmp_path):
	from app.ui.detalle.acciones import VentanaEjecucion

	ctx, api, _anuncios = crear_contexto()
	_api_ejecucion(api)
	api.url_artefacto.return_value = "https://api.github.com/repos/ana/repo/actions/artifacts/21/zip"
	api.c.url.side_effect = lambda ruta: "https://api.github.com" + ruta
	api.c.descargar.side_effect = lambda url, destino, **k: destino
	ctx.config.establecer("general.carpeta_descargas", str(tmp_path))
	ventana = VentanaEjecucion(ctx, marco, "ana/repo", 9)
	ventana.cargar()

	ventana.descargar_artefacto()
	# Va al gestor de descargas de la aplicación: sigue aunque se cierre la ventana.
	artefacto = ctx.descargas.pedidas[-1]
	assert artefacto.url.endswith("/artifacts/21/zip") and artefacto.destino == str(tmp_path / "informe.zip")
	assert artefacto.aceptar == "application/vnd.github+json" and artefacto.cuenta and artefacto.origen

	ventana.descargar_registros()
	assert ctx.descargas.pedidas[-1].url.endswith("/repos/ana/repo/actions/runs/9/logs")

	ventana.volver_a_ejecutar(solo_fallidos=True)
	api.volver_a_ejecutar.assert_called_with("ana/repo", 9, True, False)

	dialogo_modal.responder(wx.ID_YES)
	ventana.borrar_artefacto()
	api.borrar_artefacto.assert_called_with("ana/repo", 21)
	assert ventana.lista_artefactos.numero_filas() == 0

	api.despliegues_pendientes.return_value = [{"environment": {"id": 5, "name": "produccion"}, "current_user_can_approve": True}]
	dialogo_modal.responder(wx.ID_OK)  # elegir_varios con todo marcado
	dialogo_modal.responder(lambda d: d.ids_opciones[0])  # «Aprobar»
	dialogo_modal.responder(wx.ID_OK)  # comentario vacío
	ventana.revisar_despliegues()
	api.revisar_despliegue.assert_called_with("ana/repo", 9, [5], True, "")


def test_ventana_ejecucion_teclado(app_wx, marco):
	from app.ui.detalle.acciones import VentanaEjecucion

	ctx, api, _a = crear_contexto()
	ventana = VentanaEjecucion(ctx, marco, "ana/repo", 9)
	assert errores_teclado(ventana, ["Supr", "Shift+Intro"]) == []
	hijos = list(ventana.panel.GetChildren())
	for control in (ventana.lista_trabajos, ventana.lista_pasos, ventana.registro, ventana.lista_artefactos):
		assert isinstance(hijos[hijos.index(control) - 1], wx.StaticText), "etiqueta justo antes"
		assert control.GetHelpText()


def test_abrir_ejecucion_registra_la_ventana(app_wx, marco, sin_mostrar):
	from app.ui.detalle.acciones import abrir_ejecucion
	from app.ui.detalle.comun_detalle import VentanaDetalle

	ctx, api, _a = crear_contexto()
	_api_ejecucion(api)
	ventana = abrir_ejecucion(ctx, marco, "ana/repo", 9)
	assert sin_mostrar == [ventana] and VentanaDetalle._abiertas["ejecucion:ana/repo:9"] is ventana
	ventana.Close()
	assert "ejecucion:ana/repo:9" not in VentanaDetalle._abiertas


# ════════════════════════════════════════════════════════════════════════════
# Lanzar un flujo
# ════════════════════════════════════════════════════════════════════════════


def _api_flujo(api, yaml=FLUJO_COMPLETO):
	api.leer_archivo.return_value = (yaml.encode("utf-8"), "sha")
	api.todas_las_ramas.return_value = [{"name": "main"}, {"name": "desarrollo"}]
	api.repositorio.return_value = {"default_branch": "main"}
	api.entornos.return_value = [{"name": "produccion"}, {"name": "pruebas"}]


def test_lanzar_flujo_con_entradas(app_wx, marco, dialogo_modal):
	from app.ui.detalle.acciones import DialogoLanzarFlujo, lanzar_flujo

	ctx, api, anuncios = crear_contexto()
	_api_flujo(api)

	def rellenar(dialogo: DialogoLanzarFlujo):
		assert errores_teclado(dialogo) == []
		assert isinstance(dialogo.controles[1], wx.Choice) and isinstance(dialogo.controles[2], wx.CheckBox)
		assert isinstance(dialogo.controles[4], wx.Choice), "environment con la lista de entornos"
		dialogo.selector_rama.SetSelection(1)
		dialogo.controles[0].SetValue("2.0")
		dialogo.controles[1].SetSelection(1)
		dialogo.controles[2].SetValue(True)
		return wx.ID_OK

	dialogo_modal.responder(rellenar)
	lanzar_flujo(ctx, marco, "ana/repo", {"id": 77, "name": "Publicar", "path": ".github/workflows/publicar.yml"})
	api.leer_archivo.assert_called_with("ana/repo", ".github/workflows/publicar.yml")
	api.lanzar_flujo.assert_called_once()
	nombre, id_flujo, rama, entradas = api.lanzar_flujo.call_args.args
	assert (nombre, id_flujo, rama) == ("ana/repo", 77, "desarrollo")
	assert entradas == {"version": "2.0", "entorno": "prod", "depurar": "true", "notas": "", "destino": "produccion"}
	assert any("lanzado" in a for a in anuncios)


def test_lanzar_flujo_valida_obligatorios(app_wx, marco):
	from app.ui.detalle.acciones import DialogoLanzarFlujo, EntradaFlujo

	dialogo = DialogoLanzarFlujo(marco, "CI", ["main"], "main", [EntradaFlujo("version", requerida=True),
		EntradaFlujo("veces", tipo="number", defecto="x")])
	try:
		mensaje, control = dialogo.comprobar()
		assert "obligatoria" in mensaje and control is dialogo.controles[0]
		dialogo.controles[0].SetValue("1")
		assert "número" in dialogo.comprobar()[0]
		dialogo.controles[1].SetValue("3")
		assert dialogo.comprobar() == ("", None)
	finally:
		dialogo.Destroy()


def test_lanzar_flujo_sin_dispatch_avisa(app_wx, marco, dialogo_modal):
	from app.ui.detalle.acciones import lanzar_flujo

	ctx, api, _a = crear_contexto()
	_api_flujo(api, "on:\n  push:\n")
	lanzar_flujo(ctx, marco, "ana/repo", {"id": 1, "name": "CI", "path": "ci.yml"})
	assert "workflow_dispatch" in " ".join(dialogo_modal.ultimo.textos)
	api.lanzar_flujo.assert_not_called()


def test_lanzar_flujo_elige_el_flujo(app_wx, marco, dialogo_modal):
	from app.ui.detalle.acciones import lanzar_flujo

	ctx, api, _a = crear_contexto()
	_api_flujo(api, "on: workflow_dispatch\n")
	api.flujos.return_value = [{"id": 1, "name": "CI", "path": "a.yml", "state": "active"},
		{"id": 2, "name": "Nocturno", "path": "b.yml", "state": "disabled_manually"}]

	def elegir(dialogo):
		dialogo.lista.SetSelection(1)
		return wx.ID_OK

	dialogo_modal.responder(elegir, wx.ID_OK)
	lanzar_flujo(ctx, marco, "ana/repo")
	assert api.lanzar_flujo.call_args.args[:3] == ("ana/repo", 2, "main")


# ════════════════════════════════════════════════════════════════════════════
# Releases
# ════════════════════════════════════════════════════════════════════════════

RELEASE = {"id": 5, "tag_name": "v1.0", "name": "Primera", "body": "## Novedades\n- Todo", "draft": False, "prerelease": False,
	"html_url": "https://github.com/ana/repo/releases/tag/v1.0", "upload_url": "https://uploads.github.com/repos/ana/repo/releases/5/assets{?name,label}",
	"author": {"login": "ana"}, "assets": [{"id": 31, "name": "app.zip", "size": 4096, "download_count": 12, "created_at": "2024-01-01T00:00:00Z"}]}


def test_ventana_release_muestra_y_teclado(app_wx, marco):
	from app.ui.detalle.releases import VentanaRelease

	ctx, api, _a = crear_contexto()
	ventana = VentanaRelease(ctx, marco, "ana/repo", RELEASE)
	assert "Etiqueta: v1.0" in ventana.info.GetValue() and "Publicada" in ventana.info.GetValue()
	assert ventana.notas.GetValue().startswith("## Novedades")
	assert ventana.lista.texto_celda(0, 0) == "app.zip" and ventana.lista.texto_celda(0, 2) == "12"
	assert errores_teclado(ventana, ["Supr", "F2", "Shift+Intro"]) == []
	api.release.return_value = dict(RELEASE, name="Primera (editada)")
	api.recursos.return_value = RELEASE["assets"]
	api.ultima_release.return_value = {"id": 5}
	ventana.cargar()
	assert ventana.es_ultima and "es la última release" in ventana.info.GetValue()
	assert "Primera (editada)" in ventana.GetTitle()


def test_release_descargar_subir_renombrar_borrar(app_wx, marco, dialogo_modal, tmp_path):
	from app.ui.detalle.releases import VentanaRelease

	ctx, api, _a = crear_contexto()
	api.url_descarga_recurso.return_value = "https://api.github.com/repos/ana/repo/releases/assets/31"
	api.c.descargar.side_effect = lambda url, destino, **k: destino
	api.recursos.return_value = RELEASE["assets"]
	api.release.return_value = RELEASE
	ctx.config.establecer("general.carpeta_descargas", str(tmp_path))
	ventana = VentanaRelease(ctx, marco, "ana/repo", RELEASE)

	ventana.descargar_recurso()
	recurso = ctx.descargas.pedidas[-1]
	assert recurso.destino == str(tmp_path / "app.zip") and recurso.aceptar == "application/octet-stream"

	archivos = []
	for nombre in ("uno.txt", "dos.bin"):
		ruta = tmp_path / nombre
		ruta.write_bytes(b"x")
		archivos.append(str(ruta))
	ventana.subir(archivos)
	assert api.c.subir.call_count == 2
	assert api.c.subir.call_args_list[0].args[:2] == (RELEASE["upload_url"], Path(archivos[0]))
	assert api.c.subir.call_args_list[0].kwargs["tipo"] == "text/plain"

	def renombrar(dialogo):
		dialogo.campo.SetValue("app-1.0.zip")
		return wx.ID_OK

	api.editar_recurso.return_value = {"id": 31, "name": "app-1.0.zip"}
	dialogo_modal.responder(renombrar)
	ventana.renombrar_recurso()
	api.editar_recurso.assert_called_with("ana/repo", 31, nombre_archivo="app-1.0.zip")
	assert ventana.lista.texto_celda(0, 0) == "app-1.0.zip"

	dialogo_modal.responder(wx.ID_YES)
	ventana.borrar_recurso()
	api.borrar_recurso.assert_called_with("ana/repo", 31)
	assert ventana.lista.numero_filas() == 0


def test_release_editar_con_casillas(app_wx, marco, dialogo_modal):
	from app.ui.detalle.releases import VentanaRelease

	ctx, api, _a = crear_contexto()
	api.editar_release.return_value = dict(RELEASE, name="Nueva", prerelease=True)
	api.release.return_value = dict(RELEASE, name="Nueva", prerelease=True)
	api.recursos.return_value = RELEASE["assets"]
	api.ultima_release.side_effect = RuntimeError("404: sin releases publicadas")
	ventana = VentanaRelease(ctx, marco, "ana/repo", RELEASE)

	def editar(dialogo):
		assert errores_teclado(dialogo) == []
		dialogo.campo_titulo.SetValue("Nueva")
		dialogo.controles_extra["prelanzamiento"].SetValue(True)
		dialogo._al_aceptar(None)
		return wx.ID_OK

	dialogo_modal.responder(editar)
	ventana.editar()
	kwargs = api.editar_release.call_args.kwargs
	assert kwargs["name"] == "Nueva" and kwargs["prerelease"] is True and "make_latest" not in kwargs
	assert "Prelanzamiento" in ventana.info.GetValue()


def test_nueva_release_crea_y_ofrece_subir(app_wx, marco, dialogo_modal):
	from app.services.github.cliente import Pagina
	from app.ui.detalle.releases import DialogoNuevaRelease, nueva_release

	ctx, api, _a = crear_contexto()
	api.etiquetas_git.return_value = Pagina([{"name": "v0.9"}])
	api.todas_las_ramas.return_value = [{"name": "main"}]
	api.repositorio.return_value = {"default_branch": "main"}
	api.generar_notas.return_value = {"name": "v1.0", "body": "Cambios generados"}
	api.crear_release.return_value = dict(RELEASE)
	creadas = []

	def rellenar(dialogo: DialogoNuevaRelease):
		assert errores_teclado(dialogo, ["Ctrl+Intro", "F7"]) == []
		assert dialogo.campo_destino.GetValue() == "main" and dialogo.campo_etiqueta.GetCount() == 1
		dialogo.campo_etiqueta.SetValue("v1.0")
		dialogo.generar_notas()
		assert dialogo.campo_notas.GetValue() == "Cambios generados" and dialogo.campo_titulo.GetValue() == "v1.0"
		dialogo.casilla_borrador.SetValue(True)
		dialogo.crear()
		return wx.ID_OK

	dialogo_modal.responder(rellenar, wx.ID_NO)  # después: «¿Subir archivos ahora?» → No
	nueva_release(marco, ctx, "ana/repo", al_crear=creadas.append)
	api.generar_notas.assert_called_with("ana/repo", "v1.0", rama="main")
	args = api.crear_release.call_args
	assert args.args[:5] == ("ana/repo", "v1.0", "v1.0", "Cambios generados", "main")
	assert args.args[5] is True and args.kwargs["ultima"] == "false", "un borrador nunca es la última"
	assert creadas == [RELEASE]


def test_nueva_release_no_se_cierra_si_falla(app_wx, marco, dialogo_modal):
	from app.ui.detalle.releases import DialogoNuevaRelease

	ctx, api, _a = crear_contexto()
	api.crear_release.side_effect = RuntimeError("La etiqueta ya existe")
	dialogo = DialogoNuevaRelease(marco, ctx, "ana/repo", ["v0.9"], ["main"], "main")
	try:
		dialogo.campo_etiqueta.SetValue("v0.9")
		dialogo.campo_notas.SetValue("Texto valioso")
		dialogo.crear()
		assert dialogo.resultado is None and dialogo.boton_crear.IsEnabled()
		assert dialogo.campo_notas.GetValue() == "Texto valioso"
		assert "La etiqueta ya existe" in " ".join(dialogo_modal.ultimo.textos)
		assert api.crear_release.call_args.args[4] == "", "una etiqueta existente no lleva destino"
	finally:
		dialogo.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Gists
# ════════════════════════════════════════════════════════════════════════════

GIST = {"id": "abc", "description": "Mis notas", "public": False, "owner": {"login": "ana"}, "comments": 1,
	"html_url": "https://gist.github.com/abc", "git_pull_url": "https://gist.github.com/abc.git",
	"files": {"a.md": {"content": "# Hola", "language": "Markdown", "size": 6}, "b.py": {"content": "print(1)", "language": "Python", "size": 8}}}


def test_ventana_gist(app_wx, marco, dialogo_modal):
	from app.ui.detalle.gist import VentanaGist

	ctx, api, _a = crear_contexto()
	api.gist.return_value = GIST
	ventana = VentanaGist(ctx, marco, "abc")
	ventana.cargar()
	assert ventana.lista.numero_filas() == 2 and ventana.contenido.GetValue() == "# Hola"
	assert "Secreto" in ventana.info.GetValue()
	ventana.lista.enfocar_fila(1, anunciar=False)
	ventana._mostrar_contenido()
	assert ventana.contenido.GetValue() == "print(1)"
	assert errores_teclado(ventana, ["Supr", "F2"]) == []

	def renombrar(dialogo):
		dialogo.campo.SetValue("c.py")
		return wx.ID_OK

	api.editar_gist.return_value = dict(GIST, files={"a.md": GIST["files"]["a.md"], "c.py": GIST["files"]["b.py"]})
	dialogo_modal.responder(renombrar)
	ventana.renombrar_archivo()
	api.editar_gist.assert_called_with("abc", {}, renombrar={"b.py": "c.py"})
	assert ventana.nombres == ["a.md", "c.py"]

	api.tiene_estrella_gist.return_value = False
	ventana.estrella()
	api.estrella_gist.assert_called_with("abc", True)

	ventana.copiar_url_clonar()
	assert "copiado" in ctx.sonidos.eventos


def test_gist_ajeno_no_se_edita(app_wx, marco):
	from app.ui.detalle.gist import VentanaGist

	ctx, api, anuncios = crear_contexto()
	ventana = VentanaGist(ctx, marco, "abc")
	ventana.poner_gist(dict(GIST, owner={"login": "otra"}))
	ventana.borrar_archivo()
	api.editar_gist.assert_not_called()
	assert "bifurcarlo" in anuncios[-1]


def test_gist_comentarios(app_wx, marco, dialogo_modal):
	from app.ui.detalle.gist import DialogoComentariosGist

	ctx, api, _a = crear_contexto()
	dialogo = DialogoComentariosGist(marco, ctx, "abc", [{"id": 1, "user": {"login": "bea"}, "body": "Muy útil\nGracias",
		"created_at": "2024-01-01T00:00:00Z"}])
	try:
		assert errores_teclado(dialogo, ["Supr"]) == []
		assert dialogo.texto.GetValue() == "Muy útil\nGracias"
		dialogo_modal.responder(wx.ID_YES)
		dialogo.borrar()
		api.borrar_comentario_gist.assert_called_with("abc", 1)
		assert dialogo.lista.numero_filas() == 0
	finally:
		dialogo.Destroy()


def test_nuevo_gist_varios_archivos(app_wx, marco, dialogo_modal, tmp_path):
	from app.ui.detalle.gist import DialogoNuevoGist, nuevo_gist

	ctx, api, _a = crear_contexto()
	api.crear_gist.return_value = {"id": "nuevo"}
	(tmp_path / "datos.csv").write_text("a;b\n1;2", encoding="utf-8")
	(tmp_path / "binario.bin").write_bytes(b"\x00\x01")
	creados = []

	def rellenar(dialogo: DialogoNuevoGist):
		assert errores_teclado(dialogo, ["Ctrl+Intro"]) == []
		dialogo.campo_descripcion.SetValue("Ejemplo")
		dialogo.selector_visibilidad.SetSelection(1)
		dialogo.campo_nombre.SetValue("leeme.md")
		dialogo.campo_contenido.SetValue("# Ejemplo")
		dialogo.anadir_archivo()
		assert dialogo.comprobar()[0] == "El archivo 2 no tiene nombre."
		dialogo.quitar_archivo()
		dialogo_modal.responder(wx.ID_OK)  # aviso del archivo binario
		dialogo.cargar_desde_disco([str(tmp_path / "datos.csv"), str(tmp_path / "binario.bin")])
		assert dialogo.lista_archivos.GetCount() == 2
		dialogo.lista_archivos.SetSelection(0)
		dialogo._al_elegir_archivo()
		assert dialogo.campo_nombre.GetValue() == "leeme.md"
		dialogo.crear()
		return wx.ID_OK

	dialogo_modal.responder(rellenar)
	resultado = nuevo_gist(marco, ctx, al_crear=creados.append)
	api.crear_gist.assert_called_with({"leeme.md": "# Ejemplo", "datos.csv": "a;b\n1;2"}, "Ejemplo", True)
	assert resultado == {"id": "nuevo"} and creados == [resultado]


# ════════════════════════════════════════════════════════════════════════════
# Discusiones
# ════════════════════════════════════════════════════════════════════════════

DISCUSION = {
	"id": "D1", "number": 4, "title": "¿Cómo se usa?", "body": "Pregunta", "url": "https://github.com/ana/repo/discussions/4",
	"createdAt": "2024-01-01T00:00:00Z", "closed": False, "isAnswered": True, "upvoteCount": 3, "author": {"login": "ana"},
	"category": {"name": "Preguntas"},
	"comments": {"nodes": [
		{"id": "C1", "body": "Así", "isAnswer": True, "upvoteCount": 2, "author": {"login": "bea"}, "createdAt": "2024-01-02T00:00:00Z",
			"replies": {"nodes": [{"id": "R1", "body": "¡Gracias!", "author": {"login": "ana"}, "createdAt": "2024-01-03T00:00:00Z"}]}},
		{"id": "C2", "body": "Otra idea", "isAnswer": False, "upvoteCount": 0, "author": {"login": "eva"}, "createdAt": "2024-01-04T00:00:00Z",
			"replies": {"nodes": []}},
	]},
}


def test_discusion_estructura_y_acciones(app_wx, marco, dialogo_modal):
	from app.ui.detalle.discusiones import VentanaDiscusion, elementos_discusion, markdown_discusion, tipo_elemento

	elementos = elementos_discusion(DISCUSION)
	assert [e["nodo"]["id"] for e in elementos] == ["D1", "C1", "R1", "C2"]
	assert [tipo_elemento(e) for e in elementos] == ["Publicación original", "Comentario, respuesta marcada",
		"Respuesta a bea", "Comentario"]
	assert "### Respuesta a bea: ana" in markdown_discusion(DISCUSION)

	ctx, api, anuncios = crear_contexto()
	api.discusion.return_value = DISCUSION
	ventana = VentanaDiscusion(ctx, marco, "ana/repo", 4)
	ventana.cargar()
	assert ventana.lista.numero_filas() == 4 and "Respuesta marcada: Sí" in ventana.info.GetValue()
	assert errores_teclado(ventana) == []
	ventana.lista.enfocar_fila(2, anunciar=False)
	ventana._mostrar_texto()
	assert "¡Gracias!" in ventana.texto.GetValue()
	ventana.marcar_respuesta()
	assert "principal" in anuncios[-1]
	api.marcar_respuesta.assert_not_called()

	ventana.lista.enfocar_fila(3, anunciar=False)
	ventana.marcar_respuesta()
	api.marcar_respuesta.assert_called_with("C2", True)

	api.c.graphql.return_value = {"node": {"viewerHasUpvoted": True}}
	ventana.votar()
	api.votar.assert_called_with("C2", quitar=True)
	assert ventana.elemento["nodo"]["id"] == "C2", "el foco vuelve al mismo comentario tras recargar"

	def responder(dialogo):
		assert "Otra idea" in dialogo.campo_contexto.GetValue()
		dialogo.campo_cuerpo.SetValue("Respuesta")
		dialogo._al_aceptar(None)
		return wx.ID_OK

	api.comentar_discusion.return_value = {"id": "R9"}
	dialogo_modal.responder(responder)
	ventana.responder()
	api.comentar_discusion.assert_called_with("D1", "Respuesta", responde_a="C2")

	dialogo_modal.responder(lambda d: (d.lista.SetSelection(1), wx.ID_OK)[1])
	ventana.cerrar_discusion()
	api.cerrar_discusion.assert_called_with("D1", "OUTDATED")


# ════════════════════════════════════════════════════════════════════════════
# Proyectos
# ════════════════════════════════════════════════════════════════════════════

CAMPOS = [
	{"id": "F0", "name": "Title", "dataType": "TITLE"},
	{"id": "F1", "name": "Status", "dataType": "SINGLE_SELECT", "options": [{"id": "O1", "name": "Por hacer"},
		{"id": "O2", "name": "En curso"}, {"id": "O3", "name": "Hecho"}]},
	{"id": "F2", "name": "Puntos", "dataType": "NUMBER"},
	{"id": "F3", "name": "Iteración", "dataType": "ITERATION", "configuration": {"iterations": [{"id": "I1", "title": "Sprint 1",
		"startDate": "2024-01-01"}]}},
]


def _elemento(id_, titulo, estado=None, tipo="ISSUE", numero=1):
	valores = [{"name": estado, "field": {"name": "Status"}}] if estado else []
	return {"id": id_, "type": tipo, "isArchived": False, "fieldValues": {"nodes": valores},
		"content": {"title": titulo, "number": numero, "url": f"https://github.com/ana/repo/issues/{numero}",
			"repository": {"nameWithOwner": "ana/repo"}}}


def test_proyecto_funciones_puras():
	from app.ui.detalle.proyectos import campo_de_grupo, ordenar_por_grupo, poner_valor, referencia_issue, valor_campo

	elemento = _elemento("A", "Uno", "En curso")
	poner_valor(elemento, "Puntos", "number", 3.0)
	assert valor_campo(elemento, "Status") == "En curso" and valor_campo(elemento, "Puntos") == "3"
	poner_valor(elemento, "Status", "name", None)
	assert valor_campo(elemento, "Status") == ""
	grupo = campo_de_grupo(CAMPOS)
	assert grupo["id"] == "F1"
	orden = ordenar_por_grupo([_elemento("A", "a"), _elemento("B", "b", "Hecho"), _elemento("C", "c", "Por hacer")], grupo)
	assert [e["id"] for e in orden] == ["C", "B", "A"]
	assert referencia_issue("https://github.com/ana/repo/pull/12") == ("ana/repo", 12)
	assert referencia_issue("ana/repo#7") == ("ana/repo", 7)
	assert referencia_issue("no vale") is None


def test_ventana_proyecto_carga_mueve_filtra(app_wx, marco, dialogo_modal):
	from app.ui.detalle.proyectos import VentanaProyecto

	ctx, api, anuncios = crear_contexto()
	api.campos_proyecto.return_value = CAMPOS
	paginas = {None: ([_elemento("A", "Uno", "Por hacer"), _elemento("B", "Dos", "Hecho", numero=2)], "cursor1"),
		"cursor1": ([_elemento("C", "Borrador", tipo="DRAFT_ISSUE")], None)}
	api.elementos_proyecto.side_effect = lambda id_, n, cursor: paginas[cursor]
	ventana = VentanaProyecto(ctx, marco, {"id": "P1", "number": 1, "title": "Hoja de ruta", "url": "https://github.com/users/ana/projects/1"})
	ventana.cargar()
	assert ventana.lista.numero_filas() == 3, "se cargan todas las páginas por cursor"
	assert [ventana.lista.GetColumn(i).GetText() for i in range(ventana.lista.GetColumnCount())] == [
		"Título", "Tipo", "Repositorio", "Status", "Puntos", "Iteración"]
	assert ventana.lista.texto_celda(2, 1) == "Borrador"
	assert errores_teclado(ventana, ["Supr"]) == []

	ventana.lista.enfocar_fila(0, anunciar=False)
	dialogo_modal.responder(lambda d: (d.lista.SetSelection(1), wx.ID_OK)[1])
	ventana.mover_a()
	api.cambiar_campo.assert_called_with("P1", "A", "F1", {"singleSelectOptionId": "O2"})
	assert ventana.lista.texto_celda(0, 3) == "En curso" and "Movido a En curso." in anuncios

	ventana.alternar_agrupado()
	assert [e["id"] for e in ventana.visibles] == ["A", "B", "C"]
	assert ventana.elemento["id"] == "A", "el foco sigue en el mismo elemento"
	ventana.saltar_grupo()
	assert ventana.elemento["id"] == "B" and anuncios[-1] == "Hecho: Dos"

	def puntos(dialogo):
		dialogo.campo.SetValue("5")
		return wx.ID_OK

	dialogo_modal.responder(lambda d: (d.lista.SetSelection(1), wx.ID_OK)[1], puntos)
	ventana.cambiar_campo()
	api.cambiar_campo.assert_called_with("P1", "B", "F2", {"number": 5.0})

	dialogo_modal.responder(lambda d: (d.lista.SetSelection(1), wx.ID_OK)[1], lambda d: (d.lista.SetSelection(2), wx.ID_OK)[1])
	ventana.filtrar()
	assert [e["id"] for e in ventana.visibles] == ["B"]
	ventana.quitar_filtro()
	assert len(ventana.visibles) == 3

	api.id_de_nodo.return_value = "NODO"
	api.anadir_a_proyecto.return_value = "A"

	def referencia(dialogo):
		dialogo.campo.SetValue("ana/repo#9")
		return wx.ID_OK

	dialogo_modal.responder(referencia)
	ventana.anadir_issue()
	api.id_de_nodo.assert_called_with("ana/repo", 9)
	api.anadir_a_proyecto.assert_called_with("P1", "NODO")

	ventana.lista.enfocar_fila(0, anunciar=False)
	quitado = ventana.elemento["id"]
	dialogo_modal.responder(wx.ID_YES)
	ventana.borrar()
	api.borrar_elemento.assert_called_with("P1", quitado)
	assert quitado not in [e["id"] for e in ventana.visibles]


def test_abrir_proyecto_y_release_y_gist_y_discusion(app_wx, marco, sin_mostrar):
	from app.ui.detalle.discusiones import abrir_discusion
	from app.ui.detalle.gist import abrir_gist
	from app.ui.detalle.proyectos import abrir_proyecto
	from app.ui.detalle.releases import abrir_release

	ctx, api, _a = crear_contexto()
	api.campos_proyecto.return_value = CAMPOS
	api.elementos_proyecto.return_value = ([], None)
	api.release.return_value = RELEASE
	api.recursos.return_value = []
	api.gist.return_value = GIST
	api.discusion.return_value = DISCUSION
	ventanas = [abrir_proyecto(ctx, marco, {"id": "P1", "title": "Hoja"}), abrir_release(ctx, marco, "ana/repo", RELEASE),
		abrir_gist(ctx, marco, "abc"), abrir_discusion(ctx, marco, "ana/repo", 4)]
	assert sin_mostrar == ventanas
	assert all(isinstance(v, wx.Frame) for v in ventanas)
	for ventana in ventanas:
		ventana.Close()
