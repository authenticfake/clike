from routes.harper import HarperKitOptions


def test_kit_repair_accepts_bmad_flag_and_auto_eval_request():
    assert HarperKitOptions().repair is None
    assert HarperKitOptions(repair=True).repair is True
    request = {"cycle": 1, "max_cycles": 2, "failures": [], "files": []}
    assert HarperKitOptions(repair=request).repair == request


def test_kit_keeps_the_eval_check_request_of_a_local_agent():
    # an unknown field is dropped by the schema: the KIT never got its eval-sandbox verification
    kit = HarperKitOptions(targets=["REQ-002"], eval_check=True, eval_check_max_runs=4)
    assert kit.model_dump(exclude_none=True)["eval_check"] is True
    assert kit.model_dump(exclude_none=True)["eval_check_max_runs"] == 4
