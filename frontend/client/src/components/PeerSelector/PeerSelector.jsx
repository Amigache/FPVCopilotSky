import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../../services/api'
import './PeerSelector.css'

/**
 * PeerSelector - Input field with VPN peer suggestions
 * Allows manual input or selection from VPN network nodes
 */
export const PeerSelector = ({
  value,
  onChange,
  placeholder = 'IP or hostname',
  disabled = false,
  label = null,
  className = '',
  hasError = false,
}) => {
  const [peers, setPeers] = useState([])
  const [showDropdown, setShowDropdown] = useState(false)
  const [loading, setLoading] = useState(false)
  const [dropUp, setDropUp] = useState(false)
  const dropdownRef = useRef(null)
  const inputRef = useRef(null)

  // Load VPN peers
  const loadPeers = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getVPNPeers()
      // Extract peers array and include all peers (online and offline for selection)
      const peersList = data.peers || []
      setPeers(peersList.filter((peer) => !peer.is_self))
    } catch (_error) {
      // Silently handle - VPN may not be connected
      setPeers([])
    } finally {
      setLoading(false)
    }
  }, [])

  // Load VPN peers
  useEffect(() => {
    loadPeers()
  }, [loadPeers])

  // Cleanup al desmontar componente
  useEffect(() => {
    return () => {
      document.body.classList.remove('peer-selector-open')
    }
  }, [])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowDropdown(false)
        // Restaurar scroll cuando se cierre
        document.body.classList.remove('peer-selector-open')
      }
    }

    if (showDropdown) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => {
        document.removeEventListener('mousedown', handleClickOutside)
        // Cleanup: restaurar si el componente se desmonta
        document.body.classList.remove('peer-selector-open')
      }
    }
  }, [showDropdown])

  const handleSelectPeer = (peer) => {
    // Use MagicDNS name if available, fallback to IPv4
    const dnsName = peer.dns_name || ''
    const addresses = peer.ip_addresses || []
    const ip = addresses.find((addr) => !addr.includes(':')) || addresses[0] || ''
    onChange(dnsName || ip)
    setShowDropdown(false)
    // Restaurar scroll cuando se cierre
    document.body.classList.remove('peer-selector-open')
    inputRef.current?.focus()
  }

  const handleInputChange = (e) => {
    onChange(e.target.value)
  }

  const handleInputFocus = () => {
    if (peers.length > 0) {
      loadPeers() // Refresh on focus
    }
  }

  const toggleDropdown = () => {
    if (peers.length === 0 && !loading) {
      loadPeers()
    }
    if (!showDropdown && dropdownRef.current) {
      const rect = dropdownRef.current.getBoundingClientRect()
      const containerRect = dropdownRef.current.closest('.form-group')?.getBoundingClientRect()
      const viewportHeight = window.innerHeight
      const spaceBelow = viewportHeight - rect.bottom
      const spaceAbove = rect.top

      // Consider number of peers for better dropdown positioning
      const estimatedDropdownHeight = Math.min(peers.length * 60 + 60, 320)

      // Prefer dropping down, but if no space below and space above, drop up
      // Also ensure it doesn't cause page scroll by checking available space
      const shouldDropUp =
        spaceBelow < estimatedDropdownHeight &&
        spaceAbove > estimatedDropdownHeight &&
        spaceAbove > spaceBelow

      setDropUp(shouldDropUp)

      // Solo prevenir scroll, no cambiar posicionamiento
      document.body.classList.add('peer-selector-open')
    } else if (showDropdown) {
      // Restaurar scroll cuando se cierre
      document.body.classList.remove('peer-selector-open')
    }
    setShowDropdown(!showDropdown)
  }

  return (
    <div className="peer-selector" ref={dropdownRef}>
      {label && <label>{label}</label>}
      <div className="peer-selector-input-group">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={handleInputChange}
          onFocus={handleInputFocus}
          placeholder={placeholder}
          disabled={disabled}
          className={`peer-selector-input ${hasError ? 'input-error' : ''}`}
        />
        <button
          type="button"
          className="peer-selector-button"
          onClick={toggleDropdown}
          disabled={disabled}
          title="Select from VPN peers"
        >
          {loading ? (
            <span className="loading-icon">⏳</span>
          ) : (
            <svg
              className="dropdown-icon"
              width="12"
              height="12"
              viewBox="0 0 12 12"
              fill="currentColor"
            >
              <path d="M6 9L1 4h10z" />
            </svg>
          )}
        </button>
      </div>

      {showDropdown && peers.length > 0 && (
        <div className={`peer-selector-dropdown ${dropUp ? 'drop-up' : ''}`}>
          <div className="peer-selector-header">
            <span>VPN Nodes ({peers.length})</span>
            <button
              type="button"
              className="peer-selector-refresh"
              onClick={loadPeers}
              disabled={loading}
            >
              🔄
            </button>
          </div>
          <div className="peer-selector-list">
            {peers.map((peer, idx) => {
              const addresses = peer.ip_addresses || []
              const ipv4 = addresses.find((addr) => !addr.includes(':')) || addresses[0] || 'No IP'
              const dnsName = peer.dns_name || ''
              return (
                <div
                  key={idx}
                  className={`peer-selector-item ${peer.is_self ? 'self' : ''}`}
                  onClick={() => !peer.is_self && handleSelectPeer(peer)}
                >
                  <div className="peer-selector-item-name">
                    <span className="peer-name">{peer.hostname}</span>
                    {peer.is_self && <span className="peer-badge">This device</span>}
                  </div>
                  <div className="peer-selector-item-details">
                    <span className="peer-ip">{ipv4}</span>
                    <span className="peer-os">{peer.os}</span>
                  </div>
                  {dnsName && <div className="peer-dns">{dnsName}</div>}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {showDropdown && peers.length === 0 && !loading && (
        <div className={`peer-selector-dropdown ${dropUp ? 'drop-up' : ''}`}>
          <div className="peer-selector-empty">No VPN peers available</div>
        </div>
      )}
    </div>
  )
}
