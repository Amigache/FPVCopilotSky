import { useEffect, useRef, useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import { useTranslation } from 'react-i18next'
import 'leaflet/dist/leaflet.css'
import './MapView.css'

const MAP_TILES = {
  map: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  satellite:
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
}

const MAP_ATTR = {
  map: '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>',
  satellite: '&copy; <a href="https://esri.com">Esri</a>',
}

const vehicleIcon = L.divIcon({
  className: 'vehicle-marker',
  html: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <polygon points="12,2 15,10 12,8 9,10" fill="#4fc3f7" stroke="none"/>
    <polygon points="12,22 15,14 12,16 9,14" fill="#4fc3f7" stroke="none"/>
    <polygon points="2,12 10,9 8,12 10,15" fill="#4fc3f7" stroke="none"/>
    <polygon points="22,12 14,9 16,12 14,15" fill="#4fc3f7" stroke="none"/>
  </svg>`,
  iconSize: [28, 28],
  iconAnchor: [14, 14],
  popupAnchor: [0, -14],
})

const homeIcon = L.divIcon({
  className: 'home-marker',
  html: `<svg width="20" height="20" viewBox="0 0 24 24" fill="#4caf50" stroke="none">
    <circle cx="12" cy="12" r="10" fill="none" stroke="#4caf50" stroke-width="2"/>
    <path d="M12 3L3 12h3v7h4v-5h4v5h4v-7h3L12 3z" fill="#4caf50"/>
  </svg>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
})

function MapUpdater({ position }) {
  const map = useMap()
  const prevPos = useRef(null)

  useEffect(() => {
    if (position && (position.lat !== 0 || position.lon !== 0)) {
      const newPos = [position.lat, position.lon]
      const prev = prevPos.current
      const threshold = 0.0001
      if (
        !prev ||
        Math.abs(prev[0] - newPos[0]) > threshold ||
        Math.abs(prev[1] - newPos[1]) > threshold
      ) {
        map.panTo(newPos, { animate: true, duration: 0.5 })
        prevPos.current = newPos
      }
    }
  }, [position, map])

  return null
}

const SPAIN_CENTER = { lat: 40.0, lon: -3.5 }
const DEFAULT_ZOOM = 6

const MapView = ({ telemetry }) => {
  const { t } = useTranslation()
  const [tileMode, setTileMode] = useState('map')

  const lat = telemetry.gps?.lat || 0
  const lon = telemetry.gps?.lon || 0
  const alt = telemetry.gps?.alt || 0
  const satellites = telemetry.gps?.satellites || 0
  const hasValidPosition = lat !== 0 || lon !== 0

  const position = hasValidPosition ? { lat, lon } : SPAIN_CENTER

  return (
    <div className="card map-card">
      <div className="map-header">
        <h2>{t('dashboard.map')}</h2>
        <div className="map-toggles">
          <button
            className={`map-toggle-btn ${tileMode === 'map' ? 'active' : ''}`}
            onClick={() => setTileMode('map')}
          >
            {t('dashboard.mapView')}
          </button>
          <button
            className={`map-toggle-btn ${tileMode === 'satellite' ? 'active' : ''}`}
            onClick={() => setTileMode('satellite')}
          >
            {t('dashboard.satelliteView')}
          </button>
        </div>
      </div>
      <div className="map-container">
        <MapContainer
          center={[position.lat, position.lon]}
          zoom={hasValidPosition ? 18 : DEFAULT_ZOOM}
          className="map-inner"
          zoomControl={false}
          attributionControl={false}
        >
          <TileLayer url={MAP_TILES[tileMode]} attribution={MAP_ATTR[tileMode]} />
          {hasValidPosition && (
            <>
              <Marker position={[position.lat, position.lon]} icon={vehicleIcon}>
                <Popup>
                  <div className="map-popup">
                    <div>{lat.toFixed(6)}°</div>
                    <div>{lon.toFixed(6)}°</div>
                    <div>{alt.toFixed(1)} m</div>
                    <div>
                      {satellites} {t('dashboard.satellites').toLowerCase()}
                    </div>
                  </div>
                </Popup>
              </Marker>
              <Marker position={[position.lat, position.lon]} icon={homeIcon} />
            </>
          )}
          <MapUpdater position={position} />
        </MapContainer>
      </div>
    </div>
  )
}

export default MapView
