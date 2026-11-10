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
  'create_note',
  'delete_note',
])

type Listener = () => void

const listeners = new Set<Listener>()

export function isShopMutationIntent(intent: string | null | undefined): boolean {
  return !!intent && SHOP_MUTATION_INTENTS.has(intent)
}

export function subscribeShopRecords(fn: Listener): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

/** Call only after a confirmed shop mutation succeeded. */
export function notifyShopRecordsChanged(): void {
  listeners.forEach((fn) => {
    try {
      fn()
    } catch {
      /* page load errors stay local */
    }
  })
}

export function maybeNotifyShopMutation(opts: {
  executed?: boolean
  intent?: string | null
  pendingIntent?: string | null
}): void {
  if (!opts.executed) return
  if (isShopMutationIntent(opts.intent) || isShopMutationIntent(opts.pendingIntent)) {
    notifyShopRecordsChanged()
    return
  }
  if (opts.intent === 'confirmation' && !opts.pendingIntent) {
    notifyShopRecordsChanged()
  }
}
