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
    attachments: Optional[list[AttachmentIn]] = None


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


class TitleRequestBody(BaseModel):
    chatId: str
    message: str


class TitleResponseBody(BaseModel):
    title: str
