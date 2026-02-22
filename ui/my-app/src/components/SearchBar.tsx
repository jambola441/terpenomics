import React from 'react'

type SearchBarProps = {
  value: string
  onChange: (value: string) => void
  onSearch: (e: React.FormEvent) => void
  onClear: () => void
  placeholder?: string
  disabled?: boolean
  showClearButton?: boolean
}

export function SearchBar({
  value,
  onChange,
  onSearch,
  onClear,
  placeholder = 'Search...',
  disabled = false,
  showClearButton = true,
}: SearchBarProps) {
  return (
    <form onSubmit={onSearch} style={{ display: 'flex', gap: 8 }}>
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{ width: 300, padding: '6px 12px' }}
        disabled={disabled}
      />
      <button type="submit" disabled={disabled}>
        Search
      </button>
      {showClearButton && value && (
        <button type="button" onClick={onClear} disabled={disabled}>
          Clear
        </button>
      )}
    </form>
  )
}
