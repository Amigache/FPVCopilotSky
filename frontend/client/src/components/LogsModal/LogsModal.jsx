import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import './LogsModal.css';

const LogsModal = ({ show, onClose, type, onRefresh }) => {
  const { t } = useTranslation();
  const [logs, setLogs] = useState('');
  const [loading, setLoading] = useState(false);
  const logsRef = useRef(null);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const result = await onRefresh();
      setLogs(result || t('status.logs.noLogs'));
    } catch (_error) {
      setLogs(t('status.logs.errorLoading'));
    } finally {
      setLoading(false);
    }
  }, [onRefresh, t]);

  useEffect(() => {
    if (show) {
      loadLogs();
    }
     
  }, [show, type, loadLogs]);

  const handleRefresh = () => {
    loadLogs();
  };

  const handleCopy = () => {
    if (logs) {
      navigator.clipboard.writeText(logs);
      // Could add a toast notification here
    }
  };

  const handleScrollToTop = () => {
    if (logsRef.current) {
      logsRef.current.scrollTop = 0;
    }
  };

  const handleScrollToBottom = () => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  };

  if (!show) return null;

  return (
    <div className="logs-modal-overlay" onClick={onClose}>
      <div className="logs-modal-container" onClick={e => e.stopPropagation()}>
        <div className="logs-modal-header">
          <div className="logs-modal-title">
            <h3>
              {type === 'backend' ? t('status.logs.backend') : t('status.logs.frontend')}
            </h3>
            <span className="logs-modal-subtitle">
              {t('status.logs.realTime')}
            </span>
          </div>
          <div className="logs-modal-actions">
            <button 
              className="logs-action-btn" 
              onClick={handleRefresh}
              disabled={loading}
              title={t('status.logs.refresh')}
            >
              🔄
            </button>
            <button 
              className="logs-action-btn" 
              onClick={handleCopy}
              title={t('common.copy')}
            >
              📋
            </button>
            <button 
              className="logs-action-btn" 
              onClick={handleScrollToTop}
              title={t('status.logs.scrollToTop')}
            >
              ⬆️
            </button>
            <button 
              className="logs-action-btn" 
              onClick={handleScrollToBottom}
              title={t('status.logs.scrollToBottom')}
            >
              ⬇️
            </button>
            <button 
              className="logs-modal-close" 
              onClick={onClose}
              title={t('common.close')}
            >
              ×
            </button>
          </div>
        </div>
        
        <div className="logs-modal-body">
          {loading ? (
            <div className="logs-loading">
              <div className="logs-spinner"></div>
              <p>{t('common.loading')}</p>
            </div>
          ) : (
            <pre className="logs-content" ref={logsRef}>
              {logs}
            </pre>
          )}
        </div>

        <div className="logs-modal-footer">
          <button className="logs-modal-btn logs-modal-btn-close" onClick={onClose}>
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default LogsModal;
