from typing import Annotated

from fastapi import APIRouter, Depends

from gartic_helper.dependencies import get_word_learning_service
from gartic_helper.models.schemas import LearnWordRequest, LearnWordResponse
from gartic_helper.services.word_learning_service import WordLearningService

router = APIRouter(tags=["words"])


@router.post("/words/learn", response_model=LearnWordResponse)
def learn_word(
    request: LearnWordRequest,
    word_learning_service: Annotated[WordLearningService, Depends(get_word_learning_service)],
) -> LearnWordResponse:
    return word_learning_service.learn(request.word)
