"""Prepara app/data/lugares.parquet: los lugares de interés de la pestaña «Tu casa y alrededores».

Reutiliza los puntos de interés del notebook 03 y descarga de OpenStreetMap los que faltan
(monumentos y lugares de interés turístico, y parques).

Ejecútalo desde la carpeta raíz del proyecto, con el entorno «madrid» activado:
    python scripts/preparar_lugares.py
"""
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd

ox.settings.requests_timeout = 300

RAIZ = Path(__file__).resolve().parents[1]
PROCESSED = RAIZ / "data" / "processed"
RAW_OSM = RAIZ / "data" / "raw" / "osm"
SALIDA = RAIZ / "app" / "data" / "lugares.parquet"

barrios = gpd.read_parquet(PROCESSED / "barrios_precios.parquet")
MADRID_4326 = barrios.to_crs(4326).union_all()

# Categorías nuevas. Cada una puede juntar varias consultas a OpenStreetMap.
NUEVAS = {
    "monumentos": {
        "consultas": [
            {"historic": ["monument", "castle", "palace", "archaeological_site"]},
            {"tourism": "attraction"},
        ],
        "area_min": 0,
    },
    "parques": {
        "consultas": [{"leisure": "park"}],
        "area_min": 5000,  # m²: deja fuera las zonas verdes diminutas
    },
}


def descargar(nombre, conf):
    destino = RAW_OSM / f"{nombre}.parquet"
    if destino.exists():  # si ya está descargada, no repite
        return gpd.read_parquet(destino)

    capas = []
    for tags in conf["consultas"]:
        print(f"  consultando {tags} ...")
        try:
            capas.append(ox.features_from_polygon(MADRID_4326, tags=tags).reset_index())
        except Exception as e:
            print(f"    sin resultados ({e.__class__.__name__}: {e})")
    if not capas:
        return None

    g = gpd.GeoDataFrame(pd.concat(capas, ignore_index=True), geometry="geometry", crs=4326).to_crs(25830)
    col_id = "id" if "id" in g.columns else "osmid"
    g = g.rename(columns={col_id: "id"}).drop_duplicates("id")
    if "name" not in g.columns:
        g["name"] = None
    g = g[g["name"].notna()]  # solo los que tienen nombre
    if conf["area_min"]:
        g = g[g.geom_type.isin(["Polygon", "MultiPolygon"]) & (g.area >= conf["area_min"])]

    g["geometry"] = g.representative_point()  # polígonos → punto
    g = gpd.GeoDataFrame(g[["id", "name", "geometry"]], geometry="geometry", crs=25830)
    g["categoria"] = nombre
    g.to_parquet(destino)
    return g


# Si existe la versión combinada (OSM + censo de locales del Ayuntamiento, notebook 09), usamos esa
ruta_pois = PROCESSED / "pois_combinados.parquet"
if not ruta_pois.exists():
    ruta_pois = PROCESSED / "pois.parquet"
print("Usando", ruta_pois.name)
capas = [gpd.read_parquet(ruta_pois)]
for nombre, conf in NUEVAS.items():
    print("Descargando", nombre, "...")
    g = descargar(nombre, conf)
    if g is not None:
        print(f"  {len(g)} encontrados")
        capas.append(g)

lugares = gpd.GeoDataFrame(pd.concat(capas, ignore_index=True), geometry="geometry", crs=25830)
lugares = lugares[lugares.within(barrios.union_all())]  # solo dentro de Madrid capital

wgs = lugares.to_crs(4326)
salida = pd.DataFrame({
    "categoria": lugares["categoria"].values,
    "nombre": lugares["name"].fillna("Sin nombre").values,
    "x": lugares.geometry.x.round(1).values,       # metros (EPSG:25830), para medir distancias
    "y": lugares.geometry.y.round(1).values,
    "lat": wgs.geometry.y.round(6).values,         # grados, para el mapa y Google Maps
    "lon": wgs.geometry.x.round(6).values,
})
salida.to_parquet(SALIDA, index=False)

print(f"\nGuardado {SALIDA} con {len(salida)} lugares:")
print(salida["categoria"].value_counts().to_string())
