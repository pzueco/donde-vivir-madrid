import html

import folium
import gradio as gr
import pandas as pd
import plotly.graph_objects as go

from recomendador import (
    B, DIAS_LABORABLES, ETIQUETAS, INDICES, PERFILES,
    dentro_de_madrid, enlace_google_maps, geocodificar, idx_transporte_trabajo,
    minutos_hasta, nombre_visible, recomendar,
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

FRANJAS = [
    (15, "Menos de 15 min", "#1a9850"),
    (30, "15–30 min", "#91cf60"),
    (45, "30–45 min", "#fee08b"),
    (60, "45–60 min", "#fc8d59"),
    (90, "60–90 min", "#d73027"),
]
COLOR_LEJOS = "#bdbdbd"

TEXTO_DIRECCION = "…o escribe la dirección de tu trabajo (opcional, solo Madrid capital)"
EJEMPLO_DIRECCION = "Ej.: Calle de Arturo Soria 320"


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


def leyenda_isocrona():
    partes = [
        f'<span style="display:inline-block;width:14px;height:14px;background:{c};'
        f'margin:0 4px 0 12px;vertical-align:middle;"></span>{t}'
        for _, t, c in FRANJAS
    ]
    partes.append(
        f'<span style="display:inline-block;width:14px;height:14px;background:{COLOR_LEJOS};'
        f'margin:0 4px 0 12px;vertical-align:middle;"></span>Más de 90 min'
    )
    return f'<div style="margin-bottom:8px;">{"".join(partes)}</div>'


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


def buscar(presupuesto, m2, zona, direccion, max_minutos, valor_hora, *valores):
    coords, _, aviso, ok = resolver_trabajo(zona, direccion)
    if not ok:
        return "", pd.DataFrame(), aviso

    pesos = dict(zip(INDICES, valores))
    if sum(pesos.values()) == 0:
        return "<p>Sube al menos uno de los deslizadores.</p>", pd.DataFrame(), aviso

    minutos = minutos_hasta(*coords) if coords else None
    res = recomendar(presupuesto, m2, pesos, minutos=minutos,
                     max_minutos=max_minutos, valor_hora=valor_hora)
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
    minutos = minutos_hasta(*coords, modo=modo)

    d = B_WGS84.copy()
    d["minutos"] = d["cod_barrio"].map(minutos)

    def franja(mn):
        if pd.isna(mn) or mn > 90:
            return COLOR_LEJOS
        for tope, _, color in FRANJAS:
            if mn <= tope:
                return color

    d["color"] = d["minutos"].apply(franja)
    d["minutos_txt"] = d["minutos"].apply(texto_minutos)

    m = mapa_base()
    folium.GeoJson(
        d[["barrio", "distrito", "minutos_txt", "color", "geometry"]].to_json(),
        style_function=lambda f: {
            "fillColor": f["properties"]["color"], "color": "white",
            "weight": 0.6, "fillOpacity": 0.75,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["barrio", "distrito", "minutos_txt"],
            aliases=["Barrio", "Distrito", modo_texto],
        ),
    ).add_to(m)
    marcar_trabajo(m, coords)

    resumen = (
        f"Desde **{nombre_trabajo}**, {modo_texto.lower()}: "
        f"**{(d['minutos'] <= 15).sum()}** barrios a menos de 15 min, "
        f"**{(d['minutos'] <= 30).sum()}** a menos de 30 y "
        f"**{(d['minutos'] <= 45).sum()}** a menos de 45 (de 131)."
    )
    cerca_fiables = d[(d["minutos"] <= 30) & (d["n_viviendas"] >= 300)]
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
    return leyenda_isocrona() + a_iframe(m), resumen


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
            "€/m² al mes": f"{fila['eur_m2']:.1f}",
            f"Alquiler estimado ({m2} m²)": f"{fila['eur_m2'] * m2:.0f} €",
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


# ---------------------------------------------------------------- interfaz
with gr.Blocks(title="¿Dónde vivir en Madrid?") as demo:
    gr.Markdown(
        "# 🏠 ¿Dónde vivir en Madrid?\n"
        "Recomendador de barrios según tu presupuesto, dónde trabajas y lo que te importa, "
        "con datos abiertos del Ministerio de Vivienda (SERPAVI 2024), el Consorcio Regional "
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

    gr.Markdown(
        "*Alquiler estimado = mediana de €/m² de contratos de pisos declarados en 2024 × metros: "
        "precio de referencia, normalmente por debajo de los anuncios actuales; pisos completos, "
        "no habitaciones. Tiempos calculados con r5py: transporte público con los horarios GTFS "
        "del CRTM y la EMT (martes, salida entre 8:30 y 8:35); bici a velocidad tranquila y por "
        "calles poco transitadas; coche sin tráfico. Solo hay destinos dentro del municipio; para "
        "una dirección escrita se suma el tramo a pie desde el punto calculado más cercano. "
        "Direcciones localizadas con Nominatim (© OpenStreetMap); rutas detalladas en Google Maps. "
        "Coste real = alquiler + horas de transporte al año (ida y vuelta, "
        f"{DIAS_LABORABLES} días laborables) valoradas al precio que elijas; el abono no se "
        "incluye porque todo el municipio está en la misma zona tarifaria. Solo se recomiendan "
        "barrios con al menos 300 viviendas alquiladas registradas.*"
    )

    # Eventos
    entradas = [presupuesto, m2, trabajo, direccion, max_minutos, valor_hora] + sliders
    entradas_iso = [trabajo_iso, direccion_iso, modo_iso]
    entradas_cmp = [barrio_a, barrio_b, trabajo_cmp, direccion_cmp, m2_cmp]

    habitaciones.change(m2_de_habitaciones, habitaciones, m2)
    perfil.change(pesos_de_perfil, perfil, sliders)

    boton.click(buscar, entradas, [mapa, tabla, resumen])
    direccion.submit(buscar, entradas, [mapa, tabla, resumen])
    boton_iso.click(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    direccion_iso.submit(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    modo_iso.change(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    boton_cmp.click(comparar, entradas_cmp, [radar, tabla_cmp, aviso_cmp])
    direccion_cmp.submit(comparar, entradas_cmp, [radar, tabla_cmp, aviso_cmp])

    demo.load(buscar, entradas, [mapa, tabla, resumen])
    demo.load(isocrona, entradas_iso, [mapa_iso, resumen_iso])
    demo.load(comparar, entradas_cmp, [radar, tabla_cmp, aviso_cmp])


if __name__ == "__main__":
    demo.launch()