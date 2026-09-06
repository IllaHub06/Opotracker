# pyrefly: ignore [missing-import]
import streamlit as st
import time
import os
from datetime import datetime, date
from contextlib import contextmanager
# pyrefly: ignore [missing-import]
import pandas as pd

# Importar modelos y base de datos de Opotracker
# pyrefly: ignore [missing-import]
import models
# pyrefly: ignore [missing-import]
from init_db import SessionLocal, engine
# pyrefly: ignore [missing-import]
from algorithm import obtener_temas_prioritarios
# pyrefly: ignore [missing-import]
import quiz_generator

# Directorio para guardar archivos PDF
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Asegurar creación de tablas en la base de datos
models.Base.metadata.create_all(bind=engine)

# Configuración de página
st.set_page_config(
    page_title="Opotracker - Repaso Inteligente",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados para mejorar el diseño visual
st.markdown("""
<style>
    /* Estilos globales */
    .main {
        background-color: #f8fafc;
    }
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        color: white;
        padding: 1.2rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        text-align: center;
    }
    .ranking-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 6px solid #3b82f6;
        padding: 1rem 1.25rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }
    .badge-alta {
        background-color: #fee2e2;
        color: #991b1b;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-media {
        background-color: #fef3c7;
        color: #92400e;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-baja {
        background-color: #dcfce7;
        color: #166534;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .subject-pill {
        display: inline-block;
        padding: 0.2rem 0.75rem;
        border-radius: 6px;
        color: white;
        font-weight: 500;
        font-size: 0.85rem;
    }
    .pdf-badge {
        background-color: #dbeafe;
        color: #1e40af;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
        margin-left: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


@contextmanager
def get_db():
    """Generador de sesión de base de datos seguro con cierre automático."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==========================================================
# BARRA LATERAL (NAVEGACIÓN)
# ==========================================================
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3429/3429180.png", width=70)
st.sidebar.title("🎯 Opotracker")
st.sidebar.caption("Sistema de Repaso Espaciado con Tests NotebookLM")

menu = st.sidebar.radio(
    "Menú de Navegación",
    [
        "🏆 Ranking de Repasos",
        "📚 Asignaturas",
        "📝 Temas",
        "⏱️ Registrar Repaso",
        "📊 Historial de Repasos"
    ],
    index=0
)

st.sidebar.markdown("---")
gemini_env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""

with st.sidebar.expander("🔑 Configuración IA (Gemini)", expanded=(not bool(gemini_env_key))):
    st.caption("Obtén tu clave gratuita en [Google AI Studio](https://aistudio.google.com/app/apikey)")
    user_key_input = st.text_input(
        "Clave de API Gemini",
        value=gemini_env_key,
        type="password",
        placeholder="AIzaSy...",
        help="Guarda tu clave GEMINI_API_KEY para habilitar la generación de tests con IA."
    )
    if user_key_input and user_key_input.strip() != gemini_env_key:
        clave_limpia = user_key_input.strip()
        os.environ["GEMINI_API_KEY"] = clave_limpia
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        try:
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f"# Clave de API de Google Gemini\nGEMINI_API_KEY={clave_limpia}\n")
            st.success("✅ Clave guardada permanentemente en .env")
        except Exception as e:
            st.warning(f"No se pudo escribir en .env: {e}")

if os.environ.get("GEMINI_API_KEY"):
    st.sidebar.success("🟢 IA Gemini Conectada")
else:
    st.sidebar.warning("⚠️ Sin clave Gemini (usando extractor local)")


# ==========================================================
# SECCIÓN 1: RANKING DE REPASOS (DASHBOARD PRINCIPAL)
# ==========================================================
if menu == "🏆 Ranking de Repasos":
    st.title("🏆 Ranking de Temas Recomendados para Repasar")
    st.write("Temas ordenados automáticamente por el algoritmo según **prioridad**, **días sin repasar** y **última nota**.")

    with get_db() as db:
        asignaturas_count = db.query(models.Asignatura).count()
        temas_total = db.query(models.Tema).all()
        repasos_count = db.query(models.HistorialRepasos).count()

        # Métricas rápidas
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📚 Asignaturas", asignaturas_count)
        col2.metric("📝 Temas Totales", len(temas_total))
        col3.metric("⏱️ Repasos Realizados", repasos_count)
        
        # Calcular temas recomendados
        limite_ranking = st.sidebar.slider("Número de recomendaciones", min_value=3, max_value=20, value=5)
        recomendaciones = obtener_temas_prioritarios(temas_total, limite=limite_ranking)
        
        col4.metric("🔥 Temas Prioritarios", len(recomendaciones))
        st.markdown("---")

        if not temas_total:
            st.warning("⚠️ Todavía no tienes temas registrados. Ve a **Asignaturas** y **Temas** para añadir tu temario.")
        else:
            medals = ["🥇", "🥈", "🥉"]
            for idx, item in enumerate(recomendaciones, start=1):
                tema = item["tema"]
                urgencia = item["urgencia"]
                
                # Prioridad Badge
                if tema.prioridad == 3:
                    prioridad_label = '<span class="badge-alta">🔴 Alta</span>'
                elif tema.prioridad == 2:
                    prioridad_label = '<span class="badge-media">🟡 Media</span>'
                else:
                    prioridad_label = '<span class="badge-baja">🟢 Baja</span>'
                
                # Asignatura Color
                color_asig = tema.asignatura.color if tema.asignatura and tema.asignatura.color else "#3B82F6"
                nombre_asig = tema.asignatura.nombre if tema.asignatura else "Sin asignatura"
                
                # Medalla o número
                icono_pos = medals[idx - 1] if idx <= 3 else f"**#{idx}**"
                
                # Último repaso y total repasos
                total_repasos = len(tema.historial_repasos)
                if total_repasos > 0:
                    ultimo = max(tema.historial_repasos, key=lambda r: r.fecha_repaso)
                    fecha_str = ultimo.fecha_repaso.strftime("%d/%m/%Y")
                    nota_val = ultimo.aciertos if hasattr(ultimo, 'aciertos') and ultimo.aciertos is not None else ultimo.puntuacion
                    nota_str = f"{nota_val:.1f}%" if nota_val is not None else "Sin nota"
                    estado_repaso = f"Último repaso: **{fecha_str}** | Nota: **{nota_str}** | Total: **{total_repasos} veces**"
                else:
                    estado_repaso = "<span style='color: #dc2626; font-weight:600;'>🚨 NUNCA REPASADO</span>"

                numero_tema_str = f"Tema {tema.numero_tema}: " if tema.numero_tema else ""
                pdf_tag = '<span class="pdf-badge">📄 PDF Adjunto</span>' if hasattr(tema, 'archivo_pdf') and tema.archivo_pdf else ''

                st.markdown(f"""
                <div class="ranking-card" style="border-left-color: {color_asig};">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <h4 style="margin: 0;">{icono_pos} {numero_tema_str}{tema.titulo} {pdf_tag}</h4>
                        <span class="subject-pill" style="background-color: {color_asig};">{nombre_asig}</span>
                    </div>
                    <div style="display: flex; gap: 1.5rem; align-items: center; font-size: 0.95rem;">
                        <div>{prioridad_label}</div>
                        <div>⚡ Urgencia: <strong>{urgencia} pts</strong></div>
                        <div>{estado_repaso}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)


# ==========================================================
# SECCIÓN 2: GESTIÓN DE ASIGNATURAS
# ==========================================================
elif menu == "📚 Asignaturas":
    st.title("📚 Gestión de Asignaturas")
    st.write("Crea y organiza las materias de tu oposición con colores personalizados.")

    tab1, tab2 = st.tabs(["➕ Nueva Asignatura", "📋 Lista de Asignaturas"])

    with tab1:
        with st.form("form_crear_asignatura", clear_on_submit=True):
            st.subheader("Crear Asignatura")
            col_nom, col_col = st.columns([3, 1])
            nombre_asig = col_nom.text_input("Nombre de la Asignatura *", placeholder="Ej. Derecho Constitucional, Informática...")
            color_asig = col_col.color_picker("Color identificativo", value="#3B82F6")
            
            submit_asig = st.form_submit_button("💾 Guardar Asignatura", use_container_width=True)

            if submit_asig:
                if not nombre_asig.strip():
                    st.error("❌ El nombre de la asignatura no puede estar vacío.")
                else:
                    with get_db() as db:
                        nueva_asig = models.Asignatura(
                            nombre=nombre_asig.strip(),
                            color=color_asig,
                            fecha_creacion=datetime.utcnow()
                        )
                        db.add(nueva_asig)
                        db.commit()
                        st.success(f"✅ Asignatura **'{nombre_asig}'** creada correctamente.")
                        st.rerun()

    with tab2:
        with get_db() as db:
            asignaturas = db.query(models.Asignatura).all()
            if not asignaturas:
                st.info("No hay asignaturas registradas. Crea una en la pestaña superior.")
            else:
                for asig in asignaturas:
                    with st.container():
                        col_card, col_action = st.columns([4, 1])
                        num_temas = len(asig.temas)
                        col_card.markdown(f"""
                        <div style="background: white; border: 1px solid #e2e8f0; border-left: 6px solid {asig.color}; padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem;">
                            <h4 style="margin: 0; color: #1e293b;">{asig.nombre}</h4>
                            <p style="margin: 0.3rem 0 0 0; color: #64748b; font-size: 0.9rem;">
                                📖 {num_temas} tema(s) registrado(s) • Creada el {asig.fecha_creacion.strftime('%d/%m/%Y')}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if col_action.button("🗑️ Eliminar", key=f"del_asig_{asig.id}", help="Elimina la asignatura y todos sus temas"):
                            db.delete(asig)
                            db.commit()
                            st.warning(f"Asignatura '{asig.nombre}' eliminada.")
                            st.rerun()


# ==========================================================
# SECCIÓN 3: GESTIÓN DE TEMAS (CON SUBIDA DE PDF Y EXTRACCIÓN)
# ==========================================================
elif menu == "📝 Temas":
    st.title("📝 Gestión de Temas")
    st.write("Añade temas a tus asignaturas, sube archivos PDF con el contenido y define su nivel de prioridad.")

    with get_db() as db:
        asignaturas = db.query(models.Asignatura).all()

        if not asignaturas:
            st.warning("⚠️ Primero debes crear al menos una **Asignatura** antes de registrar temas.")
        else:
            tab1, tab2 = st.tabs(["➕ Nuevo Tema", "📋 Explorar Temas"])

            with tab1:
                with st.form("form_crear_tema", clear_on_submit=False):
                    st.subheader("Registrar Nuevo Tema")
                    
                    # Selector de Asignatura
                    opciones_asig = {asig.id: asig.nombre for asig in asignaturas}
                    asig_seleccionada = st.selectbox(
                        "Asignatura *",
                        options=list(opciones_asig.keys()),
                        format_func=lambda x: opciones_asig.get(x, "")
                    )

                    col_num, col_tit = st.columns([1, 3])
                    numero_tema = col_num.number_input("Nº Tema (Opcional)", min_value=1, step=1, value=None)
                    titulo_tema = col_tit.text_input("Título del Tema *", placeholder="Ej. La Constitución Española de 1978...")

                    prioridad = st.select_slider(
                        "Nivel de Prioridad / Dificultad",
                        options=[1, 2, 3],
                        value=2,
                        format_func=lambda x: {1: "🟢 1 - Baja", 2: "🟡 2 - Media", 3: "🔴 3 - Alta"}.get(x, "")
                    )

                    st.markdown("---")
                    st.markdown("##### 📄 Contenido PDF para Tests estilo NotebookLM")
                    pdf_upload = st.file_uploader(
                        "Sube el documento PDF del tema (opcional)",
                        type=["pdf"],
                        help="Extraeremos automáticamente el contenido con pypdf para formular preguntas inteligentes de test."
                    )

                    submit_tema = st.form_submit_button("💾 Guardar Tema", use_container_width=True)

                    if submit_tema:
                        if not titulo_tema.strip():
                            st.error("❌ El título del tema es obligatorio.")
                        else:
                            ruta_pdf_guardado = None
                            texto_extraido = None

                            if pdf_upload is not None:
                                try:
                                    nombre_limpio = f"tema_{int(time.time())}_{pdf_upload.name.replace(' ', '_')}"
                                    ruta_completa = os.path.join(UPLOAD_DIR, nombre_limpio)
                                    with open(ruta_completa, "wb") as f:
                                        f.write(pdf_upload.getbuffer())
                                    
                                    ruta_pdf_guardado = ruta_completa
                                    texto_extraido = quiz_generator.extraer_texto_pdf(ruta_completa)
                                    st.info(f"📑 PDF procesado: se han extraído **{len(texto_extraido)} caracteres** para los tests.")
                                except Exception as e:
                                    st.warning(f"⚠️ No se pudo procesar el PDF: {e}")

                            nuevo_tema = models.Tema(
                                id_asignatura=asig_seleccionada,
                                numero_tema=numero_tema if numero_tema else None,
                                titulo=titulo_tema.strip(),
                                prioridad=prioridad,
                                archivo_pdf=ruta_pdf_guardado,
                                contenido_texto=texto_extraido,
                                fecha_creacion=datetime.utcnow()
                            )
                            db.add(nuevo_tema)
                            db.commit()
                            st.success(f"✅ Tema **'{titulo_tema}'** creado con éxito.")
                            st.rerun()

            with tab2:
                # Filtros de visualización
                col_f1, col_f2 = st.columns(2)
                filtro_asig = col_f1.selectbox(
                    "Filtrar por Asignatura",
                    options=["Todas"] + [a.nombre for a in asignaturas]
                )
                filtro_prio = col_f2.selectbox(
                    "Filtrar por Prioridad",
                    options=["Todas", "🔴 Alta (3)", "🟡 Media (2)", "🟢 Baja (1)"]
                )

                query = db.query(models.Tema)
                if filtro_asig != "Todas":
                    query = query.join(models.Asignatura).filter(models.Asignatura.nombre == filtro_asig)
                if filtro_prio == "🔴 Alta (3)":
                    query = query.filter(models.Tema.prioridad == 3)
                elif filtro_prio == "🟡 Media (2)":
                    query = query.filter(models.Tema.prioridad == 2)
                elif filtro_prio == "🟢 Baja (1)":
                    query = query.filter(models.Tema.prioridad == 1)

                temas_filtrados = query.all()

                if not temas_filtrados:
                    st.info("No hay temas que coincidan con los filtros.")
                else:
                    for t in temas_filtrados:
                        with st.container():
                            col_info, col_del = st.columns([5, 1])
                            num_str = f"Tema {t.numero_tema}: " if t.numero_tema else ""
                            prio_dict = {1: "🟢 Baja", 2: "🟡 Media", 3: "🔴 Alta"}
                            prio_str = prio_dict.get(int(t.prioridad), "🟡 Media")
                            asig_nom = t.asignatura.nombre if t.asignatura else "Sin Asignatura"
                            total_repasos = len(t.historial_repasos)
                            pdf_badge_html = f'<span class="pdf-badge">📄 PDF Adjunto ({len(t.contenido_texto)} car.)</span>' if getattr(t, 'contenido_texto', None) else ''
                            
                            col_info.markdown(f"""
                            <div style="background: white; border: 1px solid #e2e8f0; padding: 0.8rem 1rem; border-radius: 6px; margin-bottom: 0.4rem;">
                                <strong>{num_str}{t.titulo}</strong> <span style="color: #64748b;">({asig_nom})</span> {pdf_badge_html}
                                <br><small>Prioridad: <b>{prio_str}</b> | Repasos: <b>{total_repasos}</b></small>
                            </div>
                            """, unsafe_allow_html=True)

                            if hasattr(t, 'contenido_texto') and t.contenido_texto:
                                with col_info.expander("🔍 Ver extracto del PDF guardado"):
                                    st.caption(t.contenido_texto[:400] + ("..." if len(t.contenido_texto) > 400 else ""))

                            if col_del.button("🗑️", key=f"del_tema_{t.id}", help="Eliminar tema"):
                                db.delete(t)
                                db.commit()
                                st.warning(f"Tema '{t.titulo}' eliminado.")
                                st.rerun()


# ==========================================================
# SECCIÓN 4: REGISTRAR REPASO (TEST NOTEBOOKLM O MANUAL)
# ==========================================================
elif menu == "⏱️ Registrar Repaso":
    st.title("⏱️ Sesión de Estudio y Repaso de Temas")
    st.write("Realiza un test interactivo con cronómetro estilo NotebookLM o registra tu sesión manualmente.")

    with get_db() as db:
        temas = db.query(models.Tema).all()

        if not temas:
            st.warning("⚠️ No hay temas registrados en el sistema. Añade temas primero.")
        else:
            tab_test, tab_manual = st.tabs(["🧠 Test Inteligente (NotebookLM)", "✍️ Registro Manual de Sesión"])

            # ----------------------------------------------------
            # PESTAÑA 1: TEST INTELIGENTE CON CRONÓMETRO
            # ----------------------------------------------------
            with tab_test:
                # 1. PANTALLA DE RESULTADOS (SI YA SE FINALIZÓ EL TEST)
                if st.session_state.get("test_finalizado", False) and st.session_state.get("test_resultado"):
                    res = st.session_state["test_resultado"]
                    
                    if res["porcentaje"] >= 80:
                        st.balloons()
                        st.success(f"🎉 **¡Excelente trabajo!** Has obtenido un **{res['porcentaje']}%** de aciertos.")
                    elif res["porcentaje"] >= 50:
                        st.info(f"👍 **¡Aprobado!** Has obtenido un **{res['porcentaje']}%** de aciertos. Buen ritmo de estudio.")
                    else:
                        st.warning(f"⚠️ **Refuerzo recomendado:** Has obtenido un **{res['porcentaje']}%** de aciertos. El algoritmo priorizará este tema en tu ranking.")

                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("🎯 Aciertos", f"{res['porcentaje']}%", f"{res['aciertos_count']} de {res['total_p']} correctas")
                    
                    minutos_str = f"{res['duracion_seg'] // 60}m {res['duracion_seg'] % 60}s"
                    col_m2.metric("⏱️ Duración", minutos_str, f"{res['duracion_min']} min registrados")
                    col_m3.metric("📈 Estado", "Guardado en BD", "Ranking actualizado")

                    st.markdown("---")
                    st.subheader("📋 Corrección Detallada del Examen:")

                    for idx, d in enumerate(res["desglose"], start=1):
                        with st.container():
                            if d["es_correcta"]:
                                st.markdown(f"""
                                <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 0.8rem 1rem; border-radius: 8px; margin-bottom: 0.6rem;">
                                    <span style="color: #166534; font-weight: 700;">✅ Pregunta {idx}: Correcta</span>
                                    <p style="margin: 0.3rem 0; font-weight: 600;">{d['pregunta']}</p>
                                    <p style="color: #15803d; margin: 0.2rem 0; font-size: 0.95rem;">✔️ <b>Tu respuesta:</b> {d['opciones'][d['seleccion']]}</p>
                                    <small style="color: #4b5563;">{d['explicacion']}</small>
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                user_txt = d['opciones'][d['seleccion']] if 0 <= d['seleccion'] < len(d['opciones']) else "Sin responder"
                                corr_txt = d['opciones'][d['correcta']] if 0 <= d['correcta'] < len(d['opciones']) else ""
                                st.markdown(f"""
                                <div style="background-color: #fef2f2; border: 1px solid #fecaca; padding: 0.8rem 1rem; border-radius: 8px; margin-bottom: 0.6rem;">
                                    <span style="color: #991b1b; font-weight: 700;">❌ Pregunta {idx}: Fallada</span>
                                    <p style="margin: 0.3rem 0; font-weight: 600;">{d['pregunta']}</p>
                                    <p style="color: #b91c1c; margin: 0.2rem 0; font-size: 0.95rem;">❌ <b>Tu respuesta:</b> {user_txt}</p>
                                    <p style="color: #15803d; margin: 0.2rem 0; font-size: 0.95rem;">✔️ <b>Respuesta correcta:</b> {corr_txt}</p>
                                    <small style="color: #4b5563;">{d['explicacion']}</small>
                                </div>
                                """, unsafe_allow_html=True)

                    st.markdown("---")
                    if st.button("🔄 Realizar Otro Test", type="primary", use_container_width=True):
                        st.session_state["test_activo"] = False
                        st.session_state["test_finalizado"] = False
                        st.session_state["test_resultado"] = None
                        st.session_state["test_preguntas"] = None
                        st.rerun()

                # 2. PANTALLA DE EXAMEN EN CURSO (CON CRONÓMETRO)
                elif st.session_state.get("test_activo", False) and st.session_state.get("test_preguntas"):
                    col_t_info, col_t_cancel = st.columns([4, 1])
                    with col_t_info:
                        hora_inicio = datetime.fromtimestamp(st.session_state["test_inicio_time"]).strftime("%H:%M:%S")
                        st.info(f"⏱️ **Examen en curso:** {st.session_state['test_tema_titulo']} | *Iniciado a las {hora_inicio} — Cronómetro activo*")
                    with col_t_cancel:
                        if st.button("❌ Cancelar", use_container_width=True, help="Cancela el examen sin guardar métricas"):
                            st.session_state["test_activo"] = False
                            st.session_state["test_preguntas"] = None
                            st.rerun()

                    with st.form("form_examen_activo"):
                        st.markdown("#### 📝 Responde a las preguntas formuladas:")
                        respuestas_usuario = {}

                        for i, p in enumerate(st.session_state["test_preguntas"]):
                            st.markdown(f"**{i+1}. {p['pregunta']}**")
                            resp = st.radio(
                                f"Selección para pregunta {i+1}:",
                                options=list(range(len(p["opciones"]))),
                                format_func=lambda idx, p_item=p: p_item["opciones"][idx],
                                key=f"preg_opt_{i}",
                                label_visibility="collapsed"
                            )
                            respuestas_usuario[i] = resp
                            st.markdown("---")

                        submit_examen = st.form_submit_button("🏁 Finalizar y Corregir Test", use_container_width=True)

                        if submit_examen:
                            tiempo_fin = time.time()
                            duracion_segundos = max(1, int(tiempo_fin - st.session_state["test_inicio_time"]))
                            duracion_minutos = max(1, round(duracion_segundos / 60))

                            total_p = len(st.session_state["test_preguntas"])
                            aciertos_count = 0
                            desglose = []

                            for i, q in enumerate(st.session_state["test_preguntas"]):
                                ans_idx = respuestas_usuario.get(i, -1)
                                is_ok = (ans_idx == q["respuesta_correcta"])
                                if is_ok:
                                    aciertos_count += 1
                                desglose.append({
                                    "pregunta": q["pregunta"],
                                    "opciones": q["opciones"],
                                    "seleccion": ans_idx,
                                    "correcta": q["respuesta_correcta"],
                                    "es_correcta": is_ok,
                                    "explicacion": q.get("explicacion", "")
                                })

                            porcentaje = round((aciertos_count / total_p) * 100, 1)

                            # Guardar en base de datos
                            nuevo_repaso = models.HistorialRepasos(
                                id_tema=st.session_state["test_tema_id"],
                                puntuacion=porcentaje,
                                tiempo_tardado=duracion_minutos,
                                fecha_repaso=datetime.utcnow()
                            )
                            db.add(nuevo_repaso)
                            db.commit()

                            st.session_state["test_finalizado"] = True
                            st.session_state["test_resultado"] = {
                                "aciertos_count": aciertos_count,
                                "total_p": total_p,
                                "porcentaje": porcentaje,
                                "duracion_seg": duracion_segundos,
                                "duracion_min": duracion_minutos,
                                "desglose": desglose,
                                "tema_titulo": st.session_state["test_tema_titulo"]
                            }
                            st.rerun()

                # 3. PANTALLA INICIAL: SELECCIÓN Y GENERACIÓN DEL TEST
                else:
                    st.subheader("Generador de Test Inteligente con Cronómetro")
                    st.write("Genera preguntas automáticas a partir del contenido PDF de tu tema o su temática.")

                    opciones_tema = {
                        t.id: f"{t.asignatura.nombre if t.asignatura else 'General'} - {'Tema ' + str(t.numero_tema) + ': ' if t.numero_tema else ''}{t.titulo}"
                        for t in temas
                    }

                    tema_sel_id = st.selectbox(
                        "Selecciona el Tema para el Test *",
                        options=list(opciones_tema.keys()),
                        format_func=lambda x: opciones_tema.get(x, "")
                    )

                    tema_obj = db.query(models.Tema).filter(models.Tema.id == tema_sel_id).first()

                    if tema_obj:
                        col_info1, col_info2 = st.columns(2)
                        with col_info1:
                            if hasattr(tema_obj, 'contenido_texto') and tema_obj.contenido_texto:
                                st.success(f"📄 **PDF Cargado ({len(tema_obj.contenido_texto)} caracteres):** El test se generará con IA (Gemini) basándose **ESTRICTAMENTE** en tus apuntes.")
                            else:
                                st.warning("⚠️ **Sin PDF adjunto:** Para un test basado exactamente en tus apuntes, sube el PDF en **Temas**. De lo contrario se generarán preguntas temáticas generales.")
                        with col_info2:
                            num_preguntas = st.select_slider(
                                "Número de Preguntas del Test",
                                options=[3, 5, 10],
                                value=5
                            )

                        if st.button("🚀 Iniciar Test con Cronómetro", type="primary", use_container_width=True):
                            with st.spinner("🤖 Analizando tus apuntes con Gemini y generando preguntas..."):
                                gemini_k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                                preguntas = quiz_generator.generar_preguntas_test(
                                    texto=getattr(tema_obj, 'contenido_texto', None),
                                    tema_titulo=tema_obj.titulo,
                                    asignatura_nombre=tema_obj.asignatura.nombre if tema_obj.asignatura else "",
                                    num_preguntas=num_preguntas,
                                    api_key=gemini_k
                                )
                                st.session_state["test_activo"] = True
                                st.session_state["test_tema_id"] = tema_obj.id
                                st.session_state["test_tema_titulo"] = tema_obj.titulo
                                st.session_state["test_asig_nombre"] = tema_obj.asignatura.nombre if tema_obj.asignatura else "General"
                                st.session_state["test_inicio_time"] = time.time()
                                st.session_state["test_preguntas"] = preguntas
                                st.session_state["test_finalizado"] = False
                                st.session_state["test_resultado"] = None
                                st.rerun()

            # ----------------------------------------------------
            # PESTAÑA 2: REGISTRO MANUAL DE SESIÓN
            # ----------------------------------------------------
            with tab_manual:
                st.subheader("Registro Manual de Sesión de Estudio")
                with st.form("form_repaso_manual", clear_on_submit=True):
                    opciones_tema_man = {
                        t.id: f"{t.asignatura.nombre if t.asignatura else 'General'} - {'Tema ' + str(t.numero_tema) + ': ' if t.numero_tema else ''}{t.titulo}"
                        for t in temas
                    }
                    
                    tema_sel_man = st.selectbox(
                        "Selecciona el Tema Repasado *",
                        options=list(opciones_tema_man.keys()),
                        format_func=lambda x: opciones_tema_man.get(x, "")
                    )

                    col_nota, col_tiempo = st.columns(2)
                    puntuacion = col_nota.slider(
                        "Porcentaje de Aciertos (%)",
                        min_value=0.0,
                        max_value=100.0,
                        value=80.0,
                        step=0.5,
                        help="Porcentaje de aciertos conseguido en la prueba"
                    )
                    
                    tiempo_tardado = col_tiempo.number_input(
                        "Duración / Tiempo Dedicado (minutos)",
                        min_value=1,
                        max_value=600,
                        value=30,
                        step=5
                    )

                    fecha_repaso = st.date_input("Fecha del Repaso", value=date.today())

                    submit_repaso = st.form_submit_button("💾 Guardar Repaso Manual", use_container_width=True)

                    if submit_repaso:
                        fecha_dt = datetime.combine(fecha_repaso, datetime.min.time())
                        nuevo_repaso = models.HistorialRepasos(
                            id_tema=tema_sel_man,
                            puntuacion=puntuacion,
                            tiempo_tardado=tiempo_tardado,
                            aciertos=puntuacion,
                            duracion=tiempo_tardado,
                            fecha_repaso=fecha_dt
                        )
                        db.add(nuevo_repaso)
                        db.commit()
                        st.success("🎉 ¡Repaso registrado con éxito! El ranking ha sido recalculado.")


# ==========================================================
# SECCIÓN 5: HISTORIAL DE REPASOS (CON FILTROS Y MÉTRICAS)
# ==========================================================
elif menu == "📊 Historial de Repasos":
    st.title("📊 Historial de Repasos y Métricas")
    st.write("Consulta y filtra todas las sesiones de estudio y tests realizados.")

    with get_db() as db:
        temas = db.query(models.Tema).all()
        
        # Filtros interactivos
        with st.expander("🔍 Filtros de Búsqueda", expanded=True):
            col_f1, col_f2, col_f3 = st.columns(3)
            
            opciones_filtro_tema = {0: "Todos los temas"}
            for t in temas:
                num_str = f"Tema {t.numero_tema}: " if t.numero_tema else ""
                asig_str = f" ({t.asignatura.nombre})" if t.asignatura else ""
                opciones_filtro_tema[t.id] = f"{num_str}{t.titulo}{asig_str}"

            tema_filtro = col_f1.selectbox(
                "Filtrar por Tema",
                options=list(opciones_filtro_tema.keys()),
                format_func=lambda x: opciones_filtro_tema.get(x, "")
            )

            min_score, max_score = col_f2.slider(
                "Rango de Aciertos (%)",
                0.0, 100.0, (0.0, 100.0), step=5.0
            )

            min_time, max_time = col_f3.slider(
                "Rango de Duración (minutos)",
                0, 300, (0, 300), step=5
            )

        # Construir consulta con filtros
        query = db.query(models.HistorialRepasos).join(models.Tema)
        
        if tema_filtro != 0:
            query = query.filter(models.HistorialRepasos.id_tema == tema_filtro)
        
        # Filtros básicos, adaptados para buscar en el rango de aciertos/duración
        repasos = query.order_by(models.HistorialRepasos.fecha_repaso.desc()).all()

        if not repasos:
            st.info("No se encontraron repasos con los filtros seleccionados.")
        else:
            # Resumen estadístico
            total_minutos = sum(int(r.duracion if r.duracion else (r.tiempo_tardado or 0)) for r in repasos)
            notas_validas: list[float] = []
            for r in repasos:
                nota = r.aciertos if r.aciertos is not None else r.puntuacion
                if nota is not None:
                    notas_validas.append(float(nota))

            media_nota = float(sum(notas_validas) / len(notas_validas)) if len(notas_validas) > 0 else 0.0

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Sesiones Registradas", len(repasos))
            col_m2.metric("Media de Aciertos", f"{media_nota:.1f}%")
            col_m3.metric("Tiempo Total Invertido", f"{total_minutos} min ({total_minutos/60:.1f} h)")

            # Tabla de datos
            datos = []
            for r in repasos:
                tema = r.tema
                asig_nombre = tema.asignatura.nombre if tema and tema.asignatura else "N/A"
                val_aciertos = r.aciertos if r.aciertos is not None else r.puntuacion
                val_duracion = r.duracion if r.duracion else r.tiempo_tardado
                
                datos.append({
                    "Fecha": r.fecha_repaso.strftime("%d/%m/%Y"),
                    "Asignatura": asig_nombre,
                    "Tema": tema.titulo if tema else "N/A",
                    "Aciertos (%)": f"{val_aciertos:.1f}%" if val_aciertos is not None else "Sin nota",
                    "Duración (min)": f"{val_duracion} min"
                })

            df = pd.DataFrame(datos)
            st.dataframe(df, use_container_width=True, hide_index=True)
