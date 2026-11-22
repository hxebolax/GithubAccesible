"""Buscador de GitHub sin wx: filtros declarativos, consulta, validación y tendencias.

Qué resuelve este módulo, y por qué así:

- **Descriptores declarativos** (``Filtro``) de los calificadores de cada tipo de
  búsqueda (repositorios, issues y PR, código, usuarios, commits, temas,
  etiquetas, discusiones y tendencias). El diálogo construye sus controles a
  partir de ellos, de modo que añadir un filtro es añadir una línea aquí.
- **Consulta al estilo de gh** (``construir_consulta``): valores con espacios
  entre comillas, exclusiones con guion, palabras excluidas con NOT, rangos
  ``n..m``, ``>=n`` y ``<=n`` y, en la búsqueda avanzada de issues, varios
  ``repo:``/``user:``/``in:`` agrupados con OR y el texto libre entre paréntesis
  si lleva operadores (para que un OR de la persona no se mezcle con los filtros).
- **Validación previa** con mensajes en español: 256 caracteres de texto, cinco
  operadores AND/OR/NOT, fechas AAAA-MM-DD, números, código con al menos una
  palabra (salvo ``filename:``), etiquetas con repositorio y sin calificadores.
- **Abrir en el navegador**, traducción de los errores 422 típicos, resumen de
  los fragmentos de text-match, partición por fechas para pasar del tope de
  1000 resultados y lectura de github.com/trending (sin API oficial) con caché.

Lo dudoso de la investigación (dependencias y sub-issues, ``reason:reopened``,
órdenes de discusiones, ``sort:`` dentro de la consulta) se ha dejado fuera.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urlencode

from app.core import i18n  # noqa: F401 - instala _ y N_ en builtins aunque se importe suelto (pruebas)
from app.services.github.cliente import ErrorGitHub, LimiteAlcanzado

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Tipos de búsqueda, órdenes y listas de valores
# ════════════════════════════════════════════════════════════════════════════

#: Tipos en el orden del desplegable «Buscar». Los siete primeros son de REST.
TIPOS: dict[str, str] = {
	"repositories": N_("Repositorios"),
	"code": N_("Código"),
	"issues": N_("Issues y pull requests"),
	"users": N_("Usuarios y organizaciones"),
	"commits": N_("Commits"),
	"topics": N_("Temas"),
	"labels": N_("Etiquetas"),
	"discussions": N_("Discusiones"),
	"trending": N_("Tendencias"),
}

TIPOS_REST = ("repositories", "code", "issues", "users", "commits", "topics", "labels")

#: Órdenes válidos de la API REST (verificados). Sin orden = «Mejor coincidencia».
ORDENES: dict[str, list[tuple[str, str]]] = {
	"repositories": [("", N_("Mejor coincidencia")), ("stars", N_("Estrellas")), ("forks", N_("Bifurcaciones")),
		("help-wanted-issues", N_("Issues que piden ayuda")), ("updated", N_("Actualizados recientemente"))],
	"code": [("", N_("Mejor coincidencia"))],
	"issues": [("", N_("Mejor coincidencia")), ("created", N_("Fecha de creación")), ("updated", N_("Última actualización")),
		("comments", N_("Comentarios")), ("reactions", N_("Reacciones (todas)")), ("interactions", N_("Interacciones (reacciones y comentarios)")),
		("reactions-+1", N_("Reacciones de pulgar arriba")), ("reactions--1", N_("Reacciones de pulgar abajo")),
		("reactions-smile", N_("Reacciones de sonrisa")), ("reactions-thinking_face", N_("Reacciones de cara pensativa")),
		("reactions-heart", N_("Reacciones de corazón")), ("reactions-tada", N_("Reacciones de celebración"))],
	"users": [("", N_("Mejor coincidencia")), ("followers", N_("Seguidores")), ("repositories", N_("Repositorios")), ("joined", N_("Fecha de alta"))],
	"commits": [("", N_("Mejor coincidencia")), ("author-date", N_("Fecha del autor")), ("committer-date", N_("Fecha del commit"))],
	"topics": [("", N_("Mejor coincidencia"))],
	"labels": [("", N_("Mejor coincidencia")), ("created", N_("Fecha de creación")), ("updated", N_("Última actualización"))],
	"discussions": [("", N_("Mejor coincidencia"))],
	"trending": [("", N_("El de la fuente elegida"))],
}

LENGUAJES: list[tuple[str, str]] = [
	("", N_("Todos los lenguajes")), ("python", "Python"), ("javascript", "JavaScript"), ("typescript", "TypeScript"), ("html", "HTML"),
	("css", "CSS"), ("c", "C"), ("c++", "C++"), ("c#", "C#"), ("java", "Java"), ("php", "PHP"), ("ruby", "Ruby"), ("swift", "Swift"),
	("kotlin", "Kotlin"), ("go", "Go"), ("rust", "Rust"), ("shell", "Shell / Bash"), ("powershell", "PowerShell"), ("batchfile", "Batch"),
	("scala", "Scala"), ("lua", "Lua"), ("dart", "Dart"), ("r", "R"), ("julia", "Julia"), ("zig", "Zig"), ("pascal", "Pascal / Delphi"),
	("vim-script", "Vim Script"), ("markdown", "Markdown"), ("objective-c", "Objective-C"), ("perl", "Perl"), ("haskell", "Haskell"),
	("elixir", "Elixir"), ("erlang", "Erlang"), ("clojure", "Clojure"), ("f#", "F#"), ("ocaml", "OCaml"), ("groovy", "Groovy"),
	("assembly", N_("Ensamblador")), ("fortran", "Fortran"), ("cobol", "COBOL"), ("matlab", "MATLAB"), ("jupyter-notebook", "Jupyter Notebook"),
	("dockerfile", "Dockerfile"), ("makefile", "Makefile"), ("nix", "Nix"), ("solidity", "Solidity"), ("vue", "Vue"), ("svelte", "Svelte"),
	("autohotkey", "AutoHotkey"), ("nsis", "NSIS"),
]

#: Claves de licencia del formulario de búsqueda avanzada de GitHub (las de choosealicense).
LICENCIAS: list[tuple[str, str]] = [
	("", N_("Cualquier licencia")), ("mit", "MIT"), ("apache-2.0", "Apache 2.0"), ("gpl-3.0", "GNU GPL v3"), ("gpl-2.0", "GNU GPL v2"),
	("agpl-3.0", "GNU AGPL v3"), ("lgpl-3.0", "GNU LGPL v3"), ("lgpl-2.1", "GNU LGPL v2.1"), ("bsd-3-clause", N_("BSD de 3 cláusulas")),
	("bsd-2-clause", N_("BSD de 2 cláusulas")), ("bsd-3-clause-clear", N_("BSD de 3 cláusulas «Clear»")), ("bsd-4-clause", N_("BSD de 4 cláusulas")),
	("0bsd", N_("BSD de cero cláusulas")), ("bsd-2-clause-patent", N_("BSD con patentes (BSD+Patent)")), ("mpl-2.0", "Mozilla 2.0"),
	("epl-1.0", "Eclipse 1.0"), ("epl-2.0", "Eclipse 2.0"), ("eupl-1.1", N_("Unión Europea (EUPL) 1.1")), ("eupl-1.2", N_("Unión Europea (EUPL) 1.2")),
	("isc", "ISC"), ("unlicense", "The Unlicense"), ("cc0-1.0", "Creative Commons Zero 1.0"), ("cc-by-4.0", N_("Creative Commons Atribución 4.0")),
	("cc-by-sa-4.0", N_("Creative Commons Atribución-CompartirIgual 4.0")), ("wtfpl", "WTFPL"), ("zlib", "zlib"), ("bsl-1.0", "Boost 1.0"),
	("artistic-2.0", "Artistic 2.0"), ("afl-3.0", "Academic Free 3.0"), ("ofl-1.1", "SIL Open Font 1.1"), ("osl-3.0", "Open Software 3.0"),
	("postgresql", "PostgreSQL"), ("upl-1.0", "Universal Permissive 1.0"), ("vim", "Vim"), ("mit-0", N_("MIT sin atribución (MIT-0)")),
	("ms-pl", "Microsoft Public"), ("ms-rl", "Microsoft Reciprocal"), ("ncsa", N_("Universidad de Illinois / NCSA")),
	("odbl-1.0", "Open Database 1.0"), ("lppl-1.3c", "LaTeX Project 1.3c"), ("gfdl-1.3", "GNU FDL 1.3"),
	("ecl-2.0", "Educational Community 2.0"), ("cecill-2.1", "CeCILL 2.1"), ("mulanpsl-2.0", "Mulan PSL 2.0"),
	("blueoak-1.0.0", "Blue Oak 1.0.0"), ("cern-ohl-p-2.0", N_("CERN OHL permisiva 2.0")),
	("cern-ohl-s-2.0", N_("CERN OHL fuertemente recíproca 2.0")), ("cern-ohl-w-2.0", N_("CERN OHL débilmente recíproca 2.0")),
	("cc", N_("Familia Creative Commons (todas)")), ("gpl", N_("Familia GNU GPL (todas)")), ("lgpl", N_("Familia GNU LGPL (todas)")),
]

#: Idioma hablado de la página de tendencias (código ISO 639-1).
IDIOMAS_HABLADOS: list[tuple[str, str]] = [
	("", N_("Cualquier idioma")), ("es", N_("Español")), ("en", N_("Inglés")), ("pt", N_("Portugués")), ("fr", N_("Francés")), ("de", N_("Alemán")),
	("it", N_("Italiano")), ("ca", N_("Catalán")), ("gl", N_("Gallego")), ("eu", N_("Euskera")), ("zh", N_("Chino")), ("ja", N_("Japonés")),
	("ko", N_("Coreano")), ("ru", N_("Ruso")), ("ar", N_("Árabe")), ("hi", N_("Hindi")), ("nl", N_("Neerlandés")), ("pl", N_("Polaco")),
	("tr", N_("Turco")), ("uk", N_("Ucraniano")),
]

PERIODOS: list[tuple[str, str]] = [("daily", N_("Hoy")), ("weekly", N_("Esta semana")), ("monthly", N_("Este mes"))]
DIAS_PERIODO = {"daily": 1, "weekly": 7, "monthly": 30}

FUENTES_TENDENCIAS: list[tuple[str, str]] = [
	("api", N_("Nuevos y populares (API oficial de GitHub)")),
	("web_repos", N_("Página de tendencias: repositorios (sin API oficial)")),
	("web_devs", N_("Página de tendencias: desarrolladores (sin API oficial)")),
]

TIPOS_BUSQUEDA_ISSUES: list[tuple[str, str]] = [
	("", N_("Léxica (la de siempre)")),
	("semantic", N_("Semántica (por significado)")),
	("hybrid", N_("Híbrida (significado y palabras)")),
]

PAGINAS: dict[str, str] = {
	"basico": N_("Básico"),
	"personas": N_("Personas"),
	"pr": N_("Pull requests"),
	"fechas": N_("Fechas y números"),
	"avanzado": N_("Avanzado"),
}

MAXIMO_RESULTADOS = 1000
MAXIMO_TEXTO = 256
MAXIMO_OPERADORES = 5
HOST_GITHUB = "github.com"

# Tipos de control de un filtro.
TEXTO = "texto"
NUMERO = "numero"
FECHA = "fecha"
DESPLEGABLE = "desplegable"
EN = "en"
CASILLA = "casilla"
MAYOR_QUE = "mayor_que"
EXCLUIR = "excluir"


# ════════════════════════════════════════════════════════════════════════════
# Descriptores
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Filtro:
	"""Un filtro guiado del diálogo.

	:param clave: identificador estable (se guarda en el historial y en las búsquedas guardadas).
	:param etiqueta: texto de la etiqueta, sin ``&`` (la letra se asigna sola).
	:param control: ``TEXTO``, ``NUMERO`` (mínimo y máximo), ``FECHA`` (desde y
		hasta), ``DESPLEGABLE``, ``EN`` (casillas «buscar en»), ``CASILLA``,
		``MAYOR_QUE`` o ``EXCLUIR`` (palabras con NOT).
	:param calificador: el calificador que genera («stars», «language»...). En un
		desplegable sin calificador, el valor de cada opción ya es el fragmento.
		En una casilla, es el fragmento entero («is:sponsorable»).
	:param opciones: ``(valor, nombre)`` de desplegables y casillas «buscar en».
	:param pagina: pestaña del diálogo (clave de ``PAGINAS``).
	:param agrupar_o: varios valores separados por comas se combinan con O.
	:param parametro: no va en la consulta sino como parámetro de la petición.
	"""

	clave: str
	etiqueta: str
	control: str
	calificador: str = ""
	opciones: tuple[tuple[str, str], ...] = ()
	ayuda: str = ""
	pagina: str = "basico"
	agrupar_o: bool = False
	parametro: str = ""


def _t(clave: str, etiqueta: str, cal: str, ayuda: str, pagina: str = "basico", agrupar_o: bool = False) -> Filtro:
	return Filtro(clave, etiqueta, TEXTO, cal, ayuda=ayuda, pagina=pagina, agrupar_o=agrupar_o)


def _n(clave: str, etiqueta: str, cal: str, ayuda: str, pagina: str = "fechas") -> Filtro:
	return Filtro(clave, etiqueta, NUMERO, cal, ayuda=ayuda, pagina=pagina)


def _f(clave: str, etiqueta: str, cal: str, ayuda: str, pagina: str = "fechas") -> Filtro:
	return Filtro(clave, etiqueta, FECHA, cal, ayuda=ayuda, pagina=pagina)


def _d(clave: str, etiqueta: str, opciones: Iterable[tuple[str, str]], ayuda: str, pagina: str = "basico", cal: str = "",
	parametro: str = "") -> Filtro:
	return Filtro(clave, etiqueta, DESPLEGABLE, cal, tuple(opciones), ayuda, pagina, parametro=parametro)


def _c(clave: str, etiqueta: str, fragmento: str, ayuda: str, pagina: str = "avanzado") -> Filtro:
	return Filtro(clave, etiqueta, CASILLA, fragmento, ayuda=ayuda, pagina=pagina)


def _en(opciones: Iterable[tuple[str, str]], ayuda: str) -> Filtro:
	return Filtro("en", N_("Buscar el texto en"), EN, "in", tuple(opciones), ayuda)


def _excluir(pagina: str = "avanzado") -> Filtro:
	return Filtro("excluir", N_("Excluir las palabras"), EXCLUIR, ayuda=(
		N_("Palabras que NO deben aparecer, separadas por espacios. Cada una se añade con NOT y cuenta para el "
		"máximo de cinco operadores. NOT solo sirve para palabras, no para números ni fechas.")), pagina=pagina)


_AYUDA_PERSONA = N_("Nombre de usuario. Admite @me (usted) y @copilot. Varios, separados por comas; con un guion delante se excluye.")
_AYUDA_REPOS = (N_("Repositorios con la forma dueño/nombre. Varios, separados por comas, se buscan en cualquiera de ellos. "
	"Con un guion delante (-dueño/nombre) se excluye."))
_AYUDA_DUENO = (N_("Usuario u organización dueña. Varios, separados por comas, valen cualquiera de ellos. Con un guion delante se excluye."))
_AYUDA_FECHA = N_("Fecha con la forma AAAA-MM-DD (por ejemplo 2026-01-31). Puede rellenar solo «desde», solo «hasta» o las dos.")
_AYUDA_NUMERO = N_("Número entero. Puede rellenar solo el mínimo, solo el máximo o los dos (rango inclusivo).")
_LENGUAJE = _d("lenguaje", N_("Lenguaje"), LENGUAJES, N_("Lenguaje de programación principal."), cal="language")
_VISIBILIDAD = _d("visibilidad", N_("Visibilidad"), [("", N_("Cualquiera")), ("is:public", N_("Públicos")), ("is:private", N_("Privados a los que tiene acceso"))],
	N_("Públicos o privados (los privados solo si la cuenta tiene acceso)."), pagina="avanzado")
_EXCLUIR_BASICO = _excluir("basico")

FILTROS: dict[str, list[Filtro]] = {
	"repositories": [
		_d("categoria", N_("Categoría (atajo)"), [], N_("Atajos de la búsqueda guiada: al elegir uno se rellenan los filtros "
			"(estrellas, fecha de envío, temas...). Después puede cambiarlos a su gusto."), parametro="atajo"),
		_en([("name", N_("Nombre")), ("description", N_("Descripción")), ("topics", N_("Temas")), ("readme", "README")],
			N_("Dónde buscar el texto libre. Sin marcar nada, GitHub busca en el nombre, la descripción y los temas, no en el README.")),
		_t("propietario", N_("Usuario u organización dueña"), "user", _AYUDA_DUENO, agrupar_o=True),
		_t("repos", N_("Repositorio concreto (dueño/nombre)"), "repo", _AYUDA_REPOS, agrupar_o=True),
		_LENGUAJE,
		_t("temas", N_("Temas (separados por comas)"), "topic", N_("Cada tema añadido es una condición más: el repositorio debe tenerlos todos.")),
		_d("licencia", N_("Licencia"), LICENCIAS, N_("Licencia del repositorio. Las claves de las licencias menos comunes salen del "
			"formulario de búsqueda avanzada de GitHub; si alguna no da resultados, compruébela abriendo la búsqueda en el navegador."),
			cal="license"),
		_n("estrellas", N_("Estrellas"), "stars", _AYUDA_NUMERO, pagina="basico"),
		_n("bifurcaciones", N_("Bifurcaciones"), "forks", _AYUDA_NUMERO),
		_f("envio", N_("Último envío"), "pushed", N_("Fecha del último envío a cualquier rama. "
			"Fecha con la forma AAAA-MM-DD (por ejemplo 2026-01-31). Puede rellenar solo «desde», solo «hasta» o las dos.")),
		_f("creado", N_("Fecha de creación"), "created", _AYUDA_FECHA),
		_n("tamano", N_("Tamaño en kilobytes"), "size", _AYUDA_NUMERO),
		_n("seguidores", N_("Seguidores"), "followers", N_("Personas que vigilan el repositorio. "
			"Número entero. Puede rellenar solo el mínimo, solo el máximo o los dos (rango inclusivo).")),
		_n("numero_temas", N_("Número de temas"), "topics", _AYUDA_NUMERO),
		Filtro("buenas_primeras", N_("Más de N issues para principiantes"), MAYOR_QUE, "good-first-issues",
			ayuda=N_("Repositorios con más de ese número de issues etiquetadas «good first issue». Escriba 0 para «al menos una»."), pagina="avanzado"),
		Filtro("piden_ayuda", N_("Más de N issues que piden ayuda"), MAYOR_QUE, "help-wanted-issues",
			ayuda=N_("Repositorios con más de ese número de issues etiquetadas «help wanted». Escriba 0 para «al menos una»."), pagina="avanzado"),
		_d("visibilidad", N_("Visibilidad"), [("", N_("Cualquiera")), ("is:public", N_("Públicos")), ("is:private", N_("Privados a los que tiene acceso")),
			("is:internal", N_("Internos (solo empresas)"))], N_("Visibilidad del repositorio."), pagina="avanzado"),
		_d("archivados", N_("Archivados"), [("", N_("Incluidos")), ("archived:false", N_("Sin archivar")), ("archived:true", N_("Solo archivados"))],
			N_("Repositorios archivados (de solo lectura)."), pagina="avanzado"),
		_d("bifurcados", N_("Bifurcaciones en los resultados"), [("", N_("Excluidas (como hace GitHub)")), ("fork:true", N_("Incluidas")),
			("fork:only", N_("Solo bifurcaciones"))], N_("Por defecto GitHub no muestra bifurcaciones."), pagina="avanzado"),
		_d("plantillas", N_("Plantillas"), [("", N_("Indiferente")), ("template:true", N_("Solo plantillas")), ("template:false", N_("Sin plantillas"))],
			N_("Repositorios marcados como plantilla."), pagina="avanzado"),
		_d("replicas", N_("Réplicas (mirrors)"), [("", N_("Indiferente")), ("mirror:true", N_("Solo réplicas")), ("mirror:false", N_("Sin réplicas"))],
			N_("Repositorios que son réplica de otro alojado fuera de GitHub."), pagina="avanzado"),
		_c("patrocinable", N_("Dueño con perfil de GitHub Sponsors"), "is:sponsorable", N_("Solo repositorios cuyo dueño acepta patrocinios.")),
		_c("financiacion", N_("Con archivo de financiación (FUNDING.yml)"), "has:funding-file", N_("Solo repositorios con FUNDING.yml.")),
		_excluir(),
	],
	"code": [
		_en([("file", N_("Contenido del archivo")), ("path", N_("Ruta"))], N_("Dónde buscar el texto. Sin marcar nada, en el contenido.")),
		_t("repos", N_("Repositorio (dueño/nombre)"), "repo", _AYUDA_REPOS, agrupar_o=True),
		_t("propietario", N_("Usuario u organización dueña"), "user", _AYUDA_DUENO, agrupar_o=True),
		_t("ruta", N_("Ruta o carpeta"), "path", N_("Carpeta donde está el archivo, por ejemplo app/ui. Una barra sola (/) es la raíz.")),
		_t("archivo", N_("Nombre de archivo"), "filename", N_("Nombre del archivo, por ejemplo setup.py. Con este filtro no hace falta escribir texto.")),
		_t("extension", N_("Extensión"), "extension", N_("Extensión sin punto, por ejemplo py.")),
		_LENGUAJE,
		_n("tamano", N_("Tamaño del archivo"), "size", N_("La documentación no aclara si es en bytes o en kilobytes. "
			"Número entero. Puede rellenar solo el mínimo, solo el máximo o los dos (rango inclusivo)."), pagina="basico"),
		_d("bifurcados", N_("Bifurcaciones"), [("", N_("Excluidas")), ("fork:true", N_("Incluidas")), ("fork:only", N_("Solo bifurcaciones"))],
			N_("Las bifurcaciones solo se indexan si tienen más estrellas que el original."), pagina="basico"),
	],
	"issues": [
		_d("tipo", N_("Tipo"), [("", N_("Issues y pull requests")), ("is:issue", N_("Solo issues")), ("is:pr", N_("Solo pull requests"))],
			N_("Qué se busca. La búsqueda semántica o híbrida exige «Solo issues».")),
		_d("estado", N_("Estado"), [("", N_("Cualquiera")), ("is:open", N_("Abiertas")), ("is:closed", N_("Cerradas"))], N_("Abiertas o cerradas.")),
		_d("motivo", N_("Motivo de cierre"), [("", N_("Cualquiera")), ("reason:completed", N_("Completadas")), ('reason:"not planned"', N_("No planificadas"))],
			N_("Por qué se cerró la issue.")),
		_en([("title", N_("Título")), ("body", N_("Cuerpo")), ("comments", N_("Comentarios"))], N_("Dónde buscar el texto libre.")),
		_t("repos", N_("Repositorios (dueño/nombre)"), "repo", _AYUDA_REPOS, agrupar_o=True),
		_t("propietario", N_("Usuario u organización dueña"), "user", _AYUDA_DUENO, agrupar_o=True),
		_t("etiquetas", N_("Etiquetas (separadas por comas)"), "label",
			N_("Cada etiqueta es una condición más (debe tenerlas todas). Con un guion delante se excluye: -wontfix.")),
		_LENGUAJE,
		_d("search_type", N_("Tipo de búsqueda"), TIPOS_BUSQUEDA_ISSUES,
			N_("Semántica busca por significado; híbrida combina significado y palabras. Solo issues (no pull requests), solo en el "
			"título y el cuerpo, exige sesión iniciada, sin orden, una sola página de resultados y como mucho 10 búsquedas por minuto. "
			"Si la consulta solo tiene filtros o frases entre comillas, GitHub hace una búsqueda léxica."), parametro="search_type"),
		_t("autor", N_("Autor"), "author", N_("Nombre de usuario. Admite @me (usted) y @copilot. Varios, separados por comas; con un guion delante se excluye."
			" Para una aplicación: app/NOMBRE."), pagina="personas"),
		_t("asignado", N_("Asignado a"), "assignee", _AYUDA_PERSONA, pagina="personas"),
		_t("menciona", N_("Menciona a"), "mentions", _AYUDA_PERSONA, pagina="personas"),
		_t("comentarista", N_("Comentada por"), "commenter", _AYUDA_PERSONA, pagina="personas"),
		_t("implicado", N_("Persona implicada"), "involves", N_("Autor, asignado, mencionado o comentarista. "
			"Nombre de usuario. Admite @me (usted) y @copilot. Varios, separados por comas; con un guion delante se excluye."), pagina="personas"),
		_t("equipo", N_("Equipo mencionado (org/equipo)"), "team", N_("Equipo con la forma organización/equipo."), pagina="personas"),
		_t("revisado", N_("Revisada por"), "reviewed-by", _AYUDA_PERSONA, pagina="pr"),
		_t("revision_pedida", N_("Revisión pedida a"), "review-requested", N_("Nombre de usuario. Admite @me (usted) y @copilot. Varios, separados por comas; con un guion delante se excluye."
			" Deja de aparecer cuando ya ha revisado."), pagina="pr"),
		_t("revision_equipo", N_("Revisión pedida al equipo (org/equipo)"), "team-review-requested", N_("Equipo con la forma organización/equipo."),
			pagina="pr"),
		_d("revision", N_("Estado de la revisión"), [("", N_("Cualquiera")), ("review:none", N_("Sin revisar")), ("review:required", N_("Revisión obligatoria")),
			("review:approved", N_("Aprobadas")), ("review:changes_requested", N_("Con cambios pedidos"))], N_("Estado de revisión de la pull request."), pagina="pr"),
		_d("comprobaciones", N_("Comprobaciones"), [("", N_("Cualquiera")), ("status:pending", N_("Pendientes")), ("status:success", N_("Correctas")),
			("status:failure", N_("Fallidas"))], N_("Resultado de las comprobaciones (Actions y otras)."), pagina="pr"),
		_d("fusion", N_("Fusión"), [("", N_("Cualquiera")), ("is:merged", N_("Fusionadas")), ("is:unmerged", N_("Sin fusionar"))], N_("Solo pull requests."), pagina="pr"),
		_d("borrador", N_("Borrador"), [("", N_("Cualquiera")), ("draft:true", N_("Solo borradores")), ("draft:false", N_("Sin borradores"))],
			N_("Pull requests en borrador."), pagina="pr"),
		_t("rama_origen", N_("Rama de origen"), "head", N_("Rama desde la que se propone la pull request."), pagina="pr"),
		_t("rama_destino", N_("Rama de destino"), "base", N_("Rama en la que se quiere fusionar."), pagina="pr"),
		_n("comentarios", N_("Comentarios"), "comments", _AYUDA_NUMERO),
		_n("reacciones", N_("Reacciones"), "reactions", _AYUDA_NUMERO),
		_n("interacciones", N_("Interacciones"), "interactions", N_("Reacciones más comentarios. "
			"Número entero. Puede rellenar solo el mínimo, solo el máximo o los dos (rango inclusivo).")),
		_f("creada", N_("Fecha de creación"), "created", _AYUDA_FECHA),
		_f("actualizada", N_("Última actualización"), "updated", _AYUDA_FECHA),
		_f("cerrada", N_("Fecha de cierre"), "closed", _AYUDA_FECHA),
		_f("fusionada", N_("Fecha de fusión"), "merged", N_("Solo pull requests. "
			"Fecha con la forma AAAA-MM-DD (por ejemplo 2026-01-31). Puede rellenar solo «desde», solo «hasta» o las dos.")),
		_t("hito", N_("Hito"), "milestone", N_("Nombre del hito."), pagina="avanzado"),
		_t("proyecto", N_("Proyecto (dueño/número)"), "project", N_("Proyecto con la forma dueño/número, por ejemplo github/57."), pagina="avanzado"),
		_t("tipo_issue", N_("Tipo de issue de la organización"), "type", N_("Por ejemplo Bug, Feature o Task. Los nombres dependen de cada organización."),
			pagina="avanzado"),
		_d("enlazada", N_("Enlaces"), [("", N_("Indiferente")), ("linked:pr", N_("Issues enlazadas a una pull request")),
			("-linked:pr", N_("Issues sin pull request enlazada")), ("linked:issue", N_("Pull requests enlazadas a una issue")),
			("-linked:issue", N_("Pull requests sin issue enlazada"))], N_("Relación entre issues y pull requests."), pagina="avanzado"),
		_d("tiene", N_("Tiene"), [("", N_("Indiferente")), ("has:label", N_("Alguna etiqueta")), ("has:assignee", N_("Alguna persona asignada"))],
			N_("Exige que tenga ese dato."), pagina="avanzado"),
		_d("falta", N_("Le falta"), [("", N_("Indiferente")), ("no:label", N_("Etiquetas")), ("no:milestone", N_("Hito")), ("no:assignee", N_("Persona asignada")),
			("no:project", N_("Proyecto"))], N_("Exige que NO tenga ese dato."), pagina="avanzado"),
		_d("bloqueo", N_("Conversación bloqueada"), [("", N_("Indiferente")), ("is:locked", N_("Bloqueadas")), ("is:unlocked", N_("Sin bloquear"))],
			N_("Conversaciones bloqueadas."), pagina="avanzado"),
		_VISIBILIDAD,
		_d("repo_archivado", N_("Repositorio archivado"), [("", N_("Indiferente")), ("archived:false", N_("Sin archivar")), ("archived:true", N_("Archivado"))],
			N_("Si el repositorio está archivado."), pagina="avanzado"),
		_c("cola", N_("En la cola de fusión"), "is:queued", N_("Pull requests en la cola de fusión.")),
		_c("pr_archivadas", N_("Pull requests archivadas (requiere permiso de triaje)"), "is:archived", N_("Pull requests archivadas.")),
		_excluir(),
	],
	"users": [
		_d("tipo", N_("Tipo de cuenta"), [("", N_("Personas y organizaciones")), ("type:user", N_("Solo personas")), ("type:org", N_("Solo organizaciones"))],
			N_("Qué cuentas buscar.")),
		_en([("login", N_("Nombre de usuario")), ("name", N_("Nombre")), ("email", N_("Correo público"))],
			N_("Dónde buscar el texto. Sin marcar nada, en el nombre de usuario y el correo. No se puede buscar por dominio de correo.")),
		_t("nombre_completo", N_("Nombre completo"), "fullname", N_("Nombre y apellidos tal como aparecen en el perfil.")),
		_t("ubicacion", N_("Ubicación"), "location", N_("Lugar indicado en el perfil, por ejemplo Madrid.")),
		_LENGUAJE,
		_n("repositorios", N_("Repositorios"), "repos", _AYUDA_NUMERO, pagina="basico"),
		_n("seguidores", N_("Seguidores"), "followers", _AYUDA_NUMERO, pagina="basico"),
		_f("alta", N_("Fecha de alta"), "created", _AYUDA_FECHA, pagina="basico"),
		_c("patrocinable", N_("Con perfil de GitHub Sponsors"), "is:sponsorable", N_("Cuentas que aceptan patrocinios."), pagina="basico"),
	],
	"commits": [
		_t("repos", N_("Repositorios (dueño/nombre)"), "repo", _AYUDA_REPOS, agrupar_o=True),
		_t("propietario", N_("Usuario u organización dueña"), "user", _AYUDA_DUENO, agrupar_o=True),
		_t("autor", N_("Autor (usuario)"), "author", N_("Usuario de GitHub del autor.")),
		_t("confirmador", N_("Quien hizo el commit (usuario)"), "committer", N_("Usuario de GitHub de quien hizo el commit.")),
		_d("fusion", N_("Commits de fusión"), [("", N_("Incluidos")), ("merge:true", N_("Solo fusiones")), ("merge:false", N_("Sin fusiones"))],
			N_("Commits de fusión (merge).")),
		_f("fecha_autor", N_("Fecha del autor"), "author-date", _AYUDA_FECHA, pagina="basico"),
		_f("fecha_commit", N_("Fecha del commit"), "committer-date", _AYUDA_FECHA, pagina="basico"),
		_t("nombre_autor", N_("Nombre del autor"), "author-name", N_("Nombre tal como aparece en el commit."), pagina="avanzado"),
		_t("correo_autor", N_("Correo del autor"), "author-email", N_("Correo completo."), pagina="avanzado"),
		_t("nombre_confirmador", N_("Nombre de quien hizo el commit"), "committer-name", N_("Nombre tal como aparece en el commit."), pagina="avanzado"),
		_t("correo_confirmador", N_("Correo de quien hizo el commit"), "committer-email", N_("Correo completo."), pagina="avanzado"),
		_t("hash", N_("Hash del commit"), "hash", N_("SHA completo o abreviado."), pagina="avanzado"),
		_t("padre", N_("Hijos del commit (hash del padre)"), "parent", N_("Commits cuyo padre es ese SHA."), pagina="avanzado"),
		_t("arbol", N_("Árbol (hash)"), "tree", N_("SHA del árbol."), pagina="avanzado"),
		_VISIBILIDAD,
		_excluir(),
	],
	"topics": [
		_d("destacados", N_("Destacados"), [("", N_("Indiferente")), ("is:featured", N_("Destacados")), ("is:not-featured", N_("No destacados"))],
			N_("Temas destacados en GitHub.")),
		_d("seleccionados", N_("Seleccionados"), [("", N_("Indiferente")), ("is:curated", N_("Con información seleccionada")),
			("is:not-curated", N_("Sin información seleccionada"))], N_("Temas con información añadida por GitHub.")),
		_n("repositorios", N_("Repositorios con el tema"), "repositories", _AYUDA_NUMERO, pagina="basico"),
		_f("creado", N_("Fecha de creación"), "created", _AYUDA_FECHA, pagina="basico"),
		_EXCLUIR_BASICO,
	],
	"labels": [
		Filtro("repositorio", N_("Repositorio (dueño/nombre, obligatorio)"), TEXTO, ayuda=(
			N_("GitHub solo busca etiquetas dentro de un repositorio. Escriba dueño/nombre; la aplicación averigua su número. "
			"El texto libre solo admite palabras, no calificadores.")), parametro="repositorio"),
	],
	"discussions": [
		_en([("title", N_("Título")), ("body", N_("Cuerpo")), ("comments", N_("Comentarios"))], N_("Dónde buscar el texto libre.")),
		_t("repos", N_("Repositorios (dueño/nombre)"), "repo", _AYUDA_REPOS, agrupar_o=True),
		_t("propietario", N_("Usuario u organización dueña"), "user", _AYUDA_DUENO, agrupar_o=True),
		_d("respuesta", N_("Respuesta"), [("", N_("Indiferente")), ("is:answered", N_("Respondidas")), ("is:unanswered", N_("Sin responder"))],
			N_("Discusiones con una respuesta marcada.")),
		_d("estado", N_("Estado"), [("", N_("Cualquiera")), ("is:open", N_("Abiertas")), ("is:closed", N_("Cerradas"))], N_("Abiertas o cerradas.")),
		_t("categoria", N_("Categoría"), "category", N_("Nombre de la categoría, por ejemplo Ideas.")),
		_t("etiquetas", N_("Etiquetas (separadas por comas)"), "label", N_("Cada etiqueta es una condición más. Con un guion delante se excluye.")),
		_t("autor", N_("Autor"), "author", _AYUDA_PERSONA, pagina="personas"),
		_t("comentarista", N_("Comentada por"), "commenter", _AYUDA_PERSONA, pagina="personas"),
		_t("implicado", N_("Persona implicada"), "involves", _AYUDA_PERSONA, pagina="personas"),
		_t("respondida_por", N_("Respondida por"), "answered-by", _AYUDA_PERSONA, pagina="personas"),
		_n("comentarios", N_("Comentarios"), "comments", _AYUDA_NUMERO),
		_f("creada", N_("Fecha de creación"), "created", _AYUDA_FECHA),
		_f("actualizada", N_("Última actualización"), "updated", _AYUDA_FECHA),
		_d("bloqueo", N_("Conversación bloqueada"), [("", N_("Indiferente")), ("is:locked", N_("Bloqueadas")), ("is:unlocked", N_("Sin bloquear"))],
			N_("Conversaciones bloqueadas."), pagina="avanzado"),
		_VISIBILIDAD,
		_excluir(),
	],
	"trending": [
		_d("fuente", N_("Fuente"), FUENTES_TENDENCIAS, N_("GitHub no tiene API de tendencias. «Nuevos y populares» usa la API oficial: repositorios "
			"creados en el periodo ordenados por estrellas (no mide las estrellas ganadas). Las otras dos leen la página "
			"github.com/trending una vez por consulta (se guarda una hora): no tiene API oficial y puede dejar de funcionar si GitHub "
			"cambia la página."), parametro="fuente"),
		_d("periodo", N_("Periodo"), PERIODOS, N_("Hoy, esta semana o este mes."), parametro="periodo"),
		_d("lenguaje", N_("Lenguaje"), LENGUAJES, N_("Lenguaje de programación."), cal="language"),
		_d("idioma", N_("Idioma hablado"), IDIOMAS_HABLADOS, N_("Solo para la página de tendencias de repositorios: idioma de la descripción."),
			parametro="idioma"),
	],
}

#: Tipos cuyo texto libre es una consulta de la búsqueda avanzada de issues (admite OR y paréntesis).
TIPOS_AVANZADOS = ("issues",)

# Atajos de la búsqueda guiada de repositorios: (clave, nombre, valores que rellenan).
ATAJOS_REPOSITORIOS: list[tuple[str, str, dict[str, Any]]] = [
	("", N_("Ninguno (búsqueda libre)"), {}),
	("populares", N_("Populares: muchas estrellas"), {"estrellas": ["1000", ""], "_orden": "stars"}),
	("bifurcados", N_("Más bifurcados"), {"bifurcaciones": ["100", ""], "_orden": "forks"}),
	("recientes", N_("Actualizados en el último mes"), {"envio": ["-30", ""]}),
	("desactualizados", N_("Sin actualizar desde hace un año"), {"envio": ["", "-365"]}),
	("buenas_primeras", N_("Con issues para empezar a colaborar"), {"buenas_primeras": "0"}),
	("ayuda", N_("Que piden ayuda"), {"piden_ayuda": "0"}),
	("awesome", N_("Listas Awesome"), {"_texto": "awesome", "en": ["name", "description"]}),
	("nvda", N_("Complementos y programas para NVDA"), {"_texto": "nvda"}),
] + [(clave, nombre, {"temas": tema}) for clave, nombre, tema in (
	("accesibilidad", N_("Accesibilidad"), "accessibility"), ("lector", N_("Lector de pantalla"), "screen-reader"), ("a11y", "A11y", "a11y"),
	("seguridad", N_("Seguridad"), "security"), ("ciberseguridad", N_("Ciberseguridad"), "cybersecurity"),
	("ia", N_("Inteligencia artificial"), "artificial-intelligence"), ("ml", N_("Aprendizaje automático"), "machine-learning"),
	("datos", N_("Ciencia de datos"), "data-science"), ("web", N_("Desarrollo web"), "web-development"), ("frontend", "Front-end", "frontend"),
	("backend", "Back-end", "backend"), ("movil", N_("Desarrollo móvil"), "mobile"), ("android", "Android", "android"),
	("devops", "DevOps", "devops"), ("nube", N_("Nube"), "cloud"), ("docker", "Docker", "docker"), ("linux", "Linux", "linux"),
	("windows", "Windows", "windows"), ("cli", N_("Línea de órdenes"), "cli"), ("bot", N_("Bots"), "bot"), ("juegos", N_("Videojuegos"), "game"),
	("audio", "Audio", "audio"), ("multimedia", "Multimedia", "multimedia"), ("iot", N_("Internet de las cosas"), "iot"),
	("arduino", "Arduino", "arduino"), ("raspberry", "Raspberry Pi", "raspberry-pi"), ("robotica", N_("Robótica"), "robotics"),
	("drivers", N_("Controladores (drivers)"), "drivers"), ("nas", "NAS", "nas"), ("synology", "Synology NAS", "synology"),
	("blockchain", "Blockchain", "blockchain"), ("hacktoberfest", "Hacktoberfest", "hacktoberfest"),
)]


def filtros_de(tipo: str) -> list[Filtro]:
	"""Filtros de un tipo; el atajo de repositorios lleva sus opciones calculadas."""
	filtros = list(FILTROS.get(tipo, []))
	if tipo == "repositories":
		filtros[0] = Filtro(filtros[0].clave, filtros[0].etiqueta, DESPLEGABLE, "", tuple((c, n) for c, n, _v in ATAJOS_REPOSITORIOS),
			filtros[0].ayuda, filtros[0].pagina, parametro="atajo")
	return filtros


def paginas_de(tipo: str) -> list[str]:
	"""Claves de las pestañas que usa un tipo, en el orden de ``PAGINAS``."""
	usadas = {f.pagina for f in filtros_de(tipo)}
	return [p for p in PAGINAS if p in usadas] or ["basico"]


def valores_atajo(clave: str, hoy: date | None = None) -> dict[str, Any]:
	"""Valores que rellena un atajo. Las fechas relativas («-30») se convierten en AAAA-MM-DD."""
	hoy = hoy or date.today()
	datos = next((dict(v) for c, _n, v in ATAJOS_REPOSITORIOS if c == clave), {})
	for nombre, valor in list(datos.items()):
		if isinstance(valor, list):
			datos[nombre] = [(hoy + timedelta(days=int(x))).isoformat() if re.fullmatch(r"-\d+", x or "") else x for x in valor]
	return datos


# ════════════════════════════════════════════════════════════════════════════
# Construcción de la consulta
# ════════════════════════════════════════════════════════════════════════════

_NECESITA_COMILLAS = re.compile(r'[\s,()"]')


def citar(valor: str) -> str:
	"""Pone comillas a un valor con espacios o comas (como hace gh). No duplica las que ya tenga."""
	valor = valor.strip()
	if not valor or (len(valor) >= 2 and valor.startswith('"') and valor.endswith('"')):
		return valor
	if _NECESITA_COMILLAS.search(valor):
		return '"' + valor.replace('"', "") + '"'
	return valor


def rango(minimo: str, maximo: str) -> str:
	"""``n..m``, ``>=n`` o ``<=m`` (vacío si no hay ninguno)."""
	minimo, maximo = (minimo or "").strip(), (maximo or "").strip()
	if minimo and maximo:
		return f"{minimo}..{maximo}"
	if minimo:
		return f">={minimo}"
	if maximo:
		return f"<={maximo}"
	return ""


def _par(valor: Any) -> tuple[str, str]:
	if isinstance(valor, (list, tuple)):
		primero = str(valor[0]) if len(valor) > 0 and valor[0] is not None else ""
		segundo = str(valor[1]) if len(valor) > 1 and valor[1] is not None else ""
		return primero, segundo
	return (str(valor or ""), "")


def _lista(valor: Any) -> list[str]:
	if isinstance(valor, (list, tuple)):
		return [str(v) for v in valor if str(v).strip()]
	return [v.strip() for v in str(valor or "").split(",") if v.strip()]


def _agrupar_o(fragmentos: list[str]) -> str:
	if len(fragmentos) == 1:
		return fragmentos[0]
	return "(" + " OR ".join(sorted(fragmentos)) + ")"


def fragmento(filtro: Filtro, valor: Any, tipo: str) -> str:
	"""Parte de la consulta que genera un filtro con su valor (``""`` si no aporta nada)."""
	if filtro.parametro or valor in (None, "", [], ()):
		return ""
	avanzada = tipo in TIPOS_AVANZADOS
	if filtro.control == TEXTO:
		incluidos, excluidos = [], []
		for parte in _lista(valor):
			if parte.startswith("-") and len(parte) > 1:
				excluidos.append(f"-{filtro.calificador}:{citar(parte[1:])}")
			else:
				incluidos.append(f"{filtro.calificador}:{citar(parte)}")
		partes = []
		if incluidos:
			partes.append(_agrupar_o(incluidos) if filtro.agrupar_o and avanzada else " ".join(incluidos))
		partes.extend(excluidos)
		return " ".join(partes)
	if filtro.control in (NUMERO, FECHA):
		texto = rango(*_par(valor))
		return f"{filtro.calificador}:{texto}" if texto else ""
	if filtro.control == MAYOR_QUE:
		texto = str(valor).strip()
		return f"{filtro.calificador}:>{texto}" if texto else ""
	if filtro.control == DESPLEGABLE:
		texto = str(valor).strip()
		if not texto:
			return ""
		return f"{filtro.calificador}:{citar(texto)}" if filtro.calificador else texto
	if filtro.control == EN:
		elegidos = _lista(valor)
		if not elegidos:
			return ""
		if avanzada and len(elegidos) > 1:
			return _agrupar_o([f"in:{e}" for e in elegidos])
		return "in:" + ",".join(elegidos)
	if filtro.control == CASILLA:
		return filtro.calificador if valor else ""
	if filtro.control == EXCLUIR:
		palabras = [p for p in re.split(r"[\s,]+", str(valor)) if p]
		return " ".join(f"NOT {citar(p)}" for p in palabras)
	return ""


def _tiene_operadores(texto: str) -> bool:
	return bool(re.search(r"(?<![\w-])(AND|OR|NOT)(?![\w-])", texto))


def construir_consulta(tipo: str, texto: str = "", valores: dict | None = None) -> str:
	"""Une el texto libre con los filtros guiados (función pura, se prueba sin wx).

	Orden: texto, palabras excluidas (NOT) y calificadores. En la búsqueda avanzada
	de issues, el texto con operadores va entre paréntesis, como hace gh.
	"""
	valores = valores or {}
	texto = (texto or "").strip()
	excluidas, calificadores = [], []
	for filtro in filtros_de(tipo):
		parte = fragmento(filtro, valores.get(filtro.clave), tipo)
		if not parte:
			continue
		(excluidas if filtro.control == EXCLUIR else calificadores).append(parte)
	if texto and tipo in TIPOS_AVANZADOS and calificadores and _tiene_operadores(texto):
		texto = f"( {texto} )"
	return " ".join(p for p in [texto, *excluidas, *calificadores] if p).strip()


def consulta_nuevos_populares(periodo: str = "weekly", lenguaje: str = "", texto: str = "", hoy: date | None = None) -> str:
	"""Aproximación a las tendencias con la API oficial: repositorios creados en el periodo (orden: estrellas)."""
	hoy = hoy or date.today()
	desde = hoy - timedelta(days=DIAS_PERIODO.get(periodo, 7))
	partes = [texto.strip()] if texto and texto.strip() else []
	partes.append(f"created:>={desde.isoformat()}")
	if lenguaje:
		partes.append(f"language:{citar(lenguaje)}")
	return " ".join(partes)


def _nombre_opcion(opciones: Iterable[tuple[str, str]], valor: str) -> str:
	return next((n for v, n in opciones if v == valor), valor)


def descripcion_tendencias(fuente: str, periodo: str, lenguaje: str = "", idioma: str = "") -> str:
	"""Texto legible de una consulta de la página de tendencias («desarrolladores en tendencia esta semana, Python»)."""
	# Frases enteras (no «que» + periodo pegados) para que la traducción pueda reordenarlas.
	cuando = _(_nombre_opcion(PERIODOS, periodo)).lower()
	if fuente == "web_devs":
		partes = [_("desarrolladores en tendencia {periodo}").format(periodo=cuando)]
	else:
		partes = [_("repositorios en tendencia {periodo}").format(periodo=cuando)]
	if lenguaje:
		partes.append(_(_nombre_opcion(LENGUAJES, lenguaje)))
	if idioma and fuente == "web_repos":
		nombre_idioma = _(_nombre_opcion(IDIOMAS_HABLADOS, idioma))
		# En español los idiomas van en minúscula dentro de la frase; en inglés, con mayúscula («in Spanish»).
		partes.append(_("en {i}").format(i=nombre_idioma.lower() if i18n.idioma_corto() == "es" else nombre_idioma))
	return ", ".join(partes)


def preparar_busqueda(tipo: str, texto: str = "", valores: dict | None = None, orden: str = "", direccion: str = "desc",
	hoy: date | None = None, host: str = HOST_GITHUB) -> dict:
	"""Todo lo que necesita la ventana para buscar: consulta, orden y parámetros de la petición.

	Devuelve el diccionario que espera ``VentanaPrincipal.buscar`` (``tipo``,
	``nombre_tipo``, ``consulta``, ``orden``, ``direccion``...) más ``filtros``
	(valores de los controles, para el historial), ``search_type``,
	``repositorio`` (etiquetas), ``fuente``, ``periodo``, ``lenguaje``,
	``idioma`` (tendencias) y ``url_web``.
	"""
	valores = dict(valores or {})
	texto = (texto or "").strip()
	datos: dict[str, Any] = {
		"tipo": tipo, "nombre_tipo": _(TIPOS.get(tipo, tipo)).lower(), "texto": texto, "filtros": valores,
		"orden": orden, "direccion": direccion if direccion in ("asc", "desc") else "desc",
		"search_type": "", "repositorio": "",
	}
	for filtro in filtros_de(tipo):
		if filtro.parametro and filtro.parametro != "atajo":
			datos[filtro.parametro] = str(valores.get(filtro.clave) or "").strip()
	if not any(o == orden for o, _n in ORDENES.get(tipo, [])):
		datos["orden"] = ""
	if tipo == "trending":
		datos["fuente"] = datos.get("fuente") or "api"
		datos["periodo"] = datos.get("periodo") or "daily"
		datos["lenguaje"] = str(valores.get("lenguaje") or "")
		if datos["fuente"] == "api":
			datos["consulta"] = consulta_nuevos_populares(datos["periodo"], datos["lenguaje"], texto, hoy)
			datos["orden"], datos["direccion"] = "stars", "desc"
		else:
			datos["consulta"] = descripcion_tendencias(datos["fuente"], datos["periodo"], datos["lenguaje"], datos.get("idioma", ""))
	else:
		datos["consulta"] = construir_consulta(tipo, texto, valores)
	if datos.get("search_type"):
		datos["orden"] = ""
	datos["url_web"] = url_navegador(tipo, datos["consulta"], host, datos["orden"], datos["direccion"], datos)
	return datos


# ════════════════════════════════════════════════════════════════════════════
# Validación
# ════════════════════════════════════════════════════════════════════════════

_TOKEN = re.compile(r'(?:[^\s"]+|"[^"]*")+')
_CALIFICADOR = re.compile(r'^-?[\w.\-]+:')
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def tokens(consulta: str) -> list[str]:
	return _TOKEN.findall(consulta or "")


def contar_operadores(consulta: str) -> int:
	"""Operadores AND, OR y NOT fuera de comillas."""
	return sum(1 for t in tokens(consulta) if t.strip("()") in ("AND", "OR", "NOT"))


def texto_sin_calificadores(consulta: str) -> str:
	"""Lo que cuenta para el límite de 256 caracteres: sin calificadores, operadores ni paréntesis."""
	palabras = []
	for token in tokens(consulta):
		limpio = token.strip("()")
		if not limpio or limpio in ("AND", "OR", "NOT") or _CALIFICADOR.match(limpio):
			continue
		palabras.append(limpio)
	return " ".join(palabras)


def fecha_valida(texto: str) -> bool:
	if not _FECHA.match(texto or ""):
		return False
	try:
		date.fromisoformat(texto)
	except ValueError:
		return False
	return True


def _entero(texto: str) -> int | None:
	texto = (texto or "").strip()
	return int(texto) if texto.isdigit() else None


@dataclass(frozen=True)
class Problema:
	"""Un problema de la consulta: ``clave`` del filtro (``"texto"`` o ``""`` si es general) y mensaje."""

	clave: str
	mensaje: str


def validar(tipo: str, texto: str = "", valores: dict | None = None, datos: dict | None = None) -> list[Problema]:
	"""Comprueba la búsqueda antes de enviarla. Devuelve los problemas (lista vacía = válida)."""
	valores = valores or {}
	datos = datos if datos is not None else preparar_busqueda(tipo, texto, valores)
	problemas: list[Problema] = []
	for filtro in filtros_de(tipo):
		valor = valores.get(filtro.clave)
		nombre = _(filtro.etiqueta)
		if filtro.control == NUMERO:
			minimo, maximo = _par(valor)
			for texto_numero, cual in ((minimo, _("el mínimo")), (maximo, _("el máximo"))):
				if texto_numero.strip() and _entero(texto_numero) is None:
					problemas.append(Problema(filtro.clave, _("«{f}»: {c} debe ser un número entero, sin puntos ni letras.").format(f=nombre, c=cual)))
			if _entero(minimo) is not None and _entero(maximo) is not None and _entero(minimo) > _entero(maximo):
				problemas.append(Problema(filtro.clave, _("«{f}»: el mínimo es mayor que el máximo.").format(f=nombre)))
		elif filtro.control == FECHA:
			desde, hasta = _par(valor)
			for texto_fecha, cual in ((desde, _("desde")), (hasta, _("hasta"))):
				if texto_fecha.strip() and not fecha_valida(texto_fecha.strip()):
					problemas.append(Problema(filtro.clave, _("«{f}», {c}: escriba una fecha válida con la forma AAAA-MM-DD, "
						"por ejemplo 2026-01-31.").format(f=nombre, c=cual)))
			if fecha_valida(desde.strip()) and fecha_valida(hasta.strip()) and desde.strip() > hasta.strip():
				problemas.append(Problema(filtro.clave, _("«{f}»: la fecha «desde» es posterior a «hasta».").format(f=nombre)))
		elif filtro.control == MAYOR_QUE and str(valor or "").strip() and _entero(str(valor)) is None:
			problemas.append(Problema(filtro.clave, _("«{f}»: escriba un número entero.").format(f=nombre)))
		elif filtro.control == TEXTO and filtro.calificador == "repo":
			for parte in _lista(valor):
				if "/" not in parte.lstrip("-").strip("/"):
					problemas.append(Problema(filtro.clave, _("«{f}»: «{p}» debe tener la forma dueño/nombre.").format(f=nombre, p=parte)))
	consulta = datos.get("consulta", "")
	if tipo == "trending":
		return problemas
	if tipo == "labels":
		repositorio = str(datos.get("repositorio") or "").strip().strip("/")
		if not re.fullmatch(r"[\w.\-]+/[\w.\-]+", repositorio):
			problemas.append(Problema("repositorio", _("Para buscar etiquetas escriba el repositorio con la forma dueño/nombre.")))
		if any(_CALIFICADOR.match(t) for t in tokens(texto)):
			problemas.append(Problema("texto", _("La búsqueda de etiquetas no admite calificadores: escriba solo palabras.")))
		if not texto.strip():
			problemas.append(Problema("texto", _("Escriba alguna palabra del nombre o de la descripción de la etiqueta.")))
		return problemas
	if not consulta:
		problemas.append(Problema("texto", _("Escriba un texto o elija algún filtro.")))
		return problemas
	if len(texto_sin_calificadores(consulta)) > MAXIMO_TEXTO:
		problemas.append(Problema("texto", _("El texto de búsqueda tiene más de {n} caracteres (sin contar los calificadores); "
			"GitHub no lo admite.").format(n=MAXIMO_TEXTO)))
	operadores = contar_operadores(consulta)
	if operadores > MAXIMO_OPERADORES:
		problemas.append(Problema("texto", _("La consulta tiene {n} operadores AND, OR o NOT y GitHub admite como mucho {m}. "
			"Tenga en cuenta que varios repositorios, dueños o palabras excluidas también los añaden.").format(n=operadores, m=MAXIMO_OPERADORES)))
	if tipo == "code" and not texto_sin_calificadores(consulta) and "filename:" not in consulta:
		problemas.append(Problema("texto", _("La búsqueda de código necesita al menos una palabra, salvo si indica un nombre de archivo.")))
	if tipo == "issues" and datos.get("search_type"):
		if valores.get("tipo") != "is:issue":
			problemas.append(Problema("tipo", _("La búsqueda semántica o híbrida solo busca issues: elija «Solo issues» en «Tipo».")))
	if tipo == "issues" and re.search(r"(?:^|\s)\(", texto) and texto.count("(") != texto.count(")"):
		problemas.append(Problema("texto", _("Los paréntesis del texto no están equilibrados.")))
	return problemas


# ════════════════════════════════════════════════════════════════════════════
# Navegador y errores
# ════════════════════════════════════════════════════════════════════════════

_TIPO_WEB = {
	"repositories": "repositories", "code": "code", "issues": "issues", "users": "users", "commits": "commits",
	"topics": "topics", "discussions": "discussions", "trending": "repositories",
}


def url_tendencias(fuente: str, periodo: str = "daily", lenguaje: str = "", idioma: str = "") -> str:
	"""Dirección de github.com/trending (repositorios o desarrolladores)."""
	ruta = "https://github.com/trending" + ("/developers" if fuente == "web_devs" else "")
	if lenguaje:
		ruta += "/" + quote(lenguaje.lower().replace(" ", "-"), safe="-")
	parametros = {"since": periodo if periodo in DIAS_PERIODO else "daily"}
	if idioma and fuente != "web_devs":
		parametros["spoken_language_code"] = idioma
	return f"{ruta}?{urlencode(parametros)}"


def url_navegador(tipo: str, consulta: str, host: str = HOST_GITHUB, orden: str = "", direccion: str = "desc",
	datos: dict | None = None) -> str:
	"""Dirección para «Abrir en el navegador» (lo mismo que ``gh search --web``)."""
	datos = datos or {}
	raiz = "https://" + (host or HOST_GITHUB).replace("https://", "").replace("http://", "").strip("/")
	if tipo == "trending" and datos.get("fuente") in ("web_repos", "web_devs"):
		return url_tendencias(datos["fuente"], datos.get("periodo", "daily"), datos.get("lenguaje", ""), datos.get("idioma", ""))
	if tipo == "labels":
		repositorio = str(datos.get("repositorio") or "").strip("/")
		texto = datos.get("texto") or consulta
		return f"{raiz}/{repositorio}/labels?{urlencode({'q': texto})}" if repositorio else ""
	if not consulta:
		return ""
	tipo_web = _TIPO_WEB.get(tipo, "repositories")
	if tipo == "issues" and (datos.get("filtros") or {}).get("tipo") == "is:pr":
		tipo_web = "pullrequests"
	parametros = {"q": consulta, "type": tipo_web}
	if orden:
		parametros["s"] = orden
		parametros["o"] = direccion
	return f"{raiz}/search?{urlencode(parametros)}"


_ERRORES_422: list[tuple[str, str]] = [
	(r"cannot be searched either because the resources do not exist or you do not have permission",
		N_("Alguno de los usuarios, organizaciones o repositorios indicados no existe o la cuenta no tiene permiso para verlo.")),
	(r"only the first 1000 search results",
		N_("GitHub solo devuelve los 1000 primeros resultados de una búsqueda. Acote la consulta (por ejemplo con fechas) o use «Traer todos».")),
	(r"must include at least one user, organization, or repository",
		N_("Esta búsqueda necesita al menos un usuario, una organización o un repositorio.")),
	(r"only logical operators|without any search terms",
		N_("La consulta solo tiene operadores (AND, OR, NOT) y ninguna palabra que buscar.")),
	(r"more than (five|5) .*operators|too many .*operators",
		N_("La consulta tiene más de cinco operadores AND, OR o NOT.")),
	(r"(longer than|less than|more than) 256 characters|query is too long",
		N_("La consulta es demasiado larga: el texto no puede pasar de 256 caracteres.")),
	(r"none of the search qualifiers apply",
		N_("Ninguno de los calificadores sirve para este tipo de búsqueda.")),
	(r"repository_id",
		N_("Para buscar etiquetas hace falta el repositorio.")),
	(r"semantic|hybrid|search_type",
		N_("GitHub no ha aceptado la búsqueda semántica o híbrida: recuerde que exige sesión iniciada y solo busca issues.")),
	(r"is:issue|is:pull-request|is:pr",
		N_("Indique si busca issues o pull requests (filtro «Tipo»).")),
	(r"invalid.*date|date.*invalid",
		N_("Alguna fecha no es válida: use la forma AAAA-MM-DD.")),
]


def traducir_error_busqueda(error: BaseException) -> str:
	"""Mensaje en español para los 422 típicos de la búsqueda (o el que ya traía el error)."""
	original = getattr(error, "mensaje_usuario", None) or str(error)
	if getattr(error, "codigo_http", None) != 422:
		return original
	textos = [str(getattr(error, "detalle", "") or "")]
	for detalle in getattr(error, "errores", None) or []:
		textos.append(str(detalle.get("message", detalle)) if isinstance(detalle, dict) else str(detalle))
	completo = " ".join(textos)
	for patron, mensaje in _ERRORES_422:
		if re.search(patron, completo, re.IGNORECASE):
			return _(mensaje)
	return _("GitHub no acepta la consulta. Revise los calificadores y su formato.") + f" ({original})"


# ════════════════════════════════════════════════════════════════════════════
# Resultados: text-match y avisos
# ════════════════════════════════════════════════════════════════════════════

PROPIEDADES = {
	"body": N_("el cuerpo"), "title": N_("el título"), "content": N_("el contenido"), "path": N_("la ruta"), "name": N_("el nombre"),
	"description": N_("la descripción"), "message": N_("el mensaje"), "login": N_("el usuario"), "email": N_("el correo"),
	"short_description": N_("la descripción breve"), "display_name": N_("el nombre visible"), "comments": N_("los comentarios"),
	"full_name": N_("el nombre"), "fullname": N_("el nombre"), "aliases": N_("los alias"), "readme": N_("el README"),
}


def resumen_coincidencias(elemento: dict, maximo: int = 3, largo: int = 160) -> str:
	"""«En el cuerpo: «…fragmento…»; en el título: «…»» a partir de ``text_matches``."""
	partes = []
	for coincidencia in (elemento.get("text_matches") or [])[:maximo]:
		if not isinstance(coincidencia, dict):
			continue
		texto = " ".join(str(coincidencia.get("fragment") or "").split())
		if not texto:
			continue
		if len(texto) > largo:
			marcas = coincidencia.get("matches") or []
			buscado = str((marcas[0] or {}).get("text") or "") if marcas and isinstance(marcas[0], dict) else ""
			posicion = max(0, texto.lower().find(buscado.lower())) if buscado else 0
			inicio = max(0, min(posicion - largo // 3, len(texto) - largo))
			texto = ("…" if inicio else "") + texto[inicio:inicio + largo].strip() + ("…" if inicio + largo < len(texto) else "")
		propiedad = str(coincidencia.get("property") or "")
		donde = PROPIEDADES.get(propiedad, propiedad)
		partes.append(_("en {d}: «{t}»").format(d=_(donde), t=texto) if donde else f"«{texto}»")
	resumen = "; ".join(partes)
	return resumen[:1].upper() + resumen[1:]


def avisos_resultado(total: int | None, incompleto: bool | None) -> list[str]:
	"""Avisos para la etiqueta de la lista: tope de 1000 y resultados incompletos."""
	avisos = []
	if total is not None and total > MAXIMO_RESULTADOS:
		avisos.append(_("mostrando como mucho {m} de {t}: GitHub solo devuelve {m}").format(
			m=MAXIMO_RESULTADOS, t=f"{total:,}".replace(",", ".")))
	if incompleto:
		avisos.append(_("puede que falten resultados: GitHub cortó la búsqueda por tiempo"))
	return avisos


# ════════════════════════════════════════════════════════════════════════════
# «Traer todos»: partir el intervalo de fechas para pasar del tope de 1000
# ════════════════════════════════════════════════════════════════════════════

#: Calificador de fecha que se parte en cada tipo (código no tiene fecha).
CAMPOS_FECHA_TODOS = {"repositories": "created", "issues": "created", "users": "created", "commits": "author-date", "topics": "created"}
INICIO_GITHUB = date(2007, 10, 1)
POR_PAGINA_TODOS = 100


@dataclass
class ResultadoTodos:
	elementos: list = field(default_factory=list)
	peticiones: int = 0
	avisos: list[str] = field(default_factory=list)
	cancelado: bool = False


def estimar_peticiones(total: int) -> int:
	"""Peticiones aproximadas de «Traer todos»: páginas de 100 más los tanteos de cada trozo."""
	if total <= 0:
		return 1
	trozos = math.ceil(total / MAXIMO_RESULTADOS)
	return math.ceil(total / POR_PAGINA_TODOS) + 2 * trozos


def extraer_intervalo(consulta: str, campo: str, hoy: date | None = None) -> tuple[str, date, date]:
	"""Quita ``campo:...`` de la consulta y devuelve ``(resto, desde, hasta)``.

	Admite ``a..b``, ``>=a``, ``>a``, ``<=b``, ``<b`` y una fecha sola. Sin el
	calificador, el intervalo va desde la creación de GitHub hasta hoy.
	"""
	hoy = hoy or date.today()
	desde, hasta = INICIO_GITHUB, hoy
	patron = re.compile(rf"(?<!\S){re.escape(campo)}:(\S+)")
	coincidencia = patron.search(consulta)
	if coincidencia:
		valor = coincidencia.group(1)

		def dia(texto: str, defecto: date) -> date:
			texto = texto.strip("*")[:10]
			return date.fromisoformat(texto) if fecha_valida(texto) else defecto

		if ".." in valor:
			izquierda, derecha = valor.split("..", 1)
			desde, hasta = dia(izquierda, desde), dia(derecha, hasta)
		elif valor.startswith(">="):
			desde = dia(valor[2:], desde)
		elif valor.startswith(">"):
			desde = dia(valor[1:], desde) + timedelta(days=1)
		elif valor.startswith("<="):
			hasta = dia(valor[2:], hasta)
		elif valor.startswith("<"):
			hasta = dia(valor[1:], hasta) - timedelta(days=1)
		else:
			desde = hasta = dia(valor, hoy)
		consulta = (consulta[:coincidencia.start()] + consulta[coincidencia.end():]).strip()
		consulta = re.sub(r"\s{2,}", " ", consulta)
	return consulta, desde, hasta


def traer_todos(
	buscar: Callable[[str, int], Any],
	consulta: str,
	campo: str,
	hoy: date | None = None,
	cancelado: Callable[[], bool] | None = None,
	progreso: Callable[[int, int], None] | None = None,
	maximo_peticiones: int = 500,
) -> ResultadoTodos:
	"""Trae más de 1000 resultados partiendo el intervalo de ``campo`` por la mitad.

	:param buscar: ``(consulta, numero_pagina) -> Pagina`` con 100 por página.
	:param cancelado: si devuelve ``True`` se para y se entrega lo que haya.
	:param progreso: ``(elementos, peticiones)`` tras cada petición.
	"""
	base, desde, hasta = extraer_intervalo(consulta, campo, hoy)
	resultado = ResultadoTodos()
	vistos: set = set()
	pendientes: list[tuple[date, date]] = [(desde, hasta)]

	def anotar(pagina: Any) -> None:
		for elemento in getattr(pagina, "elementos", []) or []:
			clave = elemento.get("node_id") or elemento.get("id") or elemento.get("sha") or elemento.get("html_url") if isinstance(elemento, dict) else id(elemento)
			if clave in vistos:
				continue
			vistos.add(clave)
			resultado.elementos.append(elemento)

	def pedir(texto: str, numero: int) -> Any:
		if cancelado and cancelado():
			resultado.cancelado = True
			return None
		if resultado.peticiones >= maximo_peticiones:
			if _("Se ha llegado al máximo de peticiones de «Traer todos».") not in resultado.avisos:
				resultado.avisos.append(_("Se ha llegado al máximo de peticiones de «Traer todos»."))
			return None
		resultado.peticiones += 1
		pagina = buscar(texto, numero)
		if progreso:
			progreso(len(resultado.elementos), resultado.peticiones)
		return pagina

	try:
		while pendientes:
			inicio, fin = pendientes.pop(0)
			intervalo = inicio.isoformat() if inicio == fin else f"{inicio.isoformat()}..{fin.isoformat()}"
			texto = f"{base} {campo}:{intervalo}".strip()
			primera = pedir(texto, 1)
			if primera is None:
				break
			total = primera.total or 0
			if total > MAXIMO_RESULTADOS and inicio < fin:
				mitad = inicio + (fin - inicio) // 2
				pendientes[:0] = [(inicio, mitad), (mitad + timedelta(days=1), fin)]
				continue
			if total > MAXIMO_RESULTADOS:
				resultado.avisos.append(_("El día {d} tiene más de 1000 resultados: solo se traen 1000.").format(d=inicio.isoformat()))
			anotar(primera)
			numero, actual = 1, primera
			while getattr(actual, "hay_mas", False) and numero * POR_PAGINA_TODOS < min(total, MAXIMO_RESULTADOS):
				numero += 1
				actual = pedir(texto, numero)
				if actual is None:
					break
				anotar(actual)
			if resultado.cancelado or resultado.peticiones >= maximo_peticiones:
				break
	except LimiteAlcanzado as error:
		resultado.avisos.append(_("Se ha alcanzado el límite de búsquedas de GitHub ({m}); se muestran los obtenidos hasta ahora.").format(
			m=error.mensaje_usuario))
	return resultado


# ════════════════════════════════════════════════════════════════════════════
# Tendencias: github.com/trending (sin API oficial)
# ════════════════════════════════════════════════════════════════════════════

DURACION_CACHE_TENDENCIAS = 3600.0
AGENTE_TENDENCIAS = "GithubAccesible/{v} (trending page, read once on user request)"


class ErrorTendencias(ErrorGitHub):
	"""No se ha podido leer la página de tendencias (red, límite o formato cambiado)."""


_cache_tendencias: dict[str, tuple[float, list[dict]]] = {}
_candado_tendencias = threading.Lock()


def vaciar_cache_tendencias() -> None:
	with _candado_tendencias:
		_cache_tendencias.clear()


def _version() -> str:
	try:
		from app.core.version import APP_VERSION

		return APP_VERSION
	except Exception:  # noqa: BLE001 - sin la versión, el agente lleva «0»
		return "0"


def _obtener_html(url: str) -> str:
	"""Descarga la página con un User-Agent propio (una sola petición, sin bucles)."""
	import requests

	try:
		respuesta = requests.get(url, headers={"User-Agent": AGENTE_TENDENCIAS.format(v=_version()), "Accept": "text/html",
			"Accept-Language": "es,en;q=0.8"}, timeout=(10, 30))
	except requests.RequestException as error:
		raise ErrorTendencias(_("No se pudo conectar con github.com para leer las tendencias."), None, str(error)) from error
	if respuesta.status_code == 429:
		raise ErrorTendencias(_("GitHub pide esperar antes de volver a leer las tendencias."), 429, url)
	if respuesta.status_code >= 400:
		raise ErrorTendencias(_("GitHub ha respondido con el error {c} al leer las tendencias.").format(c=respuesta.status_code),
			respuesta.status_code, url)
	respuesta.encoding = respuesta.encoding or "utf-8"
	return respuesta.text


def leer_tendencias(fuente: str = "web_repos", periodo: str = "daily", lenguaje: str = "", idioma: str = "",
	obtener: Callable[[str], str] | None = None, ahora: Callable[[], float] = time.monotonic) -> list[dict]:
	"""Repositorios o desarrolladores en tendencia. Se guarda una hora en memoria por dirección."""
	url = url_tendencias(fuente, periodo, lenguaje, idioma)
	momento = ahora()
	with _candado_tendencias:
		guardado = _cache_tendencias.get(url)
		if guardado and momento - guardado[0] < DURACION_CACHE_TENDENCIAS:
			log.debug("Tendencias desde la caché: %s", url)
			return [dict(e) for e in guardado[1]]
	html = (obtener or _obtener_html)(url)
	elementos = analizar_tendencias(html, "desarrolladores" if fuente == "web_devs" else "repositorios")
	with _candado_tendencias:
		_cache_tendencias[url] = (momento, elementos)
	return [dict(e) for e in elementos]


def _numero(texto: str) -> int | None:
	coincidencia = re.search(r"\d[\d,.\s]*", texto or "")
	if not coincidencia:
		return None
	cifras = re.sub(r"\D", "", coincidencia.group(0))
	return int(cifras) if cifras else None


def _limpio(partes: list[str]) -> str:
	return " ".join(" ".join(partes).split())


_VACIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _AnalizadorTendencias(HTMLParser):
	"""Recorre los ``<article class="Box-row">`` de github.com/trending."""

	def __init__(self, que: str) -> None:
		super().__init__(convert_charrefs=True)
		self.desarrolladores = que == "desarrolladores"
		self.pila: list[tuple[str, dict[str, str], set[str]]] = []
		self.elementos: list[dict] = []
		self.actual: dict[str, Any] | None = None
		self.nivel = -1
		self.filas = 0

	# ── Estructura ──
	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		atributos = {k: (v or "") for k, v in attrs}
		clases = set(atributos.get("class", "").split())
		if tag == "article" and "Box-row" in clases and self.actual is None:
			self.filas += 1
			self.actual = {"textos": {}, "autores": [], "href_nombre": "", "href_repo": ""}
			identificador = atributos.get("id", "")
			if identificador.startswith("pa-"):
				self.actual["login_id"] = identificador[3:]
			self.nivel = len(self.pila)
		elif self.actual is not None:
			self._inicio_dentro(tag, atributos)
		if tag not in _VACIOS:
			self.pila.append((tag, atributos, clases))

	def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		atributos = {k: (v or "") for k, v in attrs}
		if self.actual is not None:
			self._inicio_dentro(tag, atributos)

	def handle_endtag(self, tag: str) -> None:
		for posicion in range(len(self.pila) - 1, -1, -1):
			if self.pila[posicion][0] == tag:
				del self.pila[posicion:]
				break
		if self.actual is not None and len(self.pila) <= self.nivel:
			self._cerrar()

	def handle_data(self, data: str) -> None:
		if self.actual is None or not data.strip() or data.strip().casefold() == "popular repo":
			return
		destino = self._destino()
		if destino:
			self.actual["textos"].setdefault(destino, []).append(data)

	# ── Dentro de una fila ──
	def _interior(self) -> list[tuple[str, dict[str, str], set[str]]]:
		return self.pila[self.nivel + 1:]

	def _inicio_dentro(self, tag: str, atributos: dict[str, str]) -> None:
		interior = self._interior()
		etiquetas = [t for t, _a, _c in interior]
		if tag == "a":
			href = atributos.get("href", "")
			if self.desarrolladores:
				if "article" in etiquetas and "h1" in etiquetas and not self.actual["href_repo"]:
					self.actual["href_repo"] = href
				elif "h1" in etiquetas and "article" not in etiquetas and not self.actual["href_nombre"]:
					self.actual["href_nombre"] = href
			elif "h2" in etiquetas and not self.actual["href_nombre"]:
				self.actual["href_nombre"] = href
		elif tag == "img" and not self.desarrolladores and "h2" not in etiquetas:
			alternativo = atributos.get("alt", "")
			if alternativo.startswith("@"):
				self.actual["autores"].append(alternativo[1:])

	def _destino(self) -> str:
		for tag, atributos, clases in reversed(self._interior()):
			if self.desarrolladores:
				dentro_repo = any(t == "article" for t, _a, _c in self._interior())
				if dentro_repo:
					if tag == "h1":
						return "repo"
					if tag == "div" and "f6" in clases:
						return "descripcion"
					continue
				if tag == "h1":
					return "nombre"
				if tag == "p" and "f4" in clases:
					return "login"
				continue
			if tag == "h2":
				return "nombre"
			if tag == "a" and atributos.get("href", "").endswith("/stargazers"):
				return "estrellas"
			if tag == "a" and (atributos.get("href", "").endswith("/forks") or atributos.get("href", "").endswith("/network/members")):
				return "bifurcaciones"
			if tag == "span" and atributos.get("itemprop") == "programmingLanguage":
				return "lenguaje"
			if tag == "span" and "float-sm-right" in clases:
				return "periodo"
			if tag == "p":
				return "descripcion"
		return ""

	def _cerrar(self) -> None:
		datos, self.actual, self.nivel = self.actual, None, -1
		textos = {k: _limpio(v) for k, v in datos["textos"].items()}
		if self.desarrolladores:
			login = datos.get("login_id") or textos.get("login") or datos["href_nombre"].strip("/")
			repo = datos["href_repo"].strip("/")
			self.elementos.append({
				"_tipo": "tendencia_dev", "login": login, "name": textos.get("nombre", ""),
				"repo_popular": repo or textos.get("repo", "").replace(" ", ""), "descripcion_repo": textos.get("descripcion", ""),
				"html_url": f"https://github.com/{login}" if login else "",
			})
			return
		nombre = datos["href_nombre"].strip("/") or textos.get("nombre", "").replace(" ", "")
		self.elementos.append({
			"_tipo": "tendencia_repo", "full_name": nombre, "name": nombre.split("/")[-1],
			"owner": {"login": nombre.split("/")[0]} if "/" in nombre else {},
			"description": textos.get("descripcion", ""), "language": textos.get("lenguaje", ""),
			"stargazers_count": _numero(textos.get("estrellas", "")), "forks_count": _numero(textos.get("bifurcaciones", "")),
			"estrellas_periodo": _numero(textos.get("periodo", "")), "periodo_texto": textos.get("periodo", ""),
			"construido_por": list(datos["autores"]), "html_url": f"https://github.com/{nombre}" if nombre else "",
		})


_MENSAJE_FORMATO = (N_("No se ha podido leer la página de tendencias de GitHub: su formato ha cambiado. "
	"Use la fuente «Nuevos y populares (API oficial de GitHub)» o abra las tendencias en el navegador."))


def analizar_tendencias(html: str, que: str = "repositorios") -> list[dict]:
	"""Convierte el HTML de github.com/trending en una lista de diccionarios.

	Lanza ``ErrorTendencias`` con un mensaje claro si el formato ya no es el esperado.
	"""
	analizador = _AnalizadorTendencias(que)
	try:
		analizador.feed(html or "")
		analizador.close()
	except Exception as error:  # noqa: BLE001 - HTML inesperado: se explica a la persona
		raise ErrorTendencias(_(_MENSAJE_FORMATO), None, f"{type(error).__name__}: {error}") from error
	if not analizador.filas:
		if re.search(r"don.t have any trending", html or "", re.IGNORECASE):
			return []
		raise ErrorTendencias(_(_MENSAJE_FORMATO), None, "sin filas Box-row")
	clave = "login" if que == "desarrolladores" else "full_name"
	if any(not e.get(clave) or ("/" not in e[clave] and clave == "full_name") for e in analizador.elementos):
		raise ErrorTendencias(_(_MENSAJE_FORMATO), None, "fila sin nombre")
	return analizador.elementos


def filtrar_local(elementos: list[dict], texto: str) -> list[dict]:
	"""Filtra en local los resultados de la página de tendencias por un texto (sin distinguir mayúsculas)."""
	buscado = (texto or "").casefold().strip()
	if not buscado:
		return elementos
	campos = ("full_name", "description", "language", "login", "name", "repo_popular", "descripcion_repo")
	return [e for e in elementos if buscado in " ".join(str(e.get(c) or "") for c in campos).casefold()]


# ════════════════════════════════════════════════════════════════════════════
# Letras de acceso automáticas
# ════════════════════════════════════════════════════════════════════════════

LETRAS_ACCESO = "abcdefghijklmnopqrstuvwxyzñç"


def letra_de(etiqueta: str) -> str | None:
	posicion = etiqueta.replace("&&", "\0\0").find("&")
	if posicion < 0 or posicion + 1 >= len(etiqueta):
		return None
	return etiqueta[posicion + 1].lower()


def asignar_letras(etiquetas: list[str], ocupadas: Iterable[str] = ()) -> list[str]:
	"""Pone ``&`` en cada etiqueta sin repetir letras (ni las ``ocupadas``).

	Las que ya traen ``&`` se respetan. Prefiere la inicial de una palabra; si no
	queda ninguna letra libre en el texto, añade un número entre paréntesis
	(«Estrellas, máximo (&1):»).
	"""
	usadas = {o.lower() for o in ocupadas}
	usadas.update(letra for e in etiquetas if (letra := letra_de(e)))
	resultado = []
	numeros = iter("123456789")
	for etiqueta in etiquetas:
		if letra_de(etiqueta):
			resultado.append(etiqueta)
			continue
		candidatas = [i for i, c in enumerate(etiqueta) if c.lower() in LETRAS_ACCESO and (i == 0 or not etiqueta[i - 1].isalnum())]
		candidatas += [i for i, c in enumerate(etiqueta) if c.lower() in LETRAS_ACCESO and i not in candidatas]
		elegida = next((i for i in candidatas if etiqueta[i].lower() not in usadas), None)
		if elegida is not None:
			usadas.add(etiqueta[elegida].lower())
			resultado.append(etiqueta[:elegida] + "&" + etiqueta[elegida:])
			continue
		numero = next((n for n in numeros if n not in usadas), None)
		if numero is None:
			resultado.append(etiqueta)
			continue
		usadas.add(numero)
		final = ":" if etiqueta.endswith(":") else ""
		resultado.append(f"{etiqueta[:len(etiqueta) - len(final)]} (&{numero}){final}")
	return resultado
