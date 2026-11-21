# Investigación: todo sobre buscar en GitHub (para el buscador de GitHub Accesible)

Fecha de la investigación: 21 de noviembre de 2026. Versión de la API REST consultada: 2026-03-10 (la actual; la anterior es 2022-11-28).

Cómo leer este informe:

- «Verificado» quiere decir que lo he leído hoy en la documentación oficial o en el código de gh (cli/cli, clonado el 20 de noviembre de 2026, confirmación de06af2).
- «Dudoso» quiere decir que solo aparece en un anuncio antiguo, en un formulario de la web o en fuentes de terceros, o que la documentación se contradice. Conviene probarlo con una consulta real antes de ofrecerlo como control guiado.
- Al final hay una lista de fuentes con su dirección.

## 1. Estado actual del buscador de la aplicación

Lo que ya hay (archivo app/ui/busqueda.py y método ApiBusqueda.buscar en app/services/github/api_extra.py):

- Siete tipos REST: repositorios, código, issues y pull requests, usuarios, commits, temas y etiquetas.
- Texto libre que admite calificadores, historial de 20 búsquedas, orden y dirección.
- Solo para repositorios: categorías guiadas (estrellas mínimas, bifurcaciones mínimas, fecha de último envío, good-first-issues, help-wanted, Awesome y unos 30 temas), lenguaje (también para código, issues y usuarios) y licencia.
- La llamada envía siempre advanced_search=true en issues y pide fragmentos resaltados (text-match) solo en código.

Carencias detectadas frente a la documentación actual:

- Faltan órdenes válidos: en issues faltan «interacciones» y las reacciones concretas (pulgar arriba, corazón, etc.); en etiquetas faltan «creación» y «actualización».
- El tipo «Etiquetas» necesita el identificador numérico del repositorio (repository_id) y no admite calificadores; el diálogo no pide el repositorio.
- No hay filtros guiados para issues, pull requests, código, usuarios, commits ni temas.
- No se aprovecha text-match en los demás tipos (está disponible para todos).
- No hay búsqueda semántica ni híbrida de issues (nueva desde abril de 2026).
- No hay discusiones (solo GraphQL) ni tendencias.
- El buscador HTML del autor resolvía «Tendencias» y «Útiles» añadiendo las palabras «trending» y «helpful» al texto: eso no da las tendencias reales, solo repositorios que contienen esa palabra.

## 2. Sintaxis general (todos los tipos salvo la búsqueda de código nueva)

Verificado en «Understanding the search syntax» y en la página REST de búsqueda.

### Comparaciones y rangos

- Mayor que: stars:>1000. Mayor o igual: topics:>=5. Menor que: size:<50. Menor o igual: stars:<=10.
- Rango inclusivo con dos puntos: stars:10..50.
- Rango abierto con asterisco: stars:10..* equivale a >=10; stars:*..10 equivale a <=10.
- Sirven para números (estrellas, bifurcaciones, tamaño, seguidores, comentarios, reacciones, interacciones, repos, temas) y para fechas.

### Fechas

- Formato ISO 8601: AAAA-MM-DD, por ejemplo created:>2016-04-29 o pushed:2016-04-30..2016-07-04.
- Se puede añadir la hora con desfase: created:2017-01-01T01:00:00+07:00..2017-03-01T15:30:15+07:00, o en UTC con Z: 2016-03-21T14:11:00Z.
- Calificadores de fecha: created, updated, pushed (repos), closed, merged (PR), author-date y committer-date (commits).

### Exclusión

- Guion delante del calificador: -language:javascript, -label:wontfix.
- NOT delante de una palabra: hello NOT world. NOT solo funciona con palabras, no con números ni fechas.
- El guion no funciona con no: (no se puede escribir -no:label; para eso existe has:label en la búsqueda avanzada de issues).

### Comillas, mayúsculas y usuarios especiales

- Todo valor con espacios va entre comillas: label:"bug fix", cats NOT "hello world".
- La búsqueda no distingue mayúsculas y minúsculas.
- @me es la persona que ha iniciado sesión (assignee:@me, author:@me). @copilot es Copilot (author:@copilot, assignee:@copilot, reviewed-by:@copilot). Ambos solo valen como valor de un calificador, nunca como palabra suelta.
- author:app/NOMBRE busca contenido creado por una GitHub App (gh lo genera con la bandera --app).

### Límites de la consulta (verificado en la página REST)

- Máximo 256 caracteres, sin contar operadores ni calificadores.
- Máximo cinco operadores AND, OR o NOT.
- Si se supera, la API responde 422 «Validation failed».
- En la búsqueda avanzada de issues, paréntesis anidados hasta cinco niveles; hasta 16 calificadores user: u org:; repo: sin límite (verificado en la página de filtrado de issues).

### Caracteres especiales

- En la búsqueda de código antigua (la de REST) se ignoran estos caracteres: punto, coma, dos puntos, punto y coma, barra, barra invertida, acento grave, comilla simple y doble, igual, asterisco, exclamación, interrogación, almohadilla, dólar, et, más, circunflejo, barra vertical, virgulilla, menor, mayor, paréntesis, llaves, corchetes y arroba. Por eso no se puede buscar «a.b» literalmente por REST.
- La documentación general dice que la búsqueda no admite coincidencia exacta («Currently our search doesn't support exact matching»); las comillas agrupan palabras, pero no garantizan una coincidencia carácter a carácter.

## 3. Repositorios (GET /search/repositories)

Verificado en «Searching for repositories», salvo lo marcado.

### Dónde buscar el texto

- in:name, in:description, in:topics, in:readme; combinables: in:name,description.
- Sin in: se busca en nombre, descripción y temas, no en el README.
- repo:dueño/nombre para un repositorio concreto.

### Propietario

- user:NOMBRE (repos de una persona), org:NOMBRE (de una organización). Se pueden repetir; en la búsqueda clásica varios user:, repo: o is: se combinan con O (comentario del código de gh, pkg/search/query.go).

### Números

- size:n en kilobytes (size:>=30000, size:50..120).
- followers:n (seguidores del repositorio, es decir, quienes lo vigilan; followers:>=10000).
- forks:n (forks:>=205, forks:10..20).
- stars:n (stars:>=500, stars:10..20).
- topics:n número de temas (topics:5, topics:>3).
- good-first-issues:>n y help-wanted-issues:>n (la documentación solo muestra el signo mayor que).

### Fechas

- created: fecha de creación.
- pushed: último envío a cualquier rama.

### Clasificación

- language:NOMBRE (nombres o alias de Linguist: c++, c#, shell, vim-script...).
- topic:NOMBRE (se puede repetir; cada uno añade una condición Y).
- license:CLAVE con la clave de licencia, no el nombre: mit, apache-2.0, gpl-3.0, gpl-2.0, agpl-3.0, lgpl-3.0, lgpl-2.1, bsd-3-clause, bsd-2-clause, bsd-3-clause-clear, bsd-4-clause, 0bsd, mpl-2.0, epl-1.0, epl-2.0, eupl-1.1, eupl-1.2, isc, unlicense, cc0-1.0, cc-by-4.0, cc-by-sa-4.0, wtfpl, zlib, bsl-1.0, artistic-2.0, afl-3.0, ofl-1.1, osl-3.0, postgresql, upl-1.0, vim, mit-0, ms-pl, ms-rl, ncsa, odbl-1.0, lppl-1.3c, gfdl-1.3, ecl-2.0, cecill-2.1, mulanpsl-2.0, blueoak-1.0.0, bsd-2-clause-patent, cern-ohl-p-2.0, cern-ohl-s-2.0, cern-ohl-w-2.0; y las familias cc, gpl y lgpl. La lista sale del desplegable de github.com/search/advanced; las claves son las de choosealicense (dudoso solo en las menos comunes: conviene contrastar con GET /licenses).

### Estado y tipo

- is:public, is:private (privados a los que se tiene acceso), is:internal (solo empresas; gh lo ofrece en --visibility; no aparece en esta página).
- archived:true o archived:false.
- mirror:true o mirror:false.
- template:true o template:false.
- fork:true incluye bifurcaciones (por defecto se excluyen); fork:only solo bifurcaciones. Para excluirlas basta con no poner nada (gh ofrece --include-forks con false, true y only).
- is:sponsorable (el dueño tiene perfil de GitHub Sponsors).
- has:funding-file (tiene FUNDING.yml).

### Solo para organizaciones (poco útiles en una app general)

- props.PROPIEDAD:VALOR (propiedades personalizadas; exige limitar a una sola org).
- deployable:true y deployed:true (artefactos vinculados de la organización).

### Dudoso o no documentado

- is:archived, is:mirror, is:template: la documentación usa archived:, mirror: y template:. No los ofrecería.
- La documentación no dice si varios language: se combinan con O.

### Órdenes REST (verificado)

- sort: stars, forks, help-wanted-issues, updated. Sin sort: mejor coincidencia. order: desc (por defecto) o asc; se ignora si no hay sort.

## 4. Issues y pull requests (GET /search/issues)

### Calificadores (verificado en «Searching issues and pull requests» y en «Filtering and searching issues and pull requests»)

Tipo y estado:

- is:issue o type:issue; is:pr o type:pr.
- is:open, is:closed, state:open, state:closed.
- reason:completed, reason:"not planned" (motivo de cierre). El formulario de búsqueda avanzada de la web ofrece además «reopened» (reason:reopened), que no está en la documentación: dudoso.
- is:merged, is:unmerged (PR).
- is:draft, draft:true, draft:false (PR).
- is:locked, is:unlocked.
- is:archived (PR archivadas; requiere permiso de triaje).
- is:queued (PR en la cola de fusión).
- is:public, is:private.
- archived:true o archived:false (si el repositorio está archivado).

Dónde buscar el texto:

- in:title, in:body, in:comments, combinables (in:title,body).

Ámbito:

- user:, org:, repo:dueño/nombre.

Personas (todas admiten @me):

- author:, assignee: (assignee:* cualquier asignado, solo en un repositorio), mentions:, team:ORG/EQUIPO (menciones a un equipo), commenter:, involves: (autor, asignado, mencionado o comentarista).
- PR: reviewed-by:, review-requested: (desaparece tras revisar), review-involves: (sigue apareciendo tras revisar), user-review-requested:@me (solicitado a ti personalmente), team-review-requested:ORG/EQUIPO, team-review-requested-user:.

Metadatos:

- label:ETIQUETA (repetido = Y; separado por comas = O: label:bug,resolved), -label:.
- milestone:"nombre".
- project:DUEÑO/NUMERO (gh: --project owner/number).
- linked:pr (issues enlazados a una PR que los cerrará), linked:issue (PR enlazadas a un issue), y sus negaciones.
- type:"Bug", type:"Feature", type:"Task" (tipos de issue de la organización; los nombres dependen de cada org). Verificado en la página de filtrado.
- field.NOMBRE:VALOR (campos de issue): field.priority:high, field."target date":>=2026-03-01, field.story-points:>5, field.priority:high,medium (O). Verificado en la página de filtrado; es reciente.
- has:label, has:assignee... (tiene el metadato) y no:label, no:milestone, no:assignee, no:project (le falta).
- Dependencias entre issues (anuncio de agosto de 2025): is:blocked, is:blocking, blocked-by:NUMERO, blocking:NUMERO. Dudoso el formato exacto del valor.
- Sub-issues (anuncio de diciembre de 2024): has:sub-issue, no:parent-issue, parent-issue:"dueño/repo#numero". Dudoso: la grafía (singular o plural) varía entre fuentes.

Código y ramas (PR):

- status:pending, status:success, status:failure (estado de las comprobaciones; gh: --checks).
- head:RAMA (rama de origen), base:RAMA (rama de destino).
- Un SHA de al menos 7 caracteres como palabra: encuentra la PR que lo contiene.
- review:none, review:required, review:approved, review:changes_requested.

Números y fechas:

- comments:n, interactions:n (reacciones más comentarios), reactions:n; con >, <, rangos.
- created:, updated:, closed:, merged: con fechas y rangos.
- language: lenguaje del repositorio.

### Búsqueda avanzada (AND, OR, paréntesis)

- Verificado: en REST se activa con advanced_search=true; en GraphQL con type: ISSUE_ADVANCED. El esquema GraphQL de hoy todavía tiene ISSUE_ADVANCED y gh sigue enviando advanced_search=true en github.com (pkg/search/searcher.go). Hubo un anuncio de que sería el comportamiento por defecto desde el 4 de septiembre de 2025, pero no lo he podido confirmar para la API: lo prudente es seguir enviándolo, como ya hace la aplicación.
- Un espacio equivale a AND. OR debe escribirse. Paréntesis hasta cinco niveles.
- Diferencia importante: en la búsqueda clásica, varios repo:, org: o user: separados por espacios se combinan con O; en la avanzada se combinan con Y. gh los agrupa explícitamente: (repo:a OR repo:b). También rodea las palabras libres con paréntesis para que un OR del usuario no se mezcle con los filtros: ( palabras ) filtros. La aplicación debería hacer lo mismo al construir la consulta.
- gh agrupa con OR los valores opuestos de is: (open/closed, issue/pr, merged/unmerged, locked/unlocked, public/private, blocked/blocking) y de in:.

### Búsqueda semántica e híbrida (nueva, verificada)

- Disponible de forma general desde el 2 de abril de 2026.
- REST: parámetro search_type=semantic (vectorial pura) o search_type=hybrid (semántica más léxica). Sin el parámetro, búsqueda léxica.
- GraphQL: type: ISSUE_SEMANTIC o type: ISSUE_HYBRID; la conexión devuelve issueSearchType y lexicalFallbackReason (motivos por los que se volvió a la búsqueda léxica).
- Requiere autenticación y tiene su propio límite: 10 peticiones por minuto.
- Indexa título y cuerpo de issues; se puede acotar con org:, user: y repo:. Las consultas que solo tienen filtros o comillas se resuelven con búsqueda léxica.
- Restricciones que aplica gh (pkg/cmd/search/issues/issues.go): solo issues (no se puede combinar con PR), no admite sort ni order, se pide una única página, y no existe en GitHub Enterprise Server.
- Dudoso: el nombre exacto de los campos de la respuesta REST que indican qué búsqueda se hizo; hay que mirarlo en una respuesta real.

### Órdenes REST (verificado)

- sort: comments, reactions, reactions-+1, reactions--1, reactions-smile, reactions-thinking_face, reactions-heart, reactions-tada, interactions, created, updated. Sin sort: mejor coincidencia. order: desc o asc.
- En la web también existen sort:reactions-rocket y sort:reactions-eyes como calificador dentro de la consulta, y sort:relevance; en REST no están en la lista del parámetro sort (no ofrecerlos).
- Con search_type semántico o híbrido no se puede ordenar.

### Otras notas

- Si se accede a PR de más de 10 000 repositorios, conviene limitar con org:, user: o repo:.
- Con tokens de usuario de GitHub Apps, una consulta sin is:issue o is:pull-request da 422; lo más seguro es añadir siempre el tipo (gh añade type:issue o type:pr por defecto).
- Versión 2026-03-10: los resultados de /search/issues ya no traen el campo singular assignee; usar assignees.

## 5. Código (GET /search/code)

### Lo que hay en REST: la búsqueda de código antigua (verificado)

La página oficial lo dice así: solo hace falta la sintaxis antigua «si usa la API de búsqueda de código». gh avisa de lo mismo: los resultados vienen del motor antiguo, pueden no coincidir con github.com y las expresiones regulares no están en la API.

Calificadores:

- in:file, in:path, in:file,path (por defecto, contenido).
- user:, org:, repo:dueño/nombre.
- path:/ (raíz), path:DIRECTORIO, path:ruta/a/directorio.
- filename:NOMBRE.
- extension:EXT.
- language:NOMBRE.
- size:n con >, < y rangos. La documentación antigua lo expresa en bytes (ejemplo: size:>10000 para más de 10 KB); gh lo describe como kilobytes. Dudoso: presentarlo como bytes.
- fork:true o fork:only (solo bifurcaciones indexadas).

Limitaciones:

- Exige sesión iniciada; 10 peticiones por minuto (recurso code_search).
- Solo la rama por defecto, archivos de menos de 384 KB, repositorios de menos de 500 000 archivos y con actividad en el último año; los repositorios archivados no se buscan.
- Hasta 4000 repositorios privados (los más recientes de los primeros 10 000 accesibles).
- Las bifurcaciones solo se indexan si tienen más estrellas que el original.
- Hace falta al menos una palabra (language:go solo no vale), salvo con filename:.
- Como mucho dos fragmentos por archivo.
- sort=indexed y order están marcados en la documentación como «This field is closing down»: no ofrecer orden en código.
- Caracteres especiales ignorados (lista en el apartado 2).

### La búsqueda de código nueva de la web: NO está en la API

Verificado: la página de la sintaxis nueva no menciona ninguna API; la respuesta aceptada en GitHub Community (discusión 102615) dice que la API REST no admite expresiones regulares como la web y que está «en la hoja de ruta» con retraso; gh confirma que no está disponible por la API. No existe tipo CODE en el search de GraphQL.

Lo que tiene la web y no la API:

- Expresiones regulares entre barras: /sparse.*index/, con \n, \t, \x{hhhh}; sin aserciones de anticipación; distinción de mayúsculas con /(?-i)True/.
- AND, OR, NOT y paréntesis: (language:ruby OR language:python) AND NOT path:"/tests/".
- symbol: (definiciones de funciones, clases..., con Tree-sitter), content: (solo contenido), path: con comodines (* , ** , ?) y con regex, is:archived, is:fork, is:vendored, is:generated, license:, enterprise:.
- Coincidencia exacta entre comillas con escape de comillas y barras invertidas.
- Búsquedas guardadas (escribiendo saved: en la barra) e historial.

Alternativas razonables:

- Botón «Abrir esta búsqueda en el navegador»: https://github.com/search?q=CONSULTA&type=code (lo mismo que gh --web). Es la única forma oficial de usar regex y símbolos.
- Filtrar en local: pedir a REST una palabra literal del patrón y aplicar la expresión regular sobre los fragmentos de text-match o sobre el contenido descargado (es lo que hace la herramienta de terceros fulll/github-code-search). Caro en peticiones.
- Servicios de terceros como grep.app (regex sobre código público; sin API oficial documentada) o Sourcegraph: no oficiales, con sus propias condiciones; no los integraría sin revisarlas.

## 6. Usuarios y organizaciones (GET /search/users)

Verificado en «Searching users».

- type:user o type:org.
- user:NOMBRE, org:NOMBRE.
- in:login, in:name (algunos ejemplos usan in:fullname), in:email (solo correos públicos; no se puede buscar por dominio). Sin in: se busca en usuario y correo.
- fullname:NOMBRE APELLIDO (sensible a los espacios).
- repos:n (repos:>9000, repos:10..30).
- location:LUGAR.
- language:LENGUAJE (lenguaje mayoritario de sus repositorios).
- created: fecha de alta.
- followers:n.
- is:sponsorable.
- Órdenes REST: followers, repositories, joined; order desc o asc.

## 7. Commits (GET /search/commits)

Verificado en «Searching commits».

- Palabras: buscan en el mensaje.
- author:USUARIO, committer:USUARIO.
- author-name:, committer-name: (texto del nombre).
- author-email:, committer-email: (correo completo).
- author-date:, committer-date: con fechas y rangos.
- merge:true o merge:false.
- hash:SHA, parent:SHA (hijos de ese commit), tree:SHA.
- user:, org:, repo:.
- is:public, is:private.
- Solo la rama por defecto.
- Órdenes REST: author-date, committer-date; order desc o asc.

## 8. Temas (GET /search/topics)

Verificado.

- is:featured, is:not-featured, is:curated, is:not-curated.
- repositories:n (repositories:>5000).
- created: fecha.
- No admite sort ni order.
- text-match busca en short_description, description, name y display_name.

## 9. Etiquetas (GET /search/labels)

Verificado.

- repository_id obligatorio (número; se obtiene con GET /repos/dueño/nombre, campo id).
- q no admite calificadores, solo palabras.
- Órdenes: created, updated; order desc o asc.

## 10. Discusiones (solo GraphQL)

Verificado en «Searching discussions» y en la referencia GraphQL. No hay endpoint REST de búsqueda de discusiones.

Llamada: search(query: "...", type: DISCUSSION, first: 50, after: cursor), con discussionCount y nodos de tipo Discussion (título, url, autor, categoría, si está respondida, número de comentarios, votos, fechas, repositorio).

Calificadores:

- in:title, in:body, in:comments.
- user:, org:, repo:, is:public, is:private.
- author:, commenter:, involves:, answered-by:.
- is:answered, is:unanswered, is:open, is:closed, is:locked, is:unlocked.
- category:NOMBRE (category:Ideas).
- label:"nombre".
- comments:n.
- created:, updated:.
- No documentados para discusiones: reactions: e interactions:.
- El orden se pone en la consulta (sort:created, sort:updated, sort:comments...): dudoso para discusiones; probar.

## 11. Wikis, paquetes y Marketplace

- Wikis: la web tiene calificadores (user:, org:, repo:, in:title, in:body, updated:), pero no hay API. La conexión GraphQL tiene un contador wikiCount, pero SearchType no tiene valor WIKI. Solución: abrir en el navegador con type=wikis.
- Paquetes: la web admite user:, org:, is:public, is:private. No hay API de búsqueda; solo listados por dueño (GET /users/{u}/packages y GET /orgs/{org}/packages con package_type). Solución: abrir en el navegador (la documentación usa type=RegistryPackages en sus enlaces).
- Marketplace: el tipo MarketplaceListing está en la unión de resultados GraphQL, pero no hay SearchType para él.

## 12. Resultados, paginación, text-match y límites

### Paginación y tope de 1000

- per_page máximo 100 (por defecto 30), page desde 1. Hay que seguir la cabecera Link (gh lo hace así).
- Cada búsqueda devuelve como mucho 1000 resultados (REST y GraphQL). total_count puede ser mucho mayor; pedir la página 11 con 100 por página da error 422.
- Cómo pasar del tope: partir el intervalo de fechas. Algoritmo recomendado: si total_count es mayor que 1000, dividir el intervalo de created: (o pushed:, updated:, author-date:) en dos mitades y repetir hasta que cada trozo tenga 1000 o menos; luego recorrer los trozos. Para código, que no tiene fecha, partir por size:, extension:, path: o repo:. Cada trozo gasta peticiones del límite de 30 por minuto: avisar del coste y permitir cancelar. Algunas personas informan de que el orden dentro de cada trozo no es fiable: ordenar en local si importa.

### incomplete_results

- Si la consulta supera el tiempo máximo, GitHub devuelve lo encontrado hasta entonces con incomplete_results: true. No significa necesariamente que falten resultados. Conviene anunciarlo («Puede que falten resultados; GitHub cortó la búsqueda por tiempo») y ofrecer reintentar o acotar.

### text-match (fragmentos resaltados)

- Cabecera Accept: application/vnd.github.text-match+json. Funciona en todos los tipos REST, no solo en código.
- Añade text_matches a cada resultado: object_url, object_type, property (el campo donde coincidió), fragment (fragmento de texto) y matches (texto e índices dentro del fragmento).
- Campos donde busca: código (contenido y ruta), commits (mensaje), issues (título, cuerpo y comentarios), etiquetas (nombre y descripción), repositorios (nombre y descripción), temas (varios), usuarios (usuario, correo público y nombre).
- En GraphQL: textMatches en cada arista (fragment, highlights, property).
- Para lector de pantalla es muy útil: permite una columna o un detalle «Coincide en el cuerpo: ...fragmento...».

### Límites de uso (verificado)

- Búsqueda autenticada: 30 peticiones por minuto (recurso search).
- Búsqueda de código: 10 por minuto, siempre autenticada (recurso code_search).
- Sin autenticar: 10 por minuto.
- Semántica e híbrida de issues: 10 por minuto.
- Cabeceras: x-ratelimit-limit, x-ratelimit-remaining, x-ratelimit-used, x-ratelimit-reset (segundos epoch UTC), x-ratelimit-resource (search, code_search, graphql...). Las cabeceras mandan sobre GET /rate_limit.
- Al agotarse: 403 o 429 con remaining 0; esperar a reset. Límite secundario: respetar retry-after si viene; si no, esperar al menos un minuto y reintentar con espera creciente.
- GET /rate_limit no gasta del límite primario; en 2026-03-10 ya no tiene el campo rate (usar resources.core, resources.search, resources.code_search, resources.graphql).
- Errores de acceso: repo:, user: u org: a algo sin acceso da 422; si la consulta abarca varios, se omiten en silencio los inaccesibles.

## 13. GraphQL frente a REST

search(query: String!, type: SearchType!, first, last, after, before) devuelve SearchResultItemConnection.

- SearchType: ISSUE, ISSUE_ADVANCED, ISSUE_SEMANTIC, ISSUE_HYBRID, REPOSITORY, USER, DISCUSSION. No hay código, commits, temas, etiquetas, wikis ni paquetes.
- Contadores: issueCount, repositoryCount, userCount, discussionCount, codeCount, wikiCount (todos limitados a 1000 resultados navegables).
- Nodos posibles: Repository, Issue, PullRequest, User, Organization, Discussion, App, MarketplaceListing.

Qué aporta:

- Discusiones (lo único que no tiene REST).
- Pedir en una sola llamada los datos relacionados que se muestran en la lista (etiquetas, estado de revisión, número de comentarios, lenguaje principal, temas, autor) sin peticiones extra.
- Gasta del cupo GraphQL (puntos por hora) y no del recurso search de REST, según la descripción de los recursos de /rate_limit. Dudoso: puede haber límites secundarios propios de búsqueda no documentados.

Qué no aporta:

- Mismo tope de 1000, misma sintaxis, sin parámetro de orden (el orden va dentro de la consulta como sort:...). Paginación solo por cursores.

## 14. Tendencias (Trending)

No hay API oficial de tendencias.

### La página github.com/trending (verificado hoy)

- Pestañas: repositorios (/trending) y desarrolladores (/trending/developers).
- Lenguaje en la ruta: /trending/python, /trending/unknown.
- since=daily, since=weekly o since=monthly.
- spoken_language_code=es (idioma hablado, código ISO 639-1).
- Cada repositorio muestra dueño y nombre, descripción, lenguaje, estrellas y bifurcaciones totales, «construido por» y estrellas ganadas en el periodo.

### Condiciones de uso

- Las Políticas de uso aceptable definen el scraping como extraer información con un proceso automático y lo distinguen de la API. Prohíben la «actividad masiva automatizada excesiva» y cargar los servidores; prohíben usar la información para spam o vender datos personales.
- Leer la página de tendencias a petición de la persona, una vez por consulta, guardando el resultado en caché (por ejemplo una hora) y sin recorrer páginas en bucle, es un uso moderado. Aun así es frágil (el HTML cambia sin aviso) y debe presentarse como función «sin API oficial; puede dejar de funcionar».

### Aproximaciones con la API oficial

- «Nuevos y populares»: created:>=FECHA sort:stars order:desc (FECHA = hoy menos 1, 7 o 30 días). Es lo más parecido; no mide estrellas ganadas, sino estrellas de repos recientes.
- «Activos y populares»: pushed:>=FECHA stars:>100 sort:stars o sort:updated.
- La velocidad real de estrellas exigiría leer stargazers con fecha (Accept application/vnd.github.star+json) repo a repo: demasiado caro.
- OSS Insight ofrecía una API de tendencias, pero su web anuncia el cierre el 4 de diciembre de 2026: no usarla.

## 15. Ideas de otros clientes y de la comunidad

### gh search (referencia excelente; verificado en el código)

- gh search repos: --archived, --created, --followers, --forks, --good-first-issues, --help-wanted-issues, --include-forks (false, true, only), --language, --license (varias), --match (name, description, readme), --number-topics, --owner (varias), --size, --stars, --topic (varias), --updated (genera pushed:), --visibility (public, private, internal), --sort (forks, help-wanted-issues, stars, updated), --order, --limit, --web, --json.
- gh search issues: --app, --archived, --assignee, --author, --closed, --commenter, --comments, --created, --include-prs, --interactions, --involves, --label, --language, --locked, --match (title, body, comments), --mentions, --milestone, --no-assignee, --no-label, --no-milestone, --no-project, --owner, --project, --reactions, --repo, --state, --team-mentions, --updated, --visibility, --search-type (lexical, semantic, hybrid), --sort (comments, created, interactions, reactions y las seis reacciones, updated).
- gh search prs: lo mismo más --base, --head, --draft, --merged, --merged-at, --review (none, required, approved, changes_requested), --review-requested, --reviewed-by, --checks (pending, success, failure).
- gh search code: --extension, --filename, --language, --match (file, path), --owner, --repo, --size.
- gh search commits: --author, --author-date, --author-email, --author-name, --committer, --committer-date, --committer-email, --committer-name, --hash, --merge, --parent, --repo, --tree, --owner, --visibility, --sort (author-date, committer-date).
- Tope interno de gh: 1000 resultados (SearchMaxResults).
- Ideas a copiar: --web (abrir en el navegador), --json (exportar), detectar si el servidor admite semántica, avisar de la sintaxis antigua en código.

### La web de GitHub

- github.com/search/advanced: formulario con secciones (avanzado, repositorios, código, issues, usuarios, wikis). Buen modelo para el diálogo guiado: dueños, repositorios, fecha de creación, lenguaje; estrellas, bifurcaciones, tamaño, fecha de envío, licencia, bifurcaciones (no, sí, solo); extensión, ruta, nombre de archivo; estado, motivo, comentarios, etiquetas, autor, menciones, asignados, actualizado antes de; nombre completo, ubicación, seguidores, repos públicos, lenguaje.
- Filtros laterales por tipo y lenguaje con recuentos, sugerencias mientras se escribe y avisos de errores en la consulta.
- Búsquedas guardadas en la barra (saved:) e historial automático; vistas guardadas en el panel de issues.
- Dirección para abrir en el navegador: https://github.com/search?q=...&type=repositories (también code, issues, pullrequests, discussions, users, commits, registrypackages, wikis, topics). Dudoso solo el valor exacto de paquetes.

### Peticiones de la comunidad que nos sirven

- Expresiones regulares en la API de código (discusiones 102615 y 9991): no existe; ofrecer abrir en la web.
- Gestionar búsquedas guardadas (discusión 53150): la web las tiene escondidas; nuestra app puede ofrecer búsquedas guardadas con nombre, editables y exportables.
- Filtrar repositorios por expresión regular en el nombre (discusión 9824): se puede hacer en local sobre los resultados.
- Pasar del tope de 1000 (hilos de PyGithub y Stack Overflow): partir por fechas.

## 16. Fuentes

- API REST de búsqueda (2026-03-10): https://docs.github.com/en/rest/search/search?apiVersion=2026-03-10
- Cambios incompatibles de la API REST: https://docs.github.com/en/rest/about-the-rest-api/breaking-changes?apiVersion=2026-03-10
- Límites de la API REST: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- Endpoint de límites: https://docs.github.com/en/rest/rate-limit/rate-limit?apiVersion=2026-03-10
- Sintaxis de búsqueda: https://docs.github.com/en/search-github/getting-started-with-searching-on-github/understanding-the-search-syntax
- Ordenar resultados: https://docs.github.com/en/search-github/getting-started-with-searching-on-github/sorting-search-results
- Acerca de buscar en GitHub: https://docs.github.com/en/search-github/getting-started-with-searching-on-github/about-searching-on-github
- Repositorios: https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories
- Issues y pull requests: https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests
- Filtrado avanzado de issues: https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/filtering-and-searching-issues-and-pull-requests
- Código (sintaxis antigua, la de REST): https://docs.github.com/en/search-github/searching-on-github/searching-code
- Código (sintaxis nueva de la web): https://docs.github.com/en/search-github/github-code-search/understanding-github-code-search-syntax
- Usuarios: https://docs.github.com/en/search-github/searching-on-github/searching-users
- Commits: https://docs.github.com/en/search-github/searching-on-github/searching-commits
- Temas: https://docs.github.com/en/search-github/searching-on-github/searching-topics
- Discusiones: https://docs.github.com/en/search-github/searching-on-github/searching-discussions
- Wikis: https://docs.github.com/en/search-github/searching-on-github/searching-wikis
- Paquetes: https://docs.github.com/en/search-github/searching-on-github/searching-for-packages
- GraphQL search: https://docs.github.com/en/graphql/reference/search
- Anuncio de búsqueda avanzada en la API (marzo de 2025): https://github.blog/changelog/2025-03-06-github-issues-projects-api-support-for-issues-advanced-search-and-more/
- Anuncio de búsqueda semántica e híbrida (abril de 2026): https://github.blog/changelog/2026-04-02-improved-search-for-github-issues-is-now-generally-available/
- Anuncio de dependencias entre issues (agosto de 2025): https://github.blog/changelog/2025-08-21-dependencies-on-issues/
- Anuncio de sub-issues y filtros has:/no: (diciembre de 2024): https://github.blog/changelog/2024-12-12-github-issues-projects-close-issue-as-a-duplicate-rest-api-for-sub-issues-and-more/
- Formulario de búsqueda avanzada: https://github.com/search/advanced
- Tendencias: https://github.com/trending
- Políticas de uso aceptable: https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies
- Regex no disponible en la API: https://github.com/orgs/community/discussions/102615
- Búsquedas guardadas: https://github.com/orgs/community/discussions/53150
- Filtrar repos por regex: https://github.com/orgs/community/discussions/9824
- Partir por fechas (PyGithub): https://github.com/PyGithub/PyGithub/issues/824
- OSS Insight (cierra el 4 de diciembre de 2026): https://ossinsight.io/docs/api/list-trending-repos
- Código de gh: D:\Antigravity\GithubAccesible\adjuntos\repos\cli_cli\pkg\cmd\search y pkg\search (query.go, searcher.go)
