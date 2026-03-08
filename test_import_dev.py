import pandas as pd
from database import db

import os
print("CWD:", os.getcwd())

print("Loading test CSV...")
df = pd.read_csv("export_listings_1757846722946.csv").head(5)

try:
    print("Test import starting...")
    res = db.import_easync_data(df)
    print("Import success!")
    print(res)
except Exception as e:
    import traceback
    print("Error during import:")
    traceback.print_exc()
