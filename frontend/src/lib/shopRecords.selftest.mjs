import assert from 'node:assert/strict'

const SHOP_MUTATION_INTENTS = new Set([
  'record_sale',
  'purchase_stock',
  'cancel_sale',
  'return_sale',
  'correct_sale',
  'create_reminder',
  'complete_reminder',
  'delete_reminder',
  'save_note',
  'delete_note',
])

function isShopMutationIntent(intent) {
  return !!intent && SHOP_MUTATION_INTENTS.has(intent)
}

function maybeNotify(opts, notify) {
  if (!opts.executed) return
  if (isShopMutationIntent(opts.intent) || isShopMutationIntent(opts.pendingIntent)) {
    notify()
    return
  }
  if (opts.intent === 'confirmation' && !opts.pendingIntent) notify()
}

function ttsLanguage(...candidates) {
  const TTS_LANGS = new Set(['en', 'hi', 'kn', 'mr'])
  for (const raw of candidates) {
    if (!raw || typeof raw !== 'string') continue
    const base = raw.trim().toLowerCase().split(/[-_]/)[0]
    if (base && TTS_LANGS.has(base)) return base
  }
  return 'en'
}

assert.equal(ttsLanguage('hi'), 'hi')
assert.equal(ttsLanguage('kn-IN'), 'kn')
assert.equal(ttsLanguage('mr-IN', 'en'), 'mr')
assert.equal(ttsLanguage(undefined, 'en'), 'en')
assert.equal(ttsLanguage('xx', null), 'en')
assert.equal(ttsLanguage('HI'), 'hi')

let n = 0
const bump = () => {
  n += 1
}
maybeNotify({ executed: false, intent: 'record_sale' }, bump)
assert.equal(n, 0)
maybeNotify({ executed: true, intent: 'record_sale' }, bump)
assert.equal(n, 1)
maybeNotify({ executed: true, intent: 'confirmation', pendingIntent: 'record_sale' }, bump)
assert.equal(n, 2)
maybeNotify({ executed: true, intent: 'create_reminder' }, bump)
assert.equal(n, 3)
maybeNotify({ executed: true, intent: 'confirmation', pendingIntent: 'create_reminder' }, bump)
assert.equal(n, 4)
maybeNotify({ executed: true, intent: 'confirmation' }, bump)
assert.equal(n, 5)

console.log('shopRecords/ttsLanguage selftest ok')
