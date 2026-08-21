from typing import Any, Literal

from pydantic import BaseModel, Field

from app.labeling.options import DEFAULT_LABEL_OPTIONS

UrlType = Literal["pdf", "html", "text"]


class LabelTask(BaseModel):
    id: str
    name: str
    desc: str = ""
    created_at: str
    count: int
    progress: int = 0
    url_type: UrlType
    label_options: list[str] = Field(default_factory=lambda: list(DEFAULT_LABEL_OPTIONS))


class LabelItem(BaseModel):
    index: int
    url: str = ""
    type: UrlType = "pdf"
    text: str = ""
    otext: str = ""
    detailId: str = ""
    info: Any = ""
    status: str = ""
    notes: str = ""
    taskId: str = ""
    total: int | None = None
    pdf_filename: str = ""
    download_msg: str = ""
    label_options: list[str] = Field(default_factory=lambda: list(DEFAULT_LABEL_OPTIONS))


class LabelItemList(BaseModel):
    task: LabelTask
    items: list[LabelItem]


class SaveLabelRequest(BaseModel):
    id: str = ""
    text: str = ""
    otext: str = ""
    url: str = ""
    type: str = ""
    info: Any = ""
    status: str = Field(default="")
    notes: str = ""


class SaveLabelResponse(BaseModel):
    ok: bool = True
    saved: dict[str, Any]
    progress: int
