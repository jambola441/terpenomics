"""POS connectors: pull partner-store orders into pos_orders.

See POS_CONNECTORS.md. The pieces:

  base.py         the connector protocol and the normalized order shape
  square.py       Square (OAuth, Orders API, Customers API)
  registry.py     provider name -> configured connector
  crypto.py       encryption for stored OAuth credentials
  oauth_state.py  signed `state` for the OAuth round-trip
  store.py        the only code that writes pos_orders / partner_locations
  matching.py     order -> Terpee customer (link, phone, receipt claim)
  sync.py         one sync of one connection, and connect/disconnect
"""
