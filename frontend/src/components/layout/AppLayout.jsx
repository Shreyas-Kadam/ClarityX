import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

export function AppLayout() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const location = useLocation()

  const getPageTitle = (pathname) => {
    if (pathname === '/' || pathname === '/dashboard') return 'Research Dashboard'
    if (pathname === '/new') return 'New Research Session'
    if (pathname === '/history') return 'Research History'
    if (pathname.startsWith('/research/')) return 'Research Analysis Detail'
    if (pathname === '/settings') return 'Platform Settings'
    return 'ClarityX Research'
  }

  return (
    <div className="flex h-screen w-full bg-[#EDF2F4] text-[#2B2D42] overflow-hidden font-sans">
      {/* Desktop Sidebar */}
      <div className="hidden lg:flex shrink-0">
        <Sidebar />
      </div>

      {/* Mobile Drawer Overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-[#2B2D42]/60 backdrop-blur-xs z-40 lg:hidden transition-opacity"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Mobile Drawer */}
      <div
        className={`fixed inset-y-0 left-0 z-50 w-72 lg:hidden transform transition-transform duration-300 ease-in-out ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <Sidebar onClose={() => setMobileMenuOpen(false)} isMobile={true} />
      </div>

      {/* Main Workspace */}
      <div className="flex flex-col flex-1 h-full min-w-0 overflow-hidden">
        <Header
          onMenuClick={() => setMobileMenuOpen(true)}
          title={getPageTitle(location.pathname)}
        />

        <main className="flex-1 overflow-y-auto p-4 sm:p-8 space-y-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

