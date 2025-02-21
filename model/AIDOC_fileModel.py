from typing import Optional, List

from sqlalchemy import Column, JSON
from sqlmodel import SQLModel, Field


class File(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=False)
    folder_id: Optional[int] = Field(default=None, foreign_key="folder.id")
    #uploader_id: Optional[int] = Field(default=None, foreign_key="user.id")
    size: Optional[int] = Field(default=0)
    tag: Optional[List[str]] = Field(default_factory=list, sa_column=Column(JSON))
    accuracy: Optional[str] = Field(default=0)
