import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Project, Donation

app = FastAPI(title="Moonshot Fund API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Moonshot Fund Backend Running"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response

# Simple DTOs for responses
class ProjectOut(BaseModel):
    id: str
    title: str
    founder_name: str
    founder_email: str
    description: str
    category: str
    goal_amount: float
    featured: bool
    total_donations: float

class DonationOut(BaseModel):
    id: str
    project_id: str
    donor_name: str
    amount: float
    message: Optional[str] = None

@app.post("/api/projects", response_model=dict)
async def create_project(project: Project):
    try:
        inserted_id = create_document("project", project)
        return {"id": inserted_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects", response_model=List[ProjectOut])
async def list_projects(category: Optional[str] = None, featured: Optional[bool] = None):
    try:
        filter_dict = {}
        if category:
            filter_dict["category"] = category
        if featured is not None:
            filter_dict["featured"] = featured
        docs = get_documents("project", filter_dict)

        # aggregate donations per project
        results: List[ProjectOut] = []
        for d in docs:
            pid = str(d.get("_id"))
            donations = db["donation"].aggregate([
                {"$match": {"project_id": pid}},
                {"$group": {"_id": "$project_id", "total": {"$sum": "$amount"}}}
            ])
            total = 0.0
            for agg in donations:
                total = float(agg.get("total", 0))
            results.append(ProjectOut(
                id=pid,
                title=d.get("title"),
                founder_name=d.get("founder_name"),
                founder_email=d.get("founder_email"),
                description=d.get("description"),
                category=d.get("category", "AI"),
                goal_amount=float(d.get("goal_amount", 0)),
                featured=bool(d.get("featured", False)),
                total_donations=total
            ))
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/donations", response_model=dict)
async def create_donation(donation: Donation):
    # Validate project exists
    try:
        pid = donation.project_id
        try:
            _ = ObjectId(pid)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid project_id")

        project = db["project"].find_one({"_id": ObjectId(pid)})
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        inserted_id = create_document("donation", donation)
        return {"id": inserted_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str):
    try:
        doc = db["project"].find_one({"_id": ObjectId(project_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Project not found")
        donations = db["donation"].aggregate([
            {"$match": {"project_id": project_id}},
            {"$group": {"_id": "$project_id", "total": {"$sum": "$amount"}}}
        ])
        total = 0.0
        for agg in donations:
            total = float(agg.get("total", 0))
        return ProjectOut(
            id=str(doc.get("_id")),
            title=doc.get("title"),
            founder_name=doc.get("founder_name"),
            founder_email=doc.get("founder_email"),
            description=doc.get("description"),
            category=doc.get("category", "AI"),
            goal_amount=float(doc.get("goal_amount", 0)),
            featured=bool(doc.get("featured", False)),
            total_donations=total
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
