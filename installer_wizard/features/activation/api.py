from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from config import STATE_DIR
from features.activation.application.advance_journey import AdvanceJourneyUseCase
from features.activation.application.configure_step import ConfigureStepHandler
from features.activation.application.initialize_journey import InitializeJourneyUseCase
from features.activation.application.reset_journey import ResetJourneyUseCase
from features.activation.application.submit_choice import SubmitChoiceUseCase
from features.activation.domain.errors import JourneyError
from features.activation.infrastructure.hardware_probe import HardwareProbe
from features.activation.infrastructure.journey_store import JourneyStore
from features.activation.infrastructure.sequence_catalog import SequenceCatalog
from features.activation.infrastructure.step_runner import StepRunner
from steps import run_step_action

public_routes = APIRouter(prefix="/api/activation", tags=["Activation"])

_store = JourneyStore(STATE_DIR / "activation.json")
_catalog = SequenceCatalog(STATE_DIR.parent.parent / "features" / "activation" / "sequences")
_probe = HardwareProbe()


async def _execute_step_adapter(step_id: str, action: str, stream_cb) -> tuple[int, str]:
    from steps import STEP_BY_ID
    step = STEP_BY_ID.get(step_id)
    if step is None:
        return 1, f"Unknown step {step_id}"
    return await run_step_action(step, action, stream=True)


_step_runner = StepRunner(_execute_step_adapter)


class ChoicePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice: str


@public_routes.get("/state")
async def get_state():
    journey = _store.load()
    if journey is None:
        use_case = InitializeJourneyUseCase(_store, _catalog, _probe)
        try:
            journey = use_case.execute()
        except JourneyError as exc:
            raise HTTPException(400, exc.code)
    return JSONResponse(journey.to_dict())


@public_routes.post("/configure/{sequence_id}")
async def submit_configuration(sequence_id: str, payload: dict):
    journey = _store.load()
    if journey is None:
        raise HTTPException(400, "journey.not_found")
    try:
        res = ConfigureStepHandler.handle_step(sequence_id, payload)
        import time
        journey.submit(sequence_id, time.time())
        _store.save(journey)
        return JSONResponse({"result": res, "journey": journey.to_dict()})
    except JourneyError as exc:
        raise HTTPException(400, exc.code)


@public_routes.post("/defer/{sequence_id}")
async def defer_configuration(sequence_id: str):
    journey = _store.load()
    if journey is None:
        raise HTTPException(400, "journey.not_found")
    seq = _catalog.get(sequence_id)
    if seq is None:
        raise HTTPException(404, "sequence.not_found")
    try:
        import time
        journey.defer(sequence_id, seq.skippable, time.time())
        _store.save(journey)
        return JSONResponse(journey.to_dict())
    except JourneyError as exc:
        raise HTTPException(400, exc.code)


@public_routes.post("/choice/{sequence_id}")
async def submit_choice(sequence_id: str, payload: ChoicePayload):
    use_case = SubmitChoiceUseCase(_store, _catalog)
    try:
        journey = use_case.execute(sequence_id, payload.choice)
        return JSONResponse(journey.to_dict())
    except JourneyError as exc:
        raise HTTPException(400, exc.code)


@public_routes.post("/advance")
async def advance_journey():
    def write_env(d: dict[str, str]) -> None:
        from config import write_env as persist_env
        persist_env(d)

    use_case = AdvanceJourneyUseCase(_store, _catalog, _step_runner, write_env)
    try:
        journey = await use_case.execute()
        return JSONResponse(journey.to_dict())
    except JourneyError as exc:
        raise HTTPException(400, exc.code)


@public_routes.post("/reset")
async def reset_journey():
    use_case = ResetJourneyUseCase(_store)
    try:
        journey = use_case.execute()
        return JSONResponse(journey.to_dict())
    except JourneyError as exc:
        raise HTTPException(400, exc.code)
