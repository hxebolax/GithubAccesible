"""Pruebas de las ventanas de git (git REAL en tmp_path, sin red ni ventanas visibles)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest import mock

import pytest
import wx

from app.services import conflictos as c
from app.services import git_local as g
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto
from app.ui.git import operaciones as op
from app.ui.git.progreso_red import SeguidorProgreso, analizar_linea
from tests.apoyo_app import crear_contexto

requiere_git = pytest.mark.skipif(not g.git_disponible(), reason="git no está instalado")


def _repo(tmp_path: Path, nombre: str = "repo") -> g.RepositorioLocal:
	carpeta = tmp_path / nombre
	g.iniciar(carpeta)
	repo = g.RepositorioLocal(carpeta)
	for clave, valor in (("user.name", "Prueba"), ("user.email", "prueba@example.com"), ("commit.gpgsign", "false"),
		("core.autocrlf", "false"), ("merge.conflictStyle", "merge")):
		repo.establecer_config(clave, valor)
	return repo


def _commit(repo: g.RepositorioLocal, archivo: str, texto: str, mensaje: str) -> None:
	(repo.carpeta / archivo).write_bytes(texto.encode("utf-8"))
	repo.preparar_todo()
	repo.confirmar(mensaje)


def _rama(repo: g.RepositorioLocal, nombre: str) -> g.Rama:
	return next(r for r in repo.ramas() if r.nombre == nombre)


def _ventana(ctx, repo, marco):
	from app.ui.git.ventana_git import VentanaGit

	return VentanaGit(ctx, str(repo.carpeta), padre=marco)


# ════════════════════════════════════════════════════════════════════════════
# Funciones sin wx
# ════════════════════════════════════════════════════════════════════════════


def test_urls_y_nombres():
	assert op.normalizar_url("ana/proyecto") == "https://github.com/ana/proyecto.git"
	assert op.normalizar_url("ana/proyecto", "ssh") == "git@github.com:ana/proyecto.git"
	assert op.normalizar_url("https://github.com/ana/proyecto", "ssh") == "git@github.com:ana/proyecto.git"
	assert op.normalizar_url(r"C:\repos\local.git") == r"C:\repos\local.git"
	assert op.nombre_github("git@github.com:ana/proyecto.git") == "ana/proyecto"
	assert op.nombre_github("ssh://git@github.com/ana/proyecto.git") == "ana/proyecto"
	assert op.nombre_github("https://gitlab.com/ana/proyecto.git") == ""
	assert op.nombre_carpeta("https://github.com/ana/proyecto.git") == "proyecto"
	assert op.nombre_carpeta(r"C:\x\desnudo.git") == "desnudo"


def test_textos_de_git_en_espanol():
	assert op.describir_seguimiento("[ahead 2, behind 1]") == "2 por delante, 1 por detrás"
	assert op.describir_seguimiento("[gone]") == "la rama remota ya no existe"
	assert op.describir_commit_creado("[main (root-commit) abc1234] Primero\n 1 file") == "Commit abc1234 creado en main: Primero."
	assert op.linea_gitignore("src\\datos\\a.log", "extension") == "*.log"
	assert op.linea_gitignore("src/datos/a.log", "carpeta") == "/src/datos/"
	assert op.linea_gitignore("a.log") == "/a.log"
	assert op.analizar_worktree(r"C:/x/repo  1234abc [main]") == {"carpeta": "C:/x/repo", "sha": "1234abc", "rama": "main"}
	assert op.analizar_submodulo("-1234567890abcdef libs/uno")["estado"] == "sin inicializar"
	assert op.analizar_submodulo("1234567890abcdef libs/dos (v1.0)")["descripcion"] == "v1.0"
	assert op.analizar_reflog("abc123 HEAD@{0} commit: hola")["descripcion"] == "commit: hola"
	assert op.agrupar_remotos([("origin", "u1", "fetch"), ("origin", "u2", "push")]) == [{"nombre": "origin", "traer": "u1", "enviar": "u2"}]
	from app.ui.git.ventana_git import describir_tipo_conflicto

	assert describir_tipo_conflicto("UU") == "modificado en las dos versiones"
	assert describir_tipo_conflicto("AU") == "añadido solo en su versión"
	assert describir_tipo_conflicto("AU", invertido=True) == "añadido solo en la otra versión"


def test_progreso_anuncia_solo_hitos():
	assert analizar_linea("Receiving objects:  45% (450/1000), 1.2 MiB") == ("Recibiendo objetos", 45)
	assert analizar_linea("Recibiendo objetos:  80% (8/10)") == ("Recibiendo objetos", 80)
	assert analizar_linea("Cloning into 'x'...") == ("Cloning into 'x'...", None)
	seguidor = SeguidorProgreso()
	anuncios = [seguidor.procesar(f"Receiving objects: {p}% ({p}/100)")[1] for p in range(0, 101, 5)]
	assert [a for a in anuncios if a] == [f"Recibiendo objetos, {h} por ciento" for h in (25, 50, 75, 100)]
	assert seguidor.procesar("Counting objects: 100% (5/5)")[1] == "", "las fases rápidas no se anuncian"
	assert seguidor.procesar("remote: Compressing objects: 100% (3/3)")[1] == ""
	nuevo = SeguidorProgreso()
	assert nuevo.procesar("Resolving deltas: 100% (3/3), done.")[1] == "Resolviendo diferencias, 100 por ciento"
	assert nuevo.procesar("Resolving deltas: 100% (3/3), done.") == (False, "")


# ════════════════════════════════════════════════════════════════════════════
# Ventana de git
# ════════════════════════════════════════════════════════════════════════════


@requiere_git
def test_ventana_estado_commit_y_teclado(app_wx, marco, tmp_path, dialogo_modal):
	repo = _repo(tmp_path)
	_commit(repo, "a.txt", "hola\n", "Primero")
	(repo.carpeta / "a.txt").write_bytes(b"hola\nadios\n")
	(repo.carpeta / "nuevo ñ.txt").write_bytes(b"nuevo\n")
	ctx, _api, anuncios = crear_contexto()
	ventana = _ventana(ctx, repo, marco)
	assert "Rama main" in ventana.campo_estado.GetValue() and "2 sin preparar" in ventana.campo_estado.GetValue()
	assert ventana.secciones.GetString(0) == "Cambios (2)"
	panel = ventana.paneles["cambios"]
	assert {a.ruta for a in panel.elementos} == {"a.txt", "nuevo ñ.txt"}
	hijos = list(panel.GetChildren())
	assert isinstance(hijos[hijos.index(panel.lista) - 1], wx.StaticText)

	# Espacio prepara (atajo de la lista) y vuelve a quitar.
	panel.lista.enfocar_fila([a.ruta for a in panel.elementos].index("a.txt"), anunciar=False)
	evento = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
	evento.SetKeyCode(wx.WXK_SPACE)
	panel.lista.GetEventHandler().ProcessEvent(evento)
	assert [a.ruta for a in repo.estado().preparados] == ["a.txt"]
	assert any("Preparado: a.txt" in a for a in anuncios)

	ventana.campo_mensaje.SetValue("Segundo commit\n\nCon descripción")
	ventana.confirmar_commit()
	assert repo.historial()[0].asunto == "Segundo commit"
	assert any("creado en main: Segundo commit" in a for a in anuncios)
	assert "enviado" in ctx.sonidos.eventos and ventana.campo_mensaje.GetValue() == ""

	# Sin nada preparado, ofrece prepararlo todo (Sí).
	dialogo_modal.responder(wx.ID_YES)
	ventana.campo_mensaje.SetValue("Tercero")
	ventana.confirmar_commit()
	assert repo.historial()[0].asunto == "Tercero" and repo.estado().limpio

	# Historial con filtro por autor (F4).
	ventana.ir_a_seccion("historial")
	historial = ventana.paneles["historial"]
	assert [m.asunto for m in historial.elementos] == ["Tercero", "Segundo commit", "Primero"]

	def filtrar(dialogo):
		dialogo.campo_texto.SetValue("segundo")
		return wx.ID_OK

	dialogo_modal.responder(filtrar)
	ventana.filtrar_historial()
	assert [m.asunto for m in historial.elementos] == ["Segundo commit"]
	assert "segundo" in ventana.texto_filtro.GetLabel()
	ventana.quitar_filtro_historial()
	assert len(historial.elementos) == 3

	# Teclado: cada sección con su menú «Acciones» rellenado.
	for clave in ventana.ids_secciones:
		ventana.ir_a_seccion(clave)
		ventana.rellenar_menu_acciones()
		afirmar_teclado_correcto(ventana, teclas_propias=["F6", "Ctrl+Intro"])

	# Ctrl+Tab cambia de sección y F6 alterna con la lista de secciones.
	ventana.ir_a_seccion("cambios")
	ventana.cambiar_seccion(1)
	assert ventana.seccion == "historial" and anuncios[-1] == "Historial"
	ventana.cambiar_seccion(-2)
	assert ventana.seccion == "conflictos"


@requiere_git
def test_ramas_etiquetas_y_stash(app_wx, marco, tmp_path, dialogo_modal):
	repo = _repo(tmp_path)
	_commit(repo, "a.txt", "uno\n", "Primero")
	ctx, _api, anuncios = crear_contexto()
	ventana = _ventana(ctx, repo, marco)

	dialogo_modal.responder(lambda d: (d.campo.SetValue("tema"), wx.ID_OK)[1], wx.ID_NO)
	ventana.crear_rama("HEAD", "HEAD")
	assert "tema" in {r.nombre for r in repo.ramas()} and repo.rama_actual() == "main"
	ventana.cambiar_rama(_rama(repo, "tema"))
	assert repo.rama_actual() == "tema"
	ventana.ir_a_seccion("ramas")
	assert {r.nombre for r in ventana.paneles["ramas"].elementos} == {"main", "tema"}

	dialogo_modal.responder(lambda d: (d.campo.SetValue("v1.0"), wx.ID_OK)[1], lambda d: (d.campo.SetValue("Versión 1"), wx.ID_OK)[1])
	ventana.crear_etiqueta("HEAD")
	assert repo.etiquetas()[0][0] == "v1.0"

	(repo.carpeta / "a.txt").write_bytes(b"cambiado\n")
	dialogo_modal.responder(lambda d: (d.campo.SetValue("a medias"), wx.ID_OK)[1])
	ventana.guardar_stash()
	assert repo.estado().limpio and repo.stashes()[0][2].endswith("a medias")
	ventana.ir_a_seccion("stash")
	stash = ventana.paneles["stash"].elementos[0]
	ventana.aplicar_stash(stash, borrar=True)
	assert not repo.stashes() and not repo.estado().limpio

	# Borrar una rama sin fusionar pide confirmar dos veces.
	repo.preparar_todo()
	repo.confirmar("en tema")
	ventana.cambiar_rama(_rama(repo, "main"))
	dialogo_modal.responder(wx.ID_YES, wx.ID_YES)
	ventana.borrar_rama(_rama(repo, "tema"))
	assert "tema" not in {r.nombre for r in repo.ramas()}
	assert any("Rama borrada" in a for a in anuncios)


@requiere_git
def test_conflicto_de_fusion_resuelto_bloque_a_bloque(app_wx, marco, tmp_path, dialogo_modal):
	from app.ui.git.dialogos import DialogoConflictos

	repo = _repo(tmp_path)
	archivo = repo.carpeta / "a.txt"
	base = "uno\ndos\n3\n4\n5\n6\n7\nocho\n"
	_commit(repo, "a.txt", base, "base")
	repo.crear_rama("otra")
	_commit(repo, "a.txt", base.replace("dos", "DOS otra").replace("ocho", "OCHO otra"), "en otra")
	repo.cambiar_rama("main")
	_commit(repo, "a.txt", base.replace("dos", "DOS main").replace("ocho", "OCHO main"), "en main")
	ctx, _api, anuncios = crear_contexto()
	ventana = _ventana(ctx, repo, marco)

	dialogo_modal.responder(wx.ID_YES)  # ¿Fusionar? Sí; el aviso de conflictos se acepta solo
	ventana.fusionar(_rama(repo, "otra"))
	assert ventana.operacion == "fusión" and ventana.seccion == "conflictos"
	assert "Fusión en curso" in ventana.campo_estado.GetValue() and ventana.secciones.GetString(9) == "Conflictos (1)"
	assert [a.ruta for a in ventana.paneles["conflictos"].elementos] == ["a.txt"]
	assert ventana.boton_continuar.IsEnabled() and not ventana.boton_saltar.IsEnabled()

	dialogo = DialogoConflictos(ventana, ctx, repo, ventana.raiz, "a.txt", ventana.operacion)
	afirmar_teclado_correcto(dialogo)
	assert len(dialogo.archivo.bloques) == 2
	texto = dialogo.campo_bloque.GetValue()
	assert texto.startswith("Bloque 1 de 2") and texto.index("DOS main") < texto.index("DOS otra")
	assert "Su versión, marcada como «HEAD»" in texto
	dialogo.elegir(c.PROPIA)
	assert dialogo.actual == 1 and any(a.startswith("Bloque 2 de 2") for a in anuncios)
	dialogo.campo_manual.SetValue("OCHO mezcla")
	dialogo.aplicar_manual()
	assert dialogo.archivo.resuelto
	dialogo.guardar()
	assert dialogo.codigo_salida == wx.ID_OK
	assert archivo.read_text(encoding="utf-8") == base.replace("dos", "DOS main").replace("ocho", "OCHO mezcla")
	assert not repo.estado().conflictos
	dialogo.Destroy()

	ventana.refrescar()
	ventana.continuar_operacion()
	assert repo.operacion_en_curso() == "" and ventana.operacion == ""
	assert len(repo.historial()[0].padres) == 2, "queda un commit de fusión"
	assert not ventana.boton_continuar.IsEnabled()


@requiere_git
def test_conflicto_de_reorganizacion_invierte_su_version(app_wx, marco, tmp_path, dialogo_modal):
	from app.ui.git.dialogos import DialogoConflictos

	repo = _repo(tmp_path)
	archivo = repo.carpeta / "a.txt"
	_commit(repo, "a.txt", "uno\ndos\ntres\n", "base")
	repo.crear_rama("tema")
	_commit(repo, "a.txt", "uno\nDOS tema\ntres\n", "en tema")
	repo.cambiar_rama("main")
	_commit(repo, "a.txt", "uno\nDOS main\ntres\n", "en main")
	repo.cambiar_rama("tema")
	ctx, _api, _anuncios = crear_contexto()
	ventana = _ventana(ctx, repo, marco)

	dialogo_modal.responder(wx.ID_YES)
	ventana.reorganizar(_rama(repo, "main"))
	assert ventana.operacion == "reorganización" and ventana.boton_saltar.IsEnabled()
	assert "al revés" in ventana.texto_conflictos.GetLabel()
	dialogo = DialogoConflictos(ventana, ctx, repo, ventana.raiz, "a.txt", ventana.operacion)
	assert dialogo.invertido
	texto = dialogo.campo_bloque.GetValue()
	assert texto.index("DOS tema") < texto.index("DOS main"), "en un rebase «su versión» es la de abajo (theirs)"
	dialogo.elegir(c.PROPIA)
	dialogo.guardar()
	dialogo.Destroy()
	assert archivo.read_text(encoding="utf-8") == "uno\nDOS tema\ntres\n"

	ventana.continuar_operacion()
	assert repo.operacion_en_curso() == ""
	assert [m.asunto for m in repo.historial()][:2] == ["en tema", "en main"]


@requiere_git
def test_resolver_archivo_entero_y_abortar(app_wx, marco, tmp_path, dialogo_modal):
	repo = _repo(tmp_path)
	archivo = repo.carpeta / "a.txt"
	_commit(repo, "a.txt", "base\n", "base")
	repo.crear_rama("otra")
	_commit(repo, "a.txt", "otra\n", "en otra")
	repo.cambiar_rama("main")
	_commit(repo, "a.txt", "principal\n", "en main")
	ctx, _api, _a = crear_contexto()
	ventana = _ventana(ctx, repo, marco)
	dialogo_modal.responder(wx.ID_YES)
	ventana.fusionar(_rama(repo, "otra"))
	conflicto = ventana.paneles["conflictos"].elementos[0]
	ventana.resolver_entero(conflicto, c.OTRA)
	assert archivo.read_text(encoding="utf-8") == "otra\n" and not repo.estado().conflictos
	dialogo_modal.responder(wx.ID_YES)
	ventana.abortar_operacion()
	assert repo.operacion_en_curso() == "" and archivo.read_text(encoding="utf-8") == "principal\n"


@requiere_git
def test_clonar_enviar_y_traer_con_remoto_local(app_wx, marco, tmp_path, dialogo_modal):
	from app.ui.git.clonar import DialogoClonar

	origen = _repo(tmp_path, "origen")
	_commit(origen, "a.txt", "hola\n", "Primero")
	desnudo = tmp_path / "desnudo.git"
	g.ejecutar(["clone", "--bare", str(origen.carpeta), str(desnudo)])
	ctx, _api, anuncios = crear_contexto()
	ctx.config.establecer("git.carpeta_clonado", str(tmp_path / "clones"))
	clonados: list[str] = []
	dialogo = DialogoClonar(marco, ctx, str(desnudo), al_clonar=clonados.append)
	afirmar_teclado_correcto(dialogo)
	assert dialogo.campo_nombre.GetValue() == "desnudo"
	dialogo.clonar()
	destino = tmp_path / "clones" / "desnudo"
	assert dialogo.codigo_salida == wx.ID_OK and clonados == [str(destino)]
	assert (destino / "a.txt").exists()
	assert ctx.config.obtener("git.repos_locales")[0] == os.path.normpath(str(destino))
	assert "completado" in ctx.sonidos.eventos
	dialogo.Destroy()

	clon = g.RepositorioLocal(destino)
	for clave, valor in (("user.name", "Prueba"), ("user.email", "prueba@example.com"), ("commit.gpgsign", "false")):
		clon.establecer_config(clave, valor)
	_commit(clon, "b.txt", "nuevo\n", "Desde el clon")
	ventana = _ventana(ctx, clon, marco)
	assert "1 por delante" in ventana.campo_estado.GetValue()
	ventana.enviar()
	assert g.ejecutar(["log", "-1", "--format=%s"], desnudo).strip() == "Desde el clon"
	assert not ventana.progreso.en_curso and "enviada" in ventana.progreso.campo.GetValue()
	assert "al día" in ventana.campo_estado.GetValue()
	ventana.traer()
	assert any("Cambios traídos" in a for a in anuncios)

	# Una rama nueva sin remota: ofrece --set-upstream.
	clon.crear_rama("nueva")
	dialogo_modal.responder(wx.ID_YES)
	ventana.enviar()
	assert "nueva" in g.ejecutar(["branch", "--list", "nueva"], desnudo)
	assert clon.estado().rama_remota == "origin/nueva"


@requiere_git
def test_clonar_falla_sin_borrar_carpetas_ajenas(app_wx, marco, tmp_path, dialogo_modal):
	from app.ui.git.clonar import DialogoClonar

	ctx, _api, _a = crear_contexto()
	ctx.config.establecer("git.carpeta_clonado", str(tmp_path))
	dialogo = DialogoClonar(marco, ctx, str(tmp_path / "no_existe.git"))
	dialogo.clonar()
	assert dialogo.codigo_salida == wx.ID_NONE and not dialogo.clonando
	assert dialogo.boton_clonar.IsEnabled()
	assert "No se pudo clonar" in dialogo.progreso.campo.GetValue()
	assert not (tmp_path / "no_existe").exists()
	assert dialogo_modal.ultimo is not None and dialogo_modal.ultimo.titulo == "No se pudo clonar"
	dialogo.Destroy()


def test_clonar_sin_git_ofrece_zip(app_wx, tmp_path, dialogo_modal, monkeypatch):
	from app.ui.git import clonar

	monkeypatch.setattr(g, "git_disponible", lambda: False)
	ctx, api, _a = crear_contexto()
	api.archivo_zip.return_value = "https://api.github.com/repos/ana/proyecto/zipball"
	destino = tmp_path / "proyecto.zip"
	dialogo_modal.responder(lambda d: d.ids_opciones[0], lambda d: (d.campo.SetValue(str(destino)), wx.ID_OK)[1])
	assert clonar.dialogo_clonar(None, ctx, "", "ana/proyecto") is None
	assert any("Git for Windows" in t for t in dialogo_modal.mostrados[0].textos)
	zip_pedido = ctx.descargas.pedidas[-1]
	assert zip_pedido.url == "https://api.github.com/repos/ana/proyecto/zipball" and zip_pedido.destino == str(destino)
	assert zip_pedido.sobrescribir, "el destino lo eligió la persona"
	assert clonar.nombre_repo_de("git@github.com:ana/x.git", "", "github.com") == "ana/x"


@requiere_git
def test_abrir_ventana_git_trae_al_frente_la_abierta(app_wx, tmp_path, monkeypatch):
	from app.ui.git import ventana_git

	repo = _repo(tmp_path)
	ctx, _api, _a = crear_contexto()
	monkeypatch.setattr(ventana_git.VentanaGit, "Show", lambda self, mostrar=True: True)
	primera = ventana_git.abrir_ventana_git(ctx, str(repo.carpeta))
	try:
		segunda = ventana_git.abrir_ventana_git(ctx, str(repo.carpeta) + os.sep)
		assert primera is segunda and ctx.sonidos.eventos.count("abrir") == 2
		assert primera.secciones.GetString(0) == "Cambios"
	finally:
		primera.Destroy()
	assert ventana_git._clave(str(repo.carpeta)) not in ventana_git._ABIERTAS


@requiere_git
def test_biseccion_y_configuracion_del_repositorio(app_wx, marco, tmp_path):
	from app.ui.git.dialogos import DialogoBiseccion, DialogoConfigRepo, DialogoFiltroHistorial

	repo = _repo(tmp_path)
	for numero in range(4):
		_commit(repo, "a.txt", f"{numero}\n", f"commit {numero}")
	ctx, _api, anuncios = crear_contexto()
	salida = op.empezar_biseccion(repo, "HEAD", "HEAD~3")
	assert repo.operacion_en_curso() == "bisección"
	dialogo = DialogoBiseccion(marco, ctx, repo, salida)
	afirmar_teclado_correcto(dialogo)
	dialogo.paso("bad")
	dialogo.paso("reset")
	assert repo.operacion_en_curso() == "" and "Bisección terminada" in dialogo.campo.GetValue()
	dialogo.Destroy()

	configuracion = DialogoConfigRepo(marco, ctx, repo)
	afirmar_teclado_correcto(configuracion)
	assert configuracion.campo_nombre.GetValue() == "Prueba" and configuracion.selector_firma.GetSelection() == 2
	configuracion.campo_nombre.SetValue("Otra persona")
	configuracion.campo_clave.SetValue("")
	configuracion.guardar()
	assert repo.config("user.name") == "Otra persona" and configuracion.codigo_salida == wx.ID_OK
	configuracion.Destroy()

	filtro = DialogoFiltroHistorial(marco, {"autor": "Ana"})
	afirmar_teclado_correcto(filtro)
	assert filtro.valores()["autor"] == "Ana"
	filtro.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Herramientas: claves y configuración global
# ════════════════════════════════════════════════════════════════════════════


def test_ventana_de_claves(app_wx, dialogo_modal):
	from app.ui.herramientas.claves import FIRMA, VentanaClaves, huella_corta

	api = mock.MagicMock(name="ApiGitHub")
	api.claves_ssh.return_value = [{"id": 7, "title": "Portátil", "key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPrueba", "created_at": "2026-01-01T00:00:00Z"}]
	api.claves_firma_ssh.return_value = []
	ctx, api, anuncios = crear_contexto(api)
	ventana = VentanaClaves(None, ctx)
	try:
		afirmar_teclado_correcto(ventana)
		panel = ventana.paneles["ssh"]
		assert panel.lista.numero_filas() == 1 and panel.lista.texto_celda(0, 0) == "Portátil"
		assert huella_corta("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPrueba") == "ssh-ed25519 …5AAAAIPrueba"
		dialogo_modal.responder(wx.ID_YES)
		ventana.borrar()
		api.borrar_clave_ssh.assert_called_once_with(7)
		assert panel.lista.numero_filas() == 0
		ventana.anadir(texto="ssh-ed25519 AAAA equipo@casa\n", titulo="Casa")
		api.anadir_clave_ssh.assert_called_once_with("Casa", "ssh-ed25519 AAAA equipo@casa")
		ventana.subir(FIRMA, "x", "-----BEGIN OPENSSH PRIVATE KEY-----\nabc")
		api.anadir_clave_firma_ssh.assert_not_called()
		assert dialogo_modal.ultimo.titulo == "Clave privada"
		ventana.libro.SetSelection(2)
		assert ventana.tipo == "gpg"
	finally:
		ventana.Destroy()


@pytest.mark.skipif(not (shutil.which("ssh-keygen") or g.git_disponible()), reason="sin ssh-keygen")
def test_generar_clave_ssh_y_subirla(app_wx, tmp_path, dialogo_modal):
	from app.ui.herramientas.claves import VentanaClaves

	ctx, api, _a = crear_contexto()
	api.claves_ssh.return_value = []
	ventana = VentanaClaves(None, ctx)
	try:
		dialogo_modal.responder(lambda d: d.ids_opciones[0])  # «Como clave de autenticación»
		ruta = tmp_path / "ssh" / "id_ed25519"
		ventana.generar_en(ruta, "prueba@example.com")
		assert ruta.exists() and Path(str(ruta) + ".pub").exists()
		titulo, texto = api.anadir_clave_ssh.call_args.args
		assert titulo == "prueba@example.com" and texto.startswith("ssh-ed25519 ")
	finally:
		ventana.Destroy()


@requiere_git
def test_configuracion_global_de_git(app_wx, tmp_path, monkeypatch):
	from app.ui.herramientas.config_git import DialogoConfiguracionGit

	monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig_global"))
	g.establecer_config_global("user.name", "Antes")
	g.establecer_config_global("credential.helper", "manager")
	ctx, _api, _a = crear_contexto()
	dialogo = DialogoConfiguracionGit(None, ctx)
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.campo_version.GetValue().startswith("git version")
		assert dialogo.campos["user.name"].GetValue() == "Antes"
		assert dialogo.campos["core.autocrlf"].GetSelection() == 0 and not dialogo.casilla_firmar.GetValue()
		dialogo.campos["user.name"].SetValue("Después")
		dialogo.campos["core.autocrlf"].SetSelection(3)
		dialogo.campos["credential.helper"].SetValue("")
		dialogo.casilla_firmar.SetValue(True)
		dialogo.guardar()
		assert g.config_global("user.name") == "Después"
		assert g.config_global("core.autocrlf") == "false"
		assert g.config_global("credential.helper") == ""
		assert g.config_global("commit.gpgsign") == "true"
		assert g.config_global("pull.rebase") == "", "lo que no se toca no se escribe"
		assert dialogo.codigo_salida == wx.ID_OK
	finally:
		dialogo.Destroy()
