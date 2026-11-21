"""Discusiones (GitHub Discussions): ventana de una discusión con sus comentarios y respuestas.

- «Información»: título, categoría, autor, fecha, estado, si tiene respuesta
  marcada, votos y enlace.
- «Comentarios y respuestas»: la publicación original, cada comentario y,
  justo debajo, sus respuestas (columna «Tipo»: «Comentario», «Comentario,
  respuesta marcada», «Respuesta a …»). El texto completo del elemento
  enfocado aparece en «Texto del elemento elegido».
- Comentar (Ctrl+N), responder a un comentario (Ctrl+R), marcar o desmarcar
  como respuesta (Ctrl+M), votar (Ctrl+U), cerrar con motivo, reabrir, ver la
  discusión formateada (F7), abrir en el navegador (Ctrl+B).
"""

from __future__ import annotations

import builtins
import logging
import webbrowser
from typing import Any

import wx

from app.services import formato as f
from app.ui.comunes import copiar, elegir_uno
from app.ui.detalle.comun_detalle import VentanaDetalle, entrada_cerrar
from app.ui.editor import editar

log = logging.getLogger(__name__)

MOTIVOS_CIERRE = [("RESOLVED", "Resuelta"), ("OUTDATED", "Obsoleta"), ("DUPLICATE", "Duplicada")]


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _autor(nodo: dict) -> str:
	return (nodo.get("author") or {}).get("login") or _("(cuenta borrada)")


def elementos_discusion(discusion: dict) -> list[dict]:
	"""Publicación original, comentarios y, tras cada uno, sus respuestas (en ese orden).

	Cada elemento: ``{"tipo": "original" | "comentario" | "respuesta", "nodo": ..., "padre": comentario o None}``.
	"""
	elementos = [{"tipo": "original", "nodo": discusion, "padre": None}]
	for comentario in ((discusion.get("comments") or {}).get("nodes") or []):
		if not comentario:
			continue
		elementos.append({"tipo": "comentario", "nodo": comentario, "padre": None})
		for respuesta in ((comentario.get("replies") or {}).get("nodes") or []):
			if respuesta:
				elementos.append({"tipo": "respuesta", "nodo": respuesta, "padre": comentario})
	return elementos


def tipo_elemento(elemento: dict) -> str:
	if elemento["tipo"] == "original":
		return _("Publicación original")
	if elemento["tipo"] == "respuesta":
		return _("Respuesta a {a}").format(a=_autor(elemento["padre"] or {}))
	return _("Comentario, respuesta marcada") if elemento["nodo"].get("isAnswer") else _("Comentario")


def fila_elemento(elemento: dict, relativas: bool = True) -> list[str]:
	nodo = elemento["nodo"]
	votos = nodo.get("upvoteCount")
	return [_autor(nodo), tipo_elemento(elemento), f.fecha(nodo.get("createdAt"), relativas),
		"" if votos is None else str(votos), f.primera_linea(nodo.get("body"))]


def texto_informacion(discusion: dict) -> str:
	estado = _("Cerrada") if discusion.get("closed") else _("Abierta")
	if discusion.get("locked"):
		estado += _(", bloqueada")
	comentarios = (discusion.get("comments") or {}).get("nodes") or []
	lineas = [
		_("Discusión #{n}: {t}").format(n=discusion.get("number", ""), t=discusion.get("title", "")),
		_("Categoría: {c}").format(c=(discusion.get("category") or {}).get("name") or "-"),
		_("Autor: {a}").format(a=_autor(discusion)),
		_("Creada: {c}").format(c=f.fecha_completa(discusion.get("createdAt"))),
		_("Estado: {e}").format(e=estado),
		_("Respuesta marcada: {r}").format(r=f.si_no(discusion.get("isAnswered") or discusion.get("answer"))),
		_("Votos: {v}").format(v=discusion.get("upvoteCount", 0)),
		_("Comentarios: {c}").format(c=len(comentarios)),
		_("Enlace: {u}").format(u=discusion.get("url") or ""),
	]
	return "\n".join(lineas)


def texto_elemento(elemento: dict) -> str:
	nodo = elemento["nodo"]
	cabecera = _("{t} de {a}, {f}").format(t=tipo_elemento(elemento), a=_autor(nodo), f=f.fecha_completa(nodo.get("createdAt")))
	return cabecera + "\n\n" + (nodo.get("body") or _("(sin texto)"))


def markdown_discusion(discusion: dict) -> str:
	"""Toda la discusión en Markdown con encabezados (navegables con H en el modo exploración)."""
	partes = [f"# {discusion.get('title', '')}", "", texto_informacion(discusion).replace("\n", "  \n"), "",
		discusion.get("body") or ""]
	for elemento in elementos_discusion(discusion)[1:]:
		nodo = elemento["nodo"]
		nivel = "##" if elemento["tipo"] == "comentario" else "###"
		partes += ["", f"{nivel} {tipo_elemento(elemento)}: {_autor(nodo)}, {f.fecha_completa(nodo.get('createdAt'))}", "",
			nodo.get("body") or ""]
	return "\n".join(partes)


class VentanaDiscusion(VentanaDetalle):
	def __init__(self, ctx: Any, padre: wx.Window | None, nombre: str, numero: int) -> None:
		super().__init__(padre, ctx, _("Discusión #{n} de {r}").format(n=numero, r=nombre), clave=f"discusion:{nombre}:{int(numero)}",
			tamano=(1000, 720))
		self.nombre = nombre
		self.numero = int(numero)
		self.discusion: dict = {}
		self.elementos: list[dict] = []
		self._construir()

	def _construir(self) -> None:
		self.info = self.crear_texto(_("&Información:"), alto=120)
		self.lista = self.crear_lista(_("&Comentarios y respuestas:"), _("Comentarios y respuestas"),
			[(_("Autor"), 130), (_("Tipo"), 190), (_("Fecha"), 120), (_("Votos"), 60), (_("Texto"), 420)],
			ayuda=_("Las respuestas van justo debajo de su comentario. Control+R responde; Control+M marca como respuesta."))
		self.texto = self.crear_texto(_("&Texto del elemento elegido:"), alto=220, proporcion=1)
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda e: (e.Skip(), self._mostrar_texto()))
		self.teclas_de_lista(self.lista, {}, al_activar=lambda: self.texto.SetFocus())
		self.menu_contextual(self.lista, lambda: [
			(_("&Responder…\tCtrl+R"), self.responder),
			(_("&Marcar o desmarcar como respuesta\tCtrl+M"), self.marcar_respuesta),
			(_("&Votar o quitar el voto\tCtrl+U"), self.votar),
			(_("&Copiar el texto"), self.copiar_texto),
		])
		self.poner_menus([(_("&Discusión"), [
			(_("Nuevo c&omentario…\tCtrl+N"), self.comentar),
			(_("&Responder a este comentario…\tCtrl+R"), self.responder),
			(_("&Marcar o desmarcar como respuesta\tCtrl+M"), self.marcar_respuesta),
			(_("Vo&tar o quitar el voto\tCtrl+U"), self.votar),
			None,
			(_("&Cerrar la discusión…"), self.cerrar_discusion),
			(_("Reabrir la &discusión"), self.reabrir),
			None,
			(_("Ver formateada en &HTML\tF7"), self.ver_html),
			(_("Abrir en el &navegador\tCtrl+B"), self.abrir_navegador),
			(_("Co&piar el enlace\tCtrl+Shift+C"), self.copiar_enlace),
			(_("&Actualizar\tF5"), lambda: self.cargar()),
			entrada_cerrar(self, _("Cerrar la &ventana\tCtrl+W")),
		])])

	# ── Datos ─────────────────────────────────────────────────────────────────

	def cargar(self, anunciar: bool = True, enfocar_id: str | None = None) -> None:
		api = self.ctx.api()
		actual = enfocar_id or ((self.elemento or {}).get("nodo") or {}).get("id")

		def listo(discusion: dict) -> None:
			self.poner_discusion(discusion, actual)
			if anunciar:
				self.ctx.sonar("listo")

		self.en_fondo(lambda: api.discusion(self.nombre, self.numero), al_terminar=listo, sonido="")

	def poner_discusion(self, discusion: dict, enfocar_id: str | None = None) -> None:
		self.discusion = dict(discusion or {})
		self.elementos = elementos_discusion(self.discusion) if self.discusion else []
		self.info.SetValue(texto_informacion(self.discusion))
		self.SetTitle(_("Discusión #{n}: {t}").format(n=self.numero, t=self.discusion.get("title", "")))
		self.lista.reemplazar_filas([fila_elemento(e, self.ctx.relativas()) for e in self.elementos], conservar_foco=True)
		ids = [e["nodo"].get("id") for e in self.elementos]
		if enfocar_id in ids:
			self.lista.enfocar_fila(ids.index(enfocar_id), anunciar=False)
		elif self.elementos and self.lista.fila_actual() == wx.NOT_FOUND:
			self.lista.enfocar_fila(0, anunciar=False)
		self._mostrar_texto()
		comentarios = sum(1 for e in self.elementos if e["tipo"] == "comentario")
		respuestas = sum(1 for e in self.elementos if e["tipo"] == "respuesta")
		self.estado(_("{c} comentarios y {r} respuestas.").format(c=comentarios, r=respuestas))

	@property
	def elemento(self) -> dict | None:
		fila = self.lista.fila_actual() if hasattr(self, "lista") else wx.NOT_FOUND
		return self.elementos[fila] if 0 <= fila < len(self.elementos) else None

	def _mostrar_texto(self) -> None:
		elemento = self.elemento
		self.texto.SetValue(texto_elemento(elemento) if elemento else "")
		self.texto.SetInsertionPoint(0)

	# ── Acciones ──────────────────────────────────────────────────────────────

	def comentar(self) -> None:
		api = self.ctx.api()
		resultado = editar(self, self.ctx, _("Comentar la discusión"),
			lambda valores: api.comentar_discusion(self.discusion["id"], valores["cuerpo"]),
			etiqueta_cuerpo=_("Te&xto del comentario (Markdown):"))
		if resultado is not None and self.viva():
			self.cargar(anunciar=False, enfocar_id=(resultado or {}).get("id"))

	def responder(self) -> None:
		elemento = self.elemento
		if elemento is None or elemento["tipo"] == "original":
			self.ctx.avisar(_("Elija un comentario para responderle. Para escribir en la discusión use Nuevo comentario (Control+N)."))
			return
		comentario = elemento["padre"] if elemento["tipo"] == "respuesta" else elemento["nodo"]
		api = self.ctx.api()
		cita = _("{a} escribió:").format(a=_autor(comentario)) + "\n" + (comentario.get("body") or "")
		resultado = editar(self, self.ctx, _("Responder a {a}").format(a=_autor(comentario)),
			lambda valores: api.comentar_discusion(self.discusion["id"], valores["cuerpo"], responde_a=comentario["id"]),
			etiqueta_cuerpo=_("Te&xto de la respuesta (Markdown):"), texto_contexto=cita)
		if resultado is not None and self.viva():
			self.cargar(anunciar=False, enfocar_id=(resultado or {}).get("id"))

	def marcar_respuesta(self) -> None:
		elemento = self.elemento
		if elemento is None or elemento["tipo"] != "comentario":
			self.ctx.avisar(_("Solo un comentario principal (no una respuesta) se puede marcar como respuesta."))
			return
		nodo = elemento["nodo"]
		marcar = not nodo.get("isAnswer")
		api = self.ctx.api()
		self.en_fondo(lambda: api.marcar_respuesta(nodo["id"], marcar),
			exito=_("Marcado como respuesta.") if marcar else _("Ya no está marcado como respuesta."),
			al_terminar=lambda _r: self.cargar(anunciar=False, enfocar_id=nodo["id"]))

	def votar(self) -> None:
		elemento = self.elemento
		if elemento is None:
			return
		id_nodo = elemento["nodo"].get("id")
		api = self.ctx.api()

		def trabajo() -> bool:
			# Sin envoltura en la API: saber si ya se votó requiere una consulta GraphQL con el cliente crudo.
			datos = api.c.graphql("query($id: ID!) { node(id: $id) { ... on Votable { viewerHasUpvoted } } }", {"id": id_nodo})
			ya_votado = bool((datos.get("node") or {}).get("viewerHasUpvoted"))
			api.votar(id_nodo, quitar=ya_votado)
			return not ya_votado

		self.en_fondo(trabajo, exito=lambda votado: _("Voto añadido.") if votado else _("Voto quitado."),
			al_terminar=lambda _r: self.cargar(anunciar=False, enfocar_id=id_nodo))

	def cerrar_discusion(self) -> None:
		if self.discusion.get("closed"):
			self.ctx.avisar(_("La discusión ya está cerrada."))
			return
		indice = elegir_uno(self, _("Cerrar la discusión"), _("&Motivo del cierre:"), [_(n) for _c, n in MOTIVOS_CIERRE])
		if indice is None:
			return
		motivo = MOTIVOS_CIERRE[indice][0]
		api = self.ctx.api()
		self.en_fondo(lambda: api.cerrar_discusion(self.discusion["id"], motivo), exito=_("Discusión cerrada."),
			al_terminar=lambda _r: self.cargar(anunciar=False))

	def reabrir(self) -> None:
		if not self.discusion.get("closed"):
			self.ctx.avisar(_("La discusión ya está abierta."))
			return
		api = self.ctx.api()
		self.en_fondo(lambda: api.reabrir_discusion(self.discusion["id"]), exito=_("Discusión reabierta."),
			al_terminar=lambda _r: self.cargar(anunciar=False))

	def ver_html(self) -> None:
		if not self.discusion:
			return
		from app.ui import visor_ayuda

		visor_ayuda.mostrar_documento(self, _("Discusión #{n}: {t}").format(n=self.numero, t=self.discusion.get("title", "")),
			markdown_discusion(self.discusion))

	def abrir_navegador(self) -> None:
		url = self.discusion.get("url") or f"https://{self.ctx.host}/{self.nombre}/discussions/{self.numero}"
		webbrowser.open(url)

	def copiar_enlace(self) -> None:
		url = self.discusion.get("url") or f"https://{self.ctx.host}/{self.nombre}/discussions/{self.numero}"
		copiar(self.ctx, url, _("Enlace copiado."))

	def copiar_texto(self) -> None:
		elemento = self.elemento
		if elemento is not None:
			copiar(self.ctx, elemento["nodo"].get("body") or "")


def abrir_discusion(ctx: Any, padre: wx.Window | None, nombre: str, numero: int) -> wx.Frame:
	"""Abre (o trae al frente) la ventana de una discusión y la carga en segundo plano."""
	clave = f"discusion:{nombre}:{int(numero)}"
	if VentanaDetalle.abrir_existente(clave):
		return VentanaDetalle._abiertas[clave]
	ventana = VentanaDiscusion(ctx, padre, nombre, int(numero))
	ventana.mostrar(ventana.lista)
	ventana.cargar()
	return ventana
