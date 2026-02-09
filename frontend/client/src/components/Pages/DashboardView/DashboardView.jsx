import './DashboardView.css'
import { useTranslation } from 'react-i18next'
import { useWebSocket } from '../../../contexts/WebSocketContext'

const DashboardView = () => {
  const { t } = useTranslation()
  const { messages } = useWebSocket()

  const telemetry = messages.telemetry || {
    connected: false,
    attitude: { roll: 0, pitch: 0, yaw: 0 },
    gps: { lat: 0, lon: 0, alt: 0, satellites: 0 },
    battery: { voltage: 0, current: 0, remaining: 0 },
    speed: { ground_speed: 0, air_speed: 0, climb_rate: 0 },
    system: { mode: 'UNKNOWN', armed: false, system_status: 0 },
    messages: [],
  }

  const radToDeg = (rad) => ((rad * 180) / Math.PI).toFixed(1)

  // Color calculations based on FPVCopilotAir
  const satellites = telemetry.gps?.satellites || 0
  const gpsColor =
    satellites >= 6
      ? 'rgba(76, 175, 80, 0.5)'
      : satellites >= 4
        ? 'rgba(255, 152, 0, 0.5)'
        : 'rgba(244, 67, 54, 0.5)'
  const gpsBgColor =
    satellites >= 6
      ? 'rgba(76, 175, 80, 0.25)'
      : satellites >= 4
        ? 'rgba(255, 152, 0, 0.25)'
        : 'rgba(244, 67, 54, 0.25)'
  const gpsTextColor = satellites >= 6 ? '#9fe8c2' : satellites >= 4 ? '#ffcc80' : '#ffb3b8'

  const voltage = telemetry.battery?.voltage || 0
  const remaining = telemetry.battery?.remaining || 0
  const batteryColor =
    voltage < 10 || remaining < 20
      ? 'rgba(244, 67, 54, 0.5)'
      : voltage < 11 || remaining < 40
        ? 'rgba(255, 152, 0, 0.5)'
        : 'rgba(76, 175, 80, 0.5)'
  const batteryBgColor =
    remaining < 20
      ? 'rgba(244, 67, 54, 0.25)'
      : remaining < 40
        ? 'rgba(255, 152, 0, 0.25)'
        : 'rgba(76, 175, 80, 0.25)'
  const batteryTextColor = remaining < 20 ? '#ffb3b8' : remaining < 40 ? '#ffcc80' : '#9fe8c2'
  const batteryBarColor = remaining < 20 ? '#f44336' : remaining < 40 ? '#ff9800' : '#4caf50'
  const batteryBarGradient = remaining < 20 ? '#d32f2f' : remaining < 40 ? '#f57c00' : '#388e3c'

  const mode = telemetry.system?.mode || 'UNKNOWN'
  const isArmed = telemetry.system?.armed || false
  const vehicleType = telemetry.system?.vehicle_type || 'UNKNOWN'
  const autopilotType = telemetry.system?.autopilot_type || 'UNKNOWN'
  const systemState = telemetry.system?.state || 'UNKNOWN'

  // Define mode colors based on criticality
  const emergencyModes = ['RTL', 'LAND', 'BRAKE', 'QRTL', 'QLAND', 'THROW', 'FLIP']
  const cautionModes = ['AUTO', 'GUIDED', 'CIRCLE', 'FOLLOW', 'ZIGZAG', 'AUTOTUNE', 'POSHOLD']

  const isEmergencyMode = emergencyModes.includes(mode)
  const isCautionMode = cautionModes.includes(mode)

  const statusColor = isEmergencyMode
    ? 'rgba(244, 67, 54, 0.5)' // Rojo
    : isCautionMode
      ? 'rgba(255, 152, 0, 0.5)' // Naranja
      : 'rgba(76, 175, 80, 0.5)' // Verde

  const statusBgColor = isEmergencyMode
    ? 'rgba(244, 67, 54, 0.25)'
    : isCautionMode
      ? 'rgba(255, 152, 0, 0.25)'
      : 'rgba(76, 175, 80, 0.25)'

  const statusTextColor = isEmergencyMode ? '#ffb3b8' : isCautionMode ? '#ffcc80' : '#9fe8c2'

  const connectedColor = 'rgba(102, 102, 102, 0.3)'
  const climbRate = telemetry.speed?.climb_rate || 0

  return (
    <div className="monitor-columns">
      <div className="monitor-col">
        {/* Actitud Card */}
        <div className="card">
          <h2>{t('dashboard.attitude')}</h2>
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(45, 45, 63, 0.4), rgba(30, 30, 46, 0.4))',
              border: `1px solid ${connectedColor}`,
              borderRadius: '4px',
              padding: '12px 15px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            }}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))',
                gap: '8px',
                fontSize: '0.85em',
              }}
            >
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.roll')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600', fontSize: '1.1em' }}>
                  {radToDeg(telemetry.attitude?.roll || 0)}°
                </div>
              </div>
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.pitch')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600', fontSize: '1.1em' }}>
                  {radToDeg(telemetry.attitude?.pitch || 0)}°
                </div>
              </div>
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.yaw')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600', fontSize: '1.1em' }}>
                  {radToDeg(telemetry.attitude?.yaw || 0)}°
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* GPS Card */}
        <div className="card">
          <h2>{t('dashboard.gpsPosition')}</h2>
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(45, 45, 63, 0.4), rgba(30, 30, 46, 0.4))',
              border: `1px solid ${gpsColor}`,
              borderRadius: '4px',
              padding: '12px 15px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '10px',
              }}
            >
              <span style={{ fontSize: '0.9em', fontWeight: '600', color: '#d5ddff' }}>
                {t('dashboard.satellites')}
              </span>
              <span
                style={{
                  display: 'inline-block',
                  padding: '3px 8px',
                  background: gpsBgColor,
                  color: gpsTextColor,
                  borderRadius: '3px',
                  fontSize: '0.9em',
                  fontWeight: '700',
                  border: `1px solid ${gpsColor}`,
                }}
              >
                {satellites}
              </span>
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
                gap: '8px',
                fontSize: '0.85em',
              }}
            >
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.latitude')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600' }}>
                  {(telemetry.gps?.lat || 0).toFixed(6)}°
                </div>
              </div>
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.longitude')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600' }}>
                  {(telemetry.gps?.lon || 0).toFixed(6)}°
                </div>
              </div>
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.altitude')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600' }}>
                  {(telemetry.gps?.alt || 0).toFixed(1)} m
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Batería Card */}
        <div className="card">
          <h2>{t('dashboard.battery')}</h2>
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(45, 45, 63, 0.4), rgba(30, 30, 46, 0.4))',
              border: `1px solid ${batteryColor}`,
              borderRadius: '4px',
              padding: '12px 15px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '10px',
              }}
            >
              <span style={{ fontSize: '0.9em', fontWeight: '600', color: '#d5ddff' }}>
                {t('dashboard.charge')}
              </span>
              <span
                style={{
                  display: 'inline-block',
                  padding: '3px 8px',
                  background: batteryBgColor,
                  color: batteryTextColor,
                  borderRadius: '3px',
                  fontSize: '0.9em',
                  fontWeight: '700',
                  border: `1px solid ${batteryColor}`,
                }}
              >
                {remaining}%
              </span>
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: '8px',
                fontSize: '0.85em',
              }}
            >
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.voltage')}
                </div>
                <div
                  style={{
                    color: voltage < 10 ? '#f44336' : voltage < 11 ? '#ff9800' : '#d5ddff',
                    fontWeight: '700',
                    fontSize: '1.1em',
                  }}
                >
                  {voltage.toFixed(2)} V
                </div>
              </div>
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.current')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600', fontSize: '1.1em' }}>
                  {(telemetry.battery?.current || 0).toFixed(1)} A
                </div>
              </div>
            </div>
            <div
              style={{
                marginTop: '10px',
                background: 'rgba(20, 20, 30, 0.5)',
                borderRadius: '3px',
                height: '6px',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  background: `linear-gradient(90deg, ${batteryBarColor}, ${batteryBarGradient})`,
                  height: '100%',
                  width: `${remaining}%`,
                  transition: 'width 0.3s',
                }}
              ></div>
            </div>
          </div>
        </div>
      </div>

      <div className="monitor-col">
        {/* Estado Card */}
        <div className="card">
          <h2>{t('dashboard.status')}</h2>
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(45, 45, 63, 0.4), rgba(30, 30, 46, 0.4))',
              border: `1px solid ${statusColor}`,
              borderRadius: '4px',
              padding: '12px 15px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '10px',
              }}
            >
              <span style={{ fontSize: '0.9em', fontWeight: '600', color: '#d5ddff' }}>
                {t('dashboard.mode')}
              </span>
              <span
                style={{
                  display: 'inline-block',
                  padding: '3px 8px',
                  background: statusBgColor,
                  color: statusTextColor,
                  borderRadius: '3px',
                  fontSize: '0.8em',
                  fontWeight: '700',
                  border: `1px solid ${statusColor}`,
                }}
              >
                {mode}
              </span>
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: '8px',
                fontSize: '0.85em',
              }}
            >
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.armed')}
                </div>
                <div style={{ color: isArmed ? '#ff9800' : '#4caf50', fontWeight: '700' }}>
                  {isArmed ? t('dashboard.yes') : t('dashboard.no')}
                </div>
              </div>
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.type')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600', fontSize: '0.75em' }}>
                  {vehicleType}
                </div>
              </div>
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.autopilot')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600', fontSize: '0.75em' }}>
                  {autopilotType}
                </div>
              </div>
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.state')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600' }}>{systemState}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Velocidades Card */}
        <div className="card">
          <h2>{t('dashboard.speeds')}</h2>
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(45, 45, 63, 0.4), rgba(30, 30, 46, 0.4))',
              border: `1px solid ${connectedColor}`,
              borderRadius: '4px',
              padding: '12px 15px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            }}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
                gap: '8px',
                fontSize: '0.85em',
              }}
            >
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.groundSpeed')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600', fontSize: '1.1em' }}>
                  {(telemetry.speed?.ground_speed || 0).toFixed(1)} m/s
                </div>
              </div>
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.airSpeed')}
                </div>
                <div style={{ color: '#d5ddff', fontWeight: '600', fontSize: '1.1em' }}>
                  {(telemetry.speed?.air_speed || 0).toFixed(1)} m/s
                </div>
              </div>
              <div>
                <div style={{ color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px' }}>
                  {t('dashboard.climbRate')}
                </div>
                <div
                  style={{
                    color: climbRate > 0 ? '#4caf50' : climbRate < 0 ? '#ff9800' : '#d5ddff',
                    fontWeight: '600',
                    fontSize: '1.1em',
                  }}
                >
                  {climbRate.toFixed(1)} m/s
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Mensajes Card */}
        <div className="card messages-card">
          <h2>{t('dashboard.messages')}</h2>
          <div className="messages-list">
            {telemetry.messages && telemetry.messages.length > 0 ? (
              telemetry.messages.map((msg, idx) => {
                const severityColors = {
                  EMERGENCY: { bg: 'rgba(244, 67, 54, 0.2)', border: '#f44336', text: '#ffb3b8' },
                  ALERT: { bg: 'rgba(244, 67, 54, 0.2)', border: '#f44336', text: '#ffb3b8' },
                  CRITICAL: { bg: 'rgba(244, 67, 54, 0.15)', border: '#e57373', text: '#ffb3b8' },
                  ERROR: { bg: 'rgba(255, 152, 0, 0.15)', border: '#ff9800', text: '#ffcc80' },
                  WARNING: { bg: 'rgba(255, 152, 0, 0.1)', border: '#ffa726', text: '#ffcc80' },
                  NOTICE: { bg: 'rgba(33, 150, 243, 0.1)', border: '#42a5f5', text: '#90caf9' },
                  INFO: { bg: 'rgba(76, 175, 80, 0.1)', border: '#66bb6a', text: '#9fe8c2' },
                  DEBUG: { bg: 'rgba(158, 158, 158, 0.1)', border: '#9e9e9e', text: '#bdbdbd' },
                }
                const colors = severityColors[msg.severity] || severityColors['INFO']
                const timestamp = new Date(msg.timestamp * 1000).toLocaleTimeString('es-ES', {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })

                return (
                  <div
                    key={idx}
                    className="message-item"
                    style={{ background: colors.bg, border: `1px solid ${colors.border}` }}
                  >
                    <div className="message-severity" style={{ color: colors.text }}>
                      {msg.severity}
                    </div>
                    <div className="message-text" style={{ color: '#d5ddff' }}>
                      {msg.text}
                    </div>
                    <div className="message-time" style={{ color: '#9aa6c3' }}>
                      {timestamp}
                    </div>
                  </div>
                )
              })
            ) : (
              <div className="no-messages">{t('dashboard.noMessages')}</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default DashboardView
