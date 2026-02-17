/**
 * Video Sub-Component Tests
 *
 * Tests for the 7 sub-components extracted during Point 4.
 * These are pure presentational components — they receive props
 * and render UI. Testing render + interaction for each.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ---------- i18n mock (returns key as text) ----------
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
  }),
}))

// ---------- PeerSelector stub ----------
vi.mock('../../PeerSelector/PeerSelector', () => ({
  PeerSelector: ({ label, value, onChange, disabled }) => (
    <div data-testid="peer-selector">
      <label>{label}</label>
      <input
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        data-testid="peer-input"
      />
    </div>
  ),
}))

// ---------- Toggle stub ----------
vi.mock('../../Toggle/Toggle', () => ({
  default: ({ checked, onChange, disabled, label }) => (
    <label>
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        data-testid="toggle-input"
      />
      {label && <span>{label}</span>}
    </label>
  ),
}))

import StatusBanner from './StatusBanner'
import VideoSourceCard from './VideoSourceCard'
import EncodingConfigCard from './EncodingConfigCard'
import NetworkSettingsCard from './NetworkSettingsCard'
import StreamControlCard from './StreamControlCard'
import PipelineCard from './PipelineCard'
import StatsCard from './StatsCard'

// ===========================================================================
// StatusBanner
// ===========================================================================
describe('StatusBanner', () => {
  const baseConfig = {
    codec: 'h264',
    width: 1920,
    height: 1080,
    mode: 'udp',
    udp_host: '192.168.1.1',
    udp_port: 5600,
  }

  it('shows "stopped" when not streaming', () => {
    render(<StatusBanner status={{ streaming: false }} config={baseConfig} />)
    expect(screen.getByText('views.video.stopped')).toBeInTheDocument()
  })

  it('shows "streaming" when live', () => {
    render(<StatusBanner status={{ streaming: true }} config={baseConfig} />)
    expect(screen.getByText('views.video.streaming')).toBeInTheDocument()
  })

  it('shows error when present', () => {
    render(
      <StatusBanner
        status={{ streaming: false, last_error: 'Pipeline failed' }}
        config={baseConfig}
      />
    )
    expect(screen.getByText(/Pipeline failed/)).toBeInTheDocument()
  })

  it('shows UDP destination when streaming in UDP mode', () => {
    render(
      <StatusBanner
        status={{ streaming: true }}
        config={{ ...baseConfig, mode: 'udp', udp_host: '10.0.0.5', udp_port: 5600 }}
      />
    )
    expect(screen.getByText(/10\.0\.0\.5:5600/)).toBeInTheDocument()
  })
})

// ===========================================================================
// VideoSourceCard
// ===========================================================================
describe('VideoSourceCard', () => {
  const videoDevices = [
    {
      device_id: 'v4l2_video0',
      name: 'USB Camera',
      source_type: 'v4l2',
      device_path: '/dev/video0',
      provider: 'v4l2',
    },
    {
      device_id: 'v4l2_video2',
      name: 'HDMI Capture',
      source_type: 'hdmi_capture',
      device_path: '/dev/video2',
      provider: 'v4l2',
    },
  ]
  const defaultProps = {
    config: { device: '/dev/video0', width: 1920, height: 1080, framerate: 30 },
    videoDevices,
    streaming: false,
    handleCameraChange: vi.fn(),
    handleResolutionChange: vi.fn(),
    updateConfig: vi.fn(),
    availableResolutions: ['1920x1080', '1280x720', '640x480'],
    availableFps: [30, 24, 15],
  }

  it('renders camera options', () => {
    render(<VideoSourceCard {...defaultProps} />)
    expect(screen.getByText(/USB Camera/)).toBeInTheDocument()
    expect(screen.getByText(/HDMI Capture/)).toBeInTheDocument()
  })

  it('renders resolution options', () => {
    render(<VideoSourceCard {...defaultProps} />)
    expect(screen.getByText('1920x1080')).toBeInTheDocument()
    expect(screen.getByText('1280x720')).toBeInTheDocument()
  })

  it('renders FPS options', () => {
    render(<VideoSourceCard {...defaultProps} />)
    expect(screen.getByText('30 fps')).toBeInTheDocument()
    expect(screen.getByText('15 fps')).toBeInTheDocument()
  })

  it('shows "no cameras" when list is empty', () => {
    render(<VideoSourceCard {...defaultProps} videoDevices={[]} />)
    expect(screen.getByText('views.video.noCamerasAvailable')).toBeInTheDocument()
  })

  it('disables selects when streaming', () => {
    render(<VideoSourceCard {...defaultProps} streaming={true} />)
    const selects = screen.getAllByRole('combobox')
    selects.forEach((s) => expect(s).toBeDisabled())
  })

  it('calls handleCameraChange on camera select', async () => {
    const user = userEvent.setup()
    const fn = vi.fn()
    render(<VideoSourceCard {...defaultProps} handleCameraChange={fn} />)
    const select = screen.getAllByRole('combobox')[0]
    await user.selectOptions(select, '/dev/video2')
    expect(fn).toHaveBeenCalled()
  })
})

// ===========================================================================
// EncodingConfigCard
// ===========================================================================
describe('EncodingConfigCard', () => {
  const baseProps = {
    config: {
      codec: 'mjpeg',
      quality: 85,
      h264_bitrate: 2000,
      gop_size: 2,
      framerate: 30,
      mode: 'udp',
    },
    streaming: false,
    availableCodecs: [
      { id: 'mjpeg', name: 'MJPEG', description: 'Low CPU', cpu_usage: 'low', latency: 'low' },
      {
        id: 'h264',
        name: 'H.264',
        description: 'Good compression',
        cpu_usage: 'medium',
        latency: 'medium',
      },
    ],
    updateConfig: vi.fn(),
    debouncedLiveUpdate: vi.fn(),
    liveUpdate: vi.fn(),
  }

  it('renders codec selector with options', () => {
    render(<EncodingConfigCard {...baseProps} />)
    expect(screen.getByText(/MJPEG/)).toBeInTheDocument()
    expect(screen.getByText(/H\.264/)).toBeInTheDocument()
  })

  it('shows quality slider for MJPEG', () => {
    render(<EncodingConfigCard {...baseProps} />)
    const slider = screen.getByRole('slider')
    expect(slider).toBeInTheDocument()
    expect(slider).toHaveValue('85')
  })

  it('shows bitrate select for H.264', () => {
    render(<EncodingConfigCard {...baseProps} config={{ ...baseProps.config, codec: 'h264' }} />)
    // Should see bitrate options
    expect(screen.getByText(/2000/)).toBeInTheDocument()
  })

  it('shows GOP select only for h264_openh264', () => {
    render(
      <EncodingConfigCard {...baseProps} config={{ ...baseProps.config, codec: 'h264_openh264' }} />
    )
    // GOP select should be present (keyframe interval label)
    expect(screen.getByText('views.video.keyframeInterval')).toBeInTheDocument()
  })

  it('does not show GOP for plain h264', () => {
    render(<EncodingConfigCard {...baseProps} config={{ ...baseProps.config, codec: 'h264' }} />)
    expect(screen.queryByText('views.video.keyframeInterval')).not.toBeInTheDocument()
  })

  it('disables codec select when streaming', () => {
    render(<EncodingConfigCard {...baseProps} streaming={true} />)
    const selects = screen.getAllByRole('combobox')
    expect(selects[0]).toBeDisabled() // codec select
  })
})

// ===========================================================================
// NetworkSettingsCard
// ===========================================================================
describe('NetworkSettingsCard', () => {
  const baseProps = {
    config: {
      mode: 'udp',
      udp_host: '192.168.1.100',
      udp_port: 5600,
      multicast_group: '239.1.1.1',
      multicast_port: 5600,
      multicast_ttl: 1,
      rtsp_url: 'rtsp://localhost:8554/fpv',
      rtsp_transport: 'tcp',
      auto_start: false,
    },
    streaming: false,
    updateConfig: vi.fn(),
  }

  it('renders mode selector with 4 options (including webrtc)', () => {
    render(<NetworkSettingsCard {...baseProps} />)
    const modeSelect = screen.getAllByRole('combobox')[0]
    expect(modeSelect).toBeInTheDocument()
    expect(modeSelect.options.length).toBe(4)
  })

  it('shows UDP fields when mode is udp', () => {
    render(<NetworkSettingsCard {...baseProps} />)
    expect(screen.getByTestId('peer-selector')).toBeInTheDocument()
  })

  it('shows multicast fields when mode is multicast', () => {
    render(
      <NetworkSettingsCard {...baseProps} config={{ ...baseProps.config, mode: 'multicast' }} />
    )
    expect(screen.getByText('views.video.multicastGroup')).toBeInTheDocument()
    expect(screen.getByText('views.video.ttl')).toBeInTheDocument()
  })

  it('shows RTSP fields when mode is rtsp', () => {
    render(<NetworkSettingsCard {...baseProps} config={{ ...baseProps.config, mode: 'rtsp' }} />)
    expect(screen.getByText('views.video.rtspUrl')).toBeInTheDocument()
    expect(screen.getByText('views.video.rtspTransport')).toBeInTheDocument()
  })

  it('shows multicast validation error for non-multicast IP', () => {
    render(
      <NetworkSettingsCard
        {...baseProps}
        config={{ ...baseProps.config, mode: 'multicast', multicast_group: '192.168.1.1' }}
      />
    )
    const errorSmall = document.querySelector('.field-error')
    expect(errorSmall).toBeInTheDocument()
  })

  it('shows no multicast error for valid multicast IP', () => {
    render(
      <NetworkSettingsCard
        {...baseProps}
        config={{ ...baseProps.config, mode: 'multicast', multicast_group: '239.1.1.1' }}
      />
    )
    const errorSmall = document.querySelector('.field-error')
    expect(errorSmall).not.toBeInTheDocument()
  })

  it('shows RTSP URL error when prefix is wrong', () => {
    render(
      <NetworkSettingsCard
        {...baseProps}
        config={{ ...baseProps.config, mode: 'rtsp', rtsp_url: 'http://wrong' }}
      />
    )
    const errorSmall = document.querySelector('.field-error')
    expect(errorSmall).toBeInTheDocument()
  })

  it('shows input-error class on invalid multicast input', () => {
    render(
      <NetworkSettingsCard
        {...baseProps}
        config={{ ...baseProps.config, mode: 'multicast', multicast_group: '10.0.0.1' }}
      />
    )
    const errorInput = document.querySelector('.input-error')
    expect(errorInput).toBeInTheDocument()
  })

  it('disables fields when streaming', () => {
    render(<NetworkSettingsCard {...baseProps} streaming={true} />)
    const selects = screen.getAllByRole('combobox')
    selects.forEach((s) => expect(s).toBeDisabled())
  })
})

// ===========================================================================
// StreamControlCard
// ===========================================================================
describe('StreamControlCard', () => {
  const handlers = {
    applySettings: vi.fn(),
    applyConfigAndStart: vi.fn(),
    stopStream: vi.fn(),
    restartStream: vi.fn(),
  }

  it('shows Apply + Start when not streaming', () => {
    render(<StreamControlCard streaming={false} actionLoading={null} {...handlers} />)
    expect(screen.getByText('views.video.apply')).toBeInTheDocument()
    expect(screen.getByText('views.video.start')).toBeInTheDocument()
  })

  it('shows Stop + Restart when streaming', () => {
    render(<StreamControlCard streaming={true} actionLoading={null} {...handlers} />)
    expect(screen.getByText('views.video.stop')).toBeInTheDocument()
    expect(screen.getByText('views.video.restart')).toBeInTheDocument()
  })

  it('calls applyConfigAndStart on Start click', async () => {
    const user = userEvent.setup()
    const fn = vi.fn()
    render(
      <StreamControlCard
        streaming={false}
        actionLoading={null}
        {...handlers}
        applyConfigAndStart={fn}
      />
    )
    await user.click(screen.getByText('views.video.start'))
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('calls stopStream on Stop click', async () => {
    const user = userEvent.setup()
    const fn = vi.fn()
    render(
      <StreamControlCard streaming={true} actionLoading={null} {...handlers} stopStream={fn} />
    )
    await user.click(screen.getByText('views.video.stop'))
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('disables all buttons during action loading', () => {
    render(<StreamControlCard streaming={false} actionLoading="apply" {...handlers} />)
    const buttons = screen.getAllByRole('button')
    buttons.forEach((b) => expect(b).toBeDisabled())
  })

  it('renders auto-start toggle', () => {
    render(
      <StreamControlCard
        streaming={false}
        actionLoading={null}
        config={{ auto_start: false }}
        updateConfig={vi.fn()}
        {...handlers}
      />
    )
    expect(screen.getByTestId('toggle-input')).toBeInTheDocument()
  })
})

// ===========================================================================
// PipelineCard
// ===========================================================================
describe('PipelineCard', () => {
  it('renders pipeline string', () => {
    render(
      <PipelineCard
        pipelineString="gst-launch-1.0 v4l2src ! video/x-raw ..."
        onCopy={vi.fn()}
        copySuccess={false}
      />
    )
    expect(screen.getByText(/gst-launch-1.0/)).toBeInTheDocument()
  })

  it('shows "Copy" button normally', () => {
    render(<PipelineCard pipelineString="test" onCopy={vi.fn()} copySuccess={false} />)
    expect(screen.getByText('views.video.copyToClipboard')).toBeInTheDocument()
  })

  it('shows "Copied" after successful copy', () => {
    render(<PipelineCard pipelineString="test" onCopy={vi.fn()} copySuccess={true} />)
    expect(screen.getByText('views.video.copied')).toBeInTheDocument()
  })

  it('calls onCopy with pipeline string on click', async () => {
    const user = userEvent.setup()
    const onCopy = vi.fn()
    render(<PipelineCard pipelineString="pipeline-xyz" onCopy={onCopy} copySuccess={false} />)
    await user.click(screen.getByText('views.video.copyToClipboard'))
    expect(onCopy).toHaveBeenCalledWith('pipeline-xyz')
  })
})

// ===========================================================================
// StatsCard
// ===========================================================================
describe('StatsCard', () => {
  const statusData = {
    stats: {
      health: 'good',
      uptime_formatted: '1h 23m',
      current_fps: 29,
      current_bitrate: 2100,
      frames_sent: 12345,
      bytes_sent_mb: 456,
      errors: 0,
    },
    config: {
      codec: 'h264',
      width: 1920,
      height: 1080,
      framerate: 30,
      mode: 'udp',
      udp_host: '192.168.1.100',
      udp_port: 5600,
      multicast_group: '239.1.1.1',
      multicast_port: 5600,
      multicast_ttl: 1,
      rtsp_url: 'rtsp://localhost:8554/fpv',
    },
    providers: { encoder: 'openh264', source: 'v4l2' },
  }

  it('renders uptime', () => {
    render(<StatsCard status={statusData} />)
    expect(screen.getByText('1h 23m')).toBeInTheDocument()
  })

  it('renders fps', () => {
    render(<StatsCard status={statusData} />)
    expect(screen.getByText('29')).toBeInTheDocument()
  })

  it('renders bitrate', () => {
    render(<StatsCard status={statusData} />)
    expect(screen.getByText('2100')).toBeInTheDocument()
  })

  it('renders codec info', () => {
    render(<StatsCard status={statusData} />)
    expect(screen.getByText(/H264.*1920x1080/)).toBeInTheDocument()
  })

  it('renders error count', () => {
    render(<StatsCard status={statusData} />)
    expect(screen.getByText('0')).toBeInTheDocument()
  })

  it('shows RTSP clients when in rtsp mode', () => {
    const rtspStatus = {
      ...statusData,
      config: { ...statusData.config, mode: 'rtsp' },
      rtsp_server: { running: true, clients_connected: 3 },
    }
    render(<StatsCard status={rtspStatus} />)
    expect(screen.getByText('3')).toBeInTheDocument()
  })
})
