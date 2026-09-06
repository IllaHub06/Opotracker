from datetime import datetime
from typing import List, Optional
# pyrefly: ignore [missing-import]
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Text
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Asignatura(Base):
    """Tabla 'Asignatura' del esquema relacional"""
    __tablename__ = "Asignatura"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(50), default="#3B82F6")
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relación 1:N con Tema (borrado en cascada)
    temas: Mapped[List["Tema"]] = relationship("Tema", back_populates="asignatura", cascade="all, delete-orphan")


class Tema(Base):
    """Tabla 'Tema' del esquema relacional"""
    __tablename__ = "Tema"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_asignatura: Mapped[int] = mapped_column(Integer, ForeignKey("Asignatura.id"), nullable=False)
    titulo: Mapped[str] = mapped_column(String(100), nullable=False)
    numero_tema: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prioridad: Mapped[int] = mapped_column(Integer, default=2)  # 1: Baja, 2: Media, 3: Alta
    archivo_pdf: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Ruta del archivo PDF
    contenido_texto: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # Texto extraído del PDF
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relaciones
    asignatura: Mapped[Optional["Asignatura"]] = relationship("Asignatura", back_populates="temas")
    historial_repasos: Mapped[List["HistorialRepasos"]] = relationship("HistorialRepasos", back_populates="tema", cascade="all, delete-orphan")


class HistorialRepasos(Base):
    """Tabla 'Historial Repasos' del esquema relacional"""
    __tablename__ = "Historial_Repasos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_tema: Mapped[int] = mapped_column(Integer, ForeignKey("Tema.id"), nullable=False)
    puntuacion: Mapped[Optional[float]] = mapped_column(Float, nullable=True)       # Nota / Aciertos (%)
    tiempo_tardado: Mapped[int] = mapped_column(Integer, default=0)                # Minutos dedicados
    aciertos: Mapped[Optional[float]] = mapped_column(Float, nullable=True)         # Porcentaje de aciertos (%)
    duracion: Mapped[int] = mapped_column(Integer, default=0)                       # Tiempo tardado (minutos)
    fecha_repaso: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relación
    tema: Mapped[Optional["Tema"]] = relationship("Tema", back_populates="historial_repasos")