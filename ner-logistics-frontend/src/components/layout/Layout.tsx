import React from 'react'
import { Outlet } from 'react-router-dom'
import { Header } from './Header'

export const Layout: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-background font-sans antialiased text-foreground">
      <Header />
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="py-6 md:py-0 border-t">
        <div className="container mx-auto flex flex-col items-center justify-between gap-4 md:h-16 md:flex-row px-4">
          <p className="text-center text-sm leading-loose text-muted-foreground md:text-left">
            Built for NER Logistics Platform. Phase 2 Shell.
          </p>
        </div>
      </footer>
    </div>
  )
}
