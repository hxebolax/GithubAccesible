"""Pruebas de las plantillas y formularios de issue (sin wx) y de su lectura desde la API (sin red)."""

from __future__ import annotations

import base64
import json
import math
import textwrap

import pytest
import requests

from app.services import plantillas as pl
from app.services.github import ApiGitHub
from app.services.github.cliente import ClienteGitHub, ErrorValidacion

FORMULARIO = textwrap.dedent("""\
	name: Informe de fallo
	description: Algo no funciona como debería.
	title: "[Fallo]: "
	labels: ["fallo", "por clasificar"]
	assignees:
	  - ana
	type: Bug
	body:
	  - type: markdown
	    attributes:
	      value: |
	        Gracias por avisar.

	        Revise antes las issues abiertas.
	  - type: input
	    id: version
	    attributes:
	      label: Versión
	      description: La que sale en Acerca de.
	      placeholder: "1.0.4"
	    validations:
	      required: true
	  - type: textarea
	    id: registro
	    attributes:
	      label: Registro
	      render: shell
	  - type: textarea
	    attributes:
	      label: Qué pasó
	      value: Al abrir…
	  - type: dropdown
	    id: sistema
	    attributes:
	      label: Sistema
	      multiple: true
	      options:
	        - Windows 10
	        - Windows 11
	      default: 1
	  - type: dropdown
	    id: lector
	    attributes:
	      label: Lector de pantalla
	      options: [NVDA, JAWS, Narrador]
	    validations:
	      required: true
	  - type: checkboxes
	    id: normas
	    attributes:
	      label: Normas
	      options:
	        - label: He leído el código de conducta
	          required: true
	        - label: Quiero ayudar a arreglarlo
""").replace("\t", "")


# ════════════════════════════════════════════════════════════════════════════
# Lector de YAML
# ════════════════════════════════════════════════════════════════════════════


def test_mapas_listas_y_escalares():
	texto = textwrap.dedent("""\
		# comentario inicial
		nombre: Hola mundo   # comentario al final
		comillas: "dos: puntos # no es comentario"
		simples: 'it''s'
		escapes: "a\\tb\\n\\u00e9"
		vacio:
		nulo: ~
		verdad: true
		mentira: False
		si: yes
		entero: 42
		negativo: -7
		real: 1.5
		hex: 0x1F
		infinito: .inf
		almohadilla: C#sharp
		url: https://github.com/ana/proyecto
		lista:
		  - uno
		  - "dos"
		  -
		    anidado: sí
		misma_altura:
		- a
		- b
		en_linea: [x, "y, z", 3, {k: v}]
		mapa_en_linea: {name: Foro, url: "https://x"}
		vacia: []
	""")
	datos = pl.leer_yaml(texto)
	assert datos["nombre"] == "Hola mundo"
	assert datos["comillas"] == "dos: puntos # no es comentario"
	assert datos["simples"] == "it's"
	assert datos["escapes"] == "a\tb\né"
	assert datos["vacio"] is None and datos["nulo"] is None
	assert datos["verdad"] is True and datos["mentira"] is False
	assert datos["si"] == "yes", "yes y no son texto (YAML 1.2): en un desplegable son opciones"
	assert (datos["entero"], datos["negativo"], datos["real"], datos["hex"]) == (42, -7, 1.5, 31)
	assert datos["infinito"] == math.inf
	assert datos["almohadilla"] == "C#sharp"
	assert datos["url"] == "https://github.com/ana/proyecto"
	assert datos["lista"] == ["uno", "dos", {"anidado": "sí"}]
	assert datos["misma_altura"] == ["a", "b"]
	assert datos["en_linea"] == ["x", "y, z", 3, {"k": "v"}]
	assert datos["mapa_en_linea"] == {"name": "Foro", "url": "https://x"}
	assert datos["vacia"] == []


def test_bloques_literal_y_plegado_con_recortes():
	texto = textwrap.dedent("""\
		literal: |
		  línea 1
		    sangrada

		  línea 3
		recortado: |-
		  sin salto final
		conservado: |+
		  con saltos

		plegado: >
		  una
		  frase

		  otro párrafo
		    código
		  fin
		plegado_sin_salto: >-
		  a
		  b
		explicito: |2
		    dos de más
		siguiente: ok
	""")
	datos = pl.leer_yaml(texto)
	assert datos["literal"] == "línea 1\n  sangrada\n\nlínea 3\n"
	assert datos["recortado"] == "sin salto final"
	assert datos["conservado"] == "con saltos\n\n"
	assert datos["plegado"] == "una frase\notro párrafo\n  código\nfin\n"
	assert datos["plegado_sin_salto"] == "a b"
	assert datos["explicito"] == "  dos de más\n"
	assert datos["siguiente"] == "ok"


def test_escalares_en_varias_lineas_y_documento():
	texto = textwrap.dedent("""\
		%YAML 1.2
		---
		plano: esto sigue
		  en otra línea

		  y en otro párrafo
		comillas: "uno
		  dos"
		lista: [a,
		  b]
		---
		otro: documento
	""")
	datos = pl.leer_yaml(texto)
	assert datos == {"plano": "esto sigue en otra línea\ny en otro párrafo", "comillas": "uno dos", "lista": ["a", "b"]}
	assert pl.leer_yaml("") is None
	assert pl.leer_yaml("# solo comentarios\n") is None
	assert pl.leer_yaml("texto suelto") == "texto suelto"
	assert pl.leer_yaml("- a\n- b\n") == ["a", "b"]


def test_listas_de_mapas_como_en_los_formularios():
	datos = pl.leer_yaml(FORMULARIO)
	assert datos["labels"] == ["fallo", "por clasificar"]
	cuerpo = datos["body"]
	assert [e["type"] for e in cuerpo] == ["markdown", "input", "textarea", "textarea", "dropdown", "dropdown", "checkboxes"]
	assert cuerpo[0]["attributes"]["value"] == "Gracias por avisar.\n\nRevise antes las issues abiertas.\n"
	assert cuerpo[1]["validations"] == {"required": True}
	assert cuerpo[1]["attributes"]["placeholder"] == "1.0.4"
	assert cuerpo[6]["attributes"]["options"][0] == {"label": "He leído el código de conducta", "required": True}


def test_lista_entre_corchetes_cerrada_a_la_altura_de_la_clave():
	"""Como en la plantilla de errores de NVDA: «options: [» en varias líneas, coma final y «]» bajo la clave."""
	texto = textwrap.dedent("""\
		attributes:
		  options: [
		    "No he reiniciado",
		    "Sigue tras reiniciar",
		  ]
		  label: Reinicio
		""")
	assert pl.leer_yaml(texto) == {"attributes": {"options": ["No he reiniciado", "Sigue tras reiniciar"], "label": "Reinicio"}}


@pytest.mark.parametrize("texto, linea, motivo", [
	("a: 1\n  b: 2\n", 2, "sangría"),
	("a: \"sin cerrar\n", 1, "comillas"),
	("a: [1, 2\nb: 3\n", 1, "cerrar"),
	("a:\n\t- b\n", 2, "tabulaciones"),
	("- a\nb: 1\n", 2, "sobra"),
	("a: |x\n  b\n", 1, "cabecera"),
	('a: "\\q"\n', 1, "escape"),
])
def test_errores_dicen_la_linea(texto, linea, motivo):
	with pytest.raises(pl.ErrorYaml) as error:
		pl.leer_yaml(texto)
	assert error.value.linea == linea
	assert motivo in str(error.value)


def test_coincide_con_pyyaml():
	"""Contraste con PyYAML si está instalado (no es una dependencia del proyecto)."""
	yaml = pytest.importorskip("yaml")
	casos = [FORMULARIO, "a: |\n  x\n\n  y\nb: >-\n  p\n  q\nc: [1, 'd', {e: f}]\nd: ~\n", "- - a\n  - b\n- c: d\n  e: 1.5\n"]
	for texto in casos:
		assert pl.leer_yaml(texto) == yaml.safe_load(texto)


# ════════════════════════════════════════════════════════════════════════════
# Plantillas Markdown
# ════════════════════════════════════════════════════════════════════════════


def test_plantilla_markdown_con_cabecera():
	texto = "---\nname: Petición\nabout: Una idea nueva\ntitle: '[Idea] '\nlabels: mejora, idea\nassignees: ''\ntype: Feature\n---\n\n## Qué propone\n"
	plantilla = pl.leer_plantilla("idea.md", texto)
	assert (plantilla.nombre, plantilla.descripcion, plantilla.titulo) == ("Petición", "Una idea nueva", "[Idea] ")
	assert plantilla.etiquetas == ["mejora", "idea"] and plantilla.asignados == [] and plantilla.tipo == "Feature"
	assert plantilla.cuerpo == "## Qué propone\n" and not plantilla.formulario
	assert pl.describir_plantilla(plantilla) == "Petición: Una idea nueva"


def test_plantilla_markdown_sin_cabecera_o_con_cabecera_rota():
	sin = pl.leer_plantilla("docs/sin_cabecera.md", "Texto\n---\nmás")
	assert sin.nombre == "sin_cabecera" and sin.cuerpo == "Texto\n---\nmás"
	rota = pl.leer_plantilla("rota.md", "---\nname: [sin cerrar\n---\nCuerpo")
	assert rota.nombre == "rota" and rota.cuerpo == "Cuerpo", "una cabecera ilegible no impide usar el cuerpo"
	assert pl.separar_cabecera("---\n---\nX") == ("", "X")
	assert pl.lista_de_textos(["a", " b ", "a", None]) == ["a", "b"]


# ════════════════════════════════════════════════════════════════════════════
# Formularios
# ════════════════════════════════════════════════════════════════════════════


def test_formulario_completo():
	plantilla = pl.leer_plantilla("fallo.yml", FORMULARIO)
	assert plantilla.formulario and plantilla.nombre == "Informe de fallo" and plantilla.titulo == "[Fallo]: "
	assert plantilla.etiquetas == ["fallo", "por clasificar"] and plantilla.asignados == ["ana"] and plantilla.tipo == "Bug"
	assert pl.describir_plantilla(plantilla) == "Informe de fallo (formulario): Algo no funciona como debería."
	markdown, version, registro, que_paso, sistema, lector, normas = plantilla.elementos
	assert not markdown.pregunta and markdown.valor.startswith("Gracias")
	assert version.clave == "version" and version.obligatorio and version.marcador == "1.0.4"
	assert version.descripcion == "La que sale en Acerca de."
	assert registro.render == "shell" and not registro.obligatorio
	assert que_paso.clave == "campo_3" and que_paso.valor == "Al abrir…"
	assert sistema.multiple and sistema.opciones == ["Windows 10", "Windows 11"] and sistema.por_defecto == 1
	assert lector.obligatorio and not lector.multiple and lector.por_defecto is None
	assert [(c.etiqueta, c.obligatoria) for c in normas.casillas] == [
		("He leído el código de conducta", True), ("Quiero ayudar a arreglarlo", False)]


def test_cuerpo_compuesto_como_en_la_web():
	plantilla = pl.leer_plantilla("fallo.yaml", FORMULARIO)
	cuerpo = pl.componer_cuerpo(plantilla, {
		"version": "1.0.4", "registro": "Traceback\n  línea 1\n", "campo_3": "   ",
		"sistema": ["Windows 10", "Windows 11"], "lector": [], "normas": [True, False],
	})
	assert cuerpo == (
		"### Versión\n\n1.0.4\n\n"
		"### Registro\n\n```shell\nTraceback\n  línea 1\n```\n\n"
		"### Qué pasó\n\n_No response_\n\n"
		"### Sistema\n\nWindows 10, Windows 11\n\n"
		"### Lector de pantalla\n\n_No response_\n\n"
		"### Normas\n\n- [x] He leído el código de conducta\n- [ ] Quiero ayudar a arreglarlo"
	)
	vacio = pl.componer_cuerpo(plantilla, {})
	assert "### Registro\n\n_No response_" in vacio, "un registro vacío no va en un bloque de código"


def test_obligatorios_que_faltan():
	plantilla = pl.leer_plantilla("fallo.yml", FORMULARIO)
	faltas = pl.faltan_obligatorios(plantilla, {"version": " ", "lector": [], "normas": [False, True]})
	assert [f.texto for f in faltas] == ["Versión", "Lector de pantalla", "Normas: He leído el código de conducta"]
	assert faltas[2].opcion == 0
	assert pl.describir_faltas(faltas[:1]) == "Falta rellenar el campo obligatorio «Versión»."
	assert pl.describir_faltas(faltas).startswith("Faltan 3 campos obligatorios: «Versión»")
	assert pl.faltan_obligatorios(plantilla, {"version": "1", "lector": ["NVDA"], "normas": [True, False]}) == []


@pytest.mark.parametrize("texto, motivo", [
	("name: x\n", "no tiene campos"),
	("body:\n  - type: radio\n", "tipo desconocido"),
	("body: [1]\n", "no es un mapa"),
	("- a\n", "no es un formulario"),
	("body:\n  - type: input\n    attributes: {label: \"x\n", "no se puede leer"),
])
def test_formulario_mal_escrito(texto, motivo):
	with pytest.raises(pl.ErrorPlantilla) as error:
		pl.leer_plantilla("malo.yml", texto)
	assert motivo in str(error.value)
	plantillas, errores = pl.leer_plantillas([("malo.yml", texto), ("bien.md", "Hola")])
	assert [p.archivo for p in plantillas] == ["bien.md"] and len(errores) == 1


# ════════════════════════════════════════════════════════════════════════════
# config.yml y avisos
# ════════════════════════════════════════════════════════════════════════════


def test_config_de_las_plantillas():
	config = pl.leer_config(textwrap.dedent("""\
		blank_issues_enabled: false
		contact_links:
		  - name: Foro
		    url: https://github.com/orgs/ana/discussions
		    about: Preguntas y ayuda
		  - name: Sin url
		  - url: https://ejemplo.org
	"""))
	assert not config.en_blanco
	assert [(e.nombre, e.url, e.descripcion) for e in config.enlaces] == [
		("Foro", "https://github.com/orgs/ana/discussions", "Preguntas y ayuda"),
		("https://ejemplo.org", "https://ejemplo.org", ""),
	]
	assert pl.leer_config("").en_blanco and pl.leer_config("blank_issues_enabled: true").en_blanco
	assert pl.leer_config("a: [roto").en_blanco, "un config.yml ilegible deja lo de GitHub por defecto"


def test_aviso_de_lo_descartado():
	assert pl.describir_descartados([]) == ""
	assert "las etiquetas de la plantilla" in pl.describir_descartados(["etiquetas"])
	assert "las etiquetas, los asignados y el tipo" in pl.describir_descartados(["etiquetas", "asignados", "tipo"])


# ════════════════════════════════════════════════════════════════════════════
# API (sin red)
# ════════════════════════════════════════════════════════════════════════════


def respuesta(codigo=200, cuerpo=None):
	r = requests.Response()
	r.status_code = codigo
	r._content = b"" if cuerpo is None else json.dumps(cuerpo).encode()
	r.url = "https://api.github.com/x"
	r.encoding = "utf-8"
	return r


class SesionPorRuta:
	"""Contesta según la ruta pedida (lo que no está, 404) y guarda las peticiones."""

	def __init__(self, rutas: dict):
		self.rutas = rutas
		self.peticiones: list[tuple[str, str, dict]] = []

	def request(self, metodo, url, **opciones):
		ruta = url.split("api.github.com", 1)[1]
		self.peticiones.append((metodo, ruta, opciones))
		respuestas = self.rutas.get((metodo, ruta))
		if respuestas is None:
			return respuesta(404, {"message": "Not Found"})
		return respuestas.pop(0) if isinstance(respuestas, list) else respuestas


def archivo(texto: str) -> requests.Response:
	return respuesta(200, {"type": "file", "encoding": "base64", "sha": "s", "content": base64.b64encode(texto.encode()).decode()})


def api_con(rutas: dict) -> tuple[ApiGitHub, SesionPorRuta]:
	sesion = SesionPorRuta(rutas)
	return ApiGitHub(ClienteGitHub("ghp_prueba1234", crear_sesion=lambda: sesion)), sesion


BASE = "/repos/ana/proyecto/contents"


def test_leer_plantillas_issue_y_config():
	carpeta = ".github/ISSUE_TEMPLATE"
	api, _sesion = api_con({
		("GET", f"{BASE}/{carpeta}"): respuesta(200, [
			{"type": "file", "name": "config.yml", "path": f"{carpeta}/config.yml"},
			{"type": "file", "name": "fallo.yml", "path": f"{carpeta}/fallo.yml"},
			{"type": "file", "name": "idea.md", "path": f"{carpeta}/idea.md"},
			{"type": "file", "name": "LEEME.txt", "path": f"{carpeta}/LEEME.txt"},
			{"type": "dir", "name": "otra", "path": f"{carpeta}/otra"},
		]),
		("GET", f"{BASE}/{carpeta}/config.yml"): archivo("blank_issues_enabled: false\n"),
		("GET", f"{BASE}/{carpeta}/fallo.yml"): archivo("name: Fallo\nbody:\n  - type: input\n"),
		("GET", f"{BASE}/{carpeta}/idea.md"): archivo("Idea"),
	})
	plantillas, config = api.leer_plantillas_issue("ana/proyecto")
	assert plantillas == [("fallo.yml", "name: Fallo\nbody:\n  - type: input\n"), ("idea.md", "Idea")]
	assert config == "blank_issues_enabled: false\n"
	sin_carpeta, _s = api_con({})
	assert sin_carpeta.leer_plantillas_issue("ana/proyecto") == ([], "")


def test_plantillas_de_pull_request_en_todos_los_sitios():
	api, sesion = api_con({
		("GET", f"{BASE}/.github"): respuesta(200, [
			{"type": "file", "name": "PULL_REQUEST_TEMPLATE.md", "path": ".github/PULL_REQUEST_TEMPLATE.md"},
			{"type": "dir", "name": "pull_request_template", "path": ".github/pull_request_template"},
			{"type": "dir", "name": "workflows", "path": ".github/workflows"},
		]),
		("GET", f"{BASE}/.github/PULL_REQUEST_TEMPLATE.md"): archivo("Principal"),
		("GET", f"{BASE}/.github/pull_request_template"): respuesta(200, [
			{"type": "file", "name": "arreglo.md", "path": ".github/pull_request_template/arreglo.md"},
			{"type": "file", "name": "imagen.png", "path": ".github/pull_request_template/imagen.png"},
		]),
		("GET", f"{BASE}/.github/pull_request_template/arreglo.md"): archivo("Arreglo"),
		("GET", f"{BASE}/"): respuesta(200, [{"type": "file", "name": "pull_request_template.md", "path": "pull_request_template.md"}]),
		("GET", f"{BASE}/pull_request_template.md"): archivo("Raíz"),
	})
	assert api.plantillas_pr("ana/proyecto") == [
		(".github/PULL_REQUEST_TEMPLATE.md", "Principal"),
		(".github/pull_request_template/arreglo.md", "Arreglo"),
		("pull_request_template.md", "Raíz"),
	]
	assert ("GET", f"{BASE}/docs", ) == sesion.peticiones[-1][:2], "docs/ también se mira (aquí no existe)"
	assert not any("workflows" in ruta for _m, ruta, _o in sesion.peticiones), "solo se listan las carpetas que importan"


def test_crear_issue_con_plantilla_aplica_o_avisa():
	ruta = "/repos/ana/proyecto/issues"
	completa = {"number": 1, "labels": [{"name": "Fallo"}], "assignees": [{"login": "ana"}], "type": {"name": "Bug"}}
	api, sesion = api_con({("POST", ruta): respuesta(201, completa)})
	assert api.crear_issue_con_plantilla("ana/proyecto", "T", "C", ["fallo"], ["Ana"], "Bug") == (completa, [])
	assert json.loads(json.dumps(sesion.peticiones[0][2]["json"])) == {
		"title": "T", "body": "C", "labels": ["fallo"], "assignees": ["Ana"], "type": "Bug"}

	# Sin permiso de clasificación, GitHub ignora etiquetas y asignados sin decir nada.
	api, _s = api_con({("POST", ruta): respuesta(201, {"number": 2, "labels": [], "assignees": []})})
	assert api.crear_issue_con_plantilla("ana/proyecto", "T", "C", ["fallo"], ["ana"]) == (
		{"number": 2, "labels": [], "assignees": []}, ["etiquetas", "asignados"])

	# O rechaza la issue entera: se crea otra vez sin lo de la plantilla.
	rechazo = respuesta(422, {"message": "Validation Failed", "errors": [{"field": "type", "code": "invalid"}]})
	api, sesion = api_con({("POST", ruta): [rechazo, respuesta(201, {"number": 3})]})
	assert api.crear_issue_con_plantilla("ana/proyecto", "T", "C", ["fallo"], tipo="Bug") == ({"number": 3}, ["etiquetas", "tipo"])
	assert sesion.peticiones[1][2]["json"] == {"title": "T", "body": "C"}

	# Sin nada que quitar, el error se ve tal cual.
	api, _s = api_con({("POST", ruta): respuesta(422, {"message": "Validation Failed"})})
	with pytest.raises(ErrorValidacion):
		api.crear_issue_con_plantilla("ana/proyecto", "", "C")
