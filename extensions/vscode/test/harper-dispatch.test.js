const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const {
  getHarperSlashCommandName,
  isHarperSlashText,
  parseSlash,
  shouldBlockHarperSlashFromGenericChatMessage,
} = require('../slash-parser');

function simulateWebviewDispatch(input, mode = 'free') {
  const text = String(input || '');

  if (isHarperSlashText(text)) {
    const slash = parseSlash(text);
    if (!slash || slash.error) {
      return {
        mode,
        type: 'uiError',
        message: 'Invalid Harper command: ' + (slash?.error || 'Invalid Harper command.'),
      };
    }

    const cmd = String(slash.cmd || '').toLowerCase();
    if (cmd === '/eval' || cmd === '/gate') {
      return { mode, type: 'harperEDD', cmd: cmd.slice(1), slash };
    }
    return { mode, type: 'harperRun', cmd: cmd === '/add-req' ? 'extend' : cmd.slice(1), slash };
  }

  return { mode, type: 'sendChat', prompt: text };
}

test('BMAD idea slash text is recognized as Harper and not generic chat', () => {
  const input = '/idea --methodology bmad --agent analyst';

  assert.equal(isHarperSlashText(input), true);
  assert.equal(getHarperSlashCommandName(input), 'idea');

  const dispatched = simulateWebviewDispatch(input, 'free');
  assert.equal(dispatched.type, 'harperRun');
  assert.equal(dispatched.cmd, 'idea');
  assert.notEqual(dispatched.type, 'sendChat');
});

test('Harper slash dispatch is independent of current UI mode', () => {
  const input = '/idea --methodology bmad --agent analyst';

  assert.equal(simulateWebviewDispatch(input, 'free').type, 'harperRun');
  assert.equal(simulateWebviewDispatch(input, 'coding').type, 'harperRun');
  assert.equal(simulateWebviewDispatch(input, 'harper').type, 'harperRun');
});

test('BMAD spec and plan commands dispatch through Harper', () => {
  const cases = [
    ['/spec --methodology bmad --agent pm', 'spec'],
    ['/spec --methodology bmad --agent ux', 'spec'],
    ['/plan --methodology bmad --agent architect', 'plan'],
  ];

  for (const [input, cmd] of cases) {
    const dispatched = simulateWebviewDispatch(input, 'free');
    assert.equal(dispatched.type, 'harperRun', input);
    assert.equal(dispatched.cmd, cmd, input);
  }
});

test('extend and add-req aliases are Harper workflow commands', () => {
  const extend = simulateWebviewDispatch('/extend REQ-001 "Add export"', 'free');
  assert.equal(extend.type, 'harperRun');
  assert.equal(extend.cmd, 'extend');

  const addReq = simulateWebviewDispatch('/add-req "Add export"', 'free');
  assert.equal(addReq.type, 'harperRun');
  assert.equal(addReq.cmd, 'extend');
  assert.equal(addReq.slash.args.alias, 'add-req');
});

test('BMAD eval command dispatches through Harper EDD and not chat', () => {
  const dispatched = simulateWebviewDispatch('/eval REQ-001 --methodology bmad --agent qa', 'coding');

  assert.equal(dispatched.type, 'harperEDD');
  assert.equal(dispatched.cmd, 'eval');
});

test('malformed Harper commands do not fall through to generic chat', () => {
  const dispatched = simulateWebviewDispatch('/kit REQ-001 --methodology bmad --agent architect', 'free');

  assert.equal(dispatched.type, 'uiError');
  assert.match(dispatched.message, /Invalid Harper command:/);
  assert.match(dispatched.message, /not allowed for phase 'kit'/);
});

test('normal text still dispatches to generic chat', () => {
  const dispatched = simulateWebviewDispatch('hello', 'free');

  assert.equal(dispatched.type, 'sendChat');
  assert.equal(dispatched.prompt, 'hello');
});

test('non-Harper slash commands are not classified as Harper workflow commands', () => {
  const cases = ['/ragSearch coffee', '/ragIndex docs/**', '/init CoffeeBuddy', '/help', '/status', '/where', '/switch demo'];

  for (const input of cases) {
    assert.equal(isHarperSlashText(input), false, input);
  }
});

test('extension guard blocks Harper slash text from generic sendChat messages', () => {
  assert.equal(
    shouldBlockHarperSlashFromGenericChatMessage({
      type: 'sendChat',
      prompt: '/idea --methodology bmad --agent analyst',
    }),
    true
  );
  assert.equal(
    shouldBlockHarperSlashFromGenericChatMessage({
      type: 'sendGenerate',
      prompt: '/idea --methodology bmad --agent analyst',
    }),
    false
  );
  assert.equal(
    shouldBlockHarperSlashFromGenericChatMessage({
      type: 'sendChat',
      prompt: '/ragSearch coffee',
    }),
    false
  );
});

test('webview and extension keep explicit Harper slash routing guards', () => {
  const chatUi = fs.readFileSync(path.join(__dirname, '..', 'chat-ui.js'), 'utf8');
  const extension = fs.readFileSync(path.join(__dirname, '..', 'extension.js'), 'utf8');

  assert.match(chatUi, /function dispatchHarperSlashText/);
  assert.ok(
    chatUi.indexOf('if (dispatchHarperSlashText(text))') < chatUi.indexOf("post('sendChat'"),
    'Harper slash guard must run before generic sendChat post'
  );
  assert.match(extension, /Blocked Harper slash command from generic chat route/);
});
