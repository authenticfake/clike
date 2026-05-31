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
  kit: { defaultAgent: 'developer', allowedAgents: ['developer'] },
  eval: { defaultAgent: 'qa', allowedAgents: ['qa', 'developer'], advisoryOnly: true },
  gate: { clikeOnly: true, allowedAgents: [] },
  finalize: { defaultAgent: 'tech-writer', allowedAgents: ['tech-writer'] },
};

function tokenizeSlash(input) {
  const text = String(input || '').trim();
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

  for (let i = 0; i < tokens.length; i += 1) {
    const token = String(tokens[i] || '').trim();
    const lower = token.toLowerCase();

    if (lower === '--methodology') {
      methodology = String(tokens[i + 1] || '').trim().toLowerCase();
      i += 1;
      continue;
    }

    if (lower.startsWith('--methodology=')) {
      methodology = token.split('=').slice(1).join('=').trim().toLowerCase();
      continue;
    }

    if (lower === '--agent') {
      agent = String(tokens[i + 1] || '').trim().toLowerCase();
      i += 1;
      continue;
    }

    if (lower.startsWith('--agent=')) {
      agent = token.split('=').slice(1).join('=').trim().toLowerCase();
      continue;
    }

    rest.push(token);
  }

  if (agent && !methodology) {
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
        error = '/gate is CLike-owned and methodology flags are unsupported in this MVP.';
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

function parseSlash(input) {
  const parts = tokenizeSlash(input);
  if (!parts.length) return null;

  const cmd = String(parts[0] || '').toLowerCase();
  const phase = normalizePhaseFromCommand(cmd);
  const parsedFlags = parseMethodologyFlags(parts.slice(1).map(x => String(x).trim()).filter(Boolean), phase);
  const rest = parsedFlags.rest;

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

  if (cmd === '/eval' || cmd === '/gate') {
    const testMode = rest.slice(1) ? rest.slice(1)[0] : 'auto';
    const modeContent = rest.slice(2) ? rest.slice(2)[0] : 'pass';

    let targets = null;
    if (!rest.length) {
      targets = '';
    } else {
      const isReq = (value) => /^req-\d+/i.test(value);
      const onlyReqs = rest.every(isReq);
      targets = onlyReqs ? rest : [rest[0]];
    }

    return finish({ targets, testMode, modeContent });
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

    for (const token of rest) {
      const lower = token.toLowerCase();

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

    return finish({ targets, phases });
  }

  if (cmd === '/plan' || cmd === '/spec') {
    return finish({ targets: '' });
  }

  if (cmd === '/idea') {
    return finish({ name: rest[0] });
  }

  if (cmd === '/agent-default') {
    return finish({ value: String(rest[0] || '').trim().toLowerCase() });
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
  ${tokenizeSlash.toString()}
  ${normalizeReqToken.toString()}
  ${normalizePhaseFromCommand.toString()}
  const SUPPORTED_METHODOLOGIES = new Set(${JSON.stringify(Array.from(SUPPORTED_METHODOLOGIES))});
  const SUPPORTED_BMAD_AGENTS = new Set(${JSON.stringify(Array.from(SUPPORTED_BMAD_AGENTS))});
  const BMAD_PHASE_ROLES = ${JSON.stringify(BMAD_PHASE_ROLES)};
  ${parseMethodologyFlags.toString()}
  ${withMethodologyArgs.toString()}
  ${parseSlash.toString()}
  return { parseSlash };
})();
function parseSlash(s) {
  return CLIKE_SLASH_PARSER.parseSlash(s);
}
`;
}

module.exports = {
  BMAD_PHASE_ROLES,
  SUPPORTED_BMAD_AGENTS,
  SUPPORTED_METHODOLOGIES,
  parseSlash,
  parseMethodologyFlags,
  buildBrowserSlashParserSource,
};
