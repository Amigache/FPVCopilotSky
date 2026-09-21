import { useWsMessage } from '../contexts/WebSocketContext'

/**
 * Returns true when the drone is armed (telemetry.system.armed === true).
 * Used to lock dangerous controls during flight.
 */
export function useArmedState() {
  const telemetry = useWsMessage('telemetry')
  return telemetry?.system?.armed ?? false
}
