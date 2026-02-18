import './PreferencesView.css'
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../../contexts/ToastContext'
import { useModal } from '../../../contexts/ModalContext'
import Toggle from '../../Toggle/Toggle'
import api from '../../../services/api'

const PreferencesView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { showModal } = useModal()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [resettingPrefs, setResettingPrefs] = useState(false)
  const [prefs, setPrefs] = useState(null)

  // VPN auto-connect stored separately (not inside prefs.network)
  const [vpnAutoConnect, setVpnAutoConnect] = useState(false)
  const [savingVpn, setSavingVpn] = useState(false)

  // ── Load preferences ──────────────────────────────────────────────────────
  const loadPrefs = useCallback(async () => {
    try {
      const res = await api.get('/api/system/preferences')
      if (res.ok) {
        const data = await res.json()
        setPrefs(data)
        if (data.vpn) {
          setVpnAutoConnect(data.vpn.auto_connect === true)
        }
      } else {
        showToast(t('preferences.error.load'), 'error')
      }
    } catch (e) {
      console.error(e)
      showToast(t('preferences.error.load'), 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast, t])

  useEffect(() => {
    loadPrefs()
  }, [loadPrefs])

  // ── Save helpers ──────────────────────────────────────────────────────────
  const deepMerge = (base, patch) => {
    const result = { ...base }
    for (const key of Object.keys(patch)) {
      if (patch[key] && typeof patch[key] === 'object' && !Array.isArray(patch[key])) {
        result[key] = deepMerge(base[key] || {}, patch[key])
      } else {
        result[key] = patch[key]
      }
    }
    return result
  }

  const savePref = async (patch) => {
    setSaving(true)
    try {
      const res = await api.post('/api/system/preferences', patch)
      if (res.ok) {
        setPrefs((prev) => deepMerge(prev, patch))
        showToast(t('preferences.saved'), 'success')
      } else {
        showToast(t('preferences.error.save'), 'error')
      }
    } catch (e) {
      console.error(e)
      showToast(t('preferences.error.save'), 'error')
    } finally {
      setSaving(false)
    }
  }

  // ── Toggle wrappers ───────────────────────────────────────────────────────
  const setAdaptiveBitrate = (v) => savePref({ video: { auto_adaptive_bitrate: v } })
  const setAdaptiveResolution = (v) => savePref({ video: { auto_adaptive_resolution: v } })
  const setExperimentalTab = (v) => {
    savePref({ extras: { experimental_tab_enabled: v } })
    window.dispatchEvent(new CustomEvent('experimentalTabToggled', { detail: { enabled: v } }))
  }
  const setModemPoolEnabled = (v) => savePref({ network: { modem_pool_enabled: v } })
  const setAutoFailover = (v) => savePref({ network: { auto_failover_enabled: v } })
  const setPolicyRouting = (v) => savePref({ network: { policy_routing_enabled: v } })
  const setVpnHealthCheck = (v) => savePref({ network: { vpn_health_check_enabled: v } })
  const setAutoStart = (v) => savePref({ streaming: { auto_start: v } })
  const setAutoConnect = (v) => savePref({ serial: { auto_connect: v } })
  const setAutoStartOnArm = (v) => savePref({ flight_session: { auto_start_on_arm: v } })

  const handleVpnAutoConnect = async (enabled) => {
    setSavingVpn(true)
    setVpnAutoConnect(enabled)
    try {
      const res = await api.post('/api/system/preferences', { vpn: { auto_connect: enabled } })
      if (res.ok) {
        showToast(t('preferences.saved'), 'success')
      } else {
        setVpnAutoConnect(!enabled)
        showToast(t('preferences.error.save'), 'error')
      }
    } catch (_e) {
      setVpnAutoConnect(!enabled)
      showToast(t('preferences.error.save'), 'error')
    } finally {
      setSavingVpn(false)
    }
  }

  const handleResetPreferences = () => {
    showModal({
      title: t('status.preferences.confirmTitle'),
      message: t('status.preferences.confirmMessage'),
      type: 'confirm',
      confirmText: t('status.preferences.confirmButton'),
      cancelText: t('common.cancel'),
      onConfirm: async () => {
        setResettingPrefs(true)
        try {
          const response = await api.post('/api/system/preferences/reset')
          const data = await response.json()
          if (response.ok && data.success) {
            showToast(t('status.preferences.resetSuccess'), 'success')
            await loadPrefs()
          } else {
            showToast(data.detail || data.message || t('status.preferences.resetError'), 'error')
          }
        } catch (error) {
          console.error('Error resetting preferences:', error)
          showToast(t('status.preferences.resetError'), 'error')
        } finally {
          setResettingPrefs(false)
        }
      },
    })
  }

  // ── Loading state ─────────────────────────────────────────────────────────
  if (loading || !prefs) {
    return (
      <div className="card">
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('common.loadingContent')}
        </div>
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="preferences-view">
      <div className="preferences-columns">
        {/* ── Left column ─────────────────────────────────────────────── */}
        <div className="preferences-col">
          {/* Network card */}
          <div className="card">
            <h2>🌐 {t('preferences.sections.network')}</h2>
            <PrefRow
              label={t('preferences.network.modemPool')}
              description={t('preferences.network.modemPoolDesc')}
              checked={prefs.network?.modem_pool_enabled !== false}
              onChange={setModemPoolEnabled}
              disabled={saving}
            />
            <PrefRow
              label={t('preferences.network.autoFailover')}
              description={t('preferences.network.autoFailoverDesc')}
              checked={prefs.network?.auto_failover_enabled !== false}
              onChange={setAutoFailover}
              disabled={saving}
            />
            <PrefRow
              label={t('preferences.network.policyRouting')}
              description={t('preferences.network.policyRoutingDesc')}
              checked={prefs.network?.policy_routing_enabled !== false}
              onChange={setPolicyRouting}
              disabled={saving}
            />
          </div>

          {/* VPN card */}
          <div className="card">
            <h2>🔒 {t('preferences.sections.vpn', 'VPN')}</h2>
            <PrefRow
              label={t('preferences.vpn.autoConnect', 'Conectar al iniciar')}
              description={t(
                'preferences.vpn.autoConnectDesc',
                'Conectar automáticamente a la VPN al iniciar el sistema.'
              )}
              checked={vpnAutoConnect}
              onChange={handleVpnAutoConnect}
              disabled={savingVpn}
            />
            <PrefRow
              label={t('preferences.network.vpnHealthCheck')}
              description={t('preferences.network.vpnHealthCheckDesc')}
              checked={prefs.network?.vpn_health_check_enabled !== false}
              onChange={setVpnHealthCheck}
              disabled={saving}
            />
          </div>
        </div>

        {/* ── Right column ────────────────────────────────────────────── */}
        <div className="preferences-col">
          {/* Video card */}
          <div className="card">
            <h2>📹 {t('preferences.sections.video')}</h2>
            <PrefRow
              label={t('preferences.video.autoStart')}
              description={t('preferences.video.autoStartDesc')}
              checked={prefs.streaming?.auto_start === true}
              onChange={setAutoStart}
              disabled={saving}
            />
            <PrefRow
              label={t('preferences.video.adaptiveBitrate')}
              description={t('preferences.video.adaptiveBitrateDesc')}
              checked={prefs.video?.auto_adaptive_bitrate !== false}
              onChange={setAdaptiveBitrate}
              disabled={saving}
            />
            <PrefRow
              label={t('preferences.video.adaptiveResolution')}
              description={t('preferences.video.adaptiveResolutionDesc')}
              checked={prefs.video?.auto_adaptive_resolution !== false}
              onChange={setAdaptiveResolution}
              disabled={saving}
            />
          </div>

          {/* System card */}
          <div className="card">
            <h2>⚙️ {t('preferences.sections.system')}</h2>
            <PrefRow
              label={t('preferences.system.autoConnectSerial')}
              description={t('preferences.system.autoConnectSerialDesc')}
              checked={prefs.serial?.auto_connect === true}
              onChange={setAutoConnect}
              disabled={saving}
            />
            <PrefRow
              label={t('preferences.system.autoStartOnArm')}
              description={t('preferences.system.autoStartOnArmDesc')}
              checked={prefs.flight_session?.auto_start_on_arm === true}
              onChange={setAutoStartOnArm}
              disabled={saving}
            />
          </div>

          {/* UI card */}
          <div className="card">
            <h2>🖥️ {t('preferences.sections.ui')}</h2>
            <PrefRow
              label={t('preferences.ui.experimentalTab')}
              description={t('preferences.ui.experimentalTabDesc')}
              checked={prefs.extras?.experimental_tab_enabled !== false}
              onChange={setExperimentalTab}
              disabled={saving}
            />
          </div>

          {/* ── Attention / Reset card ───────────────────────────────── */}
          <div className="card pref-reset-card">
            <h2>⚠️ {t('preferences.sections.attention')}</h2>
            <p className="pref-reset-desc">{t('status.preferences.description')}</p>
            <button
              className="btn-reset-preferences"
              onClick={handleResetPreferences}
              disabled={resettingPrefs}
            >
              {resettingPrefs
                ? t('status.preferences.resetting')
                : t('status.preferences.resetButton')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Reusable preference row ──────────────────────────────────────────────────
const PrefRow = ({ label, description, checked, onChange, disabled }) => (
  <div className="pref-row">
    <div className="pref-row-info">
      <span className="pref-row-label">{label}</span>
      {description && <span className="pref-row-desc">{description}</span>}
    </div>
    <Toggle checked={checked} onChange={(e) => onChange(e.target.checked)} disabled={disabled} />
  </div>
)

export default PreferencesView
