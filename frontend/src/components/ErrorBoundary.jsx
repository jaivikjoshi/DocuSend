import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('Render error:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          minHeight: '100dvh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
          background: 'var(--soft)',
        }}>
          <div className="card card-padded" style={{ maxWidth: 560 }}>
            <h1 style={{ fontSize: 20, marginBottom: 8 }}>Something broke while rendering</h1>
            <p style={{ color: 'var(--muted)', marginBottom: 16 }}>
              The app caught a frontend error instead of leaving you on a blank screen.
            </p>
            <pre style={{
              whiteSpace: 'pre-wrap',
              background: 'var(--error-bg)',
              color: 'var(--error)',
              padding: 12,
              borderRadius: 8,
              fontSize: 12,
            }}>
              {this.state.error.message}
            </pre>
            <button
              className="btn btn-primary"
              style={{ marginTop: 16 }}
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
