<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref, watch } from 'vue'
import FieldInput from './FieldInput.vue'
import type { Editor, Option } from './bridge'
import { DEPOT_MAINTAIN_PRESETS, type DepotMaintainPresetKey } from '../user/depotMaintainPresets'
import {
  eventDepotItemId,
  eventDepotPlanIdentity,
  getEventDepotPresets,
  getEventDepotStages,
  getEventOrundumStages,
  type EventDepotMaintainPlan,
} from '../user/eventDepotMaintainPresets'
import {
  useDepotMaintainPlanEditor,
  type DepotMaintainPlanRow,
} from '../user/useDepotMaintainPlanEditor'

type Activity = { Value: string; Drop: string; DropName: string; Display: string }
type Overview = { Activity: Activity[]; ActivityTemplate: ('material' | 'orundum')[] }
const props = defineProps<{ editor: Editor; server: string; eventMode?: boolean }>()
const { config, target, t, request, update, report } = props.editor
const task = computed(() => config.value.Task)
const field = props.eventMode ? 'EventDepotMaintainPlans' : 'DepotMaintainPlans'
const quotas = props.eventMode
  ? ['EventDepotMaintainMedicineNumb', 'EventDepotMaintainStoneNumb']
  : ['DepotMaintainMedicineNumb', 'DepotMaintainStoneNumb']
const script = { scriptId: target.value!.scriptId }
const userId = target.value!.userId
const materials = ref<Option[]>([])
const inventory = ref<Record<string, string>>({})
const recognizedAt = ref('')
const stageOptions = ref<Record<string, Option[]>>({})
const activity = ref<Overview>()
const loading = ref(false)
const preset = ref<DepotMaintainPresetKey>('all')

let candidateBatch: Promise<void> | undefined
const pending = new Set<string>()
async function loadCandidates(itemId: string) {
  if (stageOptions.value[itemId]) return
  pending.add(itemId)
  candidateBatch ??= Promise.resolve().then(async () => {
    const itemIds = [...pending]
    pending.clear()
    candidateBatch = undefined
    try {
      const result = await request<{ data: Record<string, Option[]> }>(
        'POST',
        '/maa/depot/stage/candidates/batch',
        { script, itemIds }
      )
      for (const id of itemIds) stageOptions.value[id] = result.data[id] ?? []
    } catch (error) {
      report(error)
    }
  })
  await candidateBatch
}

const depot = useDepotMaintainPlanEditor({
  getSavedPlans: () => String(task.value[field]),
  savePlans: value => {
    void update('Task', { [field]: value })
  },
  loadStageCandidates: loadCandidates,
  getBestStage: itemId => stageOptions.value[itemId]?.[0]?.value,
  isLoading: () => loading.value,
  eventMode: props.eventMode,
})
const { plans } = depot
onScopeDispose(depot.dispose)

const allPlan = computed(() => plans.value.find(plan => plan.StageType === 'all'))
const activityRows = computed(() => {
  const info = activity.value
  const stages = info?.Activity ?? []
  const sections = [
    ['material', getEventDepotStages(stages)],
    ['orundum', getEventOrundumStages(stages)],
  ] as const
  return sections.flatMap(([type, list]) => {
    const saved = plans.value.filter(
      plan => plan.StageType === type || (type === 'material' && !plan.StageType)
    )
    const count = Math.max(
      list.length,
      info?.ActivityTemplate.filter(kind => kind === type).length ?? 0,
      ...saved.map(plan => plan.StageIndex ?? 0)
    )
    return Array.from({ length: count }, (_, index) => {
      const StageIndex = index + 1
      const StageType = type
      const override = saved.find(plan => plan.StageIndex === StageIndex)
      const fallback =
        type === 'orundum'
          ? (allPlan.value?.OrundumDropCount ?? 9999)
          : (allPlan.value?.DropCount ?? 999)
      const DropCount =
        type === 'orundum'
          ? (override?.OrundumDropCount ?? override?.DropCount ?? fallback)
          : (override?.DropCount ?? fallback)
      return { StageType, StageIndex, DropCount, Skip: override?.Skip, stage: list[index] }
    })
  })
})

function updateEvent(
  row: EventDepotMaintainPlan,
  field: 'DropCount' | 'Skip',
  value: number | boolean
) {
  const { StageType, StageIndex, DropCount } = row
  const plan = depot.ensureEventPlan({ StageType, StageIndex, DropCount })
  if (field === 'Skip') {
    if (value) plan.Skip = true
    else delete plan.Skip
  } else if (StageType === 'orundum') {
    plan.OrundumDropCount = Number(value)
  } else {
    plan.DropCount = Number(value)
  }
  depot.savePlans()
}

function updateDefault(field: 'DropCount' | 'OrundumDropCount', value: number) {
  const plan = depot.ensureEventPlan(getEventDepotPresets()[0])
  plan[field] = value
  depot.savePlans()
}

function updateStock(event: Event, previous: number, save: (value: number) => void) {
  const input = event.target as HTMLInputElement
  if (!input.validity.valid) {
    input.reportValidity()
    input.value = String(previous)
    return
  }
  save(input.valueAsNumber)
}

function updateDepotCount(event: Event, plan: DepotMaintainPlanRow) {
  updateStock(event, plan.DropCount, value => {
    plan.DropCount = value
    depot.savePlans()
  })
}

async function run(operation: () => Promise<unknown>) {
  loading.value = true
  try {
    await operation()
  } catch (error) {
    report(error)
  } finally {
    loading.value = false
  }
}

async function load(refresh = false) {
  await Promise.all([
    request<{ data: Option[] }>('POST', '/maa/depot/items', script).then(result => {
      materials.value = result.data
    }),
    request<{ data: Option[]; recognizedAt: string | null }>('POST', '/maa/depot/inventory', {
      script,
      userId,
    }).then(result => {
      inventory.value = Object.fromEntries(result.data.map(({ value, label }) => [value, label]))
      recognizedAt.value = result.recognizedAt ?? ''
    }),
    props.eventMode
      ? request<{ data: Record<string, Overview> }>(
          'POST',
          `/stages/overview?refresh=${refresh}`
        ).then(result => {
          activity.value = result.data[props.server]
        })
      : Promise.resolve(),
  ])
}
onMounted(() => {
  void run(load)
})
watch(
  () => props.server,
  () => {
    if (props.eventMode) void run(load)
  }
)
</script>

<template>
  <div class="stack">
    <div class="grid">
      <FieldInput
        v-for="quota in quotas"
        :key="quota"
        :label="t(quota)"
        :value="task[quota]"
        :min="0"
        :max="9999"
        nullable
        @change="update('Task', { [quota]: $event })"
      />
    </div>
    <p class="hint">{{ t('quotaHint') }}</p>
    <div class="toolbar">
      <button type="button" :disabled="loading" @click="run(() => load(true))">
        {{ t('refresh') }}
      </button>
      <span v-if="recognizedAt" class="hint">{{ t('inventory') }} · {{ recognizedAt }}</span>
    </div>
    <template v-if="eventMode">
      <div class="grid">
        <FieldInput
          :label="t('eventDefault')"
          :value="allPlan?.DropCount ?? 999"
          :min="0"
          @change="updateDefault('DropCount', Number($event))"
        />
        <FieldInput
          :label="t('orundumDefault')"
          :value="allPlan?.OrundumDropCount ?? 9999"
          :min="0"
          @change="updateDefault('OrundumDropCount', Number($event))"
        />
      </div>
      <div v-if="activityRows.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t('Stage') }}</th>
              <th>{{ t('enabled') }}</th>
              <th>{{ t('inventory') }}</th>
              <th>{{ t('targetCount') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in activityRows" :key="eventDepotPlanIdentity(row)">
              <th scope="row">
                {{ row.stage?.Display || t(row.StageType) + ' ' + row.StageIndex }}
              </th>
              <td>
                <input
                  type="checkbox"
                  :checked="!row.Skip"
                  :aria-label="t('enabled')"
                  @change="updateEvent(row, 'Skip', !($event.target as HTMLInputElement).checked)"
                />
              </td>
              <td>{{ row.stage ? (inventory[eventDepotItemId(row.stage)] ?? '–') : '–' }}</td>
              <td>
                <input
                  type="number"
                  min="0"
                  required
                  :aria-label="t('targetCount')"
                  :value="row.DropCount"
                  @change="
                    updateStock($event, row.DropCount, value =>
                      updateEvent(row, 'DropCount', value)
                    )
                  "
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="hint">{{ t('noActivity') }}</p>
    </template>
    <template v-else>
      <div class="toolbar">
        <button type="button" @click="depot.addPlan">{{ t('add') }}</button>
        <select v-model="preset" :aria-label="t('preset')">
          <option value="all">{{ t('preset-all') }}</option>
          <option v-for="choice in DEPOT_MAINTAIN_PRESETS" :key="choice.key" :value="choice.key">
            {{ t(`preset-${choice.key}`) }}
          </option>
        </select>
        <button type="button" :disabled="loading" @click="run(() => depot.importPreset(preset))">
          {{ t('import') }}
        </button>
      </div>
      <datalist id="maa-depot-items">
        <option v-for="item in materials" :key="item.value" :value="item.value">
          {{ item.label }}
        </option>
      </datalist>
      <datalist v-for="(options, id) in stageOptions" :id="`maa-depot-${id}`" :key="id">
        <option v-for="stage in options" :key="stage.value" :value="stage.value">
          {{ stage.label }}
        </option>
      </datalist>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t('item') }}</th>
              <th>{{ t('Stage') }}</th>
              <th>{{ t('inventory') }}</th>
              <th>{{ t('targetCount') }}</th>
              <th>{{ t('actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(plan, index) in plans" :key="plan.key">
              <td>
                <input
                  v-model="plan.DropId"
                  list="maa-depot-items"
                  :aria-label="t('item')"
                  @change="depot.onItemChange(plan)"
                />
              </td>
              <td>
                <input
                  v-model="plan.Stage"
                  :list="`maa-depot-${plan.DropId}`"
                  :aria-label="t('Stage')"
                  @change="depot.onStageChange(plan)"
                />
              </td>
              <td>{{ inventory[plan.DropId] ?? '–' }}</td>
              <td>
                <input
                  :value="plan.DropCount"
                  type="number"
                  min="0"
                  required
                  :aria-label="t('targetCount')"
                  @change="updateDepotCount($event, plan)"
                />
              </td>
              <td class="toolbar">
                <button
                  type="button"
                  :aria-label="t('moveUp')"
                  :disabled="index === 0 || loading"
                  @click="depot.moveRow(index, -1)"
                >
                  ↑
                </button>
                <button
                  type="button"
                  :aria-label="t('moveDown')"
                  :disabled="index === plans.length - 1 || loading"
                  @click="depot.moveRow(index, 1)"
                >
                  ↓
                </button>
                <button type="button" @click="depot.removePlan(plan.key)">{{ t('remove') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
