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

# --- ESTILO TIPO LOOKER STUDIO ---
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
    section[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e0e4e8; }
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

def cargar_datos(uploaded_file):
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        df.columns = df.columns.str.strip().str.lower()
        df = df.rename(columns={'empleado': 'vendedor', 'lat': 'latitud', 'lon': 'longitud'})
        
        df['latitud'] = pd.to_numeric(df['latitud'], errors='coerce')
        df['longitud'] = pd.to_numeric(df['longitud'], errors='coerce')
        df = df.dropna(subset=['latitud', 'longitud'])
        
        df['canal'] = df['vendedor'].apply(asignar_canal)
        df['fecha_hora'] = pd.to_datetime(df['fecha'].astype(str) + ' ' + df['hora'].astype(str))
        df['fecha_solo'] = df['fecha_hora'].dt.date
        df['semana'] = df['fecha_hora'].dt.isocalendar().week
        df['mes'] = df['fecha_hora'].dt.month_name()
        
        return df
    except Exception as e:
        st.error(f"Error al cargar: {e}")
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

st.title("📍 Dashboard de Auditoría y Ventas GPS Pro")
archivo = st.file_uploader("📂 Cargar archivo de registros", type=["xlsx", "csv"])

if archivo:
    df = cargar_datos(archivo)
    
    if df is not None:
        with st.sidebar:
            st.header("⚙️ Configuración")
            canal_sel = st.selectbox("Canal", ["MZO", "TDB"])
            fechas_disp = sorted(df['fecha_solo'].unique(), reverse=True)
            fecha_sel = st.selectbox("Fecha Auditoría", fechas_disp)
            velocidad = st.slider("Velocidad (km/h)", 10, 60, 25)

        tab1, tab2, tab3 = st.tabs(["👤 Auditoría Individual", "🏢 Análisis de Canal", "🏆 Rankings Históricos"])

        # --- TAB 1: AUDITORÍA INDIVIDUAL ---
        with tab1:
            vend_list = sorted(df[df['canal'] == canal_sel]['vendedor'].unique())
            v_sel = st.selectbox("Empleado", vend_list)
            df_v = df[(df['vendedor'] == v_sel) & (df['fecha_solo'] == fecha_sel)].sort_values('fecha_hora').reset_index(drop=True)
            
            if not df_v.empty:
                r_real = df_v.copy()
                r_real['orden_original'] = range(1, len(r_real) + 1)
                r_opt = optimizar_ruta_vecino(r_real)
                r_opt['orden_sugerido'] = range(1, len(r_opt) + 1)
                
                k1, k2, k3 = st.columns(3)
                km_real, km_opt = calc_total_km(r_real), calc_total_km(r_opt)
                k1.metric("Km Recorridos", f"{km_real:.2f} km")
                k2.metric("Km Sugeridos", f"{km_opt:.2f} km")
                k3.metric("Ahorro", f"{km_real - km_opt:.2f} km", f"{((km_real-km_opt)/km_real*100 if km_real>0 else 0):.1f}%")

                m = folium.Map(location=[r_real['latitud'].mean(), r_real['longitud'].mean()], zoom_start=14, tiles="cartodbpositron")
                Fullscreen().add_to(m)
                folium.PolyLine(list(zip(r_real['latitud'], r_real['longitud'])), color="#e74c3c", weight=2, opacity=0.4).add_to(m)
                folium.PolyLine(list(zip(r_opt['latitud'], r_opt['longitud'])), color="#27ae60", weight=4, opacity=0.7, dash_array='8, 8').add_to(m)
                
                for _, row in r_opt.iterrows():
                    num = row['orden_sugerido']
                    icon_v = "✅" if str(row['tipo']).lower() == 'preventa' else "❌"
                    html = f"""<div style="background:#27ae60;color:white;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-weight:bold;border:2px solid white;font-size:10px;">{num}</div>"""
                    folium.Marker([row['latitud'], row['longitud']], tooltip=f"{icon_v} {row['cliente']}", icon=DivIcon(icon_size=(24,24), html=html)).add_to(m)
                
                st_folium(m, width="100%", height=500)
            else:
                st.warning("Sin datos para este día.")

        # --- TAB 2: ANÁLISIS DE CANAL ---
        with tab2:
            st.subheader(f"📊 Consolidado Canal: {canal_sel}")
            
            # 1. Ventas por Canal (NUEVO)
            ventas_canal = df[df['tipo'].str.lower() == 'preventa'].groupby('canal')['monto'].sum().reset_index()
            fig_v = px.pie(ventas_canal, values='monto', names='canal', title="Participación de Ventas por Canal ($)", color_discrete_sequence=['#2ecc71', '#3498db'])
            
            c_v1, c_v2 = st.columns([1, 2])
            with c_v1:
                st.plotly_chart(fig_v, use_container_width=True)
            with c_v2:
                # 2. Filtro por ZONA (NUEVO)
                zonas_disp = sorted(df['zona'].dropna().unique())
                zona_sel = st.multiselect("Filtrar por Zona (Análisis de Ineficiencia)", zonas_disp, default=zonas_disp[:5] if zonas_disp else None)
                
                # Análisis de Ineficiencia por Zona
                df_c_z = df[(df['canal'] == canal_sel) & (df['fecha_solo'] == fecha_sel)]
                if zona_sel:
                    df_c_z = df_c_z[df_c_z['zona'].isin(zona_sel)]
                
                res_z = []
                for v in df_c_z['vendedor'].unique():
                    d_v = df_c_z[df_c_z['vendedor'] == v].sort_values('fecha_hora')
                    if len(d_v) > 1:
                        km_r, km_o = calc_total_km(d_v), calc_total_km(optimizar_ruta_vecino(d_v))
                        res_z.append({"Vendedor": v, "Desvío (Km)": round(km_r - km_o, 2), "Visitas": len(d_v)})
                
                if res_z:
                    df_res_z = pd.DataFrame(res_z).sort_values("Desvío (Km)", ascending=False)
                    fig_z = px.bar(df_res_z, x="Vendedor", y="Desvío (Km)", title="Desvío por Vendedor en Zonas Seleccionadas", color="Desvío (Km)", color_continuous_scale="Reds")
                    st.plotly_chart(fig_z, use_container_width=True)

        # --- TAB 3: RANKINGS HISTÓRICOS (NUEVO) ---
        with tab3:
            st.subheader("🏆 Cuadro de Honor: Eficiencia y Ruteo")
            r_c1, r_c2 = st.columns(2)
            
            def obtener_ranking(periodo_col, periodo_val):
                data = df[df[periodo_col] == periodo_val]
                rank = []
                for v in data['vendedor'].unique():
                    v_data = data[data['vendedor'] == v]
                    # Calculamos eficiencia promedio diaria para el periodo
                    desvios = []
                    for f in v_data['fecha_solo'].unique():
                        dia = v_data[v_data['fecha_solo'] == f].sort_values('fecha_hora')
                        if len(dia) > 1:
                            desvios.append(calc_total_km(dia) - calc_total_km(optimizar_ruta_vecino(dia)))
                    if desvios:
                        rank.append({"Vendedor": v, "Ahorro Pendiente Promedio": round(sum(desvios)/len(desvios), 2), "Ventas Totales": v_data[v_data['tipo'].str.lower()=='preventa']['monto'].sum()})
                return pd.DataFrame(rank).sort_values("Ahorro Pendiente Promedio")

            with r_c1:
                st.markdown("📅 **Top Eficiencia Semanal**")
                semana_actual = df['semana'].max()
                df_sem = obtener_ranking('semana', semana_actual)
                if not df_sem.empty:
                    st.success(f"🥇 El más eficiente: **{df_sem.iloc[0]['Vendedor']}**")
                    st.dataframe(df_sem.style.background_gradient(subset=['Ahorro Pendiente Promedio'], cmap='RdYlGn_r'))

            with r_c2:
                st.markdown("🗓️ **Top Eficiencia Mensual**")
                mes_actual = df['mes'].iloc[0] # Toma el primer mes del archivo
                df_mes = obtener_ranking('mes', mes_actual)
                if not df_mes.empty:
                    st.info(f"🏆 Líder del Mes: **{df_mes.iloc[0]['Vendedor']}**")
                    st.dataframe(df_mes.style.background_gradient(subset=['Ventas Totales'], cmap='Greens'))
