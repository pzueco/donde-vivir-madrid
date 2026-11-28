# 🏠 ¿Dónde vivir en Madrid?

**Recomendador de barrios de Madrid** según tu presupuesto, **dónde trabajas** y lo que te importa, con **tiempos reales en transporte público** calculados a partir de los horarios oficiales de Metro, Cercanías, Metro Ligero y EMT. Construido íntegramente con **datos abiertos**.

👉 **[Prueba la demo en Hugging Face](https://huggingface.co/spaces/pablozueco/donde-vivir-madrid)**

![Recomendador](docs/captura_recomendador.png)

## Qué hace

La app tiene tres pestañas:

| Pestaña | Qué hace |
| --- | --- |
| 🏠 **Recomendador** | Indicas presupuesto, habitaciones, dónde trabajas, cuántos minutos estás dispuesto a tardar y tu perfil (joven, familia, teletrabajo, deportista, cultura). Te muestra en un mapa los mejores barrios, su alquiler estimado, los minutos al trabajo, el **coste real** y **por qué** se recomiendan |
| ⏱️ **¿Qué tengo cerca?** | **Isócronas:** colorea todos los barrios de Madrid según los minutos que se tarda en transporte público hasta tu trabajo |
| ⚖️ **Comparar barrios** | Gráfico de radar con dos barrios superpuestos, más precio, tiempo al trabajo y horas al año en transporte |

![Isócronas](docs/captura_isocrona.png)

## Algunos hallazgos

- **La distancia engaña.** Desde Nuevos Ministerios, el barrio de **Atocha** está a casi 4 km pero a **menos de 15 minutos**, gracias al Cercanías directo. Barrios más cercanos en línea recta tardan más.
- Desde **Nuevos Ministerios** hay **9 barrios a menos de 15 minutos, 68 a menos de 30 y 124 a menos de 45**. El más barato a menos de 30 minutos es **Entrevías** (10,4 €/m²).
- **¿Cuánto vale tu tiempo?** Con 1.000 € y trabajando en Nuevos Ministerios, Moscardó cuesta 271 €/mes menos que Cuatro Caminos, pero supone **139 horas más al año** en transporte. Vivir en Cuatro Caminos solo compensa si valoras tu tiempo por encima de unos **23 €/hora**.

![Comparador](docs/captura_comparador.png)

## Datos

| Fuente | Qué aporta |
| --- | --- |
| [SERPAVI – Ministerio de Vivienda](https://www.mivau.gob.es/vivienda/alquila-bien-es-tu-derecho/serpavi) | Precio del alquiler (€/m², mediana) por sección censal: contratos de pisos de 2024 declarados a Hacienda |
| [Ayuntamiento de Madrid – datos.madrid.es](https://datos.madrid.es) | Límites de distritos, barrios y secciones censales; GTFS de la EMT |
| [Consorcio Regional de Transportes de Madrid (CRTM)](https://datos.crtm.es) | Horarios GTFS de Metro, Metro Ligero y Cercanías (datos explotados) |
| [OpenStreetMap](https://www.openstreetmap.org) | ~28 tipos de servicios (vía `osmnx`) y red de calles para los trayectos a pie ([extracto de Geofabrik](https://download.geofabrik.de/europe/spain.html)) |

## Cómo funciona

### Base geográfica y precios
- **21 distritos, 131 barrios y 2.462 secciones censales** (ETRS89 / UTM 30N). La asignación sección → barrio se validó comparando el código oficial con un *spatial join*: coinciden las 2.462.
- El **97,8 %** de las secciones casan con el SERPAVI. El precio de cada barrio es la media de sus secciones **ponderada por el número de viviendas alquiladas**. Los barrios con menos de 300 viviendas no se recomiendan por falta de fiabilidad.

### Servicios
- Densidad por km² de cada categoría de OpenStreetMap y distancia mediana al tren (Metro, Metro Ligero o Cercanías) y al bus más cercanos.
- Las categorías se definen en un archivo de configuración (`config/poi_categories.yaml`): añadir una nueva no requiere tocar el código.

### Tiempos en transporte público (r5py)
- Red multimodal construida con **[r5py](https://r5py.readthedocs.io)** a partir del mapa de calles de OSM y los **GTFS de Metro, Metro Ligero, Cercanías y EMT**.
- **Martes 1 de diciembre de 2026**, salida entre las **8:30 y las 8:35** (mediana de la ventana, para no depender de perder un tren por un minuto) y límite de 90 minutos.
- **Orígenes:** hasta 5 secciones censales por barrio (632 en total). **Destinos:** rejilla de puntos cada 500 m sobre Madrid, quitando los que no tienen actividad a menos de 500 m (como el Monte de El Pardo): de 2.424 a **1.333 puntos**.
- **842.456 trayectos** calculados una sola vez en local (~73 min). El tiempo de cada barrio a cada punto es la mediana de sus secciones. La app solo consulta la tabla resultante (0,4 MB), así que responde al instante.
- **Validación** con trayectos conocidos desde Sol: Nuevos Ministerios 9 min (Cercanías directo), Atocha 12, Aeropuerto T4 35, Las Tablas 43.

**Problemas de datos resueltos por el camino:**
- El GTFS del Metro publicado caducaba en mayo de 2026, sin solaparse con el de Cercanías. Como la red y los horarios apenas cambian de un año a otro, sus fechas se **desplazaron 364 días** (52 semanas, para que los martes sigan siendo martes).
- Algunos GTFS traían **tablas vacías** (tarifas) que r5py rechaza: se eliminan en una copia limpia, sin tocar los originales.

### Recomendación
- Las variables se agrupan en **9 índices** (precio, transporte, ocio, tranquilidad, cultura, salud, familia, deporte y día a día), normalizados por **percentil**.
- Si indicas dónde trabajas, el índice de transporte pasa a medir **los minutos hasta tu trabajo** (10 min o menos = 1; 60 o más = 0) y se descartan los barrios que superan tu límite.
- El precio cuenta como **holgura respecto a tu presupuesto** (con un tope del 30 %), para no premiar dos veces lo barato.
- Cada recomendación explica **en qué destaca** el barrio (índices por encima del percentil 70).
- **Coste real** = alquiler + horas de transporte al año (ida y vuelta, 220 días laborables) × lo que valoras tu hora. El abono no se incluye porque todo el municipio está en la misma zona tarifaria.

## Stack

Python · GeoPandas · pandas · DuckDB · osmnx · **r5py** · Folium · Plotly · Gradio · Hugging Face Spaces

## Estructura

```
├── app/                        # App Gradio (lo que se publica en Hugging Face)
│   ├── app.py                  # Interfaz: recomendador, isócronas y comparador
│   ├── recomendador.py         # Lógica de puntuación y tiempos
│   └── data/                   # Datos procesados que usa la app
├── config/
│   └── poi_categories.yaml     # Categorías de OpenStreetMap
├── notebooks/
│   ├── 01_barrios.ipynb             # Base geográfica y validación
│   ├── 02_precios_alquiler.ipynb    # SERPAVI por sección y barrio
│   ├── 03_ocio_servicios.ipynb      # Servicios y transporte desde OSM
│   ├── 04_recomendador.ipynb        # Índices, perfiles y pruebas
│   └── 05_tiempos_viaje.ipynb       # Red r5py, validación y matriz de tiempos
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

- El SERPAVI recoge **contratos vigentes declarados**, no precios de anuncio: es un precio de referencia, normalmente por debajo del mercado actual. Son pisos completos, no habitaciones.
- Los tiempos usan los **horarios programados**, no retrasos en tiempo real. Los del Metro proceden del GTFS de 2025 desplazado un año.
- Solo hay destinos de trabajo **dentro del municipio de Madrid**.
- OpenStreetMap no está igual de completo en todas las categorías (por ejemplo, los coworkings no se usan por estar poco mapeados).

## Próximos pasos

- [ ] Escribir la dirección exacta del trabajo
- [ ] Itinerario detallado (líneas, paradas, transbordos) y comparación con bici, coche y a pie
- [ ] Calidad del aire, ruido y zonas verdes
- [ ] Modelo de precio (LightGBM + SHAP) para detectar barrios infravalorados
- [ ] Trabajos en municipios de alrededor (Leganés, Getafe, Alcobendas, Las Rozas...)
- [ ] Asistente en lenguaje natural

## Atribución

Datos del **Consorcio Regional de Transportes de Madrid** (datos explotados), **EMT de Madrid**, **Ayuntamiento de Madrid**, **Ministerio de Vivienda y Agenda Urbana** (SERPAVI) y © colaboradores de **OpenStreetMap** (ODbL).

## Autor

**Pablo Zueco Herrero** · Grado en Ciencia e Ingeniería de Datos (UPCT) · [GitHub](https://github.com/pzueco)