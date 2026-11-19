"""
AcademIA - Gestor inteligente de tareas y entregas
Prototipo funcional - Proyecto final de Inteligencia Artificial

Arquitectura (coherente con la Fase 2):
    percibir -> memoria/estado -> razonar (función de utilidad) -> planificar
    -> actuar (plan ordenado + alertas) -> retroalimentación del estudiante.

El archivo se divide en dos bloques:
  1. Lógica pura del agente (sin Streamlit): Tarea, percibir, calcular_prioridad,
     planificar, generar_alertas y utilidades de formato. Se puede importar y
     probar con pytest sin levantar la interfaz.
  2. Interfaz Streamlit: main().

Ejecución:  streamlit run app.py
Pruebas:    pytest -q
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

try:  # La logica pura no depende de Streamlit; la interfaz si.
    import streamlit as st
except ModuleNotFoundError:  # permite ejecutar las pruebas sin instalar Streamlit
    st = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 1. CONSTANTES DEL AGENTE (pesos y parámetros configurables)
# ---------------------------------------------------------------------------

# Pesos de la función de utilidad. Deben sumar 1.0.
PESO_URGENCIA = 0.50
PESO_DIFICULTAD = 0.30
PESO_TIEMPO = 0.20
PESOS = (PESO_URGENCIA, PESO_DIFICULTAD, PESO_TIEMPO)

HORIZONTE_HORAS = 336.0      # 14 días: a partir de aquí la urgencia es 0
HORAS_MAX_TIEMPO = 10.0      # 10 h o más => tiempo normalizado = 1
UMBRAL_ALERTA_HORAS = 48.0   # regla: alerta si vence en menos de 48 h

DIFICULTAD_MIN = 1
DIFICULTAD_MAX = 5
HORAS_ESTIMADAS_MIN = 0.5
HORAS_ESTIMADAS_MAX = 100.0

DIAS_PLAN = 7                # horizonte de planificación en días
HORAS_LIBRES_POR_DEFECTO = 6.0

# Precisión del cálculo: la urgencia se conserva con 4 decimales para que el
# desglose mostrado coincida con el puntaje final (explicabilidad).
DECIMALES_URGENCIA = 4
DECIMALES_PUNTAJE = 3


# ---------------------------------------------------------------------------
# 2. LÓGICA PURA DEL AGENTE
# ---------------------------------------------------------------------------

@dataclass
class Tarea:
    """Representación de una tarea en la memoria del agente."""
    id: int
    nombre: str
    materia: str
    fecha_limite: datetime
    dificultad: int
    horas_estimadas: float
    estado: str = "pendiente"

    def esta_pendiente(self) -> bool:
        return self.estado == "pendiente"


def _redondear(valor: float, decimales: int) -> float:
    """Redondeo half-up (mitad hacia arriba) para que el desglose sea verificable."""
    if not math.isfinite(valor):
        return valor
    cuantizador = Decimal(1).scaleb(-decimales)
    return float(Decimal(str(valor)).quantize(cuantizador, rounding=ROUND_HALF_UP))


def percibir(
    nombre: str,
    materia: str,
    fecha_limite: Optional[datetime],
    dificultad: object,
    horas_estimadas: object,
    ahora: datetime,
) -> tuple[Optional[Tarea], list[str]]:
    """
    Sensor del agente: valida y normaliza los datos del formulario.

    Devuelve (Tarea, []) si los datos son coherentes o (None, errores) si no.
    La tarea se crea con id=0; la interfaz asigna el identificador definitivo.
    """
    errores: list[str] = []

    nombre_limpio = (nombre or "").strip()
    materia_limpia = (materia or "").strip()
    if not nombre_limpio:
        errores.append("El nombre de la tarea es obligatorio.")
    if not materia_limpia:
        errores.append("La materia es obligatoria.")

    if not isinstance(fecha_limite, datetime):
        errores.append("La fecha y hora límite son obligatorias.")
    elif fecha_limite <= ahora:
        errores.append("La fecha límite debe ser posterior a la fecha y hora actual.")

    if isinstance(dificultad, bool) or not isinstance(dificultad, int):
        errores.append("La dificultad debe ser un número entero entre 1 y 5.")
    elif not (DIFICULTAD_MIN <= dificultad <= DIFICULTAD_MAX):
        errores.append(
            f"La dificultad debe estar entre {DIFICULTAD_MIN} y {DIFICULTAD_MAX}."
        )

    horas: Optional[float]
    try:
        horas = float(horas_estimadas)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        horas = None
        errores.append("Las horas estimadas deben ser un número.")

    if horas is not None:
        if not math.isfinite(horas) or horas <= 0:
            errores.append("Las horas estimadas deben ser mayores que 0.")
        elif horas > HORAS_ESTIMADAS_MAX:
            errores.append(
                f"Las horas estimadas no pueden superar {HORAS_ESTIMADAS_MAX:.0f} h."
            )

    if errores:
        return None, errores

    tarea = Tarea(
        id=0,
        nombre=nombre_limpio,
        materia=materia_limpia,
        fecha_limite=fecha_limite,  # type: ignore[arg-type]
        dificultad=int(dificultad),  # type: ignore[arg-type]
        horas_estimadas=float(horas),  # type: ignore[arg-type]
        estado="pendiente",
    )
    return tarea, []


def calcular_prioridad(
    tarea: Tarea,
    ahora: datetime,
    pesos: tuple[float, float, float] = PESOS,
) -> dict:
    """
    Razonamiento del agente: función de utilidad de la Fase 2.

        Prioridad = 0,50 * Urgencia + 0,30 * Dificultad + 0,20 * Tiempo
        Urgencia  = max(0, 1 - horas_restantes / 336)
        Dificultad= nivel / 5
        Tiempo    = min(1, horas_estimadas / 10)

    Devuelve un diccionario explicable con los factores normalizados.
    """
    horas_restantes = (tarea.fecha_limite - ahora).total_seconds() / 3600.0

    # Se acota a [0, 1]: una tarea vencida tiene urgencia maxima (1.0).
    urgencia = min(1.0, max(0.0, 1.0 - horas_restantes / HORIZONTE_HORAS))
    urgencia = _redondear(urgencia, DECIMALES_URGENCIA)

    dificultad_n = tarea.dificultad / DIFICULTAD_MAX
    tiempo_n = min(1.0, tarea.horas_estimadas / HORAS_MAX_TIEMPO)

    peso_u, peso_d, peso_t = pesos
    puntaje = _redondear(
        peso_u * urgencia + peso_d * dificultad_n + peso_t * tiempo_n,
        DECIMALES_PUNTAJE,
    )

    return {
        "tarea": tarea,
        "id": tarea.id,
        "nombre": tarea.nombre,
        "materia": tarea.materia,
        "fecha_limite": tarea.fecha_limite,
        "dificultad": tarea.dificultad,
        "horas_estimadas": tarea.horas_estimadas,
        "horas_restantes": _redondear(horas_restantes, 2),
        "urgencia": urgencia,
        "dificultad_n": dificultad_n,
        "tiempo_n": tiempo_n,
        "puntaje": puntaje,
        "estado": tarea.estado,
    }


def planificar(
    tareas: list[Tarea],
    ahora: datetime,
    horas_libres_por_dia: list[float],
    pesos: tuple[float, float, float] = PESOS,
    dias: int = DIAS_PLAN,
) -> list[dict]:
    """
    Planificación: ordena por puntaje descendente y reparte bloques de estudio
    entre los días con horas libres.

    Reglas:
      * Solo se planifican tareas pendientes.
      * La capacidad de cada día se comparte entre tareas (no se sobreasigna).
      * Un día solo admite bloques si su fecha es anterior o igual a la fecha
        límite de la tarea (a nivel de día calendario).
      * Si no alcanza la capacidad, la diferencia queda como "horas_sin_asignar".

    Devuelve la lista ordenada de evaluaciones; cada una incluye "bloques"
    (lista de {fecha, horas}) y "horas_sin_asignar".
    """
    pendientes = [t for t in tareas if t.esta_pendiente()]
    evaluadas = [calcular_prioridad(t, ahora, pesos) for t in pendientes]

    # Orden determinista: puntaje, luego fecha límite y nombre.
    evaluadas.sort(
        key=lambda e: (-e["puntaje"], e["fecha_limite"], e["nombre"].lower())
    )

    capacidad = [max(0.0, float(h)) for h in list(horas_libres_por_dia)[:dias]]
    while len(capacidad) < dias:
        capacidad.append(0.0)

    for entrada in evaluadas:
        tarea: Tarea = entrada["tarea"]
        fecha_tope = tarea.fecha_limite.date()
        restante = float(tarea.horas_estimadas)
        bloques: list[dict] = []

        for indice_dia, disponible in enumerate(capacidad):
            if restante <= 1e-9:
                break
            dia = (ahora + timedelta(days=indice_dia)).date()
            if dia > fecha_tope:
                break  # ya no hay días hábiles antes del vencimiento
            if disponible <= 1e-9:
                continue
            asignar = min(disponible, restante)
            bloques.append({"fecha": dia, "horas": _redondear(asignar, 2)})
            capacidad[indice_dia] = disponible - asignar
            restante -= asignar

        entrada["bloques"] = bloques
        entrada["horas_sin_asignar"] = _redondear(max(0.0, restante), 2)
        # La planificación también marca las tareas que vencen en menos de 48 h.
        horas_restantes = (tarea.fecha_limite - ahora).total_seconds() / 3600.0
        entrada["urgente_48h"] = 0 < horas_restantes <= UMBRAL_ALERTA_HORAS

    return evaluadas


def generar_alertas(
    tareas: list[Tarea],
    ahora: datetime,
    plan: Optional[list[dict]] = None,
) -> list[str]:
    """
    Acción del agente: construye los mensajes de alerta.

    La regla principal de la Fase 2 se mantiene literal:
    «Tienes N tareas que vencen en menos de 48 horas».
    """
    alertas: list[str] = []
    pendientes = [t for t in tareas if t.esta_pendiente()]

    if not pendientes:
        return ["No tienes tareas pendientes: el plan está al día."]

    vencidas = [t for t in pendientes if t.fecha_limite <= ahora]
    if vencidas:
        if len(vencidas) == 1:
            alertas.append("Tienes 1 tarea vencida sin completar.")
        else:
            alertas.append(f"Tienes {len(vencidas)} tareas vencidas sin completar.")
        for t in vencidas:
            alertas.append(
                f"«{t.nombre}» venció el {t.fecha_limite:%d/%m/%Y %H:%M}."
            )

    criticas = [
        t
        for t in pendientes
        if 0 < (t.fecha_limite - ahora).total_seconds() <= UMBRAL_ALERTA_HORAS * 3600
    ]

    if len(criticas) == 1:
        horas = (criticas[0].fecha_limite - ahora).total_seconds() / 3600.0
        alertas.append(
            "Tienes 1 tarea que vence en menos de 48 horas: "
            f"«{criticas[0].nombre}» (en {_formato_numero(horas, 1)} h)."
        )
    elif len(criticas) > 1:
        alertas.append(
            f"Tienes {len(criticas)} tareas que vencen en menos de 48 horas."
        )
        for t in criticas:
            horas = (t.fecha_limite - ahora).total_seconds() / 3600.0
            alertas.append(
                f"«{t.nombre}» vence en {_formato_numero(horas, 1)} h."
            )
    elif not vencidas:
        alertas.append("Ninguna tarea vence en menos de 48 horas.")

    if plan:
        for entrada in plan:
            if entrada["horas_sin_asignar"] > 0:
                alertas.append(
                    "No hay horas libres suficientes antes de la fecha límite de "
                    f"«{entrada['nombre']}»: quedan "
                    f"{_formato_numero(entrada['horas_sin_asignar'], 1)} h sin asignar."
                )

    return alertas


def crear_caso_demostracion(ahora: datetime) -> list[Tarea]:
    """
    Caso de la Fase 2: A (24 h, dif. 4, 5 h), C (40 h, dif. 3, 8 h) y
    B (120 h, dif. 2, 2 h). Las fechas se calculan desde `ahora` para que
    las horas restantes sean exactamente 24, 40 y 120.
    """
    base = ahora.replace(second=0, microsecond=0)
    especificaciones = [
        # (nombre, materia, horas_restantes, dificultad, horas_estimadas)
        ("Taller de búsqueda", "Inteligencia Artificial", 24, 4, 5.0),   # A
        ("Informe de laboratorio", "Bases de Datos", 40, 3, 8.0),        # C
        ("Ensayo de ética", "Ética Profesional", 120, 2, 2.0),           # B
    ]
    return [
        Tarea(
            id=indice,
            nombre=nombre,
            materia=materia,
            fecha_limite=base + timedelta(hours=horas),
            dificultad=dificultad,
            horas_estimadas=estimadas,
        )
        for indice, (nombre, materia, horas, dificultad, estimadas)
        in enumerate(especificaciones, start=1)
    ]


# ---------------------------------------------------------------------------
# 3. UTILIDADES DE FORMATO (español: coma decimal)
# ---------------------------------------------------------------------------

def _formato_numero(valor: float, decimales: int) -> str:
    return f"{valor:.{decimales}f}".replace(".", ",")


def _desglose_texto(entrada: dict) -> str:
    """Expresión verificable del puntaje, con los factores normalizados."""
    return (
        f"0,50×{_formato_numero(entrada['urgencia'], 4)}"
        f" + 0,30×{_formato_numero(entrada['dificultad_n'], 2)}"
        f" + 0,20×{_formato_numero(entrada['tiempo_n'], 2)}"
        f" = **{_formato_numero(entrada['puntaje'], 3)}**"
    )


_DIAS_SEMANA = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def _dia_texto(dia: date) -> str:
    return f"{_DIAS_SEMANA[dia.weekday()]} {dia:%d/%m}"


def _horas_restantes_texto(horas: float) -> str:
    if horas < 0:
        return f"vencida ({_formato_numero(abs(horas), 1)} h)"
    return f"{_formato_numero(horas, 1)} h"


def _tabla_markdown(encabezados: list[str], filas: list[list[str]]) -> str:
    lineas = [
        "| " + " | ".join(encabezados) + " |",
        "|" + "|".join(["---"] * len(encabezados)) + "|",
    ]
    for fila in filas:
        celdas = [str(celda).replace("|", "\\|") for celda in fila]
        lineas.append("| " + " | ".join(celdas) + " |")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# 4. INTERFAZ STREAMLIT
# ---------------------------------------------------------------------------

def _inicializar_estado() -> None:
    """Memoria/estado del agente en la sesión del navegador."""
    if "tareas" not in st.session_state:
        st.session_state.tareas = []          # lista de Tarea
    if "siguiente_id" not in st.session_state:
        st.session_state.siguiente_id = 1
    if "horas_libres_por_dia" not in st.session_state:
        st.session_state.horas_libres_por_dia = [HORAS_LIBRES_POR_DEFECTO] * DIAS_PLAN


def _cargar_demo(ahora: datetime) -> None:
    """Reemplaza la memoria con las tres tareas del caso de la Fase 2."""
    tareas = crear_caso_demostracion(ahora)
    for tarea in tareas:
        tarea.id = st.session_state.siguiente_id
        st.session_state.siguiente_id += 1
    st.session_state.tareas = tareas


def _aplicar_estado(id_tarea: int) -> None:
    """Retroalimentación: marca/desmarca una tarea como hecha."""
    clave = f"hecha_{id_tarea}"
    nuevo_estado = "hecha" if st.session_state.get(clave) else "pendiente"
    for tarea in st.session_state.tareas:
        if tarea.id == id_tarea:
            tarea.estado = nuevo_estado


def _eliminar_tarea(id_tarea: int) -> None:
    st.session_state.tareas = [
        t for t in st.session_state.tareas if t.id != id_tarea
    ]


def _mostrar_alertas(alertas: list[str]) -> None:
    for alerta in alertas:
        if "No hay horas libres" in alerta:
            st.info(alerta)
        elif "vencida" in alerta or "venció" in alerta:
            st.error(alerta)
        elif "menos de 48 horas" in alerta:
            st.warning(alerta)
        else:
            st.info(alerta)


def main() -> None:
    if st is None:
        raise RuntimeError(
            "Streamlit no está instalado. Ejecuta: pip install -r requirements.txt"
        )

    st.set_page_config(page_title="AcademIA", page_icon="🎓", layout="wide")
    _inicializar_estado()

    ahora = datetime.now().replace(second=0, microsecond=0)
    mensaje_flash = st.session_state.pop("flash", None)

    # ------------------------- Barra lateral -------------------------
    with st.sidebar:
        st.header("Configuración")
        horas_dia = st.number_input(
            "Horas libres por día",
            min_value=0.0,
            max_value=12.0,
            value=HORAS_LIBRES_POR_DEFECTO,
            step=0.5,
            key="horas_libres_dia",
            help="Se usan para repartir los bloques de estudio de los próximos 7 días.",
        )
        st.session_state.horas_libres_por_dia = [float(horas_dia)] * DIAS_PLAN
        st.caption(
            f"Capacidad total: {_formato_numero(sum(st.session_state.horas_libres_por_dia), 1)} h "
            f"en {DIAS_PLAN} días."
        )

        st.divider()
        if st.button(
            "Cargar caso de demostración",
            type="primary",
            use_container_width=True,
        ):
            _cargar_demo(ahora)
            st.success(
                "Caso cargado: A = Taller de búsqueda (24 h), "
                "C = Informe de laboratorio (40 h), B = Ensayo de ética (120 h)."
            )
        if st.button("Limpiar tareas", use_container_width=True):
            st.session_state.tareas = []
            st.success("Memoria vaciada.")

        st.divider()
        st.markdown(
            "**Función de prioridad**\n\n"
            "`0,50×urgencia + 0,30×dificultad + 0,20×tiempo`\n\n"
            "urgencia = max(0, 1 − horas/336)\n\n"
            "dificultad = nivel/5 · tiempo = min(1, horas/10)"
        )
        st.caption("Pesos y parámetros se ajustan en las constantes de app.py.")

    # ------------------------- Encabezado -------------------------
    st.title("AcademIA")
    st.caption(
        f"Gestor inteligente de tareas y entregas · Fecha y hora del sistema: "
        f"{ahora:%d/%m/%Y %H:%M}"
    )
    st.write(
        "Registra tus tareas: el agente calcula su prioridad, reparte bloques de "
        "estudio y avisa qué vence pronto. La decisión final siempre es tuya."
    )
    if mensaje_flash:
        st.success(mensaje_flash)

    tareas: list[Tarea] = st.session_state.tareas
    plan = planificar(tareas, ahora, st.session_state.horas_libres_por_dia)
    alertas = generar_alertas(tareas, ahora, plan)

    pendientes = [t for t in tareas if t.esta_pendiente()]
    criticas = [
        t for t in pendientes
        if 0 < (t.fecha_limite - ahora).total_seconds() <= UMBRAL_ALERTA_HORAS * 3600
    ]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tareas pendientes", len(pendientes))
    col2.metric("Vencen en < 48 h", len(criticas))
    col3.metric(
        "Horas de estudio pendientes",
        f"{_formato_numero(sum(t.horas_estimadas for t in pendientes), 1)} h",
    )
    col4.metric(
        "Horas libres (7 días)",
        f"{_formato_numero(sum(st.session_state.horas_libres_por_dia), 1)} h",
    )

    # ------------------------- Percepción: formulario -------------------------
    with st.expander("Registrar una nueva tarea", expanded=not tareas):
        with st.form("form_nueva_tarea", clear_on_submit=True):
            fila1 = st.columns(2)
            nombre = fila1[0].text_input(
                "Nombre de la tarea", placeholder="Ej.: Taller de búsqueda"
            )
            materia = fila1[1].text_input(
                "Materia", placeholder="Ej.: Inteligencia Artificial"
            )

            fila2 = st.columns(3)
            fecha = fila2[0].date_input(
                "Fecha límite",
                value=(ahora + timedelta(days=1)).date(),
                min_value=ahora.date(),
            )
            hora = fila2[1].time_input("Hora límite", value=time(23, 59))
            dificultad = fila2[2].slider(
                "Dificultad (1 = fácil, 5 = difícil)", 1, 5, 3
            )

            fila3 = st.columns(2)
            horas = fila3[0].number_input(
                "Horas estimadas de estudio",
                min_value=HORAS_ESTIMADAS_MIN,
                max_value=HORAS_ESTIMADAS_MAX,
                value=2.0,
                step=0.5,
            )
            enviado = fila3[1].form_submit_button("Agregar tarea", type="primary")

        if enviado:
            fecha_limite = datetime.combine(fecha, hora)
            tarea, errores = percibir(
                nombre, materia, fecha_limite, int(dificultad), float(horas), ahora
            )
            if errores:
                for error in errores:
                    st.error(error)
            else:
                assert tarea is not None
                tarea.id = st.session_state.siguiente_id
                st.session_state.siguiente_id += 1
                st.session_state.tareas.append(tarea)
                st.session_state.flash = (
                    f"Tarea «{tarea.nombre}» registrada en la memoria."
                )
                st.rerun()

    # ------------------------- Acción: alertas -------------------------
    st.subheader("Alertas")
    _mostrar_alertas(alertas)

    # ------------------------- Acción: plan de estudio -------------------------
    st.subheader("Plan de estudio priorizado")

    if not plan:
        st.success(
            "No hay tareas pendientes. Registra una tarea o marca una como "
            "pendiente para generar el plan."
        )
    else:
        filas = []
        for orden, entrada in enumerate(plan, start=1):
            filas.append([
                str(orden),
                entrada["nombre"],
                entrada["materia"],
                ("⚠ " if entrada["urgente_48h"] else "")
                + _horas_restantes_texto(entrada["horas_restantes"]),
                _formato_numero(entrada["urgencia"], 4),
                f"{entrada['dificultad']}/5",
                f"{_formato_numero(entrada['horas_estimadas'], 1)} h",
                _formato_numero(entrada["puntaje"], 3),
            ])
        st.markdown(
            _tabla_markdown(
                [
                    "Orden",
                    "Tarea",
                    "Materia",
                    "Vence en",
                    "Urgencia",
                    "Dificultad",
                    "Tiempo est.",
                    "Puntaje",
                ],
                filas,
            )
        )
        st.caption(
            "El puntaje se calcula con la función de utilidad de la Fase 2. "
            "Cada factor está normalizado entre 0 y 1."
        )

        st.markdown("#### Desglose y bloques de estudio")
        for orden, entrada in enumerate(plan, start=1):
            with st.expander(
                f"{orden}. {entrada['nombre']} — puntaje "
                f"{_formato_numero(entrada['puntaje'], 3)}",
                expanded=(orden == 1),
            ):
                st.markdown("**Cálculo del puntaje**")
                st.markdown(_desglose_texto(entrada))
                st.caption(
                    "Urgencia = max(0, 1 − horas restantes/336); "
                    "dificultad = nivel/5; tiempo = min(1, horas estimadas/10)."
                )

                st.markdown("**Bloques asignados**")
                if entrada["bloques"]:
                    for bloque in entrada["bloques"]:
                        st.markdown(
                            f"- {_dia_texto(bloque['fecha'])}: "
                            f"{_formato_numero(bloque['horas'], 1)} h"
                        )
                else:
                    st.markdown("- Sin bloques asignados.")

                if entrada["horas_sin_asignar"] > 0:
                    st.warning(
                        "Faltan "
                        f"{_formato_numero(entrada['horas_sin_asignar'], 1)} h por "
                        "asignar antes de la fecha límite. Ajusta las horas libres "
                        "por día o reduce el alcance de la tarea."
                    )

    # ------------------------- Retroalimentación -------------------------
    st.subheader("Mis tareas")
    if not tareas:
        st.info("La memoria está vacía. Usa el formulario o el caso de demostración.")
    else:
        for tarea in st.session_state.tareas:
            icono = "✅" if tarea.estado == "hecha" else "⏳"
            with st.expander(
                f"{icono} {tarea.nombre} · {tarea.materia} · "
                f"vence {tarea.fecha_limite:%d/%m/%Y %H:%M}"
            ):
                st.checkbox(
                    "Tarea hecha",
                    value=(tarea.estado == "hecha"),
                    key=f"hecha_{tarea.id}",
                    on_change=_aplicar_estado,
                    args=(tarea.id,),
                )

                with st.form(f"form_fecha_{tarea.id}"):
                    cols = st.columns(2)
                    nueva_fecha = cols[0].date_input(
                        "Nueva fecha límite",
                        value=tarea.fecha_limite.date(),
                    )
                    nueva_hora = cols[1].time_input(
                        "Nueva hora", value=tarea.fecha_limite.time()
                    )
                    actualizar = st.form_submit_button("Actualizar fecha")

                if actualizar:
                    nueva = datetime.combine(nueva_fecha, nueva_hora)
                    _, errores = percibir(
                        tarea.nombre,
                        tarea.materia,
                        nueva,
                        tarea.dificultad,
                        tarea.horas_estimadas,
                        ahora,
                    )
                    if errores:
                        for error in errores:
                            st.error(error)
                    else:
                        tarea.fecha_limite = nueva
                        st.session_state.flash = (
                            "Fecha actualizada. El plan se recalculó."
                        )
                        st.rerun()

                st.button(
                    "Eliminar tarea",
                    key=f"eliminar_{tarea.id}",
                    on_click=_eliminar_tarea,
                    args=(tarea.id,),
                )

    st.divider()
    st.caption(
        "AcademIA no usa servicios externos ni IA generativa: aplica reglas "
        "explícitas y una función de utilidad. Los pesos son una decisión de "
        "diseño y el plan es una recomendación."
    )


if __name__ == "__main__":
    main()
