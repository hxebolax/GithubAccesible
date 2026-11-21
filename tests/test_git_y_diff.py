"""Pruebas del análisis de diff y de git local (con el git real en una carpeta temporal)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.services import diferencias as d
from app.services import git_local as g

DIFF = """diff --git a/app/uno.py b/app/uno.py
index 111..222 100644
--- a/app/uno.py
+++ b/app/uno.py
@@ -1,4 +1,5 @@ def principal():
 a = 1
-b = 2
+b = 3
+c = 4
 d = 5
@@ -10,2 +11,2 @@
 x
-y
+z
diff --git a/nuevo.txt b/nuevo.txt
new file mode 100644
--- /dev/null
+++ b/nuevo.txt
@@ -0,0 +1 @@
+hola
\\ No newline at end of file
"""


def test_analizar_diff_completo():
	archivos = d.analizar(DIFF)
	assert [a.ruta for a in archivos] == ["app/uno.py", "nuevo.txt"]
	uno, nuevo = archivos
	assert (uno.añadidas, uno.eliminadas) == (3, 2)
	assert nuevo.estado == "añadido" and nuevo.añadidas == 1
	tipos = [linea.tipo for linea in uno.lineas]
	assert tipos[:6] == [d.BLOQUE, d.CONTEXTO, d.ELIMINADA, d.AÑADIDA, d.AÑADIDA, d.CONTEXTO]
	eliminada = uno.lineas[2]
	assert (eliminada.antigua, eliminada.nueva, eliminada.texto) == (2, None, "b = 2")
	assert uno.lineas[3].nueva == 2 and uno.lineas[4].nueva == 3
	assert "principal" in uno.lineas[0].texto


def test_posiciones_para_comentar_en_la_api():
	uno = d.analizar(DIFF)[0]
	# La línea siguiente al primer @@ es la posición 1; el segundo @@ también cuenta.
	assert [linea.posicion for linea in uno.lineas] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_patch_de_un_archivo_sin_cabecera_git():
	archivos = d.analizar("@@ -1 +1 @@\n-viejo\n+nuevo", archivo_por_defecto="README.md")
	assert archivos[0].ruta == "README.md" and archivos[0].añadidas == 1


def test_saltos_entre_cambios():
	lineas = d.aplanar(d.analizar(DIFF))
	primero = d.siguiente_cambio(lineas, 0)
	assert lineas[primero].tipo == d.ELIMINADA
	segundo = d.siguiente_cambio(lineas, primero)
	assert lineas[segundo].texto == "y", "salta el grupo entero, no línea a línea"
	assert d.siguiente_cambio(lineas, segundo, hacia_atras=True) == primero
	assert "3 líneas añadidas" in d.resumen_total(d.analizar(DIFF)) or "añadidas" in d.resumen_total(d.analizar(DIFF))
	assert "Eliminada 2: b = 2" in d.texto_legible(d.analizar(DIFF))


def test_analizar_estado_porcelain_v2():
	salida = "\0".join([
		"# branch.oid abc123", "# branch.head main", "# branch.upstream origin/main", "# branch.ab +2 -1",
		"1 .M N... 100644 100644 100644 a b archivo con espacios.txt",
		"1 A. N... 000000 100644 100644 0 b nuevo.py",
		"2 R. N... 100644 100644 100644 a b R100 renombrado.py", "viejo.py",
		"u UU N... 100644 100644 100644 100644 a b c conflicto.py",
		"? sin_seguir.md", "",
	])
	estado = g.analizar_estado(salida)
	assert (estado.rama, estado.rama_remota, estado.adelante, estado.atras) == ("main", "origin/main", 2, 1)
	rutas = {a.ruta: a for a in estado.archivos}
	assert rutas["archivo con espacios.txt"].sin_preparar and not rutas["archivo con espacios.txt"].preparado
	assert rutas["nuevo.py"].preparado
	assert rutas["renombrado.py"].ruta_original == "viejo.py"
	assert rutas["conflicto.py"].conflicto
	assert rutas["sin_seguir.md"].sin_seguimiento
	assert "2 por delante y 1 por detrás" in estado.resumen()


requiere_git = pytest.mark.skipif(not g.git_disponible(), reason="git no está instalado")


def _repo(tmp_path: Path) -> g.RepositorioLocal:
	carpeta = tmp_path / "repo"
	g.iniciar(carpeta)
	repo = g.RepositorioLocal(carpeta)
	repo.establecer_config("user.name", "Prueba")
	repo.establecer_config("user.email", "prueba@example.com")
	repo.establecer_config("commit.gpgsign", "false")
	return repo


@requiere_git
def test_ciclo_completo_con_git_real(tmp_path):
	repo = _repo(tmp_path)
	assert g.RepositorioLocal.es_repositorio(repo.carpeta)
	(repo.carpeta / "léeme ñ.txt").write_text("hola\n", encoding="utf-8")
	estado = repo.estado()
	assert [a.ruta for a in estado.archivos] == ["léeme ñ.txt"] and estado.archivos[0].sin_seguimiento
	repo.preparar(["léeme ñ.txt"])
	assert repo.estado().preparados
	repo.confirmar("Primer commit\n\nCon cuerpo y acentos: ñ")
	historial = repo.historial()
	assert historial[0].asunto == "Primer commit" and "ñ" in historial[0].cuerpo
	(repo.carpeta / "léeme ñ.txt").write_text("hola\nadiós\n", encoding="utf-8")
	diff = repo.diferencias("léeme ñ.txt")
	archivo = d.analizar(diff)[0]
	assert archivo.añadidas == 1 and archivo.lineas[-1].texto == "adiós"
	repo.guardar_stash("pruebas")
	assert repo.estado().limpio and len(repo.stashes()) == 1
	repo.aplicar_stash("stash@{0}", borrar=True)
	assert not repo.estado().limpio
	repo.preparar_todo()
	repo.confirmar("Segundo")
	repo.crear_rama("tema")
	assert repo.rama_actual() == "tema"
	repo.cambiar_rama("main")
	assert {r.nombre for r in repo.ramas()} >= {"main", "tema"}
	repo.crear_etiqueta("v1.0", "Versión 1")
	assert repo.etiquetas()[0][0] == "v1.0"
	assert repo.culpables("léeme ñ.txt")[1][4] == "adiós"
	assert repo.operacion_en_curso() == ""


@requiere_git
def test_conflicto_y_resolucion(tmp_path):
	repo = _repo(tmp_path)
	archivo = repo.carpeta / "a.txt"
	archivo.write_text("base\n", encoding="utf-8")
	repo.preparar_todo()
	repo.confirmar("base")
	repo.crear_rama("otra")
	archivo.write_text("otra\n", encoding="utf-8")
	repo.preparar_todo()
	repo.confirmar("en otra")
	repo.cambiar_rama("main")
	archivo.write_text("principal\n", encoding="utf-8")
	repo.preparar_todo()
	repo.confirmar("en main")
	with pytest.raises(g.ErrorGit) as error:
		repo.fusionar("otra")
	assert "conflictos" in error.value.mensaje_usuario
	assert repo.operacion_en_curso() == "fusión"
	assert repo.estado().conflictos[0].ruta == "a.txt"
	repo.resolver_con("a.txt", "theirs")
	repo.confirmar("fusión resuelta")
	assert archivo.read_text(encoding="utf-8") == "otra\n"


@requiere_git
def test_error_fuera_de_un_repositorio(tmp_path):
	with pytest.raises(g.ErrorGit, match="no es un repositorio"):
		g.RepositorioLocal(tmp_path).estado()


def test_script_askpass_devuelve_usuario_y_token(tmp_path, monkeypatch):
	monkeypatch.setattr(g, "_carpeta_temporal", lambda: tmp_path)
	entorno, temporales = g.entorno_git("ghp_token_de_prueba", "x-access-token")
	try:
		script = entorno["GIT_ASKPASS"]
		usuario = subprocess.run([script, "Username for 'https://github.com': "], capture_output=True, text=True, env=entorno)
		clave = subprocess.run([script, "Password for 'https://x-access-token@github.com': "], capture_output=True, text=True, env=entorno)
		assert usuario.stdout.strip() == "x-access-token"
		assert clave.stdout.strip() == "ghp_token_de_prueba"
		assert "ghp_token_de_prueba" not in Path(script).read_text(encoding="utf-8"), "el token no se escribe en disco"
	finally:
		for t in temporales:
			t.unlink()
