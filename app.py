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
        df['mes'] = df['fecha_hora'].dt.strftime('%B %Y')
        df['semana'] = df['fecha_hora'].dt.isocalendar().week
        return df
    except Exception as e:
        st.error(f"Error al cargar archivo: {e}")
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

st.title("📍 Auditoría GPS & Inteligencia de Ventas")
archivo = st.file_uploader("📂 Cargar archivo de registros", type=["xlsx", "csv"])

if archivo:
    df = cargar_datos(archivo)
    
    if df is not None:
        with st.sidebar:
            st.header("⚙️ Filtros Globales")
            canal_sel = st.selectbox("Canal de Venta", ["MZO", "TDB"])
            fechas_disponibles = sorted(df['fecha_solo'].unique(), reverse=True)
            fecha_sel = st.selectbox("Fecha de Auditoría", fechas_disponibles)
            st.divider()
            velocidad = st.slider("Velocidad Promedio (km/h)", 10, 60, 25)

        tab1, tab2, tab3 = st.tabs(["👤 Auditoría Individual", "🏢 Análisis de Canal", "🏆 Rankings de Eficiencia"])

        # --- TAB 1: AUDITORÍA INDIVIDUAL ---
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
                
                c_m1, c_m2, c_m3 = st.columns(3)
                c_m1.metric("Km Recorridos", f"{km_r:.2f} km")
                c_m2.metric("Km Sugeridos", f"{km_o:.2f} km")
                c_m3.metric("Ahorro del Día", f"{km_r - km_o:.2f} km", f"{((km_r-km_o)/km_r*100 if km_r>0 else 0):.1f}%")

                m = folium.Map(location=[r_real['latitud'].mean(), r_real['longitud'].mean()], zoom_start=14, tiles="cartodbpositron")
                Fullscreen().add_to(m)
                folium.PolyLine(list(zip(r_real['latitud'], r_real['longitud'])), color="#e74c3c", weight=2, opacity=0.4).add_to(m)
                folium.PolyLine(list(zip(r_opt['latitud'], r_opt['longitud'])), color="#27ae60", weight=4, opacity=0.7, dash_array='8, 8').add_to(m)
                
                for _, row in r_opt.iterrows():
                    num = row['orden_sugerido']
                    icon_v = "✅" if str(row['tipo']).lower() == 'preventa' else "❌"
                    html = f"""<div style="background:#27ae60;color:white;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-weight:bold;border:2px solid white;font-size:11px;">{num}</div>"""
                    folium.Marker([row['latitud'], row['longitud']], tooltip=f"{icon_v} {row['cliente']}", icon=DivIcon(icon_size=(26,26), html=html)).add_to(m)
                
                st_folium(m, width="100%", height=500)
            else:
                st.warning("No hay datos para este vendedor en la fecha seleccionada.")

        # --- TAB 2: ANÁLISIS DE CANAL ---
        with tab2:
            st.subheader(f"📊 Consolidado Canal: {canal_sel}")
            
            # Filtro por Zona
            zonas_disponibles = sorted(df['zona'].dropna().unique())
            zonas_sel = st.multiselect("Filtrar por Zona", zonas_disponibles, default=zonas_disponibles[:3] if zonas_disponibles else None)
            
            # --- DATOS DEL DÍA ---
            df_c_dia = df[(df['canal'] == canal_sel) & (df['fecha_solo'] == fecha_sel)]
            if zonas_sel:
                df_c_dia = df_c_dia[df_c_dia['zona'].isin(zonas_sel)]
            
            res_dia = []
            for v in df_c_dia['vendedor'].unique():
                d_v = df_c_dia[df_c_dia['vendedor'] == v].sort_values('fecha_hora')
                if len(d_v) > 1:
                    km_r, km_o = calc_total_km(d_v), calc_total_km(optimizar_ruta_vecino(d_v))
                    res_dia.append({"Vendedor": v, "Desvío (Km)": round(km_r - km_o, 2)})
            
            if res_dia:
                st.markdown("#### 📅 Desvío del Día")
                df_res_dia = pd.DataFrame(res_dia).sort_values("Desvío (Km)", ascending=False)
                fig_dia = px.bar(df_res_dia, x="Vendedor", y="Desvío (Km)", color="Desvío (Km)", color_continuous_scale="Reds", text_auto=True)
                st.plotly_chart(fig_dia, use_container_width=True)

            # --- DATOS ACUMULADOS MENSUALES (PEDIDO DEL USUARIO) ---
            st.markdown("---")
            st.markdown("#### 🗓️ Acumulado Mensual de Desvío (Km)")
            
            mes_actual = df[df['fecha_solo'] == fecha_sel]['mes'].iloc[0]
            df_c_mes = df[(df['canal'] == canal_sel) & (df['mes'] == mes_actual)]
            if zonas_sel:
                df_c_mes = df_c_mes[df_c_mes['zona'].isin(zonas_sel)]
            
            res_mes = []
            for v in df_c_mes['vendedor'].unique():
                v_data = df_c_mes[df_c_mes['vendedor'] == v]
                desvio_total = 0
                for f in v_data['fecha_solo'].unique():
                    dia_data = v_data[v_data['fecha_solo'] == f].sort_values('fecha_hora')
                    if len(dia_data) > 1:
                        desvio_total += (calc_total_km(dia_data) - calc_total_km(optimizar_ruta_vecino(dia_data)))
                res_mes.append({"Vendedor": v, "Desvío Acumulado (Km)": round(desvio_total, 2)})
            
            if res_mes:
                df_res_mes = pd.DataFrame(res_mes).sort_values("Desvío Acumulado (Km)", ascending=False)
                fig_mes = px.bar(df_res_mes, x="Vendedor", y="Desvío Acumulado (Km)", color="Desvío Acumulado (Km)", color_continuous_scale="Oranges", text_auto=True)
                st.plotly_chart(fig_mes, use_container_width=True)
                
                # Métrica de Ventas Totales por Canal
                monto_total = df_c_mes[df_c_mes['tipo'].str.lower() == 'preventa']['monto'].sum()
                st.metric(f"Monto Total Ventas Mes ({canal_sel})", f"${monto_total:,.2f}")

        # --- TAB 3: RANKINGS ---
        with tab3:
            st.subheader("🏆 Ranking de Eficiencia")
            
            col_r1, col_r2 = st.columns(2)
            
            # Ranking Semanal
            semana_actual = df[df['fecha_solo'] == fecha_sel]['semana'].iloc[0]
            df_sem = df[df['semana'] == semana_actual]
            
            rank_sem = []
            for v in df_sem['vendedor'].unique():
                v_sem = df_sem[df_sem['vendedor'] == v]
                desvio_sem = 0
                for f in v_sem['fecha_solo'].unique():
                    d_data = v_sem[v_sem['fecha_solo'] == f].sort_values('fecha_hora')
                    if len(d_data) > 1:
                        desvio_sem += (calc_total_km(d_data) - calc_total_km(optimizar_ruta_vecino(d_data)))
                rank_sem.append({"Vendedor": v, "Desvío Semanal": round(desvio_sem, 2), "Canal": v_sem['canal'].iloc[0]})
            
            df_rank_sem = pd.DataFrame(rank_sem).sort_values("Desvío Semanal")
            with col_r1:
                st.markdown(f"**Top Eficiencia Semana {semana_actual}**")
                st.dataframe(df_rank_sem.style.background_gradient(subset=['Desvío Semanal'], cmap='RdYlGn_r'), use_container_width=True)
            
            # Ranking Mensual de Ventas
            with col_r2:
                st.markdown(f"**Top Ventas {mes_actual}**")
                rank_v = df_c_mes[df_c_mes['tipo'].str.lower() == 'preventa'].groupby('vendedor')['monto'].sum().sort_values(ascending=False).reset_index()
                st.dataframe(rank_v.style.background_gradient(subset=['monto'], cmap='Greens'), use_container_width=True)
