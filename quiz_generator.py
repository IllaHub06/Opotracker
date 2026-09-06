import re
import os
import json
import random
from typing import List, Dict, Any, Optional, TypedDict
import pypdf
import io
from dotenv import load_dotenv

# Importación del SDK actual de Google GenAI
from google import genai
from google.genai import types

# Cargar variables de entorno desde .env
load_dotenv()

class PlantillaPregunta(TypedDict):
    pregunta: str
    opciones: List[str]
    respuesta_correcta: int
    explicacion: str

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

        texto_paginas = []
        for i, page in enumerate(reader.pages):
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
    """
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError("No se ha configurado la clave de API GEMINI_API_KEY.")

    # Inicialización con el cliente de google-genai
    client = genai.Client(api_key=key)

    system_instruction = """
Eres un preparador experto de oposiciones en España. Tu objetivo es generar preguntas de examen tipo test exigentes y variadas a partir del texto proporcionado.

REGLAS OBLIGATORIAS E INVIOLABLES:
1. IDIOMA ÚNICO (CASTELLANO): 
   - Genera el 100% del contenido (enunciados, opciones y explicaciones) EXCLUSIVAMENTE en ESPAÑOL (Castellano).
   - Ignora cualquier texto, ley o fragmento que aparezca en catalán, euskera, gallego o inglés en el documento de origen.
   - Está PROHIBIDO generar opciones en cualquier idioma que no sea castellano.

2. PROHIBIDO REPETIR EL ENUNCIADO GENÉRICO:
   - Queda COMPLETAMENTE PROHIBIDO usar la frase: "Según los apuntes estudiados en el documento, ¿cuál de las siguientes opciones refleja fielmente el texto?".
   - Cada pregunta debe ser concreta, directa y abordar un concepto específico (plazos, artículos, mayorías, definiciones, competencias, excepciones, etc.).

3. FORMATO Y OPCIONES:
   - Formato de 4 opciones por pregunta (solo 1 correcta).
   - Las opciones incorrectas deben ser distractores verosímiles pero falsos sobre el tema.
"""
    prompt = f"""
    Genera un test de {num_preguntas} preguntas tipo test en formato JSON basado estrictamente en el siguiente texto:

    [
      {{
        "pregunta": "Enunciado de la pregunta en castellano",
        "opciones": ["Opción A", "Opción B", "Opción C", "Opción D"],
        "correcta": 0,
        "explicacion": "Explicación en castellano extraída del texto"
      }}
    ]

    Texto de los apuntes:
    {contenido_texto}
    """

    modelos_a_intentar = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    ultimo_error = None

    for nombre_modelo in modelos_a_intentar:
        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash',  # <--- Asegúrate de ponerlo exacto como 'gemini-2.5-flash' o 'gemini-1.5-flash' sin 'models/'
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json"
                )
            )
            texto_respuesta = response.text.strip()  # type: ignore
            # Limpiar posibles bloques markdown si los incluyera
            texto_respuesta = re.sub(r"^```json\s*", "", texto_respuesta, flags=re.MULTILINE)
            texto_respuesta = re.sub(r"^```\s*", "", texto_respuesta, flags=re.MULTILINE)
            texto_respuesta = texto_respuesta.strip()

            datos = json.loads(texto_respuesta)
            if isinstance(datos, list) and len(datos) > 0:
                resultado: List[Dict[str, Any]] = []
                for idx, item in enumerate(datos, start=1):
                    preg = str(item.get("pregunta", ""))
                    ops = [str(o) for o in item.get("opciones", [])]
                    
                    while len(ops) < 4:
                        ops.append("Opción no aplicable")
                    ops = ops[:4]

                    corr_val = item.get("correcta", item.get("respuesta_correcta", 0))
                    try:
                        corr_idx = int(corr_val)
                        if corr_idx < 0 or corr_idx >= len(ops):
                            corr_idx = 0
                    except Exception:
                        corr_idx = 0

                    explicacion_txt = str(item.get("explicacion", "💡 Pregunta generada por IA (Gemini) basada estrictamente en los apuntes del PDF."))

                    resultado.append({
                        "id": idx,
                        "pregunta": preg,
                        "opciones": ops,
                        "respuesta_correcta": corr_idx,
                        "explicacion": explicacion_txt
                    })
                return resultado
        except Exception as e:
            ultimo_error = e
            continue

    raise RuntimeError(f"Error al generar test con Gemini: {ultimo_error}")


def _extraer_oraciones_relevantes(texto: str) -> List[str]:
    """
    Divide el texto en oraciones relevantes para el generador local de respaldo.
    """
    parrafos = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n{2,}", texto) if len(p.strip()) > 35]
    oraciones = []
    
    for p in parrafos:
        if len(p) < 40 or len(p) > 300:
            continue
        oracion = " ".join(p.split())
        oraciones.append(oracion)
    
    return oraciones


def _crear_pregunta_desde_oracion(oracion: str, idx: int) -> Optional[Dict[str, Any]]:
    """
    Intenta formular una pregunta tipo test a partir de una oración extraída (fallback local).
    """
    patron_definicion = re.search(r"^(.*?)\s+(es|son|se define como|consiste en|se refiere a|corresponde a)\s+(.+)$", oracion, re.IGNORECASE)
    patron_articulo = re.search(r"(artículo\s+\d+|art\.\s*\d+)", oracion, re.IGNORECASE)
    patron_numero = re.search(r"\b(\d+)\s+(días|meses|años|horas|miembros|diputados|senadores|por ciento|%)\b", oracion, re.IGNORECASE)
    
    pregunta = ""
    correcta = ""
    distractores = []

    if patron_definicion:
        sujeto = patron_definicion.group(1).strip()
        verbo = patron_definicion.group(2).strip()
        predicado = patron_definicion.group(3).strip()

        if len(sujeto) < 60 and len(predicado) > 15:
            pregunta = f"Según el texto de los apuntes, ¿qué afirma el tema respecto a **{sujeto}**?"
            correcta = f"{verbo.capitalize()} {predicado[:120]}..." if len(predicado) > 120 else f"{verbo.capitalize()} {predicado}"
            distractores = [
                f"No guarda relación con {sujeto} según el temario.",
                f"Es una función excluida del temario analizado.",
                f"Queda sin efecto en el contexto estudiado."
            ]
    elif patron_numero:
        num = patron_numero.group(1)
        unidad = patron_numero.group(2)
        frase_oculta = oracion.replace(f"{num} {unidad}", f"[ ... {unidad} ... ]")
        pregunta = f"Completa el enunciado de acuerdo con el texto:\n> *\"{frase_oculta}\"*"
        correcta = f"{num} {unidad}"
        
        try:
            val_num = int(num)
            distractores = [
                f"{max(1, val_num - 5)} {unidad}",
                f"{val_num * 2} {unidad}",
                f"{val_num + 10} {unidad}"
            ]
        except Exception:
            distractores = [f"30 {unidad}", f"15 {unidad}", f"3 {unidad}"]
    elif patron_articulo:
        art = patron_articulo.group(1).capitalize()
        pregunta = f"En relación con lo establecido en el **{art}** citado en los apuntes, ¿cuál es la proposición correcta?"
        correcta = oracion if len(oracion) <= 140 else oracion[:137] + "..."
        distractores = [
            f"El {art} no se menciona en los apuntes analizados.",
            f"Establece una regulación incompatible con el texto.",
            f"Carece de validez según los apuntes adjuntos."
        ]
    else:
        pregunta = f"Según los apuntes estudiados en el documento, ¿cuál de las siguientes opciones refleja fielmente el texto?"
        correcta = oracion if len(oracion) <= 140 else oracion[:137] + "..."
        distractores = [
            "El texto no menciona ninguna relación al respecto.",
            "Contradice directamente lo expuesto en el temario.",
            "Se trata de un procedimiento omitido en el documento."
        ]

    if not pregunta or not correcta:
        return None

    opciones = [correcta] + distractores[:3]
    while len(opciones) < 4:
        opciones.append("Ninguna de las respuestas anteriores es correcta.")

    random.shuffle(opciones)
    idx_correcta = opciones.index(correcta)

    return {
        "id": idx,
        "pregunta": pregunta,
        "opciones": opciones,
        "respuesta_correcta": idx_correcta,
        "explicacion": f"💡 **Texto del documento:** {oracion}"
    }


def _generar_preguntas_genericas(tema_titulo: str, asignatura_nombre: str, cantidad: int) -> List[Dict[str, Any]]:
    """
    Genera preguntas de respaldo cuando no se ha subido ningún PDF ni hay texto.
    """
    banco: List[PlantillaPregunta] = [
        {
            "pregunta": f"¿Cuál es el objeto y contenido fundamental de **\"{tema_titulo}\"**?",
            "opciones": [
                f"Estudiar los conceptos esenciales, definiciones y marco de aplicación de {tema_titulo}.",
                "Limitarse a aspectos históricos sin vigencia actual.",
                "Analizar procedimientos derogados.",
                "Sustituir la normativa por directivas sin transponer."
            ],
            "respuesta_correcta": 0,
            "explicacion": f"El tema {tema_titulo} aborda los conceptos y fundamentos de la materia."
        },
        {
            "pregunta": f"Respecto a **\"{tema_titulo}\"**, ¿cuál es el principio básico de aplicación?",
            "opciones": [
                "Principio de legalidad, rigor técnico y adecuación a la materia.",
                "Discrecionalidad absoluta sin sujeción a normas.",
                "Invalidez general de los conceptos básicos.",
                "Exclusión de plazos o requisitos formales."
            ],
            "respuesta_correcta": 0,
            "explicacion": "Todo el temario se estructura bajo criterios de rigor y adecuación normativa."
        },
        {
            "pregunta": f"En relación con los plazos y términos en **\"{tema_titulo}\"**, ¿qué criterio prevalece?",
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
            "pregunta": f"¿Qué elemento es indispensable para la validez de los actos en **\"{tema_titulo}\"**?",
            "opciones": [
                "Cumplir con los requisitos formales y de competencia previstos en el temario.",
                "La mera voluntad individual sin trámite alguno.",
                "El transcurso indefinido del tiempo.",
                "La ausencia total de notificación o comunicación."
            ],
            "respuesta_correcta": 0,
            "explicacion": "Los actos y procedimientos requieren cumplimiento de los requisitos establecidos."
        },
        {
            "pregunta": f"Ante dudas de interpretación sobre los conceptos de **\"{tema_titulo}\"**, ¿qué criterio debe primar?",
            "opciones": [
                "Criterio de jerarquía, especialidad y sentido propio de las palabras.",
                "Criterio aleatorio sin fundamento técnico.",
                "Inaplicabilidad simultánea de todas las fuentes.",
                "Libre apreciación subjetiva sin motivación."
            ],
            "respuesta_correcta": 0,
            "explicacion": "La interpretación de normas y conceptos atiende a la especialidad y jerarquía de fuentes."
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
            "explicacion": p["explicacion"]
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
    Genera preguntas de test basadas EXCLUSIVAMENTE en el texto del PDF subido.
    Utiliza Gemini AI como motor principal.
    Si Gemini falla o no hay API key, procesa el contenido_texto localmente.
    """
    # 1. Si hay texto disponible en los apuntes:
    if texto and len(texto.strip()) > 30:
        # Intentar llamada a Gemini
        try:
            preguntas_gemini = generar_preguntas_con_gemini(
                contenido_texto=texto,
                num_preguntas=num_preguntas,
                api_key=api_key
            )
            if preguntas_gemini and len(preguntas_gemini) > 0:
                return preguntas_gemini
        except Exception as e:
            print(f"Aviso: Falló la generación con Gemini ({e}). Usando procesador local del PDF...")

        # Fallback local sobre el texto del PDF
        preguntas_locales = []
        oraciones = _extraer_oraciones_relevantes(texto)
        random.shuffle(oraciones)

        idx = 1
        for oracion in oraciones:
            item = _crear_pregunta_desde_oracion(oracion, idx)
            if item:
                preguntas_locales.append(item)
                idx += 1
                if len(preguntas_locales) >= num_preguntas:
                    break

        if preguntas_locales:
            return preguntas_locales[:num_preguntas]

    # 2. Si no hay contenido de texto en absoluto:
    return _generar_preguntas_genericas(tema_titulo, asignatura_nombre, num_preguntas)
