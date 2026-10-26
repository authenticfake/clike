"""Native tools of the eval sandbox: detected from the KIT, installed on confirmation, on PATH."""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

import eval_tools  # noqa: E402
import sandbox_resources  # noqa: E402
from eval_runner import EvalRunner  # noqa: E402

from tests.test_eval_regression import AUTH, _RegressionProject  # noqa: E402


class CatalogTests(unittest.TestCase):
    def test_catalog_entries_are_installable_specs(self):
        catalog = eval_tools.load_catalog()
        self.assertIn("postgresql-client", catalog)
        for name, entry in catalog.items():
            with self.subTest(name):
                self.assertTrue(entry["packages"] and all(eval_tools.package_spec_ok(p) for p in entry["packages"]))
                self.assertTrue(entry["binaries"])

    def test_resolve_names_binaries_and_versions(self):
        catalog = eval_tools.load_catalog()
        r = eval_tools.resolve(["kcat", "jdk@17", "maven", "az@2.80.0"], catalog)
        by = {t["name"]: t for t in r["tools"]}
        self.assertEqual(list(by), ["kafkacat", "jdk@17", "maven", "azure-cli@2.80.0"])
        self.assertEqual(by["jdk@17"]["packages"], ["openjdk=17.*"])
        self.assertEqual(by["maven"]["packages"], ["maven", "openjdk"])  # its own environment
        self.assertEqual(by["azure-cli@2.80.0"]["pip"], ["azure-cli==2.80.0"])  # a PyPI CLI is pinned on pip
        self.assertIn("mvn", by["maven"]["binaries"])
        self.assertEqual(eval_tools.resolve(["nope", "a;rm -rf /"], catalog)["unknown"], ["nope", "a;rm -rf /"])

    def test_project_entries_and_approvals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".clike").mkdir()
            (root / ".clike" / "eval-tools.yaml").write_text(
                "tools: [kafkacat, jdk@17]\ncustom:\n  sqlcl: {packages: [sqlcl], binaries: [sql], about: Oracle SQLcl}\n"
            )
            self.assertEqual(eval_tools.approved_tools(root), ["kafkacat", "jdk@17"])
            self.assertEqual(eval_tools.resolve(["sqlcl"], eval_tools.load_catalog(root))["tools"][0]["packages"], ["sqlcl"])

    def test_tools_go_after_the_image_programs_on_path(self):
        with patch.dict(os.environ, {"CLIKE_EVAL_TOOLS_BIN": "/opt/clike-tools/bin"}):
            self.assertEqual(eval_tools.search_path("/usr/bin:/bin"), "/usr/bin:/bin:/opt/clike-tools/bin")
            self.assertEqual(eval_tools.search_path("/usr/bin:/opt/clike-tools/bin"), "/usr/bin:/opt/clike-tools/bin")


class DetectionTests(unittest.TestCase):
    def test_programs_the_code_runs_are_found(self):
        catalog = eval_tools.load_catalog()
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "backup.py").write_text('native("pg_dump", source)\nsubprocess.run(["kcat", "-b", broker])\n')
            (src / "deploy.sh").write_text("#!/bin/sh\naws s3 ls\n  terraform validate\n")
            (src / "notes.py").write_text('MESSAGE = "go to the page, then jq it"\nlabel = "helm chart"\n')
            (src / "Client.java").write_text('new ProcessBuilder("mysqldump", "--all-databases");\n')
            (src / "LTC.json").write_text('{"command": "pwsh -NoProfile -File ci/check-powershell.ps1"}')
            (src / "README.md").write_text('Run "pwsh" later.\n')
            self.assertEqual(eval_tools.used([src], catalog), ["aws", "kcat", "mysqldump", "pg_dump", "pwsh", "terraform"])

    def test_missing_programs_in_failures(self):
        catalog = eval_tools.load_catalog()
        for text, expected in (
            ("sh: 1: kcat: command not found", ["kcat"]),
            ("Error: spawn mysqldump ENOENT", ["mysqldump"]),
            ("FileNotFoundError: [Errno 2] No such file or directory: 'pg_dump'", ["pg_dump"]),
            ('java.io.IOException: Cannot run program "mvn": error=2', ["mvn"]),
            # B2B REQ-037: the .ps1 check had no PowerShell and was sent to a repair
            ("/bin/sh: 1: pwsh: not found", ["pwsh"]),
            ("sh: 1: frobnicate: not found", []),  # not in the catalog
        ):
            self.assertEqual(eval_tools.missing_from_failure(text, catalog), expected, text)

    def test_needs_lists_what_the_sandbox_lacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kit = root / "runs" / "kit" / "REQ-001"
            (kit / "src").mkdir(parents=True)
            (kit / "ci").mkdir()
            (kit / "src" / "app.py").write_text('subprocess.run(["kcat", "-L"])\n')
            (kit / "ci" / "LTC.json").write_text(json.dumps({"environment": {"tools": ["jdk@17", "psql"]}}))
            with patch.object(eval_tools, "available", lambda b: b == "psql"):
                result = eval_tools.check(root, "REQ-001")
        tools = {m["tool"]: m for m in result["missing"]}
        self.assertEqual(set(tools), {"jdk@17", "kafkacat"})
        self.assertEqual(tools["kafkacat"]["source"], "used")
        self.assertEqual(tools["jdk@17"]["source"], "declared")
        self.assertTrue(all(m["in_catalog"] for m in result["missing"]))

    def test_script_linters_install_for_every_project_without_asking(self):
        # B2B: shellcheck (REQ-033) and pwsh (REQ-037) needed /tools add in each project
        catalog = eval_tools.load_catalog()
        self.assertEqual(eval_tools.auto_tools(catalog), {"shellcheck", "powershell"})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kit = root / "runs" / "kit" / "REQ-001"
            (kit / "ci").mkdir(parents=True)
            (kit / "ci" / "LTC.json").write_text(json.dumps({"environment": {"tools": ["kcat"]}, "checks": [
                {"id": "powershell", "command": "pwsh -NoProfile -File ci/check.ps1"},
                {"id": "shell", "command": "shellcheck -x scripts/run.sh"},
            ]}))
            with patch.object(eval_tools, "available", lambda b: False):
                result = eval_tools.check(root, "REQ-001")
        approved = {m["tool"]: m["approved"] for m in result["missing"]}
        self.assertEqual(approved, {"powershell": True, "shellcheck": True, "kafkacat": False})
        self.assertIn("pwsh", result["auto_install"])


class RunnerTests(unittest.TestCase):
    def test_a_missing_catalog_program_is_reported_not_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kit = root / "runs" / "kit" / "REQ-001"
            (kit / "ci").mkdir(parents=True)
            ltc = {"req_id": "REQ-001", "checks": [{"id": "e2e", "command": "kcat -L -b localhost:9092"}]}
            (kit / "ci" / "LTC.json").write_text(json.dumps(ltc))
            with patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
                report = EvalRunner(root).run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-001")
            case = next(c for c in report.cases if c.name == "e2e")
            self.assertTrue(case.blocked)
            self.assertIn("Missing in the eval sandbox: kcat", case.excerpt)
            self.assertEqual(report.missing_tools, ["kcat"])


class DiskTests(unittest.TestCase):
    def test_only_the_last_used_req_dirs_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "eval"
            project = base / "proj"
            for n in range(1, 7):
                d = project / f"REQ-00{n}"
                d.mkdir(parents=True)
                (d / "work").mkdir()
                os.utime(d / "work", (time.time() - 1000 + n, time.time() - 1000 + n))
                os.utime(d, (time.time() - 1000 + n, time.time() - 1000 + n))
            (project / ".npm-cache").mkdir()
            removed = []
            with patch.dict(os.environ, {"CLIKE_EVAL_BASE_DIR": str(base)}):
                sandbox_resources.prune_eval_dirs(project, "REQ-001", keep=3, min_free_gb=0, remove=lambda p: removed.append(p.name))
            # REQ-001 is current; the two most recent others stay (3 with the current one)
            self.assertEqual(sorted(removed), ["REQ-002", "REQ-003", "REQ-004"])
            with patch.dict(os.environ, {"CLIKE_EVAL_BASE_DIR": ""}):
                self.assertEqual(sandbox_resources.prune_eval_dirs(project, None, keep=0, remove=lambda p: removed.append(p)), [])

    def test_a_full_volume_stops_the_eval(self):
        with patch.object(sandbox_resources, "_free_bytes", return_value=512 * 1024 ** 2):
            self.assertIn("0.5 GB free", sandbox_resources.disk_preflight(Path("/")))
        with patch.object(sandbox_resources, "_free_bytes", return_value=50 * 1024 ** 3):
            self.assertIsNone(sandbox_resources.disk_preflight(Path("/")))


class RoutesTests(_RegressionProject):
    def test_check_and_install_routes(self):
        (self.proj / "runs" / "kit" / "REQ-002" / "src" / "dump.py").write_text('run(["mysqldump", "db"])\n')
        with patch.object(eval_tools, "available", lambda b: False):
            body = self.client.post("/v1/eval/tools/check", json={"project_root": str(self.proj), "req_id": "REQ-002"},
                                    headers=AUTH).json()
        self.assertEqual([m["tool"] for m in body["missing"]], ["mysql-client"])
        self.assertFalse(body["installable"])
        refused = self.client.post("/v1/eval/tools/install", json={"project_root": str(self.proj), "tools": ["mysql-client"]},
                                   headers=AUTH)
        self.assertEqual(refused.status_code, 503)
        listed = self.client.get("/v1/eval/tools", params={"project_root": str(self.proj)}, headers=AUTH).json()
        self.assertIn("kafkacat", listed["catalog"])


class ToolsServiceTests(unittest.TestCase):
    """The service with a fake micromamba: one environment per tool, exact lock, update, restore."""

    FAKE = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
log = os.environ["FAKE_LOG"]
open(log, "a").write(" ".join(args) + "\n")
version = os.environ.get("FAKE_VERSION", "1.0")
prefix = args[args.index("-p") + 1] if "-p" in args else ""
if args[:1] == ["list"]:
    names = open(os.path.join(prefix, "conda-meta", "names")).read().split()
    print(json.dumps({"packages": [{"name": n, "version": version} for n in names]}))
elif args[:2] == ["env", "export"]:
    print("@EXPLICIT\nhttps://conda.anaconda.org/conda-forge/fake-" + version + ".conda#md5")
elif args[:1] == ["create"]:
    if os.environ.get("FAKE_FAIL"):
        sys.exit("solver failed")
    os.makedirs(os.path.join(prefix, "bin"), exist_ok=True)
    os.makedirs(os.path.join(prefix, "conda-meta"), exist_ok=True)
    pkgs = [a.split("=")[0] for a in args[args.index("--strict-channel-priority") + 1:]] if "--strict-channel-priority" in args else ["fake"]
    open(os.path.join(prefix, "conda-meta", "names"), "w").write(" ".join(pkgs))
    for name in pkgs + ["python"]:
        path = os.path.join(prefix, "bin", "kcat" if name == "kafkacat" else name)
        if name == "python":
            body = "#!/bin/sh\nif [ \"$3\" = freeze ]; then echo azure-cli==" + version + "; fi\n"
        else:
            body = "#!/bin/sh\necho " + name + "-" + version + "\n"
        open(path, "w").write(body)
        os.chmod(path, 0o755)
"""

    def setUp(self):
        from eval_runner import _SECRET_ENV_NAME_RE

        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "tools"
        fakebin = base / "fakebin"
        fakebin.mkdir()
        (fakebin / "micromamba").write_text(self.FAKE)
        (fakebin / "micromamba").chmod(0o755)
        self.log = base / "calls.log"
        env = {k: v for k, v in os.environ.items() if not _SECRET_ENV_NAME_RE.search(k)}
        env.update({"CLIKE_EVAL_TOOLS_ROOT": str(self.root), "FAKE_LOG": str(self.log),
                    "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}"})
        self.env = patch.dict(os.environ, env, clear=True)
        self.env.start()
        sys.modules.pop("eval_tools_app", None)
        import eval_tools_app
        from starlette.testclient import TestClient

        self.app = eval_tools_app
        self.client = TestClient(eval_tools_app.app)

    def tearDown(self):
        self.env.stop()
        sys.modules.pop("eval_tools_app", None)
        self.tmp.cleanup()

    def _install(self, *tools):
        return self.client.post("/install", json={"tools": list(tools)})

    def test_each_tool_gets_its_own_environment_and_only_its_programs(self):
        body = self._install({"name": "kafkacat", "packages": ["kafkacat"], "binaries": ["kafkacat", "kcat"]},
                             {"name": "jdk@17", "packages": ["openjdk=17.*"], "binaries": ["openjdk"]}).json()
        self.assertEqual(body["binaries"], ["kcat", "openjdk"])
        self.assertEqual(body["missing_binaries"], ["kafkacat"])
        self.assertEqual(body["versions"]["kafkacat"], {"kafkacat": "1.0"})
        self.assertTrue((self.root / "envs" / "kafkacat" / "bin" / "kcat").is_file())
        self.assertTrue((self.root / "envs" / "jdk-17").is_dir())
        self.assertFalse((self.root / "bin" / "python").exists())  # never shadows the image's python
        lock = self.client.get("/lock").json()
        self.assertIn("@EXPLICIT", lock["kafkacat"]["lock"]["explicit"])
        self.assertNotIn("lock", self.client.get("/installed").json()["tools"]["kafkacat"])

    def test_the_default_tools_are_there_from_the_start(self):
        # shellcheck and PowerShell: no /tools add in each project (B2B REQ-033, REQ-037)
        self.assertEqual(self.app.install_defaults(), ["powershell", "shellcheck"])
        installed = self.client.get("/installed").json()["tools"]
        self.assertEqual(set(installed), {"powershell", "shellcheck"})
        self.assertEqual(self.app.install_defaults(), [])  # once

    def test_update_reports_the_changes_and_a_failed_rebuild_keeps_the_old_one(self):
        self._install({"name": "kafkacat", "packages": ["kafkacat"], "binaries": ["kcat"]})
        os.environ["FAKE_VERSION"] = "2.0"
        result = self.client.post("/update", json={"tools": []}).json()
        self.assertEqual(result["changes"], {"kafkacat": {"kafkacat": ["1.0", "2.0"]}})
        self.assertTrue(result["updated_at"])
        os.environ["FAKE_VERSION"], os.environ["FAKE_FAIL"] = "3.0", "1"
        result = self.client.post("/update", json={"tools": ["kafkacat"]}).json()
        self.assertIn("kafkacat", result["failed"])
        self.assertIn("kafkacat-2.0", (self.root / "envs" / "kafkacat" / "bin" / "kcat").read_text())

    def test_restore_rebuilds_from_the_exact_lock(self):
        self._install({"name": "kafkacat", "packages": ["kafkacat"], "binaries": ["kcat"]})
        lock = self.client.get("/lock").json()
        import shutil as _shutil

        _shutil.rmtree(self.root / "envs")
        (self.root / "installed.json").unlink()
        result = self.client.post("/restore", json={"lock": lock}).json()
        self.assertEqual(result["restored"], ["kafkacat"])
        self.assertIn("--file", self.log.read_text().splitlines()[-3])  # created from the explicit spec

    def test_pip_clis_and_invalid_specs(self):
        body = self._install({"name": "azure-cli", "packages": ["python=3.12", "pip"], "pip": ["azure-cli"],
                              "binaries": ["python"]}).json()
        self.assertEqual(body["versions"]["azure-cli"], {"python": "1.0", "pip": "1.0", "azure-cli": "1.0"})
        for bad in ({"name": "x", "packages": ["https://evil/x.tar"]}, {"name": "x", "pip": ["a;b"], "packages": ["p"]},
                    {"name": "x", "download": {"linux-64": {"url": "http://plain", "sha256": "0" * 64}}},
                    {"name": "x", "download": {"linux-64": {"url": "https://ok", "sha256": "short"}}}):
            self.assertEqual(self._install(bad).status_code, 400, bad)

    def test_a_verified_vendor_archive(self):
        import io
        import tarfile as _tarfile

        payload = io.BytesIO()
        with _tarfile.open(fileobj=payload, mode="w:gz") as tar:
            data = b"#!/bin/sh\necho vendor-ok\n"
            info = _tarfile.TarInfo("vendor-1.0/bin/vtool")
            info.size, info.mode = len(data), 0o755
            tar.addfile(info, io.BytesIO(data))
        archive = payload.getvalue()
        import hashlib as _hashlib

        digest = _hashlib.sha256(archive).hexdigest()

        def fake_fetch(url, sha256, dest):
            if sha256 != digest:
                raise self.app.HTTPException(status_code=422, detail="sha256 mismatch")
            dest.write_bytes(archive)

        plat = self.app._platform()
        with patch.object(self.app, "_fetch", side_effect=fake_fetch):
            ok = self._install({"name": "vtool", "binaries": ["vtool"],
                                "download": {plat: {"url": "https://vendor.example/v.tgz", "sha256": digest, "version": "1.0"}}})
            self.assertEqual(ok.json()["binaries"], ["vtool"], ok.text)
            bad = self._install({"name": "vtool2", "binaries": ["vtool"],
                                 "download": {plat: {"url": "https://vendor.example/v.tgz", "sha256": "f" * 64}}})
            self.assertEqual(bad.status_code, 422)
        self.assertEqual(self.client.get("/installed").json()["tools"]["vtool"]["versions"], {"vtool": "1.0"})


class ReportToolsTests(unittest.TestCase):
    def test_the_report_records_the_installed_tool_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = root / "tools"
            (tools / "bin").mkdir(parents=True)
            (tools / "installed.json").write_text(json.dumps({"tools": {"kafkacat": {"versions": {"kafkacat": "1.7.1"}}}}))
            kit = root / "runs" / "kit" / "REQ-001"
            (kit / "ci").mkdir(parents=True)
            ltc = {"req_id": "REQ-001", "checks": [{"id": "ok", "command": "true"}]}
            (kit / "ci" / "LTC.json").write_text(json.dumps(ltc))
            with patch.dict(os.environ, {"CLIKE_EVAL_TOOLS_BIN": str(tools / "bin")}):
                report = EvalRunner(root).run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-001")
            self.assertEqual(report.tools, {"kafkacat": {"kafkacat": "1.7.1"}})


class LockRoutesTests(_RegressionProject):
    def test_update_and_restore_keep_the_lock_outside_the_volume(self):
        import routes.routes_eval as routes

        calls = []

        async def fake(method, path, body=None, timeout=0):
            calls.append((method, path))
            return {"/lock": {"kafkacat": {"spec": {}, "lock": {}}}, "/update": {"updated": ["kafkacat"], "changes": {}},
                    "/restore": {"restored": ["kafkacat"], "failed": {}}}.get(path, {})

        with patch.dict(os.environ, {"CLIKE_EVAL_TOOLS_URL": "http://tools"}), patch.object(routes, "_tools_call", side_effect=fake):
            self.assertEqual(self.client.post("/v1/eval/tools/restore", headers=AUTH).json()["lock"], False)
            self.client.post("/v1/eval/tools/update", json={"tools": []}, headers=AUTH)
            self.assertTrue(routes._tools_lock_path().is_file())
            restored = self.client.post("/v1/eval/tools/restore", headers=AUTH).json()
        self.assertEqual((restored["restored"], restored["lock"]), (["kafkacat"], True))
        self.assertIn(("POST", "/restore"), calls)


class CliTests(unittest.TestCase):
    def test_status_restore_and_update_print_what_matters(self):
        import contextlib
        import io

        import eval_tools_cli

        answers = {
            ("GET", "/v1/eval/tools"): {"installed": {"jq": {"versions": {"jq": "1.8.2"}}}, "updated_days_ago": 40, "update_due": True},
            ("POST", "/v1/eval/tools/restore"): {"restored": ["jq"], "failed": {}, "lock": True},
            ("POST", "/v1/eval/tools/update"): {"updated": ["jq"], "changes": {"jq": {"jq": ["1.8.2", "1.9.0"]}}, "failed": {}},
        }
        out = io.StringIO()
        with patch.object(eval_tools_cli, "_call", side_effect=lambda m, p, b=None, timeout=0: answers[(m, p)]), \
                contextlib.redirect_stdout(out):
            codes = [eval_tools_cli.main(["x", c]) for c in ("status", "restore", "update")]
        self.assertEqual(codes, [0, 0, 0])
        text = out.getvalue()
        self.assertIn("jq: jq 1.8.2", text)
        self.assertIn("40 days ago", text)
        self.assertIn("restored from the lock: jq", text)
        self.assertIn("jq 1.8.2 -> 1.9.0", text)

if __name__ == "__main__":
    unittest.main()


def test_a_check_that_says_a_catalog_program_is_missing_is_a_missing_tool(monkeypatch):
    # B2B REQ-033: ci/check.py printed "shellcheck missing; provision LTC native tool" and exited;
    # the eval called it a code failure and the repair loop ran three cycles on correct code
    import eval_tools

    catalog = {"shellcheck": {"binaries": ["shellcheck"]}, "awscli": {"binaries": ["aws"]}, "jq": {"binaries": ["jq"]}}
    monkeypatch.setattr(eval_tools, "available", lambda b: b == "jq")
    said = {
        "shellcheck missing; provision LTC native tool; remains blocking": ["shellcheck"],
        "aws is not installed": ["aws"],
        "this check requires aws": ["aws"],
        "bash: shellcheck: command not found": ["shellcheck"],
        # a program that is there, and prose that names no absent program, are not missing tools
        "jq missing": [],
        "the configuration file is missing": [],
        "value missing in the shellcheckrc": [],
    }
    for text, expected in said.items():
        assert eval_tools.missing_from_failure(text, catalog) == expected, text
