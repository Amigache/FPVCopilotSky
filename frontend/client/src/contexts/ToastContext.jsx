import { createContext, useContext, useState, useCallback } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import '../components/Toast.css'

const ToastContext = createContext(null)

export const useToast = () => {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}

export const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([])

  const showToast = useCallback((message, type = 'info', duration = 3000) => {
    const id = crypto.randomUUID()

    setToasts(prev => [
      { id, message, type, duration },
      ...prev
    ])

    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, duration)
  }, [])

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}

      <div className="toast-container">
        <AnimatePresence initial={false}>
          {toasts.map(toast => (
            <motion.div
              key={toast.id}
              layout
              drag="x"
              dragConstraints={{ left: 0, right: 150 }}
              dragElastic={0.2}
              onDragEnd={(_, info) => {
                if (info.offset.x > 80) removeToast(toast.id)
              }}
              initial={{ opacity: 0, x: 80 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 80 }}
              transition={{ type: 'spring', stiffness: 500, damping: 35 }}
              className={`toast ${toast.type}`}
              onClick={() => removeToast(toast.id)}
              style={{ '--progress-duration': `${toast.duration}ms` }}
            >
              <div className="toast-message">{toast.message}</div>

              {/* Barra de progreso izquierda → derecha */}
              <motion.div
                className="toast-progress"
                initial={{ width: 0 }}
                animate={{ width: '100%' }}
                transition={{ duration: toast.duration / 1000, ease: 'linear' }}
              />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}
