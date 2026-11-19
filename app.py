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

import html
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


# ---------------------------------------------------------------------------
# 4. ESTILO VISUAL
# ---------------------------------------------------------------------------

ESTILO = """
<style>
:root{
  --paper:#F7F2E8; --surface:#FFFCF6; --surface-2:#F0E8D9;
  --ink:#1E2433; --muted:#6E6A61; --line:#E2D7C4;
  --indigo:#2E3A8C; --indigo-2:#4A57B8; --indigo-soft:#E7E8F6;
  --coral:#BC4A33; --amber:#D79A2B; --sage:#4C7A5C;
  --shadow:0 1px 2px rgba(30,36,51,.04), 0 18px 40px -32px rgba(30,36,51,.55);
  --serif:Georgia,'Times New Roman',serif;
  --sans:'Segoe UI',system-ui,-apple-system,sans-serif;
}

/* Lienzo: papel cálido con dos halos muy suaves */
.stApp{
  background:
    radial-gradient(900px 420px at 12% -10%, rgba(46,58,140,.055), transparent 70%),
    radial-gradient(720px 360px at 100% 0%, rgba(215,154,43,.07), transparent 70%),
    var(--paper);
}
.block-container{
  max-width:1160px;
  padding-top:1.5rem;
  padding-bottom:3rem;
  padding-left:2.5rem;
  padding-right:2.5rem;
}

h1,h2,h3,h4{font-family:var(--serif);color:var(--ink);letter-spacing:-.01em;}

/* Portada */
.hero{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;
  gap:2rem;padding:.35rem 0 1.25rem;border-bottom:1px solid var(--line);
  margin-bottom:1.15rem;}
.hero .eyebrow{display:inline-block;font:600 .7rem/1 var(--sans);letter-spacing:.17em;
  text-transform:uppercase;color:var(--indigo);margin-bottom:.55rem;}
.hero h1{font-family:var(--serif);font-size:clamp(2.6rem,5vw,3.35rem);line-height:.95;
  font-weight:600;margin:0;color:var(--ink);}
.hero h1 em{font-style:italic;color:var(--indigo);}
.hero p{max-width:48ch;margin:.6rem 0 0;color:var(--muted);font-size:1rem;line-height:1.55;}
.today{text-align:right;color:var(--muted);font-size:.82rem;line-height:1.5;
  margin-left:auto;}
.today-label{display:block;font:600 .66rem/1 var(--sans);letter-spacing:.16em;
  text-transform:uppercase;color:var(--indigo);margin-bottom:.3rem;}
.today b{display:block;font-family:var(--serif);font-size:1.2rem;color:var(--ink);
  font-weight:600;letter-spacing:-.01em;}
.today .hora{font-variant-numeric:tabular-nums;}

/* Cifras del tablero */
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:.6rem;margin:.2rem 0 .3rem;}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:.85rem .95rem;box-shadow:var(--shadow);min-width:0;}
.kpi span{display:block;font:600 .66rem/1.25 var(--sans);letter-spacing:.09em;
  text-transform:uppercase;color:var(--muted);}
.kpi b{display:block;margin-top:.38rem;font:600 1.75rem/1 var(--serif);color:var(--ink);
  font-variant-numeric:tabular-nums;overflow-wrap:anywhere;}
.kpi small{display:block;margin-top:.3rem;font-size:.71rem;color:var(--muted);}
.kpi.alerta{border-color:#EBC5B9;background:linear-gradient(180deg,#FFF9F5,#FFFDF8);}
.kpi.alerta b{color:var(--coral);}
@media (max-width:900px){.kpis{grid-template-columns:repeat(2,1fr);}}
@media (max-width:480px){.kpis{grid-template-columns:1fr;}}

/* Encabezados de sección */
.section-head{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;
  flex-wrap:wrap;margin:1.5rem 0 .65rem;}
.section-head.first{margin-top:.25rem;}
.section-head h2{font-family:var(--serif);font-size:1.5rem;font-weight:600;margin:0;
  line-height:1.15;}
.section-head p{margin:0;color:var(--muted);font-size:.85rem;}

/* Leyenda de factores */
.legend{display:flex;flex-wrap:wrap;gap:.4rem 1.1rem;align-items:center;
  font-size:.77rem;color:var(--muted);margin:.15rem 0 .35rem;}
.legend i{display:inline-block;width:.55rem;height:.55rem;border-radius:2px;
  margin-right:.32rem;vertical-align:0;}
.legend .u{background:var(--coral);}
.legend .d{background:var(--indigo);}
.legend .t{background:var(--amber);}

/* Tarjetas del plan */
.plan-card{display:grid;grid-template-columns:2.7rem minmax(0,1fr) auto;gap:1rem;
  align-items:center;background:var(--surface);border:1px solid var(--line);
  border-radius:16px;padding:1rem 1.15rem;box-shadow:var(--shadow);margin:.65rem 0 0;}
.plan-card.primero{border-color:#C4C7E9;
  box-shadow:inset 3px 0 0 var(--indigo),var(--shadow);}
.plan-rank{display:grid;place-items:center;width:2.7rem;height:2.7rem;
  border-radius:50%;background:var(--indigo-soft);color:var(--indigo);
  font:600 1.05rem/1 var(--sans);}
.plan-card.primero .plan-rank{background:var(--indigo);color:#fff;}
.plan-top{display:flex;align-items:center;gap:.55rem;flex-wrap:wrap;}
.plan-title{font-family:var(--serif);font-size:1.16rem;font-weight:600;line-height:1.25;
  margin:0;color:var(--ink);}
.badge{font:600 .64rem/1 var(--sans);letter-spacing:.11em;text-transform:uppercase;
  color:var(--indigo);background:var(--indigo-soft);border-radius:999px;
  padding:.3rem .55rem;}
.plan-subject{margin:.18rem 0 .6rem;font-size:.81rem;color:var(--muted);
  letter-spacing:.01em;}
.plan-bar{display:flex;height:.5rem;border-radius:999px;background:var(--surface-2);
  overflow:hidden;margin:0 0 .55rem;}
.plan-bar span{display:block;height:100%;}
.plan-bar .u{background:var(--coral);}
.plan-bar .d{background:var(--indigo);}
.plan-bar .t{background:var(--amber);}
.plan-meta{display:flex;flex-wrap:wrap;align-items:center;gap:.45rem .85rem;
  font-size:.78rem;color:var(--muted);}
.pill{border-radius:999px;padding:.16rem .55rem;font-weight:600;}
.pill.urgente{background:#FAE9E4;color:var(--coral);border:1px solid #F0CEC4;}
.pill.normal{background:var(--surface-2);color:var(--ink);border:1px solid var(--line);}
.plan-score{text-align:right;padding-left:.4rem;}
.plan-score b{display:block;font:600 1.75rem/1 var(--serif);color:var(--ink);
  font-variant-numeric:tabular-nums;}
.plan-score span{display:block;margin-top:.25rem;font:600 .64rem/1 var(--sans);
  letter-spacing:.14em;text-transform:uppercase;color:var(--muted);}

/* Semana */
.week-card{background:var(--surface);border:1px solid var(--line);border-radius:16px;
  padding:1rem 1.05rem .9rem;box-shadow:var(--shadow);}
.week-head{display:flex;justify-content:space-between;align-items:flex-end;gap:1rem;
  margin-bottom:.8rem;}
.week-head p{margin:0;font-size:.8rem;color:var(--muted);}
.week-head p b{font-family:var(--serif);font-size:1.05rem;color:var(--ink);font-weight:600;}
.week-ratio{font:600 .76rem/1 var(--sans);color:var(--indigo);
  background:var(--indigo-soft);border-radius:999px;padding:.32rem .6rem;}
.week-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:.42rem;align-items:end;}
.day{display:flex;flex-direction:column;align-items:center;gap:.3rem;min-width:0;}
.day-name{font:600 .68rem/1 var(--sans);text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);}
.day-track{width:100%;height:84px;background:var(--surface-2);border-radius:7px;
  display:flex;align-items:flex-end;overflow:hidden;}
.day-fill{display:block;width:100%;background:linear-gradient(180deg,var(--indigo-2),var(--indigo));
  border-radius:5px 5px 0 0;}
.day-fill.high{background:linear-gradient(180deg,#E8B457,var(--amber));}
.day-fill.full{background:linear-gradient(180deg,#D26850,var(--coral));}
.day b{font:600 .77rem/1 var(--sans);color:var(--ink);font-variant-numeric:tabular-nums;}
.day-date{font-size:.67rem;color:var(--muted);font-variant-numeric:tabular-nums;}
.week-legend{display:flex;flex-wrap:wrap;gap:.35rem .9rem;margin-top:.75rem;
  font-size:.71rem;color:var(--muted);}
.week-legend i{display:inline-block;width:.45rem;height:.45rem;border-radius:50%;
  margin-right:.3rem;vertical-align:0;}
.week-legend .i1{background:var(--indigo);}
.week-legend .i2{background:var(--amber);}
.week-legend .i3{background:var(--coral);}

/* Filas de tareas */
.task-name{font-family:var(--serif);font-size:1.05rem;font-weight:600;color:var(--ink);
  line-height:1.3;overflow-wrap:anywhere;}
.task-name.done{color:var(--muted);text-decoration:line-through;
  text-decoration-thickness:1px;}
.task-meta{font-size:.78rem;color:var(--muted);margin-top:.18rem;}
.task-pill{display:inline-block;margin-left:.5rem;padding:.12rem .45rem;border-radius:999px;
  background:#E8F0E9;color:var(--sage);font:600 .64rem/1.3 var(--sans);
  letter-spacing:.05em;text-transform:uppercase;}
[class*="st-key-tarea_"] [data-testid="stCheckbox"] p{font-size:.8rem;white-space:nowrap;}

/* El plan y la columna lateral se apilan cuando no caben con holgura */
@media (max-width:1100px){
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .week-card){
    flex-wrap:wrap;
  }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .week-card)
    > [data-testid="stColumn"]{
    flex:1 1 100% !important;
    min-width:100% !important;
    width:100% !important;
  }
}

/* Formulario: dos campos por fila en pantallas medianas */
@media (max-width:1000px){
  [data-testid="stForm"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap;}
  [data-testid="stForm"] [data-testid="stColumn"]{
    flex:1 1 calc(50% - .5rem) !important;
    min-width:calc(50% - .5rem) !important;
  }
}

/* Ajustes finos para pantallas pequeñas */
@media (max-width:760px){
  .block-container{padding-left:1.1rem;padding-right:1.1rem;}
  .hero{grid-template-columns:1fr;gap:1rem;padding-top:.2rem;}
  .hero h1{font-size:2.6rem;}
  .today{text-align:left;margin-left:0;}
  .plan-card{grid-template-columns:2.2rem minmax(0,1fr);gap:.8rem;}
  .plan-rank{width:2.2rem;height:2.2rem;font-size:.95rem;}
  .plan-score{grid-column:2;text-align:left;padding:0;}
  .plan-score b{display:inline;font-size:1.4rem;}
  .plan-score span{display:inline;margin-left:.5rem;}
  .week-grid{gap:.24rem;}
  .day-track{height:64px;}
  .week-head p{font-size:.76rem;}

  [class*="st-key-tarea_"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap;}
  [class*="st-key-tarea_"] [data-testid="stColumn"]{
    flex:1 1 100% !important;
    min-width:100% !important;
  }
}
@media (prefers-reduced-motion:reduce){
  *{scroll-behavior:auto !important;}
}
</style>
"""

_MESES = ("ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic")


def _h(texto: object) -> str:
    return html.escape(str(texto))


def _html(codigo: str) -> None:
    st.html(codigo)


def _fecha_hero(ahora: datetime) -> str:
    return f"{_DIAS_SEMANA[ahora.weekday()]} {ahora.day} {_MESES[ahora.month - 1]}"


def _hero_html(ahora: datetime) -> str:
    return (
        '<header class="hero">'
        "<div>"
        '<span class="eyebrow">Agente de planificación académica</span>'
        "<h1>Academ<em>IA</em></h1>"
        "<p>Qué entregar primero y cuánto estudiar cada día. "
        "Las cuentas están a la vista; la decisión final es tuya.</p>"
        "</div>"
        '<div class="today">'
        '<span class="today-label">Hoy</span>'
        f"<b>{_fecha_hero(ahora)}</b>"
        f'<span class="hora">{ahora:%H:%M} · hora local</span>'
        "</div>"
        "</header>"
    )


def _seccion(titulo: str, bajada: str = "", primera: bool = False) -> None:
    clase = " first" if primera else ""
    bajada_html = f"<p>{_h(bajada)}</p>" if bajada else ""
    _html(
        f'<div class="section-head{clase}"><h2>{_h(titulo)}</h2>{bajada_html}</div>'
    )


def _cifras_html(
    pendientes: int,
    criticas: int,
    horas_estudio: float,
    horas_libres: float,
) -> str:
    clase = " alerta" if criticas else ""
    return (
        '<div class="kpis">'
        f'<div class="kpi"><span>Pendientes</span><b>{pendientes}</b>'
        "<small>en la memoria</small></div>"
        f'<div class="kpi{clase}"><span>Vencen &lt; 48 h</span><b>{criticas}</b>'
        "<small>regla de alerta</small></div>"
        '<div class="kpi"><span>Por estudiar</span>'
        f'<b>{_formato_numero(horas_estudio, 1)} h</b>'
        "<small>horas estimadas</small></div>"
        '<div class="kpi"><span>Capacidad</span>'
        f'<b>{_formato_numero(horas_libres, 1)} h</b>'
        "<small>en los próximos 7 días</small></div>"
        "</div>"
    )


def _leyenda_html() -> str:
    return (
        '<div class="legend">'
        '<span><i class="u"></i>urgencia × 0,50</span>'
        '<span><i class="d"></i>dificultad × 0,30</span>'
        '<span><i class="t"></i>tiempo × 0,20</span>'
        "</div>"
    )


def _plan_html(orden: int, e: dict) -> str:
    """Tarjeta explicable: la barra acumula el aporte de cada factor."""
    peso_u, peso_d, peso_t = PESOS
    aportes = (
        (peso_u * e["urgencia"], "u", "Urgencia"),
        (peso_d * e["dificultad_n"], "d", "Dificultad"),
        (peso_t * e["tiempo_n"], "t", "Tiempo"),
    )
    segmentos = "".join(
        f'<span class="{clase}" title="{nombre}: {_formato_numero(valor, 3)}" '
        f'style="width:{valor * 100:.2f}%"></span>'
        for valor, clase, nombre in aportes
    )
    urgente = e["urgente_48h"] or e["horas_restantes"] <= 0
    if e["horas_restantes"] <= 0:
        texto_plazo = "vencida"
    else:
        texto_plazo = f"vence en {_horas_restantes_texto(e['horas_restantes'])}"
    pildora = f'<span class="pill {"urgente" if urgente else "normal"}">{texto_plazo}</span>'
    insignia = '<span class="badge">Empieza aquí</span>' if orden == 1 else ""
    return (
        f'<article class="plan-card{" primero" if orden == 1 else ""}">'
        f'<div class="plan-rank">{orden}</div>'
        "<div>"
        f'<div class="plan-top"><h3 class="plan-title">{_h(e["nombre"])}</h3>{insignia}</div>'
        f'<p class="plan-subject">{_h(e["materia"])}</p>'
        f'<div class="plan-bar" role="img" aria-label="Aporte de cada factor al puntaje">'
        f"{segmentos}</div>"
        '<div class="plan-meta">'
        f"{pildora}"
        f'<span>dificultad {e["dificultad"]}/5</span>'
        f'<span>{_formato_numero(e["horas_estimadas"], 1)} h de estudio</span>'
        "</div>"
        "</div>"
        '<div class="plan-score">'
        f'<b>{_formato_numero(e["puntaje"], 3)}</b>'
        "<span>puntaje</span>"
        "</div>"
        "</article>"
    )


def _semana_html(plan: list[dict], ahora: datetime, capacidad: list[float]) -> str:
    """Ocupación de los próximos 7 días según los bloques asignados."""
    usado: dict[date, float] = {}
    for entrada in plan:
        for bloque in entrada["bloques"]:
            usado[bloque["fecha"]] = usado.get(bloque["fecha"], 0.0) + bloque["horas"]

    total_capacidad = sum(capacidad)
    total_usado = sum(usado.values())
    porcentaje = (
        int(round(total_usado / total_capacidad * 100)) if total_capacidad > 0 else 0
    )

    columnas = []
    for i in range(DIAS_PLAN):
        dia = (ahora + timedelta(days=i)).date()
        cap = capacidad[i] if i < len(capacidad) else 0.0
        horas = usado.get(dia, 0.0)
        pct = min(100.0, horas / cap * 100) if cap > 0 else 0.0
        if cap > 0 and horas >= cap - 1e-9:
            estado = "full"
        elif pct >= 70:
            estado = "high"
        else:
            estado = ""
        etiqueta = f"{_formato_numero(horas, 1)} h de {_formato_numero(cap, 1)} h"
        columnas.append(
            '<div class="day">'
            f'<span class="day-name">{_DIAS_SEMANA[dia.weekday()]}</span>'
            f'<div class="day-track" role="img" aria-label="{etiqueta}">'
            f'<span class="day-fill {estado}" style="height:{pct:.0f}%"></span>'
            "</div>"
            f"<b>{_formato_numero(horas, 1)} h</b>"
            f'<span class="day-date">{dia:%d/%m}</span>'
            "</div>"
        )

    return (
        '<div class="week-card">'
        '<div class="week-head">'
        f'<p><b>{_formato_numero(total_usado, 1)} h</b> asignadas de '
        f"{_formato_numero(total_capacidad, 1)} h disponibles</p>"
        f'<span class="week-ratio">{porcentaje}%</span>'
        "</div>"
        f'<div class="week-grid">{"".join(columnas)}</div>'
        '<div class="week-legend">'
        '<span><i class="i1"></i>carga</span>'
        '<span><i class="i2"></i>día exigente</span>'
        '<span><i class="i3"></i>día completo</span>'
        "</div>"
        "</div>"
    )


def _mostrar_alertas(alertas: list[str]) -> None:
    """Agrupa las alertas por severidad sin alterar los textos del agente."""
    vencidas: list[str] = []
    urgentes: list[str] = []
    capacidad: list[str] = []
    tranquilas: list[str] = []

    for alerta in alertas:
        if "vencid" in alerta or "venció" in alerta:
            vencidas.append(alerta)
        elif alerta.startswith("Tienes") and "menos de 48 horas" in alerta:
            urgentes.append(alerta)
        elif alerta.startswith("«"):
            urgentes.append(alerta)
        elif "No hay horas libres suficientes" in alerta:
            capacidad.append(alerta)
        else:
            tranquilas.append(alerta)

    if vencidas:
        st.error("  \n".join(vencidas), title="Tareas vencidas",
                 icon=":material/error:")
    if urgentes:
        st.warning("  \n".join(urgentes), title="Vencen en menos de 48 horas",
                   icon=":material/schedule:")
    if capacidad:
        st.warning("  \n".join(capacidad), title="Capacidad insuficiente",
                   icon=":material/hourglass_empty:")
    if tranquilas:
        st.success("  \n".join(tranquilas), title="Sin urgencias",
                   icon=":material/check_circle:")


# ---------------------------------------------------------------------------
# 5. INTERFAZ STREAMLIT
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


def _tarea_html(tarea: Tarea) -> str:
    hecha = tarea.estado == "hecha"
    clase = " done" if hecha else ""
    pildora = '<span class="task-pill">completada</span>' if hecha else ""
    return (
        f'<div class="task-name{clase}">{_h(tarea.nombre)}</div>'
        f'<div class="task-meta">{_h(tarea.materia)} · vence '
        f"{tarea.fecha_limite:%d/%m/%Y · %H:%M}{pildora}</div>"
    )


def main() -> None:
    if st is None:
        raise RuntimeError(
            "Streamlit no está instalado. Ejecuta: pip install -r requirements.txt"
        )

    st.set_page_config(
        page_title="AcademIA · Plan de estudio",
        page_icon=":material/school:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inicializar_estado()
    st.html(ESTILO)

    ahora = datetime.now().replace(second=0, microsecond=0)

    # ------------------------- Barra lateral -------------------------
    with st.sidebar:
        st.markdown("#### Configuración")
        st.caption("Ajusta tu disponibilidad y carga el caso de la Fase 2.")
        horas_dia = st.number_input(
            "Horas libres por día",
            min_value=0.0,
            max_value=12.0,
            value=HORAS_LIBRES_POR_DEFECTO,
            step=0.5,
            key="horas_libres_dia",
            help="Se reparten entre los próximos 7 días, sin sobreasignar.",
        )
        st.session_state.horas_libres_por_dia = [float(horas_dia)] * DIAS_PLAN
        st.caption(
            f"Capacidad total: {_formato_numero(horas_dia * DIAS_PLAN, 1)} h "
            f"en {DIAS_PLAN} días."
        )

        st.divider()
        if st.button(
            "Cargar caso de demostración",
            icon=":material/play_circle:",
            type="primary",
            width="stretch",
        ):
            _cargar_demo(ahora)
            st.session_state.flash = "Caso cargado: el plan prioriza A → C → B."
            st.rerun()
        if st.button(
            "Vaciar memoria",
            icon=":material/delete_sweep:",
            width="stretch",
        ):
            st.session_state.tareas = []
            st.session_state.flash = "Memoria vaciada. Puedes registrar una tarea nueva."
            st.rerun()

        st.divider()
        with st.expander("Cómo decide el agente", icon=":material/function:"):
            st.markdown("**Función de utilidad**")
            st.latex(r"P = 0{,}50\,U + 0{,}30\,D + 0{,}20\,T")
            st.caption(
                "U = max(0, 1 − horas restantes/336) · D = nivel/5 · "
                "T = min(1, horas estimadas/10)"
            )
        st.caption("Prototipo académico · Fase 2")

    mensaje_flash = st.session_state.pop("flash", None)

    tareas: list[Tarea] = st.session_state.tareas
    plan = planificar(tareas, ahora, st.session_state.horas_libres_por_dia)
    alertas = generar_alertas(tareas, ahora, plan)

    pendientes = [t for t in tareas if t.esta_pendiente()]
    criticas = [
        t for t in pendientes
        if 0 < (t.fecha_limite - ahora).total_seconds() <= UMBRAL_ALERTA_HORAS * 3600
    ]
    horas_estudio = sum(t.horas_estimadas for t in pendientes)
    capacidad_total = sum(st.session_state.horas_libres_por_dia)

    # ------------------------- Encabezado -------------------------
    _html(_hero_html(ahora))
    if mensaje_flash:
        st.success(mensaje_flash, icon=":material/check_circle:")

    # ------------------------- Tablero -------------------------
    _html(_cifras_html(
        len(pendientes),
        len(criticas),
        horas_estudio,
        capacidad_total,
    ))

    izquierda, derecha = st.columns([1.75, 1], gap="large")

    # ------------------------- Acción: plan -------------------------
    with izquierda:
        _seccion(
            "Plan de estudio",
            "Ordenado por la función de utilidad de la Fase 2.",
            primera=True,
        )

        if not plan:
            st.info(
                "No hay tareas pendientes. Carga el caso de demostración o "
                "registra una tarea para generar el plan.",
                icon=":material/task_alt:",
            )
        else:
            _html(_leyenda_html())
            for orden, entrada in enumerate(plan, start=1):
                _html(_plan_html(orden, entrada))
                with st.expander(
                    "Cálculo y bloques",
                    icon=":material/calculate:",
                    type="compact",
                ):
                    st.markdown("**Desglose del puntaje**")
                    st.markdown(_desglose_texto(entrada))
                    st.caption(
                        "Urgencia = max(0, 1 − horas restantes/336) · "
                        "dificultad = nivel/5 · tiempo = min(1, horas estimadas/10)."
                    )

                    st.markdown("**Bloques de estudio**")
                    if entrada["bloques"]:
                        for bloque in entrada["bloques"]:
                            st.markdown(
                                f"- **{_dia_texto(bloque['fecha'])}** · "
                                f"{_formato_numero(bloque['horas'], 1)} h"
                            )
                    else:
                        st.markdown("- Sin bloques asignados.")

                    if entrada["horas_sin_asignar"] > 0:
                        st.warning(
                            "Faltan "
                            f"{_formato_numero(entrada['horas_sin_asignar'], 1)} h "
                            "por asignar antes de la fecha límite. Ajusta las horas "
                            "libres por día o reduce el alcance de la tarea."
                        )

    # ------------------------- Acción: alertas y semana -------------------------
    with derecha:
        _seccion("Alertas", "Reglas explícitas de la Fase 2.", primera=True)
        _mostrar_alertas(alertas)

        _seccion("Tu semana", "Carga asignada sobre tu capacidad.")
        _html(_semana_html(plan, ahora, st.session_state.horas_libres_por_dia))

    # ------------------------- Percepción: formulario -------------------------
    with st.expander(
        "Registrar una nueva tarea",
        expanded=not tareas,
        icon=":material/add_task:",
    ):
        with st.form("form_nueva_tarea", clear_on_submit=True, border=False):
            fila1 = st.columns([2, 1], gap="medium")
            nombre = fila1[0].text_input(
                "Nombre de la tarea", placeholder="Ej.: Taller de búsqueda"
            )
            materia = fila1[1].text_input(
                "Materia", placeholder="Ej.: Inteligencia Artificial"
            )

            fila2 = st.columns(4, gap="medium")
            fecha = fila2[0].date_input(
                "Fecha límite",
                value=(ahora + timedelta(days=1)).date(),
                min_value=ahora.date(),
            )
            hora = fila2[1].time_input("Hora límite", value=time(23, 59))
            dificultad = fila2[2].slider(
                "Dificultad (1–5)", 1, 5, 3, help="1 = fácil · 5 = difícil"
            )
            horas = fila2[3].number_input(
                "Horas estimadas",
                min_value=HORAS_ESTIMADAS_MIN,
                max_value=HORAS_ESTIMADAS_MAX,
                value=2.0,
                step=0.5,
            )
            enviado = st.form_submit_button(
                "Agregar tarea",
                type="primary",
                icon=":material/add:",
                width="stretch",
            )

        if enviado:
            fecha_limite = datetime.combine(fecha, hora)
            tarea, errores = percibir(
                nombre, materia, fecha_limite, int(dificultad), float(horas), ahora
            )
            if errores:
                st.error(
                    "  \n".join(errores),
                    title="Revisa los datos",
                    icon=":material/error:",
                )
            else:
                assert tarea is not None
                tarea.id = st.session_state.siguiente_id
                st.session_state.siguiente_id += 1
                st.session_state.tareas.append(tarea)
                st.session_state.flash = (
                    f"Tarea «{tarea.nombre}» registrada en la memoria."
                )
                st.rerun()

    # ------------------------- Retroalimentación -------------------------
    _seccion(
        "Mis tareas",
        "Marca lo completado o ajusta una fecha: el plan se recalcula al instante.",
    )

    if not tareas:
        st.info(
            "La memoria está vacía. Usa el formulario o el caso de demostración.",
            icon=":material/inbox:",
        )
    else:
        for tarea in tareas:
            with st.container(border=True, key=f"tarea_{tarea.id}"):
                c_estado, c_datos, c_acciones = st.columns(
                    [1.2, 3.5, 3.5], vertical_alignment="center", gap="small"
                )
                with c_estado:
                    st.checkbox(
                        "Hecha",
                        value=(tarea.estado == "hecha"),
                        key=f"hecha_{tarea.id}",
                        on_change=_aplicar_estado,
                        args=(tarea.id,),
                    )
                with c_datos:
                    _html(_tarea_html(tarea))
                with c_acciones:
                    with st.container(
                        horizontal=True,
                        horizontal_alignment="right",
                        gap="small",
                    ):
                        with st.popover(
                            "Fecha",
                            icon=":material/edit_calendar:",
                            help="Cambiar la fecha límite de la tarea.",
                        ):
                            with st.form(f"form_fecha_{tarea.id}", border=False):
                                nueva_fecha = st.date_input(
                                    "Nueva fecha límite",
                                    value=tarea.fecha_limite.date(),
                                )
                                nueva_hora = st.time_input(
                                    "Nueva hora", value=tarea.fecha_limite.time()
                                )
                                actualizar = st.form_submit_button(
                                    "Guardar fecha",
                                    type="primary",
                                    width="stretch",
                                )

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
                                    st.error("  \n".join(errores))
                                else:
                                    tarea.fecha_limite = nueva
                                    st.session_state.flash = (
                                        "Fecha actualizada. El plan se recalculó."
                                    )
                                    st.rerun()

                        st.button(
                            "Eliminar",
                            key=f"eliminar_{tarea.id}",
                            icon=":material/delete:",
                            type="tertiary",
                            help="Eliminar la tarea de la memoria.",
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
