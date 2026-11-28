<script setup lang="ts">
import type { Option, Value } from './bridge'

const props = defineProps<{
  label: string
  value: Value
  options?: Option[]
  list?: string
  min?: number
  max?: number
  readonly?: boolean
  nullable?: boolean
}>()
const emit = defineEmits<{ change: [value: Value] }>()

function change(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.validity.valid) {
    input.reportValidity()
    input.value = String(props.value ?? '')
    return
  }
  const value =
    input.type === 'checkbox'
      ? input.checked
      : props.min !== undefined
        ? input.value === ''
          ? props.nullable
            ? null
            : props.min
          : input.valueAsNumber
        : input.value
  emit('change', value)
}
</script>

<template>
  <label v-if="typeof value === 'boolean'" class="switch-tile">
    <input type="checkbox" :checked="value" :disabled="readonly" @change="change" />
    {{ label }}
  </label>
  <label v-else>
    {{ label }}
    <select v-if="options" :value="value" :disabled="readonly" @change="change">
      <option v-if="!options.some(option => option.value === value)" :value="value">
        {{ value }}
      </option>
      <option v-for="option in options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
    <input
      v-else
      :value="value"
      :list="list"
      :type="min === undefined ? 'text' : 'number'"
      :min="min"
      :max="max"
      :readonly="readonly"
      :required="min !== undefined && !nullable"
      @change="change"
    />
  </label>
</template>
