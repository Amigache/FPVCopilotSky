/**
 * FlightControllerView constants
 * Parameter definitions, vehicle configs, and baud rates
 */

export const AVAILABLE_BAUDRATES = [
  '9600',
  '19200',
  '38400',
  '57600',
  '115200',
  '230400',
  '460800',
  '921600',
]

export const DEFAULT_BAUDRATE = '115200'

// Base parameters (common to all vehicles)
export const BASE_PARAMS = {
  RC_PROTOCOLS: {
    label: 'RC_PROTOCOLS',
    description: 'rcProtocolsDesc',
    recommended: 0,
    options: [
      { value: 0, labelKey: 'rcProtocol.none' },
      { value: 1, labelKey: 'rcProtocol.all' },
      { value: 2, labelKey: 'rcProtocol.ppm' },
      { value: 4, labelKey: 'rcProtocol.ibus' },
      { value: 8, labelKey: 'rcProtocol.sbus' },
      { value: 16, labelKey: 'rcProtocol.dsm' },
      { value: 32, labelKey: 'rcProtocol.sumd' },
      { value: 64, labelKey: 'rcProtocol.srxl' },
      { value: 128, labelKey: 'rcProtocol.fport' },
      { value: 256, labelKey: 'rcProtocol.crsf' },
    ],
  },
  // GCS Failsafe: Enable action on loss of GCS heartbeat
  // https://ardupilot.org/plane/docs/parameters.html#fs-gcs-enabl-gcs-failsafe-enable
  // Triggers after FS_LONG_TIMEOUT seconds of no MAVLink heartbeat
  FS_GCS_ENABL: {
    label: 'FS_GCS_ENABL',
    description: 'fsGcsDesc',
    recommended: 1,
    options: [
      { value: 0, labelKey: 'fsGcs.disabled' },
      { value: 1, labelKey: 'fsGcs.heartbeat' },
      { value: 2, labelKey: 'fsGcs.heartbeatAndRemrssi' },
      { value: 3, labelKey: 'fsGcs.heartbeatAndAuto' },
    ],
  },
}

// Vehicle-specific parameters
export const VEHICLE_PARAMS = {
  plane: {
    titleKey: 'vehicleTitle.plane',
    params: {
      THR_FAILSAFE: {
        label: 'THR_FAILSAFE',
        description: 'thrFailsafeDesc',
        recommended: 0,
        options: [
          { value: 0, labelKey: 'thrFs.disabled' },
          { value: 1, labelKey: 'thrFs.enabled' },
          { value: 2, labelKey: 'thrFs.enabledNoFailsafe' },
        ],
      },
    },
  },
  rover: {
    titleKey: 'vehicleTitle.rover',
    params: {
      FS_THR_ENABLE: {
        label: 'FS_THR_ENABLE',
        description: 'fsThrEnableDesc',
        recommended: 0,
        options: [
          { value: 0, labelKey: 'thrFs.disabled' },
          { value: 1, labelKey: 'thrFs.enabledRtl' },
          { value: 2, labelKey: 'thrFs.continue' },
        ],
      },
    },
  },
  copter: {
    titleKey: 'vehicleTitle.copter',
    params: {
      FS_THR_ENABLE: {
        label: 'FS_THR_ENABLE',
        description: 'fsThrEnableDesc',
        recommended: 0,
        options: [
          { value: 0, labelKey: 'thrFs.disabled' },
          { value: 1, labelKey: 'thrFs.enabledLand' },
          { value: 2, labelKey: 'thrFs.rtl' },
          { value: 3, labelKey: 'thrFs.landSmartRtl' },
        ],
      },
      ARMING_CHECK: {
        label: 'ARMING_CHECK',
        description: 'armingCheckDesc',
        recommended: 65470,
        type: 'number',
      },
    },
    rcCalibration: true,
  },
}

// Stream Rate parameters
export const STREAM_RATE_PARAMS = {
  main: [
    {
      name: 'SR0_EXTRA1',
      labelKey: 'streamRate.extra1',
      descriptionKey: 'streamRate.extra1Desc',
      recommended: 4,
      color: 'green',
    },
    {
      name: 'SR0_POSITION',
      labelKey: 'streamRate.position',
      descriptionKey: 'streamRate.positionDesc',
      recommended: 2,
      color: 'blue',
    },
    {
      name: 'SR0_EXTRA3',
      labelKey: 'streamRate.extra3',
      descriptionKey: 'streamRate.extra3Desc',
      recommended: 2,
      color: 'orange',
    },
    {
      name: 'SR0_EXT_STAT',
      labelKey: 'streamRate.extStat',
      descriptionKey: 'streamRate.extStatDesc',
      recommended: 2,
      color: 'purple',
    },
  ],
  advanced: [
    {
      name: 'SR0_RAW_CTRL',
      labelKey: 'streamRate.rawCtrl',
      descriptionKey: 'streamRate.rawCtrlDesc',
      recommended: 1,
    },
    {
      name: 'SR0_RC_CHAN',
      labelKey: 'streamRate.rcChan',
      descriptionKey: 'streamRate.rcChanDesc',
      recommended: 1,
    },
  ],
}

// RC Calibration parameters (copter)
export const RC_CALIBRATION_PARAMS = [
  { channel: 1, name: 'Roll', minKey: 'RC1_MIN', maxKey: 'RC1_MAX' },
  { channel: 2, name: 'Pitch', minKey: 'RC2_MIN', maxKey: 'RC2_MAX' },
  { channel: 3, name: 'Throttle', minKey: 'RC3_MIN', maxKey: 'RC3_MAX' },
  { channel: 4, name: 'Yaw', minKey: 'RC4_MIN', maxKey: 'RC4_MAX' },
]

export const RC_CALIBRATION_RECOMMENDED = { min: 1101, max: 1901 }

/**
 * Detect vehicle type from MAV_TYPE string
 */
export const detectVehicleType = (mavType) => {
  if (!mavType) return null
  const type = mavType.toUpperCase()
  if (type.includes('FIXED') || type.includes('WING') || type.includes('PLANE')) return 'plane'
  if (
    type.includes('QUAD') ||
    type.includes('HEXA') ||
    type.includes('OCTO') ||
    type.includes('ROTOR') ||
    type.includes('COPTER') ||
    type.includes('TRI')
  )
    return 'copter'
  if (type.includes('ROVER') || type.includes('GROUND')) return 'rover'
  return null
}

/**
 * Build list of parameter names to request based on vehicle type
 */
export const getParamNamesToLoad = (vehicleType) => {
  const paramNames = [...Object.keys(BASE_PARAMS)]

  if (vehicleType && VEHICLE_PARAMS[vehicleType]) {
    Object.keys(VEHICLE_PARAMS[vehicleType].params).forEach((p) => paramNames.push(p))

    if (VEHICLE_PARAMS[vehicleType].rcCalibration) {
      RC_CALIBRATION_PARAMS.forEach((rc) => {
        paramNames.push(rc.minKey)
        paramNames.push(rc.maxKey)
      })
    }
  }

  STREAM_RATE_PARAMS.main.forEach((sr) => paramNames.push(sr.name))
  STREAM_RATE_PARAMS.advanced.forEach((sr) => paramNames.push(sr.name))

  return paramNames
}

/**
 * Build recommended params object for "Apply All Recommended"
 */
export const buildRecommendedParams = (vehicleType) => {
  const recommended = {}

  Object.entries(BASE_PARAMS).forEach(([name, config]) => {
    recommended[name] = config.recommended
  })

  if (vehicleType && VEHICLE_PARAMS[vehicleType]) {
    Object.entries(VEHICLE_PARAMS[vehicleType].params).forEach(([name, config]) => {
      recommended[name] = config.recommended
    })

    if (VEHICLE_PARAMS[vehicleType].rcCalibration) {
      RC_CALIBRATION_PARAMS.forEach((rc) => {
        recommended[rc.minKey] = RC_CALIBRATION_RECOMMENDED.min
        recommended[rc.maxKey] = RC_CALIBRATION_RECOMMENDED.max
      })
    }
  }

  STREAM_RATE_PARAMS.main.forEach((sr) => {
    recommended[sr.name] = sr.recommended
  })
  STREAM_RATE_PARAMS.advanced.forEach((sr) => {
    recommended[sr.name] = sr.recommended
  })

  return recommended
}
