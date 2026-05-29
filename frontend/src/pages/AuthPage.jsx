import { useState } from 'react';
import { supabase } from '../lib/supabaseClient';
import { FileText, Mail, Lock, User, ArrowRight, CheckCircle } from 'lucide-react';
import styles from './AuthPage.module.css';

const TAB_LOGIN = 'login';
const TAB_SIGNUP = 'signup';

export default function AuthPage() {
  const [tab,      setTab]      = useState(TAB_LOGIN);
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [name,     setName]     = useState('');
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');
  const [success,  setSuccess]  = useState('');

  const reset = () => { setError(''); setSuccess(''); };
  const switchTab = (t) => { setTab(t); reset(); };

  const handleLogin = async (e) => {
    e.preventDefault();
    reset();
    if (!email || !password) { setError('Email and password are required.'); return; }
    setLoading(true);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setLoading(false);
    if (error) setError(error.message);
  };

  const handleSignup = async (e) => {
    e.preventDefault();
    reset();
    if (!email || !password) { setError('Email and password are required.'); return; }
    if (password.length < 6) { setError('Password must be at least 6 characters.'); return; }
    setLoading(true);
    const { error } = await supabase.auth.signUp({ email, password, options: { data: { full_name: name } } });
    setLoading(false);
    if (error) return setError(error.message);
    setSuccess('Account created! Check your email to confirm, then log in.');
  };

  return (
    <div className={styles.root}>
      <div className={styles.blob1} aria-hidden />
      <div className={styles.blob2} aria-hidden />
      <div className={styles.card}>
        <div className={styles.logo}>
          <div className={styles.logoIcon}><FileText size={22} color="#fff" /></div>
          <span className={styles.logoText}>DocuSend</span>
        </div>
        <div className={styles.headline}>
          <h1>{tab === TAB_LOGIN ? 'Welcome back' : 'Create your account'}</h1>
          <p>{tab === TAB_LOGIN ? 'Sign in to continue to your workspace' : 'Start extracting documents in seconds'}</p>
        </div>
        <div className={styles.tabs} role="tablist">
          <button role="tab" aria-selected={tab === TAB_LOGIN} className={`${styles.tab} ${tab === TAB_LOGIN ? styles.tabActive : ''}`} onClick={() => switchTab(TAB_LOGIN)} id="tab-login">Sign In</button>
          <button role="tab" aria-selected={tab === TAB_SIGNUP} className={`${styles.tab} ${tab === TAB_SIGNUP ? styles.tabActive : ''}`} onClick={() => switchTab(TAB_SIGNUP)} id="tab-signup">Sign Up</button>
          <div className={styles.tabIndicator} style={{ transform: tab === TAB_SIGNUP ? 'translateX(100%)' : 'translateX(0)' }} />
        </div>
        <form className={styles.form} onSubmit={tab === TAB_LOGIN ? handleLogin : handleSignup} noValidate>
          {tab === TAB_SIGNUP && (
            <div className="form-group animate-fade-up">
              <label className="form-label" htmlFor="auth-name">Full Name</label>
              <div className={styles.inputWrap}>
                <User size={16} className={styles.inputIcon} />
                <input id="auth-name" type="text" className={`form-input ${styles.inputWithIcon}`} placeholder="Jane Smith" value={name} onChange={e => setName(e.target.value)} autoComplete="name" />
              </div>
            </div>
          )}
          <div className="form-group">
            <label className="form-label" htmlFor="auth-email">Email Address</label>
            <div className={styles.inputWrap}>
              <Mail size={16} className={styles.inputIcon} />
              <input id="auth-email" type="email" className={`form-input ${styles.inputWithIcon} ${error ? 'error' : ''}`} placeholder="you@example.com" value={email} onChange={e => { setEmail(e.target.value); reset(); }} autoComplete="email" required />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="auth-password">Password</label>
            <div className={styles.inputWrap}>
              <Lock size={16} className={styles.inputIcon} />
              <input id="auth-password" type="password" className={`form-input ${styles.inputWithIcon} ${error ? 'error' : ''}`} placeholder={tab === TAB_SIGNUP ? 'At least 6 characters' : '••••••••'} value={password} onChange={e => { setPassword(e.target.value); reset(); }} autoComplete={tab === TAB_LOGIN ? 'current-password' : 'new-password'} required />
            </div>
          </div>
          {error   && <div className="alert alert-error animate-fade-up" role="alert">{error}</div>}
          {success && <div className="alert alert-success animate-fade-up" role="alert"><CheckCircle size={16} style={{flexShrink:0}} />{success}</div>}
          <button type="submit" id={tab === TAB_LOGIN ? 'btn-login' : 'btn-signup'} className={`btn btn-primary btn-lg btn-full ${styles.submitBtn}`} disabled={loading}>
            {loading ? <><span className="spinner" style={{borderTopColor:'#fff'}} /> Processing…</> : <>{tab === TAB_LOGIN ? 'Sign In' : 'Create Account'} <ArrowRight size={16} /></>}
          </button>
        </form>
        <p className={styles.footer}>
          {tab === TAB_LOGIN
            ? <>Don't have an account? <button className={styles.link} onClick={() => switchTab(TAB_SIGNUP)}>Sign Up →</button></>
            : <>Already have an account? <button className={styles.link} onClick={() => switchTab(TAB_LOGIN)}>Sign In →</button></>}
        </p>
      </div>
    </div>
  );
}
