import os
import zipfile
from datetime import datetime
import glob
import json
import requests

carpeta_origen = r"\\sv-sys-05\Hosvi_Anex_Fact\FACTURAS"

def listar_carpeta(ruta_carpeta):
    """Lee y retorna lista de archivos en una carpeta."""
    try:
        return os.listdir(ruta_carpeta)
    except FileNotFoundError:
        print(f"❌ Carpeta no encontrada: {ruta_carpeta}")
        return []


def encontrar_zip(ruta_carpeta):
    """Busca archivos ZIP en la carpeta."""
    try:
        archivos = os.listdir(ruta_carpeta)
        zips = [f for f in archivos if f.endswith('.zip')]
        return zips
    except FileNotFoundError:
        print(f"❌ Carpeta no encontrada: {ruta_carpeta}")
        return []


def obtener_html_de_zip(ruta_zip):
    """Extrae nombres de carpetas dentro de un ZIP."""
    try:
        with zipfile.ZipFile(ruta_zip, 'r') as zip_ref:
            archivos = zip_ref.namelist()
            # Obtener carpetas únicas (líneas que terminan con /)
            carpetas = set()
            for archivo in archivos:
                if '/' in archivo:
                    carpeta = archivo.split('/')[0]
                    if carpeta:  # Evitar strings vacíos
                        carpetas.add(carpeta)
        return sorted(list(carpetas))
    except Exception as e:
        print(f"❌ Error al leer ZIP {ruta_zip}: {e}")
        return []


def buscar_archivos_por_numero(numero_factura, ruta_busqueda=None):
    """Busca archivos que contengan el número de factura en su nombre."""
    if ruta_busqueda is None:
        ruta_busqueda = carpeta_origen
    
    try:
        # Buscar archivos que contengan el número en su nombre
        patron = os.path.join(ruta_busqueda, f"*{numero_factura}*")
        archivos = glob.glob(patron)
        return [os.path.basename(f) for f in archivos]
    except Exception as e:
        print(f"❌ Error al buscar archivos: {e}")
        return []


def obtener_url_pdf_de_numero(numero_factura, ruta_busqueda=None):
    """Busca archivo Response (con cualquier número) y extrae la URL del PDF."""
    if ruta_busqueda is None:
        ruta_busqueda = carpeta_origen
    
    try:
        # Patrón flexible para Response files: {numero_factura}_*_Response.txt
        patron = os.path.join(ruta_busqueda, f"{numero_factura}_*_Response.txt")
        archivos_response = glob.glob(patron)
        
        if not archivos_response:
            print(f"   ℹ️ No se encontró archivo Response para: {numero_factura}")
            return None
        
        # Procesar el primer archivo Response encontrado
        ruta_archivo = archivos_response[0]
        nombre_archivo = os.path.basename(ruta_archivo)
        print(f"   🔍 Leyendo archivo: {nombre_archivo}")
        
        with open(ruta_archivo, 'r', encoding='utf-8') as f:
            contenido = f.read().strip()
            try:
                datos = json.loads(contenido)
                # Buscar UrlPdf (case-sensitive)
                url_pdf = datos.get("UrlPdf")
                if url_pdf:
                    print(f"   ✅ UrlPdf encontrado en {nombre_archivo}")
                    return url_pdf
                else:
                    # Mostrar todas las claves disponibles para debug
                    print(f"   ⚠️ UrlPdf no encontrado. Claves disponibles: {list(datos.keys())}")
                    return None
            except json.JSONDecodeError as e:
                print(f"   ❌ JSON inválido en {nombre_archivo}: {e}")
                return None
    except Exception as e:
        print(f"❌ Error al obtener URL PDF: {e}")
        return None


def descargar_pdf(url_pdf, numero_factura):
    """Descarga un PDF desde una URL."""
    try:
        print(f"⬇️ Descargando PDF desde: {url_pdf}")
        response = requests.get(url_pdf, stream=True, timeout=30)
        response.raise_for_status()
        
        # Guardar temporalmente en memoria
        contenido_pdf = response.content
        print(f"✅ PDF descargado exitosamente ({len(contenido_pdf)} bytes)")
        return contenido_pdf
    except Exception as e:
        print(f"❌ Error descargando PDF: {e}")
        return None


def pdf_existe_en_zip(ruta_zip, numero_factura):
    """Verifica si el PDF ya existe en el ZIP."""
    try:
        nombre_pdf = f"FEV_830066626_{numero_factura}.pdf"
        ruta_dentro_zip = f"{numero_factura}/{nombre_pdf}"
        
        with zipfile.ZipFile(ruta_zip, 'r') as zip_ref:
            return ruta_dentro_zip in zip_ref.namelist()
    except Exception as e:
        print(f"❌ Error verificando PDF en ZIP: {e}")
        return False


def agregar_pdf_a_zip(ruta_zip, numero_factura, contenido_pdf):
    """Agrega un PDF al archivo ZIP dentro de la carpeta correspondiente."""
    try:
        nombre_pdf = f"FEV_830066626_{numero_factura}.pdf"
        ruta_dentro_zip = f"{numero_factura}/{nombre_pdf}"
        
        with zipfile.ZipFile(ruta_zip, 'a') as zip_ref:
            zip_ref.writestr(ruta_dentro_zip, contenido_pdf)
        
        print(f"✅ PDF agregado al ZIP en: {ruta_dentro_zip}")
        return True
    except Exception as e:
        print(f"❌ Error agregando PDF al ZIP: {e}")
        return False


if __name__ == "__main__":
    ruta_carpeta = r"C:\Facturas"
    archivos = listar_carpeta(ruta_carpeta)
    
    if archivos:
        print(f"✅ Se encontraron {len(archivos)} elementos en {ruta_carpeta}")
        for archivo in archivos:
            print(f"  📄 {archivo}")
        
        # Buscar y procesar ZIPs
        print("\n" + "="*50)
        zips = encontrar_zip(ruta_carpeta)
        if zips:
            print(f"✅ Se encontraron {len(zips)} archivo(s) ZIP")
            for zip_file in zips:
                ruta_zip = os.path.join(ruta_carpeta, zip_file)
                carpetas = obtener_html_de_zip(ruta_zip)
                print(f"\n📦 {zip_file}")
                if carpetas:
                    for carpeta in carpetas:
                        print(f"   📁 {carpeta}")
                        # Buscar archivos con ese número en la ruta compartida
                        archivos_encontrados = buscar_archivos_por_numero(carpeta)
                        if archivos_encontrados:
                            for archivo in archivos_encontrados:
                                print(f"      📄 {archivo}")
                        else:
                            print(f"      ℹ️ No hay archivos con ese número")
                        
                        # Obtener URL del PDF
                        url_pdf = obtener_url_pdf_de_numero(carpeta)
                        if url_pdf:
                            print(f"      🔗 PDF URL: {url_pdf}")
                            
                            # Verificar si el PDF ya existe en el ZIP
                            if pdf_existe_en_zip(ruta_zip, carpeta):
                                print(f"      ⏭️ PDF ya existe en el ZIP, omitiendo descarga")
                            else:
                                # Descargar PDF y agregarlo al ZIP
                                contenido_pdf = descargar_pdf(url_pdf, carpeta)
                                if contenido_pdf:
                                    agregar_pdf_a_zip(ruta_zip, carpeta, contenido_pdf)
                        else:
                            print(f"      ⚠️ No se encontró URL del PDF")
                else:
                    print(f"   ℹ️ No contiene carpetas")
        else:
            print("ℹ️ No hay archivos ZIP en la carpeta")
    else:
        print("ℹ️ No hay archivos o la carpeta no existe")