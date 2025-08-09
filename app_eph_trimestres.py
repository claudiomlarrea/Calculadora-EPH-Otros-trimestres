# -*- coding: utf-8 -*-
"""
Calculadora EPH (2017–2024) para TODOS los trimestres (1º a 4º)
----------------------------------------------------------------
- Sube bases de Hogares e Individuos de la EPH (cualquier trimestre)
- Opcional: sube el Instructivo PDF del trimestre
- Detecta automáticamente año y trimestre desde las columnas (p.ej., ANO4/ANO/ANO2 y TRIMESTRE/TRIM)
- Evita errores de KeyError: usa búsqueda segura de columnas y salta análisis no disponibles
- Si encuentra variables TIC típicas del 4º trimestre (p.ej., TIP_III_04, TIP_III_06), incluye el análisis TIC; si no, lo omite sin romper
- Genera un informe Word (.docx) sin gráficos, con cifras y comentarios narrativos

Requisitos:
    pip install streamlit pandas numpy python-docx

Ejecución local:
    streamlit run app_eph_trimestres.py
"""

import io
import os
import re
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

# =============================
# Utilidades robustas
# =============================

@st.cache_data(show_spinner=False)
def _read_table(uploaded_file: st.runtime.uploaded_file_manager.UploadedFile) -> pd.DataFrame:
    """Lee CSV, TXT (delimitado por ; o ,) o Excel de forma robusta.
    No falla si hay encoding latino.
    """
    name = uploaded_file.name.lower()
    data = uploaded_file.read()

    # Intentar varios encodings comunes
    encodings = ["utf-8", "latin-1", "cp1252"]

    # Excel
    if name.endswith((".xlsx", ".xls")):
        uploaded_file.seek(0)
        return pd.read_excel(uploaded_file)

    # CSV/TXT
    sep_candidates = [",", ";", "\t", "|"]
    for enc in encodings:
        try:
            text = data.decode(enc)
            # Heurística de separador
            first_line = text.splitlines()[0] if text else ""
            sep = ","
            counts = {s: first_line.count(s) for s in sep_candidates}
            sep = max(counts, key=counts.get) if counts else ","
            df = pd.read_csv(io.StringIO(text), sep=sep)
            return df
        except Exception:
            continue

    # Último intento: binario con pandas
    uploaded_file.seek(0)
    try:
        return pd.read_csv(uploaded_file)
    except Exception:
        uploaded_file.seek(0)
        return pd.read_table(uploaded_file, engine="python", sep=None)


def get_first_col(df: pd.DataFrame, candidates):
    """Devuelve el primer nombre de columna existente o None."""
    for c in candidates:
        if c in df.columns:
            return c
        # tolerar mayúsc/minúsc y tildes raras
        for col in df.columns:
            if col.lower() == c.lower():
                return col
    return None


def detect_year_quarter(df: pd.DataFrame, fallback_name: str = ""):
    """Detecta año y trimestre desde columnas o, si no, desde el nombre de archivo.
    Retorna (anio:int|None, trimestre:int|None)
    """
    year_col = get_first_col(df, ["ANO4", "ANO", "AÑO", "YEAR", "ANIO", "ANIO4"])  # EPH usa ANO4
    q_col = get_first_col(df, ["TRIMESTRE", "TRIM", "TRIMES", "QUARTER"])  # EPH usa TRIMESTRE

    anio = None
    tri = None

    if year_col is not None:
        try:
            # tomar el valor más frecuente (modo) por si hay varias filas
            anio = int(pd.to_numeric(df[year_col], errors="coerce").mode().iloc[0])
        except Exception:
            pass

    if q_col is not None:
        try:
            tri = int(pd.to_numeric(df[q_col], errors="coerce").mode().iloc[0])
        except Exception:
            pass

    # fallback: extraer del nombre de archivo (p.ej., "eph_ind_2017_1t.xlsx")
    if anio is None or tri is None:
        m_year = re.search(r"(20\d{2})", fallback_name)
        if m_year and anio is None:
            anio = int(m_year.group(1))
        m_q = re.search(r"(?:^|[^\d])(1|2|3|4)\s*(?:t|tri|trim|trimestre)\b", fallback_name, re.I)
        if m_q and tri is None:
            tri = int(m_q.group(1))

    return anio, tri


# =============================
# Detección de variables clave
# =============================

class Cols:
    # Identificadores del hogar y persona (comunes EPH)
    ID_HOGAR = [["CODUSU"], ["NRO_HOGAR", "HOGAR"], ["COMPONENTE", "NRO_COMPO"]]

    # Individuos
    SEXO = ["CH04", "SEXO"]  # 1 varón, 2 mujer (EPH clásico)
    EDAD = ["CH06", "EDAD"]

    # Educación (variantes frecuentes; se usará lo que haya)
    NIVEL_ED = [
        "NIVEL_ED", "NIVEL_EDUC", "NIVEL_EDUCATIVO", "EDUC_NIVEL",
    ]

    # Ocupación / estado laboral básicos
    COND_ACT = ["CAT_OCUP", "ESTADO", "COND_ACT", "CONDICION_ACT"]

    # TIC (4º trimestre)
    TIC_PC = ["TIP_III_04", "PC_USO", "USO_PC"]  # uso de computadora (candidatos)
    TIC_INTERNET = ["TIP_III_06", "INTERNET_USO", "USO_INTERNET"]


def pick(df, options):
    return get_first_col(df, options)


def safe_value_counts(series: pd.Series):
    if series is None:
        return None
    s = pd.Series(series)
    return s.value_counts(dropna=False).sort_index()


# =============================
# Análisis
# =============================
def analyze_individuals(df_ind: pd.DataFrame):
    results = {}
    n = len(df_ind)
    results["N_individuos"] = int(n)

    sexo_col = pick(df_ind, Cols.SEXO)
    edad_col = pick(df_ind, Cols.EDAD)
    nivel_col = pick(df_ind, Cols.NIVEL_ED)
    cond_col = pick(df_ind, Cols.COND_ACT)

    # Sexo
    if sexo_col:
        mapa_sexo = {1: "Varón", 2: "Mujer", 3: "Otro"}
        v = pd.to_numeric(df_ind[sexo_col], errors="coerce")
        vc = v.map(mapa_sexo).value_counts(dropna=False)
        results["sexo_counts"] = vc.to_dict()
    else:
        results["sexo_counts"] = None

    # Edad
    if edad_col:
        v = pd.to_numeric(df_ind[edad_col], errors="coerce")
        results["edad_media"] = float(np.nanmean(v)) if v.notna().any() else None
        results["edad_p50"] = float(np.nanmedian(v)) if v.notna().any() else None
        # Tramos
        bins = [0, 5, 12, 18, 30, 45, 60, 75, 120]
        labels = ["0-4", "5-12", "13-18", "19-30", "31-45", "46-60", "61-75", "75+"]
        cat = pd.cut(v, bins=bins, labels=labels, right=True, include_lowest=True)
        results["edad_tramos"] = cat.value_counts(dropna=False).sort_index().to_dict()
    else:
        results["edad_media"] = None
        results["edad_p50"] = None
        results["edad_tramos"] = None

    # Nivel educativo (si disponible)
    if nivel_col:
        vc = safe_value_counts(df_ind[nivel_col])
        results["nivel_educativo_counts"] = None if vc is None else vc.to_dict()
    else:
        results["nivel_educativo_counts"] = None

    # Condición de actividad
    if cond_col:
        vc = safe_value_counts(df_ind[cond_col])
        results["actividad_counts"] = None if vc is None else vc.to_dict()
    else:
        results["actividad_counts"] = None

    # TIC (solo si existen columnas típicas del 4º trimestre)
    pc_col = pick(df_ind, Cols.TIC_PC)
    int_col = pick(df_ind, Cols.TIC_INTERNET)
    if pc_col or int_col:
        tic = {}
        if pc_col:
            tic["uso_pc_counts"] = safe_value_counts(df_ind[pc_col]).to_dict()
        if int_col:
            tic["uso_internet_counts"] = safe_value_counts(df_ind[int_col]).to_dict()
        results["tic"] = tic
    else:
        results["tic"] = None

    return results


def analyze_households(df_hog: pd.DataFrame):
    results = {}
    results["N_hogares"] = int(len(df_hog))

    # Ingresos totales del hogar (si existiera alguna variante)
    ing_candidates = [
        "ITF", "INGTOT", "INGRESO_TOTAL", "ING_HOGAR", "P47T", "INGTRIM"
    ]
    inc_col = pick(df_hog, ing_candidates)
    if inc_col:
        v = pd.to_numeric(df_hog[inc_col], errors="coerce")
        results["ingreso_hogar_media"] = float(np.nanmean(v)) if v.notna().any() else None
        results["ingreso_hogar_p50"] = float(np.nanmedian(v)) if v.notna().any() else None
    else:
        results["ingreso_hogar_media"] = None
        results["ingreso_hogar_p50"] = None

    return results


# =============================
# Informe Word
# =============================
def add_heading(doc: Document, text: str, level: int = 1):
    p = doc.add_heading(text, level=level)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT


def add_paragraph(doc: Document, text: str):
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(6)


def fmt_num(x, nd=0):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "s/d"
    if isinstance(x, float):
        return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(x, (int, np.integer)):
        return f"{x:,}".replace(",", ".")
    return str(x)


def dict_to_lines(d: dict, label_map: dict | None = None):
    lines = []
    for k, v in (d or {}).items():
        label = label_map.get(k, k) if label_map else k
        lines.append(f"• {label}: {fmt_num(v)}")
    return lines


def build_report(hog_res, ind_res, meta, instructivo_name: str | None):
    doc = Document()

    # Portada
    title = doc.add_paragraph()
    run = title.add_run("Universidad Católica de Cuyo\nSecretaría de Investigación\nInforme EPH por Trimestre")
    run.bold = True
    font = run.font
    font.size = Pt(16)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    add_paragraph(doc, "")
    add_paragraph(doc, f"Fecha de generación: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    # Metadatos
    add_heading(doc, "1. Metadatos del procesamiento", level=1)
    add_paragraph(doc, f"Año detectado: {meta.get('anio', 's/d')} | Trimestre detectado: {meta.get('trimestre', 's/d')}")
    add_paragraph(doc, f"Archivos cargados: Hogares = {meta.get('hog_file', 's/d')} | Individuos = {meta.get('ind_file', 's/d')}")
    if instructivo_name:
        add_paragraph(doc, f"Instructivo cargado: {instructivo_name}")
    else:
        add_paragraph(doc, "Instructivo cargado: s/d")

    # Hogares
    add_heading(doc, "2. Resultados de Hogares", level=1)
    add_paragraph(doc, f"Cantidad de hogares: {fmt_num(hog_res.get('N_hogares'))}")
    add_paragraph(doc, f"Ingreso total del hogar (media): {fmt_num(hog_res.get('ingreso_hogar_media'), 2)}")
    add_paragraph(doc, f"Ingreso total del hogar (mediana): {fmt_num(hog_res.get('ingreso_hogar_p50'), 2)}")

    # Individuos
    add_heading(doc, "3. Resultados de Individuos", level=1)
    add_paragraph(doc, f"Cantidad de individuos: {fmt_num(ind_res.get('N_individuos'))}")

    # Sexo
    if ind_res.get("sexo_counts"):
        add_heading(doc, "3.1 Distribución por sexo", level=2)
        for line in dict_to_lines(ind_res["sexo_counts"]):
            add_paragraph(doc, line)
    else:
        add_paragraph(doc, "(No se encontró una columna de sexo. Se omitió esta sección.)")

    # Edad
    if ind_res.get("edad_media") is not None:
        add_heading(doc, "3.2 Estadísticas de edad", level=2)
        add_paragraph(doc, f"Edad media: {fmt_num(ind_res.get('edad_media'), 1)} | Mediana: {fmt_num(ind_res.get('edad_p50'), 1)}")
        if ind_res.get("edad_tramos"):
            add_paragraph(doc, "Distribución por tramos:")
            for line in dict_to_lines(ind_res["edad_tramos"]):
                add_paragraph(doc, line)
    else:
        add_paragraph(doc, "(No se encontró una columna de edad. Se omitió esta sección.)")

    # Educación
    if ind_res.get("nivel_educativo_counts"):
        add_heading(doc, "3.3 Nivel educativo (conteos)", level=2)
        for line in dict_to_lines(ind_res["nivel_educativo_counts"]):
            add_paragraph(doc, line)

    # Actividad
    if ind_res.get("actividad_counts"):
        add_heading(doc, "3.4 Condición de actividad (conteos)", level=2)
        for line in dict_to_lines(ind_res["actividad_counts"]):
            add_paragraph(doc, line)

    # TIC
    if ind_res.get("tic"):
        add_heading(doc, "3.5 Acceso y uso de TIC (solo si hay columnas TIC en la base)", level=2)
        tic = ind_res["tic"]
        if tic.get("uso_pc_counts"):
            add_paragraph(doc, "Uso de computadora:")
            for line in dict_to_lines(tic["uso_pc_counts"]):
                add_paragraph(doc, line)
        if tic.get("uso_internet_counts"):
            add_paragraph(doc, "Uso de internet:")
            for line in dict_to_lines(tic["uso_internet_counts"]):
                add_paragraph(doc, line)
    else:
        add_paragraph(doc, "(No se detectaron variables TIC en esta base. Esta sección se omitió automáticamente.)")

    # Narrativa final
    add_heading(doc, "4. Comentarios e interpretación", level=1)
    narrativa = (
        "Este informe fue generado automáticamente a partir de las bases de la Encuesta Permanente de Hogares "
        "(EPH) del INDEC. El procesamiento se adaptó dinámicamente a las variables disponibles en la base del "
        "trimestre seleccionado. Si el cuestionario incluyó módulos de TIC (típicamente en 4º trimestre), los resultados "
        "aparecen en la sección 3.5; en caso contrario, se omiten sin interrumpir la generación del informe."
    )
    add_paragraph(doc, narrativa)

    return doc


# =============================
# UI Streamlit
# =============================

st.set_page_config(page_title="Calculadora EPH – Todos los trimestres", layout="wide")

st.markdown(
    """
    <div style="background:#0a3d62;color:white;padding:14px;border-radius:12px;margin-bottom:14px;">
      <div style="font-weight:700;font-size:20px;">Universidad Católica de Cuyo</div>
      <div style="font-weight:600;font-size:16px;">Secretaría de Investigación</div>
      <div style="font-size:14px;opacity:.9;">Calculadora EPH 2017–2024 · Informe Word automático · Trimestres 1º a 4º</div>
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2 = st.columns(2)
with col1:
    hog_file = st.file_uploader("Subí la base de HOGARES (CSV/TXT/Excel)", type=["csv", "txt", "xlsx", "xls"]) 
with col2:
    ind_file = st.file_uploader("Subí la base de INDIVIDUOS (CSV/TXT/Excel)", type=["csv", "txt", "xlsx", "xls"]) 

inst_file = st.file_uploader("(Opcional) Subí el Instructivo PDF del trimestre", type=["pdf"]) 

st.info("Consejo: podés subir cualquier trimestre. Si no hay variables TIC, la app lo detecta y omite esa sección sin romperse.")

if hog_file and ind_file:
    with st.spinner("Leyendo archivos…"):
        df_hog = _read_table(hog_file)
        df_ind = _read_table(ind_file)

    # Detectar año/trimestre por columnas o nombre de archivo
    anio_h, tri_h = detect_year_quarter(df_hog, hog_file.name.lower())
    anio_i, tri_i = detect_year_quarter(df_ind, ind_file.name.lower())

    # Resolver meta finales (preferir coincidencias; sino, elegir el que exista)
    anio = anio_h if anio_h is not None else anio_i
    if anio is None:
        anio = anio_i
    tri = tri_h if tri_h is not None else tri_i

    st.success(f"Detectado: Año = {anio if anio else 's/d'} · Trimestre = {tri if tri else 's/d'}")

    # Mostrar vista previa
    with st.expander("Ver primeras filas – Hogares"):
        st.dataframe(df_hog.head(10))
    with st.expander("Ver primeras filas – Individuos"):
        st.dataframe(df_ind.head(10))

    # Ejecutar análisis
    hog_res = analyze_households(df_hog)
    ind_res = analyze_individuals(df_ind)

    st.subheader("Resumen (preview)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Hogares", f"{hog_res.get('N_hogares', 0):,}".replace(",", "."))
    c2.metric("Individuos", f"{ind_res.get('N_individuos', 0):,}".replace(",", "."))
    c3.metric("Edad media", fmt_num(ind_res.get("edad_media"), 1))

    # Botón para generar Word
    if st.button("Generar informe Word"):
        meta = {
            "anio": anio,
            "trimestre": tri,
            "hog_file": hog_file.name,
            "ind_file": ind_file.name,
        }
        doc = build_report(hog_res, ind_res, meta, inst_file.name if inst_file else None)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)

        default_name = f"Informe_EPH_{anio or 'anio'}_T{tri or 'X'}.docx"
        st.download_button(
            label="Descargar Informe .docx",
            data=buf,
            file_name=default_name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

else:
    st.warning("Subí las dos bases (Hogares e Individuos) para continuar.")
