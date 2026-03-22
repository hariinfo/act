import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const styles = {
  nav: {
    background: 'var(--act-blue)',
    color: 'white',
    padding: '0 24px',
    height: 56,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
    position: 'sticky',
    top: 0,
    zIndex: 100,
  },
  logo: {
    fontSize: 20,
    fontWeight: 700,
    color: 'white',
    textDecoration: 'none',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  logoAccent: {
    background: '#fff',
    color: 'var(--act-blue)',
    padding: '2px 8px',
    borderRadius: 4,
    fontWeight: 800,
    fontSize: 18,
  },
  links: {
    display: 'flex',
    alignItems: 'center',
    gap: 20,
  },
  link: {
    color: 'rgba(255,255,255,0.85)',
    textDecoration: 'none',
    fontSize: 14,
    fontWeight: 500,
    padding: '6px 0',
    borderBottom: '2px solid transparent',
    transition: 'all 0.2s',
  },
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: 16,
  },
  username: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.9)',
  },
  badge: {
    background: '#ff6f00',
    color: 'white',
    fontSize: 10,
    padding: '2px 6px',
    borderRadius: 3,
    fontWeight: 700,
    marginLeft: 4,
  },
  btn: {
    background: 'rgba(255,255,255,0.15)',
    color: 'white',
    border: '1px solid rgba(255,255,255,0.3)',
    padding: '6px 14px',
    borderRadius: 4,
    fontSize: 13,
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
};

export default function Navbar() {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();

  return (
    <nav style={styles.nav}>
      <div style={styles.links}>
        <Link to="/" style={styles.logo}>
          <span style={styles.logoAccent}>ACT</span>
          Practice Test
        </Link>
        {user && (
          <>
            <Link to="/tests" style={styles.link}>Tests</Link>
            {isAdmin && <Link to="/admin" style={styles.link}>Admin</Link>}
          </>
        )}
      </div>
      <div style={styles.right}>
        {user ? (
          <>
            <span style={styles.username}>
              {user.username}
              {isAdmin && <span style={styles.badge}>ADMIN</span>}
            </span>
            <button
              style={styles.btn}
              onClick={() => { logout(); navigate('/'); }}
              onMouseOver={(e) => e.target.style.background = 'rgba(255,255,255,0.25)'}
              onMouseOut={(e) => e.target.style.background = 'rgba(255,255,255,0.15)'}
            >
              Logout
            </button>
          </>
        ) : (
          <>
            <Link to="/login" style={styles.link}>Login</Link>
            <Link to="/register" style={styles.link}>Register</Link>
          </>
        )}
      </div>
    </nav>
  );
}
