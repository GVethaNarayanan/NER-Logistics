import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enTranslations from './locales/en.json'
import asTranslations from './locales/as.json'

// Check localStorage for preferred language
const getStoredLanguage = () => {
  try {
    const stored = localStorage.getItem('ner_logistics_language')
    if (stored === 'en' || stored === 'as') {
      return stored
    }
  } catch (e) {
    console.error('Failed to access localStorage for i18n', e)
  }
  return 'en' // default fallback
}

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: {
        translation: enTranslations
      },
      as: {
        translation: asTranslations
      }
    },
    lng: getStoredLanguage(), // initialization language
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false // react already safes from xss
    }
  })

// Persist language changes to localStorage
i18n.on('languageChanged', (lng) => {
  try {
    localStorage.setItem('ner_logistics_language', lng)
  } catch (e) {
    console.error('Failed to save language to localStorage', e)
  }
})

export default i18n
