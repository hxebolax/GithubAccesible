# Estándar: SKILL.md de un agente (formato Agent Skills)

Para structural, comprehension e implementation_readiness cuando revisan un agente (skill) de un repositorio de agentes. Dad como contexto el perfil común de los agentes y las reglas del repositorio si existen. Escribid los hallazgos en español.

## Principio

Una IA que solo lee este SKILL.md (y lo que enlaza) sabe cuándo usarlo, qué entregar, cómo hacerlo en un proyecto real y cómo comprobar que ha funcionado, sin depender de nada que no esté en la carpeta del agente.

## Frontmatter

- `name` en minúsculas con guiones, igual que la carpeta (máximo 64 caracteres).
- `description` (máximo 1024 caracteres): qué hace y cuándo usarlo, con las frases con las que se pedirá («usa el agente de ...»).
- `license` y `metadata.version`; la versión sube con cada cambio y se anota en CAMBIOS.md.

## Autonomía

- No nombra proyectos concretos del usuario ni rutas absolutas de su equipo.
- No depende de otro agente: puede decir que se apoya en otro si está instalado, pero funciona sin él.
- Las dependencias externas (un plugin, un programa) se dicen, con cómo instalarlas y qué hacer si faltan.

## Carga progresiva

- SKILL.md por debajo de 500 líneas, breve y accionable: qué entrega, reglas de oro, flujo de trabajo, errores frecuentes.
- Los detalles van en `referencias/`, enlazados desde SKILL.md, a un solo nivel de profundidad.

## Plantillas

- Cada archivo de `plantillas/` tiene la misma ruta que tendrá en el proyecto y sus pruebas en `plantillas/tests/`.
- Funcionan con Python 3.10 o superior y solo con la biblioteca estándar, salvo que se diga.
- El SKILL.md dice cómo copiarlas, qué ajustar y cómo comprobarlas.

## Flujo de trabajo y entrega

- Separa inspeccionar (sin cambiar nada), aplicar, verificar de verdad y entregar.
- Exige separar lo verificado de lo supuesto y lo pendiente (por ejemplo, probar con un lector de pantalla real).
- Todo en español; documentos con encabezados y listas, tablas pequeñas.

## Gravedad

- **Bloqueante**: nombra proyectos o rutas del usuario, depende de otro agente, o una instrucción no se puede seguir.
- **Importante**: falta cuándo usarlo, cómo verificar o qué hacer si falta una dependencia; plantilla sin pruebas.
- **Detalle**: redacción, orden.
