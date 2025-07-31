import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
import json
import logging

class Database:
    def __init__(self, db_path: str = "sentry_solver.db"):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Sessions table - tracks solver sessions
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_slug TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'stopped',
                        started_at TIMESTAMP,
                        stopped_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Issues table - tracks processed issues
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS issues (
                        id TEXT PRIMARY KEY,
                        project_slug TEXT NOT NULL,
                        title TEXT NOT NULL,
                        culprit TEXT,
                        permalink TEXT,
                        count INTEGER DEFAULT 0,
                        level TEXT,
                        status TEXT,
                        first_seen TIMESTAMP,
                        last_seen TIMESTAMP,
                        processed_at TIMESTAMP,
                        fix_applied BOOLEAN DEFAULT FALSE,
                        fix_confidence REAL DEFAULT 0.0,
                        branch_name TEXT,
                        commit_hash TEXT,
                        resolved BOOLEAN DEFAULT FALSE,
                        error_message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Fixes table - tracks applied fixes
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fixes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        issue_id TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        line_number INTEGER,
                        original_code TEXT,
                        fixed_code TEXT NOT NULL,
                        explanation TEXT,
                        confidence REAL DEFAULT 0.0,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (issue_id) REFERENCES issues (id)
                    )
                """)
                
                conn.commit()
                self.logger.info("Database initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
    
    def create_session(self, project_slug: str) -> int:
        """Create a new solver session"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO sessions (project_slug, status, started_at)
                    VALUES (?, 'running', ?)
                """, (project_slug, datetime.now()))
                session_id = cursor.lastrowid
                conn.commit()
                return session_id
        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            return 0
    
    def update_session_status(self, session_id: int, status: str):
        """Update session status"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                stopped_at = datetime.now() if status == 'stopped' else None
                cursor.execute("""
                    UPDATE sessions 
                    SET status = ?, stopped_at = ?
                    WHERE id = ?
                """, (status, stopped_at, session_id))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to update session status: {e}")
    
    def get_active_session(self, project_slug: str) -> Optional[Dict[str, Any]]:
        """Get active session for project"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM sessions 
                    WHERE project_slug = ? AND status = 'running'
                    ORDER BY created_at DESC LIMIT 1
                """, (project_slug,))
                row = cursor.fetchone()
                if row:
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            self.logger.error(f"Failed to get active session: {e}")
            return None
    
    def save_issue(self, issue_data: Dict[str, Any]) -> bool:
        """Save or update issue data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO issues (
                        id, project_slug, title, culprit, permalink, count,
                        level, status, first_seen, last_seen, processed_at,
                        fix_applied, fix_confidence, branch_name, commit_hash,
                        resolved, error_message, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    issue_data.get('id'),
                    issue_data.get('project_slug'),
                    issue_data.get('title'),
                    issue_data.get('culprit'),
                    issue_data.get('permalink'),
                    issue_data.get('count', 0),
                    issue_data.get('level'),
                    issue_data.get('status'),
                    issue_data.get('first_seen'),
                    issue_data.get('last_seen'),
                    issue_data.get('processed_at'),
                    issue_data.get('fix_applied', False),
                    issue_data.get('fix_confidence', 0.0),
                    issue_data.get('branch_name'),
                    issue_data.get('commit_hash'),
                    issue_data.get('resolved', False),
                    issue_data.get('error_message'),
                    datetime.now()
                ))
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to save issue: {e}")
            return False
    
    def save_fix(self, fix_data: Dict[str, Any]) -> bool:
        """Save fix data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO fixes (
                        issue_id, file_path, line_number, original_code,
                        fixed_code, explanation, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    fix_data.get('issue_id'),
                    fix_data.get('file_path'),
                    fix_data.get('line_number'),
                    fix_data.get('original_code'),
                    fix_data.get('fixed_code'),
                    fix_data.get('explanation'),
                    fix_data.get('confidence', 0.0)
                ))
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to save fix: {e}")
            return False
    
    def get_issues(self, project_slug: str, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get issues for project"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = "SELECT * FROM issues WHERE project_slug = ?"
                params = [project_slug]
                
                if status:
                    query += " AND status = ?"
                    params.append(status)
                
                query += " ORDER BY processed_at DESC, created_at DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to get issues: {e}")
            return []
    
    def get_issue_stats(self, project_slug: str) -> Dict[str, int]:
        """Get issue statistics for project"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # Total issues
                cursor.execute("""
                    SELECT COUNT(*) FROM issues WHERE project_slug = ?
                """, (project_slug,))
                stats['total'] = cursor.fetchone()[0]
                
                # Fixed issues
                cursor.execute("""
                    SELECT COUNT(*) FROM issues 
                    WHERE project_slug = ? AND fix_applied = TRUE
                """, (project_slug,))
                stats['fixed'] = cursor.fetchone()[0]
                
                # Resolved issues
                cursor.execute("""
                    SELECT COUNT(*) FROM issues 
                    WHERE project_slug = ? AND resolved = TRUE
                """, (project_slug,))
                stats['resolved'] = cursor.fetchone()[0]
                
                # Pending issues
                cursor.execute("""
                    SELECT COUNT(*) FROM issues 
                    WHERE project_slug = ? AND fix_applied = FALSE AND resolved = FALSE
                """, (project_slug,))
                stats['pending'] = cursor.fetchone()[0]
                
                return stats
        except Exception as e:
            self.logger.error(f"Failed to get issue stats: {e}")
            return {'total': 0, 'fixed': 0, 'resolved': 0, 'pending': 0}
    
    def get_recent_fixes(self, project_slug: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent fixes for project"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT f.*, i.title, i.project_slug
                    FROM fixes f
                    JOIN issues i ON f.issue_id = i.id
                    WHERE i.project_slug = ?
                    ORDER BY f.applied_at DESC LIMIT ?
                """, (project_slug, limit))
                
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to get recent fixes: {e}")
            return []