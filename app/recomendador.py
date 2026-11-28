from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

CARPETA = Path(__file__).parent / "data"

B = gpd.read_parquet(CARPETA / "barrios_indices.parquet")
# Simplificar las formas (tolerancia de 15 m): el mapa pesa mucho menos y no se nota
B["geometry"] = B.simplify(15, preserve_topology=True)

# Tiempos en transporte público (r5py, martes 8:30) desde cada barrio a una rejilla de puntos
TIEMPOS = pd.read_parquet(CARPETA / "tiempos_barrio.parquet")
REJILLA = gpd.read_parquet(CARPETA / "rejilla_destinos.parquet").to_crs(25830)

DIAS_LABORABLES = 220

INDICES = ["precio", "transporte", "ocio", "tranquilidad", "cultura",
           "salud", "familia", "deporte", "dia_a_dia"]

PERFILES = {
    "joven":       {"precio": 2, "transporte": 3, "ocio": 3, "deporte": 1, "dia_a_dia": 1},
    "familia":     {"precio": 1, "transporte": 2, "familia": 3, "salud": 2, "tranquilidad": 2, "dia_a_dia": 1},
    "teletrabajo": {"precio": 2, "tranquilidad": 2, "dia_a_dia": 2, "ocio": 1, "deporte": 1},
    "deportista":  {"precio": 1, "transporte": 2, "deporte": 3, "tranquilidad": 1},
    "cultura":     {"precio": 1, "transporte": 2, "cultura": 3, "ocio": 1},
}

NOMBRES_POPULARES = {
    "Universidad": "Malasaña",
    "Embajadores": "Lavapiés",
    "Justicia": "Chueca",
    "Cortes": "Huertas",
    "Palacio": "Ópera / La Latina",
}

ETIQUETAS = {
    "precio": "buen precio", "transporte": "bien conectado", "ocio": "mucho ambiente",
    "tranquilidad": "tranquilo", "cultura": "oferta cultural", "salud": "servicios de salud",
    "familia": "para familias", "deporte": "deporte", "dia_a_dia": "comercio cercano",
}


def nombre_visible(barrio):
    return f"{barrio} ({NOMBRES_POPULARES[barrio]})" if barrio in NOMBRES_POPULARES else barrio


def minutos_hasta(lat, lon):
    """Minutos en transporte público desde cada barrio hasta el punto (lat, lon)."""
    punto = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(25830).iloc[0]
    destino = REJILLA.loc[REJILLA.distance(punto).idxmin(), "id"]
    t = TIEMPOS[TIEMPOS["id_destino"] == destino]
    return t.set_index("cod_barrio")["minutos"]


def idx_transporte_trabajo(minutos):
    """10 min o menos = 1 · 60 min o más = 0."""
    return (1 - (minutos - 10) / 50).clip(0, 1)


def coste_tiempo(minutos, valor_hora):
    """Horas al año en transporte (ida y vuelta) y su coste mensual en euros."""
    horas_ano = minutos * 2 * DIAS_LABORABLES / 60
    return horas_ano.round(0), (horas_ano * valor_hora / 12).round(0)


def recomendar(presupuesto, m2, pesos, minutos=None, max_minutos=None, valor_hora=10,
               n=10, min_viviendas=300, factor_precio=1.0, holgura_max=0.30):
    pesos = {k: w for k, w in pesos.items() if w > 0}
    etiquetas = dict(ETIQUETAS)

    d = B.copy()
    d["alquiler_estimado"] = (d["eur_m2"] * m2 * factor_precio).round(0)
    d = d[(d["alquiler_estimado"] <= presupuesto) & (d["n_viviendas"] >= min_viviendas)].copy()

    # Tiempo hasta el trabajo: filtra, sustituye al índice de transporte y da el coste real
    if minutos is not None:
        d["minutos_trabajo"] = d["cod_barrio"].map(minutos)
        d = d[d["minutos_trabajo"] <= max_minutos].copy()
        d["idx_transporte"] = idx_transporte_trabajo(d["minutos_trabajo"])
        d["horas_ano"], d["coste_tiempo_mes"] = coste_tiempo(d["minutos_trabajo"], valor_hora)
        d["coste_real"] = d["alquiler_estimado"] + d["coste_tiempo_mes"]
        etiquetas["transporte"] = "cerca de tu trabajo"

    if d.empty or not pesos:
        return d

    holgura = 1 - d["alquiler_estimado"] / presupuesto
    d["idx_precio"] = holgura.clip(0, holgura_max) / holgura_max

    suma = sum(pesos.values())
    d["puntuacion"] = (sum(w * d[f"idx_{k}"] for k, w in pesos.items()) / suma * 100).round(1)

    def motivos(fila):
        ordenados = sorted(pesos, key=lambda k: fila[f"idx_{k}"], reverse=True)
        fuertes = [etiquetas[k] for k in ordenados if fila[f"idx_{k}"] >= 0.7][:2]
        return ", ".join(fuertes) if fuertes else "equilibrado en todo"

    d["por_que"] = d.apply(motivos, axis=1)
    d["nombre"] = d["barrio"].map(nombre_visible)

    cols = ["nombre", "distrito", "puntuacion", "alquiler_estimado"]
    if minutos is not None:
        cols += ["minutos_trabajo", "horas_ano", "coste_real"]
    cols += ["por_que", "dist_tren_m", "geometry"]
    return d.sort_values("puntuacion", ascending=False)[cols].head(n)