from typing import Optional, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship

class Folder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    #owner_id: Optional[int] = Field(default=None, foreign_key="user.id")
    #owner: Optional["User"] = Relationship(back_populates="folders")
    total_accuracy: float = Field(default=0.0)

