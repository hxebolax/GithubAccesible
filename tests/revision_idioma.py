"""Revisión de la interfaz en otro idioma (``APP_PRUEBAS_IDIOMA=en``).

Las pruebas comprueban los textos en español, pero las letras de acceso y los
textos que quedan sin traducir solo se ven con la interfaz en el otro idioma.
Con la variable ``APP_PRUEBAS_IDIOMA`` (por ejemplo ``en``), ``conftest.py``:

1. Instala el catálogo de ``data/locales`` real (las pruebas redirigen ``data``).
2. Sustituye ``afirmar_teclado_correcto``: en vez de fallar, apunta en un
   informe las letras de acceso repetidas de cada ventana revisada y los textos
   visibles que siguen en español.

Así se recorren con el idioma nuevo todas las ventanas que las pruebas ya abren.
Muchas pruebas fallarán (esperan textos en español): lo que importa es el
informe, que se escribe en ``APP_PRUEBAS_INFORME`` (por defecto
``revision_idioma.txt`` en la carpeta temporal). Uso::

	set APP_PRUEBAS_IDIOMA=en
	.venv\\Scripts\\python.exe -m pytest tests\\test_ventana_principal.py tests\\test_repositorio.py ... -q
	type %TEMP%\\revision_idioma.txt
"""

from __future__ import annotations

import gettext
import os
import re
import tempfile
from pathlib import Path

VARIABLE = "APP_PRUEBAS_IDIOMA"
VARIABLE_INFORME = "APP_PRUEBAS_INFORME"
RAIZ = Path(__file__).resolve().parent.parent

# Palabras que delatan un texto en español (con tildes o muy frecuentes).
_ESPANOL = re.compile(
	r"[ñáéíóú¿¡]|\b(el|los|las|del|que|para|con|una|está|puede|archivo|repositorio|buscar|abrir|cerrar|nuevo|nueva)\b",
	re.IGNORECASE,
)


def idioma() -> str:
	return os.environ.get(VARIABLE, "").strip()


def ruta_informe() -> Path:
	return Path(os.environ.get(VARIABLE_INFORME) or Path(tempfile.gettempdir()) / "revision_idioma.txt")


def instalar_catalogo() -> None:
	"""Instala el catálogo real del idioma pedido (``data`` está redirigido en las pruebas)."""
	from app.core import i18n

	ruta_informe().write_text("", encoding="utf-8")
	if i18n.es_idioma_base(idioma()):
		# En español (el idioma del código) sirve para comparar: no hay catálogo que instalar.
		return
	traduccion = gettext.translation(i18n.DOMINIO, localedir=str(RAIZ / "data" / "locales"), languages=[idioma()])
	i18n._instalar(traduccion)
	i18n._traduccion, i18n._idioma = traduccion, idioma()
	ruta_informe().write_text("", encoding="utf-8")


def _textos(ventana) -> list[str]:
	"""Textos visibles de una ventana y sus hijas: etiquetas, opciones, columnas, páginas y menús."""
	import wx

	textos: list[str] = []

	def recorrer(v) -> None:
		if isinstance(v, (wx.StaticText, wx.Button, wx.CheckBox, wx.RadioButton, wx.StaticBox, wx.TopLevelWindow)):
			textos.append(v.GetLabel() if not isinstance(v, wx.TopLevelWindow) else v.GetTitle())
		if isinstance(v, (wx.Choice, wx.ListBox, wx.ComboBox)) and not isinstance(v, wx.CheckListBox):
			textos.extend(v.GetStrings()[:30])
		if isinstance(v, wx.ListCtrl) and v.InReportView():
			textos.extend(v.GetColumn(i).GetText() for i in range(v.GetColumnCount()))
		if isinstance(v, wx.BookCtrlBase):
			textos.extend(v.GetPageText(i) for i in range(v.GetPageCount()))
		if isinstance(v, wx.Frame) and v.GetMenuBar():
			barra = v.GetMenuBar()
			for i in range(barra.GetMenuCount()):
				textos.append(barra.GetMenuLabel(i))
				for elemento in barra.GetMenu(i).GetMenuItems():
					if not elemento.IsSeparator():
						textos.append(elemento.GetItemLabel())
		for hija in v.GetChildren():
			recorrer(hija)

	recorrer(ventana)
	return [t for t in textos if t]


def apuntar(ventana, teclas_propias=(), ignorar=()) -> None:
	"""Sustituto de ``afirmar_teclado_correcto``: apunta problemas en el informe sin fallar."""
	from app.ui.accesibilidad.revision_teclado import informe, revisar_teclado

	try:
		problemas = [p for p in revisar_teclado(ventana, teclas_propias, ignorar) if not p.aviso]
	except Exception as error:  # noqa: BLE001 - una ventana a medio destruir no debe parar la revisión
		problemas = []
		with ruta_informe().open("a", encoding="utf-8") as archivo:
			archivo.write(f"## No se pudo revisar {type(ventana).__name__}: {error}\n\n")
	nombre = type(ventana).__name__
	lineas = []
	if problemas:
		lineas.append(f"## Teclado en {nombre}\n{informe(problemas)}")
	espanol = sorted({t for t in _textos(ventana) if _ESPANOL.search(re.sub(r"\{[^}]*\}", "", t))})
	if espanol:
		lineas.append(f"## Textos en español en {nombre}\n" + "\n".join(f"- {t!r}" for t in espanol))
	if lineas:
		with ruta_informe().open("a", encoding="utf-8") as archivo:
			archivo.write("\n".join(lineas) + "\n\n")


def activar() -> None:
	"""Instala el catálogo y sustituye la comprobación de teclado (lo llama conftest)."""
	instalar_catalogo()
	from app.ui.accesibilidad import revision_teclado

	revision_teclado.afirmar_teclado_correcto = apuntar
