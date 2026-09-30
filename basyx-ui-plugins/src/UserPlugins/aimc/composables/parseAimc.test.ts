/**
 * Parser tests for the AIMC visualization plugin.
 *
 * The fixtures are the real Submodel-Repository payloads shipped with this
 * repository, so the parser is exercised against the exact wire format the
 * BaSyx Submodel Repository returns.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { parseAimc, parseAimcRoute } from './parseAimc'

const here = dirname(fileURLToPath(import.meta.url))
// The tests run from inside the BaSyx app checkout, so the repository that
// holds the fixtures is passed in explicitly.
const repoRoot = process.env.AIMC_FIXTURE_ROOT ?? resolve(here, '../../../../../..')

function loadFixture (relativePath: string): any {
  return JSON.parse(readFileSync(resolve(repoRoot, relativePath), 'utf8'))
}

/**
 * Mirrors the `path` annotation that `useSMHandling().setData` applies, which
 * is what the visualization hands to the parser and the editor persists to.
 */
function annotatePaths (node: any, path: string): any {
  node.path = path
  if (node.modelType === 'Submodel' && Array.isArray(node.submodelElements)) {
    for (const element of node.submodelElements) {
      annotatePaths(element, `${path}/submodel-elements/${element.idShort}`)
    }
  } else if (
    (node.modelType === 'SubmodelElementCollection' || node.modelType === 'SubmodelElementList')
    && Array.isArray(node.value)
  ) {
    for (const [index, element] of node.value.entries()) {
      const childPath = node.modelType === 'SubmodelElementList'
        ? `${path}[${index}]`
        : `${path}.${element.idShort}`
      annotatePaths(element, childPath)
    }
  }
  return node
}

/** Loads a fixture and unwraps the Submodel Repository event envelope if present. */
function parseFixture (relativePath: string) {
  const payload = loadFixture(relativePath)
  const submodel = payload.modelType === 'Submodel' ? payload : payload.submodel
  const annotated = annotatePaths(submodel, 'http://aas-env:8081/submodels/aimc')
  return parseAimc(annotated)
}

/** Returns the raw (annotated) list items of a fixture's MappingConfigurations. */
function routeItems (relativePath: string): any[] {
  const payload = loadFixture(relativePath)
  const submodel = payload.modelType === 'Submodel' ? payload : payload.submodel
  const annotated = annotatePaths(submodel, 'http://aas-env:8081/submodels/aimc')
  const list = annotated.submodelElements.find((element: any) => element.idShort === 'MappingConfigurations')
  return list.value
}

describe('parseAimc', () => {
  const result = parseFixture('aas-model/tests/data_aimc.json')

  it('finds the MappingConfigurations list despite its 1/0 semantic id', () => {
    expect(result.warnings).toEqual([])
    expect(result.mappings).toHaveLength(5)
  })

  it('recovers the authored route name from the IEC 61360 class metadata', () => {
    expect(result.mappings.map(mapping => mapping.name)).toEqual([
      'MQTT',
      'Halt',
      'Occupy',
      'Release',
      'Stoppering',
    ])
  })

  it('gives every route a repository path under the list', () => {
    for (const mapping of result.mappings) {
      expect(mapping.path).toMatch(/MappingConfigurations\[\d+\]$/)
    }
  })

  it('reports a warning for a submodel without mappings', () => {
    expect(parseAimc({ modelType: 'Submodel', submodelElements: [] }).warnings[0])
      .toContain('No MappingConfigurations')
  })
})

describe('parseAimcRoute', () => {
  const items = routeItems('aas-model/tests/data_aimc.json')

  it('parses a single route on its own, without the surrounding submodel', () => {
    const mqtt = parseAimcRoute(items[0], 0)
    expect(mqtt.name).toBe('MQTT')
    expect(mqtt.sources).toHaveLength(1)
    expect(mqtt.sinks).toHaveLength(2)
  })

  it('decodes the request transformation blob into Lua', () => {
    const mqtt = parseAimcRoute(items[0], 0)
    expect(mqtt.request.present).toBe(true)
    expect(mqtt.request.code).toContain('function aimc_main(sources)')
    expect(mqtt.request.code).toContain('sources.StationState.State')
  })

  it('gives the transformation blob a writable repository path', () => {
    expect(parseAimcRoute(items[0], 0).request.path)
      .toMatch(/MappingConfigurations\[\d+\]\.Transformation$/)
  })

  it('parses an AID affordance source with its protocol and group', () => {
    const [source] = parseAimcRoute(items[0], 0).sources
    expect(source!.sourceId).toBe('StationState')
    expect(source!.kind).toBe('affordance')
    expect(source!.group).toBe('properties')
    expect(source!.protocol).toBe('mqtt')
    expect(source!.refPath).toContain('InteractionMetadata')
  })

  it('parses plain AAS element sinks', () => {
    const mqtt = parseAimcRoute(items[0], 0)
    expect(mqtt.sinks.map(sink => sink.sinkId)).toEqual(['PackMLState', 'OccupationState'])
    expect(mqtt.sinks.every(sink => sink.kind === 'aas-element')).toBe(true)
  })

  it('does not mark a unidirectional data route as bi-directional', () => {
    const mqtt = parseAimcRoute(items[0], 0)
    expect(mqtt.bidirectional).toBe(false)
    expect(mqtt.response.present).toBe(false)
  })

  it('carries the raw blob element so an edit cannot drop its semanticId', () => {
    const mqtt = parseAimcRoute(items[0], 0)
    expect(mqtt.request.element?.semanticId).toBeDefined()
  })
})

describe('parseAimcRoute (DMP operation delegations)', () => {
  const items = routeItems('aas-camel-dmp/management-node/tests/data/syntegon_stoppering_aimc.json')

  it('classifies a CCI Operation source as an operation delegation', () => {
    const halt = parseAimcRoute(items[1], 1)
    expect(halt.name).toBe('Halt')
    expect(halt.kind).toBe('operation')
    expect(halt.sources[0]!.kind).toBe('operation')
    expect(halt.sources[0]!.refPath).toContain('Skills/Halt/operation')
    expect(halt.sinks[0]!.kind).toBe('affordance')
    expect(halt.sinks[0]!.group).toBe('actions')
  })

  it('is bi-directional even without a reply blob (the reply defaults to passthrough)', () => {
    const halt = parseAimcRoute(items[1], 1)
    expect(halt.bidirectional).toBe(true)
    expect(halt.response.present).toBe(false)
    expect(halt.response.code).toBe('')
  })
})

describe('parseAimcRoute (DMP ResponseTransformation extension)', () => {
  const items = routeItems('aas-camel-dmp/management-node/tests/data/events/sm_created.json')

  it('decodes the response blob and gives it its own path', () => {
    const mapping = parseAimcRoute(items[5], 5)
    expect(mapping.name).toBe('ParameterWriteMqtt')
    expect(mapping.response.code).toContain('function aimc_main(sources)')
    expect(mapping.response.path).toMatch(/MappingConfigurations\[\d+\]\.ResponseTransformation$/)
    expect(mapping.request.path).not.toBe(mapping.response.path)
  })

  it('is bi-directional because the reply blob is authored', () => {
    expect(parseAimcRoute(items[5], 5).bidirectional).toBe(true)
  })

  it('detects the writeDelegation qualifier and classifies the route', () => {
    const mapping = parseAimcRoute(items[5], 5)
    expect(mapping.kind).toBe('property-write')
    expect(mapping.writeDelegation).toContain('http')
  })
})
