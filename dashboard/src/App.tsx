// Router and layout (owner: Student A). Student B's pages are wired in already.

import { NavLink, Route, Routes } from 'react-router-dom'
import StatusBar from './components/StatusBar'
import FrameDetail from './pages/FrameDetail'
import History from './pages/History'
import Live from './pages/Live'
import Search from './pages/Search'
import Timeline from './pages/Timeline'

const links = [
  { to: '/live', label: 'Live' },
  { to: '/timeline', label: 'Timeline' },
  { to: '/search', label: 'Search' },
  { to: '/history', label: 'History' },
]

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <h1>Voice Assistant with Eyes</h1>
        <nav aria-label="Main">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to}>
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <StatusBar />
      <main>
        <Routes>
          <Route path="/" element={<Live />} />
          <Route path="/live" element={<Live />} />
          <Route path="/timeline" element={<Timeline />} />
          <Route path="/search" element={<Search />} />
          <Route path="/history" element={<History />} />
          <Route path="/frames/:id" element={<FrameDetail />} />
        </Routes>
      </main>
    </div>
  )
}
