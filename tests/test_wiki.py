"""Wiki de un repositorio: funciones puras, copia local con git y sección de la ventana."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from app.services import git_local as g
from app.services import wiki as w

requiere_git = pytest.mark.skipif(not g.git_disponible(), reason="git no está instalado")
NOMBRE = "ana/proyecto"


# ════════════════════════════════════════════════════════════════════════════
# Funciones puras
# ════════════════════════════════════════════════════════════════════════════


def test_direcciones_de_la_wiki():
	assert w.url_clonado("github.com", NOMBRE) == "https://github.com/ana/proyecto.wiki.git"
	assert w.url_web("github.com", NOMBRE) == "https://github.com/ana/proyecto/wiki"
	assert w.url_web("github.com", NOMBRE, "Home") == "https://github.com/ana/proyecto/wiki"
	assert w.url_web("github.com", NOMBRE, "Primeros-pasos") == "https://github.com/ana/proyecto/wiki/Primeros-pasos"
	assert w.url_nueva_pagina("git.empresa.es", NOMBRE) == "https://git.empresa.es/ana/proyecto/wiki/_new"


def test_titulos_y_nombres_de_archivo():
	assert w.titulo_de_archivo("Primeros-pasos.md") == "Primeros pasos"
	assert w.titulo_de_archivo("_Sidebar.md") == "Barra lateral"
	assert w.archivo_para_titulo("Mi página: guía") == "Mi-página--guía.md"
	assert w.archivo_para_titulo("Notas", ".mediawiki") == "Notas.mediawiki"
	with pytest.raises(w.ErrorWiki):
		w.archivo_para_titulo("   ")


def test_enlaces_de_gollum_a_markdown():
	texto = "Vea [[Primeros pasos]], [[la guía|Guía de uso]], [[Otra#Sección uno]], [[logo.png]] y [[GitHub|https://github.com]]."
	resultado = w.convertir_enlaces(texto, "github.com", NOMBRE)
	assert "[Primeros pasos](https://github.com/ana/proyecto/wiki/Primeros-pasos)" in resultado
	assert "[la guía](https://github.com/ana/proyecto/wiki/Gu%C3%ADa-de-uso)" in resultado
	assert "(https://github.com/ana/proyecto/wiki/Otra#secci%C3%B3n-uno)" in resultado
	assert "[Imagen: logo.png](https://github.com/ana/proyecto/wiki/logo.png)" in resultado
	assert "[GitHub](https://github.com)" in resultado


def test_enlace_a_otra_pagina_de_la_misma_wiki():
	assert w.pagina_de_enlace("https://github.com/ana/proyecto/wiki/Gu%C3%ADa-de-uso", "github.com", NOMBRE) == "Guía-de-uso"
	assert w.pagina_de_enlace("https://github.com/ana/proyecto/wiki", "github.com", NOMBRE) == "Home"
	assert w.pagina_de_enlace("https://github.com/otra/cosa/wiki/X", "github.com", NOMBRE) is None
	assert w.pagina_de_enlace("https://github.com/ana/proyecto/wiki/_new", "github.com", NOMBRE) is None
	assert w.pagina_de_enlace("https://example.com/ana/proyecto/wiki/X", "github.com", NOMBRE) is None
	paginas = [w.PaginaWiki("Guía-de-uso.md", "Guía de uso", "Markdown", 10)]
	assert w.buscar_pagina(paginas, "guía de uso") is paginas[0]
	assert w.buscar_pagina(paginas, "otra") is None


def test_listar_y_ordenar_paginas(tmp_path):
	for nombre in ("Zeta.md", "_Footer.md", "Home.md", "alfa.mediawiki", "imagen.png", ".git/config.md"):
		(tmp_path / nombre).parent.mkdir(parents=True, exist_ok=True)
		(tmp_path / nombre).write_text("x", encoding="utf-8")
	paginas = w.listar_paginas(tmp_path)
	assert [p.archivo for p in paginas] == ["Home.md", "alfa.mediawiki", "Zeta.md", "_Footer.md"]
	assert paginas[1].formato == "MediaWiki" and paginas[3].especial == "_footer"


def test_documento_para_el_visor():
	md = w.PaginaWiki("Guía.md", "Guía", "Markdown", 1)
	assert w.documento_para_visor(md, "Texto con [[Home]]", "github.com", NOMBRE).startswith("# Guía\n\nTexto con [Home](")
	assert w.documento_para_visor(md, "# Ya tiene título", "github.com", NOMBRE) == "# Ya tiene título"
	otra = w.PaginaWiki("Guía.mediawiki", "Guía", "MediaWiki", 1)
	documento = w.documento_para_visor(otra, "== Título ==", "github.com", NOMBRE)
	assert "MediaWiki" in documento and "```\n== Título ==\n```" in documento


# ════════════════════════════════════════════════════════════════════════════
# Copia local con git (un repositorio desnudo hace de GitHub)
# ════════════════════════════════════════════════════════════════════════════


def _remoto(tmp_path: Path) -> Path:
	remoto = tmp_path / "proyecto.wiki.git"
	g.ejecutar(["init", "--bare", "-b", "master", str(remoto)])
	semilla = tmp_path / "semilla"
	g.ejecutar(["clone", str(remoto), str(semilla)], analizable=False)
	(semilla / "Home.md").write_text("# Inicio\n\nVea [[Guía]].\n", encoding="utf-8")
	(semilla / "Guía.md").write_text("Primera versión.\n", encoding="utf-8")
	(semilla / "_Sidebar.md").write_text("* [[Home]]\n", encoding="utf-8")
	repo = g.RepositorioLocal(semilla)
	repo.git("config", "user.name", "Semilla")
	repo.git("config", "user.email", "semilla@example.com")
	repo.git("add", "-A")
	repo.confirmar("Primeras páginas")
	repo.git("push", "origin", "HEAD", analizable=False)
	return remoto


def _wiki(tmp_path: Path, remoto: Path) -> w.WikiLocal:
	return w.WikiLocal(tmp_path / "cache" / "wiki", "github.com", NOMBRE, identidad=("ana", "ana@users.noreply.github.com"),
		url_remoto=str(remoto))


def _archivos_remotos(remoto: Path) -> str:
	return g.ejecutar(["ls-tree", "--name-only", "HEAD"], remoto)


@requiere_git
def test_sincronizar_editar_crear_renombrar_y_borrar(tmp_path):
	remoto = _remoto(tmp_path)
	wiki = _wiki(tmp_path, remoto)
	paginas = wiki.sincronizar()
	assert [p.archivo for p in paginas] == ["Home.md", "Guía.md", "_Sidebar.md"]
	assert "Primera versión" in wiki.leer("Guía.md")

	wiki.guardar("Guía.md", "Segunda versión.\n", "Mejorar la guía")
	assert "Segunda versión" in g.ejecutar(["show", "HEAD:Guía.md"], remoto)
	with pytest.raises(w.ErrorWiki, match="no ha cambiado"):
		wiki.guardar("Guía.md", "Segunda versión.\n", "")

	nueva = wiki.guardar(w.archivo_para_titulo("Preguntas frecuentes"), "Hola", "", nueva=True)
	assert nueva.titulo == "Preguntas frecuentes" and "Preguntas-frecuentes.md" in _archivos_remotos(remoto)
	with pytest.raises(w.ErrorWiki, match="Ya existe"):
		wiki.guardar("Preguntas-frecuentes.md", "Otra", "", nueva=True)

	assert wiki.renombrar("Preguntas-frecuentes.md", "Dudas") == "Dudas.md"
	assert "Dudas.md" in _archivos_remotos(remoto) and "Preguntas-frecuentes.md" not in _archivos_remotos(remoto)

	wiki.borrar("Dudas.md")
	assert "Dudas.md" not in _archivos_remotos(remoto)

	historial = wiki.historial("Guía.md")
	assert [c.asunto for c in historial] == ["Mejorar la guía", "Primeras páginas"]
	assert "Primera versión" in wiki.version("Guía.md", historial[1].sha)
	assert "+Segunda versión." in wiki.diferencias("Guía.md", historial[0].sha)
	assert historial[0].autor == "ana" or g.config_global("user.name")


@requiere_git
def test_trae_los_cambios_hechos_en_la_web(tmp_path):
	remoto = _remoto(tmp_path)
	wiki = _wiki(tmp_path, remoto)
	wiki.sincronizar()
	otra = tmp_path / "otra"
	g.ejecutar(["clone", str(remoto), str(otra)], analizable=False)
	(otra / "Nueva.md").write_text("Desde la web", encoding="utf-8")
	repo = g.RepositorioLocal(otra)
	repo.git("config", "user.name", "Web")
	repo.git("config", "user.email", "web@example.com")
	repo.git("add", "-A")
	repo.confirmar("Página creada en la web")
	repo.git("push", "origin", "HEAD", analizable=False)
	(wiki.carpeta / "basura.md").write_text("se va", encoding="utf-8")
	assert "Nueva.md" in [p.archivo for p in wiki.sincronizar()]
	assert not (wiki.carpeta / "basura.md").exists(), "la caché queda igual que GitHub"


@requiere_git
def test_si_no_se_puede_enviar_se_deshace_el_commit(tmp_path):
	remoto = _remoto(tmp_path)
	wiki = _wiki(tmp_path, remoto)
	wiki.sincronizar()
	antes = wiki.repo.git("rev-parse", "HEAD").strip()
	real = wiki.repo.git_red

	def falla(*argumentos, **opciones):
		if argumentos and argumentos[0] == "push":
			raise g.ErrorGit("sin permiso", list(argumentos), 128, "remote: Permission denied")
		return real(*argumentos, **opciones)

	wiki.repo.git_red = falla
	with pytest.raises(w.ErrorWiki, match="No se pudo enviar"):
		wiki.guardar("Guía.md", "Cambio que no llega", "")
	assert wiki.repo.git("rev-parse", "HEAD").strip() == antes
	assert "Primera versión" in wiki.leer("Guía.md")


@requiere_git
def test_wiki_sin_paginas(tmp_path):
	wiki = _wiki(tmp_path, tmp_path / "no-existe.wiki.git")
	with pytest.raises(w.WikiSinPaginas, match="primera página"):
		wiki.sincronizar()
	assert not wiki.carpeta.exists()


def test_ruta_fuera_de_la_wiki_no_se_admite(tmp_path):
	wiki = w.WikiLocal(tmp_path / "wiki", "github.com", NOMBRE)
	(tmp_path / "wiki").mkdir()
	with pytest.raises(w.ErrorWiki):
		wiki.leer("../secreto.md")


# ════════════════════════════════════════════════════════════════════════════
# Sección «Wiki» de la ventana del repositorio
# ════════════════════════════════════════════════════════════════════════════


def _panel(marco, ctx, info: dict):
	from app.ui.repositorio import vistas
	from app.ui.vistas.base import PanelLista

	definicion = vistas.VISTAS["wiki"](NOMBRE)
	panel = PanelLista(marco, ctx, definicion, {"nombre": NOMBRE, "info": info})
	vistas.rotular(panel)
	return panel


def _accion(panel, texto: str):
	return next(a for a in panel.acciones_disponibles() if texto in a.etiqueta.replace("&", ""))


def test_seccion_wiki_desactivada_ofrece_activarla(app_wx, marco):
	import wx

	from tests.apoyo_app import crear_contexto

	ctx, api, _a = crear_contexto()
	api.editar_repositorio.return_value = {"full_name": NOMBRE, "has_wiki": True}
	panel = _panel(marco, ctx, {"full_name": NOMBRE, "has_wiki": False})
	panel.cargar()
	wx.Yield()
	assert panel.datos["estado_wiki"] == "desactivada" and "desactivada" in panel.etiqueta.GetLabel()
	assert "desactivada" in panel.definicion.texto_vacio
	etiquetas = [a.etiqueta.replace("&", "") for a in panel.acciones_disponibles()]
	assert "Activar la wiki…" in etiquetas and "Nueva página…" not in etiquetas
	with mock.patch.object(g, "git_disponible", return_value=False):
		panel.ejecutar(_accion(panel, "Activar la wiki"))
	api.editar_repositorio.assert_called_once_with(NOMBRE, has_wiki=True)
	assert panel.datos["estado_wiki"] == "sin_git"
	panel.Destroy()


def test_seccion_wiki_vacia_ofrece_el_navegador(app_wx, marco, monkeypatch):
	from tests.apoyo_app import crear_contexto

	ctx, _api, _a = crear_contexto()
	monkeypatch.setattr(g, "git_disponible", lambda: True)
	monkeypatch.setattr(w.WikiLocal, "sincronizar", mock.Mock(side_effect=w.WikiSinPaginas("vacía")))
	abiertas = []
	monkeypatch.setattr("webbrowser.open", lambda url: abiertas.append(url))
	panel = _panel(marco, ctx, {"full_name": NOMBRE, "has_wiki": True})
	panel.cargar()
	assert panel.datos["estado_wiki"] == "vacia"
	panel.ejecutar(_accion(panel, "Crear la primera página"))
	assert abiertas == ["https://github.com/ana/proyecto/wiki/_new"]
	panel.Destroy()


def test_seccion_wiki_lista_y_abre_paginas(app_wx, marco, monkeypatch):
	from app.ui import visor_ayuda
	from tests.apoyo_app import crear_contexto

	ctx, _api, _a = crear_contexto()
	paginas = [w.PaginaWiki("Home.md", "Home", "Markdown", 30), w.PaginaWiki("Guía.md", "Guía", "Markdown", 12)]
	monkeypatch.setattr(g, "git_disponible", lambda: True)
	monkeypatch.setattr(w.WikiLocal, "sincronizar", lambda self: paginas)
	monkeypatch.setattr(w.WikiLocal, "leer", lambda self, archivo: {"Home.md": "Vea [[Guía]].", "Guía.md": "Texto"}[archivo])
	mostrados = []
	monkeypatch.setattr(visor_ayuda, "mostrar_documento", lambda padre, titulo, texto, **op: mostrados.append((titulo, texto, op)))
	panel = _panel(marco, ctx, {"full_name": NOMBRE, "has_wiki": True})
	panel.cargar()
	assert [e["titulo"] for e in panel.elementos] == ["Home", "Guía"] and panel.elementos[0]["tipo"] == "Portada"
	panel.lista.enfocar_fila(0, anunciar=False)
	panel.ejecutar(_accion(panel, "Abrir la página"))
	titulo, texto, opciones = mostrados[0]
	assert titulo == "Home — wiki de ana/proyecto" and "[Guía](https://github.com/ana/proyecto/wiki/Gu%C3%ADa)" in texto
	assert opciones["al_enlace"]("https://github.com/ana/proyecto/wiki/Gu%C3%ADa") is True
	assert mostrados[1][0] == "Guía — wiki de ana/proyecto"
	assert opciones["al_enlace"]("https://github.com/ana/proyecto/wiki/No-existe") is False
	assert panel.definicion.url(panel.elementos[1]) == "https://github.com/ana/proyecto/wiki/Gu%C3%ADa"
	panel.Destroy()
