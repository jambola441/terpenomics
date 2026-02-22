import { useState } from 'react'
import supabase from '../utils/supabase'

export function useAuthenticatedFetch() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const getAuthHeaders = async () => {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    if (!token) throw new Error('Not authenticated')
    return { Authorization: `Bearer ${token}` }
  }

  const authenticatedFetch = async <T = any>(
    url: string,
    options: RequestInit = {}
  ): Promise<T> => {
    setLoading(true)
    setError(null)

    try {
      const headers = await getAuthHeaders()
      const res = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...headers,
          ...options.headers,
        },
      })

      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `Request failed with status ${res.status}`)
      }

      const data = await res.json()
      return data as T
    } catch (err: any) {
      const errorMessage = err?.message ?? String(err)
      setError(errorMessage)
      throw err
    } finally {
      setLoading(false)
    }
  }

  return {
    authenticatedFetch,
    loading,
    error,
    setLoading,
    setError,
  }
}
