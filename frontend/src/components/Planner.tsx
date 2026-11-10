import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiClientError } from '../api/client'
import {
  completeReminder,
  createNote,
  createReminder,
  deleteNote,
  deleteReminder,
  fetchBriefing,
  fetchNotes,
  fetchReminders,
  type Briefing,
  type Reminder,
  type ShopNote,
} from '../api/planner'
import { subscribeShopRecords } from '../lib/shopRecords'

function todayISO() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
}

const RECUR_OPTIONS = [
  { value: 'none', label: 'Does not repeat' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
] as const

export function Planner() {
  const [tab, setTab] = useState<'briefing' | 'reminders' | 'notes'>('briefing')
  const [data, setData] = useState<Briefing | null>(null)
  const [openReminders, setOpenReminders] = useState<Reminder[]>([])
  const [completedReminders, setCompletedReminders] = useState<Reminder[]>([])
  const [allNotes, setAllNotes] = useState<ShopNote[]>([])
  const [noteQuery, setNoteQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [title, setTitle] = useState('')
  const [dueDate, setDueDate] = useState(todayISO)
  const [dueTime, setDueTime] = useState('09:00')
  const [recurrence, setRecurrence] = useState<(typeof RECUR_OPTIONS)[number]['value']>('none')
  const [noteBody, setNoteBody] = useState('')
  const noticeTimer = useRef<number | null>(null)
  const noteQueryRef = useRef('')

  const flash = useCallback((msg: string) => {
    setNotice(msg)
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current)
    noticeTimer.current = window.setTimeout(() => setNotice(null), 4000)
  }, [])

  const loadGen = useRef(0)
  const load = useCallback(async (silent = false) => {
    const gen = ++loadGen.current
    if (!silent) {
      setError(null)
      setLoading(true)
    }
    try {
      const [brief, listed, done, noteList] = await Promise.all([
        fetchBriefing(),
        fetchReminders('open'),
        fetchReminders('completed'),
        fetchNotes(noteQueryRef.current),
      ])
      if (gen !== loadGen.current) return
      setData(brief)
      setOpenReminders(listed.reminders)
      setCompletedReminders(done.reminders)
      setAllNotes(noteList.notes)
      if (!silent) setError(null)
    } catch (err) {
      if (gen !== loadGen.current) return
      setError(err instanceof ApiClientError ? err.message : 'Could not load planner.')
    } finally {
      if (gen === loadGen.current && !silent) setLoading(false)
    }
  }, [])

  useEffect(() => subscribeShopRecords(() => void load(true)), [load])

  useEffect(() => {
    void load()
    const id = window.setInterval(() => void load(true), 30000)
    return () => {
      window.clearInterval(id)
      if (noticeTimer.current) window.clearTimeout(noticeTimer.current)
    }
  }, [load])

  useEffect(() => {
    noteQueryRef.current = noteQuery
    const t = window.setTimeout(() => {
      void fetchNotes(noteQuery)
        .then((r) => setAllNotes(r.notes))
        .catch(() => {
          /* load() surfaces planner errors */
        })
    }, 200)
    return () => window.clearTimeout(t)
  }, [noteQuery])

  const overdue = data?.overdue ?? []
  const briefingNotes: ShopNote[] = data?.notes ?? []
  const notes: ShopNote[] = allNotes
  const upcomingTotal = data?.upcoming_total ?? data?.upcoming.length ?? 0
  const upcomingLimit = data?.upcoming_limit ?? 8

  async function run(action: () => Promise<string | void>, success: string) {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const msg = await action()
      flash(typeof msg === 'string' && msg ? msg : success)
      await load(true)
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  function confirmComplete(r: Reminder) {
    const extra =
      r.recurrence && r.recurrence !== 'none'
        ? ' This repeats; the next due date will move forward.'
        : ''
    if (!window.confirm(`Mark “${r.title}” done?${extra}`)) return
    void run(async () => {
      const res = await completeReminder(r.id)
      const next = res.reminder
      if (next.recurrence && next.recurrence !== 'none') {
        return `Done. Next: ${next.due_date}${next.due_time ? ` ${next.due_time}` : ''}`
      }
      return 'Reminder marked done.'
    }, 'Reminder marked done.')
  }

  return (
    <section className="grid min-w-0 max-w-full gap-4 overflow-x-hidden">
      <div className="grid min-w-0 grid-cols-3 gap-2">
        {(['briefing', 'reminders', 'notes'] as const).map((key) => (
          <button
            key={key}
            type="button"
            className={`min-h-12 min-w-0 rounded-xl px-2 text-sm font-medium sm:text-base ${
              tab === key ? 'bg-teal-800 text-white' : 'border border-stone-300 bg-white'
            }`}
            onClick={() => setTab(key)}
          >
            {key === 'briefing' ? 'Today' : key === 'reminders' ? 'Reminders' : 'Notes'}
          </button>
        ))}
      </div>
      {loading && !data && <p className="text-stone-700">Loading planner…</p>}
      {error && (
        <p className="break-words text-red-800" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="break-words text-emerald-800" role="status">
          {notice}
        </p>
      )}
      {data && (
        <p className="text-sm text-stone-600">
          {data.notify_note} Overdue: {overdue.length}
        </p>
      )}
      {tab === 'briefing' && (
        <div className="grid min-w-0 gap-4">
          <Block
            title="Overdue"
            empty="Nothing overdue."
            items={overdue}
            busy={busy}
            onDone={confirmComplete}
          />
          <Block
            title="Today"
            empty="No reminders today."
            items={data?.today ?? []}
            busy={busy}
            onDone={confirmComplete}
          />
          <Block
            title="Upcoming"
            empty="Nothing upcoming."
            items={data?.upcoming ?? []}
            busy={busy}
            onDone={confirmComplete}
          />
          {upcomingTotal > upcomingLimit && (
            <p className="text-sm text-stone-700">
              Showing the next {upcomingLimit} of {upcomingTotal} upcoming reminders.{' '}
              <button
                type="button"
                className="font-medium text-amber-900 underline"
                onClick={() => setTab('reminders')}
              >
                Open full Reminders list
              </button>
            </p>
          )}
          {upcomingTotal > 0 && upcomingTotal <= upcomingLimit && (
            <p className="text-sm text-stone-600">
              Today shows at most {upcomingLimit} upcoming items.{' '}
              <button
                type="button"
                className="font-medium text-amber-900 underline"
                onClick={() => setTab('reminders')}
              >
                See all reminders
              </button>
            </p>
          )}
          {upcomingTotal === 0 && (
            <p className="text-sm text-stone-600">
              <button
                type="button"
                className="font-medium text-amber-900 underline"
                onClick={() => setTab('reminders')}
              >
                Open Reminders
              </button>{' '}
              for the complete list.
            </p>
          )}
          <div className="min-w-0 rounded-2xl border border-stone-200 bg-white p-4">
            <h3 className="text-lg font-semibold">Notes</h3>
            {briefingNotes.length === 0 ? (
              <p className="mt-2 text-stone-600">No notes.</p>
            ) : (
              briefingNotes.map((n) => (
                <p key={n.id} className="mt-2 break-words text-base">
                  {n.body}
                </p>
              ))
            )}
          </div>
        </div>
      )}
      {tab === 'reminders' && (
        <div className="grid min-w-0 gap-3 rounded-2xl border border-stone-200 bg-white p-4">
          <label className="min-w-0 text-sm">
            What
            <input
              className="mt-1 min-h-12 w-full min-w-0 max-w-full rounded-xl border px-3"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="min-w-0 text-sm">
              Date
              <input
                className="mt-1 min-h-12 w-full min-w-0 max-w-full rounded-xl border px-3"
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
              />
            </label>
            <label className="min-w-0 text-sm">
              Time
              <input
                className="mt-1 min-h-12 w-full min-w-0 max-w-full rounded-xl border px-3"
                type="time"
                value={dueTime}
                onChange={(e) => setDueTime(e.target.value)}
              />
            </label>
          </div>
          <label className="min-w-0 text-sm">
            Repeat
            <select
              className="mt-1 min-h-12 w-full min-w-0 max-w-full rounded-xl border px-3"
              value={recurrence}
              onChange={(e) => setRecurrence(e.target.value as typeof recurrence)}
            >
              {RECUR_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={busy}
            className="min-h-12 rounded-xl bg-teal-800 text-white disabled:opacity-60"
            onClick={() =>
              void run(async () => {
                await createReminder({
                  title,
                  due_date: dueDate,
                  due_time: dueTime || null,
                  recurrence,
                })
                setTitle('')
                setRecurrence('none')
              }, 'Reminder saved.')
            }
          >
            Save reminder
          </button>
          <Block
            title="Overdue"
            empty="Nothing overdue."
            items={openReminders.filter((r) => r.overdue)}
            busy={busy}
            onDone={confirmComplete}
            onDelete={(r) => {
              if (!window.confirm(`Delete ${r.title}?`)) return
              void run(async () => {
                await deleteReminder(r.id)
              }, 'Reminder deleted.')
            }}
          />
          <Block
            title="Open"
            empty="No open reminders."
            items={openReminders.filter((r) => !r.overdue)}
            busy={busy}
            onDone={confirmComplete}
            onDelete={(r) => {
              if (!window.confirm(`Delete ${r.title}?`)) return
              void run(async () => {
                await deleteReminder(r.id)
              }, 'Reminder deleted.')
            }}
          />
          <Block
            title="Completed"
            empty="No completed reminders."
            items={completedReminders}
            busy={busy}
          />
        </div>
      )}
      {tab === 'notes' && (
        <div className="grid min-w-0 gap-3 rounded-2xl border border-stone-200 bg-white p-4">
          <label className="min-w-0 text-sm">
            Search notes
            <input
              className="mt-1 min-h-12 w-full min-w-0 max-w-full rounded-xl border px-3"
              value={noteQuery}
              onChange={(e) => setNoteQuery(e.target.value)}
              placeholder="Search in English, हिंदी, ಕನ್ನಡ, मराठी"
            />
          </label>
          <textarea
            className="min-h-24 w-full min-w-0 rounded-xl border p-3"
            value={noteBody}
            onChange={(e) => setNoteBody(e.target.value)}
            placeholder="Supplier will deliver rice tomorrow"
          />
          <button
            type="button"
            disabled={busy}
            className="min-h-12 rounded-xl bg-amber-800 text-white disabled:opacity-60"
            onClick={() =>
              void run(async () => {
                await createNote(noteBody)
                setNoteBody('')
              }, 'Note saved.')
            }
          >
            Save note
          </button>
          {notes.length === 0 && <p className="text-stone-600">No notes.</p>}
          {notes.map((n) => (
            <div
              key={n.id}
              className="flex min-w-0 flex-col gap-2 border-b border-stone-100 py-2 sm:flex-row sm:items-start sm:justify-between"
            >
              <p className="min-w-0 break-words">{n.body}</p>
              <button
                type="button"
                disabled={busy}
                className="min-h-12 shrink-0 rounded-lg border px-3 text-red-800 disabled:opacity-60"
                onClick={() => {
                  if (!window.confirm('Delete this note?')) return
                  void run(async () => {
                    await deleteNote(n.id)
                  }, 'Note deleted.')
                }}
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function Block({
  title,
  empty,
  items,
  busy,
  onDone,
  onDelete,
}: {
  title: string
  empty: string
  items: Reminder[]
  busy: boolean
  onDone?: (r: Reminder) => void
  onDelete?: (r: Reminder) => void
}) {
  return (
    <div className="min-w-0 rounded-2xl border border-stone-200 bg-white p-4">
      <h3 className="text-lg font-semibold">{title}</h3>
      {items.length === 0 ? (
        <p className="mt-2 text-stone-600">{empty}</p>
      ) : (
        <ul className="mt-2 grid gap-2">
          {items.map((r) => (
            <li
              key={r.id}
              className={`flex min-w-0 flex-col gap-2 rounded-xl px-3 py-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between ${
                r.overdue ? 'bg-red-50' : 'bg-stone-50'
              }`}
            >
              <span className="min-w-0 break-words">
                <span className="font-medium">{r.title}</span>
                {r.overdue && (
                  <span className="ml-2 text-sm font-medium text-red-800">Overdue</span>
                )}
                {r.status === 'completed' && (
                  <span className="ml-2 text-sm font-medium text-stone-600">Completed</span>
                )}
                <span className="ml-2 block text-sm text-stone-500 sm:inline">
                  {r.due_date} {r.due_time ?? ''}
                  {r.recurrence && r.recurrence !== 'none' ? ` · ${r.recurrence}` : ''}
                </span>
              </span>
              <span className="flex min-w-0 flex-wrap gap-2">
                {onDone && (
                  <button
                    type="button"
                    disabled={busy}
                    className="min-h-12 rounded-lg border px-3 py-1 disabled:opacity-60"
                    onClick={() => onDone(r)}
                  >
                    Done
                  </button>
                )}
                {onDelete && (
                  <button
                    type="button"
                    disabled={busy}
                    className="min-h-12 rounded-lg border px-3 py-1 text-red-800 disabled:opacity-60"
                    onClick={() => onDelete(r)}
                  >
                    Delete
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
