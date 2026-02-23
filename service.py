from flask import Flask, request, Response, stream_with_context, send_file
import os, json, zipfile, io
import requests as http_requests
from requests.adapters import HTTPAdapter
from datetime import datetime

app = Flask(__name__)

CARPETA_ORIGEN = r"\\sv-sys-05\Hosvi_Anex_Fact\FACTURAS"
PREFIX_PDF = "FEV_830066626_"
WEBHOOK_URL = "https://n8n.medihelpservices.com/webhook-test/8f5dc3f2-4066-4497-a65d-5b9b50c0f2bd"


@app.route("/")
def home():
    try:
        here = os.path.dirname(__file__)
        return send_file(os.path.join(here, 'templates', 'upload.html'))
    except Exception:
        return "UI no disponible", 500


def construir_indice_responses():
    indice = {}
    try:
        for entry in os.scandir(CARPETA_ORIGEN):
            if entry.is_file() and entry.name.endswith('_Response.txt'):
                numero = entry.name.split('_')[0]
                if numero and numero not in indice:
                    indice[numero] = entry.path
    except Exception:
        pass
    return indice


def buscar_url_pdf(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == 'urlpdf' and v:
                return v
            res = buscar_url_pdf(v)
            if res:
                return res
    elif isinstance(obj, list):
        for item in obj:
            res = buscar_url_pdf(item)
            if res:
                return res
    return None


def descargar_pdf(url, session):
    try:
        resp = session.get(url, stream=True, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def enviar_al_webhook(factura, archivos_list):
    """Envía N archivos + factura al webhook. Retorna (ok, mensaje)."""
    fields = [('factura', (None, factura))]
    for i, (nombre, contenido, mime) in enumerate(archivos_list):
        fields.append((f'file_{i}', (nombre, contenido, mime)))
    resp = http_requests.post(WEBHOOK_URL, files=fields, timeout=120)
    if resp.ok:
        return True, f'Webhook OK (status {resp.status_code})'
    return False, f'Webhook error: {resp.status_code} - {resp.text[:200]}'


def extraer_facturas_de_zip(zip_bytes):
    """Extrae las carpetas de un ZIP. Retorna dict {numero_factura: [(nombre, bytes, mime), ...]}"""
    facturas = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            parts = info.filename.split('/')
            if len(parts) >= 2:
                carpeta = parts[0]
                nombre_archivo = parts[-1]
                if not nombre_archivo:
                    continue
                if carpeta not in facturas:
                    facturas[carpeta] = []
                ext = nombre_archivo.split('.')[-1].lower()
                mime_map = {'json': 'application/json', 'xml': 'text/xml', 'pdf': 'application/pdf'}
                mime = mime_map.get(ext, 'application/octet-stream')
                facturas[carpeta].append((nombre_archivo, z.read(info.filename), mime))
    return facturas


@app.route('/upload', methods=['POST'])
def upload():
    factura_manual = request.form.get('factura', '').strip()

    archivos_raw = []
    for key in request.files:
        f = request.files[key]
        archivos_raw.append({
            'filename': f.filename,
            'content': f.read(),
            'content_type': f.content_type or 'application/octet-stream'
        })

    if not archivos_raw:
        return Response(json.dumps({'type': 'log', 'msg': 'ERROR: No se recibieron archivos', 'progress': 0}) + '\n',
                        mimetype='application/x-ndjson', status=400)

    zips = [a for a in archivos_raw if a['filename'].lower().endswith('.zip')]
    sueltos = [a for a in archivos_raw if not a['filename'].lower().endswith('.zip')]

    def gen():
        inicio = datetime.now()

        def elapsed():
            s = (datetime.now() - inicio).total_seconds()
            return f"{int(s // 60):02d}:{int(s % 60):02d}"

        def log(msg, progress=0):
            return json.dumps({'type': 'log', 'msg': f'[{elapsed()}] {msg}', 'progress': progress}) + '\n'

        yield log(f'Recibidos {len(archivos_raw)} archivo(s): {len(zips)} ZIP(s), {len(sueltos)} suelto(s)', 5)

        session = http_requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        response_index = None
        total_envios = 0
        envios_ok = 0

        try:
            # === CASO 1: Archivos sueltos (ya descomprimidos, 4 archivos por factura) ===
            if sueltos:
                if not factura_manual:
                    yield log('ERROR: Archivos sueltos requieren número de factura', 0)
                else:
                    yield log(f'Enviando {len(sueltos)} archivo(s) sueltos para factura {factura_manual}...', 15)
                    archivos_list = [(a['filename'], a['content'], a['content_type']) for a in sueltos]

                    for nombre, _, _ in archivos_list:
                        yield log(f'  → {nombre}', 20)

                    yield log('Enviando al webhook...', 40)
                    total_envios += 1
                    ok, msg = enviar_al_webhook(factura_manual, archivos_list)
                    if ok:
                        envios_ok += 1
                        yield log(f'Factura {factura_manual}: {msg}', 50)
                    else:
                        yield log(f'Factura {factura_manual}: {msg}', 50)

            # === CASO 2: ZIPs (extraer carpetas, descargar PDF, enviar 4 archivos por factura) ===
            if zips:
                if response_index is None:
                    yield log('Indexando archivos Response en la red...', 55)
                    response_index = construir_indice_responses()
                    yield log(f'Índice listo: {len(response_index)} Response(s)', 58)

                for z_idx, z_file in enumerate(zips):
                    yield log(f'Procesando ZIP: {z_file["filename"]}', 60)

                    try:
                        facturas = extraer_facturas_de_zip(z_file['content'])
                    except Exception as e:
                        yield log(f'ERROR extrayendo ZIP {z_file["filename"]}: {e}', 60)
                        continue

                    yield log(f'  {len(facturas)} factura(s) encontrada(s) en {z_file["filename"]}', 62)

                    for f_idx, (num_factura, archivos_factura) in enumerate(sorted(facturas.items())):
                        progress_base = 62 + int(((z_idx * len(facturas) + f_idx) / max(len(zips) * max(len(facturas), 1), 1)) * 30)

                        ya_tiene_pdf = any(n.lower().startswith(PREFIX_PDF.lower()) and n.lower().endswith('.pdf') for n, _, _ in archivos_factura)

                        if ya_tiene_pdf:
                            yield log(f'  Factura {num_factura}: PDF ya incluido ({len(archivos_factura)} archivos)', progress_base)
                        else:
                            # Buscar Response y descargar PDF
                            ruta_response = response_index.get(num_factura)
                            if ruta_response:
                                try:
                                    with open(ruta_response, 'r', encoding='utf-8') as rf:
                                        datos = json.loads(rf.read().strip())
                                    url_pdf = buscar_url_pdf(datos)
                                    if url_pdf:
                                        pdf_bytes = descargar_pdf(url_pdf, session)
                                        if pdf_bytes:
                                            pdf_name = f'{PREFIX_PDF}{num_factura}.pdf'
                                            archivos_factura.append((pdf_name, pdf_bytes, 'application/pdf'))
                                            yield log(f'  Factura {num_factura}: PDF descargado OK', progress_base)
                                        else:
                                            yield log(f'  Factura {num_factura}: FAIL descargando PDF', progress_base)
                                    else:
                                        yield log(f'  Factura {num_factura}: UrlPdf no encontrado en Response', progress_base)
                                except Exception as e:
                                    yield log(f'  Factura {num_factura}: ERROR leyendo Response: {e}', progress_base)
                            else:
                                yield log(f'  Factura {num_factura}: sin Response en la red', progress_base)

                        # Enviar los archivos de esta factura al webhook
                        yield log(f'  Factura {num_factura}: enviando {len(archivos_factura)} archivo(s)...', progress_base + 2)
                        total_envios += 1
                        try:
                            ok, msg = enviar_al_webhook(num_factura, archivos_factura)
                            if ok:
                                envios_ok += 1
                                yield log(f'  Factura {num_factura}: {msg}', progress_base + 4)
                            else:
                                yield log(f'  Factura {num_factura}: {msg}', progress_base + 4)
                        except Exception as e:
                            yield log(f'  Factura {num_factura}: ERROR envío: {e}', progress_base + 4)

        finally:
            session.close()

        resumen = f'Completado: {envios_ok}/{total_envios} envío(s) exitoso(s)'
        yield json.dumps({'type': 'done', 'msg': f'[{elapsed()}] {resumen}', 'progress': 100}) + '\n'

    return Response(stream_with_context(gen()), mimetype='application/x-ndjson')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
