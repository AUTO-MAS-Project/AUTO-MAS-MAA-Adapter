<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import FieldInput from './FieldInput.vue'
import type { Editor, Option } from './bridge'
import type { CultivateGoalKind, CultivateTargetRow } from '../user/cultivateTargets'

type Result = {
  total: number
  ready: number
  trainable: number
  missing: number
  operators: {
    operatorId: string
    name: string
    owned: boolean
    goals: { kind: CultivateGoalKind; target_id: string; to_level: number }[]
  }[]
  assignments: { id: number; title: string; stage: string; state: string }[]
}
type SourceState = { count: number; running: boolean; available: boolean; error: string }

const props = defineProps<{ editor: Editor; binding: string }>()
const emit = defineEmits<{ merge: [targets: CultivateTargetRow[]] }>()
const { target, t, request, report } = props.editor
const source = ref('all')
const query = ref('')
const coverage = ref(90)
const requireModules = ref(true)
const ignoreLevelGaps = ref(false)
const busy = ref(false)
const sourceState = ref<SourceState>()
const authors = ref<Option[]>([])
const authorName = ref('')
const result = ref<Result>()
const selected = ref<string[]>([])
let poll: ReturnType<typeof setTimeout> | undefined
let sourceVersion = 0
const operators = computed(
  () => result.value?.operators.filter(item => item.owned && item.goals.length) ?? []
)

async function run(operation: () => Promise<void>) {
  busy.value = true
  try {
    await operation()
  } catch (error) {
    report(error)
  } finally {
    busy.value = false
  }
}

function analyze() {
  const version = sourceVersion
  result.value = undefined
  void run(async () => {
    const { scriptId, userId } = target.value!
    const analyzed = await request<Result>('POST', '/maa/copilot/analyze', {
      scriptId,
      userId,
      bindingKey: props.binding,
      source: source.value,
      query: query.value.trim(),
      coverage: coverage.value,
      requireModules: requireModules.value,
      ignoreLevelGaps: ignoreLevelGaps.value,
    })
    if (version !== sourceVersion) return
    result.value = analyzed
    selected.value = operators.value.map(item => item.operatorId)
  })
}

function searchAuthors() {
  void run(async () => {
    const response = await request<{ data: Option[] }>('POST', '/maa/copilot/authors', {
      keyword: authorName.value.trim(),
    })
    authors.value = response.data
    query.value = authors.value.length === 1 ? authors.value[0].value : ''
  })
}

function syncSource(refresh: boolean) {
  const version = ++sourceVersion
  clearTimeout(poll)
  const scope = { source: source.value, query: query.value.trim() }
  const sync = async (action: 'load' | 'refresh' | 'status') => {
    try {
      const next = await request<SourceState>('POST', '/maa/copilot/source', { ...scope, action })
      if (version !== sourceVersion) return
      sourceState.value = next
      if (next.running)
        poll = setTimeout(() => {
          void sync('status')
        }, 1500)
    } catch (error) {
      if (version === sourceVersion) {
        sourceState.value = undefined
        report(error)
      }
    }
  }
  void run(() => sync(refresh ? 'refresh' : 'load'))
}

function clearSource() {
  sourceVersion++
  clearTimeout(poll)
  result.value = undefined
  sourceState.value = undefined
}

function changeSource(value: unknown) {
  source.value = String(value)
  query.value = ''
}

watch([source, query, () => props.binding], clearSource)
watch(authorName, () => {
  authors.value = []
  query.value = ''
})
watch([coverage, requireModules, ignoreLevelGaps], () => {
  result.value = undefined
})
onScopeDispose(clearSource)

function merge() {
  emit(
    'merge',
    operators.value
      .filter(item => selected.value.includes(item.operatorId))
      .map(item => ({
        operatorId: item.operatorId,
        rawGoals: item.goals,
      }))
  )
}
</script>

<template>
  <details>
    <summary>{{ t('copilot') }}</summary>
    <fieldset class="stack" :disabled="busy || !binding">
      <div class="grid">
        <FieldInput
          :label="t('copilotSource')"
          :value="source"
          :options="
            ['all', 'author', 'set', 'copilot'].map(value => ({
              value,
              label: t(`source-${value}`),
            }))
          "
          @change="changeSource"
        />
        <label v-if="source === 'set' || source === 'copilot'">
          {{ t('copilotQuery') }}<input v-model="query" />
        </label>
        <FieldInput
          :label="t('coverage')"
          :value="coverage"
          :min="1"
          :max="100"
          @change="coverage = Number($event)"
        />
        <FieldInput
          :label="t('requireModules')"
          :value="requireModules"
          @change="requireModules = Boolean($event)"
        />
        <FieldInput
          :label="t('ignoreLevelGaps')"
          :value="ignoreLevelGaps"
          @change="ignoreLevelGaps = Boolean($event)"
        />
      </div>
      <div v-if="source === 'author'" class="toolbar">
        <input
          v-model="authorName"
          :aria-label="t('searchAuthors')"
          @keydown.enter="searchAuthors"
        />
        <button type="button" :disabled="!authorName.trim()" @click="searchAuthors">
          {{ t('searchAuthors') }}
        </button>
        <select v-if="authors.length" v-model="query" :aria-label="t('source-author')">
          <option value="">{{ t('source-author') }}</option>
          <option v-for="author in authors" :key="author.value" :value="author.value">
            {{ author.label }}
          </option>
        </select>
      </div>
      <div class="toolbar">
        <button
          type="button"
          :disabled="(source !== 'all' && !query.trim()) || sourceState?.running"
          @click="syncSource(false)"
        >
          {{ t('loadSource') }}
        </button>
        <button
          type="button"
          :disabled="(source !== 'all' && !query.trim()) || sourceState?.running"
          @click="syncSource(true)"
        >
          {{ t('syncSource') }}
        </button>
        <button
          type="button"
          :disabled="(source !== 'all' && !query.trim()) || sourceState?.running"
          @click="analyze"
        >
          {{ t('analyze') }}
        </button>
      </div>
      <p v-if="sourceState?.error" class="field-error">{{ sourceState.error }}</p>
      <p v-if="sourceState?.running" class="hint">{{ t('syncInProgress') }}</p>
      <p v-else-if="sourceState?.available" class="hint">
        {{ t('sourceCount') }} {{ sourceState.count }}
      </p>
      <template v-if="result">
        <p>
          {{ t('ready') }} {{ result.ready }} / {{ result.total }} · {{ t('trainable') }}
          {{ result.trainable }} · {{ t('missing') }} {{ result.missing }}
        </p>
        <div class="result-list">
          <label v-for="item in operators" :key="item.operatorId">
            <input v-model="selected" type="checkbox" :value="item.operatorId" />
            {{ item.name }}
          </label>
        </div>
        <button type="button" :disabled="!selected.length" @click="merge">
          {{ t('mergeGoals') }}
        </button>
        <details>
          <summary>{{ t('source-copilot') }} ({{ result.assignments.length }})</summary>
          <ul class="result-list">
            <li v-for="item in result.assignments" :key="item.id">
              {{ item.stage }} · {{ item.title }} · {{ t(item.state) }}
            </li>
          </ul>
        </details>
      </template>
    </fieldset>
  </details>
</template>
