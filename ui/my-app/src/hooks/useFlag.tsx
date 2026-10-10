import { createContext, useContext, type ReactNode } from 'react'

/**
 * Feature flags: which unreleased parts of the portal this customer sees.
 *
 * The API resolves them per customer (services/flags.py: their own override,
 * else the global default) and sends them with GET /me. The portal holds them
 * here so any screen can ask without threading them through props.
 *
 * Everything is off until /me answers, and for a name the API did not send,
 * so a slow or older API shows the portal as it was before the flag existed.
 * Flags decide what is drawn, never what a shared catalogue request asks for:
 * those answers are cached as one copy for every shopper.
 */
export type FeatureFlag =
  | 'lines'
  | 'lines_grouped'
  | 'line_page'
  | 'browse_views'
  | 'price_per_unit'
  | 'trip_planner'
  | 'personal'
  | 'alerts'
  | 'line_passport'
  | 'line_passport_rewards'
  | 'labs_status_board'
  | 'labs_line_map'
  | 'labs_field_note'
  | 'labs_cart_hint'
  | 'labs_home_rails'

type Flags = Partial<Record<string, boolean>>

const FlagsContext = createContext<Flags>({})

export function FlagsProvider({ flags, children }: { flags: Flags | null | undefined; children: ReactNode }) {
  return <FlagsContext.Provider value={flags ?? {}}>{children}</FlagsContext.Provider>
}

export function useFlag(name: FeatureFlag): boolean {
  return useContext(FlagsContext)[name] === true
}
