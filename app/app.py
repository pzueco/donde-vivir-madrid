import html
import math

import folium
import gradio as gr
import pandas as pd
import plotly.graph_objects as go

from recomendador import (
    ANO_BASE, ANO_ULTIMO, B, COL_SUBIDA, DIAS_LABORABLES, ETIQUETAS, EVOLUCION, FACTOR_RODEO,
    INDICES, LUGARES, MIN_VIVIENDAS, PERFILES, SERIE_MADRID, TIPOS_LUGAR, VELOCIDAD_A_PIE,
    asequibilidad, barrio_de, dentro_de_madrid, enlace_google_maps, enlace_ruta, geocodificar,
    idx_transporte_trabajo, lugares_cerca, minutos_hasta, nombre_visible, rango_precio,
    recomendar, trayecto,
)

# En Hugging Face (ZeroGPU) hace falta al menos una función marcada con @spaces.GPU.
# No usa la GPU para nada; en local, sin la librería "spaces", se ignora.
try:
    import spaces

    @spaces.GPU(duration=1)
    def _activar_zerogpu():
        return None
except ImportError:
    pass

B_WGS84 = B.to_crs(4326)

# ================================================================ configuración
PARA_QUIEN = {
    "🙋  Para mí": "solo",
    "👨‍👩‍👧  Pareja o familia": "familia",
    "🎓  Compartir piso": "compartir",
}
CONFIG_PARA_QUIEN = {
    "solo": {
        "habitaciones": ["Estudio", "1"], "habitacion": "1", "perfil": "joven",
        "presupuesto": (300, 3000, 1000), "texto_presupuesto": "Presupuesto para el piso (€/mes)",
        "texto_habitaciones": "Habitaciones",
    },
    "familia": {
        "habitaciones": ["1", "2", "3", "4 o más"], "habitacion": "2", "perfil": "familia",
        "presupuesto": (500, 4000, 1400), "texto_presupuesto": "Presupuesto para el piso (€/mes)",
        "texto_habitaciones": "Habitaciones",
    },
    "compartir": {
        "habitaciones": ["2", "3", "4", "5"], "habitacion": "3", "perfil": "estudiante",
        "presupuesto": (150, 1200, 450), "texto_presupuesto": "Presupuesto para TU habitación (€/mes)",
        "texto_habitaciones": "Habitaciones del piso que compartes",
    },
}
M2_POR_HABITACIONES = {"Estudio": 35, "1": 50, "2": 70, "3": 90, "4": 110, "4 o más": 115, "5": 130}

ZONAS_TRABAJO = {
    "Teletrabajo / no lo sé": None,
    "Nuevos Ministerios / AZCA": (40.4466, -3.6920),
    "Plaza de Castilla / Cuatro Torres": (40.4770, -3.6880),
    "Sol / Centro": (40.4169, -3.7035),
    "Gran Vía / Callao": (40.4200, -3.7058),
    "Atocha": (40.4065, -3.6895),
    "Méndez Álvaro": (40.3955, -3.6780),
    "Moncloa": (40.4350, -3.7190),
    "Ciudad Universitaria": (40.4450, -3.7280),
    "Las Tablas": (40.5050, -3.6700),
    "IFEMA / Campo de las Naciones": (40.4630, -3.6160),
    "Julián Camarillo (San Blas)": (40.4400, -3.6250),
    "Aeropuerto T4": (40.4910, -3.5930),
    "Hospital La Paz": (40.4810, -3.6870),
    "Hospital 12 de Octubre": (40.3750, -3.6990),
}
ZONAS_CON_DIRECCION = [z for z, c in ZONAS_TRABAJO.items() if c]

MODOS = {
    "🚇 Transporte público": "transporte",
    "🚲 Bici": "bici",
    "🚗 Coche (sin tráfico)": "coche",
    "🚶 Andando": "andando",
}

TIPOS_POR_DEFECTO = [
    "🍺 Bares y cafeterías", "🍽️ Restaurantes", "🌞 Terrazas", "🪩 Discotecas y bares de copas",
    "🗿 Monumentos y lugares de interés",
    "🏛️ Museos", "🌳 Parques", "⚽ Campos de fútbol", "💪 Gimnasios",
    "🛒 Supermercados y mercados", "🚇 Metro, Cercanías y Metro Ligero",
]
_PALETA = ["#f97316", "#db2777", "#7c3aed", "#2563eb", "#0891b2", "#16a34a", "#ca8a04", "#dc2626",
           "#9333ea", "#0d9488", "#ea580c", "#4f46e5", "#65a30d", "#be123c", "#0284c7", "#a16207",
           "#475569", "#c026d3", "#059669", "#b45309", "#1d4ed8", "#e11d48", "#15803d"]
COLOR_TIPO = {t: _PALETA[i % len(_PALETA)] for i, t in enumerate(TIPOS_LUGAR)}
MAX_EN_MAPA = 15     # lugares por tipo que se dibujan en el mapa
MAX_EN_TABLA = 5     # lugares por tipo que salen en la tabla

NOMBRE_A_BARRIO = {nombre_visible(b): b for b in sorted(B["barrio"])}
BARRIO_A_COD = dict(zip(B["barrio"], B["cod_barrio"]))

FRANJAS = [
    (15, "Menos de 15 min", "#1a9850"),
    (30, "15–30 min", "#91cf60"),
    (45, "30–45 min", "#fee08b"),
    (60, "45–60 min", "#fc8d59"),
    (90, "60–90 min", "#d73027"),
]
FRANJAS_ESFUERZO = [
    (25, "Hasta 25 %", "#1a9850"),
    (30, "25–30 %", "#91cf60"),
    (35, "30–35 %", "#fee08b"),
    (40, "35–40 %", "#fc8d59"),
    (1000, "Más del 40 %", "#d73027"),
]
COLOR_GRIS = "#bdbdbd"

TEXTO_DIRECCION = "…o escribe la dirección exacta (opcional, solo Madrid capital)"
EJEMPLO_DIRECCION = "Ej.: Calle de Arturo Soria 320"
TEXTO_2026 = "Actualizar precios a 2026 (estimación según la tendencia de cada barrio)"

# ================================================================ diseño
TEMA = gr.themes.Soft(
    primary_hue="orange",
    secondary_hue="violet",
    neutral_hue="slate",
    radius_size="lg",
    font=[gr.themes.GoogleFont("Poppins"), "ui-sans-serif", "sans-serif"],
)

CSS = """
.gradio-container { max-width: 1400px !important; margin: auto !important; }

/* ---------- Portada ---------- */
.hero {
    position: relative; overflow: hidden; border-radius: 28px;
    padding: 56px 48px 140px;
    background: linear-gradient(135deg, #0f172a 0%, #312e81 45%, #9d174d 75%, #ea580c 100%);
    color: white; box-shadow: 0 20px 50px rgba(49, 46, 129, 0.35);
}
.hero h1 { font-size: 3rem; font-weight: 800; margin: 0 0 12px; color: white !important; line-height: 1.1; }
.hero .subtitulo { font-size: 1.2rem; max-width: 720px; opacity: 0.92; color: white !important; margin: 0; }
.hero .chips { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 26px; position: relative; z-index: 2; }
.hero .chip {
    background: rgba(255, 255, 255, 0.14); border: 1px solid rgba(255, 255, 255, 0.3);
    backdrop-filter: blur(8px); padding: 8px 16px; border-radius: 999px;
    font-weight: 600; font-size: 0.92rem; color: white;
}
.hero .sol {
    position: absolute; right: 9%; top: 22%; width: 150px; height: 150px; border-radius: 50%;
    background: radial-gradient(circle, #fde68a 0%, #fb923c 55%, rgba(251, 146, 60, 0) 72%);
    opacity: 0.9;
}
.hero .estrella { position: absolute; width: 3px; height: 3px; background: white; border-radius: 50%; opacity: 0.7; }
.hero svg.skyline { position: absolute; bottom: 0; left: 0; width: 100%; height: 130px; }

/* ---------- ¿Para quién buscas? ---------- */
.titulo-seccion { font-size: 1.4rem; font-weight: 800; margin: 26px 0 6px; }
#para-quien .wrap { display: grid !important; grid-template-columns: repeat(3, 1fr); gap: 16px; }
#para-quien label {
    justify-content: center !important; padding: 26px 18px !important;
    border-radius: 20px !important; border: 2px solid var(--border-color-primary) !important;
    font-size: 1.2rem !important; font-weight: 700 !important;
    background: var(--background-fill-secondary) !important;
    transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
}
#para-quien label:hover { transform: translateY(-4px); box-shadow: 0 12px 28px rgba(0, 0, 0, 0.12); }
#para-quien label.selected {
    border-color: #f97316 !important;
    background: linear-gradient(135deg, rgba(249, 115, 22, 0.18), rgba(124, 58, 237, 0.18)) !important;
    box-shadow: 0 12px 30px rgba(249, 115, 22, 0.3);
}
#para-quien input[type="radio"] { display: none !important; }

/* ---------- Paneles, pestañas y botones ---------- */
.tarjeta {
    border-radius: 22px !important; padding: 18px !important;
    background: var(--background-fill-primary);
    box-shadow: 0 10px 35px rgba(15, 23, 42, 0.08);
    border: 1px solid var(--border-color-primary);
}
#pestanas button[role="tab"] { font-size: 1.05rem !important; font-weight: 700 !important; padding: 12px 20px !important; }
.boton-principal button, button.boton-principal {
    font-size: 1.1rem !important; font-weight: 700 !important; padding: 14px !important;
    border-radius: 14px !important; border: none !important; color: white !important;
    background: linear-gradient(90deg, #f97316, #db2777) !important;
    box-shadow: 0 8px 22px rgba(219, 39, 119, 0.3);
}
.resumen { font-size: 1.05rem; }
.pie { opacity: 0.7; font-size: 0.85rem; margin-top: 24px; }
"""

# Estrellas pequeñas en el cielo de la portada
_ESTRELLAS = "".join(
    f'<div class="estrella" style="left:{x}%; top:{y}%;"></div>'
    for x, y in [(5, 12), (14, 30), (22, 8), (31, 22), (44, 10), (52, 28), (61, 6), (68, 18), (77, 9), (93, 14), (88, 34), (38, 36)]
)

PORTADA = f"""
<div class="hero">
  {_ESTRELLAS}
  <div class="sol"></div>
  <h1>¿Dónde vivir<br>en Madrid?</h1>
  <p class="subtitulo">Encuentra tu barrio según tu presupuesto, dónde trabajas o estudias y lo que te importa.
  Con tiempos reales en transporte público y precios oficiales de alquiler.</p>
  <div class="chips">
    <span class="chip">🏘️ 131 barrios</span>
    <span class="chip">🚇 842.456 trayectos calculados</span>
    <span class="chip">📈 14 años de precios</span>
    <span class="chip">🗺️ 100 % datos abiertos</span>
  </div>
  <svg class="skyline" viewBox="0 0 1200 130" preserveAspectRatio="none">
    <path fill="rgba(15,23,42,0.55)" d="M0 130 V95 H60 V80 H95 V100 H150 V70 H190 V90 H250 V60 H280 V85 H340 V75 H400 V95 H460 V65 H500 V88 H560 V72 H620 V96 H680 V68 H730 V86 H790 V58 H830 V82 H890 V74 H950 V92 H1010 V66 H1060 V84 H1120 V78 H1200 V130 Z"/>
    <path fill="rgba(15,23,42,0.92)" d="M0 130 V105 H40 V88 H70 V110 H110 V78 H128 V66 H146 V78 H165 V100 H215 V84 H255 V96 H300 V50 H312 V28 H320 V12 H328 V28 H336 V50 H350 V98 H400 V82 H440 V108 H490 V74 H530 V90 H575 V62 H612 V100 H660 V80 H700 V44 H716 V30 H732 V44 H752 V92 H800 V76 H850 V100 H895 V70 H935 V86 H985 V56 H1022 V94 H1070 V84 H1115 V104 H1160 V90 H1200 V130 Z"/>
  </svg>
</div>
"""


# ================================================================ dónde trabajas
def resolver_trabajo(zona, direccion):
    """Devuelve (coordenadas, nombre para mostrar, aviso, ok).
    Si se ha escrito una dirección, tiene prioridad sobre la zona elegida."""
    if direccion and direccion.strip():
        r = geocodificar(direccion)
        if r is None:
            return None, None, (
                f"⚠️ No hemos encontrado «{direccion}». Prueba con calle, número y barrio, "
                "o elige una zona de la lista."
            ), False
        lat, lon, encontrada = r
        if not dentro_de_madrid(lat, lon):
            return None, None, (
                f"⚠️ «{encontrada}» está fuera del municipio de Madrid. "
                "Por ahora solo calculamos destinos dentro de Madrid capital."
            ), False
        return (lat, lon), "tu dirección", f"📍 Hemos entendido: *{encontrada}*", True
    return ZONAS_TRABAJO[zona], zona, "", True


# ================================================================ utilidades de mapa
def mapa_base():
    return folium.Map(location=[40.42, -3.70], zoom_start=11, tiles="OpenStreetMap")


def marcar_trabajo(m, coords):
    if coords is not None:
        folium.Marker(
            coords, tooltip="Tu trabajo o centro de estudios",
            icon=folium.Icon(color="red", icon="briefcase", prefix="fa"),
        ).add_to(m)


def a_iframe(m, limites=None):
    """Mapa → iframe. Por defecto encuadra todo Madrid; si no, los límites [[s, o], [n, e]]."""
    if limites is None:
        xmin, ymin, xmax, ymax = B_WGS84.total_bounds
        limites = [[ymin, xmin], [ymax, xmax]]
    m.fit_bounds(limites)

    # Recalcular tamaño y encuadre cuando el mapa se hace visible o cambia de tamaño
    nombre = m.get_name()
    script = f"""
    <script>
    function reencuadrar() {{
        {nombre}.invalidateSize();
        {nombre}.fitBounds({limites});
    }}
    window.addEventListener('load', function() {{ setTimeout(reencuadrar, 300); }});
    window.addEventListener('resize', reencuadrar);
    </script>
    """
    m.get_root().html.add_child(folium.Element(script))

    pagina = m.get_root().render()
    return (
        f'<iframe srcdoc="{html.escape(pagina)}" '
        f'style="width:100%; height:600px; border:none; border-radius:18px;"></iframe>'
    )


def leyenda(franjas, texto_gris):
    partes = [
        f'<span style="display:inline-block;width:14px;height:14px;background:{c};border-radius:4px;'
        f'margin:0 4px 0 12px;vertical-align:middle;"></span>{t}'
        for _, t, c in franjas
    ]
    partes.append(
        f'<span style="display:inline-block;width:14px;height:14px;background:{COLOR_GRIS};border-radius:4px;'
        f'margin:0 4px 0 12px;vertical-align:middle;"></span>{texto_gris}'
    )
    return f'<div style="margin-bottom:10px;">{"".join(partes)}</div>'


def color_por_franja(valor, franjas, tope):
    if pd.isna(valor) or valor > tope:
        return COLOR_GRIS
    for limite, _, color in franjas:
        if valor <= limite:
            return color
    return COLOR_GRIS


def mapa_coloreado(d, campos, alias, coords=None):
    """Mapa con cada barrio coloreado según su columna 'color'."""
    m = mapa_base()
    folium.GeoJson(
        d[campos + ["color", "geometry"]].to_json(),
        style_function=lambda f: {
            "fillColor": f["properties"]["color"], "color": "white",
            "weight": 0.6, "fillOpacity": 0.75,
        },
        tooltip=folium.GeoJsonTooltip(fields=campos, aliases=alias),
    ).add_to(m)
    marcar_trabajo(m, coords)
    return a_iframe(m)


def texto_minutos(mn):
    if pd.isna(mn):
        return "más de 2 h"
    if mn >= 60:
        return f"{int(mn // 60)} h {int(mn % 60)} min"
    return f"{mn:.0f} min"


# ================================================================ pestaña 1: recomendador
def cambiar_para_quien(opcion):
    """Adapta habitaciones, presupuesto, perfil y pesos a quién busca."""
    c = CONFIG_PARA_QUIEN[PARA_QUIEN[opcion]]
    minimo, maximo, valor = c["presupuesto"]
    pesos = [PERFILES[c["perfil"]].get(k, 0) for k in INDICES]
    return [
        gr.Radio(choices=c["habitaciones"], value=c["habitacion"], label=c["texto_habitaciones"]),
        gr.Slider(minimum=minimo, maximum=maximo, value=valor, label=c["texto_presupuesto"]),
        gr.Dropdown(value=c["perfil"]),
    ] + pesos


def m2_de_habitaciones(habitaciones):
    return M2_POR_HABITACIONES.get(habitaciones, 70)


def pesos_de_perfil(perfil):
    return [PERFILES[perfil].get(k, 0) for k in INDICES]


def mapa_recomendacion(res, coords):
    m = mapa_base()
    B_WGS84.explore(
        m=m, color="#888888", tooltip=["barrio", "distrito"],
        style_kwds={"fillOpacity": 0.05, "weight": 0.5},
    )
    if not res.empty:
        tooltip = ["nombre", "puntuacion", "alquiler_estimado"]
        if "minutos_trabajo" in res.columns:
            tooltip += ["minutos_trabajo", "coste_real"]
        tooltip.append("por_que")
        res.to_crs(4326).explore(
            m=m, column="puntuacion", cmap="YlOrRd", legend=True,
            legend_kwds={"caption": "Puntuación"},
            tooltip=tooltip,
            style_kwds={"color": "black", "weight": 1.2, "fillOpacity": 0.75},
        )
    marcar_trabajo(m, coords)
    return a_iframe(m)


def resumen_coste(res, valor_hora):
    """Frase comparando el barrio más barato con el más cercano al trabajo."""
    if "coste_real" not in res.columns or len(res) < 2:
        return ""
    barato = res.loc[res["alquiler_estimado"].idxmin()]
    cerca = res.loc[res["minutos_trabajo"].idxmin()]
    mejor = res.loc[res["coste_real"].idxmin()]
    texto = ""
    if barato["nombre"] != cerca["nombre"]:
        dif_euros = cerca["alquiler_estimado"] - barato["alquiler_estimado"]
        dif_horas = barato["horas_ano"] - cerca["horas_ano"]
        texto += (
            f"💡 **{barato['nombre']}** es el más barato de la lista ({barato['alquiler_estimado']:.0f} €/mes), "
            f"pero tardas {barato['minutos_trabajo']:.0f} min. "
            f"**{cerca['nombre']}** cuesta {dif_euros:.0f} € más al mes y te ahorra "
            f"**{dif_horas:.0f} horas al año** en transporte.\n\n"
        )
    texto += (
        f"⏳ Contando tu tiempo a {valor_hora} €/hora, el barrio con menor **coste real** es "
        f"**{mejor['nombre']}**: {mejor['coste_real']:.0f} €/mes entre alquiler y tiempo."
    )
    return texto


def buscar(para_quien, habitaciones, presupuesto, m2, zona, direccion, max_minutos,
           valor_hora, usar_2026, *valores):
    coords, _, aviso, ok = resolver_trabajo(zona, direccion)
    if not ok:
        return "", pd.DataFrame(), aviso

    pesos = dict(zip(INDICES, valores))
    if sum(pesos.values()) == 0:
        return "<p>Sube al menos uno de los deslizadores.</p>", pd.DataFrame(), aviso

    compartir = PARA_QUIEN[para_quien] == "compartir"
    dividir = int(habitaciones) if compartir else 1

    minutos = minutos_hasta(*coords) if coords else None
    res = recomendar(presupuesto, m2, pesos, minutos=minutos, max_minutos=max_minutos,
                     valor_hora=valor_hora, usar_2026=usar_2026, dividir_entre=dividir)
    if res.empty:
        return (
            "<p>No hay barrios que cumplan todo a la vez. Prueba a subir el presupuesto, "
            "bajar los metros o aceptar más minutos de trayecto.</p>",
            pd.DataFrame(), aviso,
        )

    tabla = res.drop(columns="geometry").copy()
    if coords:
        tabla["como_llegar"] = tabla["cod_barrio"].map(
            lambda c: f"[Ver ruta]({enlace_google_maps(c, coords)})"
        )
    texto_alquiler = "Alquiler por habitación (€)" if compartir else "Alquiler del piso (€)"
    tabla = (
        tabla.drop(columns="cod_barrio")
        .rename(columns={
            "nombre": "Barrio",
            "distrito": "Distrito",
            "puntuacion": "Puntuación",
            "alquiler_estimado": texto_alquiler,
            "minutos_trabajo": "Minutos de trayecto",
            "horas_ano": "Horas al año en transporte",
            "coste_real": "Coste real (€/mes)",
            "por_que": "Por qué",
            "dist_tren_m": "Tren más cercano (m)",
            "como_llegar": "Cómo llegar",
        })
        .astype(str)
    )

    partes = [aviso]
    if compartir:
        partes.append(
            f"🎓 **Precio por habitación** = alquiler de un piso de {m2:.0f} m² ÷ {dividir} habitaciones. "
            "Es orientativo: alquilar una habitación suelta suele salir algo más caro, porque suele "
            "incluir muebles, gastos o la gestión del propietario."
        )
    partes.append(resumen_coste(res, valor_hora))
    resumen = "\n\n".join(t for t in partes if t)
    return mapa_recomendacion(res, coords), tabla, resumen


# ================================================================ pestaña 2: tu casa y alrededores
def mapa_casa(casa, trabajo, radio, d):
    m = mapa_base()
    folium.Circle(casa, radius=radio, color="#f97316", weight=2, fill=True, fill_opacity=0.06).add_to(m)
    for tipo, sub in d.groupby("tipo", sort=False):
        for _, p in sub.head(MAX_EN_MAPA).iterrows():
            folium.CircleMarker(
                [p["lat"], p["lon"]], radius=6, color="white", weight=1,
                fill=True, fill_color=COLOR_TIPO[tipo], fill_opacity=0.95,
                tooltip=f"{tipo} · {p['nombre']} · {p['min_andando']} min andando",
            ).add_to(m)
    folium.Marker(casa, tooltip="Tu casa", icon=folium.Icon(color="green", icon="home", prefix="fa")).add_to(m)
    marcar_trabajo(m, trabajo)

    # Encuadre: el círculo alrededor de casa
    lat, lon = casa
    dlat = radio / 111_000 * 1.15
    dlon = dlat / max(0.1, math.cos(math.radians(lat)))
    return a_iframe(m, [[lat - dlat, lon - dlon], [lat + dlat, lon + dlon]])


def mi_casa(direccion_casa, zona, direccion_trabajo, radio, tipos):
    if not direccion_casa or not direccion_casa.strip():
        return ("", "Escribe la dirección de tu casa (o la del piso que estás mirando).", "", pd.DataFrame())
    r = geocodificar(direccion_casa)
    if r is None:
        return ("", f"⚠️ No hemos encontrado «{direccion_casa}». Prueba con calle, número y barrio.",
                "", pd.DataFrame())
    lat, lon, encontrada = r
    if not dentro_de_madrid(lat, lon):
        return ("", f"⚠️ «{encontrada}» está fuera del municipio de Madrid. Por ahora solo cubrimos Madrid capital.",
                "", pd.DataFrame())
    casa = (lat, lon)

    # ---- Tu casa y el trayecto al trabajo
    fila = barrio_de(lat, lon)
    partes = [f"📍 **Tu casa:** *{encontrada}*"]
    if fila is not None:
        partes.append(f"🏘️ Barrio de **{nombre_visible(fila['barrio'])}** ({fila['distrito']}) · "
                      f"{fila['eur_m2']:.1f} €/m² de alquiler")

    coords_trabajo, nombre_trabajo, aviso, ok = resolver_trabajo(zona, direccion_trabajo)
    if not ok:
        partes.append(aviso)
        coords_trabajo = None
    elif coords_trabajo:
        if aviso:
            partes.append(aviso)
        tiempos, dist = trayecto(casa, coords_trabajo)
        destino = "al trabajo" if nombre_trabajo == "tu dirección" else f"a {nombre_trabajo}"
        filas = ["| ¿Cómo? | Tiempo aprox. | Ruta exacta |", "|---|---|---|"]
        for texto, modo in MODOS.items():
            mn = tiempos[modo]
            filas.append(f"| {texto} | **{texto_minutos(mn) if mn is not None else '—'}** | "
                         f"[Ver en Google Maps]({enlace_ruta(casa, coords_trabajo, modo)}) |")
        bloque = (f"### 🏠 → 💼 De casa {destino}\n"
                  f"A **{dist / 1000:.1f} km** en línea recta.\n\n" + "\n".join(filas))
        mn_tp = tiempos["transporte"]
        if mn_tp is not None and pd.notna(mn_tp):
            horas = mn_tp * 2 * DIAS_LABORABLES / 60
            bloque += (f"\n\n⏳ En transporte público son unas **{horas:.0f} horas al año** "
                       f"(ida y vuelta, {DIAS_LABORABLES} días laborables).")
        bloque += ("\n\n*Tiempos calculados desde tu barrio a las 8:30 de un martes; "
                   "Google Maps te da la ruta exacta puerta a puerta.*")
        partes.append(bloque)
    texto_casa = "\n\n".join(partes)

    # ---- Lugares de interés cercanos
    if LUGARES.empty:
        return ("", texto_casa, "⚠️ Faltan los datos de lugares: ejecuta `python scripts/preparar_lugares.py`.",
                pd.DataFrame())
    tipos = [t for t in TIPOS_LUGAR if t in (tipos or [])]
    if not tipos:
        return (mapa_casa(casa, coords_trabajo, radio, lugares_cerca(lat, lon, radio, ["-"])),
                texto_casa, "Marca al menos un tipo de lugar.", pd.DataFrame())
    d = lugares_cerca(lat, lon, radio, tipos)

    min_radio = radio * FACTOR_RODEO / VELOCIDAD_A_PIE
    lineas = [f"### 🧭 Lo que tienes a menos de {radio:,} m (~{min_radio:.0f} min andando)".replace(",", ".")]
    for tipo in tipos:
        sub = d[d["tipo"] == tipo]
        if sub.empty:
            lineas.append(f"- {tipo}: *ninguno tan cerca*")
            continue
        con_nombre = sub[sub["nombre"] != "Sin nombre"]
        p = (con_nombre if not con_nombre.empty else sub).iloc[0]
        lineas.append(
            f"- **{tipo}: {len(sub)}** · el más cercano, *{p['nombre']}*, a {p['min_andando']} min "
            f"([ruta]({enlace_ruta(casa, (p['lat'], p['lon']))}))"
        )
    lineas.append("\n*Distancia andando estimada (línea recta + 30 %). Datos del censo de locales "
                  "del Ayuntamiento de Madrid y de © OpenStreetMap.*")

    tabla = d.groupby("tipo", sort=False).head(MAX_EN_TABLA).copy()
    tabla["orden"] = tabla["tipo"].map({t: i for i, t in enumerate(tipos)})
    tabla = tabla.sort_values(["orden", "dist_m"])
    tabla = pd.DataFrame({
        "Tipo": tabla["tipo"],
        "Nombre": tabla["nombre"],
        "Distancia": tabla["dist_m"].map(lambda m: f"{m:.0f} m"),
        "Andando": tabla["min_andando"].map(lambda m: f"{m} min"),
        "Cómo llegar": [f"[Ver ruta]({enlace_ruta(casa, (a, b))})" for a, b in zip(tabla["lat"], tabla["lon"])],
    })
    return mapa_casa(casa, coords_trabajo, radio, d), texto_casa, "\n".join(lineas), tabla


# ================================================================ isócronas
def isocrona(zona, direccion, modo_texto):
    coords, nombre_trabajo, aviso, ok = resolver_trabajo(zona, direccion)
    if not ok:
        return "", aviso

    modo = MODOS[modo_texto]
    d = B_WGS84.copy()
    d["minutos"] = d["cod_barrio"].map(minutos_hasta(*coords, modo=modo))
    d["color"] = d["minutos"].apply(lambda x: color_por_franja(x, FRANJAS, 90))
    d["minutos_txt"] = d["minutos"].apply(texto_minutos)

    resumen = (
        f"Desde **{nombre_trabajo}**, {modo_texto.lower()}: "
        f"**{(d['minutos'] <= 15).sum()}** barrios a menos de 15 min, "
        f"**{(d['minutos'] <= 30).sum()}** a menos de 30 y "
        f"**{(d['minutos'] <= 45).sum()}** a menos de 45 (de 131)."
    )
    cerca_fiables = d[(d["minutos"] <= 30) & (d["n_viviendas"] >= MIN_VIVIENDAS)]
    if not cerca_fiables.empty:
        barato = cerca_fiables.loc[cerca_fiables["eur_m2"].idxmin()]
        resumen += (
            f"\n\n💡 El barrio más barato a menos de 30 minutos es "
            f"**{nombre_visible(barato['barrio'])}**: {barato['eur_m2']:.1f} €/m² "
            f"y {barato['minutos']:.0f} min."
        )
    if modo == "coche":
        resumen += "\n\n*En coche, sin tráfico: en hora punta los tiempos reales pueden ser bastante mayores.*"
    if aviso:
        resumen = f"{aviso}\n\n{resumen}"

    mapa = mapa_coloreado(d, ["barrio", "distrito", "minutos_txt"],
                          ["Barrio", "Distrito", modo_texto], coords)
    return leyenda(FRANJAS, "Más de 90 min") + mapa, resumen


# ================================================================ pestaña 3: comparador
def comparar(nombre_a, nombre_b, zona, direccion, m2):
    coords, _, aviso, ok = resolver_trabajo(zona, direccion)
    if not ok:
        return None, pd.DataFrame(), aviso

    tiempos = {}
    if coords:
        tiempos = {m: minutos_hasta(*coords, modo=m) for m in ["transporte", "bici", "coche", "andando"]}

    etiquetas = {k: ETIQUETAS[k].capitalize() for k in INDICES}
    if coords:
        etiquetas["transporte"] = "Cerca de tu destino"
    ejes = [etiquetas[k] for k in INDICES]

    fig = go.Figure()
    tabla = {}
    colores = ["#f97316", "#7c3aed"]
    for nombre, color in zip([nombre_a, nombre_b], colores):
        fila = B[B["barrio"] == NOMBRE_A_BARRIO[nombre]].iloc[0]
        cod = fila["cod_barrio"]
        valores = {k: fila[f"idx_{k}"] for k in INDICES}
        datos = {
            "€/m² al mes (2024)": f"{fila['eur_m2']:.1f}",
            f"Alquiler estimado ({m2} m²)": f"{fila['eur_m2'] * m2:.0f} €",
            f"Subida {ANO_BASE}–{ANO_ULTIMO}": f"{fila[COL_SUBIDA]:+.0%}" if pd.notna(fila[COL_SUBIDA]) else "—",
            "Tren más cercano": f"{fila['dist_tren_m']:.0f} m",
        }
        if coords:
            mn = tiempos["transporte"].get(cod)
            if pd.isna(mn):
                valores["transporte"] = 0
                datos["🚇 Transporte público"] = "más de 90 min"
                datos["Horas al año en transporte"] = "—"
            else:
                valores["transporte"] = float(idx_transporte_trabajo(pd.Series([mn])).iloc[0])
                datos["🚇 Transporte público"] = texto_minutos(mn)
                datos["Horas al año en transporte"] = f"{mn * 2 * DIAS_LABORABLES / 60:.0f}"
            datos["🚲 Bici"] = texto_minutos(tiempos["bici"].get(cod))
            datos["🚗 Coche (sin tráfico)"] = texto_minutos(tiempos["coche"].get(cod))
            datos["🚶 Andando"] = texto_minutos(tiempos["andando"].get(cod))
            datos["Cómo llegar"] = f"[Ver ruta en Google Maps]({enlace_google_maps(cod, coords)})"

        r = [valores[k] * 100 for k in INDICES]
        fig.add_trace(go.Scatterpolar(
            r=r + [r[0]], theta=ejes + [ejes[0]], fill="toself", name=nombre,
            line={"color": color, "width": 3}, opacity=0.65,
        ))
        tabla[nombre] = datos

    fig.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, 100]}},
        showlegend=True, height=520, margin={"l": 60, "r": 60, "t": 40, "b": 40},
        legend={"orientation": "h", "y": -0.1}, font={"family": "Poppins, sans-serif"},
    )
    df = pd.DataFrame(tabla).reset_index().rename(columns={"index": ""})
    return fig, df, aviso


# ================================================================ pestaña 4: economía
def calcular_asequibilidad(sueldo, porcentaje, m2, usar_2026):
    if not sueldo or sueldo <= 0:
        return "", "Escribe tu sueldo neto mensual."

    tope = sueldo * porcentaje / 100
    d = asequibilidad(sueldo, m2, usar_2026)
    caben = d[d["esfuerzo"] <= porcentaje]

    texto = (
        f"Con **{sueldo:,.0f} € netos al mes** y dedicando como mucho el **{porcentaje} %** al alquiler, "
        f"tu tope es de **{tope:,.0f} €/mes**. Para {m2} m², te caben **{len(caben)} de {len(d)} barrios**."
    ).replace(",", ".")
    if not caben.empty:
        mejores = ", ".join(f"{r['nombre']} ({r['alquiler']:.0f} €)" for _, r in caben.head(3).iterrows())
        texto += f"\n\n✅ Los más asequibles: {mejores}."
    caros = d.nlargest(3, "esfuerzo")
    texto += "\n\n⚠️ Los que más te costarían: " + ", ".join(
        f"{r['nombre']} (**{r['esfuerzo']:.0f} %** del sueldo)" for _, r in caros.iterrows()
    ) + "."
    texto += "\n\n*Lo habitual es recomendar no dedicar más de un 30–35 % del sueldo neto al alquiler.*"

    mapa_d = B_WGS84.merge(d[["cod_barrio", "alquiler", "esfuerzo"]], on="cod_barrio", how="left")
    mapa_d["color"] = mapa_d["esfuerzo"].apply(lambda x: color_por_franja(x, FRANJAS_ESFUERZO, 1000))
    mapa_d["alquiler_txt"] = mapa_d["alquiler"].apply(lambda x: "sin datos fiables" if pd.isna(x) else f"{x:.0f} €/mes")
    mapa_d["esfuerzo_txt"] = mapa_d["esfuerzo"].apply(lambda x: "—" if pd.isna(x) else f"{x:.0f} % del sueldo")
    mapa = mapa_coloreado(
        mapa_d, ["barrio", "alquiler_txt", "esfuerzo_txt"], ["Barrio", "Alquiler", "Esfuerzo"]
    )
    return leyenda(FRANJAS_ESFUERZO, "Sin datos fiables") + mapa, texto


def comprobar_precio(nombre, m2, precio, usar_2026):
    if not m2 or not precio or m2 <= 0 or precio <= 0:
        return "Escribe los metros y el precio del anuncio."

    barrio = NOMBRE_A_BARRIO[nombre]
    r = rango_precio(BARRIO_A_COD[barrio], m2, usar_2026)
    if pd.isna(r["p25"]) or pd.isna(r["p75"]):
        return f"No tenemos suficientes datos de precios para **{nombre}**."

    if precio < r["p25"]:
        veredicto = "🟢 **Barato para la zona**: más barato que el 75 % de los contratos del barrio."
    elif precio <= r["mediana"]:
        veredicto = "🟢 **Precio normal, tirando a barato**: por debajo de la mediana del barrio."
    elif precio <= r["p75"]:
        veredicto = "🟡 **Precio normal, tirando a caro**: por encima de la mediana, pero dentro de lo habitual."
    elif precio <= r["p75"] * 1.15:
        veredicto = "🟠 **Caro**: más caro que el 75 % de los contratos del barrio."
    else:
        veredicto = "🔴 **Muy caro**: bastante por encima de lo que se paga en el barrio."

    referencia = "estimados para 2026" if usar_2026 else f"de los contratos de {ANO_ULTIMO}"
    dif = precio / r["mediana"] - 1
    texto = (
        f"### {veredicto}\n\n"
        f"En **{nombre}**, para un piso entero de {m2:.0f} m² (precios {referencia}):\n"
        f"- La mitad de los contratos están entre **{r['p25']:.0f} € y {r['p75']:.0f} €/mes**.\n"
        f"- El precio típico (mediana) es de **{r['mediana']:.0f} €/mes**.\n"
        f"- Tu anuncio: **{precio:.0f} €/mes** ({precio / m2:.1f} €/m²), un **{dif:+.0%}** respecto a la mediana."
    )
    if not r["fiable"]:
        texto += "\n\n⚠️ *Este barrio tiene pocos contratos registrados: tómalo con cautela.*"
    texto += (
        "\n\n*Es una referencia: el precio también depende del estado, la planta, si está amueblado, "
        "si tiene terraza o ascensor... Los datos son de contratos declarados, no de anuncios.*"
    )
    return texto


def ver_evolucion(nombres):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=SERIE_MADRID.index, y=SERIE_MADRID.values, name="Madrid (media)",
        line={"color": "#0f172a", "width": 4},
    ))
    lineas = []
    for nombre in nombres or []:
        barrio = NOMBRE_A_BARRIO[nombre]
        fila = B[B["barrio"] == barrio].iloc[0]
        serie = EVOLUCION[EVOLUCION["cod_barrio"] == fila["cod_barrio"]].sort_values("ano")
        fig.add_trace(go.Scatter(x=serie["ano"], y=serie["eur_m2"], mode="lines+markers", name=nombre, line={"width": 3}))
        # Estimación 2026, en línea de puntos
        if pd.notna(fila["eur_m2_estimado_2026"]) and not serie.empty:
            fig.add_trace(go.Scatter(
                x=[serie["ano"].iloc[-1], 2026],
                y=[serie["eur_m2"].iloc[-1], fila["eur_m2_estimado_2026"]],
                mode="lines", line={"dash": "dot"}, name=f"{nombre} (estimación)", showlegend=False,
            ))
        if pd.notna(fila[COL_SUBIDA]):
            linea = (
                f"- **{nombre}**: {fila['eur_m2']:.1f} €/m² en {ANO_ULTIMO}, "
                f"**{fila[COL_SUBIDA]:+.0%}** en {ANO_ULTIMO - ANO_BASE} años "
                f"({fila['subida_anual']:+.1%} al año). Estimación 2026: ~{fila['eur_m2_estimado_2026']:.1f} €/m²."
            )
            if fila["n_viviendas"] < MIN_VIVIENDAS:
                linea += " ⚠️ *Pocos contratos: dato poco fiable.*"
            lineas.append(linea)

    fig.update_layout(
        yaxis_title="€/m² al mes (mediana, pisos)", height=450,
        legend={"orientation": "h", "y": -0.2}, margin={"l": 40, "r": 20, "t": 30, "b": 40},
        font={"family": "Poppins, sans-serif"},
    )

    madrid_sub = SERIE_MADRID.loc[ANO_ULTIMO] / SERIE_MADRID.loc[ANO_BASE] - 1
    texto = f"📈 En toda Madrid, el alquiler ha subido un **{madrid_sub:+.0%}** entre {ANO_BASE} y {ANO_ULTIMO}.\n\n"
    texto += "\n".join(lineas)
    texto += (
        "\n\n*La estimación de 2026 (línea de puntos) prolonga la subida media de los últimos 5 años: "
        "es una extrapolación, no un dato real.*"
    )

    fiables = B[B["n_viviendas"] >= MIN_VIVIENDAS].dropna(subset=[COL_SUBIDA])
    ranking = (
        fiables.nlargest(10, COL_SUBIDA)
        .assign(
            Barrio=lambda x: x["barrio"].map(nombre_visible),
            Distrito=lambda x: x["distrito"],
            **{
                f"Subida {ANO_BASE}–{ANO_ULTIMO}": lambda x: (x[COL_SUBIDA] * 100).round(0).astype(int).astype(str) + " %",
                f"€/m² {ANO_ULTIMO}": lambda x: x["eur_m2"].round(1),
            },
        )[["Barrio", "Distrito", f"Subida {ANO_BASE}–{ANO_ULTIMO}", f"€/m² {ANO_ULTIMO}"]]
    )
    return fig, texto, ranking


# ================================================================ interfaz
# A partir de Gradio 6, el tema y el CSS se pasan a launch() en vez de a Blocks()
GRADIO_6 = int(gr.__version__.split(".")[0]) >= 6
ESTILO = {"theme": TEMA, "css": CSS}

with gr.Blocks(title="¿Dónde vivir en Madrid?", **({} if GRADIO_6 else ESTILO)) as demo:
    gr.HTML(PORTADA)

    gr.HTML('<div class="titulo-seccion">¿Para quién buscas?</div>')
    para_quien = gr.Radio(list(PARA_QUIEN), value="🙋  Para mí", show_label=False, elem_id="para-quien")

    with gr.Tabs(elem_id="pestanas"):
        # ------------------------------------------------ Recomendador
        with gr.Tab("🏠 Encuentra tu barrio"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=1, elem_classes="tarjeta"):
                    gr.Markdown("### 💶 Tu piso")
                    habitaciones = gr.Radio(["Estudio", "1"], value="1", label="Habitaciones")
                    m2 = gr.Slider(25, 150, value=50, step=5, label="Metros cuadrados del piso (ajústalo si quieres)")
                    presupuesto = gr.Slider(300, 3000, value=1000, step=25, label="Presupuesto para el piso (€/mes)")
                    usar_2026 = gr.Checkbox(value=False, label=TEXTO_2026)

                    gr.Markdown("### 📍 ¿A dónde vas cada día?")
                    trabajo = gr.Dropdown(list(ZONAS_TRABAJO), value="Nuevos Ministerios / AZCA",
                                          label="Trabajo o centro de estudios")
                    direccion = gr.Textbox(label=TEXTO_DIRECCION, placeholder=EJEMPLO_DIRECCION)
                    max_minutos = gr.Slider(15, 90, value=45, step=5, label="Tiempo máximo en transporte público (min)")

                    gr.Markdown("### ❤️ Lo que te importa")
                    perfil = gr.Dropdown(list(PERFILES), value="joven", label="Perfil")
                    with gr.Accordion("Ajustar a mano (0 = nada, 3 = mucho)", open=False):
                        sliders = [
                            gr.Slider(0, 3, value=PERFILES["joven"].get(k, 0), step=1,
                                      label=ETIQUETAS[k].capitalize())
                            for k in INDICES
                        ]
                    with gr.Accordion("⏳ Coste real: ¿cuánto vale tu tiempo?", open=False):
                        valor_hora = gr.Slider(0, 30, value=10, step=1, label="Valor de una hora de transporte (€)")
                    boton = gr.Button("🔍 Buscar mi barrio", variant="primary", elem_classes="boton-principal")
                with gr.Column(scale=2):
                    mapa = gr.HTML()
                    resumen = gr.Markdown(elem_classes="resumen")
            tabla = gr.Dataframe(interactive=False, datatype="markdown")

        # ------------------------------------------------ Isócronas
        with gr.Tab("📍 Tu casa y alrededores"):
            with gr.Column(elem_classes="tarjeta"):
                gr.Markdown("### 🏡 Escribe dónde vives (o el piso que estás mirando) y descubre qué tienes cerca")
                with gr.Row():
                    direccion_casa = gr.Textbox(label="Dirección de tu casa", value="Calle de Fuencarral 100",
                                                placeholder="Ej.: Calle de Bravo Murillo 150", scale=2)
                    radio_casa = gr.Slider(300, 2000, value=1000, step=100, scale=1,
                                           label="Distancia máxima (metros)")
                with gr.Row():
                    trabajo_casa = gr.Dropdown(list(ZONAS_TRABAJO), value="Nuevos Ministerios / AZCA",
                                               label="Trabajo o centro de estudios")
                    direccion_trabajo_casa = gr.Textbox(label=TEXTO_DIRECCION, placeholder=EJEMPLO_DIRECCION)
                tipos_casa = gr.CheckboxGroup(list(TIPOS_LUGAR), value=TIPOS_POR_DEFECTO,
                                              label="¿Qué te interesa tener cerca?")
                boton_casa = gr.Button("🔎 Ver qué tengo cerca", variant="primary", elem_classes="boton-principal")
            with gr.Row(equal_height=False):
                with gr.Column(scale=1):
                    texto_casa = gr.Markdown(elem_classes="resumen")
                    resumen_casa = gr.Markdown(elem_classes="resumen")
                with gr.Column(scale=2):
                    mapa_casa_html = gr.HTML()
            tabla_casa = gr.Dataframe(interactive=False, datatype="markdown")

            gr.HTML('<div class="titulo-seccion">🗺️ ¿Desde qué barrios llego rápido?</div>')
            with gr.Column(elem_classes="tarjeta"):
                gr.Markdown("### Elige a dónde vas cada día y cómo te mueves, y mira cuánto tardas desde cada barrio.")
                with gr.Row():
                    trabajo_iso = gr.Dropdown(ZONAS_CON_DIRECCION, value="Nuevos Ministerios / AZCA",
                                              label="Trabajo o centro de estudios")
                    direccion_iso = gr.Textbox(label=TEXTO_DIRECCION, placeholder=EJEMPLO_DIRECCION)
                modo_iso = gr.Radio(list(MODOS), value="🚇 Transporte público", label="¿Cómo te mueves?")
                boton_iso = gr.Button("🗺️ Ver mapa", variant="primary", elem_classes="boton-principal")
            resumen_iso = gr.Markdown(elem_classes="resumen")
            mapa_iso = gr.HTML()

        # ------------------------------------------------ Comparador
        with gr.Tab("⚖️ Comparar barrios"):
            with gr.Column(elem_classes="tarjeta"):
                with gr.Row():
                    barrio_a = gr.Dropdown(list(NOMBRE_A_BARRIO), value="Universidad (Malasaña)", label="Barrio A")
                    barrio_b = gr.Dropdown(list(NOMBRE_A_BARRIO), value="Vista Alegre", label="Barrio B")
                with gr.Row():
                    trabajo_cmp = gr.Dropdown(list(ZONAS_TRABAJO), value="Nuevos Ministerios / AZCA",
                                              label="Trabajo o centro de estudios")
                    direccion_cmp = gr.Textbox(label=TEXTO_DIRECCION, placeholder=EJEMPLO_DIRECCION)
                    m2_cmp = gr.Slider(25, 150, value=60, step=5, label="Metros cuadrados")
                boton_cmp = gr.Button("⚖️ Comparar", variant="primary", elem_classes="boton-principal")
            aviso_cmp = gr.Markdown()
            with gr.Row():
                radar = gr.Plot()
                tabla_cmp = gr.Dataframe(interactive=False, datatype="markdown")

        # ------------------------------------------------ Economía
        with gr.Tab("💶 Economía"):
            with gr.Column(elem_classes="tarjeta"):
                gr.Markdown("## 💰 ¿Cuánto puedo pagar?")
                with gr.Row():
                    sueldo = gr.Number(value=1600, label="Sueldo neto mensual (€)")
                    porcentaje = gr.Slider(20, 50, value=30, step=1, label="% máximo del sueldo para el alquiler")
                    m2_eco = gr.Slider(25, 150, value=50, step=5, label="Metros cuadrados")
                    usar_2026_eco = gr.Checkbox(value=True, label="Precios estimados 2026")
                boton_aseq = gr.Button("Calcular", variant="primary", elem_classes="boton-principal")
            resumen_aseq = gr.Markdown(elem_classes="resumen")
            mapa_aseq = gr.HTML()

            with gr.Column(elem_classes="tarjeta"):
                gr.Markdown("## 🔎 ¿Te están cobrando de más?")
                gr.Markdown("Has visto un piso anunciado: compara su precio con lo que se paga de verdad en el barrio.")
                with gr.Row():
                    barrio_chk = gr.Dropdown(list(NOMBRE_A_BARRIO), value="Embajadores (Lavapiés)", label="Barrio del piso")
                    m2_chk = gr.Number(value=60, label="Metros cuadrados")
                    precio_chk = gr.Number(value=1100, label="Precio del anuncio (€/mes)")
                    usar_2026_chk = gr.Checkbox(value=True, label="Comparar con precios estimados 2026")
                boton_chk = gr.Button("Comprobar", variant="primary", elem_classes="boton-principal")
            resultado_chk = gr.Markdown(elem_classes="resumen")

            with gr.Column(elem_classes="tarjeta"):
                gr.Markdown("## 📈 ¿Cómo ha evolucionado el alquiler?")
                barrios_evo = gr.Dropdown(
                    list(NOMBRE_A_BARRIO),
                    value=["Universidad (Malasaña)", "Embajadores (Lavapiés)", "Vista Alegre"],
                    multiselect=True, max_choices=5, label="Barrios a comparar (hasta 5)",
                )
                boton_evo = gr.Button("Ver evolución", variant="primary", elem_classes="boton-principal")
            grafico_evo = gr.Plot()
            resumen_evo = gr.Markdown(elem_classes="resumen")
            gr.Markdown(f"### 🔥 Los 10 barrios donde más ha subido el alquiler ({ANO_BASE}–{ANO_ULTIMO})")
            ranking_evo = gr.Dataframe(interactive=False)

    gr.Markdown(
        "*Precios: mediana de €/m² de contratos de pisos declarados a Hacienda (SERPAVI), no de "
        "anuncios. El precio por habitación es orientativo (piso entero ÷ habitaciones). La "
        "estimación 2026 prolonga la subida media de los últimos 5 años de cada barrio. Tiempos "
        "calculados con r5py: transporte público con los horarios GTFS del CRTM y la EMT (martes, "
        "salida entre 8:30 y 8:35); bici a velocidad tranquila; coche sin tráfico. Solo hay destinos "
        "dentro del municipio. Direcciones localizadas con Nominatim (© OpenStreetMap); rutas "
        "detalladas en Google Maps. Coste real = alquiler + horas de transporte al año (ida y vuelta, "
        f"{DIAS_LABORABLES} días laborables) valoradas al precio que elijas. Solo se recomiendan "
        f"barrios con al menos {MIN_VIVIENDAS} viviendas alquiladas registradas.*",
        elem_classes="pie",
    )

    # ---------------- Eventos
    entradas = ([para_quien, habitaciones, presupuesto, m2, trabajo, direccion,
                 max_minutos, valor_hora, usar_2026] + sliders)
    entradas_iso = [trabajo_iso, direccion_iso, modo_iso]
    entradas_casa = [direccion_casa, trabajo_casa, direccion_trabajo_casa, radio_casa, tipos_casa]
    salidas_casa = [mapa_casa_html, texto_casa, resumen_casa, tabla_casa]
    entradas_cmp = [barrio_a, barrio_b, trabajo_cmp, direccion_cmp, m2_cmp]
    entradas_aseq = [sueldo, porcentaje, m2_eco, usar_2026_eco]
    entradas_chk = [barrio_chk, m2_chk, precio_chk, usar_2026_chk]

    para_quien.change(cambiar_para_quien, para_quien, [habitaciones, presupuesto, perfil] + sliders)
    habitaciones.change(m2_de_habitaciones, habitaciones, m2)
    perfil.change(pesos_de_perfil, perfil, sliders)

    boton.click(buscar, entradas, [mapa, tabla, resumen])
    direccion.submit(buscar, entradas, [mapa, tabla, resumen])
    boton_casa.click(mi_casa, entradas_casa, salidas_casa)
    direccion_casa.submit(mi_casa, entradas_casa, salidas_casa)
    direccion_trabajo_casa.submit(mi_casa, entradas_casa, salidas_casa)
    boton_iso.click(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    direccion_iso.submit(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    modo_iso.change(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    boton_cmp.click(comparar, entradas_cmp, [radar, tabla_cmp, aviso_cmp])
    direccion_cmp.submit(comparar, entradas_cmp, [radar, tabla_cmp, aviso_cmp])
    boton_aseq.click(calcular_asequibilidad, entradas_aseq, [mapa_aseq, resumen_aseq])
    boton_chk.click(comprobar_precio, entradas_chk, resultado_chk)
    boton_evo.click(ver_evolucion, barrios_evo, [grafico_evo, resumen_evo, ranking_evo])

    demo.load(buscar, entradas, [mapa, tabla, resumen])
    demo.load(mi_casa, entradas_casa, salidas_casa)
    demo.load(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    demo.load(comparar, entradas_cmp, [radar, tabla_cmp, aviso_cmp])
    demo.load(calcular_asequibilidad, entradas_aseq, [mapa_aseq, resumen_aseq])
    demo.load(comprobar_precio, entradas_chk, resultado_chk)
    demo.load(ver_evolucion, barrios_evo, [grafico_evo, resumen_evo, ranking_evo])


if __name__ == "__main__":
    demo.launch(**(ESTILO if GRADIO_6 else {}))