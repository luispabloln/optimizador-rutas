import streamlit as st
import pandas as pd
import folium
from folium.features import DivIcon
from folium.plugins import Fullscreen
from streamlit_folium import st_folium
from scipy.spatial.distance import cdist
import simplekml
import math
import plotly.express as px

# --- CONFIGURACIÓN DE CARGA AUTOMÁTICA DESDE GITHUB ---
# Se utiliza la URL Raw proporcionada para la carga directa
GITHUB_RAW_URL = "https://raw.githubusercontent.com/luispabloln/optimizador-rutas/refs/heads/main/clientes%20atendidos.csv"

# --- ESTILO LOOKER STUDIO (CSS) ---
st.set_page_config(page_title="Auditoría GPS Pro", layout="wide", page_icon="📊")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e4e8;
        padding: 15px 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    h1, h2, h3 { color: #1c2b39; font-family: 'Segoe UI', sans-serif; }
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e0e4e8;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIONES DE LÓGICA ---

def asignar_canal(nombre):
    nombre = str(nombre).upper()
    mzo_keywords = ['ABDY', 'MARCIA', 'JESUS', 'KEVIN', 'MARIBEL', 'LUIS PABLO']
    if any(keyword in nombre for keyword in mzo_keywords):
        return 'MZO'
    else:
        return 'TDB'

def haversine(lat1, lon1, lat2, lon2):
    try:
        R = 6371
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi, dlambda = math.radians(lat2-lat1), math.radians(lon2-lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))
    except:
        return 0

def calc_total_km(df_temp):
    total = 0
    if len(df_temp) < 2: return 0
    for i in range(len(df_temp)-1):
        total += haversine(df_temp.iloc[i]['latitud'], df_temp.iloc[i]['longitud'], 
                           df_temp.iloc[i+1]['latitud'], df_temp.iloc[i+1]['longitud'])
    return total

def cargar_datos(source):
    try:
        if isinstance(source, str):
            if source.endswith('.csv'):
                df = pd.read_csv(source, sep=None, engine='python', on_bad_lines='skip')
            else:
                df = pd.read_excel(source)
        else:
            if source.name.endswith('.csv'):
                df = pd.read_csv(source, sep=None, engine='python', on_bad_lines='skip')
            else:
                df = pd.read_excel(source)
            
        df.columns = [str(c).replace('\ufeff', '').strip().lower() for c in df.columns]
        df = df.rename(columns={'empleado': 'vendedor', 'lat': 'latitud', 'lon': 'longitud'})
        
        df['latitud'] = pd.to_numeric(df['latitud'], errors='coerce')
        df['longitud'] = pd.to_numeric(df['longitud'], errors='coerce')
        df = df.dropna(subset=['latitud', 'longitud'])
        
        df['canal'] = df['vendedor'].apply(asignar_canal)
        if 'fecha' in df.columns and 'hora' in df.columns:
            df['fecha_hora'] = pd.to_datetime(df['fecha'].astype(str) + ' ' + df['hora'].astype(str), errors='coerce')
        else:
            df['fecha_hora'] = pd.to_datetime(df['fecha'], errors='coerce')
        
        df = df.dropna(subset=['fecha_hora'])
        df['fecha_solo'] = df['fecha_hora'].dt.date
        df['mes'] = df['fecha_hora'].dt.strftime('%Y-%m')
        return df
    except Exception as e:
        st.error(f"Error al cargar datos: {e}")
        return None

def optimizar_ruta_vecino(df_ruta):
    if len(df_ruta) < 2: return df_ruta
    df_p = df_ruta.copy()
    ruta = [df_p.iloc[0]]
    df_p = df_p.iloc[1:]
    while len(df_p) > 0:
        u = ruta[-1]
        dist = cdist([[u['latitud'], u['longitud']]], df_p[['latitud', 'longitud']].values, metric='euclidean')[0]
        idx = dist.argmin()
        ruta.append(df_p.iloc[idx])
        df_p = df_p.drop(df_p.index[idx])
    return pd.DataFrame(ruta).reset_index(drop=True)

# --- INTERFAZ ---

st.title("📍 Dashboard de Auditoría GPS Pro")

df = cargar_datos(GITHUB_RAW_URL)

if df is not None:
    with st.sidebar:
        st.header("⚙️ Configuración Global")
        canal_sel = st.selectbox("Canal de Venta", ["MZO", "TDB"])
        
        meses_disponibles = sorted(df['mes'].unique(), reverse=True)
        mes_sel = st.selectbox("Seleccionar Mes", meses_disponibles)
        
        df_filtrado_mes = df[df['mes'] == mes_sel]
        
        fechas_disponibles = sorted(df_filtrado_mes['fecha_solo'].unique(), reverse=True)
        fecha_sel = st.selectbox("Fecha de Auditoría", fechas_disponibles)
        st.divider()
        velocidad = st.slider("Velocidad (km/h)", 10, 60, 25)

    tab1, tab2 = st.tabs(["👤 Auditoría Individual", "🏢 Análisis de Canal"])

    with tab1:
        vendedores_filtrados = sorted(df_filtrado_mes[df_filtrado_mes['canal'] == canal_sel]['vendedor'].unique())
        vendedor_sel = st.selectbox("Seleccionar Empleado", vendedores_filtrados)
        
        df_vend = df_filtrado_mes[(df_filtrado_mes['vendedor'] == vendedor_sel) & (df_filtrado_mes['fecha_solo'] == fecha_sel)].sort_values('fecha_hora').reset_index(drop=True)
        
        if not df_vend.empty:
            ruta_real = df_vend.copy()
            ruta_real['orden_original'] = range(1, len(ruta_real) + 1)
            ruta_optima = optimizar_ruta_vecino(ruta_real)
            ruta_optima['orden_sugerido'] = range(1, len(ruta_optima) + 1)
            
            km_r, km_o = calc_total_km(ruta_real), calc_total_km(ruta_optima)
            
            c_met1, c_met2, c_met3 = st.columns(3)
            c_met1.metric("Km Recorridos", f"{km_r:.2f} km")
            c_met2.metric("Km Sugeridos", f"{km_o:.2f} km")
            c_met3.metric("Ahorro Potencial", f"{km_r - km_o:.2f} km", f"{((km_r-km_o)/km_r*100 if km_r>0 else 0):.1f}%")

            col_map1, col_map2 = st.columns([4, 1])
            with col_map2:
                st.write("Visualización:")
                ver_orig = st.checkbox("Ver Línea Real", True)
                ver_opt = st.checkbox("Ver Línea Sugerida", True)
                tipo_num = st.radio("Número en círculo:", ["Sugerido", "Original"])

            with col_map1:
                m = folium.Map(location=[ruta_real['latitud'].mean(), ruta_real['longitud'].mean()], zoom_start=14, tiles="cartodbpositron")
                Fullscreen(position='topright').add_to(m)
                
                if ver_orig:
                    folium.PolyLine(list(zip(ruta_real['latitud'], ruta_real['longitud'])), color="#e74c3c", weight=3, opacity=0.4).add_to(m)
                if ver_opt:
                    folium.PolyLine(list(zip(ruta_optima['latitud'], ruta_optima['longitud'])), color="#27ae60", weight=5, opacity=0.7, dash_array='8, 8').add_to(m)
                
                # Bucle para marcadores con cálculo de tiempo transcurrido
                prev_time = None
                for i, row in ruta_optima.iterrows():
                    num = row['orden_sugerido'] if tipo_num == "Sugerido" else row['orden_original']
                    color = "#27ae60" if tipo_num == "Sugerido" else "#e74c3c"
                    icon_v = "✅" if str(row.get('tipo', '')).lower() == 'preventa' else "❌"
                    
                    # Cálculo de tiempo transcurrido
                    if i == 0:
                        tiempo_transcurrido = "Primer punto"
                    else:
                        diff = row['fecha_hora'] - prev_time
                        horas, rem = divmod(diff.total_seconds(), 3600)
                        minutos, segundos = divmod(rem, 60)
                        tiempo_transcurrido = f"{int(horas)}h {int(minutos)}m" if horas > 0 else f"{int(minutos)} min"
                    
                    prev_time = row['fecha_hora']
                    
                    html_icon = f"""<div style="background:{color};color:white;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-weight:bold;border:2px solid white;font-size:11px;box-shadow: 0 2px 4px rgba(0,0,0,0.2);">{num}</div>"""
                    
                    texto_tooltip = f"{icon_v} {row['cliente']} | Hora: {row['fecha_hora'].strftime('%H:%M')} | Transcurrido: {tiempo_transcurrido}"
                    
                    texto_popup = f"""
                    <div style="font-family: sans-serif; min-width: 180px;">
                        <h4 style="margin:0;">{row['cliente']}</h4>
                        <hr style="margin:5px 0;">
                        <b>Estado:</b> {row.get('tipo', 'N/A')}<br>
                        <b>Hora Visita:</b> {row['fecha_hora'].strftime('%H:%M:%S')}<br>
                        <b>Tiempo desde anterior:</b> {tiempo_transcurrido}<br>
                        <b>Orden Real:</b> {row['orden_original']}<br>
                        <b>Orden Sugerido:</b> {row['orden_sugerido']}<br>
                        <b>Monto:</b> {row.get('monto', 0)}
                    </div>
                    """
                    
                    folium.Marker(
                        location=[row['latitud'], row['longitud']], 
                        tooltip=texto_tooltip, 
                        popup=folium.Popup(texto_popup, max_width=300),
                        icon=DivIcon(icon_size=(26,26), icon_anchor=(13,13), html=html_icon)
                    ).add_to(m)
                
                st_folium(m, width="100%", height=550)
            
            kml = simplekml.Kml()
            for _, r in ruta_optima.iterrows():
                kml.newpoint(name=f"#{r['orden_sugerido']} {r['cliente']}", coords=[(r['longitud'], r['latitud'])])
            st.download_button("📥 Descargar KML", kml.kml(), f"Ruta_{vendedor_sel}.kml")
        else:
            st.warning("Sin datos para este vendedor en esta fecha.")

    with tab2:
        st.subheader(f"📊 Desempeño Comparativo: Canal {canal_sel}")
        vendedores_canal = df_filtrado_mes[(df_filtrado_mes['canal'] == canal_sel) & (df_filtrado_mes['fecha_solo'] == fecha_sel)]['vendedor'].unique()
        resumen_data = []

        for v in vendedores_canal:
            d_v = df_filtrado_mes[(df_filtrado_mes['vendedor'] == v) & (df_filtrado_mes['fecha_solo'] == fecha_sel)].sort_values('fecha_hora')
            if len(d_v) > 1:
                km_real = calc_total_km(d_v)
                km_opt = calc_total_km(optimizar_ruta_vecino(d_v))
                
                tipo_col = 'tipo' if 'tipo' in d_v.columns else None
                if tipo_col:
                    efectividad = (len(d_v[d_v[tipo_col].str.lower() == 'preventa']) / len(d_v)) * 100
                else:
                    efectividad = 0
                    
                resumen_data.append({
                    "Vendedor": v,
                    "Km Real": round(km_real, 2),
                    "Desvío (Km)": round(km_real - km_opt, 2),
                    "Efectividad (%)": round(efectividad, 1)
                })
        
        if resumen_data:
            res_df = pd.DataFrame(resumen_data).sort_values("Desvío (Km)", ascending=False)
            fig = px.bar(res_df, x="Vendedor", y="Desvío (Km)", color="Desvío (Km)", color_continuous_scale="Reds")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(res_df.style.background_gradient(subset=['Desvío (Km)'], cmap='YlOrRd'), use_container_width=True)
        else:
            st.info("No hay suficientes datos comparativos para esta fecha.")
