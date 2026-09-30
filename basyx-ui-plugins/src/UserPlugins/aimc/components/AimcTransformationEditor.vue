<template>
  <div ref="anchor">
    <v-card border>
      <v-toolbar color="cardHeader" density="compact">
        <v-list-item>
          <v-list-item-title>
            <span class="text-title-small">Route:</span>

            <v-chip class="ml-2" color="primary" label size="small">
              {{ mapping.name }}
            </v-chip>
          </v-list-item-title>
        </v-list-item>

        <v-spacer />

        <v-btn-toggle
          v-if="mapping.bidirectional"
          v-model="activeDirection"
          color="primary"
          density="compact"
          mandatory
          variant="outlined"
        >
          <v-btn size="small" value="request">Request</v-btn>
          <v-btn size="small" value="response">Response</v-btn>
        </v-btn-toggle>

        <v-tooltip location="bottom" :text="editorMode ? 'Exit edit mode' : 'Enter edit mode'">
          <template #activator="{ props: tooltipProps }">
            <v-btn
              v-bind="tooltipProps"
              :disabled="!envStore.getAllowEditing"
              :icon="editorMode ? 'mdi-pencil-off-outline' : 'mdi-pencil-outline'"
              size="small"
              @click="editorMode = !editorMode"
            />
          </template>
        </v-tooltip>
      </v-toolbar>

      <v-divider />

      <v-card-text class="pb-2">
        <div class="d-flex align-center mb-2 ga-2">
          <v-chip
            density="compact"
            label
            size="small"
            variant="tonal"
          >
            {{ kindLabel }}
          </v-chip>

          <v-chip
            v-if="mapping.bidirectional"
            color="secondary"
            density="compact"
            label
            size="small"
            variant="tonal"
          >
            <v-icon density="compact" size="x-small" start>mdi-swap-horizontal</v-icon>
            bi-directional
          </v-chip>

          <v-chip
            v-if="activeDirection === 'response' && !responseTransformation.present"
            color="warning"
            density="compact"
            label
            size="small"
            variant="tonal"
          >
            no response blob — reply passes through unchanged
          </v-chip>
        </div>

        <v-alert
          v-if="validationError"
          class="mb-3"
          density="compact"
          type="error"
          variant="tonal"
        >
          {{ validationError }}
        </v-alert>

        <v-alert
          v-else-if="editorMode && !hasBlob"
          class="mb-3"
          density="compact"
          type="info"
          variant="tonal"
        >
          This route authors no {{ activeDirection }} blob, so there is nothing to
          save. Add the element to the AIMC submodel in the editor first.
        </v-alert>

        <!-- The key forces a fresh Monaco model whenever the selected mapping or
             direction changes, so the previous script is never shown. -->
        <LuaCodeEditor
          :key="editorKey"
          v-model="draft"
          :accessible-label="`Lua transformation of ${mapping.name}`"
          :error="Boolean(validationError)"
          :height="editorHeight"
          :options="editorOptions"
          :read-only="!editorMode"
        />
      </v-card-text>

      <v-divider />

      <v-card-actions>
        <span class="text-body-small ml-3">{{ dirty ? 'Unsaved changes' : 'Saved' }}</span>

        <v-spacer />

        <v-btn
          :disabled="!editorMode || !dirty"
          prepend-icon="mdi-restore"
          size="small"
          @click="resetDraft"
        >
          Revert
        </v-btn>

        <v-btn
          color="primary"
          :disabled="!editorMode || !dirty || !hasBlob"
          :loading="saving"
          prepend-icon="mdi-content-save"
          size="small"
          @click="save"
        >
          Save
        </v-btn>
      </v-card-actions>
    </v-card>
  </div>
</template>

<script lang="ts" setup>
  import type { AimcMapping, AimcMappingKind } from '../types'
  /**
   * Editor for the Lua transformation of a single AIMC route. The request blob
   * is edited by default; a bi-directional route exposes a second editor for the
   * correlated-reply `ResponseTransformation` (DMP extension).
   */
  import type { editor } from 'monaco-editor'
  import { useRequestHandling } from '@/composables/RequestHandling'
  import { useEnvStore } from '@/store/EnvironmentStore'
  import { useNavigationStore } from '@/store/NavigationStore'
  import LuaCodeEditor from './LuaCodeEditor.vue'

  const props = defineProps<{
    mapping: AimcMapping
    /** Which transformation to show. Lifted so the graph can drive it. */
    direction: 'request' | 'response'
  }>()

  const emit = defineEmits<{
    'update:direction': [direction: 'request' | 'response']
    'saved': []
  }>()

  // Stores
  const envStore = useEnvStore()
  const navigationStore = useNavigationStore()

  // Composables
  const { putRequest } = useRequestHandling()

  // State
  const anchor = ref<HTMLElement>()
  const editorMode = ref(false)
  const draft = ref('')
  const savedValue = ref('')
  const saving = ref(false)
  const validationError = ref('')

  const kindLabels: Record<AimcMappingKind, string> = {
    'data': 'Data mapping',
    'operation': 'Operation delegation',
    'property-write': 'Property write delegation',
    'unknown': 'Unclassified',
  }

  const editorOptions: editor.IStandaloneEditorConstructionOptions = {
    glyphMargin: false,
    lineDecorationsWidth: 12,
  }

  const activeDirection = computed({
    get: () => props.direction,
    set: value => emit('update:direction', value),
  })

  const editorHeight = computed(() => (props.mapping.bidirectional ? '260px' : '340px'))

  const editorPath = computed(() =>
    activeDirection.value === 'request' ? props.mapping.request.path : props.mapping.response.path,
  )

  const editorKey = computed(() => `${props.mapping.id}-${activeDirection.value}`)

  /** `false` for a passthrough direction, which has no blob in the repository. */
  const hasBlob = computed(() => editorPath.value !== '')

  const kindLabel = computed(() => kindLabels[props.mapping.kind])
  const responseTransformation = computed(() => props.mapping.response)
  const dirty = computed(() => draft.value !== savedValue.value)

  const transformationCode = computed(() =>
    activeDirection.value === 'request' ? props.mapping.request.code : props.mapping.response.code,
  )

  // Re-seed the draft whenever the route or the edited direction changes, so a
  // previous script is never shown against a different blob.
  watch(
    () => [props.mapping.id, activeDirection.value] as const,
    () => {
      validationError.value = ''
      draft.value = transformationCode.value
      savedValue.value = transformationCode.value
    },
    { immediate: true },
  )

  /** Brought into view whenever the graph is asked to open a transformation. */
  async function reveal (): Promise<void> {
    await nextTick()
    anchor.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  defineExpose({ reveal })

  // A mapping without a reply direction always edits the request blob.
  watch(
    () => props.mapping.bidirectional,
    bidirectional => {
      if (!bidirectional && activeDirection.value !== 'request') {
        activeDirection.value = 'request'
      }
    },
    { immediate: true },
  )

  function validate (code: string): string {
    const trimmed = code.trim()
    if (trimmed === '') {
      return 'A transformation must define an "aimc_main(sources)" entrypoint function.'
    }
    if (!/function\s+aimc_main\s*\(/.test(trimmed)) {
      return 'Missing the "aimc_main(sources)" entrypoint function.'
    }
    return ''
  }

  watch(draft, code => {
    validationError.value = editorMode.value ? validate(code) : ''
  })

  function resetDraft (): void {
    draft.value = savedValue.value
    validationError.value = editorMode.value ? validate(draft.value) : ''
  }

  /** AAS Blob payloads are plain (non URL-safe) base64 on the wire. */
  function encodeBlob (text: string): string {
    const bytes = new TextEncoder().encode(text)
    let binary = ''
    for (const byte of bytes) {
      binary += String.fromCodePoint(byte)
    }
    return btoa(binary)
  }

  async function save (): Promise<void> {
    if (!hasBlob.value) {
      return
    }
    const error = validate(draft.value)
    validationError.value = error
    if (error !== '') {
      return
    }

    saving.value = true
    try {
      // PUT replaces the whole element, so the original is echoed back with
      // only the value swapped. Rebuilding a bare Blob would drop the
      // `semanticId` the DMP resolver classifies `ResponseTransformation` by.
      const original = activeDirection.value === 'request'
        ? props.mapping.request.element
        : props.mapping.response.element
      const body = {
        ...original,
        contentType: 'text/plain',
        idShort: activeDirection.value === 'request' ? 'Transformation' : 'ResponseTransformation',
        modelType: 'Blob',
        value: encodeBlob(draft.value),
      }
      const success = await putRequest(
        editorPath.value,
        JSON.stringify(body),
        new Headers({ 'Content-Type': 'application/json' }),
        'updating AIMC transformation',
        false,
      )
      if (!success?.success) {
        return
      }
      savedValue.value = draft.value
      emit('saved')
      // Refresh the tree view so the updated blob is picked up everywhere.
      navigationStore.dispatchTriggerTreeviewReload()
    } finally {
      saving.value = false
    }
  }
</script>
