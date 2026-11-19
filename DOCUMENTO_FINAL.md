# AcademIA: gestor inteligente de tareas y entregas

**Documento final — Proyecto final de Inteligencia Artificial**

Juan Malambo · Kevin Acuña · Camilo Jiménez · Rafael Quintana

2026

---

## Resumen

AcademIA es un agente de software que ayuda a un estudiante a decidir qué tarea académica hacer primero. Recibe tareas con fecha límite, dificultad y tiempo estimado; valida los datos; calcula un puntaje de prioridad con una función de utilidad; ordena las tareas y reparte bloques de estudio según las horas libres disponibles; finalmente muestra el plan y alertas de vencimiento. El prototipo se implementó en Python con Streamlit, sin servicios externos ni IA generativa, y reproduce el caso de la Fase 2: las tareas A, C y B obtienen puntajes 0,804, 0,781 y 0,481, en ese orden, con la alerta «Tienes 2 tareas que vencen en menos de 48 horas».

## 1. Problema y usuario

El problema que aborda AcademIA no es la falta de capacidad del estudiante, sino la dificultad de decidir. Cuando varias materias coinciden en la misma semana, el estudiante debe comparar plazos, dificultad y carga de trabajo sin un criterio estable; la comparación se hace de memoria, bajo estrés y con información incompleta. El resultado típico son entregas tardías, trabajos de menor calidad y tiempo dedicado a tareas que no eran las más apremiantes.

El usuario es un estudiante universitario con varias materias activas y entregas parciales. El contexto de uso es la planificación semanal: el estudiante registra sus tareas al inicio de la semana (o cuando las recibe) y consulta el plan antes de decidir en qué trabajar. AcademIA no reemplaza la decisión del estudiante: la hace explícita, trazable y fácil de revisar.

El alcance corresponde a la Opción 2 de la Fase 2: un prototipo funcional que trabaja con los datos que el estudiante escribe, sin conectarse a plataformas externas ni usar IA generativa. Esta delimitación es deliberada: permite verificar cada cálculo y explicar por qué el agente propone un orden determinado.

## 2. Percepción

### 2.1 Entradas y origen de los datos

| Dato | Origen | Tipo y rango | Uso en el agente |
|---|---|---|---|
| Nombre de la tarea | Formulario | Texto no vacío | Identificación en el plan y las alertas |
| Materia | Formulario | Texto no vacío | Contexto para el estudiante |
| Fecha y hora límite | Formulario | Fecha futura | Cálculo de horas restantes y urgencia |
| Dificultad | Formulario | Entero de 1 a 5 | Factor de dificultad |
| Horas estimadas | Formulario | Número entre 0,5 y 100 | Factor de tiempo y reparto de bloques |
| Fecha y hora actual | Reloj del sistema | `datetime.now()` | Referencia para urgencia y alertas |
| Horas libres por día | Barra lateral | Número entre 0 y 12 | Capacidad del plan (7 días) |
| Estado de la tarea | Casilla «Tarea hecha» | Pendiente / hecha | Exclusión del plan y de las alertas |

### 2.2 Validación y normalización

La percepción no se limita a leer el formulario: comprueba que la información sea utilizable. La función `percibir()` rechaza campos vacíos o compuestos solo por espacios, fechas límite anteriores o iguales al instante actual, dificultades fuera de 1–5 y horas estimadas fuera de 0,5–100. Los textos se normalizan con `strip()` y la tarea se crea únicamente si no hay errores. Así se evita que un dato incoherente produzca un plan que parezca válido.

Cada factor se lleva a una escala común de 0 a 1 para que los pesos sean comparables:

- **Urgencia** = max(0, 1 − horas restantes / 336). El horizonte es de 14 días (336 h). Una tarea que vence en el acto tiene urgencia 1; una que vence en 14 días o más tiene urgencia 0. Una tarea vencida se acota a 1.
- **Dificultad** = nivel / 5. Convierte la escala 1–5 en 0,2–1,0.
- **Tiempo** = min(1, horas estimadas / 10). Una tarea de 10 h o más recibe el valor máximo.

La urgencia se conserva con cuatro decimales y el puntaje final se redondea a tres con redondeo *half-up* (mitad hacia arriba). Esta convención no cambia el orden; permite que el desglose que ve el estudiante coincida con el puntaje mostrado, requisito de explicabilidad del agente.

## 3. Decisión y acción

### 3.1 Arquitectura

AcademIA conserva el ciclo de la Fase 2:

```text
ENTORNO: estudiante, tareas, materias y calendario
   │  percepciones (formulario + reloj del sistema)
   ▼
PERCEPCIÓN: percibir()  →  validación y normalización
   ▼
MEMORIA / ESTADO: tareas, estado, fecha y hora, horas libres por día
   ▼
RAZONAMIENTO: calcular_prioridad()  →  urgencia, dificultad, tiempo, puntaje
   ▼
PLANIFICACIÓN: planificar()  →  orden, bloques de estudio, tareas < 48 h
   ▼
ACCIÓN: plan ordenado + generar_alertas()
   ▲
   └── RETROALIMENTACIÓN: marcar hecha / cambiar fecha → recalcular
```

La lógica del agente está separada de la interfaz en funciones puras (`percibir`, `calcular_prioridad`, `planificar`, `generar_alertas`). Esto permite probarla con pytest y explicar cada paso sin depender de la pantalla.

### 3.2 Función de utilidad

La decisión se basa en la función de prioridad propuesta en la Fase 2:

**Prioridad = 0,50 × Urgencia + 0,30 × Dificultad + 0,20 × Tiempo**

Los pesos suman 1, de modo que el puntaje también queda en [0, 1]. Son constantes ajustables en `app.py` (`PESO_URGENCIA`, `PESO_DIFICULTAD`, `PESO_TIEMPO`). El agente elige como primera acción la tarea con mayor puntaje; ante empates desempata por fecha límite y luego por nombre, para que el resultado sea determinista y reproducible.

La utilidad no es una medida objetiva del valor académico: es una estimación de conveniencia con la información disponible. Por eso el sistema muestra el desglose de cada puntaje y presenta el plan como recomendación.

### 3.3 Planificación

`planificar()` ejecuta cuatro pasos:

1. Filtra las tareas pendientes (las hechas no consumen tiempo).
2. Calcula el puntaje de cada una y las ordena de mayor a menor.
3. Recorre la lista y asigna horas de estudio desde el día actual, compartiendo la capacidad diaria entre todas las tareas. Un día solo puede recibir bloques si su fecha es anterior o igual a la fecha límite de la tarea.
4. Registra las horas que no pudieron asignarse antes del vencimiento.

Con *n* tareas y un horizonte fijo de 7 días, el costo dominante es el ordenamiento: O(*n* log *n*). El reparto es lineal en *n* × 7. Para el tamaño del problema (decenas de tareas) no se requiere una búsqueda más compleja; como señala la Fase 2, ordenar por puntaje es suficiente.

### 3.4 Acción verificable

El agente ejecuta dos acciones observables en la interfaz:

- **Plan de estudio:** tabla ordenada con tarea, materia, horas restantes, factores, puntaje y el desglose aritmético. Cada tarea muestra además los bloques asignados por día. Las tareas que vencen en menos de 48 h se marcan con ⚠ en la columna «Vence en».
- **Alertas:** mensajes de urgencia. La regla es explícita: si una tarea pendiente vence en menos de 48 h, se cuenta y se emite «Tienes N tareas que vencen en menos de 48 horas». También se alerta sobre tareas vencidas y sobre horas que no alcanzan antes de una fecha límite.

Ambas acciones son verificables: el estudiante puede recalcular el puntaje con los factores mostrados y comprobar las sumas de horas contra la capacidad configurada.

### 3.5 Tipo de agente y tabla PEAS

AcademIA es un **agente basado en utilidad, con modelo del entorno y objetivos**, y sin aprendizaje en esta versión. La memoria mantiene el modelo (tareas y estados); el objetivo es completar las entregas; la utilidad permite comparar alternativas. Es coherente con la clasificación de Russell y Norvig (2020): el agente elige la acción que maximiza el resultado esperado según su función de utilidad y la información disponible, no una acción óptima en sentido absoluto.

| Elemento | AcademIA |
|---|---|
| **P – Medida de desempeño** | Entregas a tiempo, tareas urgentes atendidas primero, plan que el estudiante considera útil y alertas oportunas |
| **E – Entorno** | Estudiante, tareas, materias y calendario académico; parcialmente observable (solo ve lo registrado) y cambiante en el tiempo |
| **A – Actuadores** | Plan de estudio ordenado y alertas de urgencia en la interfaz |
| **S – Sensores** | Formulario de captura de tareas y fecha y hora actual del sistema |

## 4. Caso completo

### 4.1 Situación inicial y entradas

Es lunes a las 10:00. El estudiante dispone de 6 horas libres por día y registra tres tareas:

| Tarea | Materia | Horas restantes | Dificultad | Horas estimadas |
|---|---|---|---|---|
| A: Taller de búsqueda | Inteligencia Artificial | 24 | 4 | 5 h |
| C: Informe de laboratorio | Bases de Datos | 40 | 3 | 8 h |
| B: Ensayo de ética | Ética Profesional | 120 | 2 | 2 h |

La fecha y hora límite se generan desde el instante de carga (`ahora + 24 h`, `ahora + 40 h`, `ahora + 120 h`), por lo que las horas restantes son exactamente las del caso de la Fase 2. El botón **Cargar caso de demostración** crea estas tres tareas en la memoria.

### 4.2 Cálculo paso a paso

**Paso 1. Urgencia** (horizonte 336 h, cuatro decimales):

- A: 1 − 24/336 = 0,928571 → **0,9286**
- C: 1 − 40/336 = 0,880952 → **0,8810**
- B: 1 − 120/336 = 0,642857 → **0,6429**

**Paso 2. Dificultad y tiempo:**

| Tarea | Dificultad = nivel/5 | Tiempo = min(1, horas/10) |
|---|---|---|
| A | 4/5 = 0,80 | 5/10 = 0,50 |
| C | 3/5 = 0,60 | 8/10 = 0,80 |
| B | 2/5 = 0,40 | 2/10 = 0,20 |

**Paso 3. Puntaje** (se conserva precisión completa en los productos y se redondea el total):

| Tarea | 0,50 × Urgencia | 0,30 × Dificultad | 0,20 × Tiempo | Suma | Puntaje |
|---|---|---|---|---|---|
| A | 0,4643 | 0,2400 | 0,1000 | 0,8043 | **0,804** |
| C | 0,4405 | 0,1800 | 0,1600 | 0,7805 | **0,781** |
| B | 0,32145 | 0,1200 | 0,0400 | 0,48145 | **0,481** |

**Paso 4. Decisión:** el orden es **A (0,804) → C (0,781) → B (0,481)**. El agente decide trabajar primero en A, luego en C y finalmente en B.

### 4.3 Plan y alertas

Con 6 h libres por día, una ejecución de referencia a las 10:00 produce este reparto:

| Tarea | Día 1 | Día 2 | Día 3 | Total asignado |
|---|---|---|---|---|
| A | 5 h | — | — | 5 h |
| C | 1 h | 6 h | 1 h | 8 h |
| B | — | — | 2 h | 2 h |
| **Ocupación** | **6 h** | **6 h** | **3 h** | **15 h** |

La capacidad se comparte: el día 1 queda completo con A y 1 h de C; el día 2 se dedica a C; el día 3 recibe la última hora de C y las 2 h de B. No hay horas sin asignar. Si la aplicación se ejecuta en otro horario, los bloques pueden desplazarse porque la elegibilidad se evalúa por día calendario; el orden y los puntajes a tres decimales se mantienen. Muy cerca de la medianoche, la ventana efectiva antes de la fecha límite de C puede reducirse y el agente añadiría una alerta de horas sin asignar, comportamiento coherente con el modelo de capacidad por día.

Las alertas generadas son:

- «Tienes 2 tareas que vencen en menos de 48 horas.»
- «Taller de búsqueda» vence en 24,0 h.
- «Informe de laboratorio» vence en 40,0 h.

### 4.4 Resultado y retroalimentación

El estudiante ve el plan A, C, B con el desglose de cada puntaje, los bloques por día y las alertas de urgencia. Si marca A como hecha, A sale del plan y de las alertas; quedan C y B, y la alerta pasa a `Tienes 1 tarea que vence en menos de 48 horas: «Informe de laboratorio» (en 40,0 h).` Si cambia la fecha de C, su urgencia disminuye y el puntaje se recalcula; el plan se reordena si corresponde. Estos cambios se reflejan en la misma sesión porque la memoria (`st.session_state`) y el cálculo se actualizan en cada interacción.

## 5. Limitaciones, sesgos y mejoras futuras

**Limitaciones de la versión actual**

- La calidad del plan depende de las estimaciones del estudiante: una dificultad o un tiempo mal estimados producen una prioridad equivocada.
- Los pesos son una decisión de diseño, no un parámetro aprendido. El horizonte de 14 días y el umbral de 48 h también son fijos.
- El reparto trabaja con días completos y capacidad uniforme; no modela franjas horarias, energía ni interrupciones.
- El agente solo conoce lo registrado. No ve el calendario institucional, el peso de cada entrega en la nota ni compromisos externos (trabajo, transporte, salud).
- La memoria vive en la sesión del navegador: no hay persistencia entre sesiones ni soporte multiusuario.
- No hay aprendizaje: no corrige estimaciones con el historial real.

**Sesgos posibles**

- **Urgencia sobre importancia académica:** el 50 % del peso favorece lo que vence pronto, aunque una entrega con mayor peso en la nota merezca más atención.
- **Dependencia de la autoestima académica:** la dificultad es autoevaluada; estudiantes con exceso de confianza o ansiedad pueden subestimarla o sobreestimarla.
- **Sesgo hacia tareas largas:** el factor tiempo premia tareas de muchas horas, que no siempre son las más valiosas.
- **Sesgo de registro:** lo que no se escribe no existe para el agente; las tareas no registradas quedan invisibles.
- **Falsa precisión:** mostrar tres decimales puede sugerir una exactitud que los datos de entrada no tienen. El desglose y la advertencia de que el plan es una recomendación mitigan este efecto.

**Mejoras futuras**

- **Aprendizaje automático:** estimar horas y dificultad a partir del historial del estudiante y ajustar los pesos con resultados reales (por ejemplo, entregas a tiempo y tiempo efectivo dedicado).
- **Ontología:** modelar formalmente Estudiante, Materia, Tarea, Entrega y relaciones como *pertenece a*, *vence en* y *requiere*, para razonar sobre prerrequisitos y pesos académicos.
- **Prolog:** expresar las reglas de alerta y sobrecarga como cláusulas verificables (por ejemplo, `alerta(T) :- vence_en(T, H), H < 48`), lo que facilitaría auditar el razonamiento.
- **Calendario y peso de la nota:** incorporar el calendario institucional y el porcentaje de cada entrega, manteniendo la explicabilidad.
- **Análisis de sensibilidad:** mostrar cómo cambia el orden al modificar los pesos, para que el estudiante entienda que la prioridad es una recomendación.

## Referencias

Russell, S. y Norvig, P. (2020). *Artificial Intelligence: A Modern Approach* (4.ª ed.). Pearson.

Malambo, J., Acuña, K., Jiménez, C. y Quintana, R. (2026). *AcademIA: Fase 2 — Justificación y diagrama de arquitectura*. Documento interno del curso de Inteligencia Artificial.

## Anexo A. Reproducibilidad

La aplicación se ejecuta con `streamlit run app.py` después de instalar `requirements.txt` (su única dependencia es Streamlit; pytest se usa solo para las pruebas). Las pruebas se ejecutan con `pytest -q` e incluyen:

1. El caso de demostración produce el orden A, C, B y los puntajes 0,804 / 0,781 / 0,481.
2. La percepción rechaza campos vacíos.
3. La percepción rechaza dificultad y horas fuera de rango.
4. La percepción rechaza fechas pasadas y acepta datos válidos (con normalización de espacios).
5. La alerta de 48 h cambia con la retroalimentación, las tareas hechas se excluyen y se reportan las horas sin asignar.

Resultado esperado: `10 passed`.
