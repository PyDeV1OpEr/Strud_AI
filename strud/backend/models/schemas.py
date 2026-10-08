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
    message: str = ""
    attachments: Optional[list[AttachmentIn]] = None


class SourceOut(BaseModel):
    label: str
    pages: list[int]


class ChatResponseBody(BaseModel):
    messageId: str
    content: str
    sources: Optional[list[SourceOut]] = None


class TitleRequestBody(BaseModel):
    chatId: str
    message: str


class TitleResponseBody(BaseModel):
    title: str
