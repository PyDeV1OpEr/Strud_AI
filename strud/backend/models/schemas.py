# ------------------------------------------------------------
# Strud AI — API schemas (mirrors frontend/types)
# ------------------------------------------------------------

from typing import Optional

from pydantic import BaseModel, Field


class AttachmentIn(BaseModel):
    name: str
    mimeType: str = Field(alias="mimeType")
    data: str  # base64

    model_config = {"populate_by_name": True}


class ChatRequestBody(BaseModel):
    chatId: str
    # A stable, browser-generated id scopes durable histories and memories.
    # Authentication can replace this with the authenticated subject later.
    userId: str = Field(alias="userId", min_length=1, max_length=200)
    message: str = ""
    title: str = ""
    # Project association is applied only when the chat metadata row is
    # first created; later messages never reassign the chat.
    projectId: Optional[str] = Field(alias="projectId", default=None, max_length=100)
    attachments: Optional[list[AttachmentIn]] = None

    model_config = {"populate_by_name": True}


class SourceOut(BaseModel):
    label: str
    pages: list[int]


class ChatResponseBody(BaseModel):
    messageId: str
    content: str
    sources: Optional[list[SourceOut]] = None


class ChatTitleUpdateBody(BaseModel):
    userId: str = Field(alias="userId", min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=80)

    model_config = {"populate_by_name": True}


# ---- Projects ------------------------------------------------------------

class ProjectCreateBody(BaseModel):
    userId: str = Field(alias="userId", min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)

    model_config = {"populate_by_name": True}


class ProjectUpdateBody(BaseModel):
    userId: str = Field(alias="userId", min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)

    model_config = {"populate_by_name": True}


class ChatProjectUpdateBody(BaseModel):
    userId: str = Field(alias="userId", min_length=1, max_length=200)
    # Omit/null projectId clears the association (back to an ordinary chat).
    projectId: Optional[str] = Field(alias="projectId", default=None, max_length=100)

    model_config = {"populate_by_name": True}


# ---- Profile --------------------------------------------------------------

class ProfileRequestBody(BaseModel):
    userId: str = Field(alias="userId", min_length=1, max_length=200)
    displayName: str = Field(alias="displayName", min_length=1, max_length=60)

    model_config = {"populate_by_name": True}


class TitleRequestBody(BaseModel):
    chatId: str
    message: str


class TitleResponseBody(BaseModel):
    title: str


# ---- AI Control Center Schemas --------------------------------------------

class ProfileFullRequestBody(BaseModel):
    userId: str = Field(alias="userId", min_length=1, max_length=200)
    displayName: str = Field(alias="displayName", min_length=1, max_length=60)
    avatar: Optional[str] = Field(default="emerald", max_length=40)
    responseStyle: Optional[str] = Field(alias="responseStyle", default="balanced", max_length=40)
    explanationDetail: Optional[str] = Field(alias="explanationDetail", default="standard", max_length=40)
    studyFocus: Optional[str] = Field(alias="studyFocus", default="exam", max_length=40)
    memoryEnabled: Optional[bool] = Field(alias="memoryEnabled", default=True)
    customInstructions: Optional[str] = Field(alias="customInstructions", default="", max_length=1000)

    model_config = {"populate_by_name": True}


class ModelActiveUpdateBody(BaseModel):
    modelId: Optional[str] = Field(alias="modelId", default=None)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    maxTokens: Optional[int] = Field(alias="maxTokens", default=None, ge=1, le=8192)
    baseUrl: Optional[str] = Field(alias="baseUrl", default=None)

    model_config = {"populate_by_name": True}


class ModelTestBody(BaseModel):
    modelId: Optional[str] = Field(alias="modelId", default=None)
    baseUrl: Optional[str] = Field(alias="baseUrl", default=None)

    model_config = {"populate_by_name": True}


class RagQueryTestBody(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class MemoryCreateBody(BaseModel):
    userId: str = Field(alias="userId", min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=500)
    source: Optional[str] = Field(default="explicit", max_length=40)

    model_config = {"populate_by_name": True}


class MemorySettingsBody(BaseModel):
    userId: str = Field(alias="userId", min_length=1, max_length=200)
    memoryEnabled: bool = Field(alias="memoryEnabled")

    model_config = {"populate_by_name": True}


class ClearHistoryBody(BaseModel):
    userId: str = Field(alias="userId", min_length=1, max_length=200)
    permanent: Optional[bool] = Field(default=False)

    model_config = {"populate_by_name": True}

