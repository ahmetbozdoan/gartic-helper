from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from gartic_helper.dependencies import get_guide_service
from gartic_helper.models.schemas import GuideRequest, GuideResponse
from gartic_helper.services.guide_service import GuideNotFoundError, GuideService
from gartic_helper.services.web_icon_search import WebIconSearchError

router = APIRouter(tags=["guide"])


@router.post("/guide", response_model=GuideResponse)
def create_drawing_guide(
    request: GuideRequest,
    guide_service: Annotated[GuideService, Depends(get_guide_service)],
) -> GuideResponse:
    try:
        return guide_service.get_guide(request.word)
    except GuideNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except WebIconSearchError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
