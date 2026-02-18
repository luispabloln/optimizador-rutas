import streamlit as st
import pandas as pd
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
from scipy.spatial.distance import cdist
import simplekml
import math

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Auditoría de Ventas GPS", layout="wide", page_icon="📊")

st.title("📊 Auditoría de Rutas y Efectividad por Canal")

# --- FUNCIONES DE LÓGICA DE NEGOCIO ---

def asignar_canal(nombre):
    """Clasifica al vendedor según las reglas de negocio."""
    nombre = str(nombre).upper()
    mzo_keywords = ['ABDY', 'MARCIA', 'JESUS', 'KEVIN', 'MARIBEL']
    if any(keyword in nombre for keyword in mzo_keywords):
        return 'MZO'
    else:
        return 'TDB'

def cargar_datos(uploaded_file):
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        df.columns = df.columns.str.strip().str.lower()
        
        # Mapeo y creación de Canal
        df = df.rename(columns={'empleado': 'vendedor', 'lat': 'latitud', 'lon': 'longitud'})
        df['canal'] = df['vendedor'].apply(asignar_canal)
        
        if 'fecha' in df.columns and 'hora' in df.columns:
            df['fecha_hora'] = pd.to_datetime(df['fecha'].astype(str) + ' ' + df['hora'].astype(str))
        else:
            df['fecha_hora'] = pd.to_datetime(df['fecha'])
            
        df['fecha_solo'] = df['fecha_hora'].dt.date
        return df
    except Exception as e:
        st.error(f"Error al leer datos: {e}")
        return None

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

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

archivo = st.file_uploader("📂 Sube tu archivo (Excel o CSV)", type=["xlsx", "csv"])

if archivo:
    df = cargar_datos(archivo)
    
    if df is not None:
        # --- BARRA LATERAL CON FILTROS ---
        with st.sidebar:
            st.header("🔍 Filtros de Auditoría")
            canal_sel = st.selectbox("Seleccionar Canal", ["MZO", "TDB"])
            
            # Filtrar vendedores por el canal seleccionado
            vendedores_filtrados = sorted(df[df['canal'] == canal_sel]['vendedor'].unique())
            vendedor_sel = st.selectbox("Seleccionar Vendedor", vendedores_filtrados)
            
            fechas_vendedor = sorted(df[df['vendedor'] == vendedor_sel]['fecha_solo'].unique())
            fecha_sel = st.selectbox("Seleccionar Fecha", fechas_vendedor)
            
            st.divider()
            st.subheader("⚙️ Mapa")
            velocidad = st.slider("Velocidad (km/h)", 10, 60, 25)
            tipo_etiqueta = st.radio("Número en Círculo:", ["Orden Sugerido (Verde)", "Orden Original (Rojo)"])

        # --- CÁLCULOS DE EFECTIVIDAD ---
        # 1. Efectividad Canal
        df_canal = df[df['canal'] == canal_sel]
        ventas_c = len(df_canal[df_canal['tipo'] == 'PreVenta'])
        total_c = len(df_canal)
        efect_c = (ventas_c / total_c * 100) if total_c > 0 else 0
        
        # 2. Efectividad Vendedor (Global)
        df_vend = df[df['vendedor'] == vendedor_sel]
        ventas_v = len(df_vend[df_vend['tipo'] == 'PreVenta'])
        total_v = len(df_vend)
        efect_v = (ventas_v / total_v * 100) if total_v > 0 else 0

        # 3. Ruta del Día
        ruta_real = df_vend[df_vend['fecha_solo'] == fecha_sel].sort_values('fecha_hora').reset_index(drop=True)
        ruta_real['orden_original'] = range(1, len(ruta_real) + 1)
        
        ventas_dia = len(ruta_real[ruta_real['tipo'] == 'PreVenta'])
        efect_dia = (ventas_dia / len(ruta_real) * 100) if not ruta_real.empty else 0

        # --- DASHBOARD SUPERIOR ---
        st.subheader(f"📈 Rendimiento Canal {canal_sel}")
        col_c1, col_c2, col_c3 = st.columns(3)
        col_c1.metric(f"Efectividad Canal {canal_sel}", f"{efect_c:.1f}%", help="Efectividad de todos los vendedores de este canal")
        col_c2.metric(f"Efectividad {vendedor_sel}", f"{efect_v:.1f}%", delta=f"{efect_v - efect_c:.1f}% vs Canal")
        col_c3.metric("Efectividad del Día", f"{efect_dia:.1f}%", f"{ventas_dia} ventas")

        if not ruta_real.empty:
            ruta_optima = optimizar_ruta_vecino(ruta_real)
            ruta_optima['orden_sugerido'] = range(1, len(ruta_optima) + 1)
            
            # Distancias
            def calc_km(df_k):
                total = 0
                for i in range(len(df_k)-1):
                    total += haversine(df_k.iloc[i]['latitud'], df_k.iloc[i]['longitud'], df_k.iloc[i+1]['latitud'], df_k.iloc[i+1]['longitud'])
                return total
            
            km_r = calc_km(ruta_real)
            km_o = calc_km(ruta_optima)
            
            st.divider()
            m1, m2, m3 = st.columns(3)
            m1.metric("📏 Distancia Real", f"{km_r:.2f} km")
            m2.metric("🎯 Distancia Óptima", f"{km_o:.2f} km")
            m3.metric("💰 Ahorro Sugerido", f"{km_r - km_o:.2f} km", f"{((km_r-km_o)/km_r*100):.1f}% de trayecto", delta_color="normal")
            
            # --- MAPA ---
            m = folium.Map(location=[ruta_real['latitud'].mean(), ruta_real['longitud'].mean()], zoom_start=14)
            folium.PolyLine(list(zip(ruta_real['latitud'], ruta_real['longitud'])), color="red", weight=2, opacity=0.4).add_to(m)
            folium.PolyLine(list(zip(ruta_optima['latitud'], ruta_optima['longitud'])), color="green", weight=4, opacity=0.7, dash_array='5, 10').add_to(m)
            
            for i, row in ruta_optima.iterrows():
                num = row['orden_sugerido'] if "Sugerido" in tipo_etiqueta else row['orden_original']
                color = "#28a745" if "Sugerido" in tipo_etiqueta else "#dc3545"
                icon_v = "✅" if row['tipo'] == 'PreVenta' else "❌"
                
                html = f"""<div style="background:{color};color:white;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-weight:bold;border:2px solid white;">{num}</div>"""
                folium.Marker(
                    [row['latitud'], row['longitud']],
                    tooltip=f"{icon_v} {row['cliente']} | Sug:#{row['orden_sugerido']} Real:#{row['orden_original']}",
                    icon=DivIcon(icon_size=(26,26), icon_anchor=(13,13), html=html)
                ).add_to(m)

            st_folium(m, width=1200, height=500)
            
            # --- TABLA Y DESCARGA ---
            with st.expander("Ver tabla comparativa de ruta"):
                st.dataframe(ruta_optima[['orden_sugerido', 'orden_original', 'cliente', 'tipo', 'monto']], use_container_width=True)
            
            kml = simplekml.Kml()
            for _, r in ruta_optima.iterrows():
                kml.newpoint(name=f"#{r['orden_sugerido']} {r['cliente']}", coords=[(r['longitud'], r['latitud'])])
            st.download_button("📥 Descargar KML Sugerido", kml.kml(), f"Ruta_{vendedor_sel}.kml")
        else:
            st.warning("No hay visitas registradas para este vendedor en la fecha seleccionada.")
