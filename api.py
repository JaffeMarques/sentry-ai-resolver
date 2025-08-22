#!/usr/bin/env python3

import asyncio
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

from main import SentrySolver
from sentry_client import SentryMCPClient
from database import Database
from config import config

# Pydantic models
class ProjectRequest(BaseModel):
    project_slug: str
    work_directory: Optional[str] = None

class SolverStatus(BaseModel):
    project_slug: Optional[str]
    status: str
    session_id: Optional[int]
    started_at: Optional[str]
    issues_processed: int
    fixes_applied: int

class GitConfigRequest(BaseModel):
    git_branch_prefix: str = "sentry-fix"
    git_include_issue_id: bool = True
    git_include_timestamp: bool = True
    commit_message_prefix: str = "fix"
    commit_message_format: str = "conventional"  # simple, conventional, detailed
    git_auto_push: bool = True

class IssueFilterRequest(BaseModel):
    issue_min_severity: str = "all"  # all, debug, info, warning, error, fatal
    issue_environments: str = "all"  # comma-separated list or "all"
    issue_min_occurrences: int = 1
    issue_max_age_days: int = 30

class IssueResponse(BaseModel):
    id: str
    title: str
    level: str
    status: str
    count: int
    fix_applied: bool
    confidence: float
    processed_at: Optional[str]

# Global solver instance management
active_solvers: Dict[str, Dict[str, Any]] = {}
solver_threads: Dict[str, threading.Thread] = {}

app = FastAPI(title="Sentry Solver API", version="1.0.0")
db = Database()

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

# Background task to run solver
def run_solver_background(project_slug: str, work_directory: Optional[str] = None):
    """Run solver in background thread"""
    try:
        # Temporarily set work directory in config if provided
        if work_directory:
            config.work_directory = work_directory
            
        solver = SentrySolver(project_slug=project_slug)
        active_solvers[project_slug] = {
            'solver': solver,
            'status': 'running',
            'session_id': db.create_session(project_slug),
            'started_at': datetime.now().isoformat(),
            'work_directory': work_directory
        }
        
        # Start the scheduler (this will block)
        solver.start_scheduler()
        
    except Exception as e:
        logging.error(f"Error running solver for {project_slug}: {e}")
        if project_slug in active_solvers:
            active_solvers[project_slug]['status'] = 'error'

@app.get("/")
async def read_root():
    """Serve the main HTML page"""
    return FileResponse('static/index.html')

@app.get("/api/projects")
async def get_projects():
    """Get list of available Sentry projects"""
    try:
        client = SentryMCPClient()
        projects = client.get_projects()
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch projects: {str(e)}")

@app.post("/api/solver/start")
async def start_solver(request: ProjectRequest):
    """Start the solver for a specific project"""
    project_slug = request.project_slug
    
    if project_slug in active_solvers and active_solvers[project_slug]['status'] == 'running':
        raise HTTPException(status_code=400, detail=f"Solver already running for project {project_slug}")
    
    try:
        # Stop existing thread if exists
        if project_slug in solver_threads and solver_threads[project_slug].is_alive():
            solver_threads[project_slug].join(timeout=1)
        
        # Start new thread
        thread = threading.Thread(
            target=run_solver_background,
            args=(project_slug, request.work_directory),
            daemon=True
        )
        thread.start()
        solver_threads[project_slug] = thread
        
        return {"message": f"Solver started for project {project_slug}", "status": "started"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start solver: {str(e)}")

@app.post("/api/solver/stop")
async def stop_solver(request: ProjectRequest):
    """Stop the solver for a specific project"""
    project_slug = request.project_slug
    
    if project_slug not in active_solvers:
        raise HTTPException(status_code=404, detail=f"No active solver found for project {project_slug}")
    
    try:
        # Update status
        active_solvers[project_slug]['status'] = 'stopping'
        
        # Update database
        session_id = active_solvers[project_slug].get('session_id')
        if session_id:
            db.update_session_status(session_id, 'stopped')
        
        # Clean up
        if project_slug in solver_threads:
            solver_threads[project_slug].join(timeout=2)
            del solver_threads[project_slug]
        
        active_solvers[project_slug]['status'] = 'stopped'
        
        return {"message": f"Solver stopped for project {project_slug}", "status": "stopped"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop solver: {str(e)}")

@app.get("/api/solver/status/{project_slug}")
async def get_solver_status(project_slug: str) -> SolverStatus:
    """Get solver status for a specific project"""
    
    # Check active solver
    if project_slug in active_solvers:
        solver_info = active_solvers[project_slug]
        stats = db.get_issue_stats(project_slug)
        
        return SolverStatus(
            project_slug=project_slug,
            status=solver_info['status'],
            session_id=solver_info.get('session_id'),
            started_at=solver_info.get('started_at'),
            issues_processed=stats['total'],
            fixes_applied=stats['fixed']
        )
    
    # Check database for last session
    session = db.get_active_session(project_slug)
    stats = db.get_issue_stats(project_slug)
    
    return SolverStatus(
        project_slug=project_slug,
        status='stopped',
        session_id=session.get('id') if session else None,
        started_at=session.get('started_at') if session else None,
        issues_processed=stats['total'],
        fixes_applied=stats['fixed']
    )

@app.get("/api/issues/{project_slug}")
async def get_issues(project_slug: str, status: Optional[str] = None, limit: int = 50):
    """Get issues for a specific project"""
    try:
        issues = db.get_issues(project_slug, status, limit)
        return {"issues": issues}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch issues: {str(e)}")

@app.get("/api/stats/{project_slug}")
async def get_stats(project_slug: str):
    """Get statistics for a specific project"""
    try:
        stats = db.get_issue_stats(project_slug)
        recent_fixes = db.get_recent_fixes(project_slug)
        
        return {
            "stats": stats,
            "recent_fixes": recent_fixes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")

@app.post("/api/solver/run-once")
async def run_solver_once(request: ProjectRequest, background_tasks: BackgroundTasks):
    """Run solver once for testing"""
    project_slug = request.project_slug
    
    def run_once_background():
        try:
            # Temporarily set work directory in config if provided
            if request.work_directory:
                config.work_directory = request.work_directory
                
            solver = SentrySolver(project_slug=project_slug)
            solver.run_once()
        except Exception as e:
            logging.error(f"Error running solver once for {project_slug}: {e}")
    
    background_tasks.add_task(run_once_background)
    return {"message": f"Running solver once for project {project_slug}"}

@app.get("/api/git-config")
async def get_git_config():
    """Get current Git configuration"""
    try:
        return {
            "git_branch_prefix": config.git_branch_prefix,
            "git_include_issue_id": config.git_include_issue_id,
            "git_include_timestamp": config.git_include_timestamp,
            "commit_message_prefix": config.commit_message_prefix,
            "commit_message_format": config.commit_message_format,
            "git_auto_push": config.git_auto_push,
            "git_create_pr": config.git_create_pr
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get git config: {str(e)}")

@app.post("/api/git-config")
async def update_git_config(git_config: GitConfigRequest):
    """Update Git configuration"""
    try:
        import os
        
        # Update the configuration values
        config.git_branch_prefix = git_config.git_branch_prefix
        config.git_include_issue_id = git_config.git_include_issue_id
        config.git_include_timestamp = git_config.git_include_timestamp
        config.commit_message_prefix = git_config.commit_message_prefix
        config.commit_message_format = git_config.commit_message_format
        config.git_auto_push = git_config.git_auto_push
        
        # Update .env file to persist changes
        env_path = ".env"
        env_updates = {
            "SENTRY_SOLVER_GIT_BRANCH_PREFIX": git_config.git_branch_prefix,
            "SENTRY_SOLVER_GIT_INCLUDE_ISSUE_ID": str(git_config.git_include_issue_id).lower(),
            "SENTRY_SOLVER_GIT_INCLUDE_TIMESTAMP": str(git_config.git_include_timestamp).lower(),
            "SENTRY_SOLVER_COMMIT_MESSAGE_PREFIX": git_config.commit_message_prefix,
            "SENTRY_SOLVER_COMMIT_MESSAGE_FORMAT": git_config.commit_message_format,
            "SENTRY_SOLVER_GIT_AUTO_PUSH": str(git_config.git_auto_push).lower()
        }
        
        # Read current .env file
        env_lines = []
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                env_lines = f.readlines()
        
        # Update or add configuration lines
        updated_keys = set()
        for i, line in enumerate(env_lines):
            for key, value in env_updates.items():
                if line.startswith(f"{key}="):
                    env_lines[i] = f"{key}={value}\n"
                    updated_keys.add(key)
                    break
        
        # Add new configuration lines for keys that weren't found
        for key, value in env_updates.items():
            if key not in updated_keys:
                env_lines.append(f"{key}={value}\n")
        
        # Write updated .env file
        with open(env_path, 'w') as f:
            f.writelines(env_lines)
        
        return {
            "message": "Git configuration updated successfully",
            "config": git_config.dict()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update git config: {str(e)}")

@app.get("/api/issue-filters")
async def get_issue_filters():
    """Get current issue filtering configuration"""
    try:
        return {
            "issue_min_severity": config.issue_min_severity,
            "issue_environments": config.issue_environments,
            "issue_min_occurrences": config.issue_min_occurrences,
            "issue_max_age_days": config.issue_max_age_days
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get issue filters: {str(e)}")

@app.post("/api/issue-filters")
async def update_issue_filters(filter_config: IssueFilterRequest):
    """Update issue filtering configuration"""
    try:
        import os
        logging.info(f"Updating issue filters: {filter_config.dict()}")
        
        # Update the configuration values
        config.issue_min_severity = filter_config.issue_min_severity
        config.issue_environments = filter_config.issue_environments
        config.issue_min_occurrences = filter_config.issue_min_occurrences
        config.issue_max_age_days = filter_config.issue_max_age_days
        
        # Update .env file to persist changes
        env_path = ".env"
        env_updates = {
            "SENTRY_SOLVER_ISSUE_MIN_SEVERITY": filter_config.issue_min_severity,
            "SENTRY_SOLVER_ISSUE_ENVIRONMENTS": filter_config.issue_environments,
            "SENTRY_SOLVER_ISSUE_MIN_OCCURRENCES": str(filter_config.issue_min_occurrences),
            "SENTRY_SOLVER_ISSUE_MAX_AGE_DAYS": str(filter_config.issue_max_age_days)
        }
        
        # Read current .env file
        env_lines = []
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                env_lines = f.readlines()
        
        # Update or add configuration lines
        updated_keys = set()
        for i, line in enumerate(env_lines):
            for key, value in env_updates.items():
                if line.startswith(f"{key}="):
                    env_lines[i] = f"{key}={value}\n"
                    updated_keys.add(key)
                    break
        
        # Add new configuration lines for keys that weren't found
        for key, value in env_updates.items():
            if key not in updated_keys:
                env_lines.append(f"{key}={value}\n")
        
        # Write updated .env file
        with open(env_path, 'w') as f:
            f.writelines(env_lines)
        
        return {
            "message": "Issue filtering configuration updated successfully",
            "config": filter_config.dict()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update issue filters: {str(e)}")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

def main():
    setup_logging()
    print("🚀 Starting Sentry Solver API...")
    print("🌐 Web interface will be available at: http://localhost:8000")
    print("📚 API docs available at: http://localhost:8000/docs")
    
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()