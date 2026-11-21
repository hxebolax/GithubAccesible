"""Pruebas de las funciones puras de conflictos (sin wx ni git)."""

from __future__ import annotations

import pytest

from app.services import conflictos as c

TEXTO = (
	"cabecera\n"
	"<<<<<<< HEAD\n"
	"mío 1\n"
	"mío 2\n"
	"=======\n"
	"suyo 1\n"
	">>>>>>> tema\n"
	"medio\n"
	"<<<<<<< HEAD\n"
	"=======\n"
	"solo en la otra\n"
	">>>>>>> tema\n"
	"final\n"
)


def test_analizar_bloques_y_lineas():
	archivo = c.analizar(TEXTO)
	assert len(archivo.bloques) == 2
	primero, segundo = archivo.bloques
	assert (primero.linea_inicio, primero.linea_fin) == (2, 7)
	assert primero.superior == ["mío 1\n", "mío 2\n"] and primero.inferior == ["suyo 1\n"]
	assert (primero.etiqueta_superior, primero.etiqueta_inferior) == ("HEAD", "tema")
	assert segundo.superior == [] and segundo.inferior == ["solo en la otra\n"]
	assert archivo.componer() == TEXTO, "sin resolver nada, el archivo queda igual"
	assert c.tiene_marcadores(TEXTO)


def test_resolver_cada_eleccion():
	archivo = c.analizar(TEXTO)
	assert c.lineas_de(archivo.bloques[0], c.AMBAS_OTRA_PRIMERO) == ["suyo 1\n", "mío 1\n", "mío 2\n"]
	c.resolver(archivo, 0, c.PROPIA)
	assert c.siguiente_pendiente(archivo, 0) == 1
	c.resolver(archivo, 1, c.AMBAS_PROPIA_PRIMERO)
	assert archivo.resuelto and c.siguiente_pendiente(archivo) is None
	assert archivo.componer() == "cabecera\nmío 1\nmío 2\nmedio\nsolo en la otra\nfinal\n"
	assert not c.tiene_marcadores(archivo.componer())
	c.deshacer(archivo, 1)
	assert len(archivo.pendientes) == 1 and "<<<<<<<" in archivo.componer()


def test_reorganizacion_invierte_los_lados():
	archivo = c.analizar(TEXTO)
	bloque = archivo.bloques[0]
	assert c.version_propia(bloque, invertido=True) == ["suyo 1\n"]
	assert c.version_otra(bloque, invertido=True) == ["mío 1\n", "mío 2\n"]
	c.resolver(archivo, 0, c.PROPIA, invertido=True)
	assert bloque.resolucion == ["suyo 1\n"]
	texto = c.describir_bloque(archivo, 0, invertido=True)
	assert texto.startswith("Bloque 1 de 2, líneas 2 a 7, resuelto con su versión.")
	assert texto.index("Su versión, marcada como «tema»") < texto.index("La otra versión, marcada como «HEAD»")
	assert c.version_git(c.PROPIA) == "ours" and c.version_git(c.PROPIA, invertido=True) == "theirs"
	assert c.version_git(c.OTRA, invertido=True) == "ours"
	assert c.es_invertido("reorganización") and not c.es_invertido("fusión")
	assert "al revés" in c.explicar_lados("reorganización")


def test_edicion_manual_conserva_crlf():
	texto = TEXTO.replace("\n", "\r\n")
	archivo = c.analizar(texto)
	assert archivo.fin_linea == "\r\n"
	inicial = c.texto_inicial_manual(archivo.bloques[0])
	assert inicial == "mío 1\nmío 2\nsuyo 1"
	c.resolver(archivo, 0, c.MANUAL, texto="mezcla\nde las dos")
	c.resolver(archivo, 1, c.MANUAL, texto="")
	assert archivo.componer() == "cabecera\r\nmezcla\r\nde las dos\r\nmedio\r\nfinal\r\n"
	with pytest.raises(ValueError):
		c.resolver(archivo, 0, c.MANUAL)


def test_diff3_con_base_y_descripcion():
	texto = "<<<<<<< ours\nA\n||||||| base\nB\n=======\nC\n>>>>>>> theirs"
	archivo = c.analizar(texto)
	bloque = archivo.bloques[0]
	assert bloque.base == ["B\n"] and bloque.etiqueta_base == "base" and bloque.inferior == ["C\n"]
	descripcion = c.describir_bloque(archivo, 0)
	assert "Versión común (base):\nB" in descripcion and "pendiente" in descripcion
	assert c.resumen(archivo) == "1 bloques: 0 resueltos y 1 pendientes."
	c.resolver(archivo, 0, c.OTRA)
	assert archivo.componer() == "C\n"


def test_marcadores_incompletos_son_texto():
	texto = "<<<<<<< sin cerrar\nalgo\n=======\nfin\n"
	archivo = c.analizar(texto)
	assert archivo.bloques == [] and archivo.componer() == texto
	assert c.texto_lineas([]) == "(vacía)"
	assert c.resumen(archivo).startswith("No quedan")
	assert not c.tiene_marcadores("<<<<<<<< ocho\n=======\n>>>>>>> x\n")
