/**
 * Get the API base URL for making requests.
 * 
 * Priority:
 * 1. VITE_API_BASE_URL environment variable (if set) - use this for cross-origin backends
 * 2. window.location.origin (in browser) - constructs URL from current origin to avoid hardcoding localhost
 * 3. Empty string (fallback) - for relative URLs, works with Vite proxy in development
 * 
 * In development:
 *   - Vite's proxy (configured in vite.config.ts) handles /api routes and forwards to http://localhost:8000
 *   - Using window.location.origin in dev will use http://localhost:5173, but the proxy intercepts /api routes
 * 
 * In production:
 *   - If VITE_API_BASE_URL is not set, uses window.location.origin (same origin as frontend)
 *   - This works when frontend and backend are served from the same domain
 *   - If backend is on a different host/port, set VITE_API_BASE_URL to the backend URL
 * 
 * Examples:
 *   - Same origin (prod): Leave VITE_API_BASE_URL unset → uses window.location.origin
 *   - Different host: VITE_API_BASE_URL=https://api.example.com
 *   - Different port: VITE_API_BASE_URL=http://localhost:8000
 */
export function getApiBaseUrl(): string {
  // If VITE_API_BASE_URL is explicitly set, use it
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL
  }
  
  // In browser environment, use window.location.origin to construct URL from current origin
  // This avoids hardcoding localhost and works for same-origin deployments
  if (typeof window !== 'undefined') {
    return window.location.origin
  }
  
  // Fallback to empty string for relative URLs (works with Vite proxy in dev)
  return ''
}

