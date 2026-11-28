<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import CultivationPanel from './CultivationPanel.vue'
import DepotPanel from './DepotPanel.vue'
import FieldInput from './FieldInput.vue'
import InfrastructurePanel from './InfrastructurePanel.vue'
import StageFields from './StageFields.vue'
import type { Editor, Fields, Option, Value } from './bridge'
import { labelWeekday, useStageOptions, weekdays } from './stage'

const props = defineProps<{ editor: Editor }>()
const { config, target, state, t, request, update, report } = props.editor
const task = computed(() => config.value.Task)
const stage = computed(() => config.value.Stage)
const user = ref<{ server: string; quickConfig: boolean; plans: Option[] }>()
const planFields = ref<Fields>()
const opened = ref({ event: false, cultivate: false, depot: false })
const isFixed = computed(() => stage.value.StageMode === 'Fixed')
const options = useStageOptions(
  props.editor,
  () => 'User',
  () => user.value?.server ?? ''
)
const daily = ['IfStartUp', 'IfRecruit', 'IfMall', 'IfAward', 'IfSwitchTheme', 'IfGreenTicketStore']
const annihilationOptions = [
  'Close',
  'Annihilation',
  'Chernobog@Annihilation',
  'LungmenOutskirts@Annihilation',
  'LungmenDowntown@Annihilation',
]
const toggle = (field: string, value: Value) => update('Task', { [field]: value })

watch(
  config,
  async (_, __, onCleanup) => {
    let current = true
    onCleanup(() => {
      current = false
    })
    try {
      const { scriptId, userId } = target.value!
      const next = await request<NonNullable<typeof user.value>>(
        'GET',
        `/editor/user/${scriptId}/${userId}`
      )
      if (current) user.value = next
    } catch (error) {
      if (current) report(error)
    }
  },
  { immediate: true }
)

watch(
  () => [stage.value.StageMode, user.value?.server] as const,
  async ([mode, server], _, onCleanup) => {
    let current = true
    onCleanup(() => {
      current = false
    })
    planFields.value = undefined
    if (!server || !mode || mode === 'Fixed') return
    try {
      const day = await request<Fields>(
        'GET',
        `/editor/plan/${encodeURIComponent(String(mode))}/active?server=${encodeURIComponent(server)}`
      )
      if (current) planFields.value = day
    } catch (error) {
      if (current) report(error)
    }
  },
  { immediate: true }
)
</script>

<template>
  <section v-if="user" class="card stack">
    <h2>{{ t('pipeline') }}</h2>
    <p v-if="!user.quickConfig" class="hint">{{ t('quickConfigOff') }}</p>
    <template v-else>
      <div class="grid">
        <FieldInput
          v-for="field in daily"
          :key="field"
          :label="t(field)"
          :value="task[field]"
          @change="toggle(field, $event)"
        />
        <FieldInput
          :label="t('Annihilation')"
          :value="task.Annihilation"
          :options="annihilationOptions.map(value => ({ value, label: t(value) }))"
          @change="toggle('Annihilation', $event)"
        />
        <FieldInput
          v-if="task.Annihilation !== 'Close'"
          :label="t('AnnihilationStartWeekday')"
          :value="task.AnnihilationStartWeekday"
          :options="weekdays.map(value => ({ value, label: labelWeekday(value, state!.locale) }))"
          @change="toggle('AnnihilationStartWeekday', $event)"
        />
      </div>
      <InfrastructurePanel :editor="editor" />
      <details @toggle="opened.event ||= ($event.target as HTMLDetailsElement).open">
        <summary>{{ t('IfEventDepotMaintain') }}</summary>
        <div class="stack">
          <FieldInput
            :label="t('enabled')"
            :value="task.IfEventDepotMaintain"
            @change="toggle('IfEventDepotMaintain', $event)"
          />
          <DepotPanel v-if="opened.event" :editor="editor" :server="user.server" event-mode />
        </div>
      </details>
      <details @toggle="opened.cultivate ||= ($event.target as HTMLDetailsElement).open">
        <summary>{{ t('IfCultivate') }}</summary>
        <div class="stack">
          <FieldInput
            :label="t('enabled')"
            :value="task.IfCultivate"
            @change="toggle('IfCultivate', $event)"
          />
          <CultivationPanel v-if="opened.cultivate" :editor="editor" />
        </div>
      </details>
      <details @toggle="opened.depot ||= ($event.target as HTMLDetailsElement).open">
        <summary>{{ t('IfDepotMaintain') }}</summary>
        <div class="stack">
          <FieldInput
            :label="t('enabled')"
            :value="task.IfDepotMaintain"
            @change="toggle('IfDepotMaintain', $event)"
          />
          <DepotPanel v-if="opened.depot" :editor="editor" :server="user.server" />
        </div>
      </details>
      <details>
        <summary>{{ t('IfFight') }}</summary>
        <div class="stack">
          <FieldInput
            :label="t('enabled')"
            :value="task.IfFight"
            @change="toggle('IfFight', $event)"
          />
          <FieldInput
            :label="t('StageMode')"
            :value="stage.StageMode"
            :options="[{ value: 'Fixed', label: t('fixed') }, ...user.plans]"
            @change="update('Stage', { StageMode: $event })"
          />
          <StageFields
            v-if="isFixed || planFields"
            :values="isFixed ? stage : planFields!"
            :options="options"
            :readonly="!isFixed"
            :t="t"
            @change="(field, value) => update('Stage', { [field]: value })"
          />
        </div>
      </details>
    </template>
  </section>
</template>
