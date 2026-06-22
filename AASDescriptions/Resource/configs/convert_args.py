#!/usr/bin/env python3
"""Convert YAML term args from parameter names to numeric indices."""
import yaml, os

os.chdir('/home/tristan/repositories/AP2030-UNS/AASDescriptions/Resource/configs')

files = [
    'planarShuttle1.yaml', 'planarShuttle2.yaml', 'planarShuttle3.yaml',
    'cytivaCapping.yaml', 'imaDispensing.yaml', 'imaLoadingSystem.yaml',
    'omronCamera.yaml', 'optimaUnloading.yaml', 'syntegonStoppering.yaml',
]

def build_name_map(params):
    return {p['key'].lower(): i for i, p in enumerate(params)}

def convert_args(term, name_map):
    if not isinstance(term, dict):
        return
    for op in ('and', 'or', 'not', 'oneOf', 'when'):
        if op in term:
            children = term[op]
            if not isinstance(children, list):
                children = [children]
            for child in children:
                convert_args(child, name_map)
    if 'args' in term:
        new = []
        for a in term['args']:
            if isinstance(a, str):
                idx = name_map.get(a.lower())
                if idx is not None:
                    new.append(idx)
                else:
                    new.append(a)
            else:
                new.append(a)
        term['args'] = new

for f in files:
    with open(f) as fh:
        data = yaml.safe_load(fh)
    aas_key = list(data.keys())[0]
    skills = data[aas_key].get('Skills', [])
    for skill in skills:
        em = skill.get('ExecutionModel')
        if not em: continue
        params = em.get('Parameters', [])
        if not params: continue
        name_map = build_name_map(params)
        for section in ('Conditions', 'Effects'):
            sec = em.get(section, {}) or {}
            for group_name, group in sec.items():
                if not isinstance(group, list): continue
                for term in group:
                    convert_args(term, name_map)
    with open(f, 'w') as fh:
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"{f}: done")
