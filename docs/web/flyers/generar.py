"""Genera los 5 flyers de Koape RR. HH. para la página de proyectos de koapesystem.com.

Cada flyer es un HTML de 1200×800 (relación 3:2) con el logo oficial a la izquierda y los colores y tipografías
del Manual de Marca Koape Sistemas EAS 2026 (magenta #EA284E / #D9438D, amarillo #F9C610 / #ECF31A, oscuro #232323,
grises #97989C / #C9CACC; Exo 2 en títulos, Segoe UI en textos). Después se pasa a PNG con un navegador sin
ventana (Edge), al doble de resolución (2400×1600) para que se vea nítido.

    python generar.py            (deja flyer-1.png … flyer-5.png en esta carpeta)
"""
import pathlib
import random
import subprocess

AQUI = pathlib.Path(__file__).resolve().parent
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Exo+2:wght@500;600;700;800&display=swap');
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1200px; height: 800px; overflow: hidden; }
body { font-family: 'Segoe UI', Tahoma, sans-serif; color: #fff; background: #232323; position: relative; }
.fondo { position: absolute; inset: 0; background:
  radial-gradient(900px 600px at 105% -10%, rgba(234,40,78,.30), transparent 60%),
  radial-gradient(700px 500px at 110% 115%, rgba(249,198,16,.18), transparent 60%), #232323; }
.cubos { position: absolute; right: -120px; bottom: -140px; width: 620px; opacity: .06; }
.franja { position: absolute; left: 0; right: 0; bottom: 0; height: 10px;
  background: linear-gradient(90deg, #D9438D, #EA284E, #F7941D, #F9C610, #ECF31A); }
.izq { position: absolute; left: 64px; top: 56px; bottom: 56px; width: 500px; display: flex; flex-direction: column; }
.logo { height: 74px; width: auto; align-self: flex-start; }
.etiqueta { margin-top: 46px; display: inline-flex; align-self: flex-start; gap: 8px; align-items: center; padding: 6px 14px;
  border-radius: 999px; background: rgba(234,40,78,.16); color: #ff8aa1; font: 600 15px 'Segoe UI'; letter-spacing: .4px; text-transform: uppercase; }
h1 { margin-top: 18px; font: 800 52px/1.05 'Exo 2', sans-serif; letter-spacing: -.5px; }
h1 .acento { background: linear-gradient(90deg, #EA284E, #F7941D, #F9C610); -webkit-background-clip: text; background-clip: text; color: transparent; }
.bajada { margin-top: 18px; font-size: 20px; line-height: 1.45; color: #d6d6d8; }
ul { margin-top: 26px; list-style: none; display: grid; gap: 13px; }
li { display: flex; gap: 12px; align-items: flex-start; font-size: 17px; line-height: 1.35; color: #ececee; }
li .punto { flex: none; width: 26px; height: 26px; border-radius: 8px; display: grid; place-items: center; margin-top: -1px;
  background: linear-gradient(135deg, #EA284E, #F9C610); color: #232323; font: 800 15px 'Exo 2'; }
.pie { margin-top: auto; display: flex; align-items: center; gap: 14px; font: 600 17px 'Exo 2'; color: #fff; }
.pie .url { color: #F9C610; }
.pie .sep { width: 6px; height: 6px; border-radius: 50%; background: #97989C; }
.der { position: absolute; right: 60px; top: 60px; bottom: 60px; width: 520px; display: flex; align-items: center; justify-content: center; }
.tarjeta { background: #fff; color: #232323; border-radius: 22px; box-shadow: 0 30px 80px rgba(0,0,0,.45); overflow: hidden; }
.barra { height: 6px; background: linear-gradient(90deg, #D9438D, #EA284E, #F7941D, #F9C610); }
.t { font: 700 20px 'Exo 2'; color: #232323; }
.s { font-size: 13px; color: #6b6b70; }
.gris { color: #97989C; }
.chip { display: inline-block; padding: 3px 10px; border-radius: 999px; font: 600 12px 'Segoe UI'; }
.ok { background: #e7f6ec; color: #1f7a3d; } .pend { background: #fff4d6; color: #8a6200; } .mag { background: #fde4ea; color: #b8173a; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
td { padding: 8px 0; border-bottom: 1px solid #ececee; vertical-align: top; }
td.n { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap; }
.neg { color: #c4183c; }
"""


def pagina(numero, etiqueta, titulo, bajada, puntos, derecha):
    items = ''.join(f'<li><span class="punto">✓</span><span>{p}</span></li>' for p in puntos)
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Koape RR. HH. — flyer {numero}</title>
<style>{CSS}</style></head><body>
<div class="fondo"></div><img class="cubos" src="logo-color.png" alt="">
<section class="izq">
  <img class="logo" src="logo-blanco.png" alt="Koape Sistemas EAS">
  <span class="etiqueta">{etiqueta}</span>
  <h1>{titulo}</h1>
  <p class="bajada">{bajada}</p>
  <ul>{items}</ul>
  <div class="pie"><span>Koape RR. HH.</span><span class="sep"></span><span class="url">rrhh.koapesystem.com</span></div>
</section>
<section class="der">{derecha}</section>
<div class="franja"></div>
</body></html>"""


def qr(semilla, lado=25, celda=9):
    """Un QR ilustrativo (no se escanea): marcas de esquina y módulos al azar."""
    r = random.Random(semilla)
    rects = []
    for fila in range(lado):
        for col in range(lado):
            esquina = (fila < 7 and col < 7) or (fila < 7 and col >= lado - 7) or (fila >= lado - 7 and col < 7)
            if esquina:
                f, c = fila % (lado - 7) if fila >= 7 else fila, col % (lado - 7) if col >= 7 else col
                lleno = f in (0, 6) or c in (0, 6) or (2 <= f <= 4 and 2 <= c <= 4)
            else:
                lleno = r.random() < 0.48
            if lleno:
                rects.append(f'<rect x="{col * celda}" y="{fila * celda}" width="{celda}" height="{celda}"/>')
    tam = lado * celda
    return f'<svg width="{tam}" height="{tam}" viewBox="0 0 {tam} {tam}" fill="#232323">{"".join(rects)}</svg>'


PANEL = """
<div class="tarjeta" style="width:500px">
  <div class="barra"></div>
  <div style="padding:22px 24px">
    <div style="display:flex;justify-content:space-between;align-items:center"><span class="t">Panel</span><span class="s">Empresa Demo S.A. · octubre 2026</span></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px">
      <div style="border:1px solid #ececee;border-radius:14px;padding:14px"><div class="s">Empleados activos</div><div style="font:800 30px 'Exo 2'">15</div></div>
      <div style="border:1px solid #ececee;border-radius:14px;padding:14px"><div class="s">Presentes hoy</div><div style="font:800 30px 'Exo 2';color:#1f7a3d">93 %</div></div>
      <div style="border:1px solid #ececee;border-radius:14px;padding:14px"><div class="s">Nómina de septiembre</div><div style="font:800 22px 'Exo 2'">Gs. 70.927.745</div><span class="chip ok">Cerrada · recibos publicados</span></div>
      <div style="border:1px solid #ececee;border-radius:14px;padding:14px"><div class="s">Para aprobar</div><div style="font:800 30px 'Exo 2';color:#EA284E">4</div><div class="s">vacaciones · anticipo · ajuste · comisión</div></div>
    </div>
    <div class="s" style="margin-top:18px">Horas trabajadas por mes</div>
    <div style="display:flex;align-items:flex-end;gap:9px;height:110px;margin-top:8px">
      """ + ''.join(f'<div style="flex:1;height:{h}%;border-radius:6px 6px 0 0;background:linear-gradient(180deg,#EA284E,#F9C610)"></div>'
                    for h in (62, 70, 66, 78, 74, 81, 76, 88, 84, 92, 87, 95)) + """
    </div>
  </div>
</div>"""

TERMINAL = f"""
<div style="position:relative;width:520px;height:600px">
  <div class="tarjeta" style="position:absolute;left:0;top:30px;width:360px;padding:0">
    <div class="barra"></div>
    <div style="padding:20px;text-align:center">
      <div class="t">Terminal · Entrada principal</div>
      <div class="s">Escaneá con tu celular · cambia cada 20 s</div>
      <div style="margin:16px auto 6px;padding:12px;border:1px solid #ececee;border-radius:14px;display:inline-block">{qr(7)}</div>
      <div style="font:700 34px 'Exo 2';letter-spacing:1px">07:58:12</div>
      <div class="s">martes 14 de octubre</div>
    </div>
  </div>
  <div style="position:absolute;right:0;bottom:0;width:220px;height:440px;border-radius:34px;background:#111;padding:12px;box-shadow:0 30px 70px rgba(0,0,0,.5)">
    <div style="width:100%;height:100%;border-radius:24px;background:#fff;color:#232323;overflow:hidden;display:flex;flex-direction:column;align-items:center">
      <div class="barra" style="width:100%"></div>
      <div style="margin-top:34px;width:76px;height:76px;border-radius:50%;background:linear-gradient(135deg,#D9438D,#F9C610);display:grid;place-items:center;font:800 28px 'Exo 2';color:#fff">LM</div>
      <div style="margin-top:14px;font:700 17px 'Exo 2'">Lucía Martínez</div>
      <div class="s">Legajo E003</div>
      <div style="margin-top:18px;width:58px;height:58px;border-radius:50%;background:#e7f6ec;display:grid;place-items:center;color:#1f7a3d;font:800 30px 'Exo 2'">✓</div>
      <div style="margin-top:10px;font:700 18px 'Exo 2';color:#1f7a3d">Entrada registrada</div>
      <div style="font:700 26px 'Exo 2';margin-top:4px">07:58:12</div>
      <div class="s" style="padding:0 16px;text-align:center;margin-top:8px">Hora del servidor · QR de un solo uso</div>
    </div>
  </div>
</div>"""

LINEAS = [('Sueldo', 'Sueldo mensual 3.800.000 / 30 días × 30 días pagados', '3.800.000'),
          ('Horas extra diurnas', '2 h autorizadas × 15.833 × 1,5 (recargo 50 %)', '47.499'),
          ('Comisión', 'Ventas 42.000.000 × 2 %', '840.000'),
          ('Premio por presentismo', 'Novedad aprobada', '150.000'),
          ('Aporte IPS', 'Base IPS 4.837.499 × 9 %', '-435.375'),
          ('Cuota de préstamo', 'Cuota 4 de 9 (préstamo del 06/10/2025)', '-500.000')]
RECIBO = """
<div class="tarjeta" style="width:520px">
  <div class="barra"></div>
  <div style="padding:20px 24px">
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <div><div class="t">Recibo de sueldo</div><div class="s">Lucía Martínez · Legajo E003 · septiembre 2026</div></div>
      <span class="chip ok">R2026-000412</span>
    </div>
    <table style="margin-top:12px">""" + ''.join(
    f'<tr><td><b>{c}</b><div class="s">{e}</div></td><td class="n {"neg" if v.startswith("-") else ""}">{v}</td></tr>' for c, e, v in LINEAS) + """
    </table>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:14px">
      <span class="s">Cada línea dice cómo se calculó</span>
      <span style="font:800 24px 'Exo 2'">Neto Gs. 3.902.124</span>
    </div>
  </div>
</div>"""

CELULAR = """
<div style="position:relative;width:520px;height:620px">
  <div style="position:absolute;left:10px;top:0;width:290px;height:600px;border-radius:40px;background:#111;padding:13px;box-shadow:0 30px 70px rgba(0,0,0,.5)">
    <div style="width:100%;height:100%;border-radius:30px;background:#f5f5f4;color:#232323;overflow:hidden">
      <div class="barra"></div>
      <div style="padding:18px">
        <div class="t" style="font-size:19px">Mis licencias</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px">
          <div style="background:#fff;border-radius:12px;padding:10px"><div style="font:800 26px 'Exo 2';color:#EA284E">12</div><div class="s">días disponibles</div></div>
          <div style="background:#fff;border-radius:12px;padding:10px"><div style="font:800 26px 'Exo 2'">6</div><div class="s">tomados este año</div></div>
        </div>
        <div style="margin-top:12px;background:linear-gradient(90deg,#EA284E,#F7941D);color:#fff;border-radius:12px;padding:11px;text-align:center;font:700 14px 'Exo 2'">+ Pedir vacaciones o permiso</div>
        <div style="margin-top:14px;display:grid;gap:8px">
          <div style="background:#fff;border-radius:12px;padding:10px"><b style="font-size:13px">Vacaciones · 16 al 20/11</b><br><span class="chip pend">Pendiente</span></div>
          <div style="background:#fff;border-radius:12px;padding:10px"><b style="font-size:13px">Permiso por horas · 08:00–10:00</b><br><span class="chip ok">Aprobada</span></div>
          <div style="background:#fff;border-radius:12px;padding:10px"><b style="font-size:13px">Reposo médico · 2 días</b><br><span class="chip ok">Aprobada · con certificado</span></div>
        </div>
        <div class="t" style="font-size:16px;margin-top:16px">Mis recibos</div>
        <div style="margin-top:8px;display:grid;gap:8px">
          <div style="background:#fff;border-radius:12px;padding:10px;display:flex;justify-content:space-between;font-size:13px"><b>Septiembre 2026</b><b>Gs. 3.902.124</b></div>
          <div style="background:#fff;border-radius:12px;padding:10px;display:flex;justify-content:space-between;font-size:13px"><b>Agosto 2026</b><b>Gs. 3.871.540</b></div>
        </div>
      </div>
    </div>
  </div>
  <div class="tarjeta" style="position:absolute;right:0;top:120px;width:250px">
    <div class="barra"></div>
    <div style="padding:16px">
      <div class="t" style="font-size:17px">Desde el celular</div>
      <div style="display:grid;gap:9px;margin-top:10px;font-size:14px">
        <div>✓ Marcar entrada y salida</div><div>✓ Ver mi asistencia</div><div>✓ Mis recibos en PDF</div>
        <div>✓ Pedir licencias</div><div>✓ Pedir anticipos</div><div>✓ Corregir una marca</div>
      </div>
    </div>
  </div>
</div>"""

MULTI = """
<div style="position:relative;width:520px;height:600px">
  <div class="tarjeta" style="position:absolute;left:0;top:10px;width:470px">
    <div style="background:#ececee;padding:10px 14px;display:flex;gap:8px;align-items:center">
      <span style="width:11px;height:11px;border-radius:50%;background:#EA284E"></span><span style="width:11px;height:11px;border-radius:50%;background:#F9C610"></span>
      <span style="width:11px;height:11px;border-radius:50%;background:#C9CACC"></span>
      <span style="margin-left:10px;background:#fff;border-radius:8px;padding:5px 12px;font-size:13px;color:#232323">🔒 rrhh.koapesystem.com/<b style="color:#1d4ed8">delacosta</b></span>
    </div>
    <div style="display:flex">
      <div style="width:150px;background:#1e3a8a;color:#fff;padding:18px;font:700 16px 'Exo 2'">De la Costa<div style="font:400 12px 'Segoe UI';opacity:.8;margin-top:8px">Su logo y sus colores</div></div>
      <div style="flex:1;padding:20px">
        <div class="t" style="font-size:18px">Ingresar</div><div class="s">Usá tu usuario de De la Costa</div>
        <div style="margin-top:12px;height:34px;border:1px solid #C9CACC;border-radius:8px"></div>
        <div style="margin-top:10px;height:34px;border:1px solid #C9CACC;border-radius:8px"></div>
        <div style="margin-top:12px;height:36px;border-radius:8px;background:#1e3a8a"></div>
      </div>
    </div>
  </div>
  <div class="tarjeta" style="position:absolute;right:0;bottom:20px;width:330px">
    <div class="barra"></div>
    <div style="padding:16px;display:grid;gap:10px;font-size:14px">
      <div style="display:flex;justify-content:space-between"><b>Planilla IPS · septiembre</b><span class="chip ok">Presentada</span></div>
      <div style="display:flex;justify-content:space-between"><b>MTESS sueldos y jornales</b><span class="chip ok">Presentada</span></div>
      <div style="display:flex;justify-content:space-between"><b>Reglas legales PY-LABORAL</b><span class="chip mag">Aprobadas · v2</span></div>
      <div style="display:flex;justify-content:space-between"><b>Auditoría</b><span class="s">quién, qué y cuándo</span></div>
    </div>
  </div>
</div>"""

FLYERS = [
    ('Producto Koape', 'Recursos humanos<br>y nómina, <span class="acento">en un solo lugar</span>',
     'Sistema web para empresas de Paraguay: del legajo al recibo de sueldo, con cada número explicado.',
     ['Legajos, contratos, sueldos y documentos', 'Asistencia, licencias y vacaciones', 'Nómina, aguinaldo, liquidación final y costo patronal',
      'Planillas para IPS y MTESS'], PANEL),
    ('Asistencia', 'Marcación con <span class="acento">QR dinámico</span>',
     'La terminal muestra un QR que cambia solo; el empleado lo escanea con su celular y la marca queda al instante.',
     ['QR de un solo uso: una foto reenviada no sirve', 'Ambas pantallas confirman legajo, nombre, hora y foto', 'También código fijo y relojes externos por archivo',
      'Tardanzas, horas extra y ausencias calculadas solas'], TERMINAL),
    ('Nómina', 'Una nómina que <span class="acento">se explica sola</span>',
     'Cada línea del recibo dice de dónde sale: base, cantidad, tasa y regla aplicada.',
     ['Comisiones, bonos, anticipos y préstamos con cuotas', 'Revisar, aprobar y cerrar, con rectificaciones', 'Recibos numerados y pagos por transferencia',
      'Aguinaldo y liquidación final según la causal'], RECIBO),
    ('Autogestión', 'Cada empleado, <span class="acento">con lo suyo</span>',
     'El empleado ve su asistencia y sus recibos, y pide permisos sin papeles. RR. HH. aprueba con un toque.',
     ['Saldo de vacaciones siempre al día', 'Pedidos que quedan pendientes hasta aprobarse', 'Certificados médicos en el legajo',
      'Solo ve sus propios datos'], CELULAR),
    ('Multiempresa y cumplimiento', 'Tu empresa, <span class="acento">tu dirección y tu marca</span>',
     'Cada empresa entra por su propia dirección, con su logo y sus colores, y ve solo sus datos.',
     ['Perfiles: administrador, gestor de RR. HH. y empleado', 'Reglas legales con fuente, vigencia y aprobación', 'Planillas IPS y MTESS validadas y exportables',
      'Auditoría de cada cambio'], MULTI),
]

for numero, (etiqueta, titulo, bajada, puntos, derecha) in enumerate(FLYERS, start=1):
    html = AQUI / f'flyer-{numero}.html'
    html.write_text(pagina(numero, etiqueta, titulo, bajada, puntos, derecha), encoding='utf-8')
    png = AQUI / f'flyer-{numero}.png'
    subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=2',
                    '--window-size=1200,800', '--virtual-time-budget=6000', f'--screenshot={png}', html.as_uri()],
                   check=True, capture_output=True)
    print('listo:', png.name)
