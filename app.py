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

# --- BARRA LATERAL (CONFIGURACIÓN) ---
with st.sidebar:
    st.header("⚙️ Configuración")
    velocidad_promedio = st.slider("Velocidad Promedio (km/h)", 10, 60, 25)
    
    st.divider()
    st.subheader("👁️ Visualización del Mapa")
    tipo_etiqueta = st.radio(
        "¿Qué número ver DENTRO del círculo?",
        ["Orden Sugerido (Verde)", "Orden Original (Rojo)"],
        index=0
    )
    ver_original = st.checkbox("Ver Línea Original (Rojo)", value=True)
    ver_optimizado = st.checkbox("Ver Línea Sugerida (Verde)", value=True)

# --- FUNCIONES DE CÁLCULO ---

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

def cargar_datos(uploaded_file):
    try:
        df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        df.columns = df.columns.str.strip().str.lower()
        
        # Mapeo de nombres según tu archivo
        df = df.rename(columns={'empleado': 'vendedor', 'lat': 'latitud', 'lon': 'longitud'})
        
        if 'fecha' in df.columns and 'hora' in df.columns:
            df['fecha_hora'] = pd.to_datetime(df['fecha'].astype(str) + ' ' + df['hora'].astype(str))
        else:
            df['fecha_hora'] = pd.to_datetime(df['fecha'])
            
        df['fecha_solo'] = df['fecha_hora'].dt.date
        return df
    except Exception as e:
        st.error(f"Error al leer datos: {e}")
        return None

def optimizar_ruta_vecino(df_ruta):
    if len(df_ruta) < 2: return df_ruta
    df_pendientes = df_ruta.copy()
    ruta_ordenada = [df_pendientes.iloc[0]]
    df_pendientes = df_pendientes.iloc[1:]
    while len(df_pendientes) > 0:
        ultimo = ruta_ordenada[-1]
        distancias = cdist([[ultimo['latitud'], ultimo['longitud']]], df_pendientes[['latitud', 'longitud']].values, metric='euclidean')[0]
        idx = distancias.argmin()
        ruta_ordenada.append(df_pendientes.iloc[idx])
        df_pendientes = df_pendientes.drop(df_pendientes.index[idx])
    return pd.DataFrame(ruta_ordenada).reset_index(drop=True)

def calcular_distancia_tiempo(df, velocidad):
    if len(df) < 2: return 0, 0, df
    distancias, tiempos = [0], [0]
    total_km = 0.0
    for i in range(len(df)-1):
        d = haversine(df.iloc[i]['latitud'], df.iloc[i]['longitud'], df.iloc[i+1]['latitud'], df.iloc[i+1]['longitud'])
        total_km += d
        distancias.append(d)
        tiempos.append((d / velocidad) * 60)
    df_res = df.copy()
    df_res['km_tramo'], df_res['min_tramo'] = distancias, tiempos
    return total_km, (total_km/velocidad)*60, df_res

# --- INTERFAZ PRINCIPAL ---

archivo = st.file_uploader("📂 Sube tu archivo (Excel o CSV)", type=["xlsx", "csv"])

if archivo:
    df = cargar_datos(archivo)
    
    if df is not None:
        c1, c2 = st.columns(2)
        vendedor_sel = c1.selectbox("Seleccionar Vendedor", sorted(df['vendedor'].unique()))
        fechas_vendedor = sorted(df[df['vendedor'] == vendedor_sel]['fecha_solo'].unique())
        fecha_sel = c2.selectbox("Seleccionar Fecha", fechas_vendedor)
        
        # --- FILTRADO DE DATOS ---
        df_vendedor_global = df[df['vendedor'] == vendedor_sel]
        ruta_real = df_vendedor_global[df_vendedor_global['fecha_solo'] == fecha_sel].sort_values('fecha_hora').reset_index(drop=True)
        ruta_real['orden_original'] = range(1, len(ruta_real) + 1)
        
        if not ruta_real.empty:
            # --- CÁLCULO DE EFECTIVIDAD ---
            # Global
            ventas_global = len(df_vendedor_global[df_vendedor_global['tipo'] == 'PreVenta'])
            total_global = len(df_vendedor_global)
            efect_global = (ventas_global / total_global * 100) if total_global > 0 else 0
            
            # Diaria
            ventas_dia = len(ruta_real[ruta_real['tipo'] == 'PreVenta'])
            total_dia = len(ruta_real)
            efect_dia = (ventas_dia / total_dia * 100) if total_dia > 0 else 0
            
            # --- DASHBOARD DE MÉTRICAS ---
            st.subheader("🎯 Indicadores de Desempeño")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Efectividad Hoy", f"{efect_dia:.1f}%", f"{ventas_dia} de {total_dia} visitas")
            m2.metric("Efectividad Global", f"{efect_global:.1f}%", f"Histórico: {vendedor_sel}")
            
            # Optimización y Rutas
            ruta_optima = optimizar_ruta_vecino(ruta_real)
            ruta_optima['orden_sugerido'] = range(1, len(ruta_optima) + 1)
            
            km_r, min_r, df_r_f = calcular_distancia_tiempo(ruta_real, velocidad_promedio)
            km_o, min_o, df_o_f = calcular_distancia_tiempo(ruta_optima, velocidad_promedio)
            
            m3.metric("Ahorro Distancia", f"{km_r - km_o:.2f} km", f"Total sugerido: {km_o:.1f} km")
            m4.metric("Tiempo Conducción", f"{min_o:.0f} min", f"Ahorro: {min_r - min_o:.0f} min")
            
            st.divider()

            # --- MAPA ---
            m = folium.Map(location=[ruta_real['latitud'].mean(), ruta_real['longitud'].mean()], zoom_start=14)
            
            if ver_original:
                folium.PolyLine(list(zip(ruta_real['latitud'], ruta_real['longitud'])), color="red", weight=3, opacity=0.4).add_to(m)
            if ver_optimizado:
                folium.PolyLine(list(zip(ruta_optima['latitud'], ruta_optima['longitud'])), color="green", weight=4, opacity=0.7, dash_array='5, 10').add_to(m)
            
            for i, row in df_o_f.iterrows():
                num = row['orden_sugerido'] if "Sugerido" in tipo_etiqueta else row['orden_original']
                color = "#28a745" if "Sugerido" in tipo_etiqueta else "#dc3545"
                
                # Efectividad visual en el punto
                marcador_icono = "✅" if row['tipo'] == 'PreVenta' else "❌"
                
                html_ponto = f"""<div style="background:{color};color:white;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-weight:bold;border:2px solid white;font-size:12px;">{num}</div>"""
                
                folium.Marker(
                    [row['latitud'], row['longitud']],
                    tooltip=f"{marcador_icono} {row['cliente']} | Sug: #{row['orden_sugerido']} | Real: #{row['orden_original']}",
                    popup=f"Estado: {row['tipo']}<br>Hora: {row['fecha_hora'].time()}",
                    icon=DivIcon(icon_size=(28,28), icon_anchor=(14,14), html=html_ponto)
                ).add_to(m)

            st_folium(m, width=1200, height=500)
            
            # --- TABLA Y DESCARGA ---
            st.subheader("📋 Detalle de Visitas (Orden Sugerido)")
            st.dataframe(df_o_f[['orden_sugerido', 'orden_original', 'cliente', 'tipo', 'km_tramo', 'min_tramo']], use_container_width=True, hide_index=True)
            
            # Generar KML (Simplificado)
            kml = simplekml.Kml()
            for _, r in df_o_f.iterrows():
                kml.newpoint(name=f"#{r['orden_sugerido']} {r['cliente']}", coords=[(r['longitud'], r['latitud'])])
            st.download_button("📥 Descargar KML Sugerido", kml.kml(), f"Ruta_{vendedor_sel}_{fecha_sel}.kml")
