# Estándar: manual de usuario de una aplicación accesible

Para structural y codebase_details cuando revisan un manual, una lista de teclas o unas novedades. Complementa a documentacion-accesible.md. Escribid los hallazgos en español.

## Principio

Una persona que no conoce la aplicación instala, arranca y hace cada tarea principal solo con el manual y el teclado.

## Secciones que no pueden faltar

1. Qué es la aplicación y para quién (dos o tres frases).
2. Instalar y primer arranque: de dónde se descarga, dónde se descomprime (una aplicación portable no va en Archivos de programa), qué pasa la primera vez (descargas, preguntas) y qué se necesita (versión de Windows o de Android, conexión).
3. Cómo está organizada la ventana o la pantalla y cómo moverse por ella con el teclado o con gestos.
4. Una sección por tarea principal, con sus teclas.
5. Opciones: dónde están y qué pestañas tienen.
6. Dónde se guardan los datos y cómo se llevan a otro equipo.
7. Qué hacer si algo falla (registros, a quién avisar).
8. Riesgos y límites, si los hay.

## Contraste con el código (codebase_details)

- Cada atajo del manual existe en el código y hace lo que dice; cada atajo del código está en la lista de teclas.
- Los menús, botones y opciones citados existen con ese nombre exacto.
- Los valores de serie que el manual da (qué hace Intro, carpetas, intervalos) coinciden con los valores por defecto del código.
- Lo que el manual dice que se anuncia por voz coincide con los textos que la aplicación manda al lector.

## Novedades (registro de cambios)

- Una sección por versión, de la más nueva a la más vieja, con fecha.
- Cada línea dice qué puede hacer ahora la persona y dónde, no cómo está programado.

## Gravedad

- **Bloqueante**: falta la instalación o el primer arranque, o un atajo o menú del manual no existe.
- **Importante**: un valor de serie o un nombre no coincide con el código; falta una tarea principal.
- **Detalle**: orden de secciones, ejemplos.
