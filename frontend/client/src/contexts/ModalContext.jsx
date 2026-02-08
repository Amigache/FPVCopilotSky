import { createContext, useContext, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'

const ModalContext = createContext(null)

export const useModal = () => {
  const context = useContext(ModalContext)
  if (!context) {
    throw new Error('useModal must be used within ModalProvider')
  }
  return context
}

export const ModalProvider = ({ children }) => {
  const { t } = useTranslation()
  const [modal, setModal] = useState(null)

  const showModal = useCallback(
    ({
      title,
      message,
      type = 'alert', // 'alert', 'confirm', 'notification'
      confirmText = t('common.ok'),
      cancelText = t('common.cancel'),
      onConfirm = null,
      onCancel = null,
    }) => {
      setModal({
        title,
        message,
        type,
        confirmText,
        cancelText,
        onConfirm,
        onCancel,
      })
    },
    [t]
  )

  const closeModal = useCallback(() => {
    setModal(null)
  }, [])

  const handleConfirm = useCallback(() => {
    if (modal?.onConfirm) {
      modal.onConfirm()
    }
    closeModal()
  }, [modal, closeModal])

  const handleCancel = useCallback(() => {
    if (modal?.onCancel) {
      modal.onCancel()
    }
    closeModal()
  }, [modal, closeModal])

  return (
    <ModalContext.Provider value={{ showModal, closeModal }}>
      {children}

      {modal && (
        <div className="modal-overlay" onClick={modal.type === 'confirm' ? null : closeModal}>
          <div className="modal-container" onClick={(e) => e.stopPropagation()}>
            <div className={`modal-header ${modal.type}`}>
              <h3>{modal.title}</h3>
              <button className="modal-close" onClick={closeModal}>
                ×
              </button>
            </div>

            <div className="modal-body">
              <p>{modal.message}</p>
            </div>

            <div className="modal-footer">
              {modal.type === 'confirm' ? (
                <>
                  <button className="modal-btn modal-btn-cancel" onClick={handleCancel}>
                    {modal.cancelText}
                  </button>
                  <button
                    className={`modal-btn modal-btn-confirm ${
                      modal.title.toLowerCase().includes('delete') ||
                      modal.title.toLowerCase().includes('elimina')
                        ? 'danger'
                        : ''
                    }`}
                    onClick={handleConfirm}
                  >
                    {modal.confirmText}
                  </button>
                </>
              ) : (
                <button className="modal-btn modal-btn-confirm" onClick={handleConfirm}>
                  {modal.confirmText}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </ModalContext.Provider>
  )
}
