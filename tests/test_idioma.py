"""Pruebas del idioma de la aplicación (1.0.7): español o inglés según el sistema y Preferencias.

Cubren la migración de la configuración, las novedades del manifiesto en los
dos idiomas, las notas bilingües de la release y el reinicio que se ofrece al
cambiar el idioma. La detección del idioma del sistema está en test_traducciones.py.
"""

from __future__ import annotations

import json
import sys

from app.core import configuracion as mod
from app.core import reinicio
from app.core.configuracion import Configuracion
from app.services import actualizador


def test_idioma_de_fabrica_automatico(tmp_path, monkeypatch):
	monkeypatch.setenv(mod.VARIABLE_DATA, str(tmp_path / "data"))
	config = Configuracion()
	assert config.obtener("general.idioma") == "auto"
	config.establecer("general.idioma", "en")
	assert config.obtener("general.idioma") == "en"


def test_quien_tenia_el_espanol_de_fabrica_pasa_a_automatico(tmp_path, monkeypatch):
	"""Hasta la 1.0.6 se guardaba «es» sin poder elegirlo: con la 1.0.7 manda el idioma de Windows."""
	monkeypatch.setenv(mod.VARIABLE_DATA, str(tmp_path / "data"))
	ruta = tmp_path / "data" / "config" / "settings.json"
	ruta.parent.mkdir(parents=True)
	ruta.write_text(json.dumps({mod.CLAVE_VERSION: 1, "general": {"idioma": "es", "confirmar_salida": True}}), encoding="utf-8")
	config = Configuracion()
	assert config.obtener("general.idioma") == "auto"
	assert config.obtener("general.confirmar_salida") is True
	guardado = json.loads(ruta.read_text(encoding="utf-8"))
	assert guardado[mod.CLAVE_VERSION] == mod.VERSION_ESQUEMA == 2
	# Elegido a mano después de la migración: se respeta.
	config.establecer("general.idioma", "es")
	assert Configuracion().obtener("general.idioma") == "es"


def test_novedades_del_manifiesto_en_el_idioma_de_la_interfaz():
	manifiesto = {
		"novedades": "Texto en español",
		"historial": [{"version": "1.0.7", "titulo": "Versión 1.0.7", "texto": "- Inglés."}],
		"novedades_en": "English text",
		"historial_en": [{"version": "1.0.7", "titulo": "Version 1.0.7", "texto": "- English."}],
	}
	assert actualizador.campo_en_idioma(manifiesto, "novedades", "es") == "Texto en español"
	assert actualizador.campo_en_idioma(manifiesto, "novedades", "en") == "English text"
	assert actualizador.campo_en_idioma(manifiesto, "historial", "en")[0]["titulo"] == "Version 1.0.7"
	# Manifiesto de una versión anterior (sin inglés): se usa el español.
	antiguo = {"novedades": "Solo español"}
	assert actualizador.campo_en_idioma(antiguo, "novedades", "en") == "Solo español"


def test_notas_de_la_release_en_los_dos_idiomas(tmp_path, monkeypatch):
	from tools import publicar

	(tmp_path / "docs" / "en").mkdir(parents=True)
	(tmp_path / "docs" / "changelog.md").write_text(
		"# Novedades\n\n## Versión 2.0.0 - 2026-11-22\n\n### Novedades\n\n- Inglés.\n\n## Versión 1.0.0 - 2026-11-01\n\n- Primera.\n",
		encoding="utf-8")
	(tmp_path / "docs" / "en" / "changelog.md").write_text(
		"# What's new\n\n## Version 2.0.0 - 2026-11-22\n\n### New\n\n- English.\n\n## Version 1.0.0 - 2026-11-01\n\n- First.\n",
		encoding="utf-8")
	monkeypatch.setattr(publicar, "RAIZ", tmp_path)
	notas = publicar.notas("2.0.0")
	assert notas.index("## Español") < notas.index("## English")
	assert "### Versión 2.0.0 - 2026-11-22" in notas and "#### Novedades" in notas
	assert "### Version 2.0.0 - 2026-11-22" in notas and "#### New" in notas
	assert "- First." in notas


def test_reinicio_pedido_relanza_la_aplicacion(monkeypatch):
	lanzados = []
	monkeypatch.setattr(reinicio.subprocess, "Popen", lambda orden, **_opciones: lanzados.append(orden))
	assert reinicio.relanzar_si_procede() is False
	reinicio.solicitar()
	assert reinicio.pendiente()
	assert reinicio.relanzar_si_procede() is True
	assert lanzados and lanzados[0][0] == sys.executable and lanzados[0][-1].endswith("main.py")
	assert not reinicio.pendiente()


def test_todo_texto_del_codigo_tiene_traduccion_inglesa():
	"""El inglés es el segundo idioma: ningún texto marcado puede quedar sin traducir ni «fuzzy».

	Si falla: tools/extraer_cadenas.py, tools/actualizar_po.py, traducir lo nuevo en
	data/locales/en/LC_MESSAGES/githubaccesible.po y tools/compilar_traducciones.py.
	"""
	from pathlib import Path

	from tools import catalogo_po, extraer_cadenas

	raiz = Path(__file__).resolve().parent.parent
	entradas, _problemas = extraer_cadenas.extraer(raiz)
	po = catalogo_po.leer_po(raiz / "data" / "locales" / "en" / "LC_MESSAGES" / "githubaccesible.po").por_clave()
	faltan = [e.msgid for e in entradas if e.clave not in po or not po[e.clave].traducida or po[e.clave].aproximada]
	assert not faltan, f"{len(faltan)} textos sin traducir al inglés, por ejemplo: {faltan[:5]}"
	# El .mo que se distribuye dice lo mismo que el .po (no se olvidó compilar).
	import gettext

	with (raiz / "data" / "locales" / "en" / "LC_MESSAGES" / "githubaccesible.mo").open("rb") as archivo:
		mo = gettext.GNUTranslations(archivo)
	distintas = [e.msgid for e in po.values() if not e.es_plural and e.msgctxt is None and e.msgid and mo.gettext(e.msgid) != e.msgstr]
	assert not distintas, f"el .mo no está al día con el .po (ejecute tools/compilar_traducciones.py): {distintas[:3]}"
