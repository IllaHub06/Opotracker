import re
import os
import json
import random
import io
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
    opciones: List[str] = Field(
        description="Lista de exactamente 4 opciones de respuesta distintas, terminadas y completas (sin puntos suspensivos)."
    )
    correcta: int = Field(
        description="Índice entero (0, 1, 2 o 3) correspondiente a la opción de respuesta correcta."
    )
    explicacion: str = Field(
        description="Explicación técnica detallada y completa que justifica por qué la opción señalada es la correcta."
    )


def _limpiar_sin_suspensivos(texto: str) -> str:
    """
    Limpia cadenas eliminando puntos suspensivos finales ('...' o '…')
    y asegura que las oraciones terminen con un punto limpio.
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
    Utiliza modelos oficiales vigentes y response_schema estructurado.
    """

    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key or not key.strip():
        raise ValueError("No se ha configurado la clave de API GEMINI_API_KEY ni GOOGLE_API_KEY.")

    # Inicialización con el cliente oficial de google-genai
    client = genai.Client(api_key=key.strip())

    # Asegurar el límite de caracteres para no perder contexto
    texto_a_enviar = contenido_texto[:MAX_CARACTERES] if len(contenido_texto) > MAX_CARACTERES else contenido_texto

    system_instruction = """
Eres un preparador experto de oposiciones oficiales en España altamente riguroso y técnico.
Tu única tarea es redactar preguntas tipo test profesionales, precisas y completas basadas de manera ESTRICTA en el texto del temario proporcionado.

REGLAS STRICTAS E INVIOLABLES:
1. NADA DE PUNTOS SUSPENSIVOS NI TEXTO TRUNCADO:
   - Tanto los enunciados como CADA UNA de las 4 opciones de respuesta DEBEN ser oraciones íntegras, cerradas y con sentido gramatical completo.
   - Queda STRICTAMENTE PROHIBIDO recortar oraciones con puntos suspensivos ("...") o el carácter "…".
   - Todas las oraciones deben concluir de forma natural y completa.

2. CERO REPETICIÓN Y PROHIBICIÓN DE PLANTILLAS GENÉRICAS:
   - JAMÁS utilices la frase: "Según los apuntes estudiados en el documento, ¿cuál de las siguientes opciones refleja fielmente el texto?".
   - JAMÁS comiences preguntas con muletillas repetitivas como "Según el texto...", "De acuerdo con los apuntes..." o "Indique la opción correcta...".
   - Cada pregunta debe indagar sobre un concepto jurídico o técnico específico (plazos, competencias, definiciones, excepciones, mayorías, trámites).

3. CASTELLANO EXCLUSIVO:
   - Todo el contenido (pregunta, 4 opciones y explicación) DEBE estar redactado al 100% en español/castellano formal.

4. CALIDAD Y PLAUSIBILIDAD DE LAS OPCIONES:
   - Las 4 opciones deben ser técnicamente plausibles, variando plazos, modificando sujetos o invirtiendo requisitos.
   - Queda terminantemente prohibido incluir opciones vacías o de relleno como "No guarda relación", "El texto no lo menciona" o "Opción omitida".
"""

    prompt = f"""
Genera un conjunto de {num_preguntas} preguntas tipo test en ESPAÑOL/CASTELLANO a partir del siguiente temario.

DIVERSIFICACIÓN OBLIGATORIA DE LAS {num_preguntas} PREGUNTAS (cada una debe utilizar una estructura distinta):
1. Pregunta sobre plazos, cómputos temporales, cifras o mayorías numéricas.
2. Pregunta sobre órganos competentes, atribuciones o funciones específicas.
3. Pregunta de completado de proposición normativa o técnica.
4. Pregunta de análisis de afirmaciones o validez de una regla.
5. Pregunta sobre definición, concepto o presupuesto de aplicación.

REQUISITO TÉCNICO:
Devuelve el resultado estrictamente conforme al esquema estructurado solicitado, con exactamente 4 opciones por pregunta y el índice de la opción correcta (0, 1, 2 o 3).

---
TEMARIO:
{texto_a_enviar}
---
"""

    # Modelos oficiales vigentes
    modelos_a_intentar = [
        "gemini-2.0-flash",
        "gemini-1.5-flash"
    ]
    ultimo_error: Optional[Exception] = None

    for nombre_modelo in modelos_a_intentar:
        try:
            response = client.models.generate_content(
                model=nombre_modelo,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=List[PreguntaTestSchema],
                    temperature=0.2,
                ),
            )

            texto_respuesta = response.text.strip() if response.text else ""
            # Limpiar posibles delimitadores markdown si vinieran incluidos
            texto_respuesta = re.sub(r"^```json\s*", "", texto_respuesta, flags=re.MULTILINE)
            texto_respuesta = re.sub(r"^```\s*", "", texto_respuesta, flags=re.MULTILINE)
            texto_respuesta = texto_respuesta.strip()

            datos = json.loads(texto_respuesta)
            if isinstance(datos, list) and len(datos) > 0:
                resultado: List[Dict[str, Any]] = []
                for idx, item in enumerate(datos, start=1):
                    # Limpiar enunciados y opciones de posibles puntos suspensivos
                    preg = _limpiar_sin_suspensivos(str(item.get("pregunta", "")))
                    if preg.endswith("."):
                        preg = preg[:-1]  # Si es pregunta, evitar punto final si ya tiene interrogación

                    ops_raw = item.get("opciones", [])
                    ops: List[str] = [_limpiar_sin_suspensivos(str(o)) for o in ops_raw]

                    while len(ops) < 4:
                        ops.append(f"Disposición supletoria general aplicable {len(ops) + 1}.")
                    ops = ops[:4]

                    corr_val = item.get("correcta", item.get("respuesta_correcta", 0))
                    try:
                        corr_idx = int(corr_val)
                        if corr_idx < 0 or corr_idx >= len(ops):
                            corr_idx = 0
                    except Exception:
                        corr_idx = 0

                    explicacion_txt = _limpiar_sin_suspensivos(
                        str(item.get("explicacion", "Pregunta generada por IA (Gemini) basada en los apuntes del PDF."))
                    )

                    resultado.append({
                        "id": idx,
                        "pregunta": preg,
                        "opciones": ops,
                        "respuesta_correcta": corr_idx,
                        "explicacion": f"💡 {explicacion_txt}" if not explicacion_txt.startswith("💡") else explicacion_txt
                    })
                return resultado
        except Exception as e:
            print(f"[ERROR GEMINI] Falló el modelo {nombre_modelo}: {e}")
            ultimo_error = e
            # Si el fallo es por autenticación o clave inválida, no seguir probando otros modelos
            err_str = str(e).upper()
            if any(k in err_str for k in ["API_KEY_INVALID", "API KEY NOT VALID", "UNAUTHENTICATED", "PERMISSION_DENIED", "401", "403"]):
                raise e
            continue

    raise RuntimeError(f"Error al generar test con Gemini tras intentar los modelos disponibles: {ultimo_error}")


def _extraer_oraciones_relevantes(texto: str) -> List[str]:
    """
    Divide el texto en oraciones relevantes y completas para el generador local de respaldo.
    """
    # Separación por puntos, exclamaciones o saltos dobles de línea
    fragmentos = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n{2,}", texto) if len(p.strip()) > 35]
    oraciones: List[str] = []
    
    for f in fragmentos:
        # Filtrar fragmentos muy cortos o demasiado largos
        if len(f) < 40 or len(f) > 350:
            continue
        # Limpiar espacios repetidos
        oracion_limpia = " ".join(f.split())
        # Descartar si parece encabezado, índice o numeración suelta
        if re.match(r"^(\d+[\.\)]|\-|\*|página|tema\s+\d+|capítulo\s+\d+)\s*$", oracion_limpia, re.IGNORECASE):
            continue
        oraciones.append(oracion_limpia)
    
    return oraciones


def _crear_pregunta_desde_oracion(
    oracion: str,
    idx: int,
    banco_oraciones: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Formula una pregunta tipo test técnica y variada a partir de una oración extraída (fallback local).
    Utiliza al menos 5 estructuras de preguntas distintas y garantiza opciones 100% completas
    sin puntos suspensivos ni frases cortadas.
    """
    oracion_limpia = _limpiar_sin_suspensivos(oracion)
    if len(oracion_limpia) < 30:
        return None

    # Detectores de patrones temáticos
    patron_definicion = re.search(
        r"^(.*?)\s+(es|son|se define como|consiste en|se refiere a|corresponde a|tiene por objeto|se entiende por|comprende)\s+(.+)$",
        oracion_limpia,
        re.IGNORECASE
    )
    patron_numero = re.search(
        r"\b(\d+(?:[.,]\d+)?)\s*(días|meses|años|horas|miembros|diputados|senadores|votos|por ciento|%|euros|artículos)\b",
        oracion_limpia,
        re.IGNORECASE
    )
    patron_articulo_organo = re.search(
        r"(artículo\s+\d+|art\.\s*\d+|disposición\s+\w+|título\s+\w+|capítulo\s+\w+|consejo|ministro|gobierno|tribunal|juzgado|comisión)",
        oracion_limpia,
        re.IGNORECASE
    )
    patron_condicional = re.search(
        r"(?:a fin de|con el objeto de|para|siempre que|en caso de|salvo que|cuando|mediante|a través de)\s+(.+)",
        oracion_limpia,
        re.IGNORECASE
    )

    pregunta = ""
    correcta = ""
    distractores: List[str] = []

    # Selección aleatoria y contextual entre al menos 5 estructuras distintas:
    # 1. Conceptos y Definiciones
    # 2. Plazos, Cifras y Magnitudes
    # 3. Completado de Proposiciones Técnicas
    # 4. Análisis de Afirmaciones / Reglas
    # 5. Requisitos Condicionales y Supuestos de Hecho
    # 6. Competencias y Preceptos

    tipo_pregunta = random.randint(1, 5)

    if patron_definicion and tipo_pregunta == 1:
        # Estructura 1: Concepto y Definición
        sujeto = patron_definicion.group(1).strip()
        verbo = patron_definicion.group(2).strip()
        predicado = patron_definicion.group(3).strip()

        if 5 <= len(sujeto) <= 80 and len(predicado) >= 15:
            plantillas_enunciado = [
                f"¿Cuál de las siguientes afirmaciones define con mayor rigor técnico a «{sujeto}»?",
                f"En relación con «{sujeto}», ¿cuál es su caracterización o definición esencial?",
                f"Respecto al concepto de «{sujeto}», ¿qué regla o función se establece expresamente?",
                f"¿Qué proposición describe con exactitud el régimen aplicable a «{sujeto}»?"
            ]
            pregunta = random.choice(plantillas_enunciado)
            correcta = _limpiar_sin_suspensivos(f"{verbo.capitalize()} {predicado}")
            distractores = [
                _limpiar_sin_suspensivos(f"Tiene carácter exclusivamente facultativo y queda sujeto a discrecionalidad absoluta."),
                _limpiar_sin_suspensivos(f"Se aplica de manera subsidiaria únicamente en defecto de pacto expreso."),
                _limpiar_sin_suspensivos(f"Constituye un trámite no vinculante exento de formalidades preceptivas.")
            ]

    elif patron_numero and (tipo_pregunta == 2 or not pregunta):
        # Estructura 2: Plazos, Cifras y Cuantías
        num_str = patron_numero.group(1)
        unidad = patron_numero.group(2)
        frase_oculta = oracion_limpia.replace(f"{num_str} {unidad}", "[ ... ]")
        if frase_oculta == oracion_limpia:
            frase_oculta = oracion_limpia.replace(f"{num_str}{unidad}", "[ ... ]")

        plantillas_enunciado = [
            f"¿Qué plazo, cifra o cómputo exacto corresponde a la siguiente regla?: «{frase_oculta}»",
            f"Indique la magnitud, plazo o valor cuantitativo fijado para el siguiente supuesto:\n> *\"{frase_oculta}\"*",
            f"De conformidad con la disposición «{frase_oculta}», ¿cuál es el término cuantitativo exigido?",
            f"¿Cuál es el valor numérico o plazo aplicable en este supuesto?: «{frase_oculta}»"
        ]
        pregunta = random.choice(plantillas_enunciado)
        correcta = f"{num_str} {unidad}"

        try:
            val_num = int(float(num_str.replace(",", ".")))
            distractores = [
                f"{max(1, val_num - 5 if val_num > 5 else val_num + 2)} {unidad}",
                f"{val_num * 2} {unidad}",
                f"{val_num + 10} {unidad}"
            ]
        except Exception:
            distractores = [f"15 {unidad}", f"30 {unidad}", f"3 {unidad}"]

    elif tipo_pregunta == 3:
        # Estructura 3: Completar Proposición Técnica (Fill-in-the-blank)
        palabras = oracion_limpia.split()
        if len(palabras) >= 8:
            corte_inicio = max(2, len(palabras) // 3)
            corte_fin = min(len(palabras) - 1, corte_inicio + max(3, len(palabras) // 3))
            fragmento_oculto = " ".join(palabras[corte_inicio:corte_fin])
            frase_con_hueco = " ".join(palabras[:corte_inicio]) + " [ ______ ] " + " ".join(palabras[corte_fin:])

            plantillas_enunciado = [
                f"Complete con exactitud técnica la siguiente proposición:\n> *\"{frase_con_hueco}\"*",
                f"¿Qué contenido o cláusula completa de forma jurídicamente válida el siguiente enunciado?: «{frase_con_hueco}»",
                f"Señale la expresión que culmina con rigor la proposición examinada:\n> *\"{frase_con_hueco}\"*",
                f"Para que el enunciado sea correcto, ¿qué elemento debe figurar en el espacio indicado?: «{frase_con_hueco}»"
            ]
            pregunta = random.choice(plantillas_enunciado)
            correcta = _limpiar_sin_suspensivos(fragmento_oculto)

            distractores = [
                _limpiar_sin_suspensivos("quedará supeditado a previa resolución judicial firme"),
                _limpiar_sin_suspensivos("se tramitará con carácter de urgencia por el órgano consultivo"),
                _limpiar_sin_suspensivos("no surtirá efectos hasta su publicación en el diario oficial correspondiente")
            ]

    elif patron_condicional and (tipo_pregunta == 4 or not pregunta):
        # Estructura 4: Requisitos Condicionales y Supuestos de Hecho
        plantillas_enunciado = [
            f"En relación con el régimen previsto en «{oracion_limpia}», ¿cuál es el presupuesto o requisito esencial fijado?",
            f"¿Qué consecuencia o condición normativa se deriva de la siguiente disposición?: «{oracion_limpia}»",
            f"Respecto al supuesto regulado en «{oracion_limpia}», ¿cuál es la proposición plenamente correcta?",
            f"Indique cuál es la exigencia procedimental establecida en este supuesto: «{oracion_limpia}»"
        ]
        pregunta = random.choice(plantillas_enunciado)
        correcta = _limpiar_sin_suspensivos(oracion_limpia)

        distractores = [
            _limpiar_sin_suspensivos("Requiere la concurrencia simultánea de informe preceptivo y vinculante del órgano superior."),
            _limpiar_sin_suspensivos("Queda condicionado a que no existan reclamaciones previas en vía administrativa."),
            _limpiar_sin_suspensivos("Se aplicará con carácter potestativo a elección exclusiva del interesado.")
        ]

    # Estructura 5 (o por defecto si las anteriores no encajan): Análisis de Afirmaciones / Validez
    if not pregunta or not correcta:
        if patron_articulo_organo:
            ref = patron_articulo_organo.group(1).capitalize()
            plantillas_enunciado = [
                f"En relación con lo establecido respecto a «{ref}», ¿cuál de las siguientes opciones formula con exactitud la regla aplicable?",
                f"Respecto a las previsiones relativas a «{ref}», ¿cuál es la proposición técnicamente correcta?",
                f"¿Qué mandato o atribución se deriva directamente de la regulación de «{ref}»?",
                f"Señale la afirmación que refleja con fidelidad lo dispuesto sobre «{ref}»:"
            ]
        else:
            plantillas_enunciado = [
                "¿Cuál de las siguientes afirmaciones formula con total exactitud la norma o principio examinado?",
                "Señale cuál de las siguientes proposiciones es técnicamente correcta según la materia estudiada:",
                "Indique cuál de las siguientes opciones recoge de manera íntegra y precisa el criterio establecido:",
                "¿Qué enunciado expresa con rigor técnico y plena validez la regla estudiada?",
                "De las siguientes proposiciones, ¿cuál refleja con fidelidad jurídica la materia tratada?"
            ]

        pregunta = random.choice(plantillas_enunciado)
        correcta = _limpiar_sin_suspensivos(oracion_limpia)

        # Usar otras oraciones del banco si existen para construir distractores realistas
        if banco_oraciones and len(banco_oraciones) >= 4:
            otros = [o for o in banco_oraciones if o != oracion_limpia and len(o) > 30]
            if len(otros) >= 3:
                seleccion_otros = random.sample(otros, 3)
                distractores = [_limpiar_sin_suspensivos(s) for s in seleccion_otros]

        if len(distractores) < 3:
            distractores = [
                _limpiar_sin_suspensivos("Su eficacia queda suspendida de pleno derecho con carácter general y sin excepciones."),
                _limpiar_sin_suspensivos("Exige la incoación de procedimiento sancionador ordinario previo a cualquier pronunciamiento."),
                _limpiar_sin_suspensivos("Será de aplicación restrictiva exclusivamente en el ámbito organizativo interno.")
            ]

    opciones = [correcta] + distractores[:3]
    while len(opciones) < 4:
        opciones.append(_limpiar_sin_suspensivos(f"Disposición supletoria complementaria {len(opciones) + 1}."))

    # Asegurar que todas las opciones sean oraciones terminadas y sin puntos suspensivos
    opciones = [_limpiar_sin_suspensivos(op) for op in opciones]

    random.shuffle(opciones)
    idx_correcta = opciones.index(correcta)

    return {
        "id": idx,
        "pregunta": pregunta,
        "opciones": opciones,
        "respuesta_correcta": idx_correcta,
        "explicacion": f"💡 Fundamento extraído del temario: {oracion_limpia}"
    }


def _generar_preguntas_genericas(tema_titulo: str, asignatura_nombre: str, cantidad: int) -> List[Dict[str, Any]]:
    """
    Genera preguntas de respaldo cuando no se ha subido ningún PDF ni hay texto.
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
    Genera preguntas de test basadas EXCLUSIVAMENTE en el texto del PDF subido.
    Utiliza Gemini AI como motor principal.
    Si Gemini falla por cuota o red, procesa el contenido localmente.
    Si falta la clave de API o está mal configurada, lanza un error descriptivo con [ERROR GEMINI].
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
        except ValueError as ve:
            # Error de configuración explícito de API key: registrar y propagar para evitar fallback silencioso
            print(f"[ERROR GEMINI] Error de configuración de clave de API: {ve}")
            raise ve
        except Exception as e:
            err_msg = str(e).upper()
            if any(k in err_msg for k in ["API_KEY_INVALID", "API KEY NOT VALID", "UNAUTHENTICATED", "PERMISSION_DENIED", "401", "403"]):
                print(f"[ERROR GEMINI] Clave de API denegada o no válida: {e}")
                raise ValueError(f"[ERROR GEMINI] La clave de API de Gemini es inválida o carece de permisos: {e}")
            elif any(k in err_msg for k in ["RESOURCE_EXHAUSTED", "429", "QUOTA"]):
                print(f"[ERROR GEMINI] Límite de cuota alcanzado en Gemini ({e}). Activando generador local de respaldo...")
            else:
                print(f"[ERROR GEMINI] Falló la llamada a Gemini ({e}). Usando procesador local del PDF...")

        # Fallback local sobre el texto del PDF
        preguntas_locales: List[Dict[str, Any]] = []
        oraciones = _extraer_oraciones_relevantes(texto)
        random.shuffle(oraciones)

        idx = 1
        for oracion in oraciones:
            item = _crear_pregunta_desde_oracion(oracion, idx, banco_oraciones=oraciones)
            if item:
                preguntas_locales.append(item)
                idx += 1
                if len(preguntas_locales) >= num_preguntas:
                    break

        if preguntas_locales:
            return preguntas_locales[:num_preguntas]

    # 2. Si no hay contenido de texto en absoluto:
    return _generar_preguntas_genericas(tema_titulo, asignatura_nombre, num_preguntas)

