from typing import List, Optional
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Depends, HTTPException, status
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

import models
import schemas
from init_db import SessionLocal, engine
from algorithm import obtener_temas_prioritarios

# Crear las tablas en la base de datos si no existen
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Opotracker API",
    description="API para la gestión de temas de oposiciones y repaso espaciado",
    version="1.0.0"
)

# Dependencia para obtener la sesión de la base de datos en cada petición
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==========================================
# ENDPOINTS DE ASIGNATURAS
# ==========================================
@app.post("/asignaturas/", response_model=schemas.AsignaturaResponse, status_code=status.HTTP_201_CREATED)
def crear_asignatura(asignatura: schemas.AsignaturaCreate, db: Session = Depends(get_db)):
    db_asignatura = models.Asignatura(**asignatura.model_dump())
    db.add(db_asignatura)
    db.commit()
    db.refresh(db_asignatura)
    return db_asignatura


@app.get("/asignaturas/", response_model=List[schemas.AsignaturaResponse])
def listar_asignaturas(db: Session = Depends(get_db)):
    return db.query(models.Asignatura).all()


# ==========================================
# ENDPOINTS DE TEMAS
# ==========================================
@app.post("/temas/", response_model=schemas.TemaResponse, status_code=status.HTTP_201_CREATED)
def crear_tema(tema: schemas.TemaCreate, db: Session = Depends(get_db)):
    # Verificar que la asignatura existe
    db_asignatura = db.query(models.Asignatura).filter(models.Asignatura.id == tema.id_asignatura).first()
    if not db_asignatura:
        raise HTTPException(status_code=404, detail="La asignatura especificada no existe")
    
    db_tema = models.Tema(**tema.model_dump())
    db.add(db_tema)
    db.commit()
    db.refresh(db_tema)
    return db_tema


@app.get("/temas/", response_model=List[schemas.TemaResponse])
def listar_temas(
    id_asignatura: Optional[int] = None,
    prioridad: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Tema)
    if id_asignatura is not None:
        query = query.filter(models.Tema.id_asignatura == id_asignatura)
    if prioridad is not None:
        query = query.filter(models.Tema.prioridad == prioridad)
    return query.all()


@app.get("/temas/{tema_id}", response_model=schemas.TemaResponse)
def obtener_tema(tema_id: int, db: Session = Depends(get_db)):
    db_tema = db.query(models.Tema).filter(models.Tema.id == tema_id).first()
    if not db_tema:
        raise HTTPException(status_code=404, detail="El tema especificado no existe")
    return db_tema


# ==========================================
# ENDPOINTS DE HISTORIAL DE REPASOS
# ==========================================
@app.post("/repasos/", response_model=schemas.HistorialRepasoResponse, status_code=status.HTTP_201_CREATED)
def registrar_repaso(repaso: schemas.HistorialRepasoCreate, db: Session = Depends(get_db)):
    # Verificar que el tema existe
    db_tema = db.query(models.Tema).filter(models.Tema.id == repaso.id_tema).first()
    if not db_tema:
        raise HTTPException(status_code=404, detail="El tema especificado no existe")

    db_repaso = models.HistorialRepasos(**repaso.model_dump())
    db.add(db_repaso)
    db.commit()
    db.refresh(db_repaso)
    return db_repaso


@app.get("/repasos/", response_model=List[schemas.HistorialRepasoResponse])
def listar_repasos(
    id_tema: Optional[int] = None,
    puntuacion_min: Optional[float] = None,
    puntuacion_max: Optional[float] = None,
    tiempo_min: Optional[int] = None,
    tiempo_max: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.HistorialRepasos)
    
    if id_tema is not None:
        query = query.filter(models.HistorialRepasos.id_tema == id_tema)
    if puntuacion_min is not None:
        query = query.filter(models.HistorialRepasos.puntuacion >= puntuacion_min)
    if puntuacion_max is not None:
        query = query.filter(models.HistorialRepasos.puntuacion <= puntuacion_max)
    if tiempo_min is not None:
        query = query.filter(models.HistorialRepasos.tiempo_tardado >= tiempo_min)
    if tiempo_max is not None:
        query = query.filter(models.HistorialRepasos.tiempo_tardado <= tiempo_max)
        
    return query.all()


# ==========================================
# ENDPOINT ESTRELLA: REPASOS RECOMENDADOS (RF-05)
# ==========================================
@app.get("/repasos/recomendados/")
def obtener_repasos_recomendados(limite: int = 5, db: Session = Depends(get_db)):
    temas = db.query(models.Tema).all()
    recomendaciones = obtener_temas_prioritarios(temas, limite=limite)
    
    # Formatear la respuesta para el frontend
    resultado = []
    for item in recomendaciones:
        tema = item["tema"]
        resultado.append({
            "id_tema": tema.id,
            "titulo_tema": tema.titulo,
            "prioridad": tema.prioridad,
            "urgencia_calculada": item["urgencia"],
            "total_repasos": len(tema.historial_repasos)
        })
    return resultado