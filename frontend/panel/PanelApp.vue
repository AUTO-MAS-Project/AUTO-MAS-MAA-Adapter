<script setup lang="ts">
import PlanPanel from './PlanPanel.vue'
import UserPanel from './UserPanel.vue'
import { usePanel } from './bridge'

defineProps<{ page: string }>()
const editor = usePanel()
const { target, error, state, t, changes, disabled } = editor
void editor.initialize().catch(editor.report)
</script>

<template>
  <p id="status" v-if="error" data-error role="alert">{{ error }}</p>
  <template v-if="target">
    <fieldset :disabled="disabled" class="stack">
      <PlanPanel v-if="page === 'plan'" :editor="editor" />
      <UserPanel v-else :editor="editor" />
      <div v-if="page === 'plan' && changes.size" class="toolbar">
        <button class="primary" type="button" @click="editor.save()">{{ t('save') }}</button>
      </div>
      <p v-for="(message, key) in state?.fieldErrors" :key="key" class="field-error" role="alert">
        {{ message }}
      </p>
    </fieldset>
  </template>
</template>
