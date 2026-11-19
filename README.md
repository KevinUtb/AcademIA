# AcademIA — Prototipo funcional

Gestor inteligente de tareas y entregas (proyecto final de Inteligencia Artificial).
Implementa el ciclo **percibir → decidir → actuar** y la función de prioridad de la Fase 2.

## Requisitos

- Python 3.10 o superior (probado con 3.15).
- Streamlit (única dependencia de la aplicación).

## Ejecución

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Streamlit abre la aplicación en `http://localhost:8501`.

1. Pulsa **Cargar caso de demostración** en la barra lateral para reproducir el caso A, C, B.
2. Ajusta las **horas libres por día** (por defecto 6 h) para ver cómo cambia el reparto de bloques.
3. Marca tareas como hechas o cambia sus fechas en **Mis tareas**: el plan y las alertas se recalculan.

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest -q
```

Las pruebas cubren el caso de demostración (orden A, C, B y puntajes 0,804 / 0,781 / 0,481),
las validaciones de la percepción, la alerta de 48 horas, la exclusión de tareas hechas y el
reparto de horas libres.

## Estructura

| Archivo | Contenido |
|---|---|
| `app.py` | Lógica pura del agente + interfaz Streamlit en un solo archivo |
| `test_app.py` | Pruebas unitarias con pytest |
| `DOCUMENTO_FINAL.md` | Documento académico de la entrega |
| `requirements.txt` | Dependencia de la aplicación |
| `requirements-dev.txt` | Dependencias para ejecutar las pruebas |

## Dónde ajustar el agente

En `app.py`, sección **1. Constantes del agente**: pesos (`PESO_URGENCIA`, `PESO_DIFICULTAD`,
`PESO_TIEMPO`), horizonte de 336 h, umbral de alerta de 48 h, rango de horas y días de planificación.
