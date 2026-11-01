/**
 * ClarityX Centralized API Client
 *
 * Configurable base URL via Vite environment variable VITE_API_BASE_URL.
 * Standardizes request headers, automatic Supabase Bearer token injection,
 * consistent error extraction, and network error handling.
 */

import { supabase } from '@/lib/supabase'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const getApiBaseUrl = () => BASE_URL

/**
 * Retrieves the active access token directly from the Supabase session.
 * Guaranteed to return the latest, refreshed token without hardcoding or manual storage.
 *
 * @returns {Promise<string>}
 */
export async function getAuthToken() {
  try {
    const { data, error } = await supabase.auth.getSession()
    if (error || !data?.session) {
      return ''
    }
    return data.session.access_token || ''
  } catch {
    return ''
  }
}

/**
 * Universal fetch wrapper for ClarityX Backend API.
 * Automatically injects the latest Supabase Bearer token for protected requests.
 *
 * @param {string} endpoint - Path such as '/api/research'
 * @param {RequestInit} [options] - Fetch configuration options
 * @returns {Promise<any>}
 */
export async function apiFetch(endpoint, options = {}) {
  const url = `${BASE_URL.replace(/\/+$/, '')}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`

  const token = await getAuthToken()

  const isFormData =
    typeof FormData !== 'undefined' && options.body instanceof FormData

  const headers = {
    Accept: 'application/json',
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers || {}),
  }

  // Remove any explicit Content-Type header (regardless of casing) for multipart FormData payloads
  if (isFormData) {
    for (const key of Object.keys(headers)) {
      if (key.toLowerCase() === 'content-type') {
        delete headers[key]
      }
    }
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  let response
  try {
    response = await fetch(url, {
      ...options,
      headers,
    })
  } catch (err) {
    const networkError = new Error(
      'Unable to connect to ClarityX backend server. Please verify the backend is running on port 8000.'
    )
    networkError.status = 0
    networkError.originalError = err
    throw networkError
  }

  let data = null
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    data = await response.json().catch(() => null)
  }

  if (!response.ok) {
    let errorMsg
    if (data?.message) {
      errorMsg = data.message
    } else if (typeof data?.detail === 'string') {
      errorMsg = data.detail
    } else if (Array.isArray(data?.detail) && data.detail[0]?.msg) {
      errorMsg = data.detail.map((d) => d.msg).join(', ')
    } else {
      errorMsg = `Request failed with status ${response.status}`
    }

    const error = new Error(errorMsg)
    error.status = response.status
    error.data = data

    // Notify auth context if access token was rejected
    if (response.status === 401) {
      if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
        window.dispatchEvent(new CustomEvent('clarityx:unauthorized'))
      }
    }

    throw error
  }

  return data
}
