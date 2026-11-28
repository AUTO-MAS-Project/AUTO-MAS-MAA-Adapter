<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'
import FieldInput from './FieldInput.vue'
import StageFields from './StageFields.vue'
import type { Editor } from './bridge'
import { labelWeekday, stageCodes, useStageOptions, weekdays } from './stage'

const props = defineProps<{ editor: Editor }>()
const { config, state, t, update } = props.editor
const info = computed(() => config.value.Info)
const groups = computed(() => {
  if (info.value.Mode === 'Weekly') return weekdays
  if (info.value.Mode === 'Rotate') {
    return Array.from({ length: Number(info.value.RotateDays) }, (_, index) => `Day${index + 1}`)
  }
  return ['ALL']
})
const modes = computed(() => ['ALL', 'Weekly', 'Rotate'].map(value => ({ value, label: t(value) })))
const group = ref('ALL')
const customStage = ref('')
const replacementStage = ref('')
watchEffect(() => {
  if (!groups.value.includes(group.value)) group.value = groups.value[0]
})

const options = useStageOptions(
  props.editor,
  () => (weekdays.includes(group.value) ? group.value : 'ALL'),
  () => 'Official'
)
const groupLabel = (value: string) => {
  if (value === 'ALL') return t('ALL')
  if (weekdays.includes(value)) return labelWeekday(value, state.value!.locale)
  return `${t('day')} ${value.slice(3)}`
}

function renameStage() {
  const oldStage = customStage.value.trim()
  const nextStage = replacementStage.value.trim() || '-'
  for (const [day, values] of Object.entries(config.value)) {
    const fields = stageCodes.filter(field => values[field] === oldStage)
    if (fields.length) void update(day, Object.fromEntries(fields.map(field => [field, nextStage])))
  }
  customStage.value = ''
  replacementStage.value = ''
}
</script>

<template>
  <section class="card stack">
    <h2>{{ t('plan') }}</h2>
    <div class="grid">
      <FieldInput
        :label="t('mode')"
        :options="modes"
        :value="info.Mode"
        @change="update('Info', { Mode: $event })"
      />
      <FieldInput
        v-if="info.Mode === 'Rotate'"
        :label="t('cycle')"
        :value="info.RotateDays"
        :min="1"
        :max="31"
        @change="update('Info', { RotateDays: $event })"
      />
      <label v-if="groups.length > 1">
        {{ t('day') }}
        <select v-model="group">
          <option v-for="day in groups" :key="day" :value="day">{{ groupLabel(day) }}</option>
        </select>
      </label>
    </div>
    <StageFields
      :values="config[group]"
      :options="options"
      :t="t"
      @change="(field, value) => update(group, { [field]: value })"
    />
    <details>
      <summary>{{ t('replaceStage') }}</summary>
      <div class="toolbar">
        <input v-model="customStage" :aria-label="t('fromStage')" :placeholder="t('fromStage')" />
        <input v-model="replacementStage" :aria-label="t('toStage')" :placeholder="t('toStage')" />
        <button type="button" :disabled="!customStage.trim()" @click="renameStage">
          {{ t('apply') }}
        </button>
      </div>
    </details>
  </section>
</template>
