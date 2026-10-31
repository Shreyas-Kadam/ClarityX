import { useState, useEffect, useRef, useCallback } from 'react'
import { AuthContext } from './authContextDef'
import { supabase } from '@/lib/supabase'
import { getCurrentUserProfile } from '@/services/authService'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [session, setSession] = useState(null)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [profileLoading, setProfileLoading] = useState(false)

  // Track the last user ID for which profile was fetched to avoid unnecessary duplicate API calls
  const lastFetchedUserId = useRef(null)

  const fetchProfile = useCallback(async (currentSession) => {
    if (!currentSession?.access_token || !currentSession?.user) {
      setProfile(null)
      lastFetchedUserId.current = null
      return
    }

    const currentUserId = currentSession.user.id
    if (lastFetchedUserId.current === currentUserId && profile) {
      return
    }

    setProfileLoading(true)
    try {
      const data = await getCurrentUserProfile()
      setProfile(data)
      lastFetchedUserId.current = currentUserId
    } catch (err) {
      console.warn('[ClarityX Auth] Could not fetch backend user profile:', err.message)
      // Provide fallback profile metadata derived from the verified Supabase user object
      setProfile({
        id: currentSession.user.id,
        email: currentSession.user.email || '',
        full_name:
          currentSession.user.user_metadata?.full_name ||
          currentSession.user.user_metadata?.name ||
          '',
        created_at: currentSession.user.created_at,
        updated_at: currentSession.user.updated_at,
      })
      lastFetchedUserId.current = currentUserId
    } finally {
      setProfileLoading(false)
    }
  }, [profile])

  useEffect(() => {
    let isMounted = true

    // 1. Initial session restore on page load / browser refresh
    async function initializeAuth() {
      try {
        const { data, error } = await supabase.auth.getSession()
        if (error) {
          console.warn('[ClarityX Auth] Error getting initial session:', error.message)
        }

        if (isMounted) {
          const currentSession = data?.session || null
          setSession(currentSession)
          setUser(currentSession?.user || null)

          if (currentSession?.user) {
            await fetchProfile(currentSession)
          }
        }
      } catch (err) {
        console.error('[ClarityX Auth] Unexpected error during session initialization:', err)
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    initializeAuth()

    // 2. Listen to Supabase auth state transitions
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, newSession) => {
      if (!isMounted) return

      setSession(newSession)
      setUser(newSession?.user || null)

      if (event === 'SIGNED_OUT' || !newSession) {
        setProfile(null)
        lastFetchedUserId.current = null
        setLoading(false)
        return
      }

      if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED' || event === 'USER_UPDATED') {
        if (newSession?.user?.id !== lastFetchedUserId.current) {
          await fetchProfile(newSession)
        }
      }

      setLoading(false)
    })

    // 3. Handle 401 Unauthorized events from backend
    const handleUnauthorized = async () => {
      console.warn('[ClarityX Auth] Backend reported 401 Unauthorized. Signing out.')
      await supabase.auth.signOut().catch(() => {})
      if (isMounted) {
        setUser(null)
        setSession(null)
        setProfile(null)
        lastFetchedUserId.current = null
      }
    }

    window.addEventListener('clarityx:unauthorized', handleUnauthorized)

    return () => {
      isMounted = false
      subscription.unsubscribe()
      window.removeEventListener('clarityx:unauthorized', handleUnauthorized)
    }
  }, [fetchProfile])

  /**
   * Signs in an existing user with email and password via Supabase Auth.
   *
   * @param {string} email
   * @param {string} password
   * @returns {Promise<{data: any, error: any}>}
   */
  const login = async (email, password) => {
    const response = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    })

    if (!response.error && response.data?.session) {
      setSession(response.data.session)
      setUser(response.data.user)
      await fetchProfile(response.data.session)
    }

    return response
  }

  /**
   * Registers a new user via Supabase Auth with full name in user metadata.
   *
   * @param {string} email
   * @param {string} password
   * @param {string} fullName
   * @returns {Promise<{data: any, error: any}>}
   */
  const register = async (email, password, fullName) => {
    const trimmedName = fullName?.trim() || ''
    const response = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: {
        data: {
          full_name: trimmedName,
        },
      },
    })

    if (!response.error && response.data?.session) {
      setSession(response.data.session)
      setUser(response.data.user)
      await fetchProfile(response.data.session)
    }

    return response
  }

  /**
   * Signs out the currently authenticated user and clears auth state.
   */
  const logout = async () => {
    try {
      await supabase.auth.signOut()
    } finally {
      setUser(null)
      setSession(null)
      setProfile(null)
      lastFetchedUserId.current = null
    }
  }

  /**
   * Refreshes the backend user profile.
   */
  const refreshProfile = async () => {
    if (session) {
      lastFetchedUserId.current = null
      await fetchProfile(session)
    }
  }

  const value = {
    user,
    session,
    profile,
    token: session?.access_token || '',
    isAuthenticated: !!user,
    loading,
    profileLoading,
    login,
    register,
    logout,
    refreshProfile,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
