import re
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd
from geopy.geocoders import Nominatim
from shapely.geometry import Point

CARPETA = Path(__file__).parent / "data"
MIN_VIVIENDAS = 300  # menos viviendas alquiladas = dato de precio poco fiable

# ---------------------------------------------------------------- barrios
B = gpd.read_parquet(CARPETA / "barrios_indices.parquet")
# Simplificar las formas (tolerancia de 15 m): el mapa pesa mucho menos y no se nota
B["geometry"] = B.simplify(15, preserve_topology=True)

# Economía: rango de precios (p25-p75), tendencia y estimación 2026
B = B.merge(pd.read_parquet(CARPETA / "barrios_economia.parquet"), on="cod_barrio", how="left")
B["eur_m2_2026"] = B["eur_m2_estimado_2026"].fillna(B["eur_m2"])
COL_SUBIDA = next(c for c in B.columns if re.fullmatch(r"subida_\d{4}_\d{4}", c))
ANO_BASE, ANO_ULTIMO = map(int, COL_SUBIDA.split("_")[1:])

# Evolución del alquiler por barrio y media de Madrid (ponderada por viviendas)
EVOLUCION = pd.read_parquet(CARPETA / "evolucion_alquiler.parquet")
_tot = (
    EVOLUCION.assign(ponderado=EVOLUCION["eur_m2"] * EVOLUCION["n_viviendas"])
    .groupby("ano")[["ponderado", "n_viviendas"]].sum()
)
SERIE_MADRID = (_tot["ponderado"] / _tot["n_viviendas"]).round(2)

# Un punto dentro de cada barrio (origen de las rutas)
_PUNTOS = B.representative_point().to_crs(4326)
PUNTO_BARRIO = {c: (p.y, p.x) for c, p in zip(B["cod_barrio"], _PUNTOS)}

# ---------------------------------------------------------------- tiempos
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

# ---------------------------------------------------------------- lugares de interés
# Se genera con scripts/preparar_lugares.py (categoria, nombre, x, y en metros, lat, lon).
# Bares, restaurantes, discotecas, supermercados, farmacias, gimnasios y veterinarios vienen del
# censo de locales del Ayuntamiento + lo que solo está en OpenStreetMap (notebook 09).
_RUTA_LUGARES = CARPETA / "lugares.parquet"
LUGARES = (
    pd.read_parquet(_RUTA_LUGARES) if _RUTA_LUGARES.exists()
    else pd.DataFrame(columns=["categoria", "nombre", "x", "y", "lat", "lon"])
)
FACTOR_RODEO = 1.3  # por la calle se anda un ~30 % más que en línea recta

# Tipo que se muestra → categorías de OpenStreetMap que lo forman
TIPOS_LUGAR = {
    "🍺 Bares y cafeterías": ["bares_cafeterias"],
    "🍽️ Restaurantes": ["restaurantes"],
    "🌞 Terrazas": ["terrazas"],
    "🪩 Discotecas y bares de copas": ["discotecas"],
    "🛍️ Centros comerciales": ["centros_comerciales"],
    "🗿 Monumentos y lugares de interés": ["monumentos"],
    "🏛️ Museos": ["museos"],
    "🎭 Cines y teatros": ["cines_teatros"],
    "📚 Bibliotecas": ["bibliotecas"],
    "🌳 Parques": ["parques"],
    "⚽ Campos de fútbol": ["campos_futbol"],
    "🎾 Tenis y pádel": ["pistas_tenis_padel"],
    "💪 Gimnasios": ["gimnasios"],
    "🏊 Piscinas": ["piscinas"],
    "🛒 Supermercados y mercados": ["supermercados", "mercados"],
    "💊 Farmacias": ["farmacias"],
    "🏥 Centros de salud y hospitales": ["centros_salud", "hospitales"],
    "🏫 Colegios y guarderías": ["colegios", "guarderias"],
    "🛝 Parques infantiles": ["parques_infantiles"],
    "🐶 Veterinarios y parques para perros": ["veterinarios", "parques_perros"],
    "💻 Coworkings": ["coworkings"],
    "🚇 Metro, Cercanías y Metro Ligero": ["estaciones_metro", "estaciones_cercanias", "estaciones_metro_ligero"],
    "🚌 Paradas de bus": ["paradas_bus"],
    "🚲 BiciMAD": ["estaciones_bicimad"],
}
TIPO_DE_CATEGORIA = {c: t for t, cats in TIPOS_LUGAR.items() for c in cats}

INDICES = ["precio", "transporte", "ocio", "tranquilidad", "cultura",
           "salud", "familia", "deporte", "dia_a_dia"]

PERFILES = {
    "joven":       {"precio": 2, "transporte": 3, "ocio": 3, "deporte": 1, "dia_a_dia": 1},
    "familia":     {"precio": 1, "transporte": 2, "familia": 3, "salud": 2, "tranquilidad": 2, "dia_a_dia": 1},
    "estudiante":  {"precio": 3, "transporte": 3, "ocio": 2, "cultura": 1, "dia_a_dia": 1},
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


def columna_precio(usar_2026):
    return "eur_m2_2026" if usar_2026 else "eur_m2"


# ---------------------------------------------------------------- direcciones
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


# ---------------------------------------------------------------- tiempos
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


def enlace_ruta(origen, destino, modo="andando"):
    """Enlace a la ruta en Google Maps entre dos puntos (lat, lon)."""
    lat_o, lon_o = origen
    lat_d, lon_d = destino
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={lat_o:.5f},{lon_o:.5f}&destination={lat_d:.5f},{lon_d:.5f}"
        f"&travelmode={MODO_GOOGLE[modo]}"
    )


def enlace_google_maps(cod_barrio, destino, modo="transporte"):
    """Enlace a la ruta en Google Maps desde el barrio hasta el destino (lat, lon)."""
    return enlace_ruta(PUNTO_BARRIO[cod_barrio], destino, modo)


def idx_transporte_trabajo(minutos):
    """10 min o menos = 1 · 60 min o más = 0."""
    return (1 - (minutos - 10) / 50).clip(0, 1)


def coste_tiempo(minutos, valor_hora):
    """Horas al año en transporte (ida y vuelta) y su coste mensual en euros."""
    horas_ano = minutos * 2 * DIAS_LABORABLES / 60
    return horas_ano.round(0), (horas_ano * valor_hora / 12).round(0)


# ---------------------------------------------------------------- tu casa
def _a_metros(lat, lon):
    """(lat, lon) → (x, y) en metros (EPSG:25830)."""
    p = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(25830).iloc[0]
    return p.x, p.y


def barrio_de(lat, lon):
    """Fila del barrio que contiene el punto, o None si está fuera de Madrid."""
    x, y = _a_metros(lat, lon)
    dentro = B[B.contains(Point(x, y))]
    return None if dentro.empty else dentro.iloc[0]


def distancia_m(a, b):
    """Distancia en línea recta, en metros, entre dos puntos (lat, lon)."""
    (xa, ya), (xb, yb) = _a_metros(*a), _a_metros(*b)
    return ((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5


def trayecto(casa, trabajo):
    """Minutos aproximados de casa al trabajo en cada modo (calculados desde el barrio de casa)."""
    fila = barrio_de(*casa)
    tiempos = {}
    for modo in ["transporte", "bici", "coche", "andando"]:
        tiempos[modo] = (
            minutos_hasta(*trabajo, modo=modo).get(fila["cod_barrio"]) if fila is not None else None
        )
    return tiempos, distancia_m(casa, trabajo)


def lugares_cerca(lat, lon, radio=1000, tipos=None):
    """Lugares de interés a menos de `radio` metros, ordenados del más cercano al más lejano."""
    x, y = _a_metros(lat, lon)
    d = LUGARES.copy()
    d["tipo"] = d["categoria"].map(TIPO_DE_CATEGORIA)
    if tipos:
        d = d[d["tipo"].isin(tipos)]
    d["dist_m"] = ((d["x"] - x) ** 2 + (d["y"] - y) ** 2) ** 0.5
    d = d[d["dist_m"] <= radio].sort_values("dist_m")
    d["min_andando"] = (d["dist_m"] * FACTOR_RODEO / VELOCIDAD_A_PIE).round().clip(lower=1).astype(int)
    return d


# ---------------------------------------------------------------- recomendador
def recomendar(presupuesto, m2, pesos, minutos=None, max_minutos=None, valor_hora=10,
               usar_2026=False, dividir_entre=1, n=10, min_viviendas=MIN_VIVIENDAS, holgura_max=0.30):
    pesos = {k: w for k, w in pesos.items() if w > 0}
    etiquetas = dict(ETIQUETAS)

    d = B.copy()
    # Alquiler del piso entero o, si se comparte, por habitación
    d["alquiler_estimado"] = (d[columna_precio(usar_2026)] * m2 / dividir_entre).round(0)
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


# ---------------------------------------------------------------- economía
def asequibilidad(sueldo, m2, usar_2026):
    """Alquiler estimado y % del sueldo que supondría en cada barrio con datos fiables."""
    d = B[B["n_viviendas"] >= MIN_VIVIENDAS].copy()
    d["alquiler"] = (d[columna_precio(usar_2026)] * m2).round(0)
    d["esfuerzo"] = (d["alquiler"] / sueldo * 100).round(0)
    d["nombre"] = d["barrio"].map(nombre_visible)
    return d.sort_values("esfuerzo")


def rango_precio(cod_barrio, m2, usar_2026):
    """Percentil 25, mediana y percentil 75 del alquiler del barrio para esos metros."""
    f = B[B["cod_barrio"] == cod_barrio].iloc[0]
    factor = f["eur_m2_2026"] / f["eur_m2"] if usar_2026 else 1.0
    return {
        "p25": f["eur_m2_p25"] * factor * m2,
        "mediana": f["eur_m2"] * factor * m2,
        "p75": f["eur_m2_p75"] * factor * m2,
        "fiable": f["n_viviendas"] >= MIN_VIVIENDAS,
    }