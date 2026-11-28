<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import CopilotPanel from './CopilotPanel.vue'
import FieldInput from './FieldInput.vue'
import type { Editor, Option } from './bridge'
import {
  appendOperator,
  levelOptionsWithSaved,
  listGoals,
  mergeCultivateTargets,
  normalizeCultivateCatalog,
  parseCultivateTargets,
  removeGoal,
  removeOperator,
  serializeCultivateTargets,
  setMasteryLevel,
  upsertGoal,
  type CultivateGoalKind,
  type CultivateOperatorCatalogEntry,
  type CultivateTargetRow,
} from '../user/cultivateTargets'

type Material = { itemId: string; name: string; count: number; stage?: string }
type Preview = {
  stages: Material[]
  demands: Material[]
  unobtainable: Material[]
  totalExpectedSanity: number | null
  hasProgression: boolean
  hasInventory: boolean
}

const props = defineProps<{ editor: Editor }>()
const { config, target, t, request, update, commit, report } = props.editor
const task = computed(() => config.value.Task)
const rows = computed(() => parseCultivateTargets(String(task.value.CultivateTargets)))
const binding = computed(() =>
  task.value.CultivateSklandAccount && task.value.CultivateSklandUid
    ? `${task.value.CultivateSklandAccount}|${task.value.CultivateSklandUid}`
    : ''
)
const catalog = ref<CultivateOperatorCatalogEntry[]>([])
const catalogById = computed(
  () => new Map(catalog.value.map(operator => [operator.value, operator]))
)
const roles = ref<Option[]>([])
const query = ref('')
const selected = ref('')
const clipboard = ref('')
const skipped = ref<{ index: number; name: string; error: string }[]>([])
const preview = ref<Preview>()
const busy = ref(false)
const ids = { scriptId: target.value!.scriptId, userId: target.value!.userId }
const cultivationFlags = [
  'CultivateAutoRaise',
  'CultivateSkipDuringActivity',
  'CultivateSkipDuringResourceCollection',
  'CultivateMonthlyCard',
]
const quotaFields = ['CultivateMedicineNumb', 'CultivateStoneNumb']

const candidates = computed(() => {
  const search = query.value.trim().toLowerCase()
  const saved = new Set(rows.value.map(row => row.operatorId))
  return catalog.value.filter(
    ({ label, value }) =>
      !saved.has(value) &&
      (label.toLowerCase().includes(search) || value.toLowerCase().includes(search))
  )
})

async function run(operation: () => Promise<void>) {
  busy.value = true
  try {
    await operation()
  } catch (cause) {
    report(cause)
  } finally {
    busy.value = false
  }
}

async function loadCatalog() {
  const response = await request<{ data: Parameters<typeof normalizeCultivateCatalog>[0] }>(
    'POST',
    '/maa/cultivate/operators',
    { script: { scriptId: ids.scriptId }, userId: ids.userId }
  )
  const byId = new Map(catalog.value.map(operator => [operator.value, operator]))
  for (const item of normalizeCultivateCatalog(response.data)) byId.set(item.value, item)
  catalog.value = [...byId.values()]
}

onMounted(() => {
  void run(loadCatalog)
})

function saveRows(next: CultivateTargetRow[]) {
  preview.value = undefined
  void update('Task', { CultivateTargets: serializeCultivateTargets(next) })
}

function loadRoles() {
  void run(async () => {
    roles.value = (await request<{ data: Option[] }>('POST', '/maa/cultivate/skland/bindings')).data
  })
}

function bind(value: string) {
  void run(async () => {
    const [account, uid = ''] = value.split('|')
    if (await commit('Task', { CultivateSklandAccount: account, CultivateSklandUid: uid })) {
      preview.value = undefined
      catalog.value = []
      await loadCatalog()
    }
  })
}

function addOperator() {
  const operator = catalogById.value.get(selected.value)
  if (!operator) return
  saveRows(appendOperator(rows.value, operator.value, [], operator.maxElite))
  selected.value = ''
}

function goals(row: CultivateTargetRow) {
  const operator = catalogById.value.get(row.operatorId)
  const tiers = (kind: CultivateGoalKind, label: string, max: number, targetId = '') => {
    const saved = listGoals(row.rawGoals, kind).find(goal => goal.targetId === targetId)
    return {
      kind,
      label,
      targetId,
      value: String(saved?.toLevel ?? ''),
      options: [
        { value: '', label: t('noGoal') },
        ...levelOptionsWithSaved(max, saved?.toLevel ?? 0).map(level => ({
          value: String(level),
          label: String(level),
        })),
      ],
    }
  }
  const special = (
    kind: 'mastery' | 'module',
    choices: CultivateOperatorCatalogEntry['skills']
  ) => {
    const saved = listGoals(row.rawGoals, kind).filter(
      goal => !choices.some(choice => choice.value === goal.targetId)
    )
    return [
      ...choices.map(item => tiers(kind, item.label, item.maxLevel, item.value)),
      ...saved.map(item => tiers(kind, item.targetId, 0, item.targetId)),
    ]
  }
  return [
    tiers('elite', t('elite'), operator?.maxElite ?? 0),
    tiers('skill', t('skill'), operator?.maxSkillLevel ?? 0),
    ...special('mastery', operator?.skills ?? []),
    ...special('module', operator?.modules ?? []),
  ].filter(goal => goal.options.length > 1)
}

function changeGoal(
  row: CultivateTargetRow,
  kind: CultivateGoalKind,
  targetId: string,
  value: string
) {
  const level = value ? Number(value) : null
  const rawGoals =
    kind === 'mastery'
      ? setMasteryLevel(row.rawGoals, targetId, level)
      : level === null
        ? removeGoal(row.rawGoals, kind, targetId)
        : upsertGoal(row.rawGoals, { kind, targetId, toLevel: level })
  saveRows(
    rows.value.map(item => (item.operatorId === row.operatorId ? { ...item, rawGoals } : item))
  )
}

function importTargets() {
  void run(async () => {
    const result = await request<{
      targets: string
      error?: string
      skipped: typeof skipped.value
      data: Parameters<typeof normalizeCultivateCatalog>[0]
    }>('POST', '/maa/cultivate/import', { scriptId: ids.scriptId, content: clipboard.value })
    skipped.value = result.skipped
    if (result.error) throw new Error(t(`import-${result.error}`))
    const incoming = normalizeCultivateCatalog(result.data)
    const byId = new Map(catalog.value.map(operator => [operator.value, operator]))
    for (const operator of incoming) byId.set(operator.value, operator)
    catalog.value = [...byId.values()]
    mergeTargets(parseCultivateTargets(result.targets))
    clipboard.value = ''
  })
}

function mergeTargets(incoming: CultivateTargetRow[]) {
  const merged = mergeCultivateTargets(rows.value, incoming)
  if (merged.result.operatorIds.length) saveRows(merged.rows)
}

function refreshCatalog() {
  void run(async () => {
    await request('POST', '/maa/cultivate/refresh', { scriptId: ids.scriptId })
    catalog.value = []
    await loadCatalog()
  })
}

function loadPreview() {
  void run(async () => {
    preview.value = await request<Preview>('POST', '/maa/cultivate/preview', {
      ...ids,
      targets: task.value.CultivateTargets,
    })
  })
}
</script>

<template>
  <fieldset class="stack" :disabled="busy">
    <div class="grid">
      <FieldInput
        v-for="field in cultivationFlags"
        :key="field"
        :label="t(field)"
        :value="task[field]"
        @change="update('Task', { [field]: $event })"
      />
      <FieldInput
        v-for="field in quotaFields"
        :key="field"
        :label="t(field)"
        :value="task[field]"
        :min="0"
        :max="9999"
        nullable
        @change="update('Task', { [field]: $event })"
      />
    </div>
    <p class="hint">{{ t('quotaHint') }}</p>
    <div class="toolbar">
      <button type="button" @click="loadRoles">{{ t('loadRoles') }}</button>
      <FieldInput
        v-if="roles.length || binding"
        :label="t('binding')"
        :value="binding"
        :options="[{ value: '', label: t('unbind') }, ...roles]"
        @change="bind(String($event))"
      />
      <FieldInput
        :label="t('CultivateAllOwned')"
        :value="task.CultivateAllOwned"
        :readonly="!binding && !task.CultivateAllOwned"
        @change="commit('Task', { CultivateAllOwned: $event })"
      />
    </div>
    <p v-if="!binding" class="hint">{{ t('bindingHint') }}</p>
    <div class="toolbar">
      <input
        v-model="query"
        type="search"
        :placeholder="t('operatorSearch')"
        :aria-label="t('operatorSearch')"
      />
      <select v-model="selected" :aria-label="t('operatorSelect')">
        <option value="">{{ t('operatorSelect') }}</option>
        <option v-for="operator in candidates" :key="operator.value" :value="operator.value">
          {{ operator.label }}
        </option>
      </select>
      <button type="button" :disabled="!selected" @click="addOperator">{{ t('add') }}</button>
      <button type="button" @click="refreshCatalog">{{ t('refreshCatalog') }}</button>
    </div>
    <p v-if="!rows.length" class="hint">{{ t('emptyGoals') }}</p>
    <details v-for="row in rows" :key="row.operatorId">
      <summary>{{ catalogById.get(row.operatorId)?.label ?? row.operatorId }}</summary>
      <div class="grid">
        <FieldInput
          v-for="goal in goals(row)"
          :key="`${goal.kind}:${goal.targetId}`"
          :label="goal.label"
          :value="goal.value"
          :options="goal.options"
          :readonly="!binding && goal.kind !== 'elite'"
          @change="changeGoal(row, goal.kind, goal.targetId, String($event))"
        />
      </div>
      <button type="button" @click="saveRows(removeOperator(rows, row.operatorId))">
        {{ t('remove') }}
      </button>
    </details>
    <details>
      <summary>{{ t('importTargets') }}</summary>
      <div class="stack">
        <label>{{ t('pasteTargets') }}<textarea v-model="clipboard" rows="4"></textarea></label>
        <button type="button" :disabled="!clipboard.trim()" @click="importTargets">
          {{ t('import') }}
        </button>
        <ul v-if="skipped.length">
          <li v-for="item in skipped" :key="item.index">
            {{ item.index }}. {{ item.name }} {{ t(`import-${item.error}`) }}
          </li>
        </ul>
      </div>
    </details>
    <CopilotPanel :editor="editor" :binding="binding" @merge="mergeTargets" />
    <div>
      <button type="button" :disabled="!rows.length" @click="loadPreview">
        {{ t('preview') }}
      </button>
      <template v-if="preview">
        <p v-if="!preview.hasInventory || !preview.hasProgression" class="hint">
          {{ t('previewEstimate') }}
        </p>
        <p v-if="preview.totalExpectedSanity !== null">
          {{ t('sanity') }} {{ Math.ceil(preview.totalExpectedSanity) }}
        </p>
        <details
          v-for="(items, key) in {
            stages: preview.stages,
            demands: preview.demands,
            unobtainable: preview.unobtainable,
          }"
          :key="key"
        >
          <summary>{{ t(key) }} ({{ items.length }})</summary>
          <ul>
            <li v-for="item in items" :key="item.itemId">
              {{ item.name }} × {{ item.count }} {{ item.stage }}
            </li>
          </ul>
        </details>
      </template>
    </div>
  </fieldset>
</template>
