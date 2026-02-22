import { useState } from 'react'

export function usePagination(initialLimit: number = 50) {
  const [hasMore, setHasMore] = useState(true)
  const [limit] = useState(initialLimit)
  const [offset, setOffset] = useState(0)

  const loadMore = () => {
    setOffset(prev => prev + limit)
  }

  const reset = () => {
    setOffset(0)
    setHasMore(true)
  }

  const updateHasMore = (itemsReceived: number) => {
    setHasMore(itemsReceived === limit)
  }

  return {
    hasMore,
    limit,
    offset,
    loadMore,
    reset,
    updateHasMore,
  }
}
