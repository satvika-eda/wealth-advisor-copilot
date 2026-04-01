import { Routes, Route, Link, Navigate, useLocation } from 'react-router-dom';
import { MessageSquare, FileText, Shield, LogOut } from 'lucide-react';
import { useAuth } from './context/AuthContext';
import Chat from './components/Chat';
import Documents from './components/Documents';
import Admin from './components/Admin';
import Login from './components/Login';
import Register from './components/Register';

const ADMIN_ROLES = new Set(['admin', 'compliance']);

function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return children;
}

function RequireRole({ roles, children }) {
  const { user } = useAuth();
  if (!roles.has(user?.role)) {
    return <Navigate to="/" replace />;
  }
  return children;
}

function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();

  const navItems = [
    { path: '/', icon: MessageSquare, label: 'Chat', roles: null },
    { path: '/documents', icon: FileText, label: 'Documents', roles: null },
    { path: '/admin', icon: Shield, label: 'Audit Logs', roles: ADMIN_ROLES },
  ].filter((item) => !item.roles || item.roles.has(user?.role));

  return (
    <div className="min-h-screen bg-slate-50 flex">
      <aside className="w-64 bg-white border-r border-slate-200 flex flex-col">
        <div className="p-4 border-b border-slate-200">
          <h1 className="text-xl font-bold text-primary-700">Wealth Advisor</h1>
          <p className="text-sm text-slate-500">Copilot</p>
        </div>

        <nav className="flex-1 p-4">
          <ul className="space-y-2">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <li key={item.path}>
                  <Link
                    to={item.path}
                    className={`flex items-center gap-3 px-4 py-2 rounded-lg transition-colors ${
                      isActive
                        ? 'bg-primary-50 text-primary-700'
                        : 'text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <item.icon className="w-5 h-5" />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="p-4 border-t border-slate-200">
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-900 truncate">{user?.email}</p>
              <p className="text-xs text-slate-500 capitalize">{user?.role}</p>
            </div>
            <button
              onClick={logout}
              title="Sign out"
              className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/" element={<Chat />} />
          <Route path="/documents" element={<Documents />} />
          <Route
            path="/admin"
            element={
              <RequireRole roles={ADMIN_ROLES}>
                <Admin />
              </RequireRole>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      />
    </Routes>
  );
}

export default App;
