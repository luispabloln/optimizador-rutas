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
st.markdown("Sube tu reporte de visitas para analizar la eficiencia del recorrido, calcular distancias y tiempos estimados.")

# --- BARRA LATERAL (CONFIGURACIÓN) ---
with st.sidebar:
    st.header("⚙️ Configuración")
    velocidad_promedio = st.slider(
        "Velocidad Promedio (km/h)", 
        min_value=10, 
        max_value=60, 
        value=25, 
        step=5,
        help="Velocidad estimada para calcular los tiempos de traslado entre puntos."
    )

# --- FUNCIONES DE CÁLCULO ---

def haversine(lat1, lon1, lat2, lon2):
    """Calcula la distancia en Kilómetros entre dos puntos (Haversine)."""
    R = 6371  # Radio de la Tierra en km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def cargar_datos(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file)
        # Normalizar columnas a minúsculas y sin espacios
        df.columns = df.columns.str.strip().str.lower()
        
        # Mapeo de nombres comunes
        cols_map = {
            'lat': 'latitud', 'lon': 'longitud', 
            'fecha': 'fecha_hora', 'hora': 'fecha_hora'
        }
        df = df.rename(columns=cols_map)

        # Convertir fecha
        df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
        df['fecha_solo'] = df['fecha_hora'].dt.date
        return df
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        return None

def optimizar_ruta_vecino(df_ruta):
    """Algoritmo del Vecino Más Cercano."""
    if len(df_ruta) < 2:
        return df_ruta
    
    # Copia de seguridad
    df_pendientes = df_ruta.copy()
    
    # Empezamos desde el primer punto registrado (asumimos que es el inicio)
    ruta_ordenada = [df_pendientes.iloc[0]]
    df_pendientes = df_pendientes.iloc[1:]
    
    while len(df_pendientes) > 0:
        ultimo_punto = ruta_ordenada[-1]
        
        # Calcular distancias a todos los pendientes
        distancias = cdist(
            [[ultimo_punto['latitud'], ultimo_punto['longitud']]], 
            df_pendientes[['latitud', 'longitud']].values, 
            metric='euclidean' # Usamos euclideana para el sort rápido
        )[0]
        
        indice_mas_cercano = distancias.argmin()
        
        # Agregar el más cercano
        siguiente_punto = df_pendientes.iloc[indice_mas_cercano]
        ruta_ordenada.append(siguiente_punto)
        
        # Eliminar de pendientes
        df_pendientes = df_pendientes.drop(df_pendientes.index[indice_mas_cercano])
        
    return pd.DataFrame(ruta_ordenada).reset_index(drop=True)

def calcular_metricas_detalladas(df, velocidad_kmh):
    """
    Calcula distancia y tiempo tramo a tramo.
    Retorna el total de km, total de minutos y el DF enriquecido.
    """
    if len(df) < 2:
        return 0, 0, df

    distancias = []
    tiempos = []
    
    total_km = 0.0
    
    # El primer punto no tiene "anterior", así que empieza en 0
    distancias.append(0)
    tiempos.append(0)
    
    for i in range(len(df) - 1):
        p1 = df.iloc[i]
        p2 = df.iloc[i+1]
        
        dist_km = haversine(p1['latitud'], p1['longitud'], p2['latitud'], p2['longitud'])
        total_km += dist_km
        
        # Tiempo = Distancia / Velocidad (en horas) -> Convertir a minutos
        tiempo_min = (dist_km / velocidad_kmh) * 60
        
        distancias.append(round(dist_km, 2))
        tiempos.append(round(tiempo_min, 1))
        
    # Agregamos las columnas al DF para mostrar en tabla (desplazado: fila i muestra distancia desde i-1)
    df_result = df.copy()
    df_result['dist_desde_anterior_km'] = distancias
    df_result['minutos_viaje'] = tiempos
    
    total_minutos = (total_km / velocidad_kmh) * 60
    
    return total_km, total_minutos, df_result

def generar_kml(df_real, df_opt, vendedor, fecha):
    kml = simplekml.Kml()
    
    # Estilos
    estilo_real = simplekml.Style()
    estilo_real.linestyle.color = simplekml.Color.red
    estilo_real.linestyle.width = 3
    
    estilo_opt = simplekml.Style()
    estilo_opt.linestyle.color = simplekml.Color.green
    estilo_opt.linestyle.width = 3

    # Ruta Real
    fol_real = kml.newfolder(name="Ruta Real")
    coords_real = [(row['longitud'], row['latitud']) for _, row in df_real.iterrows()]
    linea_r = fol_real.newlinestring(name="Trayecto Real", coords=coords_real)
    linea_r.style = estilo_real
    
    for i, row in df_real.iterrows():
        pnt = fol_real.newpoint(name=f"{i+1}. {row.get('cliente','S/N')}", coords=[(row['longitud'], row['latitud'])])

    # Ruta Optimizada
    fol_opt = kml.newfolder(name="Ruta Optimizada")
    coords_opt = [(row['longitud'], row['latitud']) for _, row in df_opt.iterrows()]
    linea_o = fol_opt.newlinestring(name="Trayecto Optimizado", coords=coords_opt)
    linea_o.style = estilo_opt
    
    return kml.kml()

# --- INTERFAZ PRINCIPAL ---

archivo = st.file_uploader("📂 Cargar Excel (.xlsx)", type=["xlsx"])

if archivo:
    df = cargar_datos(archivo)
    
    if df is not None:
        c1, c2 = st.columns(2)
        with c1:
            vendedor = st.selectbox("Vendedor", df['vendedor'].unique())
        with c2:
            fechas = df[df['vendedor'] == vendedor]['fecha_solo'].unique()
            fecha = st.selectbox("Fecha", sorted(fechas))
            
        # Filtrar datos
        ruta_real = df[(df['vendedor'] == vendedor) & (df['fecha_solo'] == fecha)].sort_values(by='fecha_hora').reset_index(drop=True)
        
        if len(ruta_real) > 1:
            # 1. Calcular Optimización
            ruta_optima_raw = optimizar_ruta_vecino(ruta_real)
            
            # 2. Calcular Métricas y Tiempos
            km_real, min_real, df_real_final = calcular_metricas_detalladas(ruta_real, velocidad_promedio)
            km_opt, min_opt, df_opt_final = calcular_metricas_detalladas(ruta_optima_raw, velocidad_promedio)
            
            # Métricas comparativas
            ahorro_km = km_real - km_opt
            ahorro_min = min_real - min_opt
            
            # --- DASHBOARD ---
            st.divider()
            col1, col2, col3, col4 = st.columns(4)
            
            col1.metric("📏 Distancia Real", f"{km_real:.2f} km", f"{min_real:.0f} min cond.")
            col2.metric("🎯 Distancia Óptima", f"{km_opt:.2f} km", f"{min_opt:.0f} min cond.")
            col3.metric("💰 Ahorro Distancia", f"{ahorro_km:.2f} km", delta_color="normal")
            col4.metric("⏱️ Ahorro Tiempo", f"{ahorro_min:.0f} min", delta_color="normal")
            st.caption(f"*Tiempos calculados a una velocidad promedio constante de {velocidad_promedio} km/h (sin contar tiempos de parada en cliente).")
            st.divider()

            # --- MAPA ---
            m = folium.Map(location=[ruta_real.iloc[0]['latitud'], ruta_real.iloc[0]['longitud']], zoom_start=14)
            
            puntos_real = list(zip(ruta_real['latitud'], ruta_real['longitud']))
            puntos_opt = list(zip(ruta_optima_raw['latitud'], ruta_optima_raw['longitud']))
            
            folium.PolyLine(puntos_real, color="red", weight=4, opacity=0.5, tooltip="Ruta Real").add_to(m)
            folium.PolyLine(puntos_opt, color="green", weight=4, opacity=0.8, dash_array='5, 10', tooltip="Ruta Sugerida").add_to(m)
            
            # Marcadores numerados ruta OPTIMIZADA
            for i, row in df_opt_final.iterrows():
                # Info para el popup
                texto_popup = f"""
                <b>Orden Sugerido: {i+1}</b><br>
                Cliente: {row['cliente']}<br>
                Viaje desde anterior: {row['minutos_viaje']} min
                """
                folium.Marker(
                    [row['latitud'], row['longitud']],
                    popup=folium.Popup(texto_popup, max_width=300),
                    icon=folium.Icon(color="blue", icon="user", prefix="fa")
                ).add_to(m)

            st_folium(m, width=1200, height=500)
            
            # --- TABLAS DETALLADAS ---
            st.subheader("📊 Detalle de la Secuencia Sugerida")
            st.dataframe(
                df_opt_final[['cliente', 'dist_desde_anterior_km', 'minutos_viaje', 'latitud', 'longitud']],
                column_config={
                    "dist_desde_anterior_km": st.column_config.NumberColumn("Km desde anterior", format="%.2f km"),
                    "minutos_viaje": st.column_config.NumberColumn("Tiempo viaje est.", format="%.1f min"),
                },
                use_container_width=True
            )
            
            # --- DESCARGA ---
            kml_data = generar_kml(ruta_real, ruta_optima_raw, vendedor, fecha)
            st.download_button("📥 Descargar KML", kml_data, f"Ruta_{vendedor}.kml")
            
        else:
            st.warning("No hay suficientes datos para generar ruta.")