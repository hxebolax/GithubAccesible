"""Pruebas del buscador: consultas, validación, API (sin red), tendencias, partición y diálogo."""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest import mock

import pytest
import requests

from app.services import busqueda as b
from app.services.github import ApiGitHub
from app.services.github.api_extra import ApiBusqueda
from app.services.github.cliente import ClienteGitHub, ErrorValidacion, Pagina

HOY = date(2026, 11, 21)


# ── Apoyo sin red (como en test_github_cliente.py) ───────────────────────────

def respuesta(codigo=200, cuerpo=None, cabeceras=None):
	r = requests.Response()
	r.status_code = codigo
	r._content = b"" if cuerpo is None else json.dumps(cuerpo).encode()
	r.headers.update(cabeceras or {})
	r.url = "https://api.github.com/x"
	r.encoding = "utf-8"
	return r


class SesionFalsa:
	def __init__(self, respuestas):
		self.respuestas = list(respuestas)
		self.peticiones = []

	def request(self, metodo, url, **opciones):
		self.peticiones.append((metodo, url, opciones))
		return self.respuestas.pop(0)


def api_con(*respuestas):
	sesion = SesionFalsa(respuestas)
	return ApiGitHub(ClienteGitHub("ghp_prueba1234", crear_sesion=lambda: sesion)), sesion


# ── Construcción de consultas ────────────────────────────────────────────────

def test_consulta_de_repositorios():
	consulta = b.construir_consulta("repositories", "lector", {
		"en": ["name", "description"], "propietario": "nvaccess, -spam", "lenguaje": "python", "temas": "a11y, screen-reader",
		"licencia": "mit", "estrellas": ["100", ""], "envio": ["", "2025-01-01"], "buenas_primeras": "0", "patrocinable": True,
		"bifurcados": "fork:only", "excluir": "juego demo",
	})
	assert consulta == ("lector NOT juego NOT demo in:name,description user:nvaccess -user:spam language:python topic:a11y "
		"topic:screen-reader license:mit stars:>=100 pushed:<=2025-01-01 good-first-issues:>0 fork:only is:sponsorable")


def test_consulta_de_issues_al_estilo_de_gh():
	consulta = b.construir_consulta("issues", "crash OR fallo", {
		"tipo": "is:issue", "estado": "is:open", "en": ["title", "body"], "repos": "a/b, c/d", "etiquetas": "bug, -wontfix",
		"creada": ["2026-01-01", "2026-02-01"], "autor": "@me", "comentarios": ["5", "10"], "falta": "no:assignee",
		"motivo": 'reason:"not planned"',
	})
	assert consulta == ('( crash OR fallo ) is:issue is:open reason:"not planned" (in:body OR in:title) (repo:a/b OR repo:c/d) '
		"label:bug -label:wontfix author:@me comments:5..10 created:2026-01-01..2026-02-01 no:assignee")
	assert b.construir_consulta("issues", "fallo", {"estado": "is:closed"}) == "fallo is:closed", "sin operadores, sin paréntesis"


def test_consultas_de_los_demas_tipos():
	assert b.construir_consulta("code", "", {"archivo": "setup.py", "extension": "py", "en": ["path"]}) == "in:path filename:setup.py extension:py"
	assert b.construir_consulta("users", "", {"tipo": "type:org", "ubicacion": "Las Palmas", "seguidores": ["", "50"]}) == \
		'type:org location:"Las Palmas" followers:<=50'
	assert b.construir_consulta("commits", "fix", {"autor": "octocat", "fusion": "merge:false", "fecha_autor": ["2025-01-01", ""]}) == \
		"fix author:octocat merge:false author-date:>=2025-01-01"
	assert b.construir_consulta("topics", "python", {"destacados": "is:featured", "repositorios": ["1000", ""]}) == \
		"python is:featured repositories:>=1000"
	assert b.construir_consulta("discussions", "error", {"respuesta": "is:unanswered", "categoria": "Ideas y dudas", "repos": "a/b, c/d"}) == \
		'error repo:a/b repo:c/d is:unanswered category:"Ideas y dudas"', "fuera de issues, varios repo: se separan con espacios (O implícito)"


def test_preparar_busqueda_parametros_y_tendencias():
	datos = b.preparar_busqueda("trending", "", {"fuente": "api", "periodo": "weekly", "lenguaje": "rust"}, hoy=HOY)
	assert datos["consulta"] == "created:>=2026-11-14 language:rust"
	assert (datos["orden"], datos["direccion"], datos["nombre_tipo"]) == ("stars", "desc", "tendencias")
	web = b.preparar_busqueda("trending", "", {"fuente": "web_repos", "periodo": "monthly", "lenguaje": "c++", "idioma": "es"})
	assert web["consulta"] == "repositorios en tendencia este mes, C++, en español"
	assert web["url_web"] == "https://github.com/trending/c%2B%2B?since=monthly&spoken_language_code=es"
	etiquetas = b.preparar_busqueda("labels", "bug", {"repositorio": "octo/repo"}, orden="created")
	assert (etiquetas["consulta"], etiquetas["repositorio"], etiquetas["orden"]) == ("bug", "octo/repo", "created")
	semantica = b.preparar_busqueda("issues", "se cuelga", {"tipo": "is:issue", "search_type": "semantic"}, orden="comments")
	assert semantica["search_type"] == "semantic" and semantica["orden"] == "", "la semántica no admite orden"
	assert b.preparar_busqueda("code", "x", {}, orden="indexed")["orden"] == "", "orden no válido para el tipo"


def test_atajos_rellenan_los_filtros():
	recientes = b.valores_atajo("recientes", HOY)
	assert recientes == {"envio": [(HOY - timedelta(days=30)).isoformat(), ""]}
	assert b.valores_atajo("populares", HOY)["_orden"] == "stars"
	assert b.valores_atajo("lector", HOY) == {"temas": "screen-reader"}


def test_citar_y_rango():
	assert b.citar("bug fix") == '"bug fix"' and b.citar("bug") == "bug" and b.citar('"ya"') == '"ya"'
	assert (b.rango("1", "5"), b.rango("1", ""), b.rango("", "5"), b.rango("", "")) == ("1..5", ">=1", "<=5", "")


# ── Validación ───────────────────────────────────────────────────────────────

def _claves(problemas):
	return [p.clave for p in problemas]


def test_validacion_de_fechas_y_numeros():
	problemas = b.validar("repositories", "", {"envio": ["2026-02-30", ""], "estrellas": ["10", "5"], "bifurcaciones": ["1.000", ""]})
	assert set(_claves(problemas)) == {"envio", "estrellas", "bifurcaciones"}
	assert any("AAAA-MM-DD" in p.mensaje for p in problemas)
	assert b.validar("repositories", "", {"creado": ["2026-01-01", "2026-02-01"]}) == []
	assert b.validar("repositories", "", {"creado": ["2026-03-01", "2026-02-01"]})[0].clave == "creado"


def test_validacion_de_limites_de_github():
	assert _claves(b.validar("repositories", "x" * 257)) == ["texto"]
	assert b.validar("repositories", "x" * 200 + " language:python stars:>1") == [], "los calificadores no cuentan"
	seis = "a OR b OR c OR d OR e OR f OR g"
	assert any("operadores" in p.mensaje for p in b.validar("issues", seis))
	assert b.contar_operadores('"a OR b" AND c') == 1
	assert _claves(b.validar("repositories", "")) == ["texto"]


def test_validacion_por_tipo():
	assert _claves(b.validar("code", "", {"lenguaje": "python"})) == ["texto"], "código necesita una palabra"
	assert b.validar("code", "", {"archivo": "setup.py"}) == [], "salvo con filename:"
	assert "repositorio" in _claves(b.validar("labels", "bug", {}))
	assert "texto" in _claves(b.validar("labels", "label:bug", {"repositorio": "a/b"}))
	assert b.validar("labels", "bug", {"repositorio": "a/b"}) == []
	assert _claves(b.validar("issues", "algo", {"search_type": "hybrid"})) == ["tipo"]
	assert b.validar("issues", "algo", {"search_type": "hybrid", "tipo": "is:issue"}) == []
	assert _claves(b.validar("issues", "x", {"repos": "solo-nombre"})) == ["repos"]
	assert b.validar("trending", "", {"fuente": "web_devs"}) == []


# ── Navegador y errores ──────────────────────────────────────────────────────

def test_url_del_navegador():
	assert b.url_navegador("repositories", "lector stars:>10", orden="stars") == \
		"https://github.com/search?q=lector+stars%3A%3E10&type=repositories&s=stars&o=desc"
	datos = b.preparar_busqueda("issues", "x", {"tipo": "is:pr"})
	assert "type=pullrequests" in datos["url_web"]
	assert b.preparar_busqueda("discussions", "x", {})["url_web"].endswith("type=discussions")
	assert b.url_navegador("code", "x", host="git.empresa.es") == "https://git.empresa.es/search?q=x&type=code"
	assert b.preparar_busqueda("labels", "bug", {"repositorio": "a/b"})["url_web"] == "https://github.com/a/b/labels?q=bug"
	assert b.url_tendencias("web_devs", "weekly", "python", "es") == "https://github.com/trending/developers/python?since=weekly"


def test_traduccion_de_errores_422():
	error = ErrorValidacion("GitHub ha rechazado los datos enviados.", 422, "GET /search → HTTP 422: Validation Failed",
		[{"message": "The listed users and repositories cannot be searched either because the resources do not exist or you do not have permission to view them."}])
	assert "no existe" in b.traducir_error_busqueda(error)
	otro = ErrorValidacion("x", 422, "Only the first 1000 search results are available")
	assert "1000" in b.traducir_error_busqueda(otro)
	assert b.traducir_error_busqueda(ErrorValidacion("Sin red", 500)) == "Sin red"


# ── ApiBusqueda: text-match, incomplete_results, semántica, etiquetas ─────────

def test_text_match_en_todos_los_tipos_e_incompleto():
	cuerpo = {"total_count": 3, "incomplete_results": True, "items": [{"id": 1, "text_matches": [{"property": "description", "fragment": "x"}]}]}
	api, sesion = api_con(respuesta(200, cuerpo))
	pagina = api.buscar("repositories", "wx")
	_metodo, url, opciones = sesion.peticiones[0]
	assert url.endswith("/search/repositories")
	assert opciones["headers"]["Accept"] == "application/vnd.github.text-match+json"
	assert pagina.incompleto is True and pagina.total == 3
	assert Pagina([1]).incompleto is None, "Pagina sigue funcionando sin el campo nuevo"


def test_busqueda_semantica_sin_orden():
	api, sesion = api_con(respuesta(200, {"total_count": 0, "items": []}))
	api.buscar("issues", "se cuelga al abrir", orden="created", search_type="semantic")
	parametros = sesion.peticiones[0][2]["params"]
	assert parametros["search_type"] == "semantic" and parametros["advanced_search"] == "true"
	assert "sort" not in parametros and "order" not in parametros


def test_etiquetas_resuelven_el_id_del_repositorio():
	ApiBusqueda._ids_repositorio.clear()
	api, sesion = api_con(respuesta(200, {"id": 42, "full_name": "a/b"}), respuesta(200, {"total_count": 1, "items": [{"name": "bug"}]}))
	pagina = api.buscar("labels", "bug", orden="created", repositorio="a/b")
	assert sesion.peticiones[0][1].endswith("/repos/a/b")
	assert sesion.peticiones[1][2]["params"]["repository_id"] == 42
	assert pagina.elementos == [{"name": "bug"}]
	with pytest.raises(ErrorValidacion):
		api.buscar("labels", "bug")


def test_error_422_de_busqueda_en_espanol():
	api, _s = api_con(respuesta(422, {"message": "Validation Failed", "errors": [{"message": "Only the first 1000 search results are available"}]}))
	with pytest.raises(ErrorValidacion) as error:
		api.buscar("repositories", "x", 21)
	assert "1000" in error.value.mensaje_usuario and "Traer todos" in error.value.mensaje_usuario


def test_resumen_de_coincidencias():
	elemento = {"text_matches": [
		{"property": "body", "fragment": "Al abrir   el lector\nse cuelga", "matches": [{"text": "lector"}]},
		{"property": "title", "fragment": "Fallo con NVDA"},
	]}
	assert b.resumen_coincidencias(elemento) == "En el cuerpo: «Al abrir el lector se cuelga»; en el título: «Fallo con NVDA»"
	largo = {"text_matches": [{"property": "content", "fragment": "x " * 200 + "AQUI" + " y" * 200, "matches": [{"text": "AQUI"}]}]}
	texto = b.resumen_coincidencias(largo, largo=40)
	assert "AQUI" in texto and texto.count("…") == 2
	assert b.resumen_coincidencias({}) == ""


# ── Discusiones por GraphQL ──────────────────────────────────────────────────

def test_discusiones_por_graphql_con_cursor():
	datos = {"data": {"search": {
		"discussionCount": 1234,
		"pageInfo": {"hasNextPage": True, "endCursor": "Y3Vyc29y"},
		"edges": [{"textMatches": [{"fragment": "cómo se instala", "property": "title", "highlights": [{"text": "instala"}]}],
			"node": {"id": "D_1", "number": 7, "title": "¿Cómo se instala?", "url": "https://github.com/a/b/discussions/7",
				"closed": False, "isAnswered": True, "upvoteCount": 3, "author": {"login": "ana"}, "category": {"name": "Q&A"},
				"comments": {"totalCount": 2}, "repository": {"nameWithOwner": "a/b"}, "labels": {"nodes": []}}},
			{"node": {}}],
	}}}
	api, sesion = api_con(respuesta(200, datos))
	pagina = api.buscar_discusiones("instala repo:a/b", 30, "anterior")
	cuerpo = sesion.peticiones[0][2]["json"]
	assert "type: DISCUSSION" in cuerpo["query"] and cuerpo["variables"] == {"q": "instala repo:a/b", "n": 30, "despues": "anterior"}
	assert pagina.total == 1234 and pagina.siguiente == "Y3Vyc29y" and pagina.hay_mas
	assert len(pagina.elementos) == 1
	discusion = pagina.elementos[0]
	assert discusion["_tipo"] == "discusion" and discusion["html_url"].endswith("/7")
	assert b.resumen_coincidencias(discusion) == "En el título: «cómo se instala»"


# ── Tendencias ───────────────────────────────────────────────────────────────

HTML_TENDENCIAS = """<!DOCTYPE html><html><body><main>
<div class="Box">
<article class="Box-row">
  <div class="float-right d-flex"><a href="/login?return_to=%2Fnvaccess%2Fnvda" class="btn">Star</a></div>
  <h2 class="h3 lh-condensed">
    <a data-view-component="true" class="Link" href="/nvaccess/nvda">
      <svg aria-hidden="true"></svg>
      <span data-view-component="true" class="text-normal">nvaccess /</span>
      nvda
    </a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">
    NVDA, the free and open source Screen Reader for Microsoft Windows
  </p>
  <div class="f6 color-fg-muted mt-2">
    <span class="d-inline-block ml-0 mr-3">
      <span class="repo-language-color" style="background-color: #3572A5"></span>
      <span itemprop="programmingLanguage">Python</span>
    </span>
    <a href="/nvaccess/nvda/stargazers" class="Link Link--muted d-inline-block mr-3"><svg aria-label="star"></svg> 2,345</a>
    <a href="/nvaccess/nvda/forks" class="Link Link--muted d-inline-block mr-3"><svg aria-label="fork"></svg> 678</a>
    <span class="d-inline-block mr-3">Built by
      <a href="/ana" class="d-inline-block"><img class="avatar mb-1 avatar-user" src="x.png" alt="@ana" width="20" height="20"/></a>
      <a href="/luis" class="d-inline-block"><img class="avatar mb-1 avatar-user" src="y.png" alt="@luis"></a>
    </span>
    <span class="d-inline-block float-sm-right"><svg></svg> 123 stars today</span>
  </div>
</article>
<article class="Box-row">
  <h2 class="h3 lh-condensed"><a class="Link" href="/octo/sin-descripcion"><span class="text-normal">octo /</span> sin-descripcion</a></h2>
  <div class="f6 color-fg-muted mt-2">
    <a href="/octo/sin-descripcion/stargazers" class="Link">1.024</a>
    <span class="d-inline-block float-sm-right">9 stars today</span>
  </div>
</article>
</div></main></body></html>"""

HTML_DESARROLLADORES = """<html><body><div class="Box">
<article class="Box-row d-flex" id="pa-ana">
  <a class="color-fg-muted f6" href="#pa-ana">1</a>
  <div class="mx-3"><a href="/ana"><img class="rounded avatar-user" src="a.png" width="48" height="48" alt="@ana"></a></div>
  <div class="d-sm-flex flex-auto">
    <div class="col-sm-8 d-md-flex">
      <div class="col-md-6">
        <h1 class="h3 lh-condensed"><a href="/ana" class="Link">Ana López</a></h1>
        <p class="f4 text-normal mb-1"><a class="Link--secondary" href="/ana">ana</a></p>
      </div>
      <div class="col-md-6">
        <div class="mt-2 mb-3 my-md-0">
          <article>
            <h1 class="h4 lh-condensed"><svg></svg> Popular repo</h1>
            <h1 class="h4 lh-condensed"><a class="css-truncate" href="/ana/lector">lector</a></h1>
            <div class="f6 color-fg-muted mt-1">Un lector de pantalla de ejemplo</div>
          </article>
        </div>
      </div>
    </div>
  </div>
</article>
</div></body></html>"""


def test_analizador_de_tendencias_de_repositorios():
	repos = b.analizar_tendencias(HTML_TENDENCIAS, "repositorios")
	assert [r["full_name"] for r in repos] == ["nvaccess/nvda", "octo/sin-descripcion"]
	nvda = repos[0]
	assert nvda["description"].startswith("NVDA, the free")
	assert (nvda["language"], nvda["stargazers_count"], nvda["forks_count"], nvda["estrellas_periodo"]) == ("Python", 2345, 678, 123)
	assert nvda["construido_por"] == ["ana", "luis"] and nvda["html_url"] == "https://github.com/nvaccess/nvda"
	assert nvda["periodo_texto"] == "123 stars today"
	assert repos[1]["description"] == "" and repos[1]["stargazers_count"] == 1024


def test_analizador_de_tendencias_de_desarrolladores():
	(ana,) = b.analizar_tendencias(HTML_DESARROLLADORES, "desarrolladores")
	assert (ana["login"], ana["name"], ana["repo_popular"]) == ("ana", "Ana López", "ana/lector")
	assert ana["descripcion_repo"] == "Un lector de pantalla de ejemplo"


def test_tendencias_formato_cambiado_y_vacias():
	with pytest.raises(b.ErrorTendencias) as error:
		b.analizar_tendencias("<html><body><ul><li>Otra cosa</li></ul></body></html>")
	assert "formato ha cambiado" in error.value.mensaje_usuario
	with pytest.raises(b.ErrorTendencias):
		b.analizar_tendencias('<article class="Box-row"><p>sin nombre</p></article>')
	assert b.analizar_tendencias("<div>It looks like we don’t have any trending repositories for Zig.</div>") == []


def test_tendencias_con_cache_de_una_hora():
	b.vaciar_cache_tendencias()
	pedidas = []

	def obtener(url):
		pedidas.append(url)
		return HTML_TENDENCIAS

	reloj = iter([0.0, 10.0, 4000.0])
	for _vez in range(3):
		repos = b.leer_tendencias("web_repos", "weekly", "python", "es", obtener=obtener, ahora=lambda: next(reloj))
		assert repos[0]["full_name"] == "nvaccess/nvda"
	assert pedidas == ["https://github.com/trending/python?since=weekly&spoken_language_code=es"] * 2, "la segunda sale de la caché"
	b.vaciar_cache_tendencias()


def test_api_de_tendencias_solo_en_github_com():
	api = ApiGitHub(ClienteGitHub("ghp_x123456", host="git.empresa.es", crear_sesion=SesionFalsa))
	with pytest.raises(Exception, match="github.com"):
		api.tendencias()
	b.vaciar_cache_tendencias()
	api_publica = ApiGitHub(ClienteGitHub("ghp_x123456", crear_sesion=SesionFalsa))
	assert api_publica.tendencias("web_devs", obtener=lambda url: HTML_DESARROLLADORES)[0]["login"] == "ana"
	b.vaciar_cache_tendencias()


def test_filtrar_tendencias_en_local():
	repos = b.analizar_tendencias(HTML_TENDENCIAS)
	assert [r["full_name"] for r in b.filtrar_local(repos, "SCREEN reader")] == ["nvaccess/nvda"]
	assert b.filtrar_local(repos, "") == repos


# ── «Traer todos»: partición por fechas ──────────────────────────────────────

def _buscador_falso(por_dia: dict[date, int]):
	"""Simula la API: cada día tiene N resultados; respeta el tope de 1000 y las páginas de 100."""
	peticiones = []

	def buscar(consulta, numero):
		peticiones.append((consulta, numero))
		intervalo = consulta.split("created:")[1]
		desde, _sep, hasta = intervalo.partition("..")
		inicio, fin = date.fromisoformat(desde), date.fromisoformat(hasta or desde)
		elementos = [{"id": f"{d.isoformat()}-{i}"} for d, n in sorted(por_dia.items()) if inicio <= d <= fin for i in range(n)]
		visibles = elementos[:1000]
		trozo = visibles[(numero - 1) * 100:numero * 100]
		return Pagina(trozo, "siguiente" if numero * 100 < len(visibles) else "", None, len(elementos), numero)

	return buscar, peticiones


def test_traer_todos_parte_el_intervalo():
	por_dia = {date(2026, 1, 1) + timedelta(days=i): 300 for i in range(10)}  # 3000 resultados
	buscar, peticiones = _buscador_falso(por_dia)
	resultado = b.traer_todos(buscar, "lector created:2026-01-01..2026-01-10", "created", hoy=HOY)
	assert len(resultado.elementos) == 3000 and not resultado.avisos and not resultado.cancelado
	assert all(c.startswith("lector created:") for c, _n in peticiones)
	assert resultado.peticiones == len(peticiones)
	assert b.estimar_peticiones(3000) >= 30


def test_traer_todos_se_puede_cancelar_y_avisa_de_dias_llenos():
	buscar, _p = _buscador_falso({date(2026, 1, 1): 1500})
	resultado = b.traer_todos(buscar, "x created:2026-01-01", "created", hoy=HOY)
	assert len(resultado.elementos) == 1000 and any("2026-01-01" in a for a in resultado.avisos)
	buscar2, peticiones2 = _buscador_falso({date(2026, 1, 1): 50})
	cancelado = b.traer_todos(buscar2, "x", "created", hoy=HOY, cancelado=lambda: True)
	assert cancelado.cancelado and not peticiones2


def test_extraer_intervalo():
	assert b.extraer_intervalo("a created:>=2026-01-01 b", "created", HOY) == ("a b", date(2026, 1, 1), HOY)
	assert b.extraer_intervalo("a created:<2026-01-10", "created", HOY) == ("a", b.INICIO_GITHUB, date(2026, 1, 9))
	assert b.extraer_intervalo("a", "author-date", HOY) == ("a", b.INICIO_GITHUB, HOY)


# ── Letras de acceso ─────────────────────────────────────────────────────────

def test_asignar_letras_sin_repetir():
	etiquetas = b.asignar_letras(["Estrellas, mínimo:", "Estrellas, máximo:", "&Ordenar por:", "Lenguaje:", "Bifurcaciones:"], set("btlunjsc"))
	letras = [b.letra_de(e) for e in etiquetas]
	assert None not in letras and len(set(letras)) == len(letras)
	assert not set(letras) & set("btlunjsc")
	assert etiquetas[2] == "&Ordenar por:"
	assert b.asignar_letras(["ab:", "ab:", "ab:"], set()) == ["&ab:", "a&b:", "ab (&1):"]


# ── Diálogo ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tipo", list(b.TIPOS))
def test_dialogo_teclado_correcto_en_cada_tipo(app_wx, tipo):
	from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto
	from app.ui.busqueda import DialogoBusqueda
	from tests.apoyo_app import crear_contexto

	ctx, _api, _a = crear_contexto()
	dialogo = DialogoBusqueda(None, ctx)
	try:
		dialogo.tipo.SetSelection(list(b.TIPOS).index(tipo))
		dialogo._al_cambiar_tipo()
		afirmar_teclado_correcto(dialogo)
		paginas = [dialogo.libro.GetPageText(i) for i in range(dialogo.libro.GetPageCount())]
		assert paginas[-1] == "Historial y guardadas"
		assert paginas[:-1] == [b.PAGINAS[p] for p in b.paginas_de(tipo)]
		assert dialogo.valores()["tipo"] == tipo
		if tipo == "trending":
			for fuente in ("web_repos", "web_devs"):
				dialogo._poner_filtros({"fuente": fuente})
				dialogo._actualizar_estado_controles()
				afirmar_teclado_correcto(dialogo)
	finally:
		dialogo.Destroy()


def test_dialogo_consulta_resultante_y_valores(app_wx):
	from app.ui.busqueda import DialogoBusqueda
	from tests.apoyo_app import crear_contexto

	ctx, _api, _a = crear_contexto()
	dialogo = DialogoBusqueda(None, ctx)
	try:
		assert dialogo.valores()["tipo"] == "repositories"
		dialogo.consulta.SetValue("lector")
		dialogo._poner_filtros({"lenguaje": "python", "estrellas": ["100", ""]})
		dialogo._actualizar_resultado()
		assert dialogo.resultado.GetValue().splitlines()[0] == "lector language:python stars:>=100"
		datos = dialogo.valores()
		for clave in ("tipo", "nombre_tipo", "consulta", "orden", "direccion", "search_type", "url_web", "filtros"):
			assert clave in datos
		# El atajo «Populares» rellena las estrellas y el orden.
		filtro, (control,) = dialogo.controles["categoria"]
		indice = [c for c, _n in filtro.opciones].index("populares")
		control.SetSelection(indice)
		evento = mock.Mock(GetSelection=lambda: indice)
		dialogo._al_cambiar_desplegable(filtro, evento)
		assert dialogo.valores()["orden"] == "stars" and dialogo.valores_filtros()["estrellas"] == ["1000", ""]
		# Al pasar a issues se conserva el lenguaje.
		dialogo.tipo.SetSelection(list(b.TIPOS).index("issues"))
		dialogo._al_cambiar_tipo()
		assert dialogo.valores_filtros()["lenguaje"] == "python"
		# La búsqueda semántica desactiva el orden y avisa si falta «Solo issues».
		dialogo._poner_filtros({"search_type": "semantic"})
		dialogo._actualizar_estado_controles()
		dialogo._actualizar_resultado()
		assert not dialogo.orden.IsEnabled()
		assert "Problema:" in dialogo.resultado.GetValue()
	finally:
		dialogo.Destroy()


def test_dialogo_carga_historial_antiguo_y_guarda_busquedas(app_wx, monkeypatch):
	from app.ui import busqueda as dialogos
	from tests.apoyo_app import crear_contexto

	ctx, _api, _a = crear_contexto()
	ctx.config.establecer("busqueda.historial", [{"tipo": "repositories", "texto": "x", "categoria": "populares", "valor": "500",
		"lenguaje": "rust", "licencia": "mit", "consulta": "x stars:>500 license:mit language:rust"}])
	dialogo = dialogos.DialogoBusqueda(None, ctx)
	try:
		dialogo.selector_historial.SetSelection(1)
		dialogo._al_elegir_historial(None)
		assert dialogo.valores()["consulta"] == "x language:rust license:mit stars:>=500"
		monkeypatch.setattr(dialogos, "pedir_texto", lambda *a, **k: "Mis rust")
		dialogo._al_guardar(None)
		guardadas = ctx.config.obtener("busqueda.guardadas")
		assert guardadas[0]["nombre"] == "Mis rust" and guardadas[0]["filtros"]["lenguaje"] == "rust"
		assert dialogo.selector_guardadas.GetSelection() == 1
		monkeypatch.setattr(dialogos, "pedir_texto", lambda *a, **k: "Rust populares")
		dialogo._al_renombrar(None)
		assert ctx.config.obtener("busqueda.guardadas")[0]["nombre"] == "Rust populares"
		monkeypatch.setattr(dialogos, "confirmar", lambda *a, **k: dialogos.wx.ID_YES)
		dialogo._al_borrar(None)
		assert ctx.config.obtener("busqueda.guardadas") == []
	finally:
		dialogo.Destroy()


def test_dialogo_no_busca_si_hay_problemas(app_wx, monkeypatch):
	from app.ui import busqueda as dialogos
	from tests.apoyo_app import crear_contexto

	ctx, _api, _a = crear_contexto()
	dialogo = dialogos.DialogoBusqueda(None, ctx)
	errores = []
	monkeypatch.setattr(dialogos, "mostrar_error", lambda padre, mensaje, titulo="": errores.append(mensaje))
	monkeypatch.setattr(dialogo, "EndModal", lambda codigo: errores.append(codigo))
	try:
		dialogo._poner_filtros({"envio": ["2026-13-01", ""]})
		dialogo._al_buscar()
		assert "AAAA-MM-DD" in errores[0] and len(errores) == 1
		dialogo._poner_filtros({"envio": ["2026-01-01", ""]})
		dialogo._al_buscar()
		assert errores[-1] == dialogos.wx.ID_OK
	finally:
		dialogo.Destroy()


# ── Vista de resultados ──────────────────────────────────────────────────────

def test_vista_columnas_por_tipo_y_aviso_de_1000(marco):
	from app.ui.vistas.base import PanelLista
	from app.ui.vistas.principales import vista_busqueda
	from tests.apoyo_app import crear_contexto
	from tests.ayudas_wx import procesar_eventos

	ctx, api, _a = crear_contexto()
	api.buscar.return_value = Pagina([{"full_name": "a/b", "description": "d", "text_matches": [{"property": "name", "fragment": "b"}]}],
		"sig", None, 25000, 1, True)
	panel = PanelLista(marco, ctx, vista_busqueda())
	panel.datos.update(b.preparar_busqueda("repositories", "b", {}))
	panel.cargar()
	procesar_eventos()
	ids = [c.id for c in panel.columnas]
	assert "coincidencias" in ids and "estrellas" in ids
	assert "1000" in panel.etiqueta.GetLabel() and "25.000" in panel.etiqueta.GetLabel()
	assert "falten" in panel.etiqueta.GetLabel()
	assert panel.fila_de(panel.elementos[0])[ids.index("coincidencias")] == "En el nombre: «b»"
	# Discusiones: columnas propias y cursor para la página siguiente.
	api.buscar_discusiones.return_value = Pagina([{"_tipo": "discusion", "number": 3, "title": "t", "url": "u", "html_url": "u",
		"repository": {"nameWithOwner": "a/b"}, "category": {"name": "Ideas"}, "comments": {"totalCount": 4}}], "CURSOR", None, 1)
	panel.datos.update(b.preparar_busqueda("discussions", "t", {}))
	panel.cargar()
	procesar_eventos()
	assert "categoria" in [c.id for c in panel.columnas]
	assert panel.datos["_cursores"][2] == "CURSOR"
	panel.cargar(reiniciar=False)
	assert api.buscar_discusiones.call_args_list[0].args[2] is None, "la primera página va sin cursor"
	assert api.buscar_discusiones.call_args.args[2] == "CURSOR", "las siguientes usan el cursor de la anterior"
	# Tendencias de la página: columnas propias y filtro local por el texto.
	api.tendencias.return_value = b.analizar_tendencias(HTML_TENDENCIAS)
	panel.datos.update(b.preparar_busqueda("trending", "screen", {"fuente": "web_repos", "periodo": "weekly"}))
	panel.cargar()
	procesar_eventos()
	assert [c.id for c in panel.columnas][:3] == ["nombre", "descripcion", "lenguaje"]
	assert [e["full_name"] for e in panel.elementos] == ["nvaccess/nvda"]
