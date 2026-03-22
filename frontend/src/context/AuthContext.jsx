import { createContext, useContext, useState, useEffect } from 'react';
import api from '../api/axios';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('act_token'));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      api.get('/auth/me')
        .then((res) => setUser(res.data))
        .catch(() => {
          setToken(null);
          localStorage.removeItem('act_token');
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = async (username, password) => {
    const res = await api.post('/auth/login', { username, password });
    const t = res.data.access_token;
    localStorage.setItem('act_token', t);
    setToken(t);
    const userRes = await api.get('/auth/me', {
      headers: { Authorization: `Bearer ${t}` },
    });
    setUser(userRes.data);
    return userRes.data;
  };

  const register = async (username, email, password) => {
    await api.post('/auth/register', { username, email, password });
    return login(username, password);
  };

  const logout = () => {
    localStorage.removeItem('act_token');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, isAdmin: user?.is_admin }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
