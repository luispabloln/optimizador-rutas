import streamlit as st
import pandas as pd
import folium
from folium.features import DivIcon
from folium.plugins import Fullscreen  # <--- Nuevo import para pantalla completa
from streamlit_folium import st_folium
from scipy.spatial.distance import cdist
import simplekml
import math

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
    .stButton>button {
        border-radius: 20px;
        border: 1px solid #007bff;
        color: #007bff;
    }
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e0e4e8;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIONES DE LÓGICA ---

def asignar_canal(nombre):
    nombre = str(nombre).upper()
    # Luis Pablo agregado a MZO según tu requerimiento
    mzo_keywords = ['ABDY', 'MARCIA', 'JESUS', 'KEVIN', 'MARIBEL', 'LUIS PABLO']
    return 'MZO' if any(keyword in nombre for keyword in mzo_keywords) else 'TDB'

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

def cargar_datos(uploaded_file):
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        df.columns = df.columns.str.strip().str.lower()
        df = df.rename(columns={'empleado': 'vendedor', 'lat': 'latitud', 'lon': 'longitud'})
        df['canal'] = df['vendedor'].apply(asignar_canal)
        if 'fecha' in df.columns and 'hora' in df.columns:
            df['fecha_hora'] = pd.to_datetime(df['fecha'].astype(str) + ' ' + df['hora'].astype(str))
        else:
            df['fecha_hora'] = pd.to_datetime(df['fecha'])
        df['fecha_solo'] = df['fecha_hora'].dt.date
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

st.title("📍 Dashboard de Auditoría GPS")
st.markdown("---")

archivo = st.file_uploader("📂 Arrastra aquí tu reporte de visitas", type=["xlsx", "csv"])

if archivo:
    df = cargar_datos(archivo)
    
    if df is not None:
        with st.sidebar:
            st.header("⚙️ Controles")
            canal_sel = st.selectbox("Canal de Venta", ["MZO", "TDB"])
            vendedores_filtrados = sorted(df[df['canal'] == canal_sel]['vendedor'].unique())
            vendedor_sel = st.selectbox("Empleado", vendedores_filtrados)
            fechas_vendedor = sorted(df[df['vendedor'] == vendedor_sel]['fecha_solo'].unique())
            fecha_sel = st.selectbox("Fecha de Auditoría", fechas_vendedor)
            
            st.divider()
            st.subheader("Configuración Mapa")
            ver_original = st.checkbox("Ver Línea Real (Rojo)", value=True)
            ver_optimizado = st.checkbox("Ver Línea Sugerida (Verde)", value=True)
            tipo_etiqueta = st.radio("Número en punto:", ["Orden Sugerido", "Orden Original"])
            velocidad = st.slider("Velocidad Promedio", 10, 60, 25)

        # Cálculos de Efectividad
        df_canal = df[df['canal'] == canal_sel]
        efect_c = (len(df_canal[df_canal['tipo'] == 'PreVenta']) / len(df_canal) * 100) if not df_canal.empty else 0
        df_vend = df[df['vendedor'] == vendedor_sel]
        efect_v = (len(df_vend[df_vend['tipo'] == 'PreVenta']) / len(df_vend) * 100) if not df_vend.empty else 0
        ruta_real = df_vend[df_vend['fecha_solo'] == fecha_sel].sort_values('fecha_hora').reset_index(drop=True)
        ruta_real['orden_original'] = range(1, len(ruta_real) + 1)
        ventas_dia = len(ruta_real[ruta_real['tipo'] == 'PreVenta'])
        efect_dia = (ventas_dia / len(ruta_real) * 100) if not ruta_real.empty else 0

        # --- DASHBOARD METRICS ---
        st.subheader(f"📈 Resultados: {vendedor_sel} ({canal_sel})")
        m1, m2, m3 = st.columns(3)
        m1.metric(f"Efectividad {canal_sel}", f"{efect_c:.1f}%")
        m2.metric("Efectividad Vendedor", f"{efect_v:.1f}%", delta=f"{efect_v - efect_c:.1f}% vs Canal")
        m3.metric("Efectividad del Día", f"{efect_dia:.1f}%", f"{ventas_dia} ventas hoy")

        if not ruta_real.empty:
            ruta_optima = optimizar_ruta_vecino(ruta_real)
            ruta_optima['orden_sugerido'] = range(1, len(ruta_optima) + 1)
            
            def calc_total_km(df_temp):
                total = 0
                for i in range(len(df_temp)-1):
                    total += haversine(df_temp.iloc[i]['latitud'], df_temp.iloc[i]['longitud'], 
                                       df_temp.iloc[i+1]['latitud'], df_temp.iloc[i+1]['longitud'])
                return total

            km_r, km_o = calc_total_km(ruta_real), calc_total_km(ruta_optima)
            
            st.markdown("<br>", unsafe_allow_html=True)
            d1, d2, d3 = st.columns(3)
            d1.metric("Km Recorridos", f"{km_r:.2f} km")
            d2.metric("Km Sugeridos", f"{km_o:.2f} km")
            d3.metric("Ahorro Potencial", f"{km_r - km_o:.2f} km", f"{((km_r-km_o)/km_r*100 if km_r>0 else 0):.1f}%")

            # --- MAPA CON FULLSCREEN ---
            st.markdown("<br>", unsafe_allow_html=True)
            m = folium.Map(location=[ruta_real['latitud'].mean(), ruta_real['longitud'].mean()], 
                           zoom_start=14, 
                           tiles="cartodbpositron")
            
            # AGREGAR BOTÓN FULLSCREEN
            Fullscreen(
                position="topright",
                title="Ver en Pantalla Completa",
                title_cancel="Salir de Pantalla Completa",
                force_separate_button=True
            ).add_to(m)
            
            if ver_original:
                folium.PolyLine(list(zip(ruta_real['latitud'], ruta_real['longitud'])), color="#e74c3c", weight=3, opacity=0.4).add_to(m)
            if ver_optimizado:
                folium.PolyLine(list(zip(ruta_optima['latitud'], ruta_optima['longitud'])), color="#27ae60", weight=5, opacity=0.7, dash_array='8, 8').add_to(m)
            
            for _, row in ruta_optima.iterrows():
                num = row['orden_sugerido'] if "Sugerido" in tipo_etiqueta else row['orden_original']
                color = "#27ae60" if "Sugerido" in tipo_etiqueta else "#e74c3c"
                icon_v = "✅" if row['tipo'] == 'PreVenta' else "❌"
                
                html = f"""<div style="background:{color};color:white;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-weight:bold;border:2px solid white;box-shadow: 0 2px 4px rgba(0,0,0,0.2);">{num}</div>"""
                
                folium.Marker(
                    [row['latitud'], row['longitud']],
                    tooltip=f"{icon_v} {row['cliente']} | Orig: #{row['orden_original']} → Sug: #{row['orden_sugerido']}",
                    icon=DivIcon(icon_size=(28,28), icon_anchor=(14,14), html=html)
                ).add_to(m)

            st_folium(m, width="100%", height=550)
            
            # --- TABLA Y DESCARGA ---
            st.divider()
            c_down1, c_down2 = st.columns([3, 1])
            with c_down1:
                st.subheader("📋 Detalle de la Ruta")
            with c_down2:
                kml = simplekml.Kml()
                for _, r in ruta_optima.iterrows():
                    kml.newpoint(name=f"#{r['orden_sugerido']} {r['cliente']}", coords=[(r['longitud'], r['latitud'])])
                st.download_button("📥 Descargar KML", kml.kml(), f"Ruta_{vendedor_sel}.kml", use_container_width=True)
            
            st.dataframe(ruta_optima[['orden_sugerido', 'orden_original', 'cliente', 'tipo', 'monto']], use_container_width=True)
        else:
            st.warning("No hay datos para la fecha seleccionada.")
