from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base

class DBUser(Base):
    __tablename__ = "users"
    
    # Matching Spring Boot User entity fields exactly
    id = Column(Integer, primary_key=True, index=True)
    fullname = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(Integer, default=1)  # 1: Employee/User, 2: Admin, 3: Manager
    status = Column(Integer, default=1) # 1: Active, 0: Inactive

class DBTask(Base):
    __tablename__ = "tasks"
    
    task_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    priority = Column(String(50), default="Medium")  # Low, Medium, High
    due_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    status = relationship("DBTaskStatus", back_populates="task", cascade="all, delete-orphan", uselist=False)
    assignments = relationship("DBAssignment", back_populates="task", cascade="all, delete-orphan")

class DBTaskStatus(Base):
    __tablename__ = "task_status"
    
    status_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False, unique=True)
    current_stage = Column(String(100), default="Backlog")  # Backlog, To Do, In Progress, Review, Completed
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    task = relationship("DBTask", back_populates="status")

class DBAssignment(Base):
    __tablename__ = "assignments"
    
    assignment_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=func.now())
    
    task = relationship("DBTask", back_populates="assignments")
    user = relationship("DBUser", foreign_keys=[user_id], primaryjoin="DBAssignment.user_id == DBUser.id")
