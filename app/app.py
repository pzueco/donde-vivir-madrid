import html

import folium
import gradio as gr
import pandas as pd

from recomendador import B, ETIQUETAS, INDICES, PERFILES, recomendar

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


def m2_de_habitaciones(habitaciones):
    return M2_POR_HABITACIONES[habitaciones]


def pesos_de_perfil(perfil):
    return [PERFILES[perfil].get(k, 0) for k in INDICES]


def hacer_mapa(res):
    m = folium.Map(location=[40.42, -3.70], zoom_start=11, tiles="OpenStreetMap")

    # Todos los barrios en gris, de fondo
    B_WGS84.explore(
        m=m, color="#888888", tooltip=["barrio", "distrito"],
        style_kwds={"fillOpacity": 0.05, "weight": 0.5},
    )

    # Los recomendados, coloreados por puntuación
    if not res.empty:
        res.to_crs(4326).explore(
            m=m, column="puntuacion", cmap="Greens", legend=True,
            legend_kwds={"caption": "Puntuación"},
            tooltip=["nombre", "puntuacion", "alquiler_estimado", "por_que"],
            style_kwds={"color": "black", "weight": 1.2, "fillOpacity": 0.7},
        )

    # Encuadrar Madrid
    xmin, ymin, xmax, ymax = B_WGS84.total_bounds
    m.fit_bounds([[ymin, xmin], [ymax, xmax]])

    # Recuadro de tamaño fijo para que el mapa calcule bien el zoom
    pagina = m.get_root().render()
    return (
        f'<iframe srcdoc="{html.escape(pagina)}" '
        f'style="width:100%; height:600px; border:none;"></iframe>'
    )


def buscar(presupuesto, m2, *valores):
    pesos = dict(zip(INDICES, valores))
    if sum(pesos.values()) == 0:
        return "<p>Sube al menos uno de los deslizadores.</p>", pd.DataFrame()

    res = recomendar(presupuesto, m2, pesos)
    if res.empty:
        return (
            "<p>No hay barrios con datos fiables para ese presupuesto. "
            "Prueba a subirlo o a bajar los metros.</p>",
            pd.DataFrame(),
        )

    tabla = (
        res.drop(columns="geometry")
        .rename(columns={
            "nombre": "Barrio",
            "distrito": "Distrito",
            "puntuacion": "Puntuación",
            "alquiler_estimado": "Alquiler estimado (€)",
            "por_que": "Por qué",
            "dist_tren_m": "Tren más cercano (m)",
        })
    )
    return hacer_mapa(res), tabla


with gr.Blocks(title="¿Dónde vivir en Madrid?") as demo:
    gr.Markdown(
        "# 🏠 ¿Dónde vivir en Madrid?\n"
        "Recomendador de barrios según tu presupuesto y lo que te importa, "
        "con datos abiertos del Ministerio de Vivienda (SERPAVI 2024), "
        "OpenStreetMap y el Ayuntamiento de Madrid."
    )

    with gr.Row():
        with gr.Column(scale=1):
            presupuesto = gr.Slider(500, 3000, value=1000, step=50, label="Presupuesto mensual (€)")
            habitaciones = gr.Radio(list(M2_POR_HABITACIONES), value="1", label="Habitaciones")
            m2 = gr.Slider(25, 150, value=50, step=5, label="Metros cuadrados (ajústalo si quieres)")
            perfil = gr.Dropdown(list(PERFILES), value="joven", label="Perfil")
            with gr.Accordion("Ajustar lo que te importa (0 = nada, 3 = mucho)", open=False):
                sliders = [
                    gr.Slider(
                        0, 3, value=PERFILES["joven"].get(k, 0), step=1,
                        label=ETIQUETAS[k].capitalize(),
                    )
                    for k in INDICES
                ]
            boton = gr.Button("Buscar barrios", variant="primary")

        with gr.Column(scale=2):
            mapa = gr.HTML()

    tabla = gr.Dataframe(interactive=False)

    gr.Markdown(
        "*Alquiler estimado = mediana de €/m² de contratos de pisos declarados en 2024 × metros. "
        "Es un precio de referencia: los anuncios actuales suelen ser más caros. "
        "Los precios son de pisos completos, no de habitaciones en piso compartido. "
        "Los metros por número de habitaciones son aproximados. "
        "Solo se muestran barrios con al menos 300 viviendas alquiladas registradas.*"
    )

    habitaciones.change(m2_de_habitaciones, habitaciones, m2)
    perfil.change(pesos_de_perfil, perfil, sliders)
    boton.click(buscar, [presupuesto, m2] + sliders, [mapa, tabla])
    demo.load(buscar, [presupuesto, m2] + sliders, [mapa, tabla])


if __name__ == "__main__":
    demo.launch()