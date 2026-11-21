from typing import Annotated

from fastapi import APIRouter, Depends

from gartic_helper.dependencies import get_guess_service
from gartic_helper.models.schemas import GuessRequest, GuessResponse
from gartic_helper.services.guess_service import GuessService

router = APIRouter(tags=["guess"])


@router.post("/guess", response_model=GuessResponse)
def guess_drawing(
    request: GuessRequest,
    guess_service: Annotated[GuessService, Depends(get_guess_service)],
) -> GuessResponse:
    return guess_service.guess(request)
