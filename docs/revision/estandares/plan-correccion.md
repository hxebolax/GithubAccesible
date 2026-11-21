# Estándar: plan de corrección o de implementación sobre un código existente

Para codebase_details (y como apoyo de implementation_readiness) cuando revisan un plan: el que sale de una auditoría, la corrección de un fallo o una función nueva sobre un proyecto que ya existe. Dad como contexto los archivos que el plan toca. Escribid los hallazgos en español.

## Principio

Otra persona puede ejecutar el plan paso a paso en este código, sin adivinar, y sabe cuándo ha terminado y cómo comprobarlo.

## Cada paso

- Cita archivo, función o símbolo que existen de verdad (`archivo:línea` cuando ayuda).
- Dice qué cambia y por qué, y qué no se toca.
- Reutiliza lo que ya hay en el proyecto (módulos de rutas, configuración, registro, red, hilos) en vez de crear otro igual.
- Dice cómo se comprueba: qué prueba se añade o ejecuta y qué resultado se espera.

## Reglas que el plan no puede romper

- La interfaz no se bloquea: red y disco en hilos; los controles solo desde el hilo principal.
- Ningún error se pierde: todo fallo queda registrado con su traza.
- Los datos del usuario (configuración, base de datos, sesiones, descargas) no se borran ni se sobrescriben.
- La accesibilidad no empeora: etiquetas, letras de acceso, foco y anuncios siguen igual o mejor.
- Lo portable sigue siendo portable: nada fuera de la carpeta data.

## Orden y riesgo

- Los pasos están en un orden que se puede ejecutar; lo que depende de otro va después.
- Lo arriesgado (migraciones, cambios de formato, borrados) tiene copia de seguridad o vuelta atrás.
- Se dice qué queda pendiente de comprobar a mano (lector de pantalla real, otro equipo, el servicio externo).

## Gravedad

- **Bloqueante**: un paso cita algo que no existe, rompe una de las reglas de arriba o no se puede verificar.
- **Importante**: falta la comprobación de un paso, duplica algo que ya existe, orden imposible.
- **Detalle**: redacción.
