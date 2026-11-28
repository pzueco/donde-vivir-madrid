from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd
from geopy.geocoders import Nominatim
from shapely.geometry import Point

CARPETA = Path(__file__).parent / "data"

B = gpd.read_parquet(CARPETA / "barrios_indices.parquet")
# Simplificar las formas (tolerancia de 15 m): el mapa pesa mucho menos y no se nota
B["geometry"] = B.simplify(15, preserve_topology=True)

# Un punto dentro de cada barrio (origen de las rutas)
_PUNTOS = B.representative_point().to_crs(4326)
PUNTO_BARRIO = {c: (p.y, p.x) for c, p in zip(B["cod_barrio"], _PUNTOS)}

# Tiempos desde cada barrio a una rejilla de puntos (r5py, martes 8:30)
TIEMPOS = pd.read_parquet(CARPETA / "tiempos_barrio.parquet")            # transporte público
OTROS_MODOS = pd.read_parquet(CARPETA / "tiempos_otros_modos.parquet")   # bici, coche, andando
REJILLA = gpd.read_parquet(CARPETA / "rejilla_destinos.parquet").to_crs(25830)

# Contorno del municipio, para comprobar si una dirección está dentro
MADRID_4326 = B.to_crs(4326).union_all()
_XMIN, _YMIN, _XMAX, _YMAX = MADRID_4326.bounds

# Geocodificador de OpenStreetMap (gratuito; máximo una consulta por segundo)
_GEOLOCALIZADOR = Nominatim(
    user_agent="donde-vivir-madrid (github.com/pzueco/donde-vivir-madrid)", timeout=10
)

DIAS_LABORABLES = 220
VELOCIDAD_A_PIE = 80  # metros por minuto

COLUMNA_MODO = {"bici": "min_bici", "coche": "min_coche", "andando": "min_andando"}
MODO_GOOGLE = {"transporte": "transit", "bici": "bicycling", "coche": "driving", "andando": "walking"}

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


@lru_cache(maxsize=500)
def geocodificar(texto):
    """Convierte una dirección en (lat, lon, dirección encontrada). None si no la encuentra."""
    texto = texto.strip()
    if not texto:
        return None
    consulta = texto if "madrid" in texto.lower() else f"{texto}, Madrid"
    try:
        r = _GEOLOCALIZADOR.geocode(
            consulta, country_codes="es", language="es",
            viewbox=[(_YMIN, _XMIN), (_YMAX, _XMAX)], bounded=False,
        )
    except Exception:
        return None
    if r is None:
        return None
    return r.latitude, r.longitude, r.address


def dentro_de_madrid(lat, lon):
    return MADRID_4326.contains(Point(lon, lat))


def _destino_cercano(lat, lon):
    """Punto de la rejilla más cercano y minutos a pie desde él hasta (lat, lon)."""
    punto = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(25830).iloc[0]
    distancias = REJILLA.distance(punto)
    i = distancias.idxmin()
    return REJILLA.loc[i, "id"], round(distancias.loc[i] / VELOCIDAD_A_PIE)


def minutos_hasta(lat, lon, modo="transporte"):
    """Minutos desde cada barrio hasta (lat, lon): transporte, bici, coche o andando."""
    destino, extra = _destino_cercano(lat, lon)
    if modo == "transporte":
        t = TIEMPOS[TIEMPOS["id_destino"] == destino].set_index("cod_barrio")["minutos"]
    else:
        t = OTROS_MODOS[OTROS_MODOS["id_destino"] == destino].set_index("cod_barrio")[COLUMNA_MODO[modo]]
    return t + extra


def enlace_google_maps(cod_barrio, destino, modo="transporte"):
    """Enlace a la ruta en Google Maps desde el barrio hasta el destino (lat, lon)."""
    lat_o, lon_o = PUNTO_BARRIO[cod_barrio]
    lat_d, lon_d = destino
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={lat_o:.5f},{lon_o:.5f}&destination={lat_d:.5f},{lon_d:.5f}"
        f"&travelmode={MODO_GOOGLE[modo]}"
    )


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

    cols = ["cod_barrio", "nombre", "distrito", "puntuacion", "alquiler_estimado"]
    if minutos is not None:
        cols += ["minutos_trabajo", "horas_ano", "coste_real"]
    cols += ["por_que", "dist_tren_m", "geometry"]
    return d.sort_values("puntuacion", ascending=False)[cols].head(n)