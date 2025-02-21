import asyncio
import json
import logging
import os
import pathlib
import urllib
import uuid
from contextlib import asynccontextmanager
from typing import List

import aiofiles
import uvicorn
from fastapi import FastAPI, Depends, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from sqlmodel import Session, select
from starlette.middleware.cors import CORSMiddleware

from AIDOC_database import create_db_and_tables, get_session, first_folder_set, update_accuracy
from AIDOC_files_reciver import launch_scan
from AIDOC_upload_status import upload_status
from model.AIDOC_fileModel import File
from model.AIDOC_folderModel import Folder

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # This will output to terminal
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager #แก้ไขฟังชั่นให้ง่ายต่อการจัดการ resource
async def lifespan(app: FastAPI): #เป็นฟังชั่นที่จะทำงานเมื่อเริ่มต้นทำงาน
    create_db_and_tables()        #เรียกใช้งาน ฟังชัน สร้างฐานข้อมูล

    session_gen = get_session()
    session = next(session_gen)  #สร้าง Session สำหรับคำสั่งถัดไป

    try:
        folders = session.exec(select(Folder)).all() #หาโฟลเดอร์ทั้งหมด
        if not folders:                              #หากไม่มีโฟลเดอร์ให้ทำขั้นตอนต่อไป
            first_folder_set(session)                #สร้างโฟลเดอร์ชุดแรก
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass
    yield                      #หยุดการทำงานฟังชั่นนี้


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )


@app.get("/getFolders")
def get_folders(session: Session = Depends(get_session)):
    update_accuracy(session)
    statement = select(Folder)
    folders = session.exec(statement).all()
    folder_list = list(folders)
    return folder_list


@app.get("/getFiles")
def get_files(folder_id:str, session: Session = Depends(get_session)):
    statement = select(File).where(File.folder_id == folder_id)
    files = session.exec(statement)
    file_list = list(files)
    return file_list

@app.post("/sendPDF")
async def send_pdf(
    background_tasks: BackgroundTasks,
    pdfs: List[UploadFile] = File(),
    session: Session = Depends(get_session)
):
    pathlib.Path("database/temp").mkdir(parents=True, exist_ok=True)
    task_ids = []
    for pdf in pdfs:
        file_name = pdf.filename
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)
        folder_list = get_folders(session)
        path = "database/temp"
        pathlib.Path(f"{path}/{task_id}").mkdir(parents=True, exist_ok=True)
        try:
            async with aiofiles.open(f'{path}/{task_id}/{file_name}', 'wb') as temp_file:
                pdf_content = await pdf.read()
                await temp_file.write(pdf_content)
            # Set initial status to "Processing"
            upload_status[task_id] = {
                "status": "Processing",
                "file_name": file_name,
                "files_remaining": len(pdfs),  # or something you update for each file
            }
            background_tasks.add_task(
                launch_scan,
                pdf_content,
                file_name,
                task_id,
                folder_list,
                session
            )
        except Exception as e:
            logger.error(f"Error reading PDF file: {e}")
            upload_status[task_id] = "Failed"
            raise HTTPException(status_code=400, detail="Failed to read PDF file")
    # Return the list of task IDs so the front end can track them individually.
    return {"status": "success", "task_ids": task_ids, "message": "PDF received and processing in background"}


@app.get("/getPDF")
def get_pdf(folder_name: str, file_name: str, session: Session = Depends(get_session)):
    file_path = os.path.join("database/storage", folder_name, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Use extended filename encoding (UTF-8) to handle non-ASCII characters (e.g., Thai)
    disposition = f"inline; filename*=UTF-8''{urllib.parse.quote(file_name)}"

    return FileResponse(
        file_path,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition}
    )
@app.get("/uploadStream/{task_id}")
async def upload_stream(task_id: str):
    """
    SSE endpoint for the front end to listen for real-time status updates
    using EventSource("/uploadStream/{task_id}").
    """

    async def event_generator():
        while True:
            # Check the dictionary for the current status
            current_status = upload_status.get(task_id)

            if current_status is None:
                # If there's no record for this task_id, send error and break
                yield f"data: {json.dumps({'error': 'Unknown Task ID'})}\n\n"
                break

            # Serialize the status dictionary to JSON
            try:
                status_json = json.dumps(current_status)
                yield f"data: {status_json}\n\n"
            except Exception as e:
                logger.error(f"Error serializing status: {e}")
                yield f"data: {json.dumps({'error': 'Status serialization failed'})}\n\n"
                break

            # If completed or failed, stop streaming
            if current_status.get('status') in ["Completed", "Failed"]:
                break

            # Wait before next check
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

@app.delete("/deleteFile")
def delete_file(file_id: str, session: Session = Depends(get_session)):

    # Query the file using its unique id
    statement = select(File).where(File.id == file_id)
    file_obj = session.exec(statement).first()
    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")

    statement_folder = select(Folder).where(Folder.id == file_obj.folder_id)
    folder_obj = session.exec(statement_folder).first()
    if not folder_obj:
        raise HTTPException(status_code=404, detail="Folder not found")

    file_path = os.path.join("database/storage", folder_obj.name, file_obj.name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    try:
        os.remove(file_path)
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(status_code=500, detail="Error deleting file")

    session.delete(file_obj)
    session.commit()

    return {"success": True, "message": "File deleted successfully"}