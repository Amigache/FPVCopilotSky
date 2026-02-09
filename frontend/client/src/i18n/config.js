import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import en from './locales/en.json'
import es from './locales/es.json'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      es: { translation: es },
    },
    fallbackLng: 'en',
    supportedLngs: ['en', 'es'],
    load: 'languageOnly', // Importante: ignora el código de región (es-ES -> es)
    debug: false, // Silenciar mensajes de debug/warning
    saveMissing: false, // No mostrar mensajes sobre claves faltantes
    showSupportNotice: false, // Ocultar banner de locize.com
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator', 'htmlTag'],
      lookupLocalStorage: 'i18nextLng',
      caches: ['localStorage'],
      convertDetectedLanguage: (lng) => lng.split('-')[0], // Convierte es-ES, es-MX, etc a 'es'
    },
  })

export default i18n
