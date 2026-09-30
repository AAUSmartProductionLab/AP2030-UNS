<template>
  <div class="aimc-graph">
    <VueFlow
      v-model:edges="edges"
      v-model:nodes="nodes"
      :default-edge-options="defaultEdgeOptions"
      :edges-updatable="false"
      :elements-selectable="true"
      :max-zoom="2"
      :min-zoom="0.1"
      :nodes-connectable="false"
      :nodes-draggable="false"
      @init="onInit"
      @node-click="onNodeClick"
      @pane-click="onPaneClick"
    >
      <!-- One group per originating SMC: all sources (or sinks) of a route
           that live in the same interface / AAS submodel share a frame. -->
      <template #node-aimcGroup="{ data }">
        <div
          class="aimc-group"
          :class="[
            `aimc-group--${data.side}`,
            { 'aimc-group--collapsed': data.members.length === 1 },
          ]"
        >
          <div class="aimc-group__header">
            <v-icon density="compact" size="x-small">
              {{ data.side === 'source' ? 'mdi-import' : 'mdi-export' }}
            </v-icon>

            <span class="text-caption font-weight-bold">{{ data.label }}</span>
            <span class="text-caption opacity-70">{{ data.members.length }}</span>
          </div>
        </div>
      </template>

      <template #node-aimcSource="{ data }">
        <div
          class="aimc-node aimc-node--endpoint"
          :class="[
            `aimc-node--${data.deliveryKind}`,
            { 'aimc-node--expanded': isExpanded(data) },
          ]"
        >
          <!-- Both edges leave this side (the request goes right towards the
               transformation, the reply arrives from the right), so the two
               connection points are split vertically to stay distinguishable. -->
          <Handle
            id="forward"
            class="aimc-handle aimc-handle--out"
            :position="Position.Right"
            :style="{ top: OUT_HANDLE_TOP }"
            type="source"
          />

          <Handle
            id="reply"
            class="aimc-handle aimc-handle--in"
            :position="Position.Right"
            :style="{ top: IN_HANDLE_TOP }"
            type="target"
          />

          <div class="aimc-node__header">
            <v-icon density="compact" size="small">{{ endpointIcon(data) }}</v-icon>
            <span class="text-body-2 font-weight-bold">{{ data.label }}</span>
          </div>

          <div class="aimc-node__meta">
            <v-chip
              v-for="badge in data.badges"
              :key="badge.text"
              :color="badge.color"
              density="compact"
              label
              size="x-small"
              variant="tonal"
            >
              {{ badge.text }}
            </v-chip>
          </div>

          <div v-if="isExpanded(data)" class="aimc-node__detail">
            <div class="aimc-node__detail-label">reference</div>

            <ol class="aimc-node__keys">
              <li
                v-for="(key, index) in data.keys"
                :key="index"
                class="aimc-node__key"
              >
                <span class="aimc-node__key-type">{{ key.type || 'Key' }}</span>
                <span class="aimc-node__key-value">{{ key.value }}</span>
              </li>
            </ol>
          </div>
        </div>
      </template>

      <template #node-aimcSink="{ data }">
        <div
          class="aimc-node aimc-node--endpoint"
          :class="[
            `aimc-node--${data.deliveryKind}`,
            { 'aimc-node--expanded': isExpanded(data) },
          ]"
        >
          <!-- Mirror of the source: the request arrives from the left, the
               reply departs to the left. -->
          <Handle
            id="forward"
            class="aimc-handle aimc-handle--in"
            :position="Position.Left"
            :style="{ top: OUT_HANDLE_TOP }"
            type="target"
          />

          <Handle
            id="reply"
            class="aimc-handle aimc-handle--out"
            :position="Position.Left"
            :style="{ top: IN_HANDLE_TOP }"
            type="source"
          />

          <div class="aimc-node__header">
            <v-icon density="compact" size="small">{{ endpointIcon(data) }}</v-icon>
            <span class="text-body-2 font-weight-bold">{{ data.label }}</span>
          </div>

          <div class="aimc-node__meta">
            <v-chip
              v-for="badge in data.badges"
              :key="badge.text"
              :color="badge.color"
              density="compact"
              label
              size="x-small"
              variant="tonal"
            >
              {{ badge.text }}
            </v-chip>
          </div>

          <div v-if="isExpanded(data)" class="aimc-node__detail">
            <div class="aimc-node__detail-label">reference</div>

            <ol class="aimc-node__keys">
              <li
                v-for="(key, index) in data.keys"
                :key="index"
                class="aimc-node__key"
              >
                <span class="aimc-node__key-type">{{ key.type || 'Key' }}</span>
                <span class="aimc-node__key-value">{{ key.value }}</span>
              </li>
            </ol>
          </div>
        </div>
      </template>

      <template #node-aimcTransform="{ data }">
        <div
          class="aimc-node aimc-node--transform"
          :class="[
            `aimc-node--${data.direction}`,
            { 'aimc-node--selected': data.direction === direction, 'aimc-node--absent': data.absent },
          ]"
        >
          <!-- The reply lane runs right-to-left, so its handles mirror the
               request lane to keep the arrowheads along the flow direction. -->
          <Handle
            v-if="data.direction === 'request'"
            :position="Position.Left"
            type="target"
          />

          <Handle
            v-if="data.direction === 'request'"
            :position="Position.Right"
            type="source"
          />

          <Handle
            v-if="data.direction === 'response'"
            :position="Position.Right"
            type="target"
          />

          <Handle
            v-if="data.direction === 'response'"
            :position="Position.Left"
            type="source"
          />

          <div class="aimc-node__header">
            <v-icon density="compact" size="small">mdi-code-braces</v-icon>
            <span class="text-body-2 font-weight-bold">{{ data.label }}</span>
          </div>

          <div class="aimc-node__meta">
            <v-chip density="compact" label size="x-small" variant="tonal">
              {{ data.absent ? 'passthrough' : 'lua' }}
            </v-chip>

            <v-chip
              v-if="data.lines"
              density="compact"
              label
              size="x-small"
              variant="tonal"
            >
              {{ data.lines }} lines
            </v-chip>
          </div>

          <div class="aimc-node__path">aimc_main(sources)</div>

          <v-btn
            class="aimc-node__open"
            density="compact"
            prepend-icon="mdi-code-tags"
            size="x-small"
            variant="tonal"
            @click.stop="emit('select-direction', data.direction)"
          >
            Open editor
          </v-btn>
        </div>
      </template>

      <Background :gap="16" pattern-color="currentColor" />
      <Controls />
    </VueFlow>
  </div>
</template>

<script lang="ts" setup>
  import type {
    AimcEndpointKind,
    AimcMapping,
    AimcReferenceKey,
  } from '../types'
  /**
   * Renders one AIMC route: sources on the left, the Lua transformation(s) in
   * the middle and sinks on the right.
   *
   * Sources and sinks that originate in the same SMC (the same `interface_*`
   * affordance group, or the same AAS submodel) share a labelled frame, so a
   * route that fans out over several interfaces stays readable.
   *
   * For a bi-directional action contract (an operation delegation, or any
   * route that authors a `ResponseTransformation`) a second, lower lane is
   * drawn: the correlated reply flows from the sink back through the response
   * transformation to the source. All connections are dashed and animated in
   * the direction of the data transfer; the forward lane additionally labels
   * each source with its delivery mode (polled or pushed).
   */
  import type { Edge, Node } from '@vue-flow/core'
  import { Background } from '@vue-flow/background'
  import { Controls } from '@vue-flow/controls'
  import { Handle, MarkerType, Position, useVueFlow, VueFlow } from '@vue-flow/core'
  import '@vue-flow/core/dist/style.css'
  import '@vue-flow/core/dist/theme-default.css'

  const props = defineProps<{
    mapping: AimcMapping
    /** Which transformation the editor is currently showing. */
    direction: 'request' | 'response'
  }>()

  const emit = defineEmits<{
    'select-direction': [direction: 'request' | 'response']
  }>()

  // Geometry of a single route. Three columns; the reply lane sits below the
  // request lane so the two directions never overlap.
  const SOURCE_X = 0
  const TRANSFORM_X = 400
  const SINK_X = 800
  const ROW_HEIGHT = 92
  const NODE_WIDTH = 250
  const NODE_HEIGHT = 66
  const REPLY_LANE_OFFSET = 132
  const GROUP_TAIL_PADDING = 40
  // The group frame carries a label strip; the first endpoint must clear it.
  const GROUP_HEADER_HEIGHT = 22
  const GROUP_HEADER_GAP = 8
  const GROUP_PAD_Y = GROUP_HEADER_HEIGHT + GROUP_HEADER_GAP
  const GROUP_PAD_X = 46
  // Connection points are placed as a share of the node height so they stay
  // distinct whether or not the endpoint is expanded to show its reference.
  const OUT_HANDLE_TOP = '30%'
  const IN_HANDLE_TOP = '72%'
  // The group frames are decorative backdrops; endpoints stack above them.
  const GROUP_Z = 0
  const INTERACTIVE_Z = 10

  // Every connection is a dashed spline whose dashes march along the flow.
  const defaultEdgeOptions = {
    animated: true,
    type: 'smoothstep',
  }

  const nodes = ref<Node[]>([])
  const edges = ref<Edge[]>([])
  const expandedNodeId = ref('')

  const { fitView } = useVueFlow()

  function isExpanded (data: any): boolean {
    return Boolean(data?.nodeId) && data.nodeId === expandedNodeId.value
  }

  function endpointIcon (data: any): string {
    const icons: Record<AimcEndpointKind, string> = {
      'affordance': data.role === 'source' ? 'mdi-broadcast' : 'mdi-access-point',
      'operation': 'mdi-play-box-outline',
      'aas-element': 'mdi-database-outline',
      'unknown': 'mdi-help-circle-outline',
    }
    return icons[data.kind as AimcEndpointKind] ?? icons.unknown
  }

  /**
   * Delivery mode of a source, as authored on the route.
   *
   * The DMP has exactly two modes (see `classify_delivery` in
   * `management_node/execution_policy.py`): a source is **polled** only when a
   * positive `PollingInterval` is declared — that is the sole case in which the
   * descriptor emits a `pollingIntervalMs` and the DMP runs a timer route.
   * Everything else is **pushed**: event affordances, properties declared
   * `observable`, and anything a push protocol (MQTT) delivers on a topic all
   * arrive on their own. An explicitly declared interval overrides the
   * transport default, so a retained MQTT topic can still be sampled.
   *
   * The affordance group (`properties` / `actions` / `events`) is transport
   * metadata shown as its own chip, not a third delivery mode.
   */
  function deliveryOf (pollingInterval: number | undefined): { kind: string, text: string, color?: string } {
    if (pollingInterval !== undefined && pollingInterval > 0) {
      return { kind: 'polling', text: `poll ${pollingInterval}s`, color: 'info' }
    }
    return { kind: 'pushed', text: 'pushed', color: 'success' }
  }

  function sourceDelivery (
    source: AimcMapping['sources'][number],
    defaultPollingInterval?: number,
  ): { kind: string, text: string, color?: string } {
    return deliveryOf(source.pollingInterval ?? defaultPollingInterval)
  }

  function sourceBadges (source: AimcMapping['sources'][number], defaultPollingInterval?: number): Array<{ text: string, color?: string }> {
    const badges: Array<{ text: string, color?: string }> = []
    if (source.protocol) {
      badges.push({ text: source.protocol.toUpperCase() })
    }
    if (source.group) {
      badges.push({ text: source.group })
    }
    if (source.kind === 'aas-element') {
      badges.push({ text: 'AAS' })
    }
    const delivery = sourceDelivery(source, defaultPollingInterval)
    badges.push({ text: delivery.text, color: delivery.color })
    return badges
  }

  function sinkBadges (sink: AimcMapping['sinks'][number]): Array<{ text: string, color?: string }> {
    const badges: Array<{ text: string, color?: string }> = []
    if (sink.protocol) {
      badges.push({ text: sink.protocol.toUpperCase() })
    }
    if (sink.group) {
      badges.push({ text: sink.group })
    }
    badges.push({ text: sink.kind === 'aas-element' ? 'AAS' : sink.kind })
    return badges
  }

  function lineCount (code: string): number {
    return code === '' ? 0 : code.split('\n').length
  }

  /** Human readable name of the SMC an endpoint lives in, e.g. `interface_mqtt`. */
  function originLabel (protocol: string, submodelId: string, side: 'source' | 'sink'): string {
    if (protocol) {
      return `interface_${protocol}`
    }
    const tail = submodelId.split('/submodels/').at(-1) ?? ''
    if (tail !== '') {
      return tail
    }
    return side === 'source' ? 'AAS source' : 'AAS sink'
  }

  interface EndpointGroup {
    key: string
    label: string
    side: 'source' | 'sink'
    rows: number[]
  }

  function groupEndpoints (
    endpoints: Array<{ protocol: string, submodelId: string }>,
    side: 'source' | 'sink',
  ): EndpointGroup[] {
    const groups = new Map<string, EndpointGroup>()
    for (const [index, endpoint] of endpoints.entries()) {
      const key = `${endpoint.submodelId}::${endpoint.protocol}`
      const existing = groups.get(key)
      if (existing) {
        existing.rows.push(index)
      } else {
        groups.set(key, {
          key,
          label: originLabel(endpoint.protocol, endpoint.submodelId, side),
          side,
          rows: [index],
        })
      }
    }
    return [...groups.values()]
  }

  function buildGraph (mapping: AimcMapping): { nodes: Node[], edges: Edge[] } {
    const nextNodes: Node[] = []
    const nextEdges: Edge[] = []
    const rowCount = Math.max(mapping.sources.length, mapping.sinks.length, 2)
    // Every node/edge id is scoped to the route. Vue Flow keys its node and edge
    // registries by id, so ids shared between routes (a plain "source-0") make
    // it re-bind an edge to the previous route's handle element, which leaves
    // the path only partially drawn after a prev/next switch.
    const requestNodeId = `${mapping.id}-request`
    const responseNodeId = `${mapping.id}-response`
    const hasResponseNode = mapping.bidirectional
    const requestY = (rowCount * ROW_HEIGHT) / 2 - NODE_HEIGHT / 2
    const responseY = hasResponseNode ? requestY + REPLY_LANE_OFFSET : 0

    for (const group of [...groupEndpoints(mapping.sources, 'source'), ...groupEndpoints(mapping.sinks, 'sink')]) {
      const isSourceSide = group.side === 'source'
      const firstRow = Math.min(...group.rows)
      const lastRow = Math.max(...group.rows)
      nextNodes.push({
        id: `${mapping.id}-group-${group.side}-${group.key}`,
        type: 'aimcGroup',
        position: {
          x: (isSourceSide ? SOURCE_X : SINK_X) - GROUP_PAD_X,
          y: firstRow * ROW_HEIGHT - GROUP_PAD_Y,
        },
        draggable: false,
        selectable: false,
        connectable: false,
        zIndex: GROUP_Z,
        style: {
          width: `${NODE_WIDTH + GROUP_PAD_X}px`,
          height: `${(lastRow - firstRow) * ROW_HEIGHT + NODE_HEIGHT + 2 * GROUP_PAD_Y + GROUP_TAIL_PADDING}px`,
        },
        data: {
          side: group.side,
          label: group.label,
          members: group.rows,
        },
      })
    }

    const deliveryOfRow = (index: number): { kind: string, text: string } =>
      sourceDelivery(mapping.sources[index]!, mapping.defaultPollingInterval)

    for (const [index, source] of mapping.sources.entries()) {
      const id = `${mapping.id}-source-${index}`
      const delivery = deliveryOfRow(index)
      nextNodes.push({
        id,
        type: 'aimcSource',
        position: { x: SOURCE_X, y: index * ROW_HEIGHT },
        draggable: false,
        connectable: false,
        zIndex: INTERACTIVE_Z,
        data: {
          nodeId: id,
          role: 'source',
          label: source.sourceId || `source_${index}`,
          kind: source.kind,
          group: source.group,
          deliveryKind: delivery.kind,
          badges: sourceBadges(source, mapping.defaultPollingInterval),
          keys: source.keys as AimcReferenceKey[],
        },
      })
      nextEdges.push({
        id: `${id}-to-request`,
        source: id,
        target: requestNodeId,
        sourceHandle: 'forward',
        targetHandle: null,
        label: source.sourceId ? `${source.sourceId} · ${delivery.text}` : delivery.text,
        class: 'aimc-edge',
        markerEnd: MarkerType.ArrowClosed,
      })
      if (hasResponseNode) {
        nextEdges.push({
          id: `${responseNodeId}-to-${id}`,
          source: responseNodeId,
          target: id,
          sourceHandle: null,
          targetHandle: 'reply',
          class: 'aimc-edge aimc-edge--reply',
          markerEnd: MarkerType.ArrowClosed,
        })
      }
    }

    for (const [index, sink] of mapping.sinks.entries()) {
      const id = `${mapping.id}-sink-${index}`
      nextNodes.push({
        id,
        type: 'aimcSink',
        position: { x: SINK_X, y: index * ROW_HEIGHT },
        draggable: false,
        connectable: false,
        zIndex: INTERACTIVE_Z,
        data: {
          nodeId: id,
          role: 'sink',
          label: sink.sinkId || `sink_${index}`,
          kind: sink.kind,
          group: sink.group,
          deliveryKind: 'sink',
          badges: sinkBadges(sink),
          keys: sink.keys as AimcReferenceKey[],
        },
      })
      nextEdges.push({
        id: `${requestNodeId}-to-${id}`,
        source: requestNodeId,
        target: id,
        sourceHandle: null,
        targetHandle: null,
        label: sink.sinkId || undefined,
        class: 'aimc-edge',
        markerEnd: MarkerType.ArrowClosed,
      })
      if (hasResponseNode) {
        nextEdges.push({
          id: `${id}-to-response`,
          source: id,
          target: responseNodeId,
          sourceHandle: 'reply',
          targetHandle: null,
          class: 'aimc-edge aimc-edge--reply',
          markerEnd: MarkerType.ArrowClosed,
        })
      }
    }

    nextNodes.push({
      id: requestNodeId,
      type: 'aimcTransform',
      position: { x: TRANSFORM_X, y: requestY },
      draggable: false,
      connectable: false,
      zIndex: INTERACTIVE_Z,
      data: {
        direction: 'request',
        label: 'Transformation',
        absent: !mapping.request.present || mapping.request.code === '',
        lines: lineCount(mapping.request.code),
      },
    })

    if (hasResponseNode) {
      nextNodes.push({
        id: responseNodeId,
        type: 'aimcTransform',
        position: { x: TRANSFORM_X, y: responseY },
        draggable: false,
        connectable: false,
        zIndex: INTERACTIVE_Z,
        data: {
          direction: 'response',
          label: 'ResponseTransformation',
          absent: !mapping.response.present || mapping.response.code === '',
          lines: lineCount(mapping.response.code),
        },
      })
    }

    return { nodes: nextNodes, edges: nextEdges }
  }

  /**
   * A single route always fits the viewport, so the graph is framed as a whole
   * rather than per route.
   */
  async function fitAll (): Promise<void> {
    await fitView({ padding: 0.18, maxZoom: 1.2, duration: 250 })
  }

  /**
   * Swaps the graph over in two phases: nodes first, then edges once the
   * handles exist. Committing both in the same tick lets Vue Flow resolve an
   * edge against a handle it has not measured yet, which draws only part of the
   * spline.
   */
  async function applyRoute (mapping: AimcMapping): Promise<void> {
    const graph = buildGraph(mapping)
    expandedNodeId.value = ''
    // The previous route's edges go first so no stale path is bound to the new
    // node ids while the new ones are still unmeasured.
    edges.value = []
    nodes.value = graph.nodes
    await nextTick()
    edges.value = graph.edges
    await nextTick()
    await fitAll()
  }

  watch(
    () => props.mapping,
    async () => {
      await applyRoute(props.mapping)
    },
    { immediate: true },
  )

  function onInit (): void {
    void nextTick().then(fitAll)
  }

  function onNodeClick (event: { node: Node }): void {
    const data = event.node.data as any
    if (event.node.type === 'aimcTransform') {
      emit('select-direction', data.direction)
      return
    }
    if (!data?.nodeId) {
      return
    }
    // Endpoint nodes toggle their reference detail; a second click collapses it.
    expandedNodeId.value = expandedNodeId.value === data.nodeId ? '' : data.nodeId
  }

  function onPaneClick (): void {
    expandedNodeId.value = ''
  }
</script>

<style scoped>
  .aimc-graph {
    height: 520px;
    min-width: 0;
  }

  /* Origin frame around the endpoints of one SMC. It sits behind the endpoint
     nodes, so it must not swallow their pointer events. */
  .aimc-group {
    position: relative;
    height: 100%;
    width: 100%;
    border-radius: 16px;
    border: 1px solid rgba(128, 128, 128, 0.28);
    background: rgba(128, 128, 128, 0.05);
    pointer-events: none;
  }

  .aimc-group--collapsed {
    border-style: dotted;
    opacity: 0.75;
  }

  .aimc-group__header {
    position: absolute;
    top: 0;
    left: 12px;
    height: 22px;
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 0 8px;
    border-radius: 0 0 8px 8px;
    background: rgba(128, 128, 128, 0.18);
  }

  .aimc-node {
    border-radius: 14px;
    border: 1px solid rgba(128, 128, 128, 0.5);
    background: rgb(var(--v-theme-surface));
    padding: 6px 10px;
    min-width: 220px;
    max-width: 250px;
  }

  .aimc-node--endpoint {
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  }

  .aimc-node--expanded {
    z-index: 5;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.24);
  }

  .aimc-node--selected {
    border-color: rgb(var(--v-theme-primary));
    box-shadow: 0 0 0 1px rgb(var(--v-theme-primary));
  }

  .aimc-node--transform {
    min-width: 200px;
  }

  .aimc-node--response {
    border-style: dashed;
    border-color: rgb(var(--v-theme-secondary));
  }

  .aimc-node--absent {
    opacity: 0.65;
  }

  /* Delivery mode tints the left accent of a source node. */
  .aimc-node--polling {
    border-left: 3px solid rgb(var(--v-theme-info));
  }

  .aimc-node--pushed {
    border-left: 3px solid rgb(var(--v-theme-success));
  }

  /* Input and output connection points, split vertically on the flow side. */
  :deep(.aimc-handle) {
    border: 2px solid rgb(var(--v-theme-surface));
  }

  :deep(.aimc-handle--in) {
    background: rgb(var(--v-theme-secondary));
  }

  :deep(.aimc-handle--out) {
    background: rgb(var(--v-theme-primary));
  }

  .aimc-node__header {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .aimc-node__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
  }

  .aimc-node__path {
    margin-top: 4px;
    font-family: monospace;
    font-size: 11px;
    opacity: 0.7;
  }

  .aimc-node__open {
    margin-top: 6px;
  }

  .aimc-node__detail {
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px dashed rgba(128, 128, 128, 0.4);
  }

  .aimc-node__detail-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    opacity: 0.6;
    margin-bottom: 2px;
  }

  .aimc-node__keys {
    list-style: none;
    margin: 0;
    padding: 0;
    font-family: monospace;
    font-size: 11px;
  }

  .aimc-node__key {
    display: flex;
    flex-direction: column;
    padding: 2px 0;
    border-bottom: 1px dotted rgba(128, 128, 128, 0.25);
    word-break: break-all;
  }

  .aimc-node__key:last-child {
    border-bottom: none;
  }

  .aimc-node__key-type {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    opacity: 0.55;
  }

  /* Dashed, marching splines. The reply lane keeps a coarser dash so the two
     directions stay distinguishable at a glance. */
  :deep(.aimc-edge .vue-flow__edge-path) {
    stroke-dasharray: 7 5;
    stroke-width: 1.75;
  }

  :deep(.aimc-edge--reply .vue-flow__edge-path) {
    stroke-dasharray: 3 5;
    stroke-width: 1.5;
  }

  :deep(.aimc-edge .vue-flow__edge-text) {
    font-size: 10px;
  }
</style>
