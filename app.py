import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from scipy.spatial.distance import cdist
import simplekml
import math

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Optimizador de Rutas", layout="wide", page_icon="🚚")

st.title("🚚 Auditoría y Optimización de Rutas GPS")

# --- BARRA LATERAL (CONFIGURACIÓN) ---
with st.sidebar:
    st.header("⚙️ Configuración")
    velocidad_promedio = st.slider(
        "Velocidad Promedio (km/h)", 
        min_value=10, 
        max_value=60, 
        value=25, 
        step=5,
        help="Velocidad estimada para calcular los tiempos de traslado."
    )
    
    st.divider()
    st.subheader("👁️ Visualización del Mapa")
    ver_original = st.checkbox("Ver Trazado Original (Rojo)", value=True)
    ver_optimizado = st.checkbox("Ver Trazado Sugerido (Verde)", value=True)

# --- FUNCIONES ---

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def cargar_datos(uploaded_file):
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        df.columns = df.columns.str.strip().str.lower()
        
        cols_map = {
            'lat': 'latitud', 'lon': 'longitud', 
            'empleado': 'vendedor'
        }
        df = df.rename(columns=cols_map)

        if 'fecha' in df.columns and 'hora' in df.columns:
            df['fecha_hora'] = df['fecha'].astype(str) + ' ' + df['hora'].astype(str)
        elif 'fecha' in df.columns:
            df['fecha_hora'] = df['fecha']

        df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
        df['fecha_solo'] = df['fecha_hora'].dt.date
        
        return df
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        return None

def optimizar_ruta_vecino(df_ruta):
    if len(df_ruta) < 2:
        return df_ruta
    
    # Guardamos el orden original antes de mover nada
    df_pendientes = df_ruta.copy()
    
    ruta_ordenada = [df_pendientes.iloc[0]]
    df_pendientes = df_pendientes.iloc[1:]
    
    while len(df_pendientes) > 0:
        ultimo_punto = ruta_ordenada[-1]
        distancias = cdist(
            [[ultimo_punto['latitud'], ultimo_punto['longitud']]], 
            df_pendientes[['latitud', 'longitud']].values, 
            metric='euclidean'
        )[0]
        indice_mas_cercano = distancias.argmin()
        siguiente_punto = df_pendientes.iloc[indice_mas_cercano]
        ruta_ordenada.append(siguiente_punto)
        df_pendientes = df_pendientes.drop(df_pendientes.index[indice_mas_cercano])
        
    return pd.DataFrame(ruta_ordenada).reset_index(drop=True)

def calcular_metricas(df, velocidad_kmh):
    if len(df) < 2:
        return 0, 0, df
    
    distancias = [0]
    tiempos = [0]
    total_km = 0.0
    
    for i in range(len(df) - 1):
        p1 = df.iloc[i]
        p2 = df.iloc[i+1]
        d = haversine(p1['latitud'], p1['longitud'], p2['latitud'], p2['longitud'])
        total_km += d
        distancias.append(d)
        tiempos.append((d / velocidad_kmh) * 60)
        
    df_res = df.copy()
    df_res['dist_tramo'] = distancias
    df_res['min_tramo'] = tiempos
    return total_km, (total_km/velocidad_kmh)*60, df_res

def generar_kml(df_real, df_opt, vendedor, fecha):
    kml = simplekml.Kml()
    
    # Ruta Real (Rojo)
    fol_real = kml.newfolder(name="Ruta Real")
    coords_real = [(row['longitud'], row['latitud']) for _, row in df_real.iterrows()]
    linea_r = fol_real.newlinestring(name="Trayecto Real", coords=coords_real)
    linea_r.style.linestyle.color = simplekml.Color.red
    linea_r.style.linestyle.width = 3
    
    for _, row in df_real.iterrows():
        pnt = fol_real.newpoint(name=f"#{row['orden_original']} (Real)", coords=[(row['longitud'], row['latitud'])])

    # Ruta Optimizada (Verde)
    fol_opt = kml.newfolder(name="Ruta Optimizada")
    coords_opt = [(row['longitud'], row['latitud']) for _, row in df_opt.iterrows()]
    linea_o = fol_opt.newlinestring(name="Trayecto Optimizado", coords=coords_opt)
    linea_o.style.linestyle.color = simplekml.Color.green
    linea_o.style.linestyle.width = 3
    
    for idx, row in df_opt.iterrows():
        # En el KML de optimizada mostramos el orden sugerido
        pnt = fol_opt.newpoint(name=f"#{idx+1} (Sugerido)", coords=[(row['longitud'], row['latitud'])])
        
    return kml.kml()

# --- INTERFAZ PRINCIPAL ---

archivo = st.file_uploader("📂 Cargar Datos (Excel/CSV)", type=["xlsx", "csv"])

if archivo:
    df = cargar_datos(archivo)
    
    if df is not None:
        c1, c2 = st.columns(2)
        with c1:
            vendedor = st.selectbox("Vendedor", df['vendedor'].unique())
        with c2:
            fechas = df[df['vendedor'] == vendedor]['fecha_solo'].unique()
            fecha = st.selectbox("Fecha", sorted(fechas))
            
        ruta_real = df[(df['vendedor'] == vendedor) & (df['fecha_solo'] == fecha)].sort_values(by='fecha_hora').reset_index(drop=True)
        
        # Asignamos el orden original (1, 2, 3...)
        ruta_real['orden_original'] = range(1, len(ruta_real) + 1)
        
        if len(ruta_real) > 1:
            ruta_optima_raw = optimizar_ruta_vecino(ruta_real)
            
            # Asignamos orden sugerido (es simplemente el nuevo índice + 1)
            ruta_optima_raw['orden_sugerido'] = range(1, len(ruta_optima_raw) + 1)
            
            km_real, min_real, df_real_final = calcular_metricas(ruta_real, velocidad_promedio)
            km_opt, min_opt, df_opt_final = calcular_metricas(ruta_optima_raw, velocidad_promedio)
            
            # Métricas
            st.divider()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("📏 Distancia Real", f"{km_real:.2f} km")
            m2.metric("🎯 Distancia Óptima", f"{km_opt:.2f} km")
            m3.metric("💰 Ahorro", f"{km_real - km_opt:.2f} km", delta_color="normal")
            m4.metric("⏱️ Tiempo Ahorrado", f"{min_real - min_opt:.0f} min", delta_color="normal")
            st.divider()

            # --- MAPA CON FILTROS ---
            m = folium.Map(location=[ruta_real.iloc[0]['latitud'], ruta_real.iloc[0]['longitud']], zoom_start=14)
            
            # 1. Dibujar Líneas según filtros
            if ver_original:
                puntos_real = list(zip(ruta_real['latitud'], ruta_real['longitud']))
                folium.PolyLine(
                    puntos_real, color="red", weight=4, opacity=0.6, tooltip="Trayecto Real (Orden Cronológico)"
                ).add_to(m)
                
            if ver_optimizado:
                puntos_opt = list(zip(ruta_optima_raw['latitud'], ruta_optima_raw['longitud']))
                folium.PolyLine(
                    puntos_opt, color="green", weight=4, opacity=0.8, dash_array='5, 10', tooltip="Trayecto Sugerido (Optimizado)"
                ).add_to(m)
            
            # 2. Dibujar Marcadores (Usamos el DF Optimizado porque tiene ambos datos: orden orig y sug)
            # Nota: Los puntos geográficos son los mismos en ambos DF, solo cambia el orden.
            for i, row in df_opt_final.iterrows():
                
                # Diseño del Tooltip (Lo que se ve al pasar el mouse)
                texto_tooltip = f"#{row['orden_original']} (Orig) ➡️ #{row['orden_sugerido']} (Sug)"
                
                # Diseño del Popup (Lo que se ve al hacer clic)
                texto_popup = f"""
                <div style="font-family: sans-serif; min-width: 200px;">
                    <h4 style="margin-bottom: 5px;">{row['cliente']}</h4>
                    <b>📍 Secuencia:</b><br>
                    • Orden Real: <b>{row['orden_original']}</b><br>
                    • Orden Sugerido: <b>{row['orden_sugerido']}</b><br>
                    <hr>
                    <b>🕒 Horario:</b> {row['fecha_hora'].time()}<br>
                    <b>🚗 Viaje est.:</b> {row['min_tramo']:.1f} min
                </div>
                """
                
                # Icono: Azul si el orden coincide, Naranja si cambió drásticamente
                color_icono = "blue" if row['orden_original'] == row['orden_sugerido'] else "orange"
                
                folium.Marker(
                    [row['latitud'], row['longitud']],
                    popup=folium.Popup(texto_popup, max_width=300),
                    tooltip=texto_tooltip,
                    icon=folium.Icon(color=color_icono, icon="user", prefix="fa")
                ).add_to(m)

            st_folium(m, width=1200, height=500)
            
            # --- TABLA COMPARATIVA ---
            st.subheader("📊 Comparación de Secuencias")
            # Unimos la info para mostrar una sola tabla limpia
            # Mostramos el orden sugerido como índice principal
            df_display = df_opt_final[['orden_sugerido', 'orden_original', 'cliente', 'fecha_hora', 'dist_tramo']].copy()
            df_display.columns = ['Orden Sugerido', 'Orden Real', 'Cliente', 'Hora Visita Real', 'Dist. Tramo (km)']
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # --- DESCARGA ---
            kml_data = generar_kml(ruta_real, df_opt_final, vendedor, fecha)
            st.download_button("📥 Descargar KML", kml_data, f"Ruta_{vendedor}.kml")
            
        else:
            st.warning("Datos insuficientes para la fecha seleccionada.")
