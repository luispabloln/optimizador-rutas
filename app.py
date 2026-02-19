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
    return 'MZO' if any(keyword in nombre for keyword in mzo_keywords) else 'TDB'

def haversine(lat1, lon1, lat2, lon2):
    try:
        R = 6371
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi, dlambda = math.radians(lat2-lat1), math.radians(lon2-lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))
    except: return 0

def calc_total_km(df_temp):
    total = 0
    if len(df_temp) < 2: return 0
    for i in range(len(df_temp)-1):
        total += haversine(df_temp.iloc[i]['latitud'], df_temp.iloc[i]['longitud'], 
                           df_temp.iloc[i+1]['latitud'], df_temp.iloc[i+1]['longitud'])
    return total

def cargar_datos(source):
    try:
        # Mejora: sep=None y engine='python' detectan automáticamente si es coma o punto y coma
        # on_bad_lines='skip' evita el error de tokenización
        if isinstance(source, str):
            df = pd.read_csv(source, sep=None, engine='python', on_bad_lines='skip') if source.endswith('.csv') else pd.read_excel(source)
        else:
            df = pd.read_csv(source, sep=None, engine='python', on_bad_lines='skip') if source.name.endswith('.csv') else pd.read_excel(source)
            
        df.columns = df.columns.str.strip().str.lower()
        df = df.rename(columns={'empleado': 'vendedor', 'lat': 'latitud', 'lon': 'longitud'})
        
        df['latitud'] = pd.to_numeric(df['latitud'], errors='coerce')
        df['longitud'] = pd.to_numeric(df['longitud'], errors='coerce')
        df = df.dropna(subset=['latitud', 'longitud'])
        
        df['canal'] = df['vendedor'].apply(asignar_canal)
        df['fecha_hora'] = pd.to_datetime(df['fecha'].astype(str) + ' ' + df['hora'].astype(str), errors='coerce')
        df = df.dropna(subset=['fecha_hora'])
        df['fecha_solo'] = df['fecha_hora'].dt.date
        df['mes'] = df['fecha_hora'].dt.strftime('%B %Y')
        df['semana'] = df['fecha_hora'].dt.isocalendar().week
        return df
    except Exception as e:
        st.error(f"Error crítico al cargar datos: {e}")
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
        fechas_disponibles = sorted(df['fecha_solo'].unique(), reverse=True)
        fecha_sel = st.selectbox("Fecha de Auditoría", fechas_disponibles)
        st.divider()
        velocidad = st.slider("Velocidad (km/h)", 10, 60, 25)

    tab1, tab2, tab3 = st.tabs(["👤 Auditoría Individual", "🏢 Análisis de Canal", "🏆 Rankings de Eficiencia"])

    with tab1:
        v_filtrados = sorted(df[df['canal'] == canal_sel]['vendedor'].unique())
        vendedor_sel = st.selectbox("Seleccionar Empleado", v_filtrados)
        df_v = df[(df['vendedor'] == vendedor_sel) & (df['fecha_solo'] == fecha_sel)].sort_values('fecha_hora').reset_index(drop=True)
        
        if not df_v.empty:
            r_real = df_v.copy()
            r_real['orden_original'] = range(1, len(r_real) + 1)
            r_opt = optimizar_ruta_vecino(r_real)
            r_opt['orden_sugerido'] = range(1, len(r_opt) + 1)
            
            km_r, km_o = calc_total_km(r_real), calc_total_km(r_opt)
            c1, c2, c3 = st.columns(3)
            c1.metric("Km Recorridos", f"{km_r:.2f} km")
            c2.metric("Km Sugeridos", f"{km_o:.2f} km")
            c3.metric("Ahorro Potencial", f"{km_r - km_o:.2f} km", f"{((km_r-km_o)/km_r*100 if km_r>0 else 0):.1f}%")

            col_m1, col_m2 = st.columns([4, 1])
            with col_m2:
                st.write("Capa:")
                v_orig = st.checkbox("Ruta Real", True)
                v_opt = st.checkbox("Ruta Sugerida", True)
                t_num = st.radio("Número:", ["Sugerido", "Original"])

            with col_m1:
                m = folium.Map(location=[r_real['latitud'].mean(), r_real['longitud'].mean()], zoom_start=14, tiles="cartodbpositron")
                Fullscreen().add_to(m)
                if v_orig: folium.PolyLine(list(zip(r_real['latitud'], r_real['longitud'])), color="#e74c3c", weight=2, opacity=0.4).add_to(m)
                if v_opt: folium.PolyLine(list(zip(r_opt['latitud'], r_opt['longitud'])), color="#27ae60", weight=4, opacity=0.7, dash_array='8, 8').add_to(m)
                
                for _, row in r_opt.iterrows():
                    num = row['orden_sugerido'] if t_num == "Sugerido" else row['orden_original']
                    color = "#27ae60" if t_num == "Sugerido" else "#e74c3c"
                    icon_v = "✅" if str(row['tipo']).lower() == 'preventa' else "❌"
                    html = f"""<div style="background:{color};color:white;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-weight:bold;border:2px solid white;font-size:11px;">{num}</div>"""
                    folium.Marker([row['latitud'], row['longitud']], tooltip=f"{icon_v} {row['cliente']}", icon=DivIcon(icon_size=(26,26), html=html)).add_to(m)
                st_folium(m, width="100%", height=500)
        else:
            st.warning("Sin datos para este día.")

    with tab2:
        st.subheader(f"📊 Desempeño Canal: {canal_sel}")
        zonas_disp = sorted(df['zona'].dropna().unique())
        z_sel = st.multiselect("Filtrar por Zona", zonas_disp, default=zonas_disp[:3] if zonas_disp else None)
        
        df_c = df[(df['canal'] == canal_sel) & (df['fecha_solo'] == fecha_sel)]
        if z_sel: df_c = df_c[df_c['zona'].isin(z_sel)]
        
        res_dia = []
        for v in df_c['vendedor'].unique():
            d_v = df_c[df_c['vendedor'] == v].sort_values('fecha_hora')
            if len(d_v) > 1:
                res_dia.append({"Vendedor": v, "Desvío (Km)": round(calc_total_km(d_v) - calc_total_km(optimizar_ruta_vecino(d_v)), 2)})
        
        if res_dia:
            st.plotly_chart(px.bar(pd.DataFrame(res_dia).sort_values("Desvío (Km)", ascending=False), x="Vendedor", y="Desvío (Km)", color="Desvío (Km)", color_continuous_scale="Reds", title="Desvío Diario"), use_container_width=True)

        # Acumulado Mensual
        st.markdown("---")
        st.markdown("#### 🗓️ Desvío Acumulado Mensual")
        mes_sel = df[df['fecha_solo'] == fecha_sel]['mes'].iloc[0]
        df_m = df[(df['canal'] == canal_sel) & (df['mes'] == mes_sel)]
        if z_sel: df_m = df_m[df_m['zona'].isin(z_sel)]
        
        res_m = []
        for v in df_m['vendedor'].unique():
            v_data = df_m[df_m['vendedor'] == v]
            d_total = sum((calc_total_km(v_data[v_data['fecha_solo']==f]) - calc_total_km(optimizar_ruta_vecino(v_data[v_data['fecha_solo']==f]))) for f in v_data['fecha_solo'].unique() if len(v_data[v_data['fecha_solo']==f]) > 1)
            res_m.append({"Vendedor": v, "Desvío Total (Km)": round(d_total, 2)})
        
        if res_m:
            st.plotly_chart(px.bar(pd.DataFrame(res_m).sort_values("Desvío Total (Km)", ascending=False), x="Vendedor", y="Desvío Total (Km)", color="Desvío Total (Km)", color_continuous_scale="Oranges", title=f"Acumulado {mes_sel}"), use_container_width=True)

    with tab3:
        st.subheader("🏆 Rankings")
        sem_sel = df[df['fecha_solo'] == fecha_sel]['semana'].iloc[0]
        rank_s = []
        for v in df[df['semana'] == sem_sel]['vendedor'].unique():
            v_s = df[(df['vendedor'] == v) & (df['semana'] == sem_sel)]
            d_s = sum((calc_total_km(v_s[v_s['fecha_solo']==f]) - calc_total_km(optimizar_ruta_vecino(v_s[v_s['fecha_solo']==f]))) for f in v_s['fecha_solo'].unique() if len(v_s[v_s['fecha_solo']==f]) > 1)
            rank_s.append({"Vendedor": v, "Desvío Semanal": round(d_s, 2)})
        
        c_r1, c_r2 = st.columns(2)
        with c_r1:
            st.write(f"**Top Eficiencia Semana {sem_sel}**")
            st.dataframe(pd.DataFrame(rank_s).sort_values("Desvío Semanal").style.background_gradient(subset=['Desvío Semanal'], cmap='RdYlGn_r'), use_container_width=True)
        with c_r2:
            st.write(f"**Top Ventas {mes_sel}**")
            st.dataframe(df[df['mes'] == mes_sel][df['tipo'].str.lower() == 'preventa'].groupby('vendedor')['monto'].sum().sort_values(ascending=False).reset_index().style.background_gradient(subset=['monto'], cmap='Greens'), use_container_width=True)
