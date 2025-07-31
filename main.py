#!/usr/bin/env python3

import time
import schedule
import logging
import sys
from datetime import datetime
from typing import List, Optional

from config import config
from sentry_client import SentryMCPClient, SentryIssue
from issue_analyzer import IssueAnalyzer, FixSuggestion
from git_manager import GitManager
from database import Database

class SentrySolver:
    def __init__(self, project_slug: Optional[str] = None):
        self.setup_logging()
        self.logger = logging.getLogger(__name__)
        
        self.project_slug = project_slug or config.sentry_project_slug
        self.work_directory = config.work_directory
        self.sentry_client = SentryMCPClient(project_slug=self.project_slug)
        self.issue_analyzer = IssueAnalyzer()
        self.git_manager = GitManager(work_directory=self.work_directory)
        self.db = Database()
        
        self.logger.info(f"SentrySolver initialized for project: {self.project_slug}")
    
    def setup_logging(self):
        logging.basicConfig(
            level=getattr(logging, config.log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('sentry_solver.log')
            ]
        )
    
    def run_cycle(self):
        """Execute one cycle of issue processing"""
        self.logger.info("Starting SentrySolver cycle")
        
        try:
            if not self.git_manager.is_repo_clean():
                self.logger.warning("Git repository is not clean, skipping cycle")
                return
            
            issues = self.sentry_client.get_issues(
                limit=config.max_issues_per_run,
                status="unresolved",
                min_severity=config.issue_min_severity,
                environments=config.issue_environments,
                min_occurrences=config.issue_min_occurrences,
                max_age_days=config.issue_max_age_days
            )
            
            if not issues:
                self.logger.info("No unresolved issues found")
                return
            
            self.logger.info(f"Found {len(issues)} unresolved issues")
            
            for issue in issues:
                try:
                    self.process_issue(issue)
                except Exception as e:
                    self.logger.error(f"Failed to process issue {issue.id}: {e}")
                    continue
            
            self.logger.info("SentrySolver cycle completed")
            
        except Exception as e:
            self.logger.error(f"Error during cycle execution: {e}")
    
    def process_issue(self, issue: SentryIssue):
        """Process a single Sentry issue"""
        self.logger.info(f"Processing issue {issue.id}: {issue.title}")
        
        detailed_issue = self.sentry_client.get_issue_details(issue.id)
        if not detailed_issue:
            self.logger.warning(f"Could not fetch details for issue {issue.id}")
            # Save issue with error
            self.db.save_issue({
                'id': issue.id,
                'project_slug': self.project_slug,
                'title': issue.title,
                'culprit': issue.culprit,
                'permalink': issue.permalink,
                'count': issue.count,
                'level': issue.level,
                'status': issue.status,
                'first_seen': issue.first_seen,
                'last_seen': issue.last_seen,
                'processed_at': datetime.now().isoformat(),
                'error_message': 'Could not fetch issue details'
            })
            return
        
        fix_suggestion = self.issue_analyzer.analyze_issue(detailed_issue)
        if not fix_suggestion:
            self.logger.info(f"No fix suggestion available for issue {issue.id}")
            # Save issue without fix
            self.db.save_issue({
                'id': detailed_issue.id,
                'project_slug': self.project_slug,
                'title': detailed_issue.title,
                'culprit': detailed_issue.culprit,
                'permalink': detailed_issue.permalink,
                'count': detailed_issue.count,
                'level': detailed_issue.level,
                'status': detailed_issue.status,
                'first_seen': detailed_issue.first_seen,
                'last_seen': detailed_issue.last_seen,
                'processed_at': datetime.now().isoformat(),
                'error_message': 'No fix suggestion available'
            })
            return
        
        if fix_suggestion.confidence < 0.6:
            self.logger.info(f"Fix confidence too low ({fix_suggestion.confidence:.1%}) for issue {issue.id}")
            # Save issue with low confidence
            self.db.save_issue({
                'id': detailed_issue.id,
                'project_slug': self.project_slug,
                'title': detailed_issue.title,
                'culprit': detailed_issue.culprit,
                'permalink': detailed_issue.permalink,
                'count': detailed_issue.count,
                'level': detailed_issue.level,
                'status': detailed_issue.status,
                'first_seen': detailed_issue.first_seen,
                'last_seen': detailed_issue.last_seen,
                'processed_at': datetime.now().isoformat(),
                'fix_confidence': fix_suggestion.confidence,
                'error_message': 'Fix confidence too low'
            })
            return
        
        self.logger.info(f"Applying fix for issue {issue.id} (confidence: {fix_suggestion.confidence:.1%})")
        
        branch_name = self.git_manager.create_fix_branch(detailed_issue)
        if not branch_name:
            self.logger.error(f"Failed to create branch for issue {issue.id}")
            return
        
        try:
            success = self.git_manager.apply_fix(fix_suggestion)
            if not success:
                self.logger.error(f"Failed to apply fix for issue {issue.id}")
                self.git_manager.cleanup_branch(branch_name)
                return
            
            success = self.git_manager.commit_fix(detailed_issue, fix_suggestion)
            if not success:
                self.logger.error(f"Failed to commit fix for issue {issue.id}")
                self.git_manager.cleanup_branch(branch_name)
                return
            
            success = self.git_manager.push_branch(branch_name)
            if not success:
                self.logger.error(f"Failed to push branch for issue {issue.id}")
                self.git_manager.cleanup_branch(branch_name)
                return
            
            title, body = self.git_manager.create_pull_request_info(
                detailed_issue, fix_suggestion, branch_name
            )
            
            # Save successful fix to database
            self.db.save_issue({
                'id': detailed_issue.id,
                'project_slug': self.project_slug,
                'title': detailed_issue.title,
                'culprit': detailed_issue.culprit,
                'permalink': detailed_issue.permalink,
                'count': detailed_issue.count,
                'level': detailed_issue.level,
                'status': detailed_issue.status,
                'first_seen': detailed_issue.first_seen,
                'last_seen': detailed_issue.last_seen,
                'processed_at': datetime.now().isoformat(),
                'fix_applied': True,
                'fix_confidence': fix_suggestion.confidence,
                'branch_name': branch_name,
                'resolved': fix_suggestion.confidence > 0.8
            })
            
            # Save fix details
            self.db.save_fix({
                'issue_id': detailed_issue.id,
                'file_path': fix_suggestion.file_path,
                'line_number': fix_suggestion.line_number,
                'original_code': fix_suggestion.original_code,
                'fixed_code': fix_suggestion.fixed_code,
                'explanation': fix_suggestion.explanation,
                'confidence': fix_suggestion.confidence
            })
            
            self.logger.info(f"Successfully processed issue {issue.id}")
            self.logger.info(f"PR Info - Title: {title[:50]}...")
            
            if fix_suggestion.confidence > 0.8:
                self.sentry_client.resolve_issue(issue.id)
                self.logger.info(f"Auto-resolved issue {issue.id} due to high confidence")
            
        except Exception as e:
            self.logger.error(f"Error processing issue {issue.id}: {e}")
            self.git_manager.cleanup_branch(branch_name)
    
    def start_scheduler(self):
        """Start the scheduled execution"""
        self.logger.info(f"Starting scheduler with {config.check_interval_minutes} minute intervals")
        
        schedule.every(config.check_interval_minutes).minutes.do(self.run_cycle)
        
        self.run_cycle()
        
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)
            except KeyboardInterrupt:
                self.logger.info("Received interrupt signal, stopping...")
                break
            except Exception as e:
                self.logger.error(f"Scheduler error: {e}")
                time.sleep(60)
    
    def run_once(self):
        """Run a single cycle and exit"""
        self.logger.info("Running single cycle")
        self.run_cycle()

def main():
    project_slug = None
    once_mode = False
    
    # Parse command line arguments
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--once":
            once_mode = True
        elif arg.startswith("--project="):
            project_slug = arg.split("=", 1)[1]
        elif arg == "--project" and i + 1 < len(sys.argv):
            project_slug = sys.argv[i + 1]
    
    solver = SentrySolver(project_slug=project_slug)
    
    if once_mode:
        solver.run_once()
    else:
        solver.start_scheduler()

if __name__ == "__main__":
    main()