from typing import Literal

from pydantic import BaseModel, Field


EntityType = Literal["Project", "Method", "Dataset", "Organization"]
RelationType = Literal["USES_METHOD", "EVALUATED_ON", "CREATED_BY"]


class EntityInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: EntityType
    id: str | None = None


class FactInput(BaseModel):
    subject: EntityInput
    relation: RelationType
    object: EntityInput
    evidence_chunk_id: str
    evidence_quote: str = Field(min_length=5, max_length=500)
    polarity: Literal["supports", "denies"] = "supports"


class SearchInput(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=30)


class AskInput(BaseModel):
    question: str = Field(min_length=1)


class TranslateTextInput(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class TopicInput(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    document_ids: list[str]
    status: Literal["suggested", "approved"] = "approved"


class TopicMergeInput(BaseModel):
    secondary_id: str


class TopicSplitInput(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    document_ids: list[str] = Field(min_length=1)

