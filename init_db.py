# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker
from models import Base

# Definición de la base de datos SQLite local
DATABASE_URL = "sqlite:///./opotracker.db"

# Motor de conexión
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def generar_base_de_datos():
    print("Creando archivo de base de datos SQLite 'opotracker.db'...")
    Base.metadata.create_all(bind=engine)
    print("¡Base de datos y tablas creadas con éxito!")

if __name__ == "__main__":
    generar_base_de_datos()