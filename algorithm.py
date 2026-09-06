# pyrefly: ignore [missing-import]
from datetime import datetime
from typing import List, Dict, Any, Optional

# pyrefly: ignore [missing-import]
import models

def calcular_urgencia_tema(tema: Any) -> float:
    """
    Calcula la puntuación de urgencia/prioridad de repaso de un tema.
    A mayor puntuación, mayor es la necesidad de repasar.
    """
    prioridad_multiplicador = float(getattr(tema, "prioridad", 2) or 2)
    historial = getattr(tema, "historial_repasos", [])

    if not historial:
        # Tema nunca repasado: prioridad máxima base
        return 1000.0 * prioridad_multiplicador

    # Obtener el último repaso realizado basado en la fecha
    ultimo_repaso = max(historial, key=lambda r: getattr(r, "fecha_repaso", datetime.min))
    
    fecha_repaso = getattr(ultimo_repaso, "fecha_repaso", datetime.utcnow())
    puntuacion = getattr(ultimo_repaso, "puntuacion", None)

    # Días transcurridos desde el último repaso
    dias_transcurridos = max(0, (datetime.utcnow() - fecha_repaso).days)
    
    # Factor de olvido según la última nota (0 a 100)
    nota = float(puntuacion) if puntuacion is not None else 50.0
    factor_olvido = (100.0 - nota) / 100.0

    # Fórmula de urgencia
    urgencia = (dias_transcurridos + 1) * (1.5 + factor_olvido) * prioridad_multiplicador

    return round(float(urgencia), 2)


def obtener_temas_prioritarios(temas: List[Any], limite: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Calcula la urgencia de una lista de temas y los devuelve ordenados descendentemente.
    """
    lista_calculada = []
    for tema in temas:
        urgencia = calcular_urgencia_tema(tema)
        lista_calculada.append({
            "tema": tema,
            "urgencia": urgencia
        })

    # Ordenar de mayor a menor urgencia
    lista_calculada.sort(key=lambda x: x["urgencia"], reverse=True)

    if limite is not None and limite > 0:
        return lista_calculada[:limite]

    return lista_calculada