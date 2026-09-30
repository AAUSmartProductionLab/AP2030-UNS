<template>
  <v-container class="pa-0" fluid>
    <VisualizationHeader
      border
      default-title="Asset Interfaces Mapping Configuration"
      :submodel-element-data="submodelElementData"
    />

    <v-card v-if="isLoading" class="mb-3">
      <v-progress-linear indeterminate />
    </v-card>

    <template v-else>
      <v-alert
        v-if="warnings.length > 0"
        class="mb-3"
        density="compact"
        type="warning"
        variant="tonal"
      >
        <ul class="ml-4">
          <li
            v-for="warning in warnings"
            :key="warning"
            class="text-body-small"
          >
            {{ warning }}
          </li>
        </ul>
      </v-alert>

      <v-card v-if="routes.length === 0" class="mb-4">
        <v-card-text class="text-body-medium">
          This AIMC submodel declares no routable mapping configuration.
        </v-card-text>
      </v-card>

      <!-- No route selected: the index doubles as the way in. It never renders
           the whole submodel as one flow. -->
      <v-card v-else-if="!focusedRoute" class="mb-4">
        <v-toolbar color="cardHeader" density="compact">
          <v-list-item>
            <v-list-item-title>
              <span class="text-title-small">
                Select a route to visualize its flow
              </span>
            </v-list-item-title>
          </v-list-item>
        </v-toolbar>

        <v-divider />

        <v-list density="compact">
          <v-list-item
            v-for="route in routes"
            :key="route.id"
            :subtitle="routeSubtitle(route)"
            :title="route.name"
            @click="focusRoute(route)"
          >
            <template #prepend>
              <v-icon
                density="compact"
                size="small"
              >
                {{ kindIcons[route.kind] }}
              </v-icon>
            </template>

            <template #append>
              <v-chip
                v-if="route.bidirectional"
                color="secondary"
                density="compact"
                label
                size="x-small"
                variant="tonal"
              >
                <v-icon density="compact" size="x-small">mdi-swap-horizontal</v-icon>
                request / reply
              </v-chip>

              <v-icon
                class="ml-2"
                density="compact"
                size="small"
              >
                mdi-chevron-right
              </v-icon>
            </template>
          </v-list-item>
        </v-list>
      </v-card>

      <template v-else>
        <!-- Route header: keeps the single route identifiable and lets the user
             step back to the index or to the next route. -->
        <v-toolbar class="mb-3" color="cardHeader" density="compact">
          <v-btn
            icon="mdi-arrow-left"
            size="small"
            @click="focusedRouteId = ''"
          />

          <v-list-item class="mx-2">
            <v-list-item-title>
              <span class="text-subtitle-2 font-weight-bold">{{ focusedRoute.name }}</span>
            </v-list-item-title>

            <v-list-item-subtitle class="text-caption">
              Route {{ focusedRouteIndex + 1 }} of {{ routes.length }}
              · {{ kindLabels[focusedRoute.kind] }}
            </v-list-item-subtitle>
          </v-list-item>

          <v-chip
            v-if="focusedRoute.bidirectional"
            color="secondary"
            density="compact"
            label
            size="small"
            variant="tonal"
          >
            <v-icon density="compact" size="x-small" start>mdi-swap-horizontal</v-icon>
            request / reply
          </v-chip>

          <v-spacer />

          <v-btn
            :disabled="focusedRouteIndex <= 0"
            icon="mdi-chevron-left"
            size="small"
            @click="stepRoute(-1)"
          />

          <v-btn
            :disabled="focusedRouteIndex >= routes.length - 1"
            icon="mdi-chevron-right"
            size="small"
            @click="stepRoute(1)"
          />
        </v-toolbar>

        <AimcMappingGraph
          class="mb-3"
          :direction="direction"
          :mapping="focusedRoute"
          @select-direction="selectDirection"
        />

        <!-- Delivery legend. The DMP has only two modes: a positive
             PollingInterval makes the DMP sample the source on a timer,
             everything else arrives pushed by the transport. -->
        <div class="d-flex flex-wrap align-center ga-4 mb-4 text-body-small">
          <span class="font-weight-bold">Delivery</span>

          <v-tooltip location="top" text="A positive PollingInterval is declared — the DMP samples the source on a timer.">
            <template #activator="{ props: tooltipProps }">
              <span v-bind="tooltipProps" class="d-inline-flex align-center ga-2">
                <span class="aimc-swatch aimc-swatch--polling" /> polled every n s
              </span>
            </template>
          </v-tooltip>

          <v-tooltip
            location="top"
            text="No polling interval — the value is pushed by the transport: an event affordance, an observable property, or a message topic."
          >
            <template #activator="{ props: tooltipProps }">
              <span v-bind="tooltipProps" class="d-inline-flex align-center ga-2">
                <span class="aimc-swatch aimc-swatch--pushed" /> pushed
              </span>
            </template>
          </v-tooltip>

          <v-divider class="my-1" vertical />

          <span class="d-inline-flex align-center ga-2">
            <span class="aimc-dash aimc-dash--forward" /> request / data flow
          </span>

          <span v-if="focusedRoute.bidirectional" class="d-inline-flex align-center ga-2">
            <span class="aimc-dash aimc-dash--reply" /> correlated reply
          </span>

          <v-divider class="my-1" vertical />

          <span class="opacity-70">
            the affordance group (properties / actions / events) is shown per endpoint
          </span>

          <span class="opacity-70">· click a source or sink to reveal its reference</span>
        </div>

        <AimcTransformationEditor
          ref="editor"
          v-model:direction="direction"
          :mapping="focusedRoute"
          @saved="refresh"
        />
      </template>
    </template>
  </v-container>
</template>

<script lang="ts" setup>
  /**
   * BaSyx AAS Web UI plugin for the IDTA AssetInterfacesMappingConfiguration
   * (AIMC) submodel, including the DMP `ResponseTransformation` extension.
   *
   * It visualizes **one route at a time**: a single MappingConfiguration is drawn
   * as a flow from sources (left) through the Lua transformation(s) (middle) to
   * sinks (right), and a bi-directional action contract additionally shows the
   * correlated reply flowing back from the sink through the response
   * transformation to the source. The Lua script of the focused route can be
   * edited and saved back to the Submodel Repository.
   *
   * Which route to show is chosen in the plugin's own route index, not in the
   * tree: a route is an item of the `MappingConfigurations` `SubmodelElementList`,
   * and AASd-114 makes every list item inherit the *list's* semanticId, so a
   * route carries no semanticId of its own. The BaSyx UI can therefore only
   * dispatch a plugin on the AIMC submodel, never on an individual route. The
   * whole submodel is never rendered as a single flow — only the focused route.
   */
  import type { AimcMapping, AimcMappingKind } from './aimc/types'
  import { useSMHandling } from '@/composables/AAS/SMHandling'
  import { useAASStore } from '@/store/AASDataStore'
  import AimcMappingGraph from './aimc/components/AimcMappingGraph.vue'
  import AimcTransformationEditor from './aimc/components/AimcTransformationEditor.vue'
  import { parseAimc } from './aimc/composables/parseAimc'
  import { AIMC_PLUGIN_SEMANTIC_IDS } from './aimc/types/semanticIds'

  defineOptions({
    name: 'AimcMappingConfiguration',
    semanticId: AIMC_PLUGIN_SEMANTIC_IDS,
  })

  // Stores
  const aasStore = useAASStore()

  // Composables
  const { setData } = useSMHandling()

  // Props
  const props = defineProps({
    submodelElementData: {
      type: Object as any,
      default: () => ({}),
    },
  })

  // State
  const isLoading = ref(false)
  const routes = ref<AimcMapping[]>([])
  const warnings = ref<string[]>([])
  const focusedRouteId = ref('')
  const direction = ref<'request' | 'response'>('request')
  const editor = ref<InstanceType<typeof AimcTransformationEditor>>()
  let visualizationUpdateId = 0

  const kindLabels: Record<AimcMappingKind, string> = {
    'data': 'data mapping',
    'operation': 'operation delegation',
    'property-write': 'property write',
    'unknown': 'unclassified',
  }

  const kindIcons: Record<AimcMappingKind, string> = {
    'data': 'mdi-arrow-right-bold-box',
    'operation': 'mdi-swap-horizontal-bold',
    'property-write': 'mdi-pencil-box',
    'unknown': 'mdi-help-circle-outline',
  }

  const focusedRoute = computed(() => routes.value.find(route => route.id === focusedRouteId.value))
  const focusedRouteIndex = computed(() => routes.value.findIndex(route => route.id === focusedRouteId.value))

  watch(
    () => props.submodelElementData,
    () => {
      initializeVisualization()
    },
  )

  onMounted(() => {
    initializeVisualization()
  })

  async function initializeVisualization (): Promise<void> {
    const updateId = ++visualizationUpdateId
    if (!props.submodelElementData || Object.keys(props.submodelElementData).length === 0) {
      return
    }

    isLoading.value = true
    try {
      // `setData` annotates every element with its repository `path`; the
      // editor needs the blob's path in order to persist an edit.
      // It yields an empty object when there is no path to start from.
      const submodelData = await setData(
        { ...props.submodelElementData },
        aasStore.getSelectedNode.path,
        false,
        aasStore.getSelectedNode.timestamp,
      )
      if (updateId !== visualizationUpdateId) return
      if (!submodelData || Object.keys(submodelData).length === 0) {
        routes.value = []
        focusedRouteId.value = ''
        warnings.value = ['The submodel could not be read: the Web UI has no repository path for it yet.']
        return
      }

      const parsed = parseAimc(submodelData)
      routes.value = parsed.mappings
      warnings.value = parsed.warnings
      // Keep the focused route while it still exists in the submodel.
      if (routes.value.some(route => route.id === focusedRouteId.value)) {
        return
      }
      focusedRouteId.value = ''
    } catch (error) {
      if (updateId !== visualizationUpdateId) return
      routes.value = []
      focusedRouteId.value = ''
      warnings.value = [`Unable to read this submodel: ${error instanceof Error ? error.message : String(error)}`]
    } finally {
      if (updateId === visualizationUpdateId) {
        isLoading.value = false
      }
    }
  }

  async function refresh (): Promise<void> {
    await initializeVisualization()
  }

  function focusRoute (route: AimcMapping): void {
    focusedRouteId.value = route.id
    direction.value = 'request'
  }

  function stepRoute (offset: number): void {
    const next = routes.value[focusedRouteIndex.value + offset]
    if (next) {
      focusRoute(next)
    }
  }

  function selectDirection (next: 'request' | 'response'): void {
    direction.value = next
    void editor.value?.reveal()
  }

  function routeSubtitle (route: AimcMapping): string {
    const sources = route.sources.length === 1
      ? route.sources[0]!.sourceId || 'source'
      : `${route.sources.length} sources`
    const sinks = route.sinks.length === 1
      ? route.sinks[0]!.sinkId || 'sink'
      : `${route.sinks.length} sinks`
    return `${kindLabels[route.kind]} · ${sources} → ${sinks}`
  }
</script>

<style scoped>
  .aimc-swatch {
    display: inline-block;
    width: 14px;
    height: 14px;
    border-radius: 4px;
    border: 1px solid rgba(128, 128, 128, 0.5);
    background: rgb(var(--v-theme-surface));
  }

  .aimc-swatch--polling {
    border-left: 3px solid rgb(var(--v-theme-info));
  }

  .aimc-swatch--pushed {
    border-left: 3px solid rgb(var(--v-theme-success));
  }

  .aimc-dash {
    display: inline-block;
    width: 26px;
    height: 0;
    border-top: 2px dashed currentColor;
  }

  .aimc-dash--reply {
    border-top-style: dotted;
    opacity: 0.7;
  }
</style>
