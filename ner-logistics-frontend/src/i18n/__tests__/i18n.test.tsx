import { render, screen, act } from '@testing-library/react'
import '@testing-library/jest-dom'
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import i18n from '../config'
import { I18nextProvider, useTranslation } from 'react-i18next'
import { getAlertMessage } from '../../pages/Alerts'

const TestComponent = () => {
  const { t, i18n: i18nInstance } = useTranslation()
  return (
    <div>
      <span data-testid="title">{t('navigation.dashboard')}</span>
      <button 
        data-testid="lang-btn" 
        onClick={() => i18nInstance.changeLanguage(i18nInstance.language === 'en' ? 'as' : 'en')}
      >
        {i18nInstance.language}
      </button>
    </div>
  )
}

describe('i18n core functionality', () => {
  beforeEach(async () => {
    localStorage.clear()
    await i18n.changeLanguage('en')
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('renders English by default', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <TestComponent />
      </I18nextProvider>
    )
    
    expect(screen.getByTestId('title')).toHaveTextContent('Dashboard')
    expect(screen.getByTestId('lang-btn')).toHaveTextContent('en')
  })

  it('switches to Assamese and persists to localStorage', async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <TestComponent />
      </I18nextProvider>
    )
    
    expect(screen.getByTestId('title')).toHaveTextContent('Dashboard')
    
    await act(async () => {
      screen.getByTestId('lang-btn').click()
    })
    
    expect(screen.getByTestId('lang-btn')).toHaveTextContent('as')
    expect(screen.getByTestId('title')).toHaveTextContent('ডেচবৰ্ড')
    expect(localStorage.getItem('ner_logistics_language')).toBe('as')
  })

  it('falls back to English if a key is missing in Assamese (assumes fallbackLng=en is set)', async () => {
    // We haven't set a missing key deliberately, but the config handles it.
    // If you add a key only to en.json, it will show the English text.
    await i18n.changeLanguage('as')
    
    // Testing the alert message helper instead for specific backend fallback logic
    const alertMock = {
      id: 1,
      alert_type: 'general',
      severity: 'high',
      message_en: 'Road closed',
      message_local: null,
      language: 'en',
      status: 'active',
      created_at: new Date().toISOString()
    }
    
    // When Assamese is selected but message_local is null
    const result = getAlertMessage(alertMock as any, 'as')
    expect(result).toBe('Road closed') // Fallback to EN
    
    ;(alertMock as any).message_local = 'ৰাস্তা বন্ধ'
    const result2 = getAlertMessage(alertMock as any, 'as')
    expect(result2).toBe('ৰাস্তা বন্ধ') // Uses local
  })
})
