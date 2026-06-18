from services.local_agent_package import _materialize_attachments


def test_inline_attachments_materialized_under_runs_phase_attachments():
    payload = {
        "attachments": [
            {
                "name": "screen.png",
                "path": ".clike/uploads/screen.png",
                "mime": "image/png",
                "bytes_b64": "aGVsbG8=",
                "size": 5,
            },
            {
                "name": "notes.md",
                "path": ".clike/uploads/notes.md",
                "mime": "text/plain",
                "content": "# Notes",
                "size": 7,
            },
        ],
    }

    manifest, package_files = _materialize_attachments(payload, "idea")

    assert manifest["present"] is True
    assert manifest["count"] == 2

    by_name = {i.get("name"): i for i in manifest["items"]}
    assert by_name["screen.png"]["materialized"] is True
    assert by_name["screen.png"]["workspace_path"] == "runs/idea/attachments/screen.png"
    assert by_name["notes.md"]["materialized"] is True
    assert by_name["notes.md"]["workspace_path"] == "runs/idea/attachments/notes.md"

    by_path = {f["path"]: f for f in package_files}
    assert by_path["runs/idea/attachments/screen.png"]["content_base64"] == "aGVsbG8="
    assert by_path["runs/idea/attachments/screen.png"]["encoding"] == "base64"
    assert by_path["runs/idea/attachments/notes.md"]["content"] == "# Notes"


def test_path_only_attachment_is_not_materialized():
    payload = {
        "attachments": [
            {"name": "huge.bin", "path": ".clike/uploads/huge.bin", "mime": "application/octet-stream"},
        ],
    }
    manifest, package_files = _materialize_attachments(payload, "idea")
    assert manifest["count"] == 1
    assert manifest["items"][0]["materialized"] is False
    assert not any(f["path"].startswith("runs/idea/attachments/") for f in package_files)


def test_attachments_are_phase_scoped():
    payload = {"attachments": [{"name": "a.png", "bytes_b64": "AAAA", "mime": "image/png"}]}
    _, package_files = _materialize_attachments(payload, "spec")
    assert package_files[0]["path"] == "runs/spec/attachments/a.png"
