# 🏠 ¿Dónde vivir en Madrid?

**Recomendador de barrios de Madrid** según tu presupuesto, el tamaño de piso que buscas y lo que te importa (transporte, ambiente, tranquilidad, familia, deporte, cultura...), construido íntegramente con **datos abiertos oficiales**.

👉 **[Prueba la demo en Hugging Face](https://huggingface.co/spaces/pablozueco/donde-vivir-madrid)**

![Captura de la app](docs/captura_app.png)

## Qué hace

1. Indicas tu **presupuesto**, el **número de habitaciones** (o los m²) y tu **perfil** (joven, familia, teletrabajo, deportista, cultura), o ajustas a mano lo que te importa.
2. La app estima el **alquiler en cada uno de los 131 barrios** de Madrid y descarta los que se salen del presupuesto.
3. Puntúa el resto de 0 a 100 según tus prioridades y te muestra en un **mapa** los mejores, con su alquiler estimado y **por qué** se recomiendan.

## Datos

| Fuente | Qué aporta |
| --- | --- |
| [SERPAVI – Ministerio de Vivienda](https://www.mivau.gob.es/vivienda/alquila-bien-es-tu-derecho/serpavi) | Precio del alquiler (€/m², mediana) por sección censal, contratos de 2024 declarados a Hacienda |
| [Portal de datos abiertos del Ayuntamiento de Madrid](https://datos.madrid.es) | Límites de distritos, barrios y secciones censales |
| [OpenStreetMap](https://www.openstreetmap.org) (vía `osmnx`) | ~28 tipos de servicios: supermercados, restaurantes, bares, gimnasios, colegios, centros de salud, museos, estaciones de Metro, Cercanías y bus... |

## Cómo funciona

- **Base geográfica:** 21 distritos, 131 barrios y 2.462 secciones censales (ETRS89 / UTM 30N). La asignación sección → barrio se validó comparando el código oficial con un *spatial join*: coinciden las 2.462.
- **Precios:** el 97,8 % de las secciones casan con el SERPAVI. El precio de cada barrio es la media de sus secciones **ponderada por el número de viviendas alquiladas**. Los barrios con menos de 300 viviendas se excluyen por falta de fiabilidad.
- **Servicios:** densidad por km² de cada categoría y distancia mediana (desde las secciones censales) al tren más cercano (Metro, Metro Ligero o Cercanías) y a la parada de bus.
- **Índices:** las variables se agrupan en 9 índices (precio, transporte, ocio, tranquilidad, cultura, salud, familia, deporte y día a día) normalizados por **percentil**, robusto frente a valores extremos como la densidad de bares de Sol.
- **Puntuación:** media ponderada de los índices con los pesos del usuario. El precio se mide como **holgura respecto al presupuesto** (con un tope del 30 %), para no premiar dos veces lo barato.
- **Explicación:** cada recomendación indica en qué destaca el barrio (índices por encima del percentil 70).

## Stack

Python · GeoPandas · pandas · DuckDB · osmnx · Folium · Gradio · Hugging Face Spaces

## Estructura

```
├── app/                  # App Gradio (lo que se publica en Hugging Face)
│   ├── app.py            # Interfaz y mapa
│   ├── recomendador.py   # Lógica de puntuación
│   └── data/             # Datos procesados que usa la app
├── config/
│   └── poi_categories.yaml   # Categorías de OpenStreetMap
├── notebooks/
│   ├── 01_barrios.ipynb          # Base geográfica y validación
│   ├── 02_precios_alquiler.ipynb # SERPAVI por sección y barrio
│   ├── 03_ocio_servicios.ipynb   # Servicios y transporte desde OSM
│   └── 04_recomendador.ipynb     # Índices, perfiles y pruebas
└── environment.yml
```

## Ejecutarlo en local

```bash
conda env create -f environment.yml
conda activate madrid
cd app
python app.py
```

## Limitaciones

- El SERPAVI recoge **contratos vigentes declarados**, no precios de anuncio: es un precio de referencia, normalmente por debajo del mercado actual.
- Los precios son de **pisos completos**, no de habitaciones en piso compartido.
- OpenStreetMap no está igual de completo en todas las categorías (por ejemplo, los coworkings no se usan por estar poco mapeados).
- La distancia al transporte es en línea recta, no el tiempo real de viaje.

## Próximos pasos

- [ ] Tiempo real de viaje al trabajo en transporte público (r5py + horarios GTFS de CRTM y EMT)
- [ ] Mapa de isócronas: todo lo que tienes a 15, 30 y 45 minutos
- [ ] Coste real de vivir en cada barrio: alquiler + abono + horas de transporte al año
- [ ] Comparador de dos barrios
- [ ] Modelo de precio (LightGBM + SHAP) para detectar barrios infravalorados
- [ ] Calidad del aire, ruido y zonas verdes

## Autor

**Pablo Zueco Herrero** · Grado en Ciencia e Ingeniería de Datos (UPCT) · [GitHub](https://github.com/pzueco)