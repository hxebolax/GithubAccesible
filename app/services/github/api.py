"""Fachada de la API de GitHub: una función por operación, agrupadas por áreas (sin wx).

Cada método es una envoltura fina de un punto de la API REST (o GraphQL)
que devuelve los datos tal como llegan (diccionarios de JSON). Así la
interfaz no conoce rutas ni cabeceras, y las pruebas pueden sustituir el
cliente por uno falso.

Las áreas están repartidas en mezclas (mixins) en varios archivos:

- ``api.py``: cuenta, repositorios, contenidos, ramas, commits, issues,
  pull requests, revisiones, releases, etiquetas e hitos.
- ``api_extra.py``: Actions, gists, notificaciones, organizaciones, equipos,
  búsqueda, seguridad, webhooks, Pages, paquetes, codespaces, claves...
- ``api_graphql.py``: lo que solo existe en GraphQL (Projects, Discussions,
  elementos fijados, contribuciones, resolver conversaciones de revisión).
"""

from __future__ import annotations

import base64
import builtins
from typing import Any
from urllib.parse import quote

from app.services.github.cliente import ClienteGitHub, ErrorValidacion, NoEncontrado, Pagina, SinPermiso

ACEPTAR_DIFF = "application/vnd.github.diff"
ACEPTAR_PATCH = "application/vnd.github.patch"
ACEPTAR_CRUDO = "application/vnd.github.raw+json"
ACEPTAR_HTML = "application/vnd.github.html+json"
ACEPTAR_TEXTO_COMPLETO = "application/vnd.github.full+json"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def ruta_repo(nombre_completo: str) -> str:
	"""«dueño/repo» → «/repos/dueño/repo» (con cada parte escapada)."""
	dueno, _sep, repo = nombre_completo.strip().strip("/").partition("/")
	if not dueno or not repo:
		raise ValueError(_("El repositorio debe tener la forma «dueño/nombre»: {n}").format(n=nombre_completo))
	return f"/repos/{quote(dueno, safe='')}/{quote(repo, safe='')}"


def _q(valor: str) -> str:
	return quote(str(valor), safe="")


def _ruta_archivo(ruta: str) -> str:
	return quote(ruta.strip("/"), safe="/")


def _limpiar(datos: dict[str, Any]) -> dict[str, Any]:
	"""Quita las claves con ``None`` (GitHub interpreta ``null`` como «borrar»)."""
	return {k: v for k, v in datos.items() if v is not None}


class _Base:
	def __init__(self, cliente: ClienteGitHub) -> None:
		self.c = cliente


# ════════════════════════════════════════════════════════════════════════════
# Cuenta y usuarios
# ════════════════════════════════════════════════════════════════════════════


class ApiUsuarios(_Base):
	def yo(self) -> dict:
		return self.c.get("/user")

	def actualizar_perfil(self, **campos: Any) -> dict:
		"""name, email, blog, twitter_username, company, location, hireable, bio."""
		return self.c.patch("/user", _limpiar(campos))

	def usuario(self, login: str) -> dict:
		return self.c.get(f"/users/{_q(login)}")

	def tarjeta_usuario(self, login: str) -> dict:
		return self.c.get(f"/users/{_q(login)}/hovercard")

	def seguidores(self, login: str | None = None, numero: int = 1) -> Pagina:
		return self.c.pagina(f"/users/{_q(login)}/followers" if login else "/user/followers", numero=numero, por_pagina=100)

	def seguidos(self, login: str | None = None, numero: int = 1) -> Pagina:
		return self.c.pagina(f"/users/{_q(login)}/following" if login else "/user/following", numero=numero, por_pagina=100)

	def sigo_a(self, login: str) -> bool:
		return self.c.existe(f"/user/following/{_q(login)}")

	def seguir(self, login: str) -> None:
		self.c.put(f"/user/following/{_q(login)}")

	def dejar_de_seguir(self, login: str) -> None:
		self.c.delete(f"/user/following/{_q(login)}")

	def bloqueados(self) -> list:
		return self.c.todos("/user/blocks")

	def bloquear(self, login: str) -> None:
		self.c.put(f"/user/blocks/{_q(login)}")

	def desbloquear(self, login: str) -> None:
		self.c.delete(f"/user/blocks/{_q(login)}")

	def correos(self) -> list:
		return self.c.todos("/user/emails")

	def anadir_correos(self, correos: list[str]) -> list:
		return self.c.post("/user/emails", {"emails": correos})

	def borrar_correos(self, correos: list[str]) -> None:
		self.c.delete("/user/emails", {"emails": correos})

	def visibilidad_correo(self, visibilidad: str) -> list:
		return self.c.patch("/user/email/visibility", {"visibility": visibilidad})

	def claves_ssh(self) -> list:
		return self.c.todos("/user/keys")

	def anadir_clave_ssh(self, titulo: str, clave: str) -> dict:
		return self.c.post("/user/keys", {"title": titulo, "key": clave.strip()})

	def borrar_clave_ssh(self, id_clave: int) -> None:
		self.c.delete(f"/user/keys/{int(id_clave)}")

	def claves_firma_ssh(self) -> list:
		return self.c.todos("/user/ssh_signing_keys")

	def anadir_clave_firma_ssh(self, titulo: str, clave: str) -> dict:
		return self.c.post("/user/ssh_signing_keys", {"title": titulo, "key": clave.strip()})

	def borrar_clave_firma_ssh(self, id_clave: int) -> None:
		self.c.delete(f"/user/ssh_signing_keys/{int(id_clave)}")

	def claves_gpg(self) -> list:
		return self.c.todos("/user/gpg_keys")

	def anadir_clave_gpg(self, nombre: str, clave_armadura: str) -> dict:
		return self.c.post("/user/gpg_keys", {"name": nombre, "armored_public_key": clave_armadura})

	def borrar_clave_gpg(self, id_clave: int) -> None:
		self.c.delete(f"/user/gpg_keys/{int(id_clave)}")

	def redes_sociales(self) -> list:
		return self.c.todos("/user/social_accounts")

	def eventos_recibidos(self, login: str, numero: int = 1) -> Pagina:
		"""Lo que hacen las personas y repositorios que sigue (el «feed»)."""
		return self.c.pagina(f"/users/{_q(login)}/received_events", numero=numero, por_pagina=50)

	def eventos_de(self, login: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"/users/{_q(login)}/events", numero=numero, por_pagina=50)

	def limite_uso(self) -> dict:
		return self.c.get("/rate_limit", condicional=False)

	def interacciones_limitadas(self) -> dict:
		return self.c.get("/user/interaction-limits")


# ════════════════════════════════════════════════════════════════════════════
# Repositorios
# ════════════════════════════════════════════════════════════════════════════


class ApiRepositorios(_Base):
	def mis_repositorios(self, numero: int = 1, tipo: str = "owner", orden: str = "updated", afiliacion: str = "") -> Pagina:
		params: dict[str, Any] = {"sort": orden}
		if afiliacion:
			params["affiliation"] = afiliacion
		else:
			params["type"] = tipo
		return self.c.pagina("/user/repos", params, numero, 100)

	def repositorios_de(self, login: str, numero: int = 1, orden: str = "updated") -> Pagina:
		return self.c.pagina(f"/users/{_q(login)}/repos", {"sort": orden}, numero, 100)

	def repositorios_org(self, org: str, numero: int = 1, tipo: str = "all") -> Pagina:
		return self.c.pagina(f"/orgs/{_q(org)}/repos", {"type": tipo, "sort": "updated"}, numero, 100)

	def repositorio(self, nombre: str) -> dict:
		return self.c.get(ruta_repo(nombre))

	def crear_repositorio(self, nombre: str, descripcion: str = "", privado: bool = False, org: str = "",
		auto_init: bool = False, gitignore: str = "", licencia: str = "", **extra: Any) -> dict:
		datos = _limpiar({
			"name": nombre, "description": descripcion or None, "private": privado, "auto_init": auto_init,
			"gitignore_template": gitignore or None, "license_template": licencia or None, **extra,
		})
		return self.c.post(f"/orgs/{_q(org)}/repos" if org else "/user/repos", datos)

	def crear_desde_plantilla(self, plantilla: str, dueno: str, nombre: str, descripcion: str = "",
		privado: bool = False, todas_las_ramas: bool = False) -> dict:
		return self.c.post(f"{ruta_repo(plantilla)}/generate", {
			"owner": dueno, "name": nombre, "description": descripcion, "private": privado,
			"include_all_branches": todas_las_ramas,
		})

	def editar_repositorio(self, nombre: str, **campos: Any) -> dict:
		"""name, description, homepage, private, visibility, has_issues, has_projects, has_wiki,
		has_discussions, is_template, default_branch, allow_squash_merge, allow_merge_commit,
		allow_rebase_merge, allow_auto_merge, delete_branch_on_merge, archived, web_commit_signoff_required..."""
		return self.c.patch(ruta_repo(nombre), _limpiar(campos))

	def borrar_repositorio(self, nombre: str) -> None:
		self.c.delete(ruta_repo(nombre))

	def transferir(self, nombre: str, nuevo_dueno: str, nuevo_nombre: str = "") -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/transfer", _limpiar({"new_owner": nuevo_dueno, "new_name": nuevo_nombre or None}))

	def bifurcar(self, nombre: str, org: str = "", nombre_nuevo: str = "", solo_rama_principal: bool = False) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/forks", _limpiar({
			"organization": org or None, "name": nombre_nuevo or None, "default_branch_only": solo_rama_principal,
		}))

	def bifurcaciones(self, nombre: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"{ruta_repo(nombre)}/forks", {"sort": "newest"}, numero, 100)

	def sincronizar_bifurcacion(self, nombre: str, rama: str) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/merge-upstream", {"branch": rama})

	def temas(self, nombre: str) -> list[str]:
		return (self.c.get(f"{ruta_repo(nombre)}/topics") or {}).get("names", [])

	def poner_temas(self, nombre: str, temas: list[str]) -> list[str]:
		return (self.c.put(f"{ruta_repo(nombre)}/topics", {"names": temas}) or {}).get("names", [])

	def lenguajes(self, nombre: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/languages")

	def colaboradores_codigo(self, nombre: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"{ruta_repo(nombre)}/contributors", numero=numero, por_pagina=100)

	def licencia(self, nombre: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/license")

	def salud_comunidad(self, nombre: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/community/profile")

	def readme(self, nombre: str, ref: str = "") -> str:
		return self.c.texto(f"{ruta_repo(nombre)}/readme", ACEPTAR_CRUDO, {"ref": ref} if ref else None)

	def readme_html(self, nombre: str, ref: str = "") -> str:
		return self.c.texto(f"{ruta_repo(nombre)}/readme", ACEPTAR_HTML, {"ref": ref} if ref else None)

	# Estrellas y vigilancia
	def tiene_estrella(self, nombre: str) -> bool:
		return self.c.existe(f"/user/starred/{nombre.strip('/')}")

	def dar_estrella(self, nombre: str) -> None:
		self.c.put(f"/user/starred/{nombre.strip('/')}")

	def quitar_estrella(self, nombre: str) -> None:
		self.c.delete(f"/user/starred/{nombre.strip('/')}")

	def con_estrella(self, login: str | None = None, numero: int = 1) -> Pagina:
		ruta = f"/users/{_q(login)}/starred" if login else "/user/starred"
		return self.c.pagina(ruta, {"sort": "created"}, numero, 100)

	def observadores_estrella(self, nombre: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"{ruta_repo(nombre)}/stargazers", numero=numero, por_pagina=100)

	def vigilados(self, numero: int = 1) -> Pagina:
		return self.c.pagina("/user/subscriptions", numero=numero, por_pagina=100)

	def suscripcion(self, nombre: str) -> dict | None:
		respuesta = self.c.peticion("GET", f"{ruta_repo(nombre)}/subscription", permitir=(404,), condicional=False)
		return respuesta.json() if respuesta.status_code == 200 else None

	def vigilar(self, nombre: str, suscrito: bool = True, ignorado: bool = False) -> dict:
		return self.c.put(f"{ruta_repo(nombre)}/subscription", {"subscribed": suscrito, "ignored": ignorado})

	def dejar_de_vigilar(self, nombre: str) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/subscription")

	# Colaboradores e invitaciones
	def colaboradores(self, nombre: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"{ruta_repo(nombre)}/collaborators", {"affiliation": "all"}, numero, 100)

	def invitar_colaborador(self, nombre: str, login: str, permiso: str = "push") -> Any:
		return self.c.put(f"{ruta_repo(nombre)}/collaborators/{_q(login)}", {"permission": permiso})

	def quitar_colaborador(self, nombre: str, login: str) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/collaborators/{_q(login)}")

	def permiso_de(self, nombre: str, login: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/collaborators/{_q(login)}/permission")

	def invitaciones_repo(self, nombre: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/invitations")

	def cancelar_invitacion_repo(self, nombre: str, id_invitacion: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/invitations/{int(id_invitacion)}")

	def mis_invitaciones(self) -> list:
		return self.c.todos("/user/repository_invitations")

	def aceptar_invitacion(self, id_invitacion: int) -> None:
		self.c.patch(f"/user/repository_invitations/{int(id_invitacion)}")

	def rechazar_invitacion(self, id_invitacion: int) -> None:
		self.c.delete(f"/user/repository_invitations/{int(id_invitacion)}")

	# Tráfico y estadísticas
	def visitas(self, nombre: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/traffic/views")

	def clonados(self, nombre: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/traffic/clones")

	def referentes(self, nombre: str) -> list:
		return self.c.get(f"{ruta_repo(nombre)}/traffic/popular/referrers") or []

	def rutas_populares(self, nombre: str) -> list:
		return self.c.get(f"{ruta_repo(nombre)}/traffic/popular/paths") or []

	def actividad_semanal(self, nombre: str) -> Any:
		return self.c.get(f"{ruta_repo(nombre)}/stats/commit_activity")

	def participacion(self, nombre: str) -> Any:
		return self.c.get(f"{ruta_repo(nombre)}/stats/participation")

	def estadisticas_contribuyentes(self, nombre: str) -> Any:
		return self.c.get(f"{ruta_repo(nombre)}/stats/contributors")

	def actividad(self, nombre: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"{ruta_repo(nombre)}/activity", numero=numero, por_pagina=100)

	def eventos_repo(self, nombre: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"{ruta_repo(nombre)}/events", numero=numero, por_pagina=100)

	# Despliegues y entornos
	def entornos(self, nombre: str) -> list:
		return (self.c.get(f"{ruta_repo(nombre)}/environments") or {}).get("environments", [])

	def crear_entorno(self, nombre: str, entorno: str, **reglas: Any) -> dict:
		return self.c.put(f"{ruta_repo(nombre)}/environments/{_q(entorno)}", _limpiar(reglas) or None)

	def borrar_entorno(self, nombre: str, entorno: str) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/environments/{_q(entorno)}")

	def despliegues(self, nombre: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"{ruta_repo(nombre)}/deployments", numero=numero, por_pagina=100)

	def estados_despliegue(self, nombre: str, id_despliegue: int) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/deployments/{int(id_despliegue)}/statuses")

	def crear_despliegue(self, nombre: str, ref: str, entorno: str = "production", descripcion: str = "") -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/deployments", {"ref": ref, "environment": entorno, "description": descripcion,
			"auto_merge": False})

	def borrar_despliegue(self, nombre: str, id_despliegue: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/deployments/{int(id_despliegue)}")

	# Webhooks y claves de despliegue
	def webhooks(self, nombre: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/hooks")

	def crear_webhook(self, nombre: str, url: str, eventos: list[str], secreto: str = "", tipo_contenido: str = "json",
		activo: bool = True) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/hooks", {
			"name": "web", "active": activo, "events": eventos,
			"config": _limpiar({"url": url, "content_type": tipo_contenido, "secret": secreto or None, "insecure_ssl": "0"}),
		})

	def editar_webhook(self, nombre: str, id_hook: int, **campos: Any) -> dict:
		return self.c.patch(f"{ruta_repo(nombre)}/hooks/{int(id_hook)}", _limpiar(campos))

	def borrar_webhook(self, nombre: str, id_hook: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/hooks/{int(id_hook)}")

	def probar_webhook(self, nombre: str, id_hook: int) -> None:
		self.c.post(f"{ruta_repo(nombre)}/hooks/{int(id_hook)}/tests")

	def entregas_webhook(self, nombre: str, id_hook: int) -> list:
		return self.c.get(f"{ruta_repo(nombre)}/hooks/{int(id_hook)}/deliveries", {"per_page": 50}) or []

	def claves_despliegue(self, nombre: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/keys")

	def anadir_clave_despliegue(self, nombre: str, titulo: str, clave: str, solo_lectura: bool = True) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/keys", {"title": titulo, "key": clave.strip(), "read_only": solo_lectura})

	def borrar_clave_despliegue(self, nombre: str, id_clave: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/keys/{int(id_clave)}")

	# Pages
	def pages(self, nombre: str) -> dict | None:
		respuesta = self.c.peticion("GET", f"{ruta_repo(nombre)}/pages", permitir=(404,), condicional=False)
		return respuesta.json() if respuesta.status_code == 200 else None

	def activar_pages(self, nombre: str, rama: str, carpeta: str = "/", tipo: str = "legacy") -> dict:
		datos: dict[str, Any] = {"build_type": tipo}
		if tipo == "legacy":
			datos["source"] = {"branch": rama, "path": carpeta}
		return self.c.post(f"{ruta_repo(nombre)}/pages", datos)

	def editar_pages(self, nombre: str, **campos: Any) -> None:
		self.c.put(f"{ruta_repo(nombre)}/pages", _limpiar(campos))

	def desactivar_pages(self, nombre: str) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/pages")

	def compilaciones_pages(self, nombre: str) -> list:
		return self.c.get(f"{ruta_repo(nombre)}/pages/builds", {"per_page": 30}) or []

	def compilar_pages(self, nombre: str) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/pages/builds")

	# Plantillas
	def plantillas_gitignore(self) -> list[str]:
		return self.c.get("/gitignore/templates") or []

	def licencias(self) -> list:
		return self.c.get("/licenses", {"per_page": 100}) or []

	def emojis(self) -> dict:
		return self.c.get("/emojis") or {}

	def markdown_a_html(self, texto: str, contexto: str = "") -> str:
		datos: dict[str, Any] = {"text": texto, "mode": "gfm" if contexto else "markdown"}
		if contexto:
			datos["context"] = contexto
		respuesta = self.c.peticion("POST", "/markdown", json_datos=datos, aceptar="text/html", condicional=False)
		return respuesta.text

	def autoenlaces(self, nombre: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/autolinks")

	def propiedades_personalizadas(self, nombre: str) -> list:
		return self.c.get(f"{ruta_repo(nombre)}/properties/values") or []

	def archivo_zip(self, nombre: str, ref: str = "") -> str:
		"""URL para descargar el código en zip (se sigue la redirección)."""
		return self.c.url(f"{ruta_repo(nombre)}/zipball/{_q(ref)}" if ref else f"{ruta_repo(nombre)}/zipball")


# ════════════════════════════════════════════════════════════════════════════
# Contenidos (archivos y carpetas)
# ════════════════════════════════════════════════════════════════════════════


class ApiContenidos(_Base):
	def contenido(self, nombre: str, ruta: str = "", ref: str = "") -> Any:
		"""Lista de una carpeta (lista de dicts) o datos de un archivo (dict con content en base64)."""
		return self.c.get(f"{ruta_repo(nombre)}/contents/{_ruta_archivo(ruta)}", {"ref": ref} if ref else None)

	def leer_archivo(self, nombre: str, ruta: str, ref: str = "") -> tuple[bytes, str]:
		"""Devuelve (bytes, sha). Usa el modo «raw» si el archivo es grande (> 1 MB)."""
		datos = self.contenido(nombre, ruta, ref)
		if isinstance(datos, dict) and datos.get("encoding") == "base64" and datos.get("content"):
			return base64.b64decode(datos["content"]), datos.get("sha", "")
		bruto = self.c.binario(f"{ruta_repo(nombre)}/contents/{_ruta_archivo(ruta)}", "application/vnd.github.raw",
			{"ref": ref} if ref else None)
		return bruto, (datos or {}).get("sha", "") if isinstance(datos, dict) else ""

	def guardar_archivo(self, nombre: str, ruta: str, contenido: bytes, mensaje: str, sha: str = "", rama: str = "",
		autor: dict | None = None) -> dict:
		"""Crea o actualiza un archivo con un commit (``sha`` obligatorio al actualizar)."""
		datos = _limpiar({
			"message": mensaje, "content": base64.b64encode(contenido).decode("ascii"),
			"sha": sha or None, "branch": rama or None, "author": autor,
		})
		return self.c.put(f"{ruta_repo(nombre)}/contents/{_ruta_archivo(ruta)}", datos)

	def borrar_archivo(self, nombre: str, ruta: str, sha: str, mensaje: str, rama: str = "") -> dict:
		return self.c.delete(f"{ruta_repo(nombre)}/contents/{_ruta_archivo(ruta)}",
			_limpiar({"message": mensaje, "sha": sha, "branch": rama or None}))

	def arbol(self, nombre: str, ref: str, recursivo: bool = True) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/git/trees/{_q(ref)}", {"recursive": "1"} if recursivo else None)

	def blob(self, nombre: str, sha: str) -> bytes:
		datos = self.c.get(f"{ruta_repo(nombre)}/git/blobs/{_q(sha)}")
		return base64.b64decode(datos.get("content", "")) if datos.get("encoding") == "base64" else datos.get("content", "").encode()

	def commit_multiple(self, nombre: str, rama: str, mensaje: str, archivos: dict[str, bytes | None]) -> dict:
		"""Un solo commit con varios archivos (``None`` = borrar) usando la API de datos de Git."""
		ref = self.c.get(f"{ruta_repo(nombre)}/git/ref/heads/{_ruta_archivo(rama)}")
		sha_base = ref["object"]["sha"]
		commit_base = self.c.get(f"{ruta_repo(nombre)}/git/commits/{sha_base}")
		elementos = []
		for ruta, datos in archivos.items():
			if datos is None:
				elementos.append({"path": ruta, "mode": "100644", "type": "blob", "sha": None})
			else:
				blob = self.c.post(f"{ruta_repo(nombre)}/git/blobs", {"content": base64.b64encode(datos).decode(), "encoding": "base64"})
				elementos.append({"path": ruta, "mode": "100644", "type": "blob", "sha": blob["sha"]})
		arbol = self.c.post(f"{ruta_repo(nombre)}/git/trees", {"base_tree": commit_base["tree"]["sha"], "tree": elementos})
		commit = self.c.post(f"{ruta_repo(nombre)}/git/commits", {"message": mensaje, "tree": arbol["sha"], "parents": [sha_base]})
		self.c.patch(f"{ruta_repo(nombre)}/git/refs/heads/{_ruta_archivo(rama)}", {"sha": commit["sha"]})
		return commit


# ════════════════════════════════════════════════════════════════════════════
# Ramas, etiquetas, commits, comparaciones, protección y reglas
# ════════════════════════════════════════════════════════════════════════════


class ApiRamas(_Base):
	def ramas(self, nombre: str, numero: int = 1, protegidas: bool | None = None) -> Pagina:
		params = {"protected": str(protegidas).lower()} if protegidas is not None else None
		return self.c.pagina(f"{ruta_repo(nombre)}/branches", params, numero, 100)

	def todas_las_ramas(self, nombre: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/branches")

	def rama(self, nombre: str, rama: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/branches/{_ruta_archivo(rama)}")

	def crear_rama(self, nombre: str, rama: str, desde_sha: str) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/git/refs", {"ref": f"refs/heads/{rama}", "sha": desde_sha})

	def borrar_rama(self, nombre: str, rama: str) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/git/refs/heads/{_ruta_archivo(rama)}")

	def renombrar_rama(self, nombre: str, rama: str, nueva: str) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/branches/{_ruta_archivo(rama)}/rename", {"new_name": nueva})

	def fusionar_rama(self, nombre: str, base: str, cabeza: str, mensaje: str = "") -> Any:
		return self.c.post(f"{ruta_repo(nombre)}/merges", _limpiar({"base": base, "head": cabeza, "commit_message": mensaje or None}))

	def proteccion(self, nombre: str, rama: str) -> dict | None:
		respuesta = self.c.peticion("GET", f"{ruta_repo(nombre)}/branches/{_ruta_archivo(rama)}/protection",
			permitir=(404,), condicional=False)
		return respuesta.json() if respuesta.status_code == 200 else None

	def proteger(self, nombre: str, rama: str, revisiones: int = 1, checks: list[str] | None = None,
		admins: bool = False, historial_lineal: bool = False, forzar: bool = False, borrar: bool = False,
		conversaciones: bool = False, firmas: bool = False) -> dict:
		datos = {
			"required_status_checks": {"strict": True, "contexts": checks} if checks else None,
			"enforce_admins": admins,
			"required_pull_request_reviews": {"required_approving_review_count": revisiones} if revisiones else None,
			"restrictions": None,
			"required_linear_history": historial_lineal,
			"allow_force_pushes": forzar,
			"allow_deletions": borrar,
			"required_conversation_resolution": conversaciones,
		}
		resultado = self.c.put(f"{ruta_repo(nombre)}/branches/{_ruta_archivo(rama)}/protection", datos)
		if firmas:
			self.c.post(f"{ruta_repo(nombre)}/branches/{_ruta_archivo(rama)}/protection/required_signatures")
		return resultado

	def desproteger(self, nombre: str, rama: str) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/branches/{_ruta_archivo(rama)}/protection")

	def reglas(self, nombre: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/rulesets")

	def regla(self, nombre: str, id_regla: int) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/rulesets/{int(id_regla)}")

	def crear_regla(self, nombre: str, datos: dict) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/rulesets", datos)

	def editar_regla(self, nombre: str, id_regla: int, datos: dict) -> dict:
		return self.c.put(f"{ruta_repo(nombre)}/rulesets/{int(id_regla)}", datos)

	def borrar_regla(self, nombre: str, id_regla: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/rulesets/{int(id_regla)}")

	def reglas_de_rama(self, nombre: str, rama: str) -> list:
		return self.c.get(f"{ruta_repo(nombre)}/rules/branches/{_ruta_archivo(rama)}") or []

	def etiquetas_git(self, nombre: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"{ruta_repo(nombre)}/tags", numero=numero, por_pagina=100)

	def crear_etiqueta_git(self, nombre: str, etiqueta: str, sha: str, mensaje: str = "") -> dict:
		if mensaje:
			objeto = self.c.post(f"{ruta_repo(nombre)}/git/tags", {"tag": etiqueta, "message": mensaje, "object": sha, "type": "commit"})
			sha = objeto["sha"]
		return self.c.post(f"{ruta_repo(nombre)}/git/refs", {"ref": f"refs/tags/{etiqueta}", "sha": sha})

	def borrar_etiqueta_git(self, nombre: str, etiqueta: str) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/git/refs/tags/{_ruta_archivo(etiqueta)}")


class ApiCommits(_Base):
	def commits(self, nombre: str, numero: int = 1, rama: str = "", ruta: str = "", autor: str = "",
		desde: str = "", hasta: str = "") -> Pagina:
		params = _limpiar({"sha": rama or None, "path": ruta or None, "author": autor or None,
			"since": desde or None, "until": hasta or None})
		return self.c.pagina(f"{ruta_repo(nombre)}/commits", params, numero, 100)

	def commit(self, nombre: str, sha: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/commits/{_q(sha)}")

	def diff_commit(self, nombre: str, sha: str) -> str:
		return self.c.texto(f"{ruta_repo(nombre)}/commits/{_q(sha)}", ACEPTAR_DIFF)

	def comparar(self, nombre: str, base: str, cabeza: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/compare/{_q(base)}...{_q(cabeza)}")

	def diff_comparacion(self, nombre: str, base: str, cabeza: str) -> str:
		return self.c.texto(f"{ruta_repo(nombre)}/compare/{_q(base)}...{_q(cabeza)}", ACEPTAR_DIFF)

	def estado_combinado(self, nombre: str, ref: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/commits/{_q(ref)}/status")

	def checks_de(self, nombre: str, ref: str) -> list:
		return (self.c.get(f"{ruta_repo(nombre)}/commits/{_q(ref)}/check-runs", {"per_page": 100}) or {}).get("check_runs", [])

	def anotaciones_check(self, nombre: str, id_check: int) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/check-runs/{int(id_check)}/annotations")

	def volver_a_pedir_check(self, nombre: str, id_check: int) -> None:
		self.c.post(f"{ruta_repo(nombre)}/check-runs/{int(id_check)}/rerequest")

	def crear_estado(self, nombre: str, sha: str, estado: str, contexto: str = "default", descripcion: str = "",
		url: str = "") -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/statuses/{_q(sha)}", _limpiar({
			"state": estado, "context": contexto, "description": descripcion or None, "target_url": url or None,
		}))

	def comentarios_commit(self, nombre: str, sha: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/commits/{_q(sha)}/comments")

	def comentar_commit(self, nombre: str, sha: str, texto: str, ruta: str = "", linea: int | None = None) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/commits/{_q(sha)}/comments",
			_limpiar({"body": texto, "path": ruta or None, "line": linea}))

	def prs_de_commit(self, nombre: str, sha: str) -> list:
		return self.c.get(f"{ruta_repo(nombre)}/commits/{_q(sha)}/pulls") or []


# ════════════════════════════════════════════════════════════════════════════
# Issues, comentarios, etiquetas, hitos, reacciones
# ════════════════════════════════════════════════════════════════════════════

REACCIONES = {
	"+1": N_("Me gusta"), "-1": N_("No me gusta"), "laugh": N_("Risa"), "confused": N_("Confusión"),
	"heart": N_("Corazón"), "hooray": N_("Celebración"), "rocket": N_("Cohete"), "eyes": N_("Ojos"),
}


class ApiIssues(_Base):
	def issues(self, nombre: str, numero: int = 1, estado: str = "open", etiquetas: str = "", asignado: str = "",
		creador: str = "", mencionado: str = "", hito: str = "", orden: str = "updated", direccion: str = "desc") -> Pagina:
		params = _limpiar({
			"state": estado, "labels": etiquetas or None, "assignee": asignado or None, "creator": creador or None,
			"mentioned": mencionado or None, "milestone": hito or None, "sort": orden, "direction": direccion,
		})
		return self.c.pagina(f"{ruta_repo(nombre)}/issues", params, numero, 100)

	def mis_issues(self, numero: int = 1, filtro: str = "assigned", estado: str = "open") -> Pagina:
		"""filtro: assigned, created, mentioned, subscribed, repos, all."""
		return self.c.pagina("/issues", {"filter": filtro, "state": estado, "sort": "updated"}, numero, 100)

	def issue(self, nombre: str, numero: int) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/issues/{int(numero)}")

	def crear_issue(self, nombre: str, titulo: str, cuerpo: str = "", etiquetas: list[str] | None = None,
		asignados: list[str] | None = None, hito: int | None = None, tipo: str = "") -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/issues", _limpiar({
			"title": titulo, "body": cuerpo, "labels": etiquetas, "assignees": asignados, "milestone": hito, "type": tipo or None,
		}))

	def editar_issue(self, nombre: str, numero: int, **campos: Any) -> dict:
		"""title, body, state (open/closed), state_reason (completed, not_planned, reopened),
		labels, assignees, milestone."""
		return self.c.patch(f"{ruta_repo(nombre)}/issues/{int(numero)}", campos)

	def cerrar_issue(self, nombre: str, numero: int, motivo: str = "completed") -> dict:
		return self.editar_issue(nombre, numero, state="closed", state_reason=motivo)

	def reabrir_issue(self, nombre: str, numero: int) -> dict:
		return self.editar_issue(nombre, numero, state="open", state_reason="reopened")

	def bloquear_issue(self, nombre: str, numero: int, motivo: str = "") -> None:
		self.c.put(f"{ruta_repo(nombre)}/issues/{int(numero)}/lock", _limpiar({"lock_reason": motivo or None}))

	def desbloquear_issue(self, nombre: str, numero: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/issues/{int(numero)}/lock")

	def comentarios(self, nombre: str, numero: int) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/issues/{int(numero)}/comments", maximo=3000)

	def comentar(self, nombre: str, numero: int, texto: str) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/issues/{int(numero)}/comments", {"body": texto})

	def editar_comentario(self, nombre: str, id_comentario: int, texto: str) -> dict:
		return self.c.patch(f"{ruta_repo(nombre)}/issues/comments/{int(id_comentario)}", {"body": texto})

	def borrar_comentario(self, nombre: str, id_comentario: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/issues/comments/{int(id_comentario)}")

	def cronologia(self, nombre: str, numero: int) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/issues/{int(numero)}/timeline", maximo=3000)

	def eventos_issue(self, nombre: str, numero: int) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/issues/{int(numero)}/events")

	def subissues(self, nombre: str, numero: int) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/issues/{int(numero)}/sub_issues")

	def anadir_subissue(self, nombre: str, numero: int, id_issue: int) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/issues/{int(numero)}/sub_issues", {"sub_issue_id": int(id_issue)})

	# Reacciones
	def reacciones_issue(self, nombre: str, numero: int) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/issues/{int(numero)}/reactions")

	def reaccionar_issue(self, nombre: str, numero: int, reaccion: str) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/issues/{int(numero)}/reactions", {"content": reaccion})

	def reaccionar_comentario(self, nombre: str, id_comentario: int, reaccion: str, de_revision: bool = False) -> dict:
		tipo = "pulls" if de_revision else "issues"
		return self.c.post(f"{ruta_repo(nombre)}/{tipo}/comments/{int(id_comentario)}/reactions", {"content": reaccion})

	def borrar_reaccion_issue(self, nombre: str, numero: int, id_reaccion: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/issues/{int(numero)}/reactions/{int(id_reaccion)}")

	# Asignados
	def asignables(self, nombre: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/assignees")

	def asignar(self, nombre: str, numero: int, logins: list[str]) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/issues/{int(numero)}/assignees", {"assignees": logins})

	def desasignar(self, nombre: str, numero: int, logins: list[str]) -> dict:
		return self.c.delete(f"{ruta_repo(nombre)}/issues/{int(numero)}/assignees", {"assignees": logins})

	# Etiquetas (labels)
	def etiquetas(self, nombre: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/labels")

	def crear_etiqueta(self, nombre: str, etiqueta: str, color: str = "ededed", descripcion: str = "") -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/labels", {"name": etiqueta, "color": color.lstrip("#"), "description": descripcion})

	def editar_etiqueta(self, nombre: str, etiqueta: str, nuevo: str = "", color: str = "", descripcion: str | None = None) -> dict:
		return self.c.patch(f"{ruta_repo(nombre)}/labels/{_q(etiqueta)}", _limpiar({
			"new_name": nuevo or None, "color": color.lstrip("#") or None, "description": descripcion,
		}))

	def borrar_etiqueta(self, nombre: str, etiqueta: str) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/labels/{_q(etiqueta)}")

	def poner_etiquetas(self, nombre: str, numero: int, etiquetas: list[str]) -> list:
		return self.c.put(f"{ruta_repo(nombre)}/issues/{int(numero)}/labels", {"labels": etiquetas})

	# Hitos
	def hitos(self, nombre: str, estado: str = "open") -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/milestones", {"state": estado, "sort": "due_on"})

	def crear_hito(self, nombre: str, titulo: str, descripcion: str = "", fecha: str = "") -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/milestones", _limpiar({"title": titulo, "description": descripcion,
			"due_on": fecha or None}))

	def editar_hito(self, nombre: str, numero: int, **campos: Any) -> dict:
		return self.c.patch(f"{ruta_repo(nombre)}/milestones/{int(numero)}", _limpiar(campos))

	def borrar_hito(self, nombre: str, numero: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/milestones/{int(numero)}")

	# Plantillas de issue
	def crear_issue_con_plantilla(self, nombre: str, titulo: str, cuerpo: str = "", etiquetas: list[str] | None = None,
		asignados: list[str] | None = None, tipo: str = "") -> tuple[dict, list[str]]:
		"""Crea una issue con las etiquetas, asignados y tipo de una plantilla.

		Quien no tiene permiso de clasificación en el repositorio no puede poner
		etiquetas ni asignados: GitHub a veces los ignora sin decir nada y otras
		rechaza la issue entera (422, o 403 con el tipo). En ese caso se crea sin
		ellos, para no perder lo escrito.

		:return: ``(issue, descartados)``; ``descartados`` dice qué no se aplicó
			(``"etiquetas"``, ``"asignados"``, ``"tipo"``).
		"""
		pedidos = [(clave, valor) for clave, valor in (("etiquetas", etiquetas), ("asignados", asignados), ("tipo", tipo)) if valor]
		try:
			issue = self.crear_issue(nombre, titulo, cuerpo, etiquetas or None, asignados or None, tipo=tipo)
		except (ErrorValidacion, SinPermiso):
			if not pedidos:
				raise
			return self.crear_issue(nombre, titulo, cuerpo), [clave for clave, _v in pedidos]
		issue = issue if isinstance(issue, dict) else {}
		puestas = {str(e.get("name", "")).lower() for e in issue.get("labels") or [] if isinstance(e, dict)}
		puestos = {str(u.get("login", "")).lower() for u in issue.get("assignees") or [] if isinstance(u, dict)}
		descartados = []
		if etiquetas and any(e.lower() not in puestas for e in etiquetas):
			descartados.append("etiquetas")
		if asignados and any(a.lower() not in puestos for a in asignados):
			descartados.append("asignados")
		if tipo and not issue.get("type"):
			descartados.append("tipo")
		return issue, descartados

	def plantillas_issue(self, nombre: str) -> list[dict]:
		"""Plantillas y formularios de .github/ISSUE_TEMPLATE (sin su config.yml)."""
		try:
			lista = self.c.get(f"{ruta_repo(nombre)}/contents/.github/ISSUE_TEMPLATE")
		except Exception:  # noqa: BLE001 - sin plantillas: lista vacía
			return []
		resultado = []
		for elemento in lista if isinstance(lista, list) else []:
			archivo = elemento.get("name", "").lower()
			if elemento.get("type") == "file" and archivo.endswith((".md", ".yml", ".yaml")) and archivo not in (
				"config.yml", "config.yaml"):
				resultado.append(elemento)
		return resultado

	def leer_plantillas_issue(self, nombre: str) -> tuple[list[tuple[str, str]], str]:
		"""Textos de las plantillas de .github/ISSUE_TEMPLATE y de su config.yml, en una sola llamada.

		:return: ``([(archivo, texto), …], texto_de_config)``; sin carpeta, ``([], "")``.
			Una plantilla que ha desaparecido entre el listado y la lectura se omite.
		"""
		try:
			lista = self.c.get(f"{ruta_repo(nombre)}/contents/.github/ISSUE_TEMPLATE")
		except NoEncontrado:
			return [], ""
		plantillas: list[tuple[str, str]] = []
		config = ""
		for elemento in lista if isinstance(lista, list) else []:
			archivo = elemento.get("name", "")
			if elemento.get("type") != "file" or not archivo.lower().endswith((".md", ".yml", ".yaml")):
				continue
			try:
				bruto, _sha = self.leer_archivo(nombre, elemento.get("path") or f".github/ISSUE_TEMPLATE/{archivo}")
			except NoEncontrado:
				continue
			texto = bruto.decode("utf-8", errors="replace")
			if archivo.lower() in ("config.yml", "config.yaml"):
				config = texto
			else:
				plantillas.append((archivo, texto))
		return plantillas, config


# ════════════════════════════════════════════════════════════════════════════
# Pull requests y revisiones
# ════════════════════════════════════════════════════════════════════════════


class ApiPulls(_Base):
	def prs(self, nombre: str, numero: int = 1, estado: str = "open", base: str = "", cabeza: str = "",
		orden: str = "updated", direccion: str = "desc") -> Pagina:
		params = _limpiar({"state": estado, "base": base or None, "head": cabeza or None, "sort": orden, "direction": direccion})
		return self.c.pagina(f"{ruta_repo(nombre)}/pulls", params, numero, 100)

	def pr(self, nombre: str, numero: int) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/pulls/{int(numero)}")

	def crear_pr(self, nombre: str, titulo: str, cabeza: str, base: str, cuerpo: str = "", borrador: bool = False,
		editable_por_mantenedores: bool = True) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/pulls", {
			"title": titulo, "head": cabeza, "base": base, "body": cuerpo, "draft": borrador,
			"maintainer_can_modify": editable_por_mantenedores,
		})

	def plantillas_pr(self, nombre: str) -> list[tuple[str, str]]:
		"""Plantillas de pull request: ``[(ruta, texto), …]`` en el orden en que las busca GitHub.

		GitHub admite ``pull_request_template.md`` (sin distinguir mayúsculas) en
		``.github/``, en la raíz o en ``docs/``, y varias plantillas dentro de una
		carpeta ``PULL_REQUEST_TEMPLATE/`` en esos mismos sitios. Se lista cada
		carpeta una vez (en lugar de probar cada nombre) para no gastar peticiones.
		"""
		resultado: list[tuple[str, str]] = []
		for carpeta in (".github", "", "docs"):
			try:
				lista = self.contenido(nombre, carpeta)
			except NoEncontrado:
				continue
			for elemento in lista if isinstance(lista, list) else []:
				archivo = str(elemento.get("name", "")).lower()
				ruta = elemento.get("path") or "/".join(p for p in (carpeta, elemento.get("name", "")) if p)
				if elemento.get("type") == "file" and archivo in ("pull_request_template.md", "pull_request_template.txt"):
					resultado.append((ruta, self._texto_plantilla(nombre, ruta)))
				elif elemento.get("type") == "dir" and archivo == "pull_request_template":
					try:
						varias = self.contenido(nombre, ruta)
					except NoEncontrado:
						continue
					for plantilla in varias if isinstance(varias, list) else []:
						if plantilla.get("type") == "file" and str(plantilla.get("name", "")).lower().endswith((".md", ".txt")):
							ruta_plantilla = plantilla.get("path") or f"{ruta}/{plantilla.get('name', '')}"
							resultado.append((ruta_plantilla, self._texto_plantilla(nombre, ruta_plantilla)))
		return [(ruta, texto) for ruta, texto in resultado if texto is not None]

	def _texto_plantilla(self, nombre: str, ruta: str) -> str | None:
		"""Texto de una plantilla, o ``None`` si ha desaparecido entre el listado y la lectura."""
		try:
			bruto, _sha = self.leer_archivo(nombre, ruta)
		except NoEncontrado:
			return None
		return bruto.decode("utf-8", errors="replace")

	def editar_pr(self, nombre: str, numero: int, **campos: Any) -> dict:
		"""title, body, state, base, maintainer_can_modify."""
		return self.c.patch(f"{ruta_repo(nombre)}/pulls/{int(numero)}", _limpiar(campos))

	def archivos_pr(self, nombre: str, numero: int) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/pulls/{int(numero)}/files", maximo=3000)

	def commits_pr(self, nombre: str, numero: int) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/pulls/{int(numero)}/commits", maximo=250)

	def diff_pr(self, nombre: str, numero: int) -> str:
		return self.c.texto(f"{ruta_repo(nombre)}/pulls/{int(numero)}", ACEPTAR_DIFF)

	def esta_fusionado(self, nombre: str, numero: int) -> bool:
		return self.c.existe(f"{ruta_repo(nombre)}/pulls/{int(numero)}/merge")

	def fusionar_pr(self, nombre: str, numero: int, metodo: str = "merge", titulo: str = "", mensaje: str = "",
		sha: str = "") -> dict:
		"""metodo: merge, squash o rebase."""
		return self.c.put(f"{ruta_repo(nombre)}/pulls/{int(numero)}/merge", _limpiar({
			"merge_method": metodo, "commit_title": titulo or None, "commit_message": mensaje or None, "sha": sha or None,
		}))

	def actualizar_rama_pr(self, nombre: str, numero: int) -> dict:
		return self.c.put(f"{ruta_repo(nombre)}/pulls/{int(numero)}/update-branch")

	# Revisores
	def pedir_revision(self, nombre: str, numero: int, revisores: list[str], equipos: list[str] | None = None) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/pulls/{int(numero)}/requested_reviewers",
			{"reviewers": revisores, "team_reviewers": equipos or []})

	def quitar_revision(self, nombre: str, numero: int, revisores: list[str]) -> dict:
		return self.c.delete(f"{ruta_repo(nombre)}/pulls/{int(numero)}/requested_reviewers", {"reviewers": revisores})

	def revisores_pedidos(self, nombre: str, numero: int) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/pulls/{int(numero)}/requested_reviewers")

	# Revisiones
	def revisiones(self, nombre: str, numero: int) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/pulls/{int(numero)}/reviews")

	def crear_revision(self, nombre: str, numero: int, evento: str, cuerpo: str = "", comentarios: list[dict] | None = None,
		sha: str = "") -> dict:
		"""evento: APPROVE, REQUEST_CHANGES, COMMENT o «» (pendiente).

		``comentarios``: ``[{"path", "line", "side", "body"}]`` (o ``start_line`` para varias líneas).
		"""
		datos = _limpiar({"body": cuerpo or None, "event": evento or None, "comments": comentarios or None,
			"commit_id": sha or None})
		return self.c.post(f"{ruta_repo(nombre)}/pulls/{int(numero)}/reviews", datos)

	def enviar_revision(self, nombre: str, numero: int, id_revision: int, evento: str, cuerpo: str = "") -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/pulls/{int(numero)}/reviews/{int(id_revision)}/events",
			{"event": evento, "body": cuerpo})

	def descartar_revision(self, nombre: str, numero: int, id_revision: int, mensaje: str) -> dict:
		return self.c.put(f"{ruta_repo(nombre)}/pulls/{int(numero)}/reviews/{int(id_revision)}/dismissals",
			{"message": mensaje, "event": "DISMISS"})

	def borrar_revision_pendiente(self, nombre: str, numero: int, id_revision: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/pulls/{int(numero)}/reviews/{int(id_revision)}")

	def comentarios_revision(self, nombre: str, numero: int) -> list:
		"""Comentarios en línea de todas las revisiones del PR."""
		return self.c.todos(f"{ruta_repo(nombre)}/pulls/{int(numero)}/comments", maximo=3000)

	def comentar_linea(self, nombre: str, numero: int, sha: str, ruta: str, linea: int, texto: str, lado: str = "RIGHT",
		linea_inicial: int | None = None) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/pulls/{int(numero)}/comments", _limpiar({
			"body": texto, "commit_id": sha, "path": ruta, "line": int(linea), "side": lado,
			"start_line": linea_inicial, "start_side": lado if linea_inicial else None,
		}))

	def comentar_archivo(self, nombre: str, numero: int, sha: str, ruta: str, texto: str) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/pulls/{int(numero)}/comments",
			{"body": texto, "commit_id": sha, "path": ruta, "subject_type": "file"})

	def responder_comentario_revision(self, nombre: str, numero: int, id_comentario: int, texto: str) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/pulls/{int(numero)}/comments/{int(id_comentario)}/replies", {"body": texto})

	def editar_comentario_revision(self, nombre: str, id_comentario: int, texto: str) -> dict:
		return self.c.patch(f"{ruta_repo(nombre)}/pulls/comments/{int(id_comentario)}", {"body": texto})

	def borrar_comentario_revision(self, nombre: str, id_comentario: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/pulls/comments/{int(id_comentario)}")


# ════════════════════════════════════════════════════════════════════════════
# Releases
# ════════════════════════════════════════════════════════════════════════════


class ApiReleases(_Base):
	def releases(self, nombre: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"{ruta_repo(nombre)}/releases", numero=numero, por_pagina=100)

	def release(self, nombre: str, id_release: int) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/releases/{int(id_release)}")

	def ultima_release(self, nombre: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/releases/latest")

	def release_por_etiqueta(self, nombre: str, etiqueta: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/releases/tags/{_q(etiqueta)}")

	def crear_release(self, nombre: str, etiqueta: str, titulo: str = "", cuerpo: str = "", rama: str = "",
		borrador: bool = False, prelanzamiento: bool = False, generar_notas: bool = False, ultima: str = "true") -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/releases", _limpiar({
			"tag_name": etiqueta, "name": titulo or etiqueta, "body": cuerpo, "target_commitish": rama or None,
			"draft": borrador, "prerelease": prelanzamiento, "generate_release_notes": generar_notas, "make_latest": ultima,
		}))

	def editar_release(self, nombre: str, id_release: int, **campos: Any) -> dict:
		return self.c.patch(f"{ruta_repo(nombre)}/releases/{int(id_release)}", _limpiar(campos))

	def borrar_release(self, nombre: str, id_release: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/releases/{int(id_release)}")

	def generar_notas(self, nombre: str, etiqueta: str, anterior: str = "", rama: str = "") -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/releases/generate-notes", _limpiar({
			"tag_name": etiqueta, "previous_tag_name": anterior or None, "target_commitish": rama or None,
		}))

	def recursos(self, nombre: str, id_release: int) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/releases/{int(id_release)}/assets")

	def borrar_recurso(self, nombre: str, id_recurso: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/releases/assets/{int(id_recurso)}")

	def editar_recurso(self, nombre: str, id_recurso: int, nombre_archivo: str = "", etiqueta: str = "") -> dict:
		return self.c.patch(f"{ruta_repo(nombre)}/releases/assets/{int(id_recurso)}",
			_limpiar({"name": nombre_archivo or None, "label": etiqueta or None}))

	def url_descarga_recurso(self, nombre: str, id_recurso: int) -> str:
		return self.c.url(f"{ruta_repo(nombre)}/releases/assets/{int(id_recurso)}")
