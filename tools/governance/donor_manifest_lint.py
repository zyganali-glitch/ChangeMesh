#!/usr/bin/env python3
"""
Permanent Governance Tooling: Donor Manifest Linter

This script validates the DONOR_REUSE_MANIFEST.md structure, enumerations, and required fields.
It does NOT perform actual donor path or semantic behavior verification (that is left to the primary agent and auditors).
"""

import sys
import re
import hashlib
import yaml

MANIFEST_PATH = 'docs/DONOR_REUSE_MANIFEST.md'

VALID_REUSE_METHODS = {'COPIED', 'ADAPTED', 'CLEAN_ROOM_REIMPLEMENTED', 'IDEA_ONLY', 'REFERENCE_ONLY'}
VALID_STATUSES = {'DISCOVERED', 'PIN_REQUIRED', 'UNDER_REVIEW', 'BLOCKED', 'APPROVED_FOR_IMPLEMENTATION', 'IMPLEMENTED_PENDING_PARITY', 'VERIFIED', 'EXCLUDED', 'SUPERSEDED'}

def lint_manifest():
    with open(MANIFEST_PATH, 'rb') as f:
        raw_text = f.read()
    
    sha256 = hashlib.sha256(raw_text).hexdigest()
    text = raw_text.decode('utf-8')
    
    blocks = re.findall(r'```yaml(.*?)```', text, re.MULTILINE | re.DOTALL)
    components = []
    
    for b in blocks:
        try:
            d = yaml.safe_load(b)
            if not isinstance(d, dict):
                print("ERROR: Malformed YAML block found (not a dict).")
                sys.exit(1)
        except yaml.YAMLError as e:
            print(f"ERROR: Malformed YAML block found: {e}")
            sys.exit(1)
            
        if 'component_id' not in d:
            print("ERROR: Missing component_id in YAML block.")
            sys.exit(1)
            
        comp_id = d['component_id']
        
        # Ignore exact schema example
        if comp_id == 'DONOR-COMPONENT-NNN':
            continue
            
        if not comp_id:
            print("ERROR: component_id is empty.")
            sys.exit(1)
            
        # Validate required fields
        required_fields = ['donor_id', 'source_commit', 'source_paths', 'license_state', 'source_behavior', 'reuse_method', 'target_paths_or_contracts', 'status']
        for field in required_fields:
            if field not in d or not d[field]:
                print(f"ERROR: Component {comp_id} is missing required field '{field}'.")
                sys.exit(1)
                
        status = d['status']
        if status not in VALID_STATUSES:
            print(f"ERROR: Component {comp_id} has invalid status '{status}'.")
            sys.exit(1)
            
        reuse_method = d['reuse_method']
        if reuse_method not in VALID_REUSE_METHODS:
            print(f"ERROR: Component {comp_id} has invalid reuse_method '{reuse_method}'. Must be a single allowed enum value.")
            sys.exit(1)
            
        # Check SHA format
        commit = str(d['source_commit'])
        if not re.match(r'^[0-9a-f]{40}$', commit):
            print(f"ERROR: Component {comp_id} has invalid source_commit '{commit}'. Must be a 40-character SHA.")
            sys.exit(1)
            
        components.append(d)
        
    print(f"SHASUM: {sha256}")
    print(f"Components: {len(components)}")
    print("Manifest linting passed successfully.")

if __name__ == '__main__':
    lint_manifest()
