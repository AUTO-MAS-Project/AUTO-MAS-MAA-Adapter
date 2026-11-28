<script setup lang="ts">
import { computed } from 'vue'
import type { Fields, Option, Value } from './bridge'
import FieldInput from './FieldInput.vue'
import { stageCodes } from './stage'

const props = defineProps<{
  values: Fields
  options: Option[]
  readonly?: boolean
  t: (key: string) => string
}>()
defineEmits<{ change: [field: string, value: Value] }>()

const series = computed(() => [
  { value: '0', label: props.t('unchanged') },
  ...['6', '5', '4', '3', '2', '1'].map(value => ({ label: value, value })),
  { value: '-1', label: props.t('maximum') },
])
</script>

<template>
  <div class="grid">
    <FieldInput
      :label="t('MedicineNumb')"
      :value="values.MedicineNumb"
      :min="0"
      :max="9999"
      :readonly="readonly"
      @change="$emit('change', 'MedicineNumb', $event)"
    />
    <FieldInput
      :label="t('SeriesNumb')"
      :value="values.SeriesNumb"
      :options="series"
      :readonly="readonly"
      @change="$emit('change', 'SeriesNumb', $event)"
    />
    <FieldInput
      v-for="field in stageCodes"
      :key="field"
      :label="t(field)"
      :value="values[field]"
      list="maa-stage-options"
      :readonly="readonly"
      @change="$emit('change', field, String($event).trim() || '-')"
    />
    <datalist id="maa-stage-options">
      <option v-for="option in options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </datalist>
  </div>
</template>
