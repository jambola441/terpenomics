import React from 'react'
import { t } from '../theme'

const inputStyle: React.CSSProperties = {
  width: 300, padding: '6px 12px', fontSize: 13, borderRadius: 8,
  background: t.surface2, border: `1px solid ${t.border}`, color: t.text1, outline: 'none',
}
const buttonStyle: React.CSSProperties = {
  padding: '6px 12px', fontSize: 13, borderRadius: 8,
  background: t.surface2, border: `1px solid ${t.border}`, color: t.text2, cursor: 'pointer',
}

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
        style={inputStyle}
        disabled={disabled}
      />
      <button type="submit" disabled={disabled} style={buttonStyle}>
        Search
      </button>
      {showClearButton && value && (
        <button type="button" onClick={onClear} disabled={disabled} style={buttonStyle}>
          Clear
        </button>
      )}
    </form>
  )
}
