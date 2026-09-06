from datetime import datetime
from typing import Optional, List
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field

# ==========================================
# ESQUEMAS DE HISTORIAL DE REPASOS
# ==========================================
class HistorialRepasoBase(BaseModel):
    puntuacion: Optional[float] = Field(None, ge=0, le=100, description="Porcentaje de aciertos (0-100)")
    tiempo_tardado: int = Field(0, ge=0, description="Tiempo en minutos")
    aciertos: Optional[float] = Field(None, ge=0, le=100, description="Porcentaje de aciertos (0-100)")
    duracion: int = Field(0, ge=0, description="Tiempo tardado en minutos")

class HistorialRepasoCreate(HistorialRepasoBase):
    id_tema: int

class HistorialRepasoResponse(HistorialRepasoBase):
    id: int
    id_tema: int
    fecha_repaso: datetime

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS DE TEMA
# ==========================================
class TemaBase(BaseModel):
    titulo: str = Field(..., max_length=100)
    numero_tema: Optional[int] = None
    prioridad: int = Field(2, ge=1, le=3, description="1: Baja, 2: Media, 3: Alta")
    archivo_pdf: Optional[str] = None
    contenido_texto: Optional[str] = None

class TemaCreate(TemaBase):
    id_asignatura: int

class TemaResponse(TemaBase):
    id: int
    id_asignatura: int
    fecha_creacion: datetime
    historial_repasos: List[HistorialRepasoResponse] = []

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS DE ASIGNATURA
# ==========================================
class AsignaturaBase(BaseModel):
    nombre: str = Field(..., max_length=50)
    color: str = Field("#3B82F6", max_length=20)

class AsignaturaCreate(AsignaturaBase):
    pass

class AsignaturaResponse(AsignaturaBase):
    id: int
    fecha_creacion: datetime
    temas: List[TemaResponse] = []

    class Config:
        from_attributes = True