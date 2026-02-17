import { useState } from 'react'
import { useTranslation } from 'react-i18next'

const SOURCE_TYPE_ICONS = {
  v4l2: '📷',
  libcamera: '🎥',
  hdmi_capture: '🖥️',
  network_stream: '🌐',
}

const SOURCE_TYPE_LABELS = {
  v4l2: 'USB/V4L2',
  libcamera: 'CSI/LibCamera',
  hdmi_capture: 'HDMI Capture',
  network_stream: 'Network Stream',
}

const VideoDevicesCard = ({ devices, loading, activeDevicePath }) => {
  const { t } = useTranslation()
  const [expandedDevice, setExpandedDevice] = useState(null)

  const toggleExpand = (deviceId) => {
    setExpandedDevice(expandedDevice === deviceId ? null : deviceId)
  }

  const formatResolutions = (resolutions) => {
    if (!resolutions || resolutions.length === 0) return '-'
    // Show top 4 resolutions
    const shown = resolutions.slice(0, 4)
    const extra = resolutions.length - shown.length
    return shown.join(', ') + (extra > 0 ? ` (+${extra})` : '')
  }

  return (
    <div className="card">
      <h2 style={{ marginBottom: '0.5rem' }}>
        📹 {t('views.system.videoDevices', 'Video Devices')}
      </h2>

      {loading ? (
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('common.loading', 'Loading')}
        </div>
      ) : !devices || devices.length === 0 ? (
        <div className="waiting-data">
          {t('views.system.noVideoDevices', 'No video devices detected')}
        </div>
      ) : (
        <div className="video-devices-list">
          {devices.map((device) => (
            <div
              key={device.device_id}
              className={`video-device-item ${
                device.device_path === activeDevicePath ? 'active' : ''
              }`}
              onClick={() => toggleExpand(device.device_id)}
            >
              <div className="video-device-header">
                <span className="video-device-icon">
                  {SOURCE_TYPE_ICONS[device.source_type] || '📷'}
                </span>
                <div className="video-device-info">
                  <span className="video-device-name">{device.name}</span>
                  <span className="video-device-meta">
                    {SOURCE_TYPE_LABELS[device.source_type] || device.source_type}
                    {device.device_path && ` · ${device.device_path}`}
                  </span>
                </div>
                <div className="video-device-badges">
                  {device.device_path === activeDevicePath && (
                    <span className="video-device-badge active-badge">
                      {t('views.system.activeDevice', 'Active')}
                    </span>
                  )}
                  {device.hardware_encoding && (
                    <span className="video-device-badge hw-badge">HW Enc</span>
                  )}
                </div>
              </div>

              {/* Compact info always visible */}
              <div className="video-device-summary">
                <span className="video-device-tag">
                  {device.formats && device.formats.length > 0
                    ? device.formats.slice(0, 3).join(', ')
                    : '-'}
                </span>
                <span className="video-device-tag">{formatResolutions(device.resolutions)}</span>
                {device.compatible_codecs &&
                  device.compatible_codecs.filter((c) => c.compatible).length > 0 && (
                    <span className="video-device-tag codec-tag">
                      🎬{' '}
                      {device.compatible_codecs
                        .filter((c) => c.compatible)
                        .map((c) => c.display_name)
                        .slice(0, 3)
                        .join(', ')}
                      {device.compatible_codecs.filter((c) => c.compatible).length > 3
                        ? ` (+${device.compatible_codecs.filter((c) => c.compatible).length - 3})`
                        : ''}
                    </span>
                  )}
              </div>

              {/* Expanded details */}
              {expandedDevice === device.device_id && (
                <div className="video-device-details">
                  <div className="video-device-detail-row">
                    <span className="video-device-detail-label">
                      {t('views.system.vdDriver', 'Driver')}:
                    </span>
                    <span className="video-device-detail-value">{device.driver}</span>
                  </div>
                  {device.bus_info && (
                    <div className="video-device-detail-row">
                      <span className="video-device-detail-label">
                        {t('views.system.vdBusInfo', 'Bus')}:
                      </span>
                      <span className="video-device-detail-value">{device.bus_info}</span>
                    </div>
                  )}
                  <div className="video-device-detail-row">
                    <span className="video-device-detail-label">
                      {t('views.system.vdProvider', 'Provider')}:
                    </span>
                    <span className="video-device-detail-value">{device.provider}</span>
                  </div>
                  <div className="video-device-detail-row">
                    <span className="video-device-detail-label">
                      {t('views.system.vdFormats', 'Formats')}:
                    </span>
                    <span className="video-device-detail-value">
                      {device.formats && device.formats.length > 0
                        ? device.formats.join(', ')
                        : '-'}
                    </span>
                  </div>
                  <div className="video-device-detail-row">
                    <span className="video-device-detail-label">
                      {t('views.system.vdResolutions', 'Resolutions')}:
                    </span>
                    <span className="video-device-detail-value">
                      {device.resolutions && device.resolutions.length > 0
                        ? device.resolutions.join(', ')
                        : '-'}
                    </span>
                  </div>

                  {/* Compatible codecs */}
                  {device.compatible_codecs && device.compatible_codecs.length > 0 && (
                    <div className="video-device-fps-section">
                      <span className="video-device-detail-label">
                        {t('views.system.vdCodecs', 'Codecs')}:
                      </span>
                      <div className="video-device-codec-list">
                        {device.compatible_codecs.map((codec) => (
                          <span
                            key={codec.codec_id}
                            className={`video-device-codec-tag ${
                              codec.compatible ? codec.reason : 'incompatible'
                            }`}
                            title={
                              codec.compatible
                                ? `${codec.encoder_type} (${codec.reason})`
                                : t(
                                    'views.system.vdCodecIncompatible',
                                    'Not compatible with this device'
                                  )
                            }
                          >
                            {codec.compatible ? '✅' : '❌'} {codec.display_name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* FPS by resolution */}
                  {device.fps_by_resolution && Object.keys(device.fps_by_resolution).length > 0 && (
                    <div className="video-device-fps-section">
                      <span className="video-device-detail-label">
                        {t('views.system.vdFpsByRes', 'FPS by Resolution')}:
                      </span>
                      <div className="video-device-fps-grid">
                        {Object.entries(device.fps_by_resolution)
                          .slice(0, 6)
                          .map(([res, fpsList]) => (
                            <div key={res} className="video-device-fps-item">
                              <span className="fps-res">{res}</span>
                              <span className="fps-values">
                                {Array.isArray(fpsList) ? fpsList.join(', ') : fpsList} fps
                              </span>
                            </div>
                          ))}
                      </div>
                    </div>
                  )}

                  {/* Format-specific resolutions */}
                  {device.format_resolutions &&
                    Object.keys(device.format_resolutions).length > 0 && (
                      <div className="video-device-fps-section">
                        <span className="video-device-detail-label">
                          {t('views.system.vdResByFormat', 'Resolutions by Format')}:
                        </span>
                        <div className="video-device-fps-grid">
                          {Object.entries(device.format_resolutions)
                            .slice(0, 4)
                            .map(([fmt, resList]) => (
                              <div key={fmt} className="video-device-fps-item">
                                <span className="fps-res">{fmt}</span>
                                <span className="fps-values">
                                  {Array.isArray(resList)
                                    ? resList.slice(0, 3).join(', ')
                                    : resList}
                                  {Array.isArray(resList) && resList.length > 3
                                    ? ` (+${resList.length - 3})`
                                    : ''}
                                </span>
                              </div>
                            ))}
                        </div>
                      </div>
                    )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default VideoDevicesCard
