"""Resultados de búsqueda: de quién es cada cosa y acciones para ir al propietario, al autor o al repositorio."""

from __future__ import annotations

from app.ui.accesibilidad.revision_teclado import letra_de_acceso
from app.ui.vistas import principales as pr
from app.ui.vistas.base import PanelLista

REPO = {"full_name": "ana/proyecto", "owner": {"login": "ana", "type": "User"}, "clone_url": "https://github.com/ana/proyecto.git"}
ISSUE = {"number": 4, "title": "Fallo", "user": {"login": "luis"}, "repository_url": "https://api.github.com/repos/org/app"}
CODIGO = {"path": "app/main.py", "repository": {"full_name": "org/app", "owner": {"login": "org"}}}
COMMIT = {"sha": "abc", "commit": {"message": "x"}, "author": {"login": "eva"}, "repository": {"full_name": "org/app"}}
USUARIO = {"login": "marta", "type": "User"}
TENDENCIA = {"_tipo": "tendencia_repo", "full_name": "pepe/cosa", "name": "cosa"}
DESARROLLADOR = {"_tipo": "tendencia_dev", "login": "rosa", "name": "Rosa"}
DISCUSION = {"_tipo": "discusion", "number": 2, "author": {"login": "ines"}, "repository": {"nameWithOwner": "org/app"}}
ETIQUETA = {"name": "bug", "color": "ff0000", "default": True}


def test_propietario_autor_y_repositorio_de_cada_tipo():
	assert pr.propietario_del_resultado(REPO) == "ana"
	assert pr.propietario_del_resultado(ISSUE) == "org" and pr.autor_del_resultado(ISSUE) == "luis"
	assert pr.repo_del_resultado(ISSUE) == "org/app"
	assert pr.propietario_del_resultado(CODIGO) == "org" and pr.repo_del_resultado(CODIGO) == "org/app"
	assert pr.autor_del_resultado(COMMIT) == "eva" and pr.propietario_del_resultado(COMMIT) == "org"
	assert pr.propietario_del_resultado(TENDENCIA) == "pepe" and pr.es_repositorio_resultado(TENDENCIA)
	assert pr.autor_del_resultado(DISCUSION) == "ines" and pr.repo_del_resultado(DISCUSION) == "org/app"
	assert pr.repo_del_resultado(ETIQUETA, {"repositorio": "ana/proyecto"}) == "ana/proyecto"
	# Una cuenta no tiene propietario: se sigue a ella directamente.
	for cuenta, login in ((USUARIO, "marta"), (DESARROLLADOR, "rosa")):
		assert pr.propietario_del_resultado(cuenta) == "" and pr.cuenta_del_resultado(cuenta) == login
	assert pr.cuenta_del_resultado(REPO) == "" and pr.cuenta_del_resultado(ISSUE) == ""
	assert pr.es_repositorio_resultado(REPO) and not pr.es_repositorio_resultado(ISSUE)
	assert not pr.es_repositorio_resultado(CODIGO) and not pr.es_repositorio_resultado(COMMIT)


def _panel(marco, ctx, elementos):
	panel = PanelLista(marco, ctx, pr.vista_busqueda(), {"tipo": "repositories", "consulta": "x"})
	panel.elementos = list(elementos)
	panel.visibles = list(elementos)
	panel.lista.reemplazar_filas([panel.fila_de(e) for e in elementos])
	return panel


def _etiquetas(panel, fila):
	panel.lista.enfocar_fila(fila, anunciar=False)
	return [a.etiqueta.replace("&", "") for a in panel.acciones_disponibles()]


def test_acciones_segun_el_resultado(app_wx, marco, monkeypatch):
	from tests.apoyo_app import crear_contexto

	ctx, api, _a = crear_contexto()
	abiertos = []
	monkeypatch.setattr(pr.abrir, "usuario", lambda c, padre, login: abiertos.append(("usuario", login)))
	monkeypatch.setattr(pr.abrir, "repositorio", lambda c, nombre, seccion="": abiertos.append(("repo", nombre)))
	panel = _panel(marco, ctx, [REPO, ISSUE, USUARIO])

	en_repo = _etiquetas(panel, 0)
	assert "Ver el propietario (perfil, repositorios, seguir)" in en_repo and "Clonar…" in en_repo
	assert "Ir al repositorio" not in en_repo and "Ver al autor" not in en_repo
	panel.ejecutar(next(a for a in panel.acciones_disponibles() if "propietario" in a.etiqueta.replace("&", "")))
	assert abiertos[-1] == ("usuario", "ana")

	en_issue = _etiquetas(panel, 1)
	assert {"Ver al autor", "Ir al repositorio", "Ver el propietario (perfil, repositorios, seguir)"} <= set(en_issue)
	assert "Clonar…" not in en_issue
	panel.ejecutar(next(a for a in panel.acciones_disponibles() if "autor" in a.etiqueta.replace("&", "")))
	panel.ejecutar(next(a for a in panel.acciones_disponibles() if "Ir al" in a.etiqueta.replace("&", "")))
	assert abiertos[-2:] == [("usuario", "luis"), ("repo", "org/app")]

	en_usuario = _etiquetas(panel, 2)
	assert "Seguir o dejar de seguir" in en_usuario and not any("propietario" in t for t in en_usuario)
	api.sigo_a.return_value = False
	panel.ejecutar(next(a for a in panel.acciones_disponibles() if "Seguir" in a.etiqueta.replace("&", "")))
	api.seguir.assert_called_once_with("marta")
	panel.Destroy()


def test_letras_de_acceso_de_la_busqueda_sin_repetir(app_wx, marco):
	from tests.apoyo_app import crear_contexto

	ctx, _api, _a = crear_contexto()
	panel = PanelLista(marco, ctx, pr.vista_busqueda(), {"tipo": "repositories"})
	letras = [letra_de_acceso(a.etiqueta) for a in panel.todas_las_acciones() if "Detener" not in a.etiqueta.replace("&", "")]
	assert None not in letras
	assert not {letra for letra in letras if letras.count(letra) > 1}
	panel.Destroy()
