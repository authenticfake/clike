"""Finalize results rejected for what they did right (test project, release v2 on AWS): a deploy
script named after the secret references it creates, and apply wrappers that delegate to one
implementation holding the CLIKE_ALLOW_CLOUD_MUTATION guard."""

from services.local_agent.finalize_profiles import _is_safe_finalize_root
from services.local_agent.normalize import normalize_local_agent_result


def test_a_script_named_after_secrets_is_code_but_secret_stores_stay_forbidden():
    for ok in ("deploy/aws/04_secrets.sh", "scripts/rotate_credentials.ps1", "src/app/secret_refs.py",
               "deploy/aws/secrets.env.example", "docs/harper/SECRETS.md"):
        assert _is_safe_finalize_root(ok), ok
    for bad in ("deploy/aws/secrets.json", "config/credentials.yaml", "deploy/id_rsa.sh", "keys/private_key.pem",
                "secrets/run.sh", "deploy/secret", ".env"):
        assert not _is_safe_finalize_root(bad), bad


def _finalize(files, existing=None):
    payload = {
        "phase": "finalize", "req_id": "SOLUTION", "exit_code": 0,
        "files": [{"path": p, "content": c} for p, c in files],
        "cloud_provisioning_profile": {"cloud_detected": True},
    }
    if existing is not None:
        payload["existing_source_files"] = [{"path": p, "content": c} for p, c in existing]
    return normalize_local_agent_result(payload)


SH = '#!/bin/sh\nexec python3 "$root/scripts/cloud_local.py" apply "$@"\n'
PS1 = "& $Python (Join-Path $PSScriptRoot 'cloud_local.py') apply @args\n"
GUARDED = "if env.get('CLIKE_ALLOW_CLOUD_MUTATION') != '1':\n    raise RuntimeError('refused')\n"


def test_the_apply_guard_counts_in_the_script_the_wrappers_delegate_to():
    files = [("scripts/provision_cloud_apply.sh", SH), ("scripts/provision_cloud_apply.ps1", PS1),
             ("deploy/aws/04_secrets.sh", "#!/bin/sh\ndata_identity secrets \"$@\"\n")]
    returned = _finalize(files + [("scripts/cloud_local.py", GUARDED)])
    assert "finalize_cloud_apply_guard_missing" not in returned["errors"]
    assert "local_agent_wrote_outside_allowed_roots" not in returned["errors"]
    unchanged = _finalize(files, existing=[("scripts/cloud_local.py", GUARDED)])
    assert "finalize_cloud_apply_guard_missing" not in unchanged["errors"]
    unguarded = _finalize(files + [("scripts/cloud_local.py", "run()\n")])
    assert "finalize_cloud_apply_guard_missing" in unguarded["errors"]
