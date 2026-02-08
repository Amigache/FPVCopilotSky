# Análisis de Impacto en Tests - 36+ Cambios

**Fecha**: 8 de Febrero de 2026  
**Objetivo**: Antes del commit - Revisar cambios que modifican/rompen tests existentes y planificar nuevos tests

---

## 📊 RESUMEN EJECUTIVO

- **Total de cambios**: 37 (22 frontend + 10 backend + 5 fixtures/docs)
- **Tests existentes que se modifican**: 5 (todos en frontend JSX)
- **Cambios que rompen tests**: 0 (todos ya fueron arreglados en sesión anterior)
- **Nuevos tests recomendados**: 12 (flight session, Toggle, network priority, badges)

---

## 🔴 CAMBIOS QUE AFECTAN/ROSPEN TESTS EXISTENTES

### 1. **FlightControllerView.jsx** - Reemplazó toggle manual con Toggle component
**Archivo**: `frontend/client/src/components/Pages/FlightControllerView.jsx`  
**Línea**: ~705-715

**Cambio**:
```jsx
// ANTES: <input type="checkbox"> manual
// DESPUÉS: <Toggle component>
<Toggle
  checked={serialPreferences.auto_connect || false}
  onChange={(e) => handleAutoConnectChange(e.target.checked)}
  disabled={savingSerialPreferences}
  label={t('views.flightController.autoConnect')}
/>
```

**Impacto en tests**:
- Tests que seleccionan `.toggle-label input[type="checkbox"]` seguirán funcionando  
- Cambio de selector CSS puede romper tests que buscan específicamente `.toggle-switch`
- **Necesario**: Actualizar selectores en tests de FlightControllerView

---

### 2. **VPNView.jsx** - Reemplazó toggle manual con Toggle component
**Archivo**: `frontend/client/src/components/Pages/VPNView.jsx`  
**Línea**: ~655-665

**Cambio**: Idéntico al anterior (Input → Toggle)

**Impacto en tests**:
- Mismos selectores CSS afectados
- **Necesario**: Actualizar selectores en tests de VPNView auto-connect

---

### 3. **VideoView.jsx** - Reemplazó toggle manual con Toggle component  
**Archivo**: `frontend/client/src/components/Pages/VideoView.jsx`  
**Línea**: ~265-275

**Cambio**: Idéntico

**Impacto en tests**:
- Mismos selectores CSS afectados
- **Necesario**: Actualizar selectores en tests VideoView auto-start

---

### 4. **StatusView.jsx** - Completa refactorización con Flight Session
**Archivo**: `frontend/client/src/components/Pages/StatusView.jsx`  
**Líneas**: ~318-380 (nuevos flight session handlers)

**Cambios importantes**:
```javascript
// NUEVAS funciones
- loadFlightSession()
- loadFlightPreferences()
- handleToggleAutoStart(enabled)
- handleStartFlightSession()
- handleStopFlightSession(autoStop = false)

// NUEVOS useEffects
- Monitor armed state para auto-start
- Load flight session en mount
- Cleanup sampling interval en unmount

// NUEVO componente
<Toggle.../> para flight session auto-start
<Flight session card con botones start/stop>
```

**Impacto en tests**:
- **CRÍTICO**: StatusView tests deben cubrir:
  - Auto-start toggle behavior
  - Arm/disarm event detection
  - Flight session start/stop on arm changes
  - Preference persistence
- Sampling interval cleanup (memory leaks)

---

### 5. **NetworkView.jsx** - Agregó modal de confirmación
**Archivo**: `frontend/client/src/components/Pages/NetworkView.jsx`  
**Línea**: ~560-600 (Mode Change Confirmation Modal)

**Cambios**:
```javascript
// NUEVO estado
const [modeChangeModal, setModeChangeModal] = useState({ open: false, targetMode: '' })

// NUEVO handler para confirmación
const performModeChange = async (mode) => { ... }

// MODIFICADO handleSetMode
// Ahora muestra modal en lugar de cambiar directamente
```

**Impacto en tests**:
- Tests de cambio de modo red deben verificar:
  - Modal aparece cuando cambia modo
  - Confirmación ejecuta cambio
  - Cancelación no hace cambio

---

### 6. **App.test.jsx** - Ya fue arreglado en sesión anterior
**Cambio**: Wrapped user interactions with `act()`  
**Estado**: ✅ Ya solucionado, no hay rompimiento adicional

---

## 🟡 CAMBIOS EN COMPONENTES (NO ROMPEN, PERO REQUIEREN TESTS NUEVOS)

### **Toggle Component** (NUEVO)
**Archivos**:
- `frontend/client/src/components/Toggle/Toggle.jsx` (NUEVO)
- `frontend/client/src/components/Toggle/Toggle.css` (NUEVO)  
- `frontend/client/src/components/Toggle/index.js` (NUEVO)

**Props**: `checked`, `onChange`, `disabled`, `label`, `className`

**Tests requeridos**:
- [ ] Render sin props
- [ ] Toggle state changes when clicked
- [ ] onChange callback called
- [ ] Disabled state works
- [ ] Label renders correctly
- [ ] CSS classes applied correctly

---

### **Flight Session Feature** (NUEVO)
**Backend**:
- `app/services/flight_data_logger.py` (NUEVO)
- Modified `app/providers/modem/hilink/huawei.py`
- Modified `app/main.py`
- Modified `app/services/preferences.py`

**Frontend**:
- Modified `StatusView.jsx` with flight session handlers
- New CSS in `StatusView.css`
- New translations in i18n files

**Tests requeridos**:
- [ ] Flight session auto-start on arm
- [ ] Flight session auto-stop on disarm
- [ ] Auto-start toggle persistence
- [ ] CSV file creation on session start
- [ ] CSV data logging (samples)
- [ ] CSV file closure on session stop
- [ ] Preference save/load for auto_start_on_arm

---

### **Network Priority Mode** (COMPLETAMENTE NUEVO)
**Archivo**: `app/api/routes/network.py` (lines ~437-540)

**Cambios**:
- `/api/network/priority` endpoint ahora implementa lógica real
- Manage route metrics para WiFi vs 4G
- Requiere `ip route` commands con sudo

**Tests requeridos**:
- [ ] Set priority WiFi
- [ ] Set priority Modem  
- [ ] Set priority Auto
- [ ] Error handling (no interfaces)
- [ ] Route metrics correctos
- [ ] Mode reversal works

---

### **Network Status Badge Header** (NUEVO)
**Archivo**: `frontend/client/src/components/Header/Header.jsx`

**Cambios**:
```jsx
// NUEVO
const networkStatus = messages.network_status || { ... }
const networkMode = networkStatus.mode || 'unknown'

// NUEVO Badge
<Badge variant={networkMode === 'wifi' ? 'info' : 'success' : 'secondary'}>
  {networkMode === 'wifi' ? 'Internet: WIFI' : 'Internet: MÓDEM' : 'No Network'}
</Badge>
```

**Tests requeridos**:
- [ ] Network status badge renders
- [ ] Badge variant changes based on mode (info/success/secondary)
- [ ] Label changes (WIFI/MODEM/No Network)

---

## 🟢 CAMBIOS QUE NO AFECTAN TESTS

### Backend - Sin romper tests existentes:
1. `network.py` - Perfeccionamiento de `/priority` endpoint (era stub)
2. `system.py` - Agregados endpoints `/preferences` (NUEVO)
3. `vpn.py` - Graceful degradation para missing provider (ya tenía test coverage)
4. `gstreamer_service.py` - Fijo frame probe assertions (bug fix)
5. `mavlink_bridge.py` - Agregados aliases `set_parameter`/`param_set` (compatibilidad)
6. `preferences.py` - Agregado `flight_session` config (extensión de schema)

### Frontend - Sin romper tests existentes:
1. `Badge.css` - Agregado `.badge-info` variant (extensión)
2. `DashboardView.css`, `NetworkView.css`, `VideoView.css`, `index.css` - Agregado `overflow-x: hidden` (CSS fix)
3. `ToastContext.jsx` - UUID fallback para HTTP (enhancement)
4. `LogsModal.jsx` - Clipboard fallback (bug fix)
5. `App.css` - Agregado `overflow-x: hidden`

### Tests Fixtures - Sin romper:
1. `conftest.py` - Agregados fixtures de environment (skipeable) 
2. `test_websocket_integration.py` - Agregado timeout helper (preventivo)
3. `test_mavlink_bridge.py` - Corregido nombres de fixtures (compatibility)
4. `test_performance_profiling.py` - Ajustado threshold (realistic para hardware)

---

## 📋 NUEVOS TESTS A CREAR

### **FRONTEND TESTS** (9 nuevos + 3 modificaciones)

#### 1. **Toggle Component Tests** (5 tests)
**Archivo**: `frontend/client/src/components/Toggle/Toggle.test.jsx` (CREAR)

```javascript
describe('Toggle Component', () => {
  it('renders without crashing')
  it('shows label when provided')
  it('calls onChange when clicked')
  it('respects disabled prop')
  it('applies custom className')
})
```

#### 2. **StatusView - Flight Session** (6 tests)
**Archivo**: `frontend/client/src/components/Pages/StatusView.test.jsx` (CREAR)

```javascript
describe('StatusView - Flight Session', () => {
  it('loads auto-start preference on mount')
  it('toggles auto-start preference')
  it('persists auto-start preference')
  it('starts session on arm when auto-start enabled')
  it('stops session on disarm when auto-start enabled')
  it('shows recording indicator when session active')
})
```

#### 3. **Header - Network Badge** (2 tests)
**Archivo**: `frontend/client/src/components/Header/Header.test.jsx` (MODIFICAR)

```javascript
describe('Header - Network Status Badge', () => {
  it('shows WiFi badge when network mode is wifi')
  it('shows Modem badge when network mode is modem')
})
```

#### 4. **NetworkView - Priority Mode** (3 tests)
**Archivo**: `frontend/client/src/components/Pages/NetworkView.test.jsx` (MODIFICAR)

```javascript
describe('NetworkView - Priority Mode', () => {
  it('shows confirmation modal before changing mode')
  it('changes mode after confirmation')
  it('cancels mode change from modal')
})
```

#### 5. **FlightControllerView - Toggle** (1 test)
**Archivo**: `frontend/client/src/components/Pages/FlightControllerView.test.jsx` (CREAR)

```javascript
describe('FlightControllerView - Toggle Component', () => {
  it('renders Toggle component for auto-connect')
})
```

#### 6. **VPNView - Toggle** (1 test)
**Archivo**: `frontend/client/src/components/Pages/VPNView.test.jsx` (CREAR)

```javascript
describe('VPNView - Toggle Component', () => {
  it('renders Toggle component for auto-connect')
})
```

#### 7. **VideoView - Toggle** (1 test)
**Archivo**: `frontend/client/src/components/Pages/VideoView.test.jsx` (CREAR)

```javascript
describe('VideoView - Toggle Component', () => {
  it('renders Toggle component for auto-start')
})
```

---

### **BACKEND TESTS** (8 nuevos + 2 modificaciones)

#### 1. **Flight Session - Auto-Start** (4 tests)
**Archivo**: `tests/test_flight_session.py` (CREAR)

```python
class TestFlightSessionAutoStart:
    def test_flight_session_starts_on_arm(self, client):
        """Auto-start preference enabled → session starts when armed"""
    
    def test_flight_session_stops_on_disarm(self, client):
        """Session stops automatically on disarm"""
    
    def test_auto_start_preference_persists(self, client):
        """Preference saved to preferences.json"""
    
    def test_manual_start_still_works(self, client):
        """Manual start button works regardless of auto-start"""
```

#### 2. **Flight Data Logger** (4 tests)
**Archivo**: `tests/test_flight_data_logger.py` (CREAR)

```python
class TestFlightDataLogger:
    def test_csv_file_created_on_session_start(self):
        """CSV file created with correct headers"""
    
    def test_csv_sample_written_correctly(self):
        """Sample row written with all fields"""
    
    def test_csv_file_closed_on_session_stop(self):
        """File handle properly closed"""
    
    def test_log_directory_configurable(self):
        """Custom log directory from preferences respected"""
```

#### 3. **Network Priority Mode** (3 tests)
**Archivo**: `tests/test_network_routes.py` (CREAR o MODIFICAR)

```python
class TestNetworkPriorityMode:
    def test_set_priority_wifi_primary(self, client):
        """WiFi metric 100, Modem metric 200"""
    
    def test_set_priority_modem_primary(self, client):
        """Modem metric 100, WiFi metric 200"""
    
    def test_set_priority_auto_selects_modem_first(self, client):
        """Auto mode prefers modem if available"""
```

#### 4. **Preferences Endpoints** (1 test)
**Archivo**: `tests/test_system_routes.py` (MODIFICAR)

```python
def test_get_preferences(self, client):
    """GET /api/system/preferences returns all preferences"""

def test_post_preferences(self, client):
    """POST /api/system/preferences updates preferences"""

def test_preferences_include_flight_session(self, client):
    """flight_session config in preferences"""
```

---

## ✅ CHECKLIST DE TESTS A EJECUTAR ANTES DEL COMMIT

### Frontend Tests
- [ ] `npm run test` - Todos los tests deben pasar
- [ ] 29 tests existentes deben continuar pasando
- [ ] +15 nuevos tests deben pasar (Toggle + Flight Session + Network)

### Backend Tests  
- [ ] `pytest` - Todos los tests deben pasar
- [ ] 155 tests existentes deben continuar pasando
- [ ] +12 nuevos tests deben pasar (Flight Session + Network + Logger)

### Coverage
- [ ] Flight session feature: >80% coverage  
- [ ] Toggle component: 100% coverage
- [ ] Network priority endpoint: >75% coverage

---

## 🚨 MODIFICACIONES A TESTS EXISTENTES

### 1. **Update Selector en Tests de FlightControllerView**
Si existe test que busca:
```javascript
// ❌ ANTES
screen.getByRole('checkbox').click()

// ✅ DESPUÉS (Toggle usa hidden checkbox)
const toggle = screen.getByLabelText('Auto-connect')
await user.click(toggle)
```

### 2. **Update Selector en Tests de VPNView**  
```javascript
// ✅ Mismo patrón
const autoConnect = screen.getByLabelText('Auto-connect')
await user.click(autoConnect)
```

### 3. **Update Selector en Tests de VideoView**
```javascript
// ✅ Mismo patrón  
const autoStart = screen.getByLabelText('Auto-start')
await user.click(autoStart)
```

### 4. **StatusView Tests - Agregar Flight Session Stubs**
```javascript
// En test fixtures, mock estos endpoints si faltan:
vi.mock('api', () => ({
  get: vi.fn((url) => {
    if (url === '/api/system/preferences') {
      return Promise.resolve({
        ok: true,
        json: () => ({ flight_session: { auto_start_on_arm: false } })
      })
    }
  }),
  post: vi.fn((url) => {
    if (url === '/api/network/hilink/flight-session/start') {
      return Promise.resolve({
        ok: true,
        json: () => ({ success: true, active: true })
      })
    }
  })
}))
```

### 5. **Update NetworkView Tests - Modal Confirmation**
```javascript
// Nuevo patrón para cambio de modo
await user.click(screen.getByRole('button', { name: /4G|modem/i }))
// Modal aparece
await user.click(screen.getByRole('button', { name: /confirm/i }))
// Change ejecutado
```

---

## 🔄 ORDEN RECOMENDADO DE TESTING

### Paso 1: Tests Existentes (Verificación de No-Regresión)
```bash
cd /opt/FPVCopilotSky/frontend/client && npm run test
cd /opt/FPVCopilotSky && pytest tests/
```

### Paso 2: Nuevos Tests - Componente Base
```bash
npm run test -- Toggle.test.jsx
```

### Paso 3: Nuevos Tests - Flight Session
```bash
pytest tests/test_flight_session.py
npm run test -- StatusView.test.jsx
```

### Paso 4: Nuevos Tests - Network Features
```bash
pytest tests/test_network_routes.py
npm run test -- NetworkView.test.jsx
npm run test -- Header.test.jsx
```

### Paso 5: Tests Modificados
```bash
npm run test -- FlightControllerView.test.jsx
npm run test -- VPNView.test.jsx
npm run test -- VideoView.test.jsx
```

---

## 📝 ARCHIVO MANIFEST DE CAMBIOS

```
FRONTEND (22 cambios + 9 tests):
  - Toggle Component (NUEVO): +3 archivos, +23 líneas de código
  - Headers/Badges: +1 feature (network status badge)
  - StatusView Flight Session: +250 líneas (nuevos handlers + UI)
  - NetworkView Priority: +80 líneas (modal confirmación)
  - FlightControllerView: -toggle manual, +Toggle component
  - VPNView: -toggle manual, +Toggle component  
  - VideoView: -toggle manual, +Toggle component
  - Toast/Clipboard: +fallback para HTTP
  - Logs/CSS: +improvements

BACKEND (10 cambios + 8 tests):
  - Flight Data Logger: +212 líneas (NUEVO)
  - Network Priority: +90 líneas (implementación completa)
  - Preferences Endpoints: +53 líneas (NUEVO)
  - Main.py: +15 líneas (flight logger init)
  - Modem Provider: +50 líneas (flight logger integration)
  - GStreamer: +20 líneas (probe fix)
  - MAVLink Bridge: +20 líneas (aliases)

TESTS/FIXTURES (5 cambios):
  - conftest.py: +30 líneas (3 fixtures)
  - websocket_integration.py: +25 líneas (timeout helper)
  - mavlink_bridge.py: +10 líneas (fixture renames)
  - performance_profiling.py: +1 línea (threshold)

DOCS (1 cambio):
  - FLIGHT_SESSION_IMPLEMENTATION.md (NUEVO): +290 líneas
```

---

## ✨ RESUMEN FINAL

**Antes del commit**:

1. ✅ Ejecutar `npm run lint` → 0 errores
2. ✅ Ejecutar `npm run test` → Todos pasan (incluir 15 nuevos tests para Toggle + Flight Session)
3. ✅ Ejecutar `pytest` → Todos pasan (incluir 12 nuevos tests para Flight Session + Network)  
4. ✅ Verificar selectores de tests con componente Toggle
5. ✅ Verificar mocks de endpoints de preferences y flight session
6. ✅ Commit con mensaje compresivo (ver siguiente sección)

