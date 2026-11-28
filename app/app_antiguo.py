import html

import folium
import gradio as gr
import pandas as pd
import plotly.graph_objects as go

from recomendador import (
    ANO_BASE, ANO_ULTIMO, B, COL_SUBIDA, DIAS_LABORABLES, ETIQUETAS, EVOLUCION, INDICES,
    MIN_VIVIENDAS, PERFILES, SERIE_MADRID,
    asequibilidad, dentro_de_madrid, enlace_google_maps, geocodificar,
    idx_transporte_trabajo, minutos_hasta, nombre_visible, rango_precio, recomendar,
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

M2_POR_HABITACIONES = {"Estudio": 35, "1": 50, "2": 70, "3": 90, "4 o más": 115}

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

TEXTO_DIRECCION = "…o escribe la dirección de tu trabajo (opcional, solo Madrid capital)"
EJEMPLO_DIRECCION = "Ej.: Calle de Arturo Soria 320"
TEXTO_2026 = "Actualizar precios a 2026 (estimación según la tendencia de cada barrio)"


# ---------------------------------------------------------------- dónde trabajas
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
                "Por ahora solo calculamos trabajos dentro de Madrid capital."
            ), False
        return (lat, lon), "tu dirección", f"📍 Hemos entendido: *{encontrada}*", True
    return ZONAS_TRABAJO[zona], zona, "", True


# ---------------------------------------------------------------- utilidades de mapa
def mapa_base():
    return folium.Map(location=[40.42, -3.70], zoom_start=11, tiles="OpenStreetMap")


def marcar_trabajo(m, coords):
    if coords is not None:
        folium.Marker(
            coords, tooltip="Tu trabajo",
            icon=folium.Icon(color="red", icon="briefcase", prefix="fa"),
        ).add_to(m)


def a_iframe(m):
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
        f'style="width:100%; height:600px; border:none;"></iframe>'
    )


def leyenda(franjas, texto_gris):
    partes = [
        f'<span style="display:inline-block;width:14px;height:14px;background:{c};'
        f'margin:0 4px 0 12px;vertical-align:middle;"></span>{t}'
        for _, t, c in franjas
    ]
    partes.append(
        f'<span style="display:inline-block;width:14px;height:14px;background:{COLOR_GRIS};'
        f'margin:0 4px 0 12px;vertical-align:middle;"></span>{texto_gris}'
    )
    return f'<div style="margin-bottom:8px;">{"".join(partes)}</div>'


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


# ---------------------------------------------------------------- pestaña 1: recomendador
def m2_de_habitaciones(habitaciones):
    return M2_POR_HABITACIONES[habitaciones]


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
            m=m, column="puntuacion", cmap="Greens", legend=True,
            legend_kwds={"caption": "Puntuación"},
            tooltip=tooltip,
            style_kwds={"color": "black", "weight": 1.2, "fillOpacity": 0.7},
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
            f"pero tardas {barato['minutos_trabajo']:.0f} min al trabajo. "
            f"**{cerca['nombre']}** cuesta {dif_euros:.0f} € más al mes y te ahorra "
            f"**{dif_horas:.0f} horas al año** en transporte.\n\n"
        )
    texto += (
        f"Contando tu tiempo a {valor_hora} €/hora, el barrio con menor **coste real** es "
        f"**{mejor['nombre']}**: {mejor['coste_real']:.0f} €/mes entre alquiler y tiempo."
    )
    return texto


def buscar(presupuesto, m2, zona, direccion, max_minutos, valor_hora, usar_2026, *valores):
    coords, _, aviso, ok = resolver_trabajo(zona, direccion)
    if not ok:
        return "", pd.DataFrame(), aviso

    pesos = dict(zip(INDICES, valores))
    if sum(pesos.values()) == 0:
        return "<p>Sube al menos uno de los deslizadores.</p>", pd.DataFrame(), aviso

    minutos = minutos_hasta(*coords) if coords else None
    res = recomendar(presupuesto, m2, pesos, minutos=minutos, max_minutos=max_minutos,
                     valor_hora=valor_hora, usar_2026=usar_2026)
    if res.empty:
        return (
            "<p>No hay barrios que cumplan todo a la vez. Prueba a subir el presupuesto, "
            "bajar los metros o aceptar más minutos hasta el trabajo.</p>",
            pd.DataFrame(), aviso,
        )

    tabla = res.drop(columns="geometry").copy()
    if coords:
        tabla["como_llegar"] = tabla["cod_barrio"].map(
            lambda c: f"[Ver ruta]({enlace_google_maps(c, coords)})"
        )
    tabla = (
        tabla.drop(columns="cod_barrio")
        .rename(columns={
            "nombre": "Barrio",
            "distrito": "Distrito",
            "puntuacion": "Puntuación",
            "alquiler_estimado": "Alquiler estimado (€)",
            "minutos_trabajo": "Minutos al trabajo",
            "horas_ano": "Horas al año en transporte",
            "coste_real": "Coste real (€/mes)",
            "por_que": "Por qué",
            "dist_tren_m": "Tren más cercano (m)",
            "como_llegar": "Cómo llegar",
        })
        .astype(str)
    )
    resumen = "\n\n".join(t for t in [aviso, resumen_coste(res, valor_hora)] if t)
    return mapa_recomendacion(res, coords), tabla, resumen


# ---------------------------------------------------------------- pestaña 2: isócronas
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
            f"\n\nEl barrio más barato a menos de 30 minutos es "
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


# ---------------------------------------------------------------- pestaña 3: comparador
def comparar(nombre_a, nombre_b, zona, direccion, m2):
    coords, _, aviso, ok = resolver_trabajo(zona, direccion)
    if not ok:
        return None, pd.DataFrame(), aviso

    tiempos = {}
    if coords:
        tiempos = {m: minutos_hasta(*coords, modo=m) for m in ["transporte", "bici", "coche", "andando"]}

    etiquetas = {k: ETIQUETAS[k].capitalize() for k in INDICES}
    if coords:
        etiquetas["transporte"] = "Cerca de tu trabajo"
    ejes = [etiquetas[k] for k in INDICES]

    fig = go.Figure()
    tabla = {}
    for nombre in [nombre_a, nombre_b]:
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
            r=r + [r[0]], theta=ejes + [ejes[0]], fill="toself", name=nombre, opacity=0.6,
        ))
        tabla[nombre] = datos

    fig.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, 100]}},
        showlegend=True, height=520, margin={"l": 60, "r": 60, "t": 40, "b": 40},
        legend={"orientation": "h", "y": -0.1},
    )
    df = pd.DataFrame(tabla).reset_index().rename(columns={"index": ""})
    return fig, df, aviso


# ---------------------------------------------------------------- pestaña 4: economía
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
        texto += f"\n\nLos más asequibles: {mejores}."
    caros = d.nlargest(3, "esfuerzo")
    texto += "\n\nLos que más te costarían: " + ", ".join(
        f"{r['nombre']} (**{r['esfuerzo']:.0f} %** del sueldo)" for _, r in caros.iterrows()
    ) + "."
    texto += (
        "\n\n*Lo habitual es recomendar no dedicar más de un 30–35 % del sueldo neto al alquiler.*"
    )

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
        f"{veredicto}\n\n"
        f"En **{nombre}**, para {m2:.0f} m² (precios {referencia}):\n"
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
        line={"color": "black", "width": 4},
    ))
    lineas = []
    for nombre in nombres or []:
        barrio = NOMBRE_A_BARRIO[nombre]
        fila = B[B["barrio"] == barrio].iloc[0]
        serie = EVOLUCION[EVOLUCION["cod_barrio"] == fila["cod_barrio"]].sort_values("ano")
        traza = fig.add_trace(go.Scatter(x=serie["ano"], y=serie["eur_m2"], mode="lines+markers", name=nombre))
        # Estimación 2026, en línea discontinua
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
    )

    madrid_sub = SERIE_MADRID.loc[ANO_ULTIMO] / SERIE_MADRID.loc[ANO_BASE] - 1
    texto = f"En toda Madrid, el alquiler ha subido un **{madrid_sub:+.0%}** entre {ANO_BASE} y {ANO_ULTIMO}.\n\n"
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


# ---------------------------------------------------------------- interfaz
with gr.Blocks(title="¿Dónde vivir en Madrid?") as demo:
    gr.Markdown(
        "# 🏠 ¿Dónde vivir en Madrid?\n"
        "Recomendador de barrios según tu presupuesto, dónde trabajas y lo que te importa, "
        "con datos abiertos del Ministerio de Vivienda (SERPAVI), el Consorcio Regional "
        "de Transportes, la EMT, OpenStreetMap y el Ayuntamiento de Madrid."
    )

    with gr.Tabs():
        # ------------------------------------------------ Recomendador
        with gr.Tab("🏠 Recomendador"):
            with gr.Row():
                with gr.Column(scale=1):
                    presupuesto = gr.Slider(500, 3000, value=1000, step=50, label="Presupuesto mensual (€)")
                    habitaciones = gr.Radio(list(M2_POR_HABITACIONES), value="1", label="Habitaciones")
                    m2 = gr.Slider(25, 150, value=50, step=5, label="Metros cuadrados (ajústalo si quieres)")
                    usar_2026 = gr.Checkbox(value=False, label=TEXTO_2026)
                    trabajo = gr.Dropdown(list(ZONAS_TRABAJO), value="Nuevos Ministerios / AZCA", label="¿Dónde trabajas?")
                    direccion = gr.Textbox(label=TEXTO_DIRECCION, placeholder=EJEMPLO_DIRECCION)
                    max_minutos = gr.Slider(15, 90, value=45, step=5, label="Tiempo máximo al trabajo en transporte público (min)")
                    perfil = gr.Dropdown(list(PERFILES), value="joven", label="Perfil")
                    with gr.Accordion("Ajustar lo que te importa (0 = nada, 3 = mucho)", open=False):
                        sliders = [
                            gr.Slider(0, 3, value=PERFILES["joven"].get(k, 0), step=1,
                                      label=ETIQUETAS[k].capitalize())
                            for k in INDICES
                        ]
                    with gr.Accordion("Coste real: ¿cuánto vale tu tiempo?", open=False):
                        valor_hora = gr.Slider(0, 30, value=10, step=1, label="Valor de una hora de transporte (€)")
                    boton = gr.Button("Buscar barrios", variant="primary")
                with gr.Column(scale=2):
                    mapa = gr.HTML()
            resumen = gr.Markdown()
            tabla = gr.Dataframe(interactive=False, datatype="markdown")

        # ------------------------------------------------ Isócronas
        with gr.Tab("⏱️ ¿Qué tengo cerca?"):
            gr.Markdown("Elige dónde trabajas y cómo te mueves, y mira cuánto tardas desde cada barrio de Madrid.")
            with gr.Row():
                trabajo_iso = gr.Dropdown(ZONAS_CON_DIRECCION, value="Nuevos Ministerios / AZCA", label="¿Dónde trabajas?")
                direccion_iso = gr.Textbox(label=TEXTO_DIRECCION, placeholder=EJEMPLO_DIRECCION)
            modo_iso = gr.Radio(list(MODOS), value="🚇 Transporte público", label="¿Cómo te mueves?")
            boton_iso = gr.Button("Ver mapa", variant="primary")
            resumen_iso = gr.Markdown()
            mapa_iso = gr.HTML()

        # ------------------------------------------------ Comparador
        with gr.Tab("⚖️ Comparar barrios"):
            with gr.Row():
                barrio_a = gr.Dropdown(list(NOMBRE_A_BARRIO), value="Universidad (Malasaña)", label="Barrio A")
                barrio_b = gr.Dropdown(list(NOMBRE_A_BARRIO), value="Vista Alegre", label="Barrio B")
            with gr.Row():
                trabajo_cmp = gr.Dropdown(list(ZONAS_TRABAJO), value="Nuevos Ministerios / AZCA", label="¿Dónde trabajas?")
                direccion_cmp = gr.Textbox(label=TEXTO_DIRECCION, placeholder=EJEMPLO_DIRECCION)
                m2_cmp = gr.Slider(25, 150, value=60, step=5, label="Metros cuadrados")
            boton_cmp = gr.Button("Comparar", variant="primary")
            aviso_cmp = gr.Markdown()
            with gr.Row():
                radar = gr.Plot()
                tabla_cmp = gr.Dataframe(interactive=False, datatype="markdown")

        # ------------------------------------------------ Economía
        with gr.Tab("💶 Economía"):
            gr.Markdown("## 💰 ¿Cuánto puedo pagar?")
            with gr.Row():
                sueldo = gr.Number(value=1600, label="Sueldo neto mensual (€)")
                porcentaje = gr.Slider(20, 50, value=30, step=1, label="% máximo del sueldo para el alquiler")
                m2_eco = gr.Slider(25, 150, value=50, step=5, label="Metros cuadrados")
                usar_2026_eco = gr.Checkbox(value=True, label="Precios estimados 2026")
            boton_aseq = gr.Button("Calcular", variant="primary")
            resumen_aseq = gr.Markdown()
            mapa_aseq = gr.HTML()

            gr.Markdown("## 🔎 ¿Te están cobrando de más?")
            gr.Markdown("Has visto un piso anunciado: compara su precio con lo que se paga de verdad en el barrio.")
            with gr.Row():
                barrio_chk = gr.Dropdown(list(NOMBRE_A_BARRIO), value="Embajadores (Lavapiés)", label="Barrio del piso")
                m2_chk = gr.Number(value=60, label="Metros cuadrados")
                precio_chk = gr.Number(value=1100, label="Precio del anuncio (€/mes)")
                usar_2026_chk = gr.Checkbox(value=True, label="Comparar con precios estimados 2026")
            boton_chk = gr.Button("Comprobar", variant="primary")
            resultado_chk = gr.Markdown()

            gr.Markdown("## 📈 ¿Cómo ha evolucionado el alquiler?")
            barrios_evo = gr.Dropdown(
                list(NOMBRE_A_BARRIO),
                value=["Universidad (Malasaña)", "Embajadores (Lavapiés)", "Vista Alegre"],
                multiselect=True, max_choices=5, label="Barrios a comparar (hasta 5)",
            )
            boton_evo = gr.Button("Ver evolución", variant="primary")
            grafico_evo = gr.Plot()
            resumen_evo = gr.Markdown()
            gr.Markdown(f"### Los 10 barrios donde más ha subido el alquiler ({ANO_BASE}–{ANO_ULTIMO})")
            ranking_evo = gr.Dataframe(interactive=False)

    gr.Markdown(
        "*Precios: mediana de €/m² de contratos de pisos declarados a Hacienda (SERPAVI), no de "
        "anuncios; pisos completos, no habitaciones. La estimación 2026 prolonga la subida media "
        "de los últimos 5 años de cada barrio. Tiempos calculados con r5py: transporte público con "
        "los horarios GTFS del CRTM y la EMT (martes, salida entre 8:30 y 8:35); bici a velocidad "
        "tranquila y por calles poco transitadas; coche sin tráfico. Solo hay destinos dentro del "
        "municipio. Direcciones localizadas con Nominatim (© OpenStreetMap); rutas detalladas en "
        "Google Maps. Coste real = alquiler + horas de transporte al año (ida y vuelta, "
        f"{DIAS_LABORABLES} días laborables) valoradas al precio que elijas. Solo se recomiendan "
        f"barrios con al menos {MIN_VIVIENDAS} viviendas alquiladas registradas.*"
    )

    # Eventos
    entradas = [presupuesto, m2, trabajo, direccion, max_minutos, valor_hora, usar_2026] + sliders
    entradas_iso = [trabajo_iso, direccion_iso, modo_iso]
    entradas_cmp = [barrio_a, barrio_b, trabajo_cmp, direccion_cmp, m2_cmp]
    entradas_aseq = [sueldo, porcentaje, m2_eco, usar_2026_eco]
    entradas_chk = [barrio_chk, m2_chk, precio_chk, usar_2026_chk]

    habitaciones.change(m2_de_habitaciones, habitaciones, m2)
    perfil.change(pesos_de_perfil, perfil, sliders)

    boton.click(buscar, entradas, [mapa, tabla, resumen])
    direccion.submit(buscar, entradas, [mapa, tabla, resumen])
    boton_iso.click(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    direccion_iso.submit(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    modo_iso.change(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    boton_cmp.click(comparar, entradas_cmp, [radar, tabla_cmp, aviso_cmp])
    direccion_cmp.submit(comparar, entradas_cmp, [radar, tabla_cmp, aviso_cmp])
    boton_aseq.click(calcular_asequibilidad, entradas_aseq, [mapa_aseq, resumen_aseq])
    boton_chk.click(comprobar_precio, entradas_chk, resultado_chk)
    boton_evo.click(ver_evolucion, barrios_evo, [grafico_evo, resumen_evo, ranking_evo])

    demo.load(buscar, entradas, [mapa, tabla, resumen])
    demo.load(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    demo.load(comparar, entradas_cmp, [radar, tabla_cmp, aviso_cmp])
    demo.load(calcular_asequibilidad, entradas_aseq, [mapa_aseq, resumen_aseq])
    demo.load(comprobar_precio, entradas_chk, resultado_chk)
    demo.load(ver_evolucion, barrios_evo, [grafico_evo, resumen_evo, ranking_evo])


if __name__ == "__main__":
    demo.launch()