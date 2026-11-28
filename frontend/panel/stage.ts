import { shallowRef, watch } from 'vue'
import type { Editor, Option } from './bridge'

export const weekdays = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]
export const stageCodes = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3']

export function labelWeekday(day: string, locale: string) {
  const date = new Date(Date.UTC(2026, 0, 5 + weekdays.indexOf(day)))
  return new Intl.DateTimeFormat(locale, { weekday: 'long', timeZone: 'UTC' }).format(date)
}

export function useStageOptions(editor: Editor, stageType: () => string, server: () => string) {
  const options = shallowRef<Option[]>([])
  const cache = new Map<string, Option[]>()
  watch(
    [stageType, server],
    async ([type, region], _, onCleanup) => {
      let current = true
      onCleanup(() => {
        current = false
      })
      const key = `${type}/${region}`
      options.value = cache.get(key) ?? []
      if (!region || cache.has(key)) return
      try {
        const response = await editor.request<{ data: Option[] }>('POST', '/stages/options', {
          type,
          server: region,
        })
        cache.set(key, response.data)
        if (current) options.value = response.data
      } catch (error) {
        if (current) editor.report(error)
      }
    },
    { immediate: true }
  )
  return options
}
