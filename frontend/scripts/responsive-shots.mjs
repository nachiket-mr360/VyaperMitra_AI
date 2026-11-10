import { spawn } from 'node:child_process'
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const out = join(root, 'responsive-shots')
mkdirSync(out, { recursive: true })
const PORT = String(4300 + Math.floor(Math.random() * 500))

const emptyDash = {
  ok: true,
  timezone: 'Asia/Kolkata',
  cash_note: 'Amounts are recorded sales, not cash received.',
  profit_note: 'Profit is not shown. Purchase cost is often unknown.',
  today: { date: '2026-11-08', total_amount: 0, transactions: 0 },
  yesterday: { date: '2026-11-07', total_amount: 0, transactions: 0 },
  period: { from: '2026-11-02', to: '2026-11-08', total_amount: 0, transactions: 0 },
  trend: [],
  best_sellers: [],
  by_product: [],
  inventory: [],
  low_stock: [],
}

const fullDash = {
  ok: true,
  timezone: 'Asia/Kolkata',
  cash_note: 'Amounts are recorded sales, not cash received.',
  profit_note: 'Profit is not shown. Purchase cost is often unknown.',
  today: { date: '2026-11-08', total_amount: 4200, transactions: 6 },
  yesterday: { date: '2026-11-07', total_amount: 3100, transactions: 4 },
  period: { from: '2026-11-02', to: '2026-11-08', total_amount: 18600, transactions: 28 },
  trend: [
    { date: '2026-11-02', total_amount: 1800, transactions: 3 },
    { date: '2026-11-03', total_amount: 2200, transactions: 4 },
    { date: '2026-11-04', total_amount: 1500, transactions: 2 },
    { date: '2026-11-05', total_amount: 2600, transactions: 5 },
    { date: '2026-11-06', total_amount: 3200, transactions: 4 },
    { date: '2026-11-07', total_amount: 3100, transactions: 4 },
    { date: '2026-11-08', total_amount: 4200, transactions: 6 },
  ],
  best_sellers: [
    { product_id: 1, name: 'Rice', unit: 'kg', quantity: 40, amount: 8000 },
    { product_id: 2, name: 'Toor dal', unit: 'kg', quantity: 12, amount: 5400 },
    { product_id: 3, name: 'Oil', unit: 'l', quantity: 8, amount: 3200 },
  ],
  by_product: [
    { product_id: 1, name: 'Rice', unit: 'kg', quantity: 40, amount: 8000 },
    { product_id: 2, name: 'Toor dal', unit: 'kg', quantity: 12, amount: 5400 },
    { product_id: 3, name: 'Oil', unit: 'l', quantity: 8, amount: 3200 },
  ],
  inventory: [
    { id: 1, name: 'Rice', unit: 'kg', current_stock: 48, stock_known: true, low_stock: false },
    { id: 2, name: 'Toor dal', unit: 'kg', current_stock: 9, stock_known: true, low_stock: true },
    { id: 3, name: 'Oil', unit: 'l', current_stock: 14, stock_known: true, low_stock: false },
  ],
  low_stock: [{ id: 2, name: 'Toor dal', unit: 'kg', current_stock: 9, stock_known: true, low_stock: true }],
}

const briefing = {
  ok: true,
  timezone: 'Asia/Kolkata',
  date: '2026-11-08',
  today: [],
  overdue: [],
  upcoming: [],
  notes: [],
  notify_note: 'Reminders stay in the app.',
}

async function mock(page, dash) {
  await page.unroute('**/api/**').catch(() => {})
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    let body = { ok: true }
    if (url.includes('/analytics/dashboard')) body = dash
    else if (url.includes('/reminders/briefing')) body = briefing
    else if (url.includes('/reminders')) body = { ok: true, reminders: [] }
    else if (url.includes('/notes')) body = { ok: true, notes: [] }
    else if (url.includes('/products')) {
      body = { ok: true, products: dash.inventory.map((p) => ({ ...p, active: true })) }
    } else if (url.includes('/sales')) body = { ok: true, sales: [] }
    else if (url.includes('/health')) {
      body = {
        ok: true,
        app: 'VyaparMitra',
        phase: 7,
        timezone: 'Asia/Kolkata',
        server_time: '2026-11-08T00:00:00',
        database: { connected: true, demo: false },
        gnani: { enabled: false, configured: false, integration: 'prisma_stt', note: 'test' },
      }
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
}

async function overflow(page) {
  return page.evaluate(() => {
    const el = document.querySelector('.vm-main-scroll') || document.documentElement
    return {
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
      overflowing: el.scrollWidth > el.clientWidth + 1,
    }
  })
}

async function assertFabClear(page) {
  const hit = await page.evaluate(() => {
    const fab = document.querySelector('[data-testid="voice-fab"]')
    const overlay = document.querySelector('[role="dialog"]')
    if (!fab || overlay) return null
    const fr = fab.getBoundingClientRect()
    const samples = [
      [fr.left + fr.width / 2, fr.top + fr.height / 2],
      [fr.left + 8, fr.top + 8],
      [fr.right - 8, fr.top + 8],
      [fr.left + fr.width / 2, fr.top + 12],
    ]
    fab.style.pointerEvents = 'none'
    let found = null
    for (const [x, y] of samples) {
      const el = document.elementFromPoint(x, y)
      if (!el) continue
      const block = el.closest('.vm-glass, table, h1, h2, p, li, label, button:not([data-testid="voice-fab"])')
      const nav = el.closest('nav')
      const header = el.closest('header')
      if (nav || header) continue
      if (block && !block.classList.contains('vm-main-scroll')) {
        found = (block.textContent || '').trim().slice(0, 90)
        break
      }
    }
    fab.style.pointerEvents = ''
    return found
  })
  if (hit) throw new Error(`FAB overlaps content: ${hit}`)
}

async function shot(page, name) {
  await page.waitForTimeout(name.includes('chart') ? 900 : 250)
  await page.screenshot({ path: join(out, name), fullPage: false })
  const ov = await overflow(page)
  console.log(name, ov)
  if (ov.overflowing) throw new Error(`Horizontal overflow on ${name}`)
  if (!name.includes('voice')) await assertFabClear(page)
}

const viewports = {
  '375x812': { width: 375, height: 812 },
  '390x844': { width: 390, height: 844 },
  '430x932': { width: 430, height: 932 },
  '768x1024': { width: 768, height: 1024 },
  '1280x800': { width: 1280, height: 800 },
  '1920x1080': { width: 1920, height: 1080 },
}

let base = `http://127.0.0.1:${PORT}`
const preview = spawn('npx', ['vite', 'preview', '--host', '127.0.0.1', `--port`, PORT, '--strictPort'], {
  cwd: root,
  shell: true,
  stdio: ['ignore', 'pipe', 'pipe'],
})
await new Promise((resolve, reject) => {
  const t = setTimeout(() => reject(new Error('preview timeout')), 30000)
  const onData = (buf) => {
    const s = buf.toString()
    process.stdout.write(s)
    const plain = s.replace(/\x1B\[[0-9;]*m/g, '')
    const m = plain.match(/127\.0\.0\.1:(\d+)/)
    if (m || plain.includes('Local')) {
      if (m) base = `http://127.0.0.1:${m[1]}`
      clearTimeout(t)
      resolve()
    }
  }
  preview.stdout.on('data', onData)
  preview.stderr.on('data', onData)
  preview.on('error', reject)
})

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: viewports['375x812'] })
await mock(page, emptyDash)
await page.goto(`${base}/`, { waitUntil: 'networkidle' })

await page.setViewportSize(viewports['375x812'])
await shot(page, '375-dashboard.png')
await page.locator('[data-testid="voice-fab"]').locator('visible=true').click()
await shot(page, '375-voice.png')
await page.getByRole('button', { name: 'Close' }).click()

await page.setViewportSize(viewports['390x844'])
await page.getByTestId('mnav-inventory').click()
await shot(page, '390-inventory.png')

await page.setViewportSize(viewports['430x932'])
await page.getByTestId('mnav-planner').click()
await shot(page, '430-planner.png')

await page.setViewportSize(viewports['768x1024'])
await page.getByTestId('mnav-dashboard').click()
await shot(page, '768-dashboard.png')

await page.setViewportSize(viewports['1280x800'])
await page.getByTestId('nav-dashboard').click()
await shot(page, '1280-dashboard.png')
await page.locator('[data-testid="voice-fab"]').locator('visible=true').click()
await shot(page, '1280-voice.png')
await page.getByRole('button', { name: 'Close' }).click()

await page.setViewportSize(viewports['1920x1080'])
await shot(page, '1920-dashboard.png')

for (const id of ['inventory', 'sales', 'planner', 'insights', 'settings']) {
  await page.getByTestId(`nav-${id}`).first().click()
  await page.waitForTimeout(250)
  const ov = await overflow(page)
  console.log('1920', id, ov)
  if (ov.overflowing) throw new Error(`overflow ${id}`)
}

await mock(page, fullDash)
await page.goto(`${base}/`, { waitUntil: 'networkidle' })
await page.setViewportSize(viewports['375x812'])
await page.getByTestId('mnav-dashboard').click()
await shot(page, '375-dashboard-full.png')
await page.getByRole('heading', { name: 'Sales trend' }).scrollIntoViewIfNeeded()
await shot(page, '375-dashboard-full-charts.png')
await page.setViewportSize(viewports['768x1024'])
await shot(page, '768-dashboard-full.png')
await page.getByRole('heading', { name: 'Sales trend' }).scrollIntoViewIfNeeded()
await shot(page, '768-dashboard-full-charts.png')
await page.setViewportSize(viewports['1280x800'])
await shot(page, '1280-dashboard-full.png')
await page.getByRole('heading', { name: 'Sales trend' }).scrollIntoViewIfNeeded()
await shot(page, '1280-dashboard-full-charts.png')
await page.setViewportSize(viewports['1920x1080'])
await shot(page, '1920-dashboard-full.png')
await page.getByRole('heading', { name: 'Product performance' }).scrollIntoViewIfNeeded()
await shot(page, '1920-dashboard-full-charts.png')

await browser.close()
preview.kill()
console.log('shots written to', out)
