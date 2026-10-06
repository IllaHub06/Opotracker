import re
import os
import json
import random
import io
import time
from typing import List, Dict, Any, Optional, TypedDict
import pypdf
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Importación del SDK oficial de Google GenAI
from google import genai
from google.genai import types

# Cargar variables de entorno desde .env
load_dotenv()

# Límite máximo de caracteres extraídos del PDF para la llamada a Gemini
MAX_CARACTERES: int = 80000


class PlantillaPregunta(TypedDict):
    pregunta: str
    opciones: List[str]
    respuesta_correcta: int
    explicacion: str


class PreguntaTestSchema(BaseModel):
    pregunta: str = Field(
        description="Enunciado completo, formal y directo de la pregunta de test (sin puntos suspensivos ni frases cortadas)."
    )
    opciones: list[str] = Field(
        description="Lista de exactamente 4 opciones de respuesta distintas, terminadas y completas (índices 0, 1, 2 y 3). Solo UNA opción debe ser la correcta."
    )
    respuesta_correcta: int = Field(
        description="Índice entero (0, 1, 2 o 3) correspondiente a la posición exacta de la opción de respuesta correcta en la lista 'opciones' (0 = primera, 1 = segunda, 2 = tercera, 3 = cuarta)."
    )
    explicacion: str = Field(
        description="Explicación técnica detallada y completa que justifica por qué la opción señalada por 'respuesta_correcta' es la correcta según los apuntes."
    )


class ListaPreguntasSchema(BaseModel):
    preguntas: list[PreguntaTestSchema] = Field(
        description="Lista de preguntas tipo test estructuradas."
    )


def _limpiar_sin_suspensivos(texto: str) -> str:
    """
    Limpia cadenas eliminando puntos suspensivos finales ('...' o '…')
    y asegura que las oraciones terminen con un signo de puntuación limpio.
    """
    if not texto:
        return ""
    limpio = texto.strip()
    limpio = re.sub(r"\s*(\.\.\.|…)+\s*$", "", limpio).strip()
    if limpio and not limpio.endswith((".", ":", "?", "!", ";")):
        limpio += "."
    return limpio


def extraer_texto_pdf(file_input: Any) -> str:
    """
    Extrae el texto de un archivo PDF (ruta en disco, objeto BytesIO o UploadedFile).
    """
    try:
        if isinstance(file_input, str):
            reader = pypdf.PdfReader(file_input)
        elif hasattr(file_input, "read"):
            bytes_data = file_input.read()
            if hasattr(file_input, "seek"):
                file_input.seek(0)
            reader = pypdf.PdfReader(io.BytesIO(bytes_data))
        elif isinstance(file_input, (bytes, bytearray)):
            reader = pypdf.PdfReader(io.BytesIO(file_input))
        else:
            reader = pypdf.PdfReader(file_input)

        texto_paginas: List[str] = []
        for page in reader.pages:
            txt = page.extract_text()
            if txt:
                texto_paginas.append(txt.strip())

        texto_completo = "\n\n".join(texto_paginas)
        texto_limpio = re.sub(r"[ \t]+", " ", texto_completo)
        return texto_limpio.strip()
    except Exception as e:
        print(f"Error al extraer texto del PDF: {e}")
        return ""


def generar_preguntas_con_gemini(
    contenido_texto: str,
    num_preguntas: int = 5,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Llama a la API de Gemini para generar preguntas de test basadas
    ESTRICTAMENTE en el contenido_texto extraído del PDF.
    Garantiza que el índice 'respuesta_correcta' coincida exactamente con
    la posición de la opción correcta en la lista 'opciones'.
    """

    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key or not key.strip():
        raise ValueError("No se ha configurado la clave de API GEMINI_API_KEY ni GOOGLE_API_KEY.")

    # Inicialización con el cliente oficial de google-genai
    client = genai.Client(api_key=key.strip())

    # Asegurar el límite de caracteres para no desbordar el contexto
    texto_a_enviar = contenido_texto[:MAX_CARACTERES] if len(contenido_texto) > MAX_CARACTERES else contenido_texto

    system_instruction = """
Eres un preparador experto de oposiciones oficiales en España altamente riguroso y técnico.
Tu única tarea es redactar preguntas tipo test profesionales, precisas y completas basadas de manera ESTRICTA en el texto del temario proporcionado.

REGLAS ESTRICTAS E INVIOLABLES:
1. PRECISIÓN Y RIGOR EN LA RESPUESTA CORRECTA:
   - Para cada pregunta, redacta exactamente 4 opciones de respuesta distintas en la lista 'opciones'.
   - Solo UNA de las 4 opciones debe ser la respuesta jurídicamente/técnicamente correcta según el temario.
   - El campo 'respuesta_correcta' DEBE ser el índice numérico entero (0, 1, 2 o 3) correspondiente a la posición exacta de esa opción correcta dentro del array 'opciones':
     * 0 -> si la opción correcta es la 1ª (opciones[0]).
     * 1 -> si la opción correcta es la 2ª (opciones[1]).
     * 2 -> si la opción correcta es la 3ª (opciones[2]).
     * 3 -> si la opción correcta es la 4ª (opciones[3]).
   - DISTRIBUCIÓN EQUITATIVA DEL ÍNDICE: Distribuye las respuestas correctas de manera variada entre las posiciones 0, 1, 2 y 3. NO coloques siempre la respuesta correcta en el índice 0.
   - COHERENCIA TOTAL: Verifica meticulosamente que la opción situada en opciones[respuesta_correcta] sea 100% verídica conforme al texto y coincida con lo explicado en el campo 'explicacion'.

2. NADA DE PUNTOS SUSPENSIVOS NI TEXTO TRUNCADO:
   - Tanto los enunciados como CADA UNA de las 4 opciones de respuesta DEBEN ser oraciones íntegras, cerradas y con sentido gramatical completo.
   - Queda ESTRICTAMENTE PROHIBIDO recortar oraciones con puntos suspensivos ("...") o el carácter "…".
   - Todas las oraciones deben concluir de forma natural y completa.

3. CERO REPETICIÓN Y PROHIBICIÓN DE PLANTILLAS GENÉRICAS:
   - JAMÁS utilices la frase: "¿Cuál de las siguientes opciones refleja fielmente el texto?".
   - JAMÁS comiences preguntas con muletillas repetitivas como "Según el texto...", "De acuerdo con los apuntes..." o "Indique la opción correcta...".
   - Cada pregunta debe indagar sobre un concepto jurídico o técnico específico (plazos, competencias, definiciones, excepciones, mayorías, trámites, órganos).

4. CASTELLANO EXCLUSIVO:
   - Todo el contenido (pregunta, 4 opciones y explicación) DEBE estar redactado al 100% en español formal.

5. CALIDAD Y PLAUSIBILIDAD DE LOS DISTRACTORES:
   - Las 3 opciones incorrectas deben ser distractores verosímiles y técnicos (variando plazos, modificando órganos competentes, invirtiendo requisitos o cambiando mayorías).
   - Queda prohibido incluir opciones vacías o absurdas como "Ninguna de las anteriores", "Todas son correctas", "No guarda relación" o "Opción no mencionada".
"""

    prompt = f"""
Genera un conjunto de {num_preguntas} preguntas tipo test en ESPAÑOL a partir del siguiente temario.

DIVERSIFICACIÓN OBLIGATORIA DE LAS PREGUNTAS (cada una debe abordar un ángulo diferente):
- Plazos, cómputos temporales, cifras o mayorías numéricas.
- Órganos competentes, atribuciones, funciones o jerarquía.
- Requisitos, supuestos de aplicación o presupuestos de hecho.
- Definición, concepto o principio normativo/técnico.
- Excepciones, prohibiciones o límites legales.

REQUISITO TÉCNICO ESTRUCTURAL:
Devuelve el resultado estrictamente conforme al esquema JSON solicitado:
- Cada elemento de la lista "preguntas" debe tener:
  - "pregunta": enunciado claro, formal y directo.
  - "opciones": lista de exactamente 4 strings con las alternativas (índices 0, 1, 2 y 3).
  - "respuesta_correcta": número entero (0, 1, 2 o 3) señalando la posición exacta de la opción correcta en la lista "opciones".
  - "explicacion": explicación técnica detallada de por qué opciones[respuesta_correcta] es la opción correcta según el temario.

---
TEMARIO:
{texto_a_enviar}
---
"""

    # Configuración de reintentos para soportar picos de demanda (error 503)
    max_reintentos = 4
    response = None

    for intento in range(max_reintentos):
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=ListaPreguntasSchema,
                    temperature=0.2,
                ),
            )
            # Si se ejecutó correctamente y hay respuesta, salimos del bucle
            if response and response.text:
                break
        except Exception as e:
            err_str = str(e).upper()
            # Si el servidor responde con 503, UNAVAILABLE o HIGH DEMAND, reintentamos
            if any(k in err_str for k in ["503", "UNAVAILABLE", "HIGH DEMAND"]):
                if intento < max_reintentos - 1:
                    tiempo_espera = (intento + 1) * 4  # Tiempos de espera: 4s, 8s, 12s...
                    print(f"[AVISO] Servidor saturado (503). Reintentando en {tiempo_espera}s... (Intento {intento + 1}/{max_reintentos})")
                    time.sleep(tiempo_espera)
                    continue  # Pasa al siguiente intento del bucle sin lanzar excepción
            
            # Si es un error de autenticación o la API key es inválida, se detiene de inmediato
            if any(k in err_str for k in ["API_KEY_INVALID", "API KEY NOT VALID", "UNAUTHENTICATED", "PERMISSION_DENIED", "401", "403"]):
                raise ValueError(f"[ERROR GEMINI] Clave de API no válida o denegada: {e}") from e
            
            # Si no es un 503 y es el último intento, lanza la excepción
            if intento == max_reintentos - 1:
                raise RuntimeError(f"Error al generar test con Gemini tras {max_reintentos} intentos: {e}") from e

    # Validación final de la respuesta recibida
    if response is None or not response.text:
        raise RuntimeError("No se obtuvo respuesta de Gemini tras varios reintentos por saturación del servidor.")

    texto_respuesta = response.text.strip()
    if not texto_respuesta:
        raise ValueError("El modelo gemini-3.8-flash devolvió una respuesta vacía.")

    # Limpiar posibles delimitadores markdown si vinieran incluidos
    texto_respuesta = re.sub(r"^```(?:json)?\s*", "", texto_respuesta, flags=re.MULTILINE)
    texto_respuesta = re.sub(r"^```\s*", "", texto_respuesta, flags=re.MULTILINE)
    texto_respuesta = texto_respuesta.strip()

    datos = json.loads(texto_respuesta)
    if isinstance(datos, dict):
        for k in ["preguntas", "questions", "items", "data", "results"]:
            if k in datos and isinstance(datos[k], list):
                datos = datos[k]
                break
        else:
            for val in datos.values():
                if isinstance(val, list) and len(val) > 0:
                    datos = val
                    break

    if not isinstance(datos, list) or len(datos) == 0:
        raise ValueError("No se pudieron extraer preguntas estructuradas de la respuesta de Gemini.")

    resultado: List[Dict[str, Any]] = []
    for idx, item in enumerate(datos, start=1):
        if not isinstance(item, dict):
            continue

        # Limpiar enunciados y opciones de posibles puntos suspensivos
        preg = _limpiar_sin_suspensivos(str(item.get("pregunta", "")).strip())
        if preg.endswith("."):
            preg = preg[:-1]

        ops_raw = item.get("opciones", [])
        if not isinstance(ops_raw, list):
            continue

        ops: List[str] = [_limpiar_sin_suspensivos(str(o)).strip() for o in ops_raw if str(o).strip()]

        while len(ops) < 4:
            ops.append(f"Disposición o alternativa supletoria {len(ops) + 1}.")
        ops = ops[:4]

        # Determinar y validar índice de respuesta correcta (0, 1, 2 o 3)
        corr_val = item.get("respuesta_correcta")
        if corr_val is None:
            corr_val = item.get("correcta")
        if corr_val is None:
            corr_val = item.get("correct_index")
        if corr_val is None:
            corr_val = item.get("correct_answer")

        corr_idx = 0
        if isinstance(corr_val, int):
            corr_idx = corr_val
        elif isinstance(corr_val, str):
            corr_val_clean = corr_val.strip().upper()
            mapa_letras = {
                "A": 0, "B": 1, "C": 2, "D": 3,
                "OPCIÓN A": 0, "OPCIÓN B": 1, "OPCIÓN C": 2, "OPCIÓN D": 3,
                "OPCION A": 0, "OPCION B": 1, "OPCION C": 2, "OPCION D": 3,
            }
            if corr_val_clean in mapa_letras:
                corr_idx = mapa_letras[corr_val_clean]
            else:
                try:
                    corr_idx = int(corr_val_clean)
                except ValueError:
                    if corr_val in ops:
                        corr_idx = ops.index(corr_val)
                    else:
                        corr_idx = 0

        if corr_idx < 0 or corr_idx >= len(ops):
            corr_idx = 0

        # Aleatorizar el orden de las opciones y recalcular el índice de la respuesta correcta
        opcion_correcta_texto = ops[corr_idx]
        random.shuffle(ops)
        nuevo_corr_idx = ops.index(opcion_correcta_texto)

        explicacion_raw = str(item.get("explicacion", "Pregunta generada por IA (Gemini) basada en los apuntes del PDF.")).strip()
        explicacion_txt = _limpiar_sin_suspensivos(explicacion_raw)

        resultado.append({
            "id": idx,
            "pregunta": preg,
            "opciones": ops,
            "respuesta_correcta": int(nuevo_corr_idx),
            "explicacion": f"💡 {explicacion_txt}" if not explicacion_txt.startswith("💡") else explicacion_txt
        })

    if len(resultado) > 0:
        return resultado

    raise RuntimeError("No se pudieron procesar las preguntas generadas por Gemini.")


def _generar_preguntas_genericas(tema_titulo: str, asignatura_nombre: str, cantidad: int) -> List[Dict[str, Any]]:
    """
    Genera preguntas de respaldo únicamente cuando no se ha subido ningún PDF ni hay texto disponible.
    Garantiza que la respuesta correcta asignada coincida exactamente con la opción verdadera.
    """
    banco: List[PlantillaPregunta] = [
        {
            "pregunta": f"¿Cuál es el objeto y contenido fundamental de «{tema_titulo}»?",
            "opciones": [
                f"Estudiar los conceptos esenciales, definiciones y marco de aplicación de {tema_titulo}.",
                "Limitarse a aspectos históricos sin vigencia jurídica actual.",
                "Analizar exclusivamente procedimientos derogados.",
                "Sustituir la normativa por directivas sin transponer."
            ],
            "respuesta_correcta": 0,
            "explicacion": f"El tema {tema_titulo} aborda los conceptos y fundamentos esenciales de la materia."
        },
        {
            "pregunta": f"Respecto a «{tema_titulo}», ¿cuál es el principio básico de aplicación que rige la materia?",
            "opciones": [
                "Principio de legalidad, rigor técnico y adecuación a la materia.",
                "Discrecionalidad absoluta sin sujeción a normas.",
                "Invalidez general de los conceptos básicos.",
                "Exclusión de plazos o requisitos formales."
            ],
            "respuesta_correcta": 0,
            "explicacion": "El temario se estructura bajo criterios de rigor y adecuación normativa."
        },
        {
            "pregunta": f"En relación con los plazos y términos en «{tema_titulo}», ¿qué criterio prevalece?",
            "opciones": [
                "Los plazos establecidos son de obligado cumplimiento para las partes interesadas.",
                "Los plazos son siempre meramente indicativos y nunca precluyen.",
                "No existen términos fijados en la materia.",
                "Se aplican exclusivamente días inhábiles."
            ],
            "respuesta_correcta": 0,
            "explicacion": "Los plazos fijados en los temarios y procedimientos son vinculantes."
        },
        {
            "pregunta": f"¿Qué elemento es indispensable para la validez de los actos en «{tema_titulo}»?",
            "opciones": [
                "Cumplir con los requisitos formales y de competencia previstos en el temario.",
                "La mera voluntad individual sin trámite alguno.",
                "El transcurso indefinido del tiempo.",
                "La ausencia total de notificación o comunicación formal."
            ],
            "respuesta_correcta": 0,
            "explicacion": "Los actos y procedimientos requieren cumplimiento de los requisitos establecidos."
        },
        {
            "pregunta": f"Ante dudas de interpretación sobre los conceptos de «{tema_titulo}», ¿qué criterio debe primar?",
            "opciones": [
                "Criterio de jerarquía, especialidad y sentido propio de las palabras.",
                "Criterio aleatorio sin fundamento técnico.",
                "Inaplicabilidad simultánea de todas las fuentes.",
                "Libre apreciación subjetiva sin motivación alguna."
            ],
            "respuesta_correcta": 0,
            "explicacion": "La interpretación atiende a la especialidad y jerarquía de fuentes."
        }
    ]

    preguntas_seleccionadas = banco[:cantidad]
    resultado: List[Dict[str, Any]] = []

    for idx, p in enumerate(preguntas_seleccionadas, start=1):
        opciones_mezcladas: List[str] = list(p["opciones"])
        idx_corr = int(p["respuesta_correcta"])
        correcta_txt: str = opciones_mezcladas[idx_corr]
        random.shuffle(opciones_mezcladas)
        idx_correcta: int = opciones_mezcladas.index(correcta_txt)

        resultado.append({
            "id": idx,
            "pregunta": p["pregunta"],
            "opciones": opciones_mezcladas,
            "respuesta_correcta": idx_correcta,
            "explicacion": f"💡 {p['explicacion']}"
        })

    return resultado


def generar_preguntas_test(
    texto: Optional[str],
    tema_titulo: str,
    asignatura_nombre: str = "",
    num_preguntas: int = 5,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Genera preguntas de test basadas en el texto del PDF subido o temario.
    Utiliza Gemini AI como motor principal.
    Si se proporciona texto y la llamada a Gemini falla, lanza una excepción clara
    en lugar de recurrir a generadores locales defectuosos.
    Si no hay texto de PDF disponible, utiliza preguntas temáticas predefinidas de respaldo.
    """
    # 1. Si hay texto disponible en los apuntes del tema:
    if texto and len(texto.strip()) > 30:
        return generar_preguntas_con_gemini(
            contenido_texto=texto,
            num_preguntas=num_preguntas,
            api_key=api_key
        )

    # 2. Si no hay contenido de texto en absoluto (no se subió PDF):
    return _generar_preguntas_genericas(tema_titulo, asignatura_nombre, num_preguntas)