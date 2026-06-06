const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { GATE_METHODOLOGY_FLAGS_ERROR, parseSlash } = require('../slash-parser');

test('legacy Harper slash commands parse without methodology fields', () => {
  const cases = [
    ['/idea', { cmd: '/idea', args: { name: undefined } }],
    ['/spec', { cmd: '/spec', args: { targets: '' } }],
    ['/plan', { cmd: '/plan', args: { targets: '' } }],
    ['/kit REQ-001', { cmd: '/kit', args: { targets: ['REQ-001'], phases: null } }],
    ['/kit REQ-001 --integrity', { cmd: '/kit', args: { targets: ['REQ-001'], phases: ['integrity_eval'] } }],
    ['/kit REQ-001 --hardener', { cmd: '/kit', args: { targets: ['REQ-001'], phases: ['promotion_hardener'] } }],
    ['/kit REQ-001 --promotion-eval', { cmd: '/kit', args: { targets: ['REQ-001'], phases: ['promotion_eval'] } }],
    ['/kit REQ-001 --phases=kit,integrity_eval', { cmd: '/kit', args: { targets: ['REQ-001'], phases: ['kit', 'integrity_eval'] } }],
    ['/eval REQ-001', { cmd: '/eval', args: { targets: ['REQ-001'], testMode: undefined, modeContent: undefined } }],
    ['/eval REQ-001 manual pass', { cmd: '/eval', args: { targets: ['REQ-001'], testMode: 'manual', modeContent: 'pass' } }],
    ['/gate REQ-001', { cmd: '/gate', args: { targets: ['REQ-001'], testMode: undefined, modeContent: undefined } }],
    ['/gate REQ-001 manual pass', { cmd: '/gate', args: { targets: ['REQ-001'], testMode: 'manual', modeContent: 'pass' } }],
    ['/finalize', { cmd: '/finalize', args: {} }],
  ];

  for (const [input, expected] of cases) {
    const parsed = parseSlash(input);
    assert.deepEqual(parsed, expected, input);
    assert.equal(parsed.args.methodology, undefined, input);
    assert.equal(parsed.args.agent, undefined, input);
    assert.equal(parsed.args.methodology_context, undefined, input);
  }
});

test('BMAD Harper slash commands parse supported phase-agent mappings', () => {
  const cases = [
    ['/idea --methodology bmad --agent analyst', '/idea', undefined, 'analyst'],
    ['/spec --methodology bmad --agent pm', '/spec', undefined, 'pm'],
    ['/spec --methodology bmad --agent ux', '/spec', undefined, 'ux'],
    ['/plan --methodology bmad --agent architect', '/plan', undefined, 'architect'],
    ['/plan --methodology bmad --agent pm', '/plan', undefined, 'pm'],
    ['/kit REQ-001 --methodology bmad --agent developer', '/kit', ['REQ-001'], 'developer'],
    ['/kit REQ-001 --repair --methodology bmad --agent developer', '/kit', ['REQ-001'], 'developer'],
    ['/eval REQ-001 --methodology bmad --agent qa', '/eval', ['REQ-001'], 'qa'],
    ['/eval REQ-001 --methodology bmad --agent developer', '/eval', ['REQ-001'], 'developer'],
    ['/finalize --methodology bmad --agent tech-writer', '/finalize', undefined, 'tech-writer'],
  ];

  for (const [input, cmd, targets, agent] of cases) {
    const parsed = parseSlash(input);
    assert.equal(parsed.error, undefined, input);
    assert.equal(parsed.cmd, cmd, input);
    assert.equal(parsed.args.methodology, 'bmad', input);
    assert.equal(parsed.args.agent, agent, input);
    assert.deepEqual(parsed.args.methodology_context, { methodology: 'bmad', agent }, input);
    if (targets) assert.deepEqual(parsed.args.targets, targets, input);
  }

  assert.equal(parseSlash('/kit REQ-001 --repair --methodology bmad --agent developer').args.repair, true);
});

test('BMAD spec PM and UX agents parse as distinct methodology roles', () => {
  const pm = parseSlash('/spec --methodology bmad --agent pm');
  assert.equal(pm.error, undefined);
  assert.equal(pm.cmd, '/spec');
  assert.equal(pm.args.methodology, 'bmad');
  assert.equal(pm.args.agent, 'pm');
  assert.deepEqual(pm.args.methodology_context, { methodology: 'bmad', agent: 'pm' });

  const ux = parseSlash('/spec --methodology bmad --agent ux');
  assert.equal(ux.error, undefined);
  assert.equal(ux.cmd, '/spec');
  assert.equal(ux.args.methodology, 'bmad');
  assert.equal(ux.args.agent, 'ux');
  assert.deepEqual(ux.args.methodology_context, { methodology: 'bmad', agent: 'ux' });
});

test('legacy kit slash parsing remains unchanged without methodology flags', () => {
  assert.deepEqual(parseSlash('/kit REQ-001 --hardener'), {
    cmd: '/kit',
    args: {
      targets: ['REQ-001'],
      phases: ['promotion_hardener'],
    },
  });

  assert.deepEqual(parseSlash('/kit REQ-001 --phases=kit,integrity_eval'), {
    cmd: '/kit',
    args: {
      targets: ['REQ-001'],
      phases: ['kit', 'integrity_eval'],
    },
  });
});

test('legacy eval and gate arguments remain unchanged without methodology flags', () => {
  assert.deepEqual(parseSlash('/eval REQ-002 manual pass'), {
    cmd: '/eval',
    args: {
      targets: ['REQ-002'],
      testMode: 'manual',
      modeContent: 'pass',
    },
  });

  assert.deepEqual(parseSlash('/gate REQ-003'), {
    cmd: '/gate',
    args: {
      targets: ['REQ-003'],
      testMode: undefined,
      modeContent: undefined,
    },
  });

  assert.deepEqual(parseSlash('/gate REQ-001 manual pass'), {
    cmd: '/gate',
    args: {
      targets: ['REQ-001'],
      testMode: 'manual',
      modeContent: 'pass',
    },
  });

  assert.deepEqual(parseSlash('/gate REQ-001 manual block'), {
    cmd: '/gate',
    args: {
      targets: ['REQ-001'],
      testMode: 'manual',
      modeContent: 'block',
    },
  });

  assert.deepEqual(parseSlash('/gate REQ-001 manual needs-repair'), {
    cmd: '/gate',
    args: {
      targets: ['REQ-001'],
      testMode: 'manual',
      modeContent: 'needs-repair',
    },
  });
});

test('methodology flag supports split and equals forms', () => {
  assert.equal(parseSlash('/spec --methodology bmad').args.methodology, 'bmad');
  assert.equal(parseSlash('/spec --methodology=bmad').args.methodology, 'bmad');
});

test('agent flag supports split and equals forms', () => {
  assert.equal(parseSlash('/kit REQ-004 --methodology bmad --agent developer').args.agent, 'developer');
  assert.equal(parseSlash('/kit REQ-004 --methodology=bmad --agent=developer').args.agent, 'developer');
});

test('agent without methodology returns a clear error', () => {
  const parsed = parseSlash('/kit REQ-005 --agent developer');
  assert.match(parsed.error, /--agent requires --methodology/);
});

test('invalid methodology returns a clear error', () => {
  const parsed = parseSlash('/spec --methodology scrum');
  assert.match(parsed.error, /Unsupported methodology: scrum/);
});

test('invalid BMAD agent returns a clear error', () => {
  const parsed = parseSlash('/spec --methodology bmad --agent coach');
  assert.match(parsed.error, /Unsupported BMAD agent: coach/);
});

test('invalid BMAD phase-agent mapping returns a clear error', () => {
  const parsed = parseSlash('/kit REQ-006 --methodology bmad --agent architect');
  assert.match(parsed.error, /not allowed for phase 'kit'/);
});

test('gate cannot be overridden by BMAD methodology flags', () => {
  const methodologyOnly = parseSlash('/gate REQ-001 --methodology bmad');
  assert.equal(methodologyOnly.error, GATE_METHODOLOGY_FLAGS_ERROR);

  const methodologyAndAgent = parseSlash('/gate REQ-001 --methodology bmad --agent qa');
  assert.equal(methodologyAndAgent.error, GATE_METHODOLOGY_FLAGS_ERROR);

  const agentOnly = parseSlash('/gate REQ-001 --agent qa');
  assert.equal(agentOnly.error, GATE_METHODOLOGY_FLAGS_ERROR);

  const equalsForms = parseSlash('/gate REQ-001 --methodology=bmad --agent=qa');
  assert.equal(equalsForms.error, GATE_METHODOLOGY_FLAGS_ERROR);
});

test('kit phases and repair flags parse without changing legacy phase behavior', () => {
  assert.deepEqual(parseSlash('/kit REQ-001 --phases=kit,integrity_eval'), {
    cmd: '/kit',
    args: {
      targets: ['REQ-001'],
      phases: ['kit', 'integrity_eval'],
    },
  });

  assert.deepEqual(parseSlash('/kit REQ-001 --repair'), {
    cmd: '/kit',
    args: {
      targets: ['REQ-001'],
      phases: null,
      repair: true,
    },
  });

  assert.deepEqual(parseSlash('/kit REQ-001 --repair --methodology bmad --agent developer'), {
    cmd: '/kit',
    args: {
      targets: ['REQ-001'],
      phases: null,
      repair: true,
      methodology: 'bmad',
      agent: 'developer',
      methodology_context: {
        methodology: 'bmad',
        agent: 'developer',
      },
    },
  });
});

test('methodology role and local executor concepts remain separate in slash parsing', () => {
  const parsed = parseSlash('/kit REQ-001 --repair --methodology bmad --agent developer');

  assert.equal(parsed.args.methodology, 'bmad');
  assert.equal(parsed.args.agent, 'developer');
  assert.equal(parsed.args.localAgentExecutor, undefined);
  assert.equal(parsed.args.executionPreference, undefined);
});

test('extension propagates kit repair and rejects methodology context for gate defense in depth', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'extension.js'), 'utf8');
  const guardIndex = source.indexOf("phase === 'gate' &&");
  const handleGateIndex = source.indexOf('report = await handleGate(');

  assert.notEqual(guardIndex, -1);
  assert.notEqual(handleGateIndex, -1);
  assert.ok(guardIndex < handleGateIndex);
  assert.match(source, /msg\.methodology \|\| msg\.agent \|\| msg\.methodology_context/);
  assert.match(source, /Gate is CLike-owned\. Methodology flags are not accepted for \/gate in MVP\./);
  assert.match(source, /\.\.\.\(msg\.repair \? \{ repair: true \} : \{\}\)/);
});

test('utility collects bounded Harper companion docs and includes IDEA for downstream phases', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'utility.js'), 'utf8');

  assert.match(source, /case "kit":\s+return \["IDEA\.md", "SPEC\.md", "PLAN\.md", "plan\.json", "TECH_CONSTRAINTS\.yaml"\]/);
  assert.match(source, /case "eval":\s+return \["IDEA\.md", "SPEC\.md", "PLAN\.md", "plan\.json", "TECH_CONSTRAINTS\.yaml"\]/);
  assert.match(source, /case "finalize":\s+return \["IDEA\.md", "SPEC\.md", "PLAN\.md",\s+"plan\.json", "TECH_CONSTRAINTS\.yaml"\]/);
  assert.match(source, /const HARPER_COMPANION_ROOTS = \['bmad', 'ux'\]/);
  assert.match(source, /const HARPER_COMPANION_MAX_FILES = 40/);
  assert.match(source, /const HARPER_COMPANION_MAX_BYTES_PER_FILE = 64 \* 1024/);
  assert.match(source, /companion::\$\{relPath\}/);
  assert.match(source, /Object\.assign\(core_blobs, await collectHarperCompanionCoreBlobs\(_docRoot, phase\)\)/);
});

test('utility includes BMAD vendor skill blobs only for BMAD methodology requests', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'utility.js'), 'utf8');

  assert.match(source, /collectClikeCapabilityCoreBlobs\(projectRootUri\)/);
  assert.match(source, /Object\.assign\(core_blobs, await collectClikeCapabilityCoreBlobs\(projectRootUri\)\)/);
  assert.match(source, /'\.clike', 'capabilities\.yaml'/);
  assert.match(source, /\['\.clike', 'skills'\], \['SKILL\.md'\]/);
  assert.match(source, /rootParts\.join\('\/'\) === '\.clike\/skills' && name === 'vendor'/);
  assert.match(source, /const BMAD_VENDOR_SKILL_ROOT = '\.clike\/skills\/vendor\/bmad'/);
  assert.match(source, /function payloadRequestsBmadMethodology\(payload\)/);
  assert.match(source, /methodology === 'bmad'/);
  assert.match(source, /collectBmadVendorSkillCoreBlobs\(projectRootUri, payload\)/);
  assert.match(source, /`\$\{BMAD_VENDOR_SKILL_ROOT\}\/manifest\.json`/);
  assert.match(source, /`\$\{BMAD_VENDOR_SKILL_ROOT\}\/\$\{name\}\/SKILL\.md`/);
  assert.match(source, /Object\.assign\(core_blobs, await collectBmadVendorSkillCoreBlobs\(projectRootUri, payload\)\)/);
});
