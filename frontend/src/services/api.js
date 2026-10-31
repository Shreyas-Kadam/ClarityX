/**
 * ClarityX Centralized API Client
 *
 * Configurable base URL via Vite environment variable VITE_API_BASE_URL.
 * Standardizes request headers, bearer token injection, and error formatting.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const getApiBaseUrl = () => BASE_URL

export const getAuthToken = () => {
  return localStorage.getItem('clarityx_access_token') || ''
}

export const setAuthToken = (token) => {
  if (token) {
    localStorage.setItem('clarityx_access_token', token)
  } else {
    localStorage.removeItem('clarityx_access_token')
  }
}

/**
 * Universal fetch wrapper for ClarityX Backend API.
 *
 * @param {string} endpoint - Path such as '/api/research'
 * @param {RequestInit} [options] - Fetch configuration options
 * @returns {Promise<any>}
 */
export async function apiFetch(endpoint, options = {}) {
  const url = `${BASE_URL.replace(/\/+$/, '')}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`
  const token = getAuthToken()

  const headers = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    ...(options.headers || {}),
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    })

    const data = await response.json().catch(() => null)

    if (!response.ok) {
      const errorMsg = data?.message || data?.detail || `Request failed with status ${response.status}`
      const error = new Error(errorMsg)
      error.status = response.status
      error.data = data
      throw error
    }

    return data
  } catch (error) {
    // Distinguish network failures from server responses
    if (!error.status) {
      error.status = 0
      error.message = error.message || 'Unable to connect to the backend server. Please verify your connection.'
    }
    throw error
  }
}

