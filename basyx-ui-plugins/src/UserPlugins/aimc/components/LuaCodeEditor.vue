<template>
  <div>
    <div
      ref="container"
      class="aimc-lua-editor rounded border"
      :class="{ 'aimc-lua-editor--error': error }"
      :style="{ height }"
    />

    <v-progress-linear v-if="loading" :aria-label="`Loading ${accessibleLabel}`" indeterminate />

    <v-alert
      v-if="loadError"
      class="mt-2"
      role="alert"
      type="error"
      variant="tonal"
    >
      {{ loadError }}
    </v-alert>
  </div>
</template>

<script lang="ts" setup>
  import type * as MonacoRuntime from '@/components/Code/monacoRuntime'
  /**
   * Monaco based Lua editor for AIMC transformation blobs.
   *
   * The BaSyx app already ships `monaco-editor` and a JSON/XML-flavoured
   * `CodeEditor`; the Lua language is not registered by default, so the
   * language definition is pulled in lazily here. The existing
   * `monacoRuntime` is reused so the worker environment stays shared with the
   * rest of the app.
   */
  import type { editor, IDisposable } from 'monaco-editor'
  import { v4 as uuidv4 } from 'uuid'
  import { useTheme } from 'vuetify'

  const props = withDefaults(defineProps<{
    accessibleLabel: string
    readOnly?: boolean
    height?: string
    error?: boolean
    options?: editor.IStandaloneEditorConstructionOptions
  }>(), {
    readOnly: false,
    height: '320px',
    error: false,
    options: () => ({}),
  })
  const value = defineModel<string>({ required: true })
  const emit = defineEmits<{
    'ready': [model: editor.ITextModel]
    'content-change': [value: string]
    'load-error': [error: unknown]
  }>()

  const container = ref<HTMLElement>()
  const loading = ref(true)
  const loadError = ref('')
  const theme = useTheme()
  let runtime: typeof MonacoRuntime | undefined
  let instance: editor.IStandaloneCodeEditor | undefined
  let model: editor.ITextModel | undefined
  let subscription: IDisposable | undefined
  let unmounted = false
  let applyingExternalValue = false

  const editorOptions = computed<editor.IStandaloneEditorConstructionOptions>(() => ({
    ariaLabel: props.accessibleLabel,
    automaticLayout: true,
    folding: true,
    fontFamily: 'var(--v-theme-aimc-lua-font-family, monospace)',
    fontSize: 13,
    formatOnPaste: false,
    formatOnType: false,
    minimap: { enabled: false },
    quickSuggestions: { comments: false, other: true, strings: true },
    readOnly: props.readOnly,
    domReadOnly: props.readOnly,
    renderValidationDecorations: props.readOnly ? 'off' : 'on',
    scrollBeyondLastLine: false,
    tabSize: 4,
    wordBasedSuggestions: 'off',
    ...props.options,
    theme: theme.global.current.value.dark ? 'vs-dark' : 'vs',
  }))

  watch(value, text => {
    if (!model || text === model.getValue()) return
    applyingExternalValue = true
    try {
      model.setValue(text)
    } finally {
      applyingExternalValue = false
    }
  }, { flush: 'sync' })
  watch(editorOptions, options => instance?.updateOptions(options), { deep: true })

  onMounted(async () => {
    try {
      // Register the Lua Monarch definition, then reuse the app-wide runtime so
      // the worker environment and JSON diagnostics setup are not duplicated.
      await import('monaco-editor/languages/definitions/lua/register')
      runtime = await import('@/components/Code/monacoRuntime')
      if (unmounted || !container.value) return
      const { monaco } = runtime
      const uri = monaco.Uri.parse(`inmemory://aimc-lua/${uuidv4()}.lua`)
      model = monaco.editor.createModel(value.value, 'lua', uri)
      instance = monaco.editor.create(container.value, { ...editorOptions.value, model })
      subscription = model.onDidChangeContent(() => {
        if (!model) return
        const text = model.getValue()
        emit('content-change', text)
        if (!applyingExternalValue) value.value = text
      })
      emit('ready', model)
    } catch (error) {
      disposeEditor()
      if (unmounted) return
      loadError.value = `Unable to load the Lua editor: ${error instanceof Error ? error.message : String(error)}`
      emit('load-error', error)
    } finally {
      if (!unmounted) loading.value = false
    }
  })

  onBeforeUnmount(() => {
    unmounted = true
    disposeEditor()
  })

  function disposeEditor (): void {
    subscription?.dispose()
    instance?.dispose()
    model?.dispose()
    subscription = undefined
    instance = undefined
    model = undefined
  }

  function find (): void {
    instance?.focus()
    void instance?.getAction('actions.find')?.run()
  }

  function suggest (): void {
    instance?.focus()
    void instance?.getAction('editor.action.triggerSuggest')?.run()
  }

  defineExpose({ find, suggest })
</script>

<style scoped>
  /* Monaco positions overflow widgets against the viewport. Vuetify's layout
     containment creates a different fixed-position origin inside dialogs. */
  :global(.v-overlay__content:has(.aimc-lua-editor)) {
    contain: none;
  }

  .aimc-lua-editor {
    min-width: 0;
    overflow: hidden;
  }

  .aimc-lua-editor--error {
    border-color: rgb(var(--v-theme-error)) !important;
  }
</style>
