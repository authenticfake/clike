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
        r = eval_tools.resolve(["kcat", "jdk@17", "maven"], catalog)
        self.assertEqual(r["packages"], ["kafkacat", "openjdk=17.*", "maven", "openjdk"])
        self.assertIn("mvn", r["binaries"])
        self.assertEqual(eval_tools.resolve(["nope", "a;rm -rf /"], catalog)["unknown"], ["nope", "a;rm -rf /"])

    def test_project_entries_and_approvals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".clike").mkdir()
            (root / ".clike" / "eval-tools.yaml").write_text(
                "tools: [kafkacat, jdk@17]\ncustom:\n  sqlcl: {packages: [sqlcl], binaries: [sql], about: Oracle SQLcl}\n"
            )
            self.assertEqual(eval_tools.approved_tools(root), ["kafkacat", "jdk@17"])
            self.assertEqual(eval_tools.resolve(["sqlcl"], eval_tools.load_catalog(root))["packages"], ["sqlcl"])

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
            self.assertEqual(eval_tools.used([src], catalog), ["aws", "kcat", "mysqldump", "pg_dump", "terraform"])

    def test_missing_programs_in_failures(self):
        catalog = eval_tools.load_catalog()
        for text, expected in (
            ("sh: 1: kcat: command not found", ["kcat"]),
            ("Error: spawn mysqldump ENOENT", ["mysqldump"]),
            ("FileNotFoundError: [Errno 2] No such file or directory: 'pg_dump'", ["pg_dump"]),
            ('java.io.IOException: Cannot run program "mvn": error=2', ["mvn"]),
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


if __name__ == "__main__":
    unittest.main()


class ToolsServiceTests(unittest.TestCase):
    def test_install_exposes_only_the_requested_programs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tools"
            fakebin = Path(tmp) / "fakebin"
            fakebin.mkdir()
            # a fake micromamba: "create -p ENV …" makes ENV/bin/{kcat,python}; "list" prints versions
            (fakebin / "micromamba").write_text(
                "#!/bin/sh\n"
                'if [ "$1" = list ]; then echo \'{"log_history": [], "packages": [{"name": "kafkacat", "version": "1.7.1"}]}\'; exit 0; fi\n'
                'env="$4"; mkdir -p "$env/bin" "$env/conda-meta"\n'
                'printf "#!/bin/sh\\necho kcat-ok\\n" > "$env/bin/kcat"; chmod +x "$env/bin/kcat"\n'
                'printf "#!/bin/sh\\n" > "$env/bin/python"; chmod +x "$env/bin/python"\n'
            )
            (fakebin / "micromamba").chmod(0o755)
            from eval_runner import _SECRET_ENV_NAME_RE

            env = {k: v for k, v in os.environ.items() if not _SECRET_ENV_NAME_RE.search(k)}
            env.update({"CLIKE_EVAL_TOOLS_ROOT": str(root), "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}"})
            with patch.dict(os.environ, env, clear=True):
                sys.modules.pop("eval_tools_app", None)
                import eval_tools_app
                from starlette.testclient import TestClient

                client = TestClient(eval_tools_app.app)
                body = client.post("/install", json={"packages": ["kafkacat"], "binaries": ["kcat", "kafkacat"], "tools": ["kafkacat"]}).json()
                self.assertEqual(body["binaries"], ["kcat"])
                self.assertEqual(body["missing_binaries"], ["kafkacat"])
                self.assertEqual(body["versions"], {"kafkacat": "1.7.1"})
                self.assertTrue((root / "bin" / "kcat").is_file())
                self.assertFalse((root / "bin" / "python").exists())  # never shadows the image's python
                self.assertIn("kafkacat", client.get("/health").json()["installed"])
                self.assertEqual(client.post("/install", json={"packages": ["https://evil/x.tar"], "binaries": []}).status_code, 400)
            sys.modules.pop("eval_tools_app", None)
