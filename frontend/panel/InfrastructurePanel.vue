<script setup lang="ts">
import { computed, ref } from 'vue'
import FieldInput from './FieldInput.vue'
import type { Editor, Option, Value } from './bridge'

const props = defineProps<{ editor: Editor }>()
const { config, target, t, request, update, report } = props.editor
const task = computed(() => config.value.Task)
const ids = () => ({ scriptId: target.value!.scriptId, userId: target.value!.userId })
const modes = computed(() =>
  ['Normal', 'Rotation', 'Custom'].map(value => ({ value, label: t(value) }))
)
const loading = ref(false)
const shifts = ref<Option[]>([])
const state = ref('')
const selected = ref(-1)

async function load() {
  const [result, current] = await Promise.all([
    request<{ data: Option[]; state: string }>('POST', '/user/combox/infrastructure', ids()),
    request<{ index: number }>('POST', '/user/infrastructure/plan-select/get', ids()),
  ])
  shifts.value = result.data
  state.value = result.state
  selected.value = current.index
}

async function run(operation: () => Promise<void>) {
  loading.value = true
  try {
    await operation()
  } catch (error) {
    report(error)
  } finally {
    loading.value = false
  }
}

function importPlan() {
  void run(async () => {
    const file = await props.editor.pickPath({
      mode: 'file',
      filters: [{ name: 'JSON', extensions: ['json'] }],
    })
    if (!file.path) return
    await request('POST', '/user/infrastructure', { ...ids(), jsonFile: file.path })
    await load()
  })
}

function select(value: unknown) {
  void run(async () => {
    const reply = await request<{ index: number }>('POST', '/user/infrastructure/plan-select', {
      ...ids(),
      index: Number(value),
    })
    selected.value = reply.index
  })
}

function changeMode(value: Value) {
  void update('Task', { InfrastMode: value })
  if (value === 'Custom') void run(load)
}
</script>

<template>
  <details @toggle="task.InfrastMode === 'Custom' && !state && !loading && run(load)">
    <summary>{{ t('IfInfrast') }}</summary>
    <div class="grid">
      <FieldInput
        :label="t('enabled')"
        :value="task.IfInfrast"
        @change="update('Task', { IfInfrast: $event })"
      />
      <FieldInput
        :label="t('InfrastMode')"
        :value="task.InfrastMode"
        :options="modes"
        @change="changeMode"
      />
    </div>
    <div v-if="task.InfrastMode === 'Custom'" class="stack">
      <div class="toolbar">
        <button type="button" :disabled="loading" @click="importPlan">
          {{ t('infrastructureImport') }}
        </button>
        <button type="button" :disabled="loading" @click="run(load)">{{ t('refresh') }}</button>
      </div>
      <FieldInput
        v-if="state === 'rotate'"
        :label="t('infrastructureShift')"
        :value="String(selected)"
        :options="[{ value: '-1', label: t('auto') }, ...shifts]"
        :readonly="loading"
        @change="select"
      />
      <p v-else-if="state" class="hint">{{ t(`infrastructure-${state}`) }}</p>
    </div>
  </details>
</template>
