from routes.harper import HarperKitOptions


def test_kit_repair_accepts_bmad_flag_and_auto_eval_request():
    assert HarperKitOptions().repair is None
    assert HarperKitOptions(repair=True).repair is True
    request = {"cycle": 1, "max_cycles": 2, "failures": [], "files": []}
    assert HarperKitOptions(repair=request).repair == request
