from fastapi import APIRouter, Depends, HTTPException, status, Header
import httpx
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from models.embeddings_helper import get_embedding
from controllers.auth_helper import get_current_user

router = APIRouter()

SPRING_URL = "http://localhost:8001"
NODE_URL = "http://localhost:8002"

# --- Pydantic Schemas ---

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    priority: str = "Medium"  # Low, Medium, High
    due_date: Optional[str] = None  # YYYY-MM-DD
    assigned_user_id: Optional[int] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None

class StatusUpdate(BaseModel):
    status: str  # Backlog, To Do, In Progress, Review, Completed

class AssignRequest(BaseModel):
    task_id: int
    user_id: int

class CommentCreate(BaseModel):
    task_id: int
    comment: str

class SemanticSearchQuery(BaseModel):
    query: str

class UserCreateSchema(BaseModel):
    fullname: str
    phone: str
    email: str
    password: str
    role: int = 1
    status: int = 1

class UserEditSchema(BaseModel):
    fullname: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[int] = None
    status: Optional[int] = None

# --- Helper to resolve active user details from Spring Boot ---
async def get_user_profile(token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(f"{SPRING_URL}/user/profile", headers={"Token": token})
            if res.status_code == 200:
                profile = res.json()
                if profile.get("code") == 200 and profile.get("user"):
                    # The return value from Spring Boot is [Users, Roles] or list of lists
                    user_list = profile["user"]
                    if isinstance(user_list, list) and len(user_list) > 0:
                        # Spring profileByEmail returns object array or single object depending on mapping
                        # Let's extract user object
                        user_obj = user_list[0]
                        return user_obj
        except Exception as e:
            print(f"Error fetching user profile: {e}")
    raise HTTPException(status_code=401, detail="Could not resolve user profile from Spring Boot.")

# --- Tasks REST API Endpoints ---

@router.get("/tasks")
async def get_tasks(
    current_user: dict = Depends(get_current_user),
    Token: str = Header(..., alias="Token")
):
    user_obj = await get_user_profile(Token)
    user_id = user_obj.get("id")
    user_role = current_user["role"]

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SPRING_URL}/api/tasks",
            headers={
                "X-User-Id": str(user_id),
                "X-User-Role": str(user_role)
            }
        )
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()

@router.post("/tasks", status_code=201)
async def create_task(
    payload: TaskCreate,
    current_user: dict = Depends(get_current_user),
    Token: str = Header(..., alias="Token")
):
    if current_user["role"] != 2:
        raise HTTPException(status_code=403, detail="Access denied. Only administrators can create tasks.")

    user_obj = await get_user_profile(Token)

    # 1. Save to Spring Boot SQL database
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SPRING_URL}/api/tasks",
            json=payload.model_dump()
        )
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    spring_res = response.json()
    task_id = spring_res.get("task_id")
    assigned_user_name = spring_res.get("assigned_user_name", "Unassigned")

    # 2. Write MongoDB task_logs
    log_payload = {
        "task_id": task_id,
        "action": "Task Created",
        "old_status": None,
        "new_status": "Backlog",
        "assigned_user": assigned_user_name,
        "updated_by": user_obj.get("fullname", "Admin")
    }
    async with httpx.AsyncClient() as client:
        await client.post(f"{NODE_URL}/api/logs", json=log_payload)

    # 3. Generate text embedding and store in MongoDB
    combined_text = f"Title: {payload.title} | Description: {payload.description or ''} | Comments: "
    vector = get_embedding(combined_text)
    embedding_payload = {
        "task_id": task_id,
        "embedding": vector,
        "text": combined_text
    }
    async with httpx.AsyncClient() as client:
        await client.post(f"{NODE_URL}/api/embeddings", json=embedding_payload)

    # 4. Fetch the created task from Spring Boot and sync with MongoDB tasks collection
    async with httpx.AsyncClient() as client:
        tasks_res = await client.get(
            f"{SPRING_URL}/api/tasks",
            headers={
                "X-User-Id": str(user_obj.get("id")),
                "X-User-Role": str(current_user["role"])
            }
        )
        tasks_list = tasks_res.json()
        new_task_details = next((t for t in tasks_list if t["task_id"] == task_id), None)

    if new_task_details:
        mongo_task_payload = {
            "task_id": task_id,
            "title": new_task_details["title"],
            "description": new_task_details["description"],
            "due_date": new_task_details["due_date"],
            "current_stage": new_task_details["current_stage"],
            "assigned_to": new_task_details["assigned_to"]
        }
        async with httpx.AsyncClient() as client:
            await client.post(f"{NODE_URL}/api/mongodb/tasks", json=mongo_task_payload)

    return {"message": "Task created successfully.", "task_id": task_id}

@router.put("/tasks/{id}")
async def update_task(
    id: int,
    payload: TaskUpdate,
    current_user: dict = Depends(get_current_user),
    Token: str = Header(..., alias="Token")
):
    if current_user["role"] not in [2, 3]:
        raise HTTPException(status_code=403, detail="Access denied. Only managers and administrators can update tasks.")

    user_obj = await get_user_profile(Token)

    # 1. Update metadata in Spring Boot SQL Database
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{SPRING_URL}/api/tasks/{id}",
            json=payload.model_dump()
        )
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    # 2. Fetch the updated task details to refresh embedding text
    async with httpx.AsyncClient() as client:
        tasks_res = await client.get(
            f"{SPRING_URL}/api/tasks",
            headers={
                "X-User-Id": str(user_obj.get("id")),
                "X-User-Role": str(current_user["role"])
            }
        )
        tasks_list = tasks_res.json()
        updated_task = next((t for t in tasks_list if t["task_id"] == id), None)

    if updated_task:
        # Fetch comments from Node.js
        async with httpx.AsyncClient() as client:
            comments_res = await client.get(f"{NODE_URL}/api/comments/{id}")
            comments_list = [c["comment"] for c in comments_res.json()]

        # Generate vector embedding text
        comments_str = " ".join(comments_list)
        combined_text = f"Title: {updated_task['title']} | Description: {updated_task['description'] or ''} | Comments: {comments_str}"
        vector = get_embedding(combined_text)

        # Upsert embedding
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{NODE_URL}/api/embeddings",
                json={
                    "task_id": id,
                    "embedding": vector,
                    "text": combined_text
                }
            )

        # Sync metadata update with MongoDB tasks collection
        mongo_task_payload = {
            "title": updated_task["title"],
            "description": updated_task["description"],
            "due_date": updated_task["due_date"],
            "current_stage": updated_task["current_stage"],
            "assigned_to": updated_task["assigned_to"]
        }
        async with httpx.AsyncClient() as client:
            await client.put(f"{NODE_URL}/api/mongodb/tasks/{id}", json=mongo_task_payload)

    # 3. Log Update Event in MongoDB
    log_payload = {
        "task_id": id,
        "action": "Task Metadata Updated",
        "updated_by": user_obj.get("fullname", "Admin")
    }
    async with httpx.AsyncClient() as client:
        await client.post(f"{NODE_URL}/api/logs", json=log_payload)

    return {"message": "Task updated successfully."}

@router.delete("/tasks/{id}")
async def delete_task(
    id: int,
    current_user: dict = Depends(get_current_user),
    Token: str = Header(..., alias="Token")
):
    if current_user["role"] not in [2, 3]:
        raise HTTPException(status_code=403, detail="Access denied. Only managers and administrators can delete tasks.")

    # 1. Delete from Spring Boot SQL Database
    async with httpx.AsyncClient() as client:
        response = await client.delete(f"{SPRING_URL}/api/tasks/{id}")
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    # 2. Clean up NoSQL MongoDB collections
    async with httpx.AsyncClient() as client:
        await client.delete(f"{NODE_URL}/api/comments/task/{id}")
        await client.delete(f"{NODE_URL}/api/logs/task/{id}")
        await client.delete(f"{NODE_URL}/api/embeddings/task/{id}")
        await client.delete(f"{NODE_URL}/api/mongodb/tasks/{id}")

    return {"message": "Task deleted successfully."}

# --- Workflow Management ---

@router.put("/tasks/{id}/status")
async def update_task_status(
    id: int,
    payload: StatusUpdate,
    current_user: dict = Depends(get_current_user),
    Token: str = Header(..., alias="Token")
):
    user_obj = await get_user_profile(Token)

    # 1. Perform status update validation & change in Spring Boot
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{SPRING_URL}/api/tasks/{id}/status",
            json={"status": payload.status},
            headers={"X-User-Name": user_obj.get("fullname", "User")}
        )
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    spring_res = response.json()
    old_stage = spring_res.get("old_stage")
    current_stage = spring_res.get("current_stage")

    # Sync status update with MongoDB tasks collection
    async with httpx.AsyncClient() as client:
        await client.put(f"{NODE_URL}/api/mongodb/tasks/{id}", json={"current_stage": current_stage})

    # 2. Log Status Transition event in MongoDB
    log_payload = {
        "task_id": id,
        "action": "Status Changed",
        "old_status": old_stage,
        "new_status": current_stage,
        "updated_by": user_obj.get("fullname", "User")
    }
    async with httpx.AsyncClient() as client:
        await client.post(f"{NODE_URL}/api/logs", json=log_payload)

    return {"message": f"Task status updated to '{current_stage}'.", "task_id": id, "current_stage": current_stage}

# --- Task Assignment Module ---

@router.post("/assign-task")
async def assign_task(
    payload: AssignRequest,
    current_user: dict = Depends(get_current_user),
    Token: str = Header(..., alias="Token")
):
    if current_user["role"] not in [2, 3]:
        raise HTTPException(status_code=403, detail="Access denied. Only managers and administrators can assign tasks.")

    user_obj = await get_user_profile(Token)

    # 1. Update assignment in Spring Boot
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SPRING_URL}/api/assign-task",
            json=payload.model_dump(),
            headers={"X-User-Name": user_obj.get("fullname", "Manager")}
        )
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    spring_res = response.json()
    old_assignee = spring_res.get("old_assignee", "Unassigned")
    new_assignee = spring_res.get("new_assignee")

    # Fetch updated task list from Spring Boot to get full assigned_to details
    async with httpx.AsyncClient() as client:
        tasks_res = await client.get(
            f"{SPRING_URL}/api/tasks",
            headers={
                "X-User-Id": str(user_obj.get("id")),
                "X-User-Role": str(current_user["role"])
            }
        )
        tasks_list = tasks_res.json()
        updated_task = next((t for t in tasks_list if t["task_id"] == payload.task_id), None)

    if updated_task:
        # Sync assignee update with MongoDB tasks collection
        async with httpx.AsyncClient() as client:
            await client.put(f"{NODE_URL}/api/mongodb/tasks/{payload.task_id}", json={"assigned_to": updated_task["assigned_to"]})

    # 2. Log Assignment Change event in MongoDB
    log_payload = {
        "task_id": payload.task_id,
        "action": "Assignment Changed",
        "old_assignee": old_assignee,
        "new_assignee": new_assignee,
        "updated_by": user_obj.get("fullname", "Manager")
    }
    async with httpx.AsyncClient() as client:
        await client.post(f"{NODE_URL}/api/logs", json=log_payload)

    return {"message": f"Task successfully assigned to '{new_assignee}'."}

# --- Comment Collaboration ---

@router.post("/comments")
async def add_comment(
    payload: CommentCreate,
    current_user: dict = Depends(get_current_user),
    Token: str = Header(..., alias="Token")
):
    user_obj = await get_user_profile(Token)

    # 1. Save comment to MongoDB
    comment_payload = {
        "task_id": payload.task_id,
        "user_id": user_obj.get("id"),
        "user_name": user_obj.get("fullname"),
        "comment": payload.comment
    }
    async with httpx.AsyncClient() as client:
        comment_res = await client.post(f"{NODE_URL}/api/comments", json=comment_payload)
    if comment_res.status_code != 201:
        raise HTTPException(status_code=comment_res.status_code, detail=comment_res.text)

    # 2. Log Comment event to MongoDB
    log_payload = {
        "task_id": payload.task_id,
        "action": "Comment Added",
        "updated_by": user_obj.get("fullname")
    }
    async with httpx.AsyncClient() as client:
        await client.post(f"{NODE_URL}/api/logs", json=log_payload)

    # 3. Refresh vector embedding in MongoDB
    # Fetch task details from Spring Boot
    async with httpx.AsyncClient() as client:
        tasks_res = await client.get(
            f"{SPRING_URL}/api/tasks",
            headers={
                "X-User-Id": str(user_obj.get("id")),
                "X-User-Role": str(current_user["role"])
            }
        )
        task = next((t for t in tasks_res.json() if t["task_id"] == payload.task_id), None)

    if task:
        # Fetch all comments for task
        async with httpx.AsyncClient() as client:
            comments_res = await client.get(f"{NODE_URL}/api/comments/{payload.task_id}")
            comments_list = [c["comment"] for c in comments_res.json()]

        # Generate embedding
        comments_str = " ".join(comments_list)
        combined_text = f"Title: {task['title']} | Description: {task['description'] or ''} | Comments: {comments_str}"
        vector = get_embedding(combined_text)

        # Upsert embedding
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{NODE_URL}/api/embeddings",
                json={
                    "task_id": payload.task_id,
                    "embedding": vector,
                    "text": combined_text
                }
            )

    return {"message": "Comment added successfully."}

@router.get("/comments/{task_id}")
async def get_comments(
    task_id: int,
    current_user: dict = Depends(get_current_user)
):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{NODE_URL}/api/comments/{task_id}")
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()

@router.get("/tasks/{task_id}/logs")
async def get_task_logs(
    task_id: int,
    current_user: dict = Depends(get_current_user)
):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{NODE_URL}/api/logs/{task_id}")
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()

# --- Dashboard Analytics ---

@router.get("/dashboard")
async def get_dashboard_analytics(
    current_user: dict = Depends(get_current_user)
):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{SPRING_URL}/api/dashboard")
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()

# --- Intelligent Semantic Search (Main AI Feature) ---

@router.post("/semantic-search")
async def semantic_search(
    payload: SemanticSearchQuery,
    current_user: dict = Depends(get_current_user),
    Token: str = Header(..., alias="Token")
):
    user_obj = await get_user_profile(Token)

    # 1. Generate query vector embedding
    query_vector = get_embedding(payload.query)

    # 2. Match similarity locally on Node.js / MongoDB
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{NODE_URL}/api/semantic-search",
            json={"query_vector": query_vector}
        )
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    similarities = response.json()  # List of {"task_id": 1, "score": 0.89}
    if not similarities:
        return []

    # Map task similarity score
    score_map = {item["task_id"]: item["score"] for item in similarities}
    task_ids = list(score_map.keys())

    # 3. Fetch task details from Spring Boot (PostgreSQL)
    async with httpx.AsyncClient() as client:
        tasks_res = await client.get(
            f"{SPRING_URL}/api/tasks",
            headers={
                "X-User-Id": str(user_obj.get("id")),
                "X-User-Role": str(current_user["role"])
            }
        )
    if tasks_res.status_code != 200:
        raise HTTPException(status_code=tasks_res.status_code, detail=tasks_res.text)

    all_tasks = tasks_res.json()

    # Filter tasks in similarity list and attach score
    matched_tasks = []
    for t in all_tasks:
        tid = t["task_id"]
        if tid in score_map:
            t_copy = t.copy()
            t_copy["score"] = float(score_map[tid])
            matched_tasks.append(t_copy)

    # Sort matching tasks exactly by similarity score descending
    matched_tasks.sort(key=lambda x: x["score"], reverse=True)

    return matched_tasks

# --- Admin User Management Endpoints Routed to Spring Boot ---

@router.post("/authservice/adduser")
async def add_user(
    payload: UserCreateSchema,
    current_user: dict = Depends(get_current_user),
    Token: str = Header(..., alias="Token")
):
    if current_user["role"] != 2:
        raise HTTPException(status_code=403, detail="Access denied. Only administrators can add users.")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SPRING_URL}/user/adduser",
            json=payload.model_dump()
        )
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()

@router.put("/authservice/edituser/{id}")
async def edit_user(
    id: int,
    payload: UserEditSchema,
    current_user: dict = Depends(get_current_user),
    Token: str = Header(..., alias="Token")
):
    # Admin (role=2) can edit any user; user editing their own profile is handled directly
    # check validation rules:
    if current_user["role"] != 2:
        # Allow if editing their own profile ID
        user_obj = await get_user_profile(Token)
        if user_obj.get("id") != id:
            raise HTTPException(status_code=403, detail="Access denied. Only administrators can edit other users.")

    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{SPRING_URL}/user/edituser/{id}",
            json=payload.model_dump()
        )
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()

@router.delete("/authservice/deleteuser/{id}")
async def delete_user(
    id: int,
    current_user: dict = Depends(get_current_user),
    Token: str = Header(..., alias="Token")
):
    if current_user["role"] != 2:
        raise HTTPException(status_code=403, detail="Access denied. Only administrators can delete users.")

    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{SPRING_URL}/user/deleteuser/{id}"
        )
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()
