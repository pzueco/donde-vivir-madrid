from pathlib import Path

import geopandas as gpd

DATA = Path(__file__).parent / "data" / "barrios_indices.parquet"
B = gpd.read_parquet(DATA)

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


def recomendar(presupuesto, m2, pesos, n=10, min_viviendas=300, factor_precio=1.0, holgura_max=0.30):
    pesos = {k: w for k, w in pesos.items() if w > 0}

    d = B.copy()
    d["alquiler_estimado"] = (d["eur_m2"] * m2 * factor_precio).round(0)
    d = d[(d["alquiler_estimado"] <= presupuesto) & (d["n_viviendas"] >= min_viviendas)].copy()
    if d.empty or not pesos:
        return d

    holgura = 1 - d["alquiler_estimado"] / presupuesto
    d["idx_precio"] = holgura.clip(0, holgura_max) / holgura_max

    suma = sum(pesos.values())
    d["puntuacion"] = (sum(w * d[f"idx_{k}"] for k, w in pesos.items()) / suma * 100).round(1)

    def motivos(fila):
        ordenados = sorted(pesos, key=lambda k: fila[f"idx_{k}"], reverse=True)
        fuertes = [ETIQUETAS[k] for k in ordenados if fila[f"idx_{k}"] >= 0.7][:2]
        return ", ".join(fuertes) if fuertes else "equilibrado en todo"

    d["por_que"] = d.apply(motivos, axis=1)
    d["nombre"] = d["barrio"].map(
        lambda x: f"{x} ({NOMBRES_POPULARES[x]})" if x in NOMBRES_POPULARES else x
    )

    cols = ["nombre", "distrito", "puntuacion", "alquiler_estimado", "por_que", "dist_tren_m", "geometry"]
    return d.sort_values("puntuacion", ascending=False)[cols].head(n)