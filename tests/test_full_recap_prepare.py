import ast
from pathlib import Path


def _load_prepare_method():
    source = Path("pipeline/orchestrator.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    owner = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            isinstance(member, ast.FunctionDef)
            and member.name == "step_full_recap_prepare"
            for member in node.body
        )
    )
    method = next(
        member for member in owner.body
        if isinstance(member, ast.FunctionDef)
        and member.name == "step_full_recap_prepare"
    )
    isolated = ast.Module(body=[method], type_ignores=[])
    namespace = {}
    exec(compile(isolated, "pipeline/orchestrator.py", "exec"), namespace)
    return namespace["step_full_recap_prepare"]


class FakeState:
    def __init__(self, is_batch=False):
        self.error = None
        self.is_batch = is_batch
        self.chapter_list = [1]
        self.full_recap_status = "not_started"
        self.saved = 0

    def save(self):
        self.saved += 1


class FakeOrchestrator:
    def __init__(self):
        self._should_cancel = False
        self.progress = []
        self.calls = []
        self._emit_progress = lambda *args: self.progress.append(args)

        for name in (
            "step_stitch",
            "step_detect_bubble_text",
            "step_crop_bubble_text_panels",
            "step_stitch_bubble_panels",
            "step_detect_art_panels",
            "step_crop_art_panels",
            "step_extract_dialogue_text",
        ):
            setattr(self, name, self._step(name))

    def _step(self, name):
        def invoke(state):
            self.calls.append(name)
            return state
        return invoke

    def _reset_viewing_to_first_chapter(self, state):
        self.reset_called = True


def test_full_recap_prepare_runs_native_steps_in_order_once():
    prepare = _load_prepare_method()
    orchestrator = FakeOrchestrator()
    state = FakeState()

    result = prepare(orchestrator, state)

    assert result is state
    assert orchestrator.calls == [
        "step_stitch",
        "step_detect_bubble_text",
        "step_crop_bubble_text_panels",
        "step_stitch_bubble_panels",
        "step_detect_art_panels",
        "step_crop_art_panels",
        "step_extract_dialogue_text",
    ]
    assert result.full_recap_status == "panels_ready"
    assert result.error is None
    assert result.saved >= 2


def test_full_recap_prepare_stops_on_first_failed_native_step():
    prepare = _load_prepare_method()
    orchestrator = FakeOrchestrator()
    state = FakeState()

    def fail(state):
        orchestrator.calls.append("step_crop_art_panels")
        state.error = "Crop 2 failed"
        return state

    orchestrator.step_crop_art_panels = fail
    result = prepare(orchestrator, state)

    assert result is state
    assert orchestrator.calls == [
        "step_stitch",
        "step_detect_bubble_text",
        "step_crop_bubble_text_panels",
        "step_stitch_bubble_panels",
        "step_detect_art_panels",
        "step_crop_art_panels",
    ]
    assert result.full_recap_status == "prepare_failed"
    assert "Crop 2 failed" in result.error


def test_full_recap_prepare_stops_when_cancelled_before_next_step():
    prepare = _load_prepare_method()
    orchestrator = FakeOrchestrator()
    orchestrator._should_cancel = True
    state = FakeState()

    result = prepare(orchestrator, state)

    assert result is state
    assert orchestrator.calls == []
    assert result.full_recap_status == "prepare_cancelled"
