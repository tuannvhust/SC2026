import os
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.memory.working.postgres_store import default_database_url, describe_database_url
from sqlalchemy import create_engine, inspect, text

url = default_database_url()
print("Connected DB desc:", describe_database_url(url))

engine = create_engine(url)
insp = inspect(engine)
tables = insp.get_table_names()
print("Tables in currently configured project:", tables)

with engine.connect() as conn:
    for t in tables:
        count = conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar()
        print(f"  - {t}: {count} rows")
        cols = [c["name"] + " (" + str(c["type"]) + ")" for c in insp.get_columns(t)]
        print(f"    cols: {', '.join(cols[:8])}{' ...' if len(cols) > 8 else ''}")
