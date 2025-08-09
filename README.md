
# Calculadora EPH – Todos los trimestres (2017–2024)

App de Streamlit que:
- acepta hogares e individuos de cualquier trimestre,
- mapea códigos a etiquetas nominales (sexo, nivel educativo, condición de actividad),
- detecta año/trimestre automáticamente,
- genera un informe Word con conclusiones robustas,
- incorpora TIC si las columnas existen.

## Uso local
```bash
pip install -r requirements.txt
streamlit run app_eph_trimestres.py
```
Subí las bases y descargá el `.docx`.

## Despliegue en Streamlit Cloud
- Repo: `usuario/Calculadora-EPH-Otros-trimestres`
- Branch: `main`
- Main file path: `app_eph_trimestres.py`
- Activá auto-deploy on push.
