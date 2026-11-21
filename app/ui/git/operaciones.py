"""Ayudas sin wx para las ventanas de git: textos, URL y órdenes que faltan en ``git_local``.

Todo lo de aquí se puede probar sin ventanas. Las órdenes git que no tiene
``RepositorioLocal`` se lanzan con ``repo.git(...)`` y quedan anotadas:

- ``continuar_operacion``: ``git rebase --continue`` (y ``merge --continue``)
  abren el editor para el mensaje y el ``GIT_EDITOR`` de ``git_local``
  («cmd /c exit 0») falla en Git for Windows (sh convierte «/c» en una ruta).
  Por eso primero se confirma con ``git commit --no-edit`` (usa MERGE_MSG) y
  después se continúa: así nunca se abre un editor.
- ``abortar_operacion``: ``cherry-pick --abort``, ``revert --abort``, ``bisect reset``.
- ``quitar_todo_de_preparados`` y ``quitar_de_preparados``: sin commits todavía,
  ``git restore --staged`` falla; se usa ``git rm --cached``.
- ``establecer_seguimiento``: ``git branch --set-upstream-to``.
- Configuración local del repositorio: ``git config --local`` y ``--unset``.
"""

from __future__ import annotations

import builtins
import logging
import re
from pathlib import Path

from app.services import git_local

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ════════════════════════════════════════════════════════════════════════════
# Textos y URL (puras)
# ════════════════════════════════════════════════════════════════════════════

_NOMBRE_CORTO = re.compile(r"^([\w.-]+)/([\w.-]+?)(?:\.git)?$")


def es_ruta_local(texto: str) -> bool:
	"""Una carpeta del disco o ``file://`` (se clona tal cual)."""
	texto = texto.strip()
	return bool(re.match(r"^[a-zA-Z]:[\\/]", texto) or texto.startswith(("\\\\", "file://", "/", "./", "../")))


def normalizar_url(texto: str, protocolo: str = "https", host: str = "github.com") -> str:
	"""«dueño/repo» o una URL de GitHub → URL para clonar con el protocolo elegido.

	:param protocolo: «https» o «ssh».
	"""
	texto = texto.strip()
	if not texto or es_ruta_local(texto):
		return texto
	nombre = nombre_github(texto, host) if "://" in texto or texto.startswith("git@") else ""
	if not nombre:
		corto = _NOMBRE_CORTO.match(texto)
		if not corto:
			return texto
		nombre = f"{corto.group(1)}/{corto.group(2)}"
	if protocolo.lower() == "ssh":
		return f"git@{host}:{nombre}.git"
	return f"https://{host}/{nombre}.git"


def nombre_github(url: str, host: str = "github.com") -> str:
	"""«dueño/repo» si ``url`` es de ``host`` (HTTPS, SSH o ssh://); «» si no."""
	url = url.strip()
	patrones = (
		rf"^https?://(?:[^@/]+@)?{re.escape(host)}/([^/]+)/([^/]+?)(?:\.git)?/?$",
		rf"^(?:ssh://)?git@{re.escape(host)}[:/]([^/]+)/([^/]+?)(?:\.git)?/?$",
	)
	for patron in patrones:
		coincidencia = re.match(patron, url, re.I)
		if coincidencia:
			return f"{coincidencia.group(1)}/{coincidencia.group(2)}"
	return ""


def nombre_carpeta(url: str) -> str:
	"""Nombre de carpeta que usaría ``git clone`` para ``url``."""
	limpio = url.strip().rstrip("/\\")
	limpio = re.sub(r"\.git$", "", limpio)
	return re.split(r"[/\\:]", limpio)[-1] if limpio else ""


def describir_seguimiento(texto: str) -> str:
	"""``%(upstream:track)`` («[ahead 2, behind 1]», «[gone]») en español."""
	texto = texto.strip().strip("[]")
	if not texto:
		return ""
	if texto == "gone":
		return _("la rama remota ya no existe")
	partes = []
	adelante = re.search(r"ahead (\d+)", texto)
	atras = re.search(r"behind (\d+)", texto)
	if adelante:
		partes.append(_("{n} por delante").format(n=adelante.group(1)))
	if atras:
		partes.append(_("{n} por detrás").format(n=atras.group(1)))
	return ", ".join(partes) or texto


def describir_commit_creado(salida: str) -> str:
	"""«[main abc1234] Mensaje» → «Commit abc1234 creado en main: Mensaje.»"""
	for linea in salida.splitlines():
		coincidencia = re.match(r"^\[(.+?)(?: \(root-commit\))? ([0-9a-f]{4,})\] (.*)$", linea.strip())
		if coincidencia:
			rama, sha, asunto = coincidencia.groups()
			return _("Commit {s} creado en {r}: {a}.").format(s=sha, r=rama, a=asunto)
	return _("Commit creado.")


def linea_gitignore(ruta: str, modo: str = "archivo") -> str:
	"""Línea para ``.gitignore``: «archivo» (/ruta), «extension» (*.ext) o «carpeta» (/carpeta/)."""
	ruta = ruta.replace("\\", "/").strip("/")
	if modo == "extension":
		sufijo = Path(ruta).suffix
		return f"*{sufijo}" if sufijo else "/" + ruta
	if modo == "carpeta":
		carpeta = ruta.rsplit("/", 1)[0] if "/" in ruta else ""
		return f"/{carpeta}/" if carpeta else "/" + ruta
	return "/" + ruta


def anadir_a_gitignore(raiz: Path, linea: str) -> bool:
	"""Añade ``linea`` al ``.gitignore`` de la raíz si no estaba. Devuelve si la añadió."""
	archivo = Path(raiz) / ".gitignore"
	actual = archivo.read_text(encoding="utf-8", errors="replace") if archivo.exists() else ""
	if linea in [l.strip() for l in actual.splitlines()]:
		return False
	separador = "" if not actual or actual.endswith("\n") else "\n"
	with open(archivo, "a", encoding="utf-8", newline="") as salida:
		salida.write(f"{separador}{linea}\n")
	return True


def preparado_texto(archivo: git_local.ArchivoEstado) -> str:
	"""Columna «Preparado»: sí, no, en parte o en conflicto."""
	if archivo.conflicto:
		return _("en conflicto")
	if archivo.preparado and archivo.arbol != ".":
		return _("en parte")
	return _("sí") if archivo.preparado else _("no")


def analizar_submodulo(linea: str) -> dict:
	"""Línea de ``git submodule status``: estado, sha, ruta y descripción."""
	estados = {"-": _("sin inicializar"), "+": _("en otro commit"), "U": _("en conflicto"), " ": _("al día")}
	marca = linea[:1] if linea[:1] in estados else " "
	resto = linea[1:].strip() if marca != " " or linea.startswith(" ") else linea.strip()
	partes = resto.split(" ", 2)
	return {
		"estado": estados[marca], "sha": partes[0][:10] if partes else "",
		"ruta": partes[1] if len(partes) > 1 else "", "descripcion": partes[2].strip("()") if len(partes) > 2 else "",
	}


def analizar_worktree(linea: str) -> dict:
	"""Línea de ``git worktree list``: carpeta, sha y rama."""
	coincidencia = re.match(r"^(.*?)\s+([0-9a-f]{4,}|\(bare\))\s*(?:\[(.*)\])?(.*)$", linea.strip())
	if not coincidencia:
		return {"carpeta": linea.strip(), "sha": "", "rama": ""}
	carpeta, sha, rama, extra = coincidencia.groups()
	return {"carpeta": carpeta.strip(), "sha": sha, "rama": rama or extra.strip() or _("(sin rama)")}


def analizar_reflog(linea: str) -> dict:
	"""Línea de ``reflog --format=%h %gd %gs``."""
	partes = linea.split(" ", 2)
	return {"sha": partes[0], "referencia": partes[1] if len(partes) > 1 else "", "descripcion": partes[2] if len(partes) > 2 else ""}


def agrupar_remotos(filas: list[tuple[str, str, str]]) -> list[dict]:
	"""(nombre, url, tipo) de ``remote -v`` → un elemento por remoto con su URL de traer y de enviar."""
	por_nombre: dict[str, dict] = {}
	for nombre, url, tipo in filas:
		remoto = por_nombre.setdefault(nombre, {"nombre": nombre, "traer": "", "enviar": ""})
		remoto["traer" if tipo == "fetch" else "enviar"] = url
	return list(por_nombre.values())


# ════════════════════════════════════════════════════════════════════════════
# Órdenes git que faltan en git_local (se ejecutan en segundo plano)
# ════════════════════════════════════════════════════════════════════════════


def hay_preparados(repo: git_local.RepositorioLocal) -> bool:
	return bool(repo.git("diff", "--cached", "--name-only").strip())


def continuar_operacion(repo: git_local.RepositorioLocal, operacion: str) -> str:
	"""Continúa la fusión, reorganización, cherry-pick o reversión en curso sin abrir ningún editor."""
	conflictos = repo.estado().conflictos
	if conflictos:
		raise git_local.ErrorGit(_("Quedan {n} archivos en conflicto. Resuélvalos y márquelos como resueltos antes de continuar.").format(
			n=len(conflictos)))
	salida = ""
	if operacion == _("fusión"):
		return repo.git("commit", "--no-edit", analizable=False)
	if operacion == _("reorganización"):
		if hay_preparados(repo):
			salida = repo.git("commit", "--no-edit", analizable=False)
		return salida + repo.continuar_reorganizacion()
	if operacion in (_("cherry-pick"), _("reversión")):
		orden = "cherry-pick" if operacion == _("cherry-pick") else "revert"
		if hay_preparados(repo):
			salida = repo.git("commit", "--no-edit", analizable=False)
		if repo.operacion_en_curso() == operacion:
			salida += repo.git(orden, "--continue", analizable=False)
		return salida
	raise git_local.ErrorGit(_("No hay ninguna operación que continuar."))


def abortar_operacion(repo: git_local.RepositorioLocal, operacion: str) -> None:
	if operacion == _("fusión"):
		repo.abortar_fusion()
	elif operacion == _("reorganización"):
		repo.abortar_reorganizacion()
	elif operacion == _("cherry-pick"):
		repo.git("cherry-pick", "--abort")
	elif operacion == _("reversión"):
		repo.git("revert", "--abort")
	elif operacion == _("bisección"):
		repo.bisecar("reset")
	else:
		raise git_local.ErrorGit(_("No hay ninguna operación que abortar."))


def quitar_de_preparados(repo: git_local.RepositorioLocal, rutas: list[str]) -> None:
	try:
		repo.quitar_de_preparados(rutas)
	except git_local.ErrorGit:
		# Sin ningún commit todavía no hay HEAD con el que restaurar el índice.
		log.debug("restore --staged falló; se usa rm --cached", exc_info=True)
		repo.git("rm", "--cached", "-q", "--", *rutas)


def quitar_todo_de_preparados(repo: git_local.RepositorioLocal) -> None:
	try:
		repo.git("restore", "--staged", "--", ":/")
	except git_local.ErrorGit:
		log.debug("restore --staged :/ falló; se usa rm --cached", exc_info=True)
		repo.git("rm", "--cached", "-r", "-q", "--", ":/")


def establecer_seguimiento(repo: git_local.RepositorioLocal, remota: str, rama: str = "") -> None:
	repo.git("branch", f"--set-upstream-to={remota}", *([rama] if rama else []))


def config_local(repo: git_local.RepositorioLocal, clave: str) -> str:
	return repo.git("config", "--local", "--get", clave, aceptar_codigos=(0, 1)).strip()


def establecer_config_local(repo: git_local.RepositorioLocal, clave: str, valor: str) -> None:
	"""Valor vacío = quitar la clave del repositorio (vuelve a mandar la global)."""
	if valor:
		repo.git("config", "--local", clave, valor)
	else:
		repo.git("config", "--local", "--unset", clave, aceptar_codigos=(0, 5))


def quitar_config_global(clave: str) -> None:
	git_local.ejecutar(["config", "--global", "--unset", clave], tiempo=15, aceptar_codigos=(0, 5))


def empezar_biseccion(repo: git_local.RepositorioLocal, malo: str, bueno: str) -> str:
	return repo.git("bisect", "start", malo, bueno, analizable=False)
