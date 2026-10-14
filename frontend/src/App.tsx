import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { SesionProvider } from './services/SesionProvider'
import Diseno from './components/Diseno'
import Ingreso from './pages/Ingreso'
import Panel from './pages/Panel'
import Listado from './pages/Listado'
import Formulario from './pages/Formulario'
import MiFicha from './pages/MiFicha'
import Manual from './pages/Manual'
// Las pantallas con QR (librerías pesadas) se cargan recién cuando se abren.
const MiMarcacion = lazy(() => import('./pages/MiMarcacion'))
const Terminal = lazy(() => import('./pages/Terminal'))
import ConfiguracionMarcador from './pages/ConfiguracionMarcador'
import ImportarMarcaciones from './pages/ImportarMarcaciones'
import LoteImportacion from './pages/LoteImportacion'
import AsistenciaDiaria from './pages/AsistenciaDiaria'
import DiaAsistencia from './pages/DiaAsistencia'
import MiAsistencia from './pages/MiAsistencia'
import Vacaciones from './pages/Vacaciones'
import MisLicencias from './pages/MisLicencias'
import ParametrosVigentes from './pages/ParametrosVigentes'
import MisMovimientos from './pages/MisMovimientos'
import NuevaLiquidacion from './pages/NuevaLiquidacion'
import CorridaNomina from './pages/CorridaNomina'
import ReciboSueldo from './pages/ReciboSueldo'
import CostoPatronal from './pages/CostoPatronal'
import MisRecibos from './pages/MisRecibos'
import PlanillaOficial from './pages/PlanillaOficial'
import Reportes from './pages/Reportes'

export default function App() {
  return (
    <SesionProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="fondo-app flex items-center justify-center text-stone-500">Cargando…</div>}>
        <Routes>
          <Route path="/ingresar" element={<Ingreso />} />
          {/* Terminal de marcación: sin usuario, se autentica con la clave de la terminal. */}
          <Route path="/terminal" element={<Terminal />} />
          <Route element={<Diseno />}>
            <Route index element={<Panel />} />
            <Route path="/mi-ficha" element={<MiFicha />} />
            <Route path="/mi-marcacion" element={<MiMarcacion />} />
            {/* Enlace que lleva el QR de la terminal: lo abre la cámara normal del teléfono. */}
            <Route path="/marcar/:token" element={<MiMarcacion />} />
            <Route path="/asistencia/configuracion" element={<ConfiguracionMarcador />} />
            <Route path="/asistencia/importar" element={<ImportarMarcaciones />} />
            <Route path="/asistencia/importaciones/:id" element={<LoteImportacion />} />
            <Route path="/asistencia/dias" element={<AsistenciaDiaria />} />
            <Route path="/asistencia/dias/:id" element={<DiaAsistencia />} />
            <Route path="/mi-asistencia" element={<MiAsistencia />} />
            <Route path="/vacaciones" element={<Vacaciones />} />
            <Route path="/mis-licencias" element={<MisLicencias />} />
            <Route path="/nomina/parametros" element={<ParametrosVigentes />} />
            <Route path="/mis-movimientos" element={<MisMovimientos />} />
            <Route path="/nomina/liquidar" element={<NuevaLiquidacion />} />
            <Route path="/nomina/liquidaciones/:id" element={<CorridaNomina />} />
            <Route path="/nomina/costo" element={<CostoPatronal />} />
            <Route path="/recibos/:id" element={<ReciboSueldo />} />
            <Route path="/mis-recibos" element={<MisRecibos />} />
            <Route path="/nomina/planillas/:id" element={<PlanillaOficial />} />
            <Route path="/reportes" element={<Reportes />} />
            {/* Manual de usuario: solo con sesión iniciada. */}
            <Route path="/manual" element={<Manual />} />
            <Route path="/m/:clave" element={<Listado />} />
            <Route path="/m/:clave/nuevo" element={<Formulario />} />
            <Route path="/m/:clave/:id" element={<Formulario />} />
          </Route>
          {/* Ingreso propio de cada empresa: hhrr.koapesystem.com/<dirección> (las rutas fijas de arriba tienen prioridad). */}
          <Route path="/:direccion" element={<Ingreso />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </BrowserRouter>
    </SesionProvider>
  )
}
