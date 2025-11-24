import React, { Component, ReactNode, ErrorInfo } from 'react'
import { ErrorState } from './ErrorState'
import './ErrorBoundary.css'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    }
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    // Update state so the next render will show the fallback UI
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log error details for debugging
    console.error('ErrorBoundary caught an error:', error, errorInfo)
    
    // Store error info in state for potential reporting
    this.setState({
      error,
      errorInfo,
    })

    // Optional: Log to error reporting service
    // Example: Sentry, LogRocket, etc.
    // if (window.Sentry) {
    //   window.Sentry.captureException(error, { contexts: { react: { componentStack: errorInfo.componentStack } } })
    // }
  }

  handleReset = () => {
    // Reset error boundary state and reload the page to ensure clean state
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    })
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      // Use custom fallback if provided, otherwise use default ErrorState
      if (this.props.fallback) {
        return this.props.fallback
      }

      // Default fallback UI
      return (
        <div className="error-boundary-container">
          <div className="error-boundary-content">
            <ErrorState
              error={this.state.error}
              title="Error inesperado en la aplicación"
              onRetry={this.handleReset}
              showRetry={true}
            />
            {process.env.NODE_ENV === 'development' && this.state.error && (
              <details className="error-boundary-details">
                <summary className="error-boundary-summary">Detalles técnicos (solo en desarrollo)</summary>
                <div className="error-boundary-stack">
                  <h4>Error:</h4>
                  <pre className="error-boundary-pre">{this.state.error.toString()}</pre>
                  {this.state.errorInfo && (
                    <>
                      <h4>Stack trace:</h4>
                      <pre className="error-boundary-pre">{this.state.errorInfo.componentStack}</pre>
                    </>
                  )}
                </div>
              </details>
            )}
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary

