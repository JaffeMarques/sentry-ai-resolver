import os
from typing import Optional
from pydantic_settings import BaseSettings

class Config(BaseSettings):
    sentry_auth_token: str
    sentry_project_slug: Optional[str] = None
    sentry_organization_slug: str
    
    check_interval_minutes: int = 30
    max_issues_per_run: int = 5
    
    # Issue Filtering Configuration
    issue_min_severity: str = "all"  # debug, info, warning, error, fatal
    issue_environments: str = "all"  # comma-separated list or "all"
    issue_min_occurrences: int = 1
    issue_max_age_days: int = 30
    
    # Git Configuration
    git_default_branch: str = "main"
    git_branch_prefix: str = "sentry-fix"
    git_include_timestamp: bool = True
    git_include_issue_id: bool = True
    commit_message_prefix: str = "fix"
    commit_message_format: str = "conventional"  # conventional, simple, detailed
    git_auto_push: bool = True
    git_create_pr: bool = False
    work_directory: Optional[str] = None
    
    log_level: str = "INFO"
    
    # Security Configuration
    enable_safety_checks: bool = True
    allow_config_file_fixes: bool = False
    allow_migration_fixes: bool = False
    allow_system_command_fixes: bool = False
    
    class Config:
        env_file = ".env"
        env_prefix = "SENTRY_SOLVER_"

config = Config()