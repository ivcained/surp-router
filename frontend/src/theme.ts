import { createTheme } from '@mui/material/styles'

/**
 * surp phosphor-terminal theme — MUI's system dressed in our identity.
 * Pure black, phosphor green (#00ff9c), JetBrains Mono, CRT-tight borders.
 * We use MUI for states/elevation/typography consistency, not its default
 * light-blue look.
 */
const phosphor = '#00ff9c'
const bg = '#0a0a0a'
const bgAlt = '#111111'
const border = '#1e1e1e'
const borderBright = '#2e2e2e'
const fg = '#f0f0f0'
const dim = '#8a8a8a'
const yellow = '#ffd75f'
const red = '#ff5f5f'

export const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: phosphor, contrastText: '#001108' },
    secondary: { main: '#7df9ff', contrastText: '#001a1c' },
    background: { default: bg, paper: bgAlt },
    text: { primary: fg, secondary: dim },
    divider: border,
    error: { main: red },
    warning: { main: yellow },
    success: { main: phosphor },
    info: { main: '#7df9ff' },
  },
  typography: {
    fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace',
    h4: { fontWeight: 700, letterSpacing: '-0.02em' },
    h6: { fontWeight: 700 },
    subtitle2: { color: dim, fontSize: 12 },
    body2: { fontSize: 13 },
    caption: { fontSize: 11, color: dim },
    button: { textTransform: 'none', fontWeight: 600, letterSpacing: '0.02em' },
  },
  shape: { borderRadius: 4 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: bg,
          color: fg,
          fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: `1px solid ${border}`,
          boxShadow: 'none',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: `1px solid ${border}`,
          boxShadow: 'none',
          '&:hover': { borderColor: borderBright },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 4,
          padding: '6px 14px',
          fontSize: 12.5,
          '&:focus-visible': { outline: `1px solid ${phosphor}`, outlineOffset: 2 },
        },
        contained: {
          color: '#001108',
          fontWeight: 700,
          '&:hover': { backgroundColor: '#33ffb0' },
        },
        outlined: { borderColor: borderBright, color: fg, '&:hover': { borderColor: phosphor, color: phosphor, backgroundColor: 'rgba(0,255,156,0.06)' } },
        text: { color: dim, '&:hover': { color: phosphor } },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            backgroundColor: '#000',
            '& fieldset': { borderColor: borderBright },
            '&:hover fieldset': { borderColor: phosphor },
            '&.Mui-focused fieldset': { borderColor: phosphor, borderWidth: 1 },
            '& input': { color: fg, fontFamily: 'inherit', fontSize: 13 },
          },
        },
      },
    },
    MuiSelect: {
      styleOverrides: {
        root: {
          backgroundColor: '#000',
          fontSize: 13,
          '& .MuiOutlinedInput-notchedOutline': { borderColor: borderBright },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: phosphor },
        },
      },
    },
    MuiMenuItem: {
      styleOverrides: {
        root: { fontSize: 13, '&.Mui-selected': { backgroundColor: 'rgba(0,255,156,0.12)', color: phosphor } },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          backgroundColor: 'rgba(0,255,156,0.08)',
          border: `1px solid ${borderBright}`,
          color: fg,
          fontSize: 11.5,
          '& .MuiChip-label': { fontFamily: 'inherit' },
        },
        colorSuccess: { borderColor: phosphor, color: phosphor, backgroundColor: 'rgba(0,255,156,0.06)' },
      },
    },
    MuiTable: {
      styleOverrides: {
        root: { fontFamily: 'inherit' },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderBottom: `1px solid ${border}`,
          fontSize: 12.5,
          fontFamily: 'inherit',
        },
        head: { color: phosphor, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 700 },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontSize: 13,
          color: dim,
          '&.Mui-selected': { color: phosphor },
          '&.Mui-focusVisible': { outline: `1px solid ${phosphor}` },
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        indicator: { backgroundColor: phosphor },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: '#000',
          border: `1px solid ${borderBright}`,
          color: fg,
          fontSize: 11.5,
          fontFamily: 'inherit',
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: { backgroundColor: '#1a1a1a', height: 6, borderRadius: 3 },
        bar: { backgroundColor: phosphor },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          '&.Mui-selected': { backgroundColor: 'rgba(0,255,156,0.1)', color: phosphor, '&:hover': { backgroundColor: 'rgba(0,255,156,0.14)' } },
        },
      },
    },
  },
})

export default theme
