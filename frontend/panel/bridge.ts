import { computed, ref, shallowReactive } from 'vue'
import { messageKeys } from './messages'

export type Value = string | number | boolean | null
export type Fields = Record<string, Value>
type Config = Record<string, Fields>
export type Option = { label: string; value: string }
type Change = { group: string; field: string; value: Value }
type Target = { scriptId: string; userId: string; planId: string }
type State = {
  locale: string
  i18nRevision: number
  locked: boolean
  busy: boolean
  fieldErrors?: Record<string, string>
}
type Snapshot = { config: Config }
type PickedPath = { path?: string | null; cancelled?: boolean }
type Reply<T> = { ok: boolean; status: number; data: T }
type Envelope = { code?: number; message?: string; detail?: string }

declare function connectPanel(): {
  getContext(): Promise<State & Snapshot & { target: Target }>
  translate(keys: string[]): Promise<{ locale: string; messages: Record<string, string> }>
  request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<Reply<T & Envelope>>
  saveConfig(
    changes: Change[],
    phase: 'draft' | 'commit'
  ): Promise<{ ok: boolean; message?: string }>
  pickPath(options: {
    mode: 'file'
    filters: { name: string; extensions: string[] }[]
  }): Promise<PickedPath>
  onStateChange(callback: (state: State) => void): void
  onConfigReloaded(callback: (snapshot: Snapshot) => void): void
}

export function usePanel() {
  const panel = connectPanel()
  const config = ref<Config>({})
  const target = ref<Target>()
  const error = ref('')
  const messages = ref<Record<string, string>>({})
  const state = ref<State>()
  const saving = ref(false)
  const changes = shallowReactive(new Map<string, Change>())
  const disabled = computed(
    () => !state.value || state.value.locked || state.value.busy || saving.value
  )
  let translationVersion = 0
  let submitted = Promise.resolve()

  const t = (key: string) => messages.value[`panel.editor.${key}`] ?? key
  const report = (cause: unknown) => {
    error.value = cause instanceof Error ? cause.message : String(cause)
  }

  async function applyState(next: State) {
    const previous = state.value
    state.value = next
    if (previous?.i18nRevision === next.i18nRevision && previous.locale === next.locale) return
    const version = ++translationVersion
    const result = await panel.translate(messageKeys.map(key => `panel.editor.${key}`))
    if (version !== translationVersion) return
    document.documentElement.lang = result.locale
    messages.value = result.messages
  }

  function applyConfig({ config: latest }: Snapshot) {
    config.value = latest
    for (const [key, { group, field, value }] of changes) {
      if (latest[group]?.[field] !== value) changes.delete(key)
    }
  }

  async function initialize() {
    const context = await panel.getContext()
    applyConfig(context)
    panel.onStateChange(next => {
      void applyState(next).catch(report)
    })
    panel.onConfigReloaded(applyConfig)
    await applyState(context)
    target.value = context.target
  }

  async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
    const { ok, status, data } = await panel.request<T>(method, path, body)
    if (!ok || (data.code !== undefined && data.code !== 200)) {
      throw new Error(data.message || data.detail || `HTTP ${status}`)
    }
    return data
  }

  async function update(group: string, fields: Fields) {
    const batch = Object.entries(fields)
      .map(([field, value]) => ({ group, field, value }))
      .filter(({ field, value }) => config.value[group][field] !== value)
    if (!batch.length) return
    for (const change of batch) {
      config.value[group][change.field] = change.value
      changes.set(`${group}.${change.field}`, change)
    }
    submitted = submitted
      .then(async () => {
        const result = await panel.saveConfig(batch, 'draft')
        if (!result.ok) throw new Error(result.message)
      })
      .catch(report)
    await submitted
  }

  async function save(keys = [...changes.keys()]) {
    error.value = ''
    saving.value = true
    try {
      await submitted
      const batch = keys.flatMap(key => {
        const change = changes.get(key)
        return change ? [change] : []
      })
      const result = await panel.saveConfig(batch, 'commit')
      if (!result.ok) throw new Error(result.message)
      for (const key of keys) changes.delete(key)
      return true
    } catch (cause) {
      report(cause)
      return false
    } finally {
      saving.value = false
    }
  }

  async function commit(group: string, fields: Fields) {
    await update(group, fields)
    return save(Object.keys(fields).map(field => `${group}.${field}`))
  }

  return {
    config,
    target,
    error,
    state,
    disabled,
    changes,
    t,
    report,
    initialize,
    request,
    update,
    save,
    commit,
    pickPath: panel.pickPath,
  }
}

export type Editor = ReturnType<typeof usePanel>
