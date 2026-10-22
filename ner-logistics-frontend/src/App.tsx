import React from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { RegionProvider } from './contexts/RegionContext'
import { Layout } from './components/layout/Layout'

// Pages
import { Home } from './pages/Home'
import { Login } from './pages/Login'
import { Register } from './pages/Register'
import { Vehicles } from './pages/Vehicles'
import { SavedRoutes } from './pages/SavedRoutes'
import { Incidents } from './pages/Incidents'
import { Districts } from './pages/Placeholders'
import { Alerts } from './pages/Alerts'

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <RegionProvider>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<Home />} />
              <Route path="login" element={<Login />} />
              <Route path="register" element={<Register />} />
              <Route path="districts" element={<Districts />} />
              <Route path="vehicles" element={<Vehicles />} />
              <Route path="incidents" element={<Incidents />} />
              <Route path="alerts" element={<Alerts />} />
              <Route path="routes" element={<SavedRoutes />} />
            </Route>
          </Routes>
        </RegionProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App

