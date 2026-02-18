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

st.title("📊 Auditoría de Rutas y Efectividad")

# --- FUNCIONES DE LÓGICA DE NEGOCIO ---

def asignar_canal(nombre):
    """Clasifica al vendedor según el Canal."""
    nombre = str(nombre).upper()
    # Lista actualizada de nombres para canal MZO
    mzo_keywords = ['ABDY', 'MARCIA', 'JESUS', 'KEVIN', 'MARIBEL', 'LUIS PABLO']
    if any(keyword in nombre for keyword in mzo_keywords):
        return 'MZO'
    else:
        return 'TDB'

def cargar_datos(uploaded_file):
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        df.columns = df.columns.str.strip().str.lower()
        
        # Mapeo de columnas según archivo del usuario
        df = df.rename(columns={'empleado': 'vendedor', 'lat': 'latitud', 'lon': 'longitud'})
        df['canal'] = df['vendedor'].apply(asignar_canal)
        
        # Procesamiento de fechas
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
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

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
            canal_sel = st.selectbox("Canal", ["MZO", "TDB"])
            
            vendedores_filtrados = sorted(df[df['canal'] == canal_sel]['vendedor'].unique())
            vendedor_sel = st.selectbox("Vendedor", vendedores_filtrados)
            
            fechas_vendedor = sorted(df[df['vendedor'] == vendedor_sel]['fecha_solo'].unique())
            fecha_sel = st.selectbox("Fecha", fechas_vendedor)
            
            st.divider()
            st.subheader("👁️ Visualización")
            ver_original = st.checkbox("Ver Línea Original (Rojo)", value=True)
            ver_optimizado = st.checkbox("Ver Línea Sugerida (Verde)", value=True)
            tipo_etiqueta = st.radio("Número en Círculo:", ["Orden Sugerido", "Orden Original"])
            
            st.divider()
            velocidad = st.slider("Velocidad Promedio (km/h)", 10, 60, 25)

        # --- CÁLCULOS DE EFECTIVIDAD ---
        df_canal = df[df['canal'] == canal_sel]
        efect_c = (len(df_canal[df_canal['tipo'] == 'PreVenta']) / len(df_canal) * 100) if not df_canal.empty else 0
        
        df_vend = df[df['vendedor'] == vendedor_sel]
        efect_v = (len(df_vend[df_vend['tipo'] == 'PreVenta']) / len(df_vend) * 100) if not df_vend.empty else 0

        ruta_real = df_vend[df_vend['fecha_solo'] == fecha_sel].sort_values('fecha_hora').reset_index(drop=True)
        ruta_real['orden_original'] = range(1, len(ruta_real) + 1)
        
        ventas_dia = len(ruta_real[ruta_real['tipo'] == 'PreVenta'])
        efect_dia = (ventas_dia / len(ruta_real) * 100) if not ruta_real.empty else 0

        # --- DASHBOARD DE MÉTRICAS ---
        st.subheader(f"📈 Rendimiento Canal {canal_sel} | {vendedor_sel}")
        m_c1, m_c2, m_c3 = st.columns(3)
        m_c1.metric(f"Efectividad {canal_sel}", f"{efect_c:.1f}%")
        m_c2.metric(f"Efectividad Global Vendedor", f"{efect_v:.1f}%", delta=f"{efect_v - efect_c:.1f}% vs Canal")
        m_c3.metric("Efectividad del Día", f"{efect_dia:.1f}%", f"{ventas_dia} ventas")

        if not ruta_real.empty:
            ruta_optima = optimizar_ruta_vecino(ruta_real)
            ruta_optima['orden_sugerido'] = range(1, len(ruta_optima) + 1)
            
            # Cálculo de distancias
            def calc_total_km(df_temp):
                total = 0
                for i in range(len(df_temp)-1):
                    total += haversine(df_temp.iloc[i]['latitud'], df_temp.iloc[i]['longitud'], 
                                       df_temp.iloc[i+1]['latitud'], df_temp.iloc[i+1]['longitud'])
                return total

            km_r = calc_total_km(ruta_real)
            km_o = calc_total_km(ruta_optima)
            ahorro = km_r - km_o
            
            st.divider()
            d1, d2, d3 = st.columns(3)
            d1.metric("Distancia Real", f"{km_r:.2f} km")
            d2.metric("Distancia Óptima", f"{km_o:.2f} km")
            d3.metric("Ahorro de Trayecto", f"{ahorro:.2f} km", f"{((ahorro/km_r*100) if km_r>0 else 0):.1f}% menos")

            # --- MAPA ---
            m = folium.Map(location=[ruta_real['latitud'].mean(), ruta_real['longitud'].mean()], zoom_start=14)
            
            if ver_original:
                folium.PolyLine(list(zip(ruta_real['latitud'], ruta_real['longitud'])), 
                                color="red", weight=2, opacity=0.4, tooltip="Ruta Real").add_to(m)
            if ver_optimizado:
                folium.PolyLine(list(zip(ruta_optima['latitud'], ruta_optima['longitud'])), 
                                color="green", weight=4, opacity=0.7, dash_array='5, 10', tooltip="Ruta Sugerida").add_to(m)
            
            for _, row in ruta_optima.iterrows():
                num = row['orden_sugerido'] if "Sugerido" in tipo_etiqueta else row['orden_original']
                color = "#28a745" if "Sugerido" in tipo_etiqueta else "#dc3545"
                icon_v = "✅" if row['tipo'] == 'PreVenta' else "❌"
                
                html = f"""<div style="background:{color};color:white;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-weight:bold;border:2px solid white;font-size:11px;">{num}</div>"""
                
                folium.Marker(
                    [row['latitud'], row['longitud']],
                    tooltip=f"{icon_v} {row['cliente']} | Sug:#{row['orden_sugerido']} Real:#{row['orden_original']}",
                    popup=f"Estado: {row['tipo']}<br>Monto: {row['monto']}",
                    icon=DivIcon(icon_size=(26,26), icon_anchor=(13,13), html=html)
                ).add_to(m)

            st_folium(m, width=1200, height=500)
            
            # --- DESCARGA ---
            kml = simplekml.Kml()
            for _, r in ruta_optima.iterrows():
                kml.newpoint(name=f"#{r['orden_sugerido']} {r['cliente']}", coords=[(r['longitud'], r['latitud'])])
            st.download_button("📥 Descargar KML Optimizado", kml.kml(), f"Ruta_{vendedor_sel}_{fecha_sel}.kml")
        else:
            st.warning("No hay datos para el vendedor en esta fecha.")
