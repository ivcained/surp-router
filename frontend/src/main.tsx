import React from 'react'
import ReactDOM from 'react-dom/client'
import { PrivyProvider } from '@privy-io/react-auth'
import { base } from 'viem/chains'
import App from './App'

// Privy App ID — PUBLIC value (safe to embed in frontend code).
// The App Secret lives in .env.privy on the server and is never exposed.
const PRIVY_APP_ID = 'cmsnb7ylz000p0ejs4hkvmpes'

const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement)

root.render(
  <React.StrictMode>
    <PrivyProvider
      appId={PRIVY_APP_ID}
      config={{
        // Auto-create an embedded wallet the moment the user authenticates —
        // no separate "create wallet" step needed.
        embeddedWallets: {
          createOnLogin: 'users-without-wallets',
        },
        // Default chain for the embedded wallet — Base (where surp settles USDC).
        defaultChain: base,
        supportedChains: [base],
        // Appearance — match the surp dark theme.
        appearance: {
          theme: 'dark',
          accentColor: '#00ff9c',
        },
        // External wallet connectors — let crypto-native users connect MetaMask.
        externalWallets: {
          walletConnect: { enabled: true },
        },
        // Login methods configured in the Privy dashboard: email, passkeys, Farcaster.
        // The dashboard config controls which methods appear.
      }}
    >
      <App />
    </PrivyProvider>
  </React.StrictMode>,
)
