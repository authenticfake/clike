'use strict';
// Autocompletion of the chat's slash commands, in every chat theme: command names, REQ ids, flags
// and their values while the developer types, the signature of the command with the part being
// typed, and the error the parser would give before the command is sent. Pure (no VS Code API,
// no DOM): the same factory runs in node tests and, serialized, inside the webview.

const { BMAD_PHASE_ROLES } = require('./slash-parser');

/**
 * Builds the completer. Self-contained on purpose: `createSlashCompleter.toString()` is injected
 * in the webview, so it may only use its argument and globals.
 */
function createSlashCompleter(bmadRoles) {
  const ROLES = bmadRoles || {};
  // Signature parts: `key` names what the part completes (req, flag:--x, value:--x, sub, text).
  const SPECS = {
    '/help': { group: 'Start & project', desc: 'Quick guide of the commands', sig: [] },
    '/init': { group: 'Start & project', harper: true, desc: 'Initialize the Harper project in the workspace',
      sig: [{ t: '<name>', key: 'text' }, { t: '[--path <abs>]', key: 'flag:--path' }, { t: '[--force]', key: 'flag:--force' }] },
    '/status': { group: 'Start & project', harper: true, desc: 'Harper project / context status', sig: [] },
    '/where': { group: 'Start & project', harper: true, desc: 'Harper workspace / doc-root path', sig: [] },
    '/switch': { group: 'Start & project', harper: true, desc: 'Switch to another Harper project', sig: [{ t: '<name|path>', key: 'text' }] },
    '/idea': { group: 'Harper phases', harper: true, phase: 'idea', desc: 'Formalize IDEA.md; --extend: the next release',
      sig: [{ t: '[--extend', key: 'flag:--extend' }, { t: '[--from attachment]', key: 'flag:--from' }, { t: '[--release vN]', key: 'flag:--release' },
        { t: '[--dry-run]]', key: 'flag:--dry-run' }, { t: '[--methodology bmad', key: 'flag:--methodology' }, { t: '[--agent <role>]]', key: 'flag:--agent' }] },
    '/spec': { group: 'Harper phases', harper: true, phase: 'spec', desc: 'Generate / update SPEC.md (with Use Cases)',
      sig: [{ t: '[file|text]', key: 'text' }, { t: '[--methodology bmad', key: 'flag:--methodology' }, { t: '[--agent pm|ux]]', key: 'flag:--agent' }] },
    '/plan': { group: 'Harper phases', harper: true, phase: 'plan', desc: 'Generate / update PLAN.md and plan.json',
      sig: [{ t: '[spec_path]', key: 'text' }, { t: '[--methodology bmad', key: 'flag:--methodology' }, { t: '[--agent architect|pm]]', key: 'flag:--agent' }] },
    '/extend': { group: 'Harper phases', harper: true, phase: 'extend', desc: 'Append new REQs to the plan',
      sig: [{ t: '[REQ-ID]', key: 'req' }, { t: '"<title>"', key: 'text' }, { t: '[--after REQ-ID]', key: 'flag:--after' },
        { t: '[--from attachment]', key: 'flag:--from' }, { t: '[--methodology bmad', key: 'flag:--methodology' }, { t: '[--agent <role>]]', key: 'flag:--agent' }] },
    '/add-req': { group: 'Harper phases', harper: true, phase: 'extend', desc: 'Alias for /extend',
      sig: [{ t: '[REQ-ID]', key: 'req' }, { t: '"<title>"', key: 'text' }, { t: '[--after REQ-ID]', key: 'flag:--after' }, { t: '[--from attachment]', key: 'flag:--from' }] },
    '/kit': { group: 'Harper phases', harper: true, phase: 'kit', desc: 'Build the KIT candidate of a REQ',
      sig: [{ t: '<REQ-ID>', key: 'req' }, { t: '[--repair]', key: 'flag:--repair' }, { t: '[--integrity|--hardener|--promotion-eval]', key: 'flag:--integrity' },
        { t: '[--phases=…]', key: 'flag:--phases=' }, { t: '[--methodology bmad', key: 'flag:--methodology' }, { t: '[--agent developer]]', key: 'flag:--agent' }] },
    '/eval': { group: 'Eval & gate', harper: true, phase: 'eval', desc: 'Acceptance checks of the REQ in the sandbox (+ regression)',
      sig: [{ t: '<REQ-ID>', key: 'req' }, { t: '[--fix ["hint"]]', key: 'flag:--fix' }, { t: '[--accept "reason"]', key: 'flag:--accept' },
        { t: '[--methodology bmad', key: 'flag:--methodology' }, { t: '[--agent qa|developer]]', key: 'flag:--agent' }] },
    '/gate': { group: 'Eval & gate', harper: true, phase: 'gate', desc: 'Promotion gate: PASS promotes the REQ',
      sig: [{ t: '<REQ-ID>', key: 'req' }, { t: '[--auto-merge|--ask|--no-promote]', key: 'flag:--auto-merge' }, { t: '[--fix ["hint"]]', key: 'flag:--fix' }] },
    '/autopilot': { group: 'Eval & gate', harper: true, desc: 'Every REQ unattended: /kit → /eval --fix → /gate',
      sig: [{ t: '[N | stop | status]', key: 'sub' }, { t: '[--executor cloud|codex|claude]', key: 'flag:--executor' }, { t: '[--methodology bmad]', key: 'flag:--methodology' }] },
    '/tools': { group: 'Eval & gate', harper: true, desc: 'Native tools of the eval sandbox',
      sig: [{ t: '[search <text> | add <tool[@version]>… | update [tool…] | remove <tool>…]', key: 'sub' }] },
    '/finalize': { group: 'Harper phases', harper: true, phase: 'finalize', desc: 'The promoted solution running and configured',
      sig: [{ t: '[--methodology bmad', key: 'flag:--methodology' }, { t: '[--agent tech-writer]]', key: 'flag:--agent' }] },
    '/agent-session': { group: 'Agents', desc: 'Agent chat sessions; new starts a new one', sig: [{ t: '[new | new all]', key: 'sub' }] },
    '/agent-model': { group: 'Agents', desc: 'Show or set the model of Claude Code / Codex',
      sig: [{ t: '[list | claude|codex', key: 'sub' }, { t: '[model]]', key: 'model' }] },
    '/agent-default': { group: 'Agents', desc: 'Preferred local agent', sig: [{ t: 'codex|claude|auto', key: 'sub' }] },
    '/rag': { group: 'RAG', desc: 'Search the RAG; +N attaches a result', sig: [{ t: '<query> | +N | list | clear', key: 'sub' }] },
    '/ragIndex': { group: 'RAG', desc: 'Index files into the RAG', sig: [{ t: '[glob]', key: 'text' }] },
    '/ragSearch': { group: 'RAG', desc: 'Search the RAG', sig: [{ t: '<query>', key: 'text' }] },
  };
  // Flags of each command: the description shown, the value they take, what they exclude.
  const FLAGS = {
    '/init': { '--path': { desc: 'absolute path of the project', value: 'path' }, '--force': { desc: 'into a non-empty folder, existing files kept' } },
    '/idea': {
      '--extend': { desc: 'next release of a delivered project' },
      '--from': { desc: 'inputs from the attachments', value: 'from', needs: '--extend' },
      '--release': { desc: 'release to build (docs/inputs/vN)', value: 'release', needs: '--extend' },
      '--dry-run': { desc: 'show the cascade, write nothing', needs: '--extend' },
      '--methodology': { desc: 'BMAD role guidance', value: 'methodology' },
      '--agent': { desc: 'BMAD role', value: 'agent', needs: '--methodology' },
    },
    '/spec': { '--methodology': { desc: 'BMAD role guidance', value: 'methodology' }, '--agent': { desc: 'BMAD role', value: 'agent', needs: '--methodology' } },
    '/plan': { '--methodology': { desc: 'BMAD role guidance', value: 'methodology' }, '--agent': { desc: 'BMAD role', value: 'agent', needs: '--methodology' } },
    '/extend': {
      '--after': { desc: 'insert after this REQ', value: 'req' },
      '--from': { desc: 'REQs from the attachments', value: 'from' },
      '--methodology': { desc: 'BMAD role guidance', value: 'methodology' },
      '--agent': { desc: 'BMAD role', value: 'agent', needs: '--methodology' },
    },
    '/add-req': { '--after': { desc: 'insert after this REQ', value: 'req' }, '--from': { desc: 'REQs from the attachments', value: 'from' } },
    '/kit': {
      '--repair': { desc: 'repair from the latest eval failures' },
      '--integrity': { desc: 'follow-up phase: integrity eval', excludes: ['--phases='] },
      '--hardener': { desc: 'follow-up phase: promotion hardener', excludes: ['--phases='] },
      '--promotion-eval': { desc: 'follow-up phase: promotion eval', excludes: ['--phases='] },
      '--phases=': { desc: 'explicit follow-up phases', value: 'phases', excludes: ['--integrity', '--hardener', '--promotion-eval'] },
      '--methodology': { desc: 'BMAD developer guidance', value: 'methodology' },
      '--agent': { desc: 'BMAD role', value: 'agent', needs: '--methodology' },
    },
    '/eval': {
      '--fix': { desc: 'repair from the real failures, then eval again', excludes: ['--accept'] },
      '--accept': { desc: 'audited acceptance of an edited test / ci/', value: 'quoted', excludes: ['--fix'] },
      '--methodology': { desc: 'BMAD QA advisory on the eval', value: 'methodology' },
      '--agent': { desc: 'BMAD role', value: 'agent', needs: '--methodology' },
    },
    '/gate': {
      '--auto-merge': { desc: 'promote by auto-merge (3-way per file)', excludes: ['--ask', '--no-promote'] },
      '--ask': { desc: 'choose the promotion strategy', excludes: ['--auto-merge', '--no-promote'] },
      '--no-promote': { desc: 'gate only, no promotion', excludes: ['--auto-merge', '--ask'] },
      '--fix': { desc: 'on failure: KIT repair, then gate again' },
    },
    '/autopilot': {
      '--executor': { desc: 'who writes the KITs in this run', value: 'executor' },
      '--methodology': { desc: 'KIT as BMAD developer, eval with QA advisory', value: 'methodology' },
    },
    '/finalize': { '--methodology': { desc: 'BMAD documentation guidance', value: 'methodology' }, '--agent': { desc: 'BMAD role', value: 'agent', needs: '--methodology' } },
  };
  const SUBS = {
    '/autopilot': [['stop', 'stop after the current step'], ['status', 'where it is, promoted and parked REQs']],
    '/tools': [['search', 'search the catalog'], ['add', 'install and approve for this project'], ['update', 'rebuild at the latest versions'], ['remove', 'withdraw the approval']],
    '/agent-session': [['new', 'new conversation in this mode'], ['new all', 'new conversation in every mode']],
    '/agent-model': [['list', 'models you can set'], ['claude', 'model of Claude Code'], ['codex', 'model of Codex']],
    '/agent-default': [['codex', 'GPT Codex'], ['claude', 'Claude Code'], ['auto', 'CLike chooses']],
    '/rag': [['list', 'current attachments'], ['clear', 'clear the attachments'], ['+1', 'attach result #1 of the last search']],
  };
  const KIT_PHASES = ['integrity_eval', 'promotion_hardener', 'promotion_eval'];
  const DONE = new Set(['done', 'deferred']);
  const lower = (s) => String(s || '').toLowerCase();
  const commandNames = Object.keys(SPECS);

  function specOf(cmd) {
    const key = commandNames.find((c) => lower(c) === lower(cmd));
    return key ? { name: key, ...SPECS[key] } : null;
  }

  /** The tokens before the caret (quotes kept together) and the token being typed. */
  function splitAtCaret(text, caret) {
    const before = String(text || '').slice(0, caret == null ? String(text || '').length : caret);
    const lead = before.match(/^\s*/)[0].length;
    const body = before.slice(lead);
    const tokens = body.match(/"[^"]*"?|'[^']*'?|[^\s]+/g) || [];
    const endsWithSpace = /\s$/.test(body);
    const current = endsWithSpace ? '' : (tokens.pop() || '');
    return { tokens, current, start: before.length - current.length };
  }

  function phaseOf(cmd, tokens) {
    if (lower(cmd) === '/idea' && tokens.some((t) => lower(t) === '--extend')) return 'extend';
    const spec = specOf(cmd);
    return spec && spec.phase ? spec.phase : '';
  }

  /** REQs ranked for a command: what can run now first, with a note when it cannot. */
  function reqItems(cmd, reqs, typed) {
    const c = lower(cmd);
    const rank = (r) => {
      const st = lower(r.status);
      if (c === '/kit') return st === 'in_progress' ? 0 : st === 'open' && !(r.waiting || []).length ? 1 : st === 'open' ? 3 : 4;
      if (c === '/gate') return r.note === 'next: /gate' ? 0 : st === 'in_progress' ? 1 : r.has_kit && !DONE.has(st) ? 2 : 4;
      if (c === '/eval') return st === 'in_progress' ? 0 : r.has_kit && !DONE.has(st) ? 1 : DONE.has(st) ? 2 : 3;
      return 1;
    };
    const warn = (r) => {
      const st = lower(r.status);
      if ((c === '/eval' || c === '/gate') && !r.has_kit) return '⚠ /kit first';
      if (c === '/kit' && (r.waiting || []).length) return `⚠ waits ${r.waiting[0]}`;
      if ((c === '/kit' || c === '/gate') && DONE.has(st)) return 'already done';
      return '';
    };
    const t = lower(typed);
    return (reqs || [])
      .filter((r) => r && r.id && (!t || lower(r.id).startsWith(t) || lower(r.id).replace(/^req-0*/, '').startsWith(t.replace(/^req-0*/, ''))
        || lower(r.title).includes(t)))
      .map((r, i) => ({ r, i, k: rank(r) }))
      .sort((a, b) => a.k - b.k || a.i - b.i)
      .slice(0, 8)
      .map(({ r }) => ({
        label: `${r.id} ${r.title || ''}`.trim(), insert: r.id, kind: 'req',
        detail: `${r.status === 'in_progress' ? '◐' : DONE.has(lower(r.status)) ? '●' : '○'} ${r.note || r.status}`, warn: warn(r),
      }));
  }

  function valueItems(kind, cmd, tokens, ctx, typed) {
    const t = lower(typed);
    const list = (pairs) => pairs.filter(([v]) => !t || lower(v).startsWith(t)).map(([v, d]) => ({ label: v, insert: v, detail: d || '', kind: 'value' }));
    if (kind === 'methodology') return list([['bmad', 'BMAD roles as guidance; CLike contracts win']]);
    if (kind === 'agent') {
      const rules = ROLES[phaseOf(cmd, tokens)] || {};
      return list((rules.allowedAgents || []).map((a) => [a, a === rules.defaultAgent ? 'default for this phase' : '']));
    }
    if (kind === 'executor') return list([['cloud', 'the cloud model'], ['codex', 'GPT Codex'], ['claude', 'Claude Code']]);
    if (kind === 'from') return list([['attachment', 'the files attached to this command']]);
    if (kind === 'release') return list((ctx.releases || []).map((r) => [r, 'docs/inputs/' + r]));
    if (kind === 'req') return reqItems('/extend', ctx.reqs, typed);
    if (kind === 'phases') {
      const done = t.split(',');
      const last = done.pop();
      const prefix = done.length ? done.join(',') + ',' : '';
      return KIT_PHASES.filter((p) => !done.includes(p) && p.startsWith(last))
        .map((p) => ({ label: p, insert: '--phases=' + prefix + p, detail: 'follow-up KIT phase', kind: 'value', replaceToken: true }));
    }
    return [];
  }

  function flagItems(cmd, tokens, typed) {
    const flags = FLAGS[specOf(cmd)?.name] || {};
    const used = new Set(tokens.map((x) => (lower(x).startsWith('--phases=') ? '--phases=' : lower(x).split('=')[0])));
    const t = lower(typed);
    return Object.entries(flags)
      .filter(([f, info]) => !used.has(f) && !(info.excludes || []).some((x) => used.has(x)) && (!info.needs || used.has(info.needs)))
      .filter(([f]) => !t || f.startsWith(t))
      .map(([f, info]) => ({ label: f + (info.value === 'quoted' ? ' "…"' : ''), insert: f, detail: info.desc, kind: 'flag', noSpace: f.endsWith('=') }));
  }

  /** The signature parts with the one being typed marked active. */
  function signature(spec, tokens, current, expecting) {
    if (!spec) return null;
    const flag = expecting ? expecting.flag : (current.startsWith('--') ? lower(current).replace(/=.*$/, '=') : '');
    const reqTyped = tokens.slice(1).some((x) => /^req-\d+/i.test(x));
    return {
      command: spec.name,
      parts: spec.sig.map((p) => {
        let active = false;
        if (flag) active = p.key === 'flag:' + flag || (flag.length > 2 && p.key.startsWith('flag:' + flag));
        else if (p.key === 'req') active = !reqTyped || /^req/i.test(current);
        else if (p.key === 'sub') active = tokens.length <= 1;
        return { text: p.t, active };
      }),
    };
  }

  /**
   * Suggestions for `text` with the caret at `caret`.
   * ctx: { mode, reqs:[{id,title,status,note,waiting,has_kit}], next:{command}, releases, tools,
   *        models:{claude,codex}, history:[] }
   * parse: the chat's parseSlash (the error shown is the one sending would give).
   * Returns { items, replaceFrom, signature, error, fix } — items empty when nothing to suggest.
   */
  function complete(text, caret, ctx, parse) {
    ctx = ctx || {};
    const src = String(text || '');
    const empty = { items: [], replaceFrom: 0, signature: null, error: '', fix: '' };
    if (!/^\s*\//.test(src)) return empty;
    const { tokens, current, start } = splitAtCaret(src, caret);
    const harper = lower(ctx.mode) === 'harper';
    const available = (name) => harper || !SPECS[name].harper;

    // 1. the command name
    if (!tokens.length) {
      const t = lower(current);
      const nextCmd = String(ctx.next && ctx.next.command || '');
      const items = [];
      if (harper && nextCmd && lower(nextCmd).startsWith(t) && t.length >= 1) {
        items.push({ label: nextCmd, insert: nextCmd, detail: 'next action of the project', kind: 'next', whole: true });
      }
      const starts = commandNames.filter((c) => available(c) && lower(c).startsWith(t));
      const contains = commandNames.filter((c) => available(c) && !starts.includes(c) && t.length > 1 && lower(c).includes(t.slice(1)));
      for (const c of [...starts, ...contains]) {
        const s = SPECS[c];
        items.push({ label: c, insert: c, detail: s.desc, sig: s.sig.map((p) => p.t).join(' '), group: s.group, kind: 'command' });
      }
      const known = specOf(current);
      return { ...empty, items: items.slice(0, 10), replaceFrom: start, signature: known && lower(known.name) === t ? signature(known, [current], '', null) : null };
    }

    const cmd = tokens[0];
    const spec = specOf(cmd);
    const result = { ...empty, replaceFrom: start };
    if (!spec) {
      result.error = `Unknown command ${cmd}. Type / to see the commands.`;
      return result;
    }
    if (spec.harper && !harper) result.error = 'This command is available only in Harper mode.';

    // 2. a flag waiting for its value?
    const flags = FLAGS[spec.name] || {};
    const prev = lower(tokens[tokens.length - 1]);
    const expectingInfo = flags[prev];
    let expecting = expectingInfo && expectingInfo.value && expectingInfo.value !== 'quoted' && expectingInfo.value !== 'path'
      ? { flag: prev, kind: expectingInfo.value } : null;
    if (lower(current).startsWith('--phases=')) expecting = { flag: '--phases=', kind: 'phases', typed: current.slice('--phases='.length) };
    result.signature = signature(spec, tokens, current, expecting);

    let items = [];
    if (expecting) {
      items = valueItems(expecting.kind, cmd, tokens, ctx, expecting.typed !== undefined ? expecting.typed : current);
    } else if (current.startsWith('-')) {
      items = flagItems(cmd, tokens, current);
    } else {
      const sub = SUBS[spec.name];
      const args = tokens.slice(1);
      const c = lower(spec.name);
      if (sub && !args.length) {
        items = sub.filter(([v]) => !current || lower(v).startsWith(lower(current))).map(([v, d]) => ({ label: v, insert: v, detail: d, kind: 'value' }));
        if (c === '/autopilot' && !current) items.unshift({ label: 'N', insert: '', detail: 'stop after N promoted REQs (e.g. /autopilot 3)', kind: 'hint' });
      } else if (c === '/tools' && ['add', 'update', 'remove'].includes(lower(args[0]))) {
        items = (ctx.tools || []).filter((n) => (!current || lower(n).startsWith(lower(current))) && !args.includes(n))
          .slice(0, 10).map((n) => ({ label: n, insert: n, detail: 'eval sandbox tool', kind: 'value' }));
      } else if (c === '/agent-model' && ['claude', 'codex'].includes(lower(args[0])) && args.length === 1) {
        items = ((ctx.models || {})[lower(args[0])] || []).filter((m) => !current || lower(m).startsWith(lower(current)))
          .slice(0, 10).map((m) => ({ label: m, insert: m, detail: `model of ${lower(args[0]) === 'claude' ? 'Claude Code' : 'Codex'}`, kind: 'value' }));
      } else if (spec.sig.some((p) => p.key === 'req') && !args.some((x) => /^req-\d+/i.test(x)) && !args.some((x) => x.startsWith('--'))
        && (!current || /^r(e(q(-\d*)?)?)?$/i.test(current) || /^\d+$/.test(current))) {
        items = reqItems(cmd, ctx.reqs, current);
      } else if (!current) {
        items = flagItems(cmd, tokens, '');
      }
    }
    result.items = items.slice(0, 10);

    // 3. what sending it now would say (not while a suggested value is still being typed)
    if (!result.error && typeof parse === 'function' && !(current && result.items.length)) {
      let parsed = null;
      try { parsed = parse(src); } catch (e) { parsed = { error: String(e && e.message || e) }; }
      if (parsed && parsed.error) {
        result.error = String(parsed.error);
        if (lower(spec.name) === '/gate' && /methodology/i.test(result.error)) {
          result.fix = src.replace(/\s+--(methodology|agent)(=\S+|\s+\S+)?/gi, '').trim();
        } else if (/not allowed for phase|Unsupported BMAD agent/i.test(result.error)) {
          const rules = ROLES[phaseOf(cmd, tokens)] || {};
          if (rules.defaultAgent) result.fix = src.replace(/(--agent(=|\s+))\S+/i, `$1${rules.defaultAgent}`);
        } else if (/--agent requires --methodology/i.test(result.error)) {
          result.fix = src.replace(/--agent/i, '--methodology bmad --agent');
        }
      }
    }
    result.fix = String(result.fix || '').trim();
    const reqTok = tokens.slice(1).find((x) => /^req-\d+$/i.test(x));
    if (!result.error && reqTok && Array.isArray(ctx.reqs) && ctx.reqs.length
      && !ctx.reqs.some((r) => lower(r.id) === lower(reqTok))) {
      result.error = `${reqTok.toUpperCase()} is not in the plan (docs/harper/plan.json).`;
    }
    return result;
  }

  /** The text after accepting `item` (replacing the token being typed) and where the caret goes. */
  function accept(text, caret, replaceFrom, item) {
    const src = String(text || '');
    const end = caret == null ? src.length : caret;
    if (item.whole) {
      const value = item.insert + ' ';
      return { text: value + src.slice(end).replace(/^\S*/, '').trimStart(), caret: value.length };
    }
    const tail = src.slice(end).replace(/^\S*/, '');
    const space = item.noSpace || !item.insert ? '' : ' ';
    const head = src.slice(0, replaceFrom) + item.insert + space;
    return { text: head + tail.replace(/^\s+/, ''), caret: head.length };
  }

  /**
   * The command with the methodology preference of the cockpit (BMAD, the role chosen per phase)
   * when the developer typed none: only where the parser accepts it (never /gate, /eval --accept,
   * /autopilot stop|status), so the bubble shows the command that actually runs.
   */
  function withMethodology(text, prefs) {
    const src = String(text || '').trim();
    if (!prefs || prefs.methodology !== 'bmad' || !/^\//.test(src)) return src;
    if (/(^|\s)--(methodology|agent)(\s|=|$)/i.test(src)) return src;
    const tokens = src.split(/\s+/);
    const cmd = lower(tokens[0]);
    if (cmd === '/autopilot') return ['stop', 'status'].includes(lower(tokens[1])) ? src : `${src} --methodology bmad`;
    const spec = specOf(cmd);
    if (!spec || !spec.phase || spec.phase === 'gate' || cmd === '/add-req') return src;
    if (cmd === '/eval' && /\s--accept(\s|$)/i.test(src)) return src;
    const phase = phaseOf(cmd, tokens);
    const rules = ROLES[phase] || {};
    const role = (prefs.roles || {})[phase];
    const agent = role && role !== rules.defaultAgent && (rules.allowedAgents || []).includes(role) ? ` --agent ${role}` : '';
    return `${src} --methodology bmad${agent}`;
  }

  return { complete, accept, withMethodology, specs: SPECS };
}

const completer = createSlashCompleter(BMAD_PHASE_ROLES);

function buildBrowserSlashCompleteSource() {
  return `
const CLIKE_SLASH_COMPLETE = (${createSlashCompleter.toString()})(${JSON.stringify(BMAD_PHASE_ROLES)});
`;
}

module.exports = {
  createSlashCompleter,
  completeSlash: completer.complete,
  acceptCompletion: completer.accept,
  withMethodology: completer.withMethodology,
  buildBrowserSlashCompleteSource,
};
