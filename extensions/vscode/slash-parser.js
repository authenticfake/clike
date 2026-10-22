const SUPPORTED_METHODOLOGIES = new Set(['bmad']);
const SUPPORTED_BMAD_AGENTS = new Set([
  'analyst',
  'pm',
  'architect',
  'developer',
  'ux',
  'qa',
  'tech-writer',
]);

const BMAD_PHASE_ROLES = {
  idea: { defaultAgent: 'analyst', allowedAgents: ['analyst'] },
  spec: { defaultAgent: 'pm', allowedAgents: ['pm', 'ux'] },
  plan: { defaultAgent: 'architect', allowedAgents: ['architect', 'pm'] },
  // /extend and /idea --extend: the release cascade does the work of idea, spec and plan
  extend: { defaultAgent: 'pm', allowedAgents: ['pm', 'analyst', 'architect', 'ux'] },
  kit: { defaultAgent: 'developer', allowedAgents: ['developer'] },
  eval: { defaultAgent: 'qa', allowedAgents: ['qa', 'developer'], advisoryOnly: true },
  gate: { clikeOnly: true, allowedAgents: [] },
  finalize: { defaultAgent: 'tech-writer', allowedAgents: ['tech-writer'] },
};

const GATE_METHODOLOGY_FLAGS_ERROR = 'Gate is CLike-owned. Methodology flags are not accepted for /gate in MVP.';
const HARPER_SLASH_COMMANDS = Object.freeze([
  'idea',
  'spec',
  'plan',
  'kit',
  'eval',
  'gate',
  'finalize',
  'extend',
  'add-req',
]);
const HARPER_SLASH_COMMAND_SET = new Set(HARPER_SLASH_COMMANDS);

function getSlashCommandName(input) {
  const match = String(input || '').trim().match(/^\/([A-Za-z][A-Za-z0-9-]*)\b/);
  return match ? match[1].toLowerCase() : '';
}

function getHarperSlashCommandName(input) {
  const command = getSlashCommandName(input);
  return HARPER_SLASH_COMMAND_SET.has(command) ? command : '';
}

function isHarperSlashText(input) {
  return Boolean(getHarperSlashCommandName(input));
}

function shouldBlockHarperSlashFromGenericChatMessage(message) {
  return Boolean(
    message &&
    String(message.type || '') === 'sendChat' &&
    isHarperSlashText(message.prompt)
  );
}

// Decoration pasted in front of a command (terminal box borders, quote markers, bullets,
// non-breaking and zero-width spaces) must not turn it into plain chat text.
const SLASH_PREFIX_NOISE = /^[\s\u00a0\u200b-\u200d\ufeff\u2500-\u257f>•·]+(?=\/)/;

function tokenizeSlash(input) {
  const text = String(input || '').trim().replace(SLASH_PREFIX_NOISE, '');
  if (!text.startsWith('/')) return [];
  return text.match(/"([^"]*)"|'([^']*)'|[^\s]+/g) || [];
}

function normalizeReqToken(value) {
  return String(value || '')
    .trim()
    .toUpperCase()
    .replace(/[–—]/g, '-')
    .replace(/[,;]+$/, '');
}

function normalizePhaseFromCommand(cmd) {
  return String(cmd || '').replace(/^\//, '').trim().toLowerCase();
}

function parseMethodologyFlags(tokens, phase) {
  const rest = [];
  let methodology = null;
  let agent = null;
  let error = null;
  let sawMethodologyFlag = false;
  let sawAgentFlag = false;

  for (let i = 0; i < tokens.length; i += 1) {
    const token = String(tokens[i] || '').trim();
    const lower = token.toLowerCase();

    if (lower === '--methodology') {
      sawMethodologyFlag = true;
      methodology = String(tokens[i + 1] || '').trim().toLowerCase();
      i += 1;
      continue;
    }

    if (lower.startsWith('--methodology=')) {
      sawMethodologyFlag = true;
      methodology = token.split('=').slice(1).join('=').trim().toLowerCase();
      continue;
    }

    if (lower === '--agent') {
      sawAgentFlag = true;
      agent = String(tokens[i + 1] || '').trim().toLowerCase();
      i += 1;
      continue;
    }

    if (lower.startsWith('--agent=')) {
      sawAgentFlag = true;
      agent = token.split('=').slice(1).join('=').trim().toLowerCase();
      continue;
    }

    rest.push(token);
  }

  if (phase === 'gate' && (sawMethodologyFlag || sawAgentFlag)) {
    error = GATE_METHODOLOGY_FLAGS_ERROR;
  } else if (agent && !methodology) {
    error = '--agent requires --methodology.';
  } else if (methodology && !SUPPORTED_METHODOLOGIES.has(methodology)) {
    error = `Unsupported methodology: ${methodology}. Supported methodologies: bmad.`;
  } else if (methodology === 'bmad' && agent && !SUPPORTED_BMAD_AGENTS.has(agent)) {
    error = `Unsupported BMAD agent: ${agent}. Supported agents: ${Array.from(SUPPORTED_BMAD_AGENTS).join(', ')}.`;
  } else if (methodology === 'bmad' && agent) {
    const phaseRules = BMAD_PHASE_ROLES[phase] || null;
    const allowed = new Set((phaseRules && phaseRules.allowedAgents) || []);
    if (!phaseRules || phaseRules.clikeOnly || !allowed.has(agent)) {
      if (phase === 'gate' && phaseRules && phaseRules.clikeOnly) {
        error = GATE_METHODOLOGY_FLAGS_ERROR;
      } else {
        const allowedText = allowed.size ? Array.from(allowed).join(', ') : 'none';
        error = `BMAD agent '${agent}' is not allowed for phase '${phase}'. Allowed agents: ${allowedText}.`;
      }
    }
  }

  const methodologyContext = methodology
    ? {
        methodology,
        agent: agent || null,
      }
    : null;

  return {
    rest,
    methodology,
    agent,
    methodology_context: methodologyContext,
    error,
  };
}

function withMethodologyArgs(args, flags) {
  const next = { ...(args || {}) };
  if (flags.methodology) next.methodology = flags.methodology;
  if (flags.agent) next.agent = flags.agent;
  if (flags.methodology_context) next.methodology_context = flags.methodology_context;
  return next;
}

/** `/eval|/gate REQ --fix ["hint"]`: tokens after --fix are the developer hint for the KIT repair. */
function parseFixArgs(tokens) {
  const rest = [];
  const hint = [];
  let fix = false;
  for (const raw of tokens || []) {
    const token = String(raw || '').trim();
    if (!token) continue;
    if (token.toLowerCase() === '--fix') {
      fix = true;
      continue;
    }
    if (fix) hint.push(token.replace(/^(["'])(.*)\1$/, '$2'));
    else rest.push(token);
  }
  return { fix, hint: hint.join(' ').trim(), rest };
}

function parseSlash(input) {
  const parts = tokenizeSlash(input);
  if (!parts.length) return null;

  const cmd = String(parts[0] || '').toLowerCase();
  // /idea --extend runs the extend phase: its BMAD agents are those of extend
  const phase = cmd === '/idea' && parts.some((t) => String(t).toLowerCase() === '--extend')
    ? 'extend'
    : normalizePhaseFromCommand(cmd);
  const parsedFlags = parseMethodologyFlags(parts.slice(1).map(x => String(x).trim()).filter(Boolean), phase);
  let rest = parsedFlags.rest;

  const finish = (args) => {
    const parsed = { cmd, args: withMethodologyArgs(args, parsedFlags) };
    if (parsedFlags.error) parsed.error = parsedFlags.error;
    return parsed;
  };

  if (cmd === '/init') {
    const name = rest[0];
    const tail = rest.slice(1);
    const force = tail.includes('--force');
    const pathTokens = tail.filter(x => x !== '--force');
    const path = pathTokens.length ? pathTokens.join(' ') : undefined;
    return finish({ name, path, force });
  }

  if (cmd === '/autopilot') {
    // /autopilot [N] | stop | status: the REQs of the plan unattended (kit → eval --fix → gate)
    const first = String(rest[0] || '').toLowerCase();
    if (first === 'stop' || first === 'status') return finish({ action: first });
    const max = /^\d+$/.test(first) ? Number(first) : 0;
    return finish({ action: 'start', max });
  }

  if (cmd === '/tools') {
    // /tools [list|search <q>|add <name[@version]>…|remove <name>…]: native tools of the eval sandbox
    const action = String(rest[0] || 'list').toLowerCase();
    return finish({ action, names: rest.slice(1) });
  }

  if (cmd === '/eval' || cmd === '/gate') {
    // /gate promotion mode for this run: --ask (interactive strategy), --no-promote, --auto-merge
    let promote;
    if (cmd === '/gate') {
      const flags = { '--ask': 'ask', '--no-promote': 'off', '--auto-merge': 'merge' };
      rest = rest.filter((t) => {
        const mode = flags[String(t).toLowerCase()];
        if (mode) promote = mode;
        return !mode;
      });
    }
    // /eval REQ --accept ["reason"]: the developer accepts a deliberate edit of the locked tests / ci
    let accept;
    if (cmd === '/eval') {
      const at = rest.findIndex((t) => String(t).toLowerCase() === '--accept');
      if (at >= 0) {
        accept = rest.slice(at + 1).map((t) => String(t).replace(/^(["'])(.*)\1$/, '$2')).join(' ').trim();
        rest = rest.slice(0, at);
      }
    }
    const fixArgs = parseFixArgs(rest);
    const tokens = fixArgs.rest;
    const testMode = tokens.slice(1) ? tokens.slice(1)[0] : 'auto';
    const modeContent = tokens.slice(2) ? tokens.slice(2)[0] : 'pass';

    let targets = null;
    if (!tokens.length) {
      targets = '';
    } else {
      const isReq = (value) => /^req-\d+/i.test(value);
      const onlyReqs = tokens.every(isReq);
      targets = onlyReqs ? tokens : [tokens[0]];
    }

    const fix = fixArgs.fix ? { fix: true, hint: fixArgs.hint } : {};
    return finish({ targets, testMode, modeContent, ...fix, ...(promote ? { promote } : {}), ...(accept !== undefined ? { accept } : {}) });
  }

  if (cmd === '/extend' || cmd === '/add-req') {
    let anchorReq = '';
    let explicitReq = '';
    let fromAttachment = false;
    const freeTextTokens = [];

    for (let i = 0; i < rest.length; i += 1) {
      const token = rest[i];
      const lower = token.toLowerCase();

      if (lower === '--from' && String(rest[i + 1] || '').toLowerCase() === 'attachment') {
        fromAttachment = true;
        i += 1;
        continue;
      }

      if (lower === '--from=attachment') {
        fromAttachment = true;
        continue;
      }

      if (lower === '--after') {
        anchorReq = normalizeReqToken(rest[i + 1] || '');
        i += 1;
        continue;
      }

      if (lower.startsWith('--after=')) {
        anchorReq = normalizeReqToken(token.split('=').slice(1).join('='));
        continue;
      }

      const normalized = normalizeReqToken(token);
      if (!explicitReq && /^REQ-\d+$/i.test(normalized)) {
        explicitReq = normalized;
        continue;
      }

      freeTextTokens.push(token);
    }

    return finish({
      anchorReq,
      explicitReq,
      fromAttachment,
      rawInput: freeTextTokens.join(' ').trim(),
      alias: cmd === '/add-req' ? 'add-req' : null,
    });
  }

  if (cmd === '/kit') {
    const reqTokens = [];
    const candidateTokens = [];
    const phaseTokens = [];
    let inlinePhases = null;
    let repair = false;

    for (const token of rest) {
      const lower = token.toLowerCase();

      if (lower === '--repair') {
        repair = true;
        continue;
      }
      if (lower === '--integrity') {
        phaseTokens.push('integrity_eval');
        continue;
      }
      if (lower === '--hardener') {
        phaseTokens.push('promotion_hardener');
        continue;
      }
      if (lower === '--promotion-eval') {
        phaseTokens.push('promotion_eval');
        continue;
      }
      if (lower.startsWith('--phases=')) {
        inlinePhases = token.split('=').slice(1).join('=').trim();
        continue;
      }

      const normalized = normalizeReqToken(token);
      if (/^REQ-\d+/i.test(normalized)) {
        reqTokens.push(normalized);
        continue;
      }

      candidateTokens.push(normalized);
    }

    let targets = '';
    if (reqTokens.length) {
      targets = reqTokens;
    } else if (candidateTokens.length) {
      targets = [candidateTokens[0]];
    }

    let phases = null;
    if (inlinePhases) {
      phases = inlinePhases
        .split(',')
        .map(x => String(x).trim().toLowerCase())
        .filter(Boolean);
    } else if (phaseTokens.length) {
      phases = Array.from(new Set(phaseTokens));
    }

    return finish({
      targets,
      phases,
      ...(repair ? { repair: true } : {}),
    });
  }

  if (cmd === '/plan' || cmd === '/spec') {
    return finish({ targets: '' });
  }

  if (cmd === '/idea') {
    // /idea --extend [--from attachment] [--dry-run] [--release vN] [text]: the release cascade
    if (!rest.some((t) => t.toLowerCase() === '--extend')) return finish({ name: rest[0] });
    let fromAttachment = false;
    let dryRun = false;
    let release = '';
    const text = [];
    for (let i = 0; i < rest.length; i += 1) {
      const lower = rest[i].toLowerCase();
      if (lower === '--extend') continue;
      if (lower === '--dry-run') { dryRun = true; continue; }
      if (lower === '--from=attachment') { fromAttachment = true; continue; }
      if (lower === '--from' && String(rest[i + 1] || '').toLowerCase() === 'attachment') { fromAttachment = true; i += 1; continue; }
      if (lower.startsWith('--release=')) { release = lower.split('=').slice(1).join('='); continue; }
      if (lower === '--release') { release = String(rest[i + 1] || '').toLowerCase(); i += 1; continue; }
      text.push(rest[i]);
    }
    return finish({ extend: true, fromAttachment, dryRun, release, rawInput: text.join(' ').trim() });
  }

  if (cmd === '/agent-default') {
    return finish({ value: String(rest[0] || '').trim().toLowerCase() });
  }

  if (cmd === '/agent-session') {
    return finish({ action: rest.join(' ').trim().toLowerCase() });
  }

  if (cmd === '/agent-model') {
    return finish({ agent: String(rest[0] || '').trim().toLowerCase(), model: rest.slice(1).join(' ').trim() });
  }

  if (cmd === '/ragindex') {
    return finish({ glob: rest.join(' ').trim() });
  }

  if (cmd === '/ragsearch') {
    return finish({ query: rest.join(' ').trim() });
  }

  if (cmd === '/rag') {
    const tail = rest.join(' ').trim();
    if (!tail) return finish({ action: 'help' });
    if (tail[0] === '+') {
      const index = parseInt(tail.slice(1), 10);
      if (Number.isFinite(index) && index > 0) {
        return finish({ action: 'addByIndex', index });
      }
    }
    if (/^(list|clear)$/i.test(tail)) {
      return finish({ action: tail.toLowerCase() });
    }
    return finish({ action: 'search', query: tail });
  }

  return finish({});
}

function buildBrowserSlashParserSource() {
  return `
const CLIKE_SLASH_PARSER = (() => {
  const module = { exports: {} };
  const exports = module.exports;
  const HARPER_SLASH_COMMANDS = ${JSON.stringify(HARPER_SLASH_COMMANDS)};
  const HARPER_SLASH_COMMAND_SET = new Set(HARPER_SLASH_COMMANDS);
  ${getSlashCommandName.toString()}
  ${getHarperSlashCommandName.toString()}
  ${isHarperSlashText.toString()}
  const SLASH_PREFIX_NOISE = ${SLASH_PREFIX_NOISE.toString()};
  ${tokenizeSlash.toString()}
  ${normalizeReqToken.toString()}
  ${normalizePhaseFromCommand.toString()}
  const SUPPORTED_METHODOLOGIES = new Set(${JSON.stringify(Array.from(SUPPORTED_METHODOLOGIES))});
  const SUPPORTED_BMAD_AGENTS = new Set(${JSON.stringify(Array.from(SUPPORTED_BMAD_AGENTS))});
  const BMAD_PHASE_ROLES = ${JSON.stringify(BMAD_PHASE_ROLES)};
  const GATE_METHODOLOGY_FLAGS_ERROR = ${JSON.stringify(GATE_METHODOLOGY_FLAGS_ERROR)};
  ${parseMethodologyFlags.toString()}
  ${withMethodologyArgs.toString()}
  ${parseFixArgs.toString()}
  ${parseSlash.toString()}
  return { parseSlash, isHarperSlashText, getHarperSlashCommandName };
})();
function parseSlash(s) {
  return CLIKE_SLASH_PARSER.parseSlash(s);
}
function isHarperSlashText(s) {
  return CLIKE_SLASH_PARSER.isHarperSlashText(s);
}
function getHarperSlashCommandName(s) {
  return CLIKE_SLASH_PARSER.getHarperSlashCommandName(s);
}
`;
}

module.exports = {
  BMAD_PHASE_ROLES,
  GATE_METHODOLOGY_FLAGS_ERROR,
  HARPER_SLASH_COMMANDS,
  SUPPORTED_BMAD_AGENTS,
  SUPPORTED_METHODOLOGIES,
  getHarperSlashCommandName,
  getSlashCommandName,
  isHarperSlashText,
  parseSlash,
  parseMethodologyFlags,
  parseFixArgs,
  shouldBlockHarperSlashFromGenericChatMessage,
  buildBrowserSlashParserSource,
};
