from fastapi import APIRouter, HTTPException
from datetime import date

from ..schemas.group_schemas import (
    CreateGroupRequest, UpdateMembersRequest, UpdatePreferencesRequest,
    GroupResponse, PreferencesResponse,
)
from ...domain.models import Member, GroupPreferences
from ...domain.exceptions.domain_exceptions import GroupNotFound
from ...services.group_service import GroupService

router = APIRouter(prefix="/groups", tags=["groups"])


def _get_service() -> GroupService:
    return GroupService()


@router.post("", response_model=GroupResponse, status_code=201)
def create_or_get_group(body: CreateGroupRequest):
    service = _get_service()
    group, created = service.get_or_create(
        whatsapp_number=body.whatsapp_number,
        park_id=body.park_id,
        visit_date=body.visit_date or date.today(),
    )
    next_step = None if group.setup_complete else (
        "add_members" if not group.members else "add_preferences"
    )
    return GroupResponse(
        group_id=group.group_id,
        created=created,
        profile_id=group.profile_id.value if group.profile_id else None,
        setup_complete=group.setup_complete,
        next_step=next_step,
        members_count=len(group.members),
    )


@router.get("/{group_id}", response_model=GroupResponse)
def get_group(group_id: str):
    service = _get_service()
    try:
        group = service.get_by_id(group_id)
    except GroupNotFound:
        raise HTTPException(status_code=404, detail=f"Group not found: {group_id}")

    next_step = None if group.setup_complete else (
        "add_members" if not group.members else "add_preferences"
    )
    return GroupResponse(
        group_id=group.group_id,
        created=False,
        profile_id=group.profile_id.value if group.profile_id else None,
        setup_complete=group.setup_complete,
        next_step=next_step,
        members_count=len(group.members),
    )


@router.patch("/{group_id}/members", response_model=GroupResponse)
def update_members(group_id: str, body: UpdateMembersRequest):
    service = _get_service()
    try:
        members = [
            Member(
                role=m.role, age=m.age, height_cm=m.height_cm, name=m.name,
                fear_of_dark=m.fear_of_dark, fear_of_heights=m.fear_of_heights,
                motion_sickness=m.motion_sickness, mobility_restricted=m.mobility_restricted,
            )
            for m in body.members
        ]
        group = service.update_members(group_id, members)
    except GroupNotFound:
        raise HTTPException(status_code=404, detail=f"Group not found: {group_id}")

    return GroupResponse(
        group_id=group.group_id,
        created=False,
        profile_id=group.profile_id.value if group.profile_id else None,
        setup_complete=group.setup_complete,
        next_step=None if group.setup_complete else "add_preferences",
        members_count=len(group.members),
    )


@router.put("/{group_id}/preferences", response_model=PreferencesResponse)
def update_preferences(group_id: str, body: UpdatePreferencesRequest):
    import uuid
    service = _get_service()
    try:
        prefs = GroupPreferences(
            pref_id=f"pref_{uuid.uuid4().hex[:10]}",
            group_id=group_id,
            intensity_preference=body.intensity_preference,
            priority_order=body.priority_order,
            avoid_types=body.avoid_types,
            max_queue_minutes=body.max_queue_minutes,
            must_do_attractions=body.must_do_attractions,
            skip_attractions=body.skip_attractions,
            show_interest=body.show_interest,
            meal_break_times=body.meal_break_times,
            allow_group_split=body.allow_group_split,
        )
        group = service.save_preferences(group_id, prefs)
    except GroupNotFound:
        raise HTTPException(status_code=404, detail=f"Group not found: {group_id}")

    return PreferencesResponse(
        group_id=group_id,
        preferences_saved=True,
        profile_id=group.profile_id.value if group.profile_id else None,
        setup_complete=group.setup_complete,
        next_step=None if group.setup_complete else "add_members",
    )
