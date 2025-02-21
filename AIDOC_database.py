import logging
import os
from typing import Annotated

from fastapi import Depends
from sqlmodel import create_engine, Session, SQLModel, select
from typing_extensions import Generator

from model.AIDOC_fileModel import File
from model.AIDOC_folderModel import Folder

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session_internal() -> Session:
    return Session(bind=engine)

def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


sessionDep = Annotated[Session, Depends(get_session)]


def create_folder(folder_name: str, session: Session):
    os.makedirs(f'database/storage/{folder_name}', exist_ok=True)
    folder = Folder(name=folder_name)
    session.add(folder)
    session.commit()
    session.refresh(folder)


def first_folder_set(session: Session):
    create_folder("MobileApp", session)
    create_folder("HardwareIOT", session)
    create_folder("WebApp", session)

def get_folder(session: Session):
    statement = select(Folder.name).order_by(Folder.id)  # Order by ID
    result = session.exec(statement)
    folder_list = list(result)  # Convert once
    logger.debug("LIST OF FOLDER: %s", folder_list)
    return folder_list

def update_file_data(folder_name: str, file_name: str, accuracy:int, session: Session):
    statement = select(Folder).where(Folder.name == folder_name)
    result = session.exec(statement)
    folder_obj = result.first()
    folder_id = folder_obj.id
    file = File(name=file_name, folder_id=folder_id, accuracy = accuracy)
    session.add(file)
    session.commit()
    session.refresh(file)

def update_accuracy(session: Session):
    statement = select(Folder)
    result = session.exec(statement)
    folder_list = list(result)
    accuracy_value = 0.0
    for folder in folder_list:
        file_statement = select(File).where(File.folder_id == folder.id)
        file_result = session.exec(file_statement)
        file_list = list(file_result)
        if file_list is not None:
            total_accuracy = []
            for file in file_list:
                if file.accuracy:  # Ensure accuracy is not None or empty
                    accuracy_values = list(
                        map(int, file.accuracy.strip("[]").split(",")))  # Convert string to list of ints

                    index = folder.id - 1  # Adjust index since folders start at 1

                    if 0 <= index < len(accuracy_values):  # Check if index is valid
                        folder_accuracy = accuracy_values[index]  # Get the accuracy using the adjusted index
                        total_accuracy.append(folder_accuracy)

            if total_accuracy:
                accuracy_value = sum(total_accuracy) / len(
                    total_accuracy)
                folder.total_accuracy =  accuracy_value # Compute the average accuracy for the folder

            session.commit()  # Save changes
    return accuracy_value