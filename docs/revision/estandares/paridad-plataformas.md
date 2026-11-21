# Estándar: paridad entre plataformas (adaptación o clon de una aplicación)

Para codebase_details, implementation_readiness y design_critic cuando revisan un documento que compara una aplicación original con su versión para otra plataforma (por ejemplo, de Android a Windows o al revés): un diseño de la adaptación, una lista de funciones o un informe de lo que falta. Dad como contexto la documentación y el código de LAS DOS versiones (o sus carpetas). Escribid los hallazgos en español.

## Principio

Quien lea el documento sabe, función por función, qué tiene la original, qué tiene la nueva, qué se ha adaptado a la plataforma y qué falta, y puede comprobarlo en el código de las dos.

## Lo que debe cubrir

- **Inventario de funciones** de la original (pantallas, menús, ajustes, servicios externos, formatos) y su equivalente en la nueva: igual, adaptada (cómo y por qué), pendiente o descartada (con motivo).
- **Comportamiento**, no solo nombres: valores de serie, qué pasa al terminar, al fallar la red, al cerrar y volver a abrir.
- **Lo propio de cada plataforma**: lector de pantalla (TalkBack frente a NVDA o JAWS), gestos frente a teclas, notificaciones, segundo plano, permisos, almacenamiento y actualizaciones.
- **Datos y formatos compartidos**: si la nueva lee o escribe lo mismo (archivos, cuentas, servidores), que coincidan los formatos.
- **Lógica común**: lo que se puede portar casi igual (analizadores, reglas de negocio) está identificado y probado con las mismas muestras.
- **Cambios del servicio externo**: si la original tuvo que adaptarse a cambios de un servicio (una API que cambia), la nueva los recoge.

## Accesibilidad

- Cada adaptación de interfaz dice cómo se maneja con el lector de pantalla de la nueva plataforma.
- Ninguna función queda solo para quien ve la pantalla.

## Gravedad

- **Bloqueante**: una función principal de la original no aparece ni como pendiente, o se describe un comportamiento distinto sin decirlo.
- **Importante**: falta el comportamiento ante errores o al reanudar; una adaptación no explica cómo se usa con lector de pantalla.
- **Detalle**: nombres, orden.
