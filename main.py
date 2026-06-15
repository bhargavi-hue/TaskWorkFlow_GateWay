from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from controllers.init import *
from models.database import engine, Base
import models.task  # imports models so SQLAlchemy knows about them
from fastapi.middleware.cors import CORSMiddleware

# Create database tables if they do not exist
try:
    Base.metadata.create_all(bind=engine)
    print("Database: Created tables successfully.")
    
    # Seed new menu 3 (Semantic Search) and Manager role (3) mapping
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO menus (mid, menu, icon) VALUES (1, 'Dashboard', 'dashboard.png') ON CONFLICT (mid) DO NOTHING"))
        conn.execute(text("INSERT INTO menus (mid, menu, icon) VALUES (2, 'My Tasks', 'tasks.png') ON CONFLICT (mid) DO NOTHING"))
        conn.execute(text("INSERT INTO menus (mid, menu, icon) VALUES (3, 'Semantic Search', 'search.png') ON CONFLICT (mid) DO NOTHING"))
        conn.execute(text("INSERT INTO menus (mid, menu, icon) VALUES (4, 'User Manager', 'users.png') ON CONFLICT (mid) DO NOTHING"))
        conn.execute(text("INSERT INTO menus (mid, menu, icon) VALUES (5, 'Profile', 'profile.png') ON CONFLICT (mid) DO NOTHING"))
        
        # Seed Role Mapping for User (role 1) -> mid 1, 2, 3, 5
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (1, 1) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (1, 2) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (1, 3) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (1, 5) ON CONFLICT DO NOTHING"))
        
        # Seed Role Mapping for Administrator (role 2) -> mid 1, 3, 4, 5
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (2, 1) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (2, 3) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (2, 4) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (2, 5) ON CONFLICT DO NOTHING"))
        
        # Seed Role Mapping for Manager (role 3) -> mid 1, 2, 3, 5
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (3, 1) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (3, 2) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (3, 3) ON CONFLICT DO NOTHING"))
        conn.execute(text("INSERT INTO roles_mapping (role, mid) VALUES (3, 5) ON CONFLICT DO NOTHING"))
        
        # Seed Manager Role details in roles table (if role 3 is missing)
        conn.execute(text("INSERT INTO roles (role, rolename) VALUES (3, 'Manager') ON CONFLICT (role) DO NOTHING"))
        
        conn.commit()
        print("Database: Seeded 'Semantic Search' (mid 3) and 'Manager' (role 3) mappings successfully.")
except Exception as e:
    print(f"Database: Table creation or seeding failed (or schema loading in progress): {e}")


app = FastAPI()

# Enable Cors - allow frontend dev server and all origins for testing
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins = origins,   
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"]
)

# Register all routes
app.include_router(AuthenticationRouter)
app.include_router(TaskRouter)

@app.get("/")
def home():
    return "Started...."