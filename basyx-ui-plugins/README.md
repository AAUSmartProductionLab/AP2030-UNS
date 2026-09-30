# BaSyx AAS Web UI — AP2030-UNS plugins

Custom plugins for the [BaSyx AAS Web UI](https://wiki.basyx.org/en/latest/content/user_documentation/basyx_components/web_ui/features/plugin_mechanism.html).

| Plugin | Registered for | Purpose |
| --- | --- | --- |
| `AimcMappingConfiguration` | `https://admin-shell.io/idta/AssetInterfacesMappingConfiguration/2/0/Submodel` (and `1/0`) | Flow visualisation of a **single** IDTA AIMC route, plus a Lua editor for its transformation blobs — including the DMP `ResponseTransformation` extension from [`aas-model`](../aas-model/src/aas_model/submodel_templates/aimc.py). |

## Why the image is rebuilt

The BaSyx Web UI discovers plugins at **build** time:

```ts
// aas-web-ui/src/main.ts
const pluginComponents = import.meta.glob('./UserPlugins/**/*.vue')
```

There is no runtime plugin drop-in, so a custom plugin has to be compiled into
the image. The `Dockerfile` here therefore checks out the upstream app, copies
`src/UserPlugins/` over the bundled `HelloWorldPlugin.vue`, and runs the normal
production build.

```bash
docker build -t aas-gui-ap2030 ./basyx-ui-plugins
```

`BASYX_WEB_UI_REF` pins the upstream commit so rebuilds are reproducible.

## Use it in the stack

`compose/docker-compose.basyx.yml` builds `aas-web-ui` from this directory
instead of pulling `eclipsebasyx/aas-gui:SNAPSHOT`, so a plain bring-up already
contains the plugin:

```bash
docker compose up -d --build aas-web-ui
```

The service keeps every environment variable of the stock Web UI (repository
paths, logo, primary colour, start page) and additionally sets
`ALLOW_EDITING=true`, which the transformation editor needs in order to persist
a saved blob.

## Layout

```
basyx-ui-plugins/
├── Dockerfile                                  bakes the plugins into aas-gui
└── src/UserPlugins/
    ├── AimcMappingConfiguration.vue            plugin entry point (semanticId dispatch)
    └── aimc/
        ├── components/
        │   ├── AimcMappingGraph.vue            Vue Flow graph of one route
        │   ├── AimcTransformationEditor.vue    editor card + persistence
        │   └── LuaCodeEditor.vue               Monaco with Lua registered
        ├── composables/
        │   ├── parseAimc.ts                    parseAimcRoute / parseAimc
        │   └── parseAimc.test.ts               tests against the repo fixtures
        └── types/
            ├── index.ts                        mapping model
            └── semanticIds.ts                  IDTA + DMP semantic ids
```

## Inspecting a running station

`docker-compose.yml` includes `compose/docker-compose.simulated-stations.yml`,
so the simulated stations come up with the stack and register themselves. The
station publishes its AAS config to MQTT topic
`NN/Nybrovej/InnoLab/Registration/Config`; `registration-service` turns that into
AAS, submodel and descriptor entries in the BaSyx repositories.

```bash
docker compose up -d --build          # UI (with plugin) + station + registries
open http://localhost:3001            # -> syntegonStopperingSystemAAS
                                    #    -> AssetInterfacesMappingConfiguration
                                    #    -> Visualization
```

`COMPOSE_PROFILES=simulated-stations` in `.env` is what activates the profile
the station services are declared under.

Note that `.env` also sets `BASYX_FEATURE_KAFKA_ENABLED=true` and
`SPRING_KAFKA_BOOTSTRAP_SERVERS=PLAINTEXT://kafka:9092`. Kafka must be up
(`docker compose up -d kafka`) or every BaSyx repository write fails with
`500 ConfigException: No resolvable bootstrap urls given in bootstrap.servers`.

## The AIMC visualisation

The plugin renders **one route at a time**. Opening the AIMC submodel shows an
index of its routes (name, kind, endpoints, reply badge); picking one draws that
route alone. The header keeps back/next arrows so you can step along the list.
The whole submodel is never drawn as a single flow.

> The route is chosen in the plugin's index, **not** in the AAS tree. A route is
> an item of the `MappingConfigurations` `SubmodelElementList`, and
> **AASd-114** makes every list item inherit the *list's* semanticId — so
> `aas_pydantic` deliberately strips the per-item `semanticId` during
> serialisation (`convert_pydantic_model.py`, "Clear individual semantic_ids
> (AASd-114)"). The BaSyx UI only dispatches a plugin when the selected element
> *has* a `semanticId`, so it can dispatch on the AIMC submodel but never on an
> individual route. The tree correspondingly labels them `[0] SubmodelElementCollection`,
> `[1] …`, which is another reason the in-plugin index is needed.

Within the focused route:

- **sources on the left** as rounded rectangles, **sinks on the right** in the
  same shape;
- the **Lua transformation in the middle** (`ResponseTransformation` below it for
  bi-directional action contracts);
- **all connections are dashed splines whose dashes march along the flow**. The
  correlated reply of a bi-directional route is drawn as a separate return lane
  with a coarser dash, from the sink back through the response transformation to
  the source.

Endpoints and transformations are interactive:

- **click a source or sink** — it expands and lists the `ModelReference` keys of
  the `ReferenceElement` it points at (`Submodel` → `SubmodelElementCollection` →
  …);
- **click a transformation** (or its *Open editor* button) — scrolls to the Lua
  editor, switching to the response direction when the reply blob is clicked.

Each box carries **two distinct connection points** on the side the data leaves
or enters, so the two directions never share a single attachment point:

| | out (primary) | in (secondary) |
| --- | --- | --- |
| source | upper — the request towards the transformation | lower — the reply coming back |
| sink | lower — the reply heading to the response transformation | upper — the request arriving |

The points are placed as a share of the node height, so they stay apart whether
or not the endpoint is expanded.

Sources and sinks that originate in the same SMC share a labelled frame
(`interface_mqtt`, `Variables`, …), so a route that fans out over several
interfaces stays readable.

### Delivery modes

The DMP has exactly **two** delivery modes (`classify_delivery` in
`management_node/execution_policy.py`), and the plugin mirrors them:

| Accent | Label | Meaning |
| --- | --- | --- |
| blue | `poll Ns` | a positive `PollingInterval` is declared — the descriptor emits a `pollingIntervalMs` and the DMP samples the source on a timer |
| green | `pushed` | no polling interval — the transport delivers the value: an event affordance, a property declared `observable`, or a message topic |

A per-source `PollingInterval` wins over the route's `DefaultPollingInterval`. An
explicitly declared interval **overrides** the transport default, so a retained
MQTT topic can still be sampled — which is exactly what the
`StationStateTimer` route of the stoppering station does (`poll 2s` on a
retained topic). Everything else on that station is `pushed`.

The affordance group (`properties` / `actions` / `events`) is transport metadata
and is shown as its own chip per endpoint — it is *not* a third delivery mode.
Sinks carry no accent, because delivery is a property of how a value is read.

### Editing and saving

The editor is read-only until the pencil toggle is switched on, which requires
`ALLOW_EDITING=true` in the Web UI environment. Saving validates that an
`aimc_main(sources)` entrypoint is present, then `PUT`s the blob back to its
Submodel Repository path.

The `PUT` echoes the original element back with only `value` replaced, so
`semanticId`, `description` and any qualifiers survive — the DMP resolver
classifies `ResponseTransformation` by its semantic id, so rebuilding a bare
`Blob` would break the mapping.

## Tests

`parseAimc.test.ts` runs against the real Submodel Repository payloads in this
repository (`aas-model/tests/data_aimc.json`,
`aas-camel-dmp/management-node/tests/data/**`). Run it from a BaSyx app checkout
with the plugin copied into `src/UserPlugins`:

```bash
AIMC_FIXTURE_ROOT=/path/to/AP2030-UNS npx vitest run src/UserPlugins
```

The tests are excluded from the image build (see the `Dockerfile`): upstream's
`prebuild` runs the whole vitest suite, and the fixtures are not part of the
image build context.
