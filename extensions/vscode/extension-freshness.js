'use strict';
// A window keeps running the CLike it loaded when it opened: reinstalling the extension changes the
// files on disk, not the code of the open windows (B2B REQ-032: a window opened the day before ran
// a day of fixes without them, and the repair's test correction was restored and lost). Before a
// run CLike compares its files with the ones it loaded and says once how to load the new version.

const fs = require('fs');

const RUN_TYPES = new Set(['harperRun', 'harperEDD', 'autopilot']);

const STALE_MESSAGE =
  'CLike was updated after this window opened: this window still runs the previous version. ' +
  'Reload the window (command "Developer: Reload Window") to use the new one.';

function stamp(file) {
  try {
    return fs.statSync(file).mtimeMs;
  } catch {
    return 'missing';
  }
}

/**
 * Returns check(type): STALE_MESSAGE the first time a run starts while the extension file differs
 * from the one loaded (rewritten or removed), null otherwise.
 */
function createFreshnessCheck(file) {
  const loaded = stamp(file);
  let warned = false;
  return (type) => {
    if (warned || !RUN_TYPES.has(type) || loaded === 'missing') return null;
    if (stamp(file) === loaded) return null;
    warned = true;
    return STALE_MESSAGE;
  };
}

module.exports = { createFreshnessCheck, STALE_MESSAGE };
