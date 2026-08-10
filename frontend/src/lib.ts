import { usePrivy, useWallets } from '@privy-io/react-auth'

/** Hook to get an authenticated fetch function that injects the Privy token. */
export function useAuthFetch() {
  const { getAccessToken } = usePrivy()
  const { wallets } = useWallets()
  const activeWallet = wallets[0]

  return async (url: string, options: RequestInit = {}) => {
    const token = await activeWallet?.getAccessToken?.()
    if (!token) throw new Error('not authenticated')
    const headers = new Headers(options.headers)
    headers.set('Authorization', `Bearer ${token}`)
    if (options.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
    return fetch(url, { ...options, headers })
  }
}

/** Format cents as USD. */
export function fmtUSD(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

/** Format a unix timestamp as a readable date/time. */
export function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

/** Shorten a wallet address for display. */
export function shortAddr(addr: string): string {
  if (!addr || addr.length < 10) return addr
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`
}

/** Shorten a tx hash for display + link to basescan. */
export function txLink(txHash: string): { short: string, url: string } | null {
  if (!txHash) return null
  return {
    short: `${txHash.slice(0, 6)}...${txHash.slice(-4)}`,
    url: `https://basescan.org/tx/${txHash}`,
  }
}
