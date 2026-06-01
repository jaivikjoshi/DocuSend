import { useState, useEffect } from 'react';
import { supabase } from './lib/supabaseClient';
import AuthPage from './pages/AuthPage';
import DashboardPage from './pages/DashboardPage';
import './index.css';

export default function App() {
  const [session, setSession] = useState(undefined); // undefined = loading
  const [guestMode, setGuestMode] = useState(false);

  useEffect(() => {
    let mounted = true;

    Promise.race([
      supabase.auth.getSession(),
      new Promise(resolve => setTimeout(() => resolve({ data: { session: null } }), 4000)),
    ]).then(({ data: { session } }) => {
      if (mounted) setSession(session);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (session) setGuestMode(false);
    });

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, []);

  if (session === undefined) {
    return (
      <div style={{
        height: '100dvh', display: 'flex', alignItems: 'center',
        justifyContent: 'center', background: 'var(--soft)',
      }}>
        <div className="spinner spinner-lg" />
      </div>
    );
  }

  if (guestMode) {
    return (
      <DashboardPage
        session={{
          user: {
            id: 'guest',
            email: 'guest@local',
            user_metadata: { full_name: 'Guest Mode' },
          },
        }}
        isGuest
        onExitGuest={() => setGuestMode(false)}
      />
    );
  }

  return session
    ? <DashboardPage session={session} />
    : <AuthPage onGuest={() => setGuestMode(true)} />;
}
