const test = require('node:test');
const assert = require('node:assert/strict');

const { parseSlash } = require('../slash-parser');

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
  const parsed = parseSlash('/gate REQ-001 --methodology bmad --agent qa');
  assert.match(parsed.error, /\/gate is CLike-owned/);
});
