import streamlit as st
import pandas as pd
import folium
from folium.features import DivIcon
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
        step=5
    )
    
    st.divider()
    st.subheader("👁️ Visualización del Mapa")
    
    # Opción para elegir qué número ver dentro del círculo
    tipo_etiqueta = st.radio(
        "¿Qué número ver DENTRO del círculo?",
        ["Orden Sugerido (Verde)", "Orden Original (Rojo)"],
        index=0
    )
    
    st.caption("Filtros de Líneas:")
    ver_original = st.checkbox("Ver Línea Original", value=True)
    ver_optimizado = st.checkbox("Ver Línea Sugerida", value=True)

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
        
        # Mapeo flexible de columnas
        cols_map = {
            'lat': 'latitud', 'lon': 'longitud', 
            'empleado': 'vendedor'
        }
        df = df.rename(columns=cols_map)

        # Unir fecha y hora si vienen separadas
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
    
    fol_real = kml.newfolder(name="Ruta Real")
    coords_real = [(row['longitud'], row['latitud']) for _, row in df_real.iterrows()]
    linea_r = fol_real.newlinestring(name="Trayecto Real", coords=coords_real)
    linea_r.style.linestyle.color = simplekml.Color.red
    linea_r.style.linestyle.width = 3
    
    for _, row in df_real.iterrows():
        pnt = fol_real.newpoint(name=f"#{row['orden_original']} (Real)", coords=[(row['longitud'], row['latitud'])])

    fol_opt = kml.newfolder(name="Ruta Optimizada")
    coords_opt = [(row['longitud'], row['latitud']) for _, row in df_opt.iterrows()]
    linea_o = fol_opt.newlinestring(name="Trayecto Optimizado", coords=coords_opt)
    linea_o.style.linestyle.color = simplekml.Color.green
    linea_o.style.linestyle.width = 3
    
    for idx, row in df_opt.iterrows():
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
        ruta_real['orden_original'] = range(1, len(ruta_real) + 1)
        
        if len(ruta_real) > 1:
            ruta_optima_raw = optimizar_ruta_vecino(ruta_real)
            ruta_optima_raw['orden_sugerido'] = range(1, len(ruta_optima_raw) + 1)
            
            km_real, min_real, df_real_final = calcular_metricas(ruta_real, velocidad_promedio)
            km_opt, min_opt, df_opt_final = calcular_metricas(ruta_optima_raw, velocidad_promedio)
            
            st.divider()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("📏 Distancia Real", f"{km_real:.2f} km")
            m2.metric("🎯 Distancia Óptima", f"{km_opt:.2f} km")
            m3.metric("💰 Ahorro", f"{km_real - km_opt:.2f} km")
            m4.metric("⏱️ Tiempo Ahorrado", f"{min_real - min_opt:.0f} min")
            st.divider()

            # --- MAPA ---
            m = folium.Map(location=[ruta_real.iloc[0]['latitud'], ruta_real.iloc[0]['longitud']], zoom_start=14)
            
            if ver_original:
                puntos_real = list(zip(ruta_real['latitud'], ruta_real['longitud']))
                folium.PolyLine(puntos_real, color="red", weight=4, opacity=0.4, tooltip="Original").add_to(m)
                
            if ver_optimizado:
                puntos_opt = list(zip(ruta_optima_raw['latitud'], ruta_optima_raw['longitud']))
                folium.PolyLine(puntos_opt, color="green", weight=4, opacity=0.6, dash_array='5, 10', tooltip="Sugerido").add_to(m)
            
            # --- MARCADORES PERSONALIZADOS ---
            for i, row in df_opt_final.iterrows():
                
                # 1. Configurar Icono Visual (Circulo con numero)
                if "Sugerido" in tipo_etiqueta:
                    numero_mostrar = row['orden_sugerido']
                    color_fondo = "#28a745" # Verde
                else:
                    numero_mostrar = row['orden_original']
                    color_fondo = "#dc3545" # Rojo
                
                html_icono = f"""
                <div style="
                    background-color: {color_fondo};
                    color: white;
                    border-radius: 50%;
                    width: 30px;
                    height: 30px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    font-family: Arial, sans-serif;
                    border: 2px solid white;
                    box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
                    font-size: 14px;
                ">
                    {numero_mostrar}
                </div>
                """
                
                # 2. Configurar Tooltip (Lo que pediste: Original vs Sugerido)
                texto_tooltip = f"Cliente: {row['cliente']} | Orig: #{row['orden_original']} ➡️ Sug: #{row['orden_sugerido']}"
                
                # 3. Configurar Popup (Click para detalles)
                texto_popup = f"""
                <div style="font-family: sans-serif; min-width: 200px;">
                    <h4 style="margin:0;">{row['cliente']}</h4>
                    <hr style="margin: 5px 0;">
                    <b>Orden Real:</b> {row['orden_original']}<br>
                    <b>Orden Sugerido:</b> {row['orden_sugerido']}<br>
                    <b>Hora Real:</b> {row['fecha_hora'].time()}
                </div>
                """
                
                folium.Marker(
                    location=[row['latitud'], row['longitud']],
                    popup=folium.Popup(texto_popup, max_width=250),
                    tooltip=texto_tooltip, # <--- AQUI ESTA TU ETIQUETA FLOTANTE
                    icon=DivIcon(
                        icon_size=(30,30),
                        icon_anchor=(15,15),
                        html=html_icono
                    )
                ).add_to(m)

            st_folium(m, width=1200, height=500)
            
            st.subheader("📊 Comparación de Secuencias")
            df_display = df_opt_final[['orden_sugerido', 'orden_original', 'cliente', 'fecha_hora', 'dist_tramo']].copy()
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            kml_data = generar_kml(ruta_real, df_opt_final, vendedor, fecha)
            st.download_button("📥 Descargar KML", kml_data, f"Ruta_{vendedor}.kml")
            
        else:
            st.warning("Datos insuficientes.")
