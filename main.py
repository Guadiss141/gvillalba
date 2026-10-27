# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import engine, Base, get_db
from models import TaskModel
from schemas import TaskCreate, TaskResponse


# Evento de inicio para crear las tablas automáticamente
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="FastAPI con SQLAlchemy 2.0",
    description="Ejemplo práctico de integración asíncrona",
    version="1.0.0",
    lifespan=lifespan
)


# Helper: busca una tarea por ID o lanza 404
async def get_task_or_404(task_id: int, db: AsyncSession) -> TaskModel:
    result = await db.execute(select(TaskModel).where(TaskModel.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada")
    return task


# 1. Crear una Tarea (CREATE)
@app.post("/tasks/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_db)):
    db_task = TaskModel(
        title=task.title,
        description=task.description,
        completed=task.completed
    )
    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)
    return db_task


# 2. Listar Tareas (READ - List). Oculta las archivadas por defecto
@app.get("/tasks/", response_model=list[TaskResponse])
async def read_tasks(
    skip: int = 0,
    limit: int = 10,
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
):
    query = select(TaskModel)
    if not include_archived:
        query = query.where(TaskModel.archived.is_(False))
    result = await db.execute(query.order_by(TaskModel.id).offset(skip).limit(limit))
    return list(result.scalars().all())


# 3. Obtener una Tarea por ID (READ - Detail)
@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def read_task(task_id: int, db: AsyncSession = Depends(get_db)):
    return await get_task_or_404(task_id, db)


# 4. Actualizar una Tarea (UPDATE)
@app.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, task_data: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = await get_task_or_404(task_id, db)

    task.title = task_data.title
    task.description = task_data.description
    task.completed = task_data.completed

    await db.commit()
    await db.refresh(task)
    return task


# 5. Eliminar una Tarea (DELETE)
@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await get_task_or_404(task_id, db)

    await db.delete(task)
    await db.commit()
    return None


# 6. Marcar como terminada
@app.patch("/tasks/{task_id}/complete", response_model=TaskResponse)
async def complete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await get_task_or_404(task_id, db)
    task.completed = True
    await db.commit()
    await db.refresh(task)
    return task


# 7. Archivar una tarea (solo si está terminada)
@app.patch("/tasks/{task_id}/archive", response_model=TaskResponse)
async def archive_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await get_task_or_404(task_id, db)
    if not task.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se pueden archivar tareas terminadas",
        )
    task.archived = True
    await db.commit()
    await db.refresh(task)
    return task


# 8. Archivar todas las terminadas de una vez
@app.post("/tasks/archive-completed")
async def archive_completed(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        update(TaskModel)
        .where(TaskModel.completed.is_(True), TaskModel.archived.is_(False))
        .values(archived=True)
    )
    await db.commit()
    return {"archived": result.rowcount}