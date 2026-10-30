import sys
import os
import uuid
from dotenv import load_dotenv

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(backend_dir, ".env"))
sys.path.insert(0, backend_dir)

from app.db.session import engine, SessionLocal
from app.db.models import Base, User, Workspace, WorkspaceMember

def init_db():
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created.")
    
    db = SessionLocal()
    try:
        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        ws_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            print("Creating default dev user...")
            dev_user = User(
                id=user_id,
                email="dev@local.internal",
                display_name="Dev Administrator",
                role="admin",
                status="active"
            )
            db.add(dev_user)
            db.commit()
            
        ws = db.query(Workspace).filter_by(id=ws_id).first()
        if not ws:
            print("Creating default workspace...")
            dev_ws = Workspace(
                id=ws_id,
                name="Default Workspace",
                created_by_id=user_id
            )
            db.add(dev_ws)
            db.commit()
            
        member = db.query(WorkspaceMember).filter_by(workspace_id=ws_id, user_id=user_id).first()
        if not member:
            print("Creating default membership...")
            dev_member = WorkspaceMember(
                workspace_id=ws_id,
                user_id=user_id,
                role="admin"
            )
            db.add(dev_member)
            db.commit()
            
        print("Database initialized successfully!")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
