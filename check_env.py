import subprocess
import pandas, geopandas, duckdb, shapely, sklearn, lightgbm, r5py

print("pandas   ", pandas.__version__)
print("geopandas", geopandas.__version__)
print("duckdb   ", duckdb.__version__)
print("shapely  ", shapely.__version__)
print("sklearn  ", sklearn.__version__)
print("lightgbm ", lightgbm.__version__)
print("r5py     ", r5py.__version__)

java = subprocess.run(["java", "-version"], capture_output=True, text=True)
print("java     ", java.stderr.splitlines()[0])

con = duckdb.connect()
con.install_extension("spatial")
con.load_extension("spatial")
print("duckdb spatial OK")