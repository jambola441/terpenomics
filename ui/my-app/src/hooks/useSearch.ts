import { useState } from 'react'

export function useSearch() {
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearch(searchInput)
  }

  const clearSearch = () => {
    setSearchInput('')
    setSearch('')
  }

  return {
    search,
    searchInput,
    setSearchInput,
    handleSearch,
    clearSearch,
  }
}
