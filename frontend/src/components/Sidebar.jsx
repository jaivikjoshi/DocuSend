import { supabase } from '../lib/supabaseClient';
import { FileText, LayoutDashboard, Files, Download, LogOut, ChevronRight } from 'lucide-react';
import styles from './Sidebar.module.css';

const VIEWS = {
  DASHBOARD: 'dashboard',
  DOCUMENTS: 'documents',
  EXPORT:    'export',
};

const NAV = [
  { id: VIEWS.DASHBOARD, label: 'Dashboard', icon: LayoutDashboard },
  { id: VIEWS.DOCUMENTS, label: 'Documents',  icon: Files },
  { id: VIEWS.EXPORT,    label: 'Export',     icon: Download },
];

export default function Sidebar({ user, activeView, onViewChange, documentCount }) {
  const handleLogout = async () => {
    await supabase.auth.signOut();
  };

  const initials = user?.email?.slice(0, 2).toUpperCase() ?? '??';
  const emailDisplay = user?.email ?? '';

  return (
    <aside className={styles.sidebar}>
      {/* Logo */}
      <div className={styles.logo}>
        <div className={styles.logoIcon}>
          <FileText size={18} color="#fff" />
        </div>
        <span className={styles.logoText}>DocuSend</span>
      </div>

      <div className={styles.divider} />

      {/* Navigation */}
      <nav className={styles.nav} aria-label="Main navigation">
        {NAV.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            id={`nav-${id}`}
            className={`${styles.navItem} ${activeView === id ? styles.navItemActive : ''}`}
            onClick={() => onViewChange(id)}
            aria-current={activeView === id ? 'page' : undefined}
          >
            <Icon size={17} className={styles.navIcon} />
            <span>{label}</span>
            {id === VIEWS.DOCUMENTS && documentCount > 0 && (
              <span className={`badge badge-pine ${styles.navBadge}`}>{documentCount}</span>
            )}
            {activeView === id && <ChevronRight size={14} className={styles.navChevron} />}
          </button>
        ))}
      </nav>

      <div className={styles.spacer} />

      {/* User section */}
      <div className={styles.userSection}>
        <div className={styles.avatar}>{initials}</div>
        <div className={styles.userInfo}>
          <span className={styles.userName}>{user?.user_metadata?.full_name || 'User'}</span>
          <span className={styles.userEmail}>{emailDisplay}</span>
        </div>
      </div>

      <button
        id="btn-logout"
        className={`${styles.logoutBtn}`}
        onClick={handleLogout}
      >
        <LogOut size={15} />
        Sign Out
      </button>
    </aside>
  );
}
