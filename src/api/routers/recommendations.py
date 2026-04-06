from fastapi import APIRouter, HTTPException

from ..schemas.recommendation_schemas import (
    CreateContextRequest, UpdateLocationRequest, AddDoneRequest,
    UpdateQueuesRequest, ContextResponse, RecommendRequest, RecommendationResponse,
    AttractionScoreResponse, ScoreBreakdownResponse,
)
from ...domain.exceptions.domain_exceptions import (
    GroupNotFound, NoContextActive, NoEligibleAttractions, GroupSetupIncomplete,
)
from ...services.group_service import GroupService
from ...services.context_service import ContextService
from ...services.recommendation_service import RecommendationService

context_router = APIRouter(prefix="/groups/{group_id}/context", tags=["context"])
rec_router = APIRouter(prefix="/groups/{group_id}", tags=["recommendations"])


@context_router.post("", response_model=ContextResponse, status_code=201)
def create_context(group_id: str, body: CreateContextRequest):
    try:
        GroupService().get_by_id(group_id)
    except GroupNotFound:
        raise HTTPException(404, f"Group not found: {group_id}")

    ctx = ContextService().create_context(
        group_id=group_id,
        park_id="magic_kingdom",
        location_area=body.current_location_area,
        queue_snapshot=body.queue_snapshot,
        done_attractions=body.done_attractions,
        closed_attractions=body.closed_attractions,
        weather=body.weather,
        group_states=body.group_states,
        filter_override=body.filter_override,
    )
    return ContextResponse(
        context_id=ctx.context_id,
        group_id=group_id,
        time_of_day=_time_label(ctx.current_datetime.hour),
        ready_to_recommend=True,
    )


@context_router.patch("/location")
def update_location(group_id: str, body: UpdateLocationRequest):
    try:
        ContextService().update_location(group_id, body.location_area)
    except NoContextActive:
        raise HTTPException(404, "No active context. Create one first.")
    return {"updated": True, "location_area": body.location_area}


@context_router.patch("/done")
def mark_done(group_id: str, body: AddDoneRequest):
    try:
        ContextService().mark_attraction_done(group_id, body.attraction_id)
    except NoContextActive:
        raise HTTPException(404, "No active context.")
    return {"updated": True, "attraction_id": body.attraction_id}


@context_router.put("/queues")
def update_queues(group_id: str, body: UpdateQueuesRequest):
    try:
        ContextService().update_queues(group_id, body.queue_snapshot)
    except NoContextActive:
        raise HTTPException(404, "No active context.")
    return {"updated": True, "attractions_updated": len(body.queue_snapshot)}


@rec_router.post("/recommend", response_model=RecommendationResponse)
def recommend(group_id: str, body: RecommendRequest):
    gs = GroupService()
    cs = ContextService()
    rs = RecommendationService()

    try:
        group = gs.get_by_id(group_id)
        gs.assert_setup_complete(group)
        prefs = gs.get_preferences(group_id)
        if not prefs:
            raise HTTPException(422, "Preferences not set. Call PUT /preferences first.")
        context = cs.get_active_context(group_id)
    except GroupNotFound:
        raise HTTPException(404, f"Group not found: {group_id}")
    except GroupSetupIncomplete as e:
        raise HTTPException(422, str(e))
    except NoContextActive:
        raise HTTPException(404, "No active context. Call POST /context first.")

    try:
        rec = rs.recommend(
            group=group,
            preferences=prefs,
            context=context,
            filter_override=body.filter_override.model_dump() if body.filter_override else None,
            generate_text=body.generate_text,
        )
    except NoEligibleAttractions as e:
        raise HTTPException(422, str(e))

    return _serialize_recommendation(rec)


def _serialize_recommendation(rec) -> RecommendationResponse:
    def _score(s) -> AttractionScoreResponse:
        bd = None
        if s.score_breakdown:
            b = s.score_breakdown
            bd = ScoreBreakdownResponse(
                d1_queue=b.d1_queue, d2_proximity=b.d2_proximity,
                d3_profile=b.d3_profile, d4_time=b.d4_time,
                d5_strategy=b.d5_strategy, bonuses=b.bonuses,
                penalties=b.penalties, total=b.total,
            )
        return AttractionScoreResponse(
            attraction_id=s.attraction_id, name=s.name, score=s.score,
            current_wait=s.current_wait, walk_minutes=s.walk_minutes,
            primary_reason=s.primary_reason, supporting_reasons=s.supporting_reasons,
            context_note=s.context_note, score_breakdown=bd,
        )

    return RecommendationResponse(
        recommendation_id=rec.recommendation_id,
        primary=_score(rec.primary),
        secondary=_score(rec.secondary) if rec.secondary else None,
        filters_applied=rec.filters_applied,
        candidates_evaluated=rec.candidates_evaluated,
        whatsapp_message=rec.whatsapp_message,
    )


def _time_label(hour: int) -> str:
    if hour < 10: return "rope_drop"
    if hour < 12: return "morning"
    if hour < 14: return "midday"
    if hour < 17: return "afternoon"
    if hour < 20: return "evening"
    return "night"
