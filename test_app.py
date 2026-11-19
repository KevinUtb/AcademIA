"""
Pruebas del agente AcademIA (logica pura, sin Streamlit).

Ejecucion:
    pip install -r requirements-dev.txt
    pytest -q
"""

from datetime import date, datetime, timedelta

import pytest

from app import (
    crear_caso_demostracion,
    generar_alertas,
    percibir,
    planificar,
)

# Fecha fija para que las pruebas sean deterministas (lunes 4 de mayo de 2026).
AHORA = datetime(2026, 5, 4, 10, 0)


def _plan_demo(horas_libres=6.0):
    tareas = crear_caso_demostracion(AHORA)
    return tareas, planificar(tareas, AHORA, [horas_libres] * 7)


def test_caso_demostracion_produce_el_orden_y_los_puntajes_de_la_fase_2():
    """A (24 h) debe quedar 1.º, C (40 h) 2.º y B (120 h) 3.º."""
    _, plan = _plan_demo()

    assert [e["nombre"] for e in plan] == [
        "Taller de búsqueda",
        "Informe de laboratorio",
        "Ensayo de ética",
    ]
    assert [e["puntaje"] for e in plan] == [0.804, 0.781, 0.481]

    # El desglose debe ser el que se muestra en el documento.
    assert plan[0]["urgencia"] == 0.9286
    assert plan[1]["urgencia"] == 0.8810
    assert plan[2]["urgencia"] == 0.6429

    # La planificacion marca las tareas que vencen en menos de 48 h.
    assert [e["urgente_48h"] for e in plan] == [True, True, False]


def test_percibir_rechaza_campos_vacios():
    tarea, errores = percibir("", "   ", None, 3, 2.0, AHORA)

    assert tarea is None
    assert any("nombre" in e and "obligatorio" in e for e in errores)
    assert any("materia" in e for e in errores)
    assert any("fecha" in e for e in errores)


@pytest.mark.parametrize(
    "dificultad, horas, mensaje",
    [
        (0, 2.0, "dificultad"),
        (6, 2.0, "dificultad"),
        (3, 0, "horas"),
        (3, -4, "horas"),
        (3, 150, "horas"),
    ],
)
def test_percibir_rechaza_valores_fuera_de_rango(dificultad, horas, mensaje):
    _, errores = percibir(
        "Taller", "Inteligencia Artificial", AHORA + timedelta(days=1),
        dificultad, horas, AHORA,
    )

    assert any(mensaje in e for e in errores)


def test_percibir_rechaza_fecha_pasada_y_acepta_datos_validos():
    _, errores = percibir(
        "Taller", "Inteligencia Artificial", AHORA - timedelta(minutes=1),
        4, 5.0, AHORA,
    )
    assert any("posterior" in e for e in errores)

    tarea, errores = percibir(
        "  Taller de búsqueda  ", "  Inteligencia Artificial  ",
        AHORA + timedelta(hours=24), 4, 5.0, AHORA,
    )
    assert errores == []
    assert tarea is not None
    assert tarea.nombre == "Taller de búsqueda"  # se eliminan espacios sobrantes
    assert tarea.estado == "pendiente"


def test_alertas_de_48_horas_y_retroalimentacion():
    tareas, plan = _plan_demo()

    alertas = generar_alertas(tareas, AHORA, plan)
    assert "Tienes 2 tareas que vencen en menos de 48 horas." in alertas
    assert any("Taller de búsqueda" in a and "vence en 24,0 h" in a for a in alertas)

    # Retroalimentacion: al marcar A como hecha, la alerta cambia.
    tareas[0].estado = "hecha"
    alertas = generar_alertas(tareas, AHORA, planificar(tareas, AHORA, [6.0] * 7))
    assert "Tienes 2 tareas que vencen en menos de 48 horas." not in alertas
    assert any(a.startswith("Tienes 1 tarea que vence en menos de 48 horas")
               for a in alertas)


def test_planificar_reparte_horas_libres_excluye_hechas_y_avisa_faltantes():
    tareas, plan = _plan_demo()

    # A (5 h) ocupa las 5 h libres del lunes; C y B caben en los dias siguientes.
    assert plan[0]["bloques"] == [{"fecha": date(2026, 5, 4), "horas": 5.0}]
    assert plan[0]["horas_sin_asignar"] == 0
    assert sum(b["horas"] for b in plan[1]["bloques"]) == 8.0
    assert all(e["horas_sin_asignar"] == 0 for e in plan)

    # Una tarea hecha no se planifica ni genera alertas de urgencia.
    tareas[0].estado = "hecha"
    plan_hechas = planificar(tareas, AHORA, [6.0] * 7)
    assert len(plan_hechas) == 2
    assert all(e["nombre"] != "Taller de búsqueda" for e in plan_hechas)

    # Sin horas libres, la planificacion reporta las horas sin asignar.
    sin_capacidad = planificar(tareas, AHORA, [0.0] * 7)
    assert sin_capacidad[0]["bloques"] == []
    assert sin_capacidad[0]["horas_sin_asignar"] == 8.0
    assert any(
        "No hay horas libres suficientes" in a
        for a in generar_alertas(tareas, AHORA, sin_capacidad)
    )
