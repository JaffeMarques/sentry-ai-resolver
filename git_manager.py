import os
import logging
from git import Repo
from git.exc import GitCommandError
from typing import Optional, Tuple
from datetime import datetime

from config import config
from issue_analyzer import FixSuggestion
from sentry_client import SentryIssue

class GitManager:
    def __init__(self, repo_path: str = ".", work_directory: Optional[str] = None):
        self.repo_path = work_directory or repo_path
        self.work_directory = work_directory
        self.logger = logging.getLogger(__name__)
        self.repo = None
        
        try:
            self.repo = Repo(self.repo_path)
            self.logger.info(f"Git repository initialized at: {self.repo_path}")
        except Exception as e:
            self.logger.error(f"Failed to initialize Git repo at {self.repo_path}: {e}")
            self.logger.info("You can set a custom work directory via SENTRY_SOLVER_WORK_DIRECTORY or the web interface")
    
    def create_fix_branch(self, issue: SentryIssue) -> Optional[str]:
        if not self.repo:
            return None
        
        try:
            branch_name = self._generate_branch_name(issue)
            
            self.repo.git.checkout(config.git_default_branch)
            self.repo.git.pull("origin", config.git_default_branch)
            
            new_branch = self.repo.create_head(branch_name)
            new_branch.checkout()
            
            self.logger.info(f"Created and switched to branch: {branch_name}")
            return branch_name
        except GitCommandError as e:
            self.logger.error(f"Failed to create branch for issue {issue.id}: {e}")
            return None
    
    def _generate_branch_name(self, issue: SentryIssue) -> str:
        """Generate branch name based on configuration"""
        parts = [config.git_branch_prefix]
        
        if config.git_include_issue_id:
            parts.append(str(issue.id))
        
        # Add a simplified error type for better branch names
        error_type = self._extract_clean_error_title(issue.title).split(':')[0]
        # Sanitize for git branch name (no spaces, special chars)
        clean_error = ''.join(c for c in error_type if c.isalnum() or c in '-_').lower()
        if clean_error and len(clean_error) > 3:
            parts.append(clean_error[:20])  # Limit length
        
        if config.git_include_timestamp:
            parts.append(datetime.now().strftime('%Y%m%d-%H%M%S'))
        
        return '-'.join(parts)
    
    def apply_fix(self, fix: FixSuggestion) -> bool:
        if not self.repo:
            return False
        
        # Additional safety check before applying any fix
        if not self._is_safe_to_apply(fix):
            self.logger.error(f"Refusing to apply potentially dangerous fix to {fix.file_path}")
            return False
        
        try:
            # Handle both absolute and relative paths correctly
            if os.path.isabs(fix.file_path):
                # If it's an absolute path, try to make it relative to the repo
                file_path = fix.file_path
                # Try to find the file relative to repo root
                relative_path = None
                
                # Common patterns for Docker/container paths
                if file_path.startswith('/app/'):
                    relative_path = file_path[5:]  # Remove /app/ prefix
                elif file_path.startswith('/public/'):
                    relative_path = 'public' + file_path[7:]  # Convert /public/... to public/...
                elif file_path.startswith('/'):
                    relative_path = file_path[1:]  # Remove leading slash
                
                if relative_path:
                    test_path = os.path.join(self.repo_path, relative_path)
                    if os.path.exists(test_path):
                        file_path = test_path
                    else:
                        # Still use the original path construction
                        file_path = os.path.join(self.repo_path, fix.file_path)
                else:
                    file_path = os.path.join(self.repo_path, fix.file_path)
            else:
                # Relative path - join with repo path
                file_path = os.path.join(self.repo_path, fix.file_path)
            
            # Ensure the file path is within the work directory (only for relative paths)
            file_path = os.path.abspath(file_path)
            repo_abs_path = os.path.abspath(self.repo_path)
            
            # Only validate if the original path was relative or we successfully converted it
            if not os.path.isabs(fix.file_path) or file_path.startswith(repo_abs_path):
                if not file_path.startswith(repo_abs_path):
                    self.logger.warning(f"File path {file_path} is outside repository {repo_abs_path}")
                    return False
            else:
                self.logger.warning(f"Could not locate file {fix.file_path} within repository {repo_abs_path}")
                return False
            
            if not os.path.exists(file_path):
                self.logger.warning(f"File not found: {file_path}")
                return False
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.splitlines()
            
            success = self._apply_intelligent_fix(lines, fix, file_path)
            if success:
                updated_content = '\n'.join(lines)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                
                self.logger.info(f"Applied fix to {file_path}:{fix.line_number}")
                return True
            else:
                self.logger.warning(f"Failed to apply fix to {file_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to apply fix to {fix.file_path}: {e}")
            return False
    
    def commit_fix(self, issue: SentryIssue, fix: FixSuggestion) -> bool:
        if not self.repo:
            return False
        
        try:
            # Convert absolute path to relative path for git operations
            relative_path = self._get_relative_path_for_git(fix.file_path)
            self.repo.git.add(relative_path)
            
            commit_message = self._generate_commit_message(issue, fix)
            
            self.repo.index.commit(commit_message)
            
            self.logger.info(f"Committed fix for issue {issue.id}")
            return True
        except GitCommandError as e:
            self.logger.error(f"Failed to commit fix for issue {issue.id}: {e}")
            return False
    
    def push_branch(self, branch_name: str) -> bool:
        if not self.repo:
            return False
        
        if not config.git_auto_push:
            self.logger.info(f"Auto-push disabled, skipping push of branch {branch_name}")
            return True
        
        try:
            origin = self.repo.remote('origin')
            origin.push(branch_name)
            
            self.logger.info(f"Pushed branch {branch_name} to origin")
            return True
        except GitCommandError as e:
            self.logger.error(f"Failed to push branch {branch_name}: {e}")
            return False
    
    def create_pull_request_info(self, issue: SentryIssue, fix: FixSuggestion, branch_name: str) -> Tuple[str, str]:
        title = f"Fix Sentry Issue: {issue.title}"
        
        body = f"""
## 🔧 Auto-generated Fix for Sentry Issue

**Issue ID:** {issue.id}
**Issue Title:** {issue.title}
**Error Level:** {issue.level}
**Occurrences:** {issue.count}

### 📋 Issue Details
- **Culprit:** {issue.culprit}
- **First Seen:** {issue.first_seen}
- **Last Seen:** {issue.last_seen}
- **Status:** {issue.status}

### 🔗 Links
- [View Issue in Sentry]({issue.permalink})

### 🛠️ Fix Applied
**File:** `{fix.file_path}`
**Line:** {fix.line_number}
**Confidence:** {fix.confidence:.1%}

**Explanation:** {fix.explanation}

### 💡 Code Changes
```python
# Before
{fix.original_code}

# After  
{fix.fixed_code}
```

### ⚠️ Important Notes
- This fix was automatically generated based on the Sentry error data
- Please review the changes carefully before merging
- Consider adding tests to prevent regression
- Monitor the issue in Sentry after deployment

---
*Generated by Sentry Solver - Automated Issue Resolution*
"""
        
        return title, body
    
    def _generate_commit_message(self, issue: SentryIssue, fix: FixSuggestion) -> str:
        """Generate commit message based on configured format"""
        clean_title = self._extract_clean_error_title(issue.title)
        file_name = fix.file_path.split('/')[-1] if fix.file_path != "unknown" else "unknown file"
        
        if config.commit_message_format == "simple":
            return self._generate_simple_commit(clean_title, file_name)
        elif config.commit_message_format == "detailed":
            return self._generate_detailed_commit(issue, fix, clean_title, file_name)
        else:  # conventional (default)
            return self._generate_conventional_commit(issue, fix, clean_title, file_name)
    
    def _generate_simple_commit(self, clean_title: str, file_name: str) -> str:
        """Generate simple commit message"""
        commit_title = f"{config.commit_message_prefix}: {clean_title} in {file_name}"
        if len(commit_title) > 72:
            commit_title = commit_title[:69] + "..."
        return commit_title
    
    def _generate_conventional_commit(self, issue: SentryIssue, fix: FixSuggestion, clean_title: str, file_name: str) -> str:
        """Generate conventional commit message"""
        commit_title = f"{config.commit_message_prefix}: {clean_title} in {file_name}"
        if len(commit_title) > 72:
            commit_title = commit_title[:69] + "..."
        
        commit_message = f"""{commit_title}

- Fixed {issue.level} error in {fix.file_path}:{fix.line_number}
- Issue ID: {issue.id}
- Occurrences: {issue.count}
- Confidence: {fix.confidence:.1%}

Sentry Issue: {issue.permalink}"""
        
        return commit_message
    
    def _generate_detailed_commit(self, issue: SentryIssue, fix: FixSuggestion, clean_title: str, file_name: str) -> str:
        """Generate detailed commit message with full explanation"""
        commit_title = f"{config.commit_message_prefix}: {clean_title} in {file_name}"
        if len(commit_title) > 72:
            commit_title = commit_title[:69] + "..."
        
        commit_message = f"""{commit_title}

- Fixed {issue.level} error in {fix.file_path}:{fix.line_number}
- Issue ID: {issue.id}
- Occurrences: {issue.count}
- Confidence: {fix.confidence:.1%}

## Fix Details
{fix.explanation}

## Code Changes
Original:
{fix.original_code}

Fixed:
{fix.fixed_code}

Sentry Issue: {issue.permalink}"""
        
        return commit_message
    
    def _extract_clean_error_title(self, title: str) -> str:
        """Extract a clean, concise error title from Sentry error title"""
        # Remove namespace prefixes and get the actual error type
        if '\\' in title:
            # Extract the last part of the exception class name
            parts = title.split('\\')
            error_type = parts[-1].split(':')[0].strip()
            
            # Get additional context if available, but clean it up
            if ':' in title:
                context = title.split(':', 1)[1].strip()
                context = self._clean_error_context(context)
                if context:
                    return f"{error_type}: {context}"
                else:
                    return error_type
            else:
                return error_type
        else:
            # Handle non-namespaced errors
            if ':' in title:
                error_part = title.split(':', 1)[0].strip()
                context = title.split(':', 1)[1].strip()
                context = self._clean_error_context(context)
                if context:
                    return f"{error_part}: {context}"
                else:
                    return error_part
            else:
                # Just return the title truncated if needed
                return title[:40] + "..." if len(title) > 40 else title
    
    def _clean_error_context(self, context: str) -> str:
        """Clean up error context to make it more readable"""
        context = context.strip()
        
        # Skip contexts that are just JSON fragments or meaningless
        if context in ['{', '}', '{}', '[]', '""', "''"]:
            return ""
        
        # If it starts with { and looks like incomplete JSON, skip it
        if context.startswith('{') and not context.endswith('}'):
            return ""
        
        # If it's a very long JSON object, summarize it
        if context.startswith('{') and len(context) > 50:
            return "malformed request data"
        
        # Clean up common patterns
        context = context.replace('\n', ' ').replace('\r', ' ')
        context = ' '.join(context.split())  # Normalize whitespace
        
        # Limit length for commit messages
        if len(context) > 30:
            context = context[:27] + "..."
        
        return context
    
    def cleanup_branch(self, branch_name: str) -> bool:
        if not self.repo:
            return False
        
        try:
            self.repo.git.checkout(config.git_default_branch)
            
            self.repo.delete_head(branch_name, force=True)
            
            self.logger.info(f"Cleaned up branch: {branch_name}")
            return True
        except GitCommandError as e:
            self.logger.error(f"Failed to cleanup branch {branch_name}: {e}")
            return False
    
    def is_repo_clean(self) -> bool:
        if not self.repo:
            return False
        
        return not self.repo.is_dirty() and not self.repo.untracked_files
    
    def get_current_branch(self) -> str:
        if not self.repo:
            return "unknown"
        
        return self.repo.active_branch.name
    
    def _get_relative_path_for_git(self, file_path: str) -> str:
        """Convert file path to relative path for git operations"""
        if os.path.isabs(file_path):
            # If it's an absolute path, convert to relative
            if file_path.startswith('/app/'):
                return file_path[5:]  # Remove /app/ prefix
            elif file_path.startswith('/public/'):
                return 'public' + file_path[7:]  # Convert /public/... to public/...
            elif file_path.startswith('/'):
                return file_path[1:]  # Remove leading slash
        
        return file_path
    
    def _apply_intelligent_fix(self, lines, fix, file_path):
        """Apply fix with intelligent code replacement and indentation handling"""
        if not fix.line_number or fix.line_number <= 0 or fix.line_number > len(lines):
            self.logger.warning(f"Invalid line number {fix.line_number} for file {file_path}")
            return False
        
        target_line_idx = fix.line_number - 1
        
        # Try to find the exact original code in the file
        if fix.original_code and fix.original_code.strip():
            success = self._replace_original_code(lines, fix, target_line_idx)
            if success:
                return True
        
        # If no original code or replacement failed, try context-based insertion
        return self._context_based_insertion(lines, fix, target_line_idx)
    
    def _replace_original_code(self, lines, fix, target_line_idx):
        """Replace original code with fixed code, preserving indentation"""
        original_lines = fix.original_code.strip().split('\n')
        fixed_lines = fix.fixed_code.strip().split('\n')
        
        # Look for the original code around the target line
        search_range = 10  # Search 10 lines above and below
        start_search = max(0, target_line_idx - search_range)
        end_search = min(len(lines), target_line_idx + search_range)
        
        for i in range(start_search, end_search):
            if self._matches_original_code(lines, i, original_lines):
                # Found match, replace with fixed code
                self._replace_code_block(lines, i, original_lines, fixed_lines)
                self.logger.info(f"Replaced original code at line {i + 1}")
                return True
        
        return False
    
    def _matches_original_code(self, lines, start_idx, original_lines):
        """Check if the original code matches at the given position"""
        if start_idx + len(original_lines) > len(lines):
            return False
        
        for i, orig_line in enumerate(original_lines):
            if orig_line.strip() not in lines[start_idx + i].strip():
                return False
        
        return True
    
    def _replace_code_block(self, lines, start_idx, original_lines, fixed_lines):
        """Replace a block of code with proper indentation"""
        # Get the indentation from the first line
        if start_idx < len(lines):
            base_indentation = lines[start_idx][:len(lines[start_idx]) - len(lines[start_idx].lstrip())]
        else:
            base_indentation = ''
        
        # Remove original lines
        for _ in range(len(original_lines)):
            if start_idx < len(lines):
                lines.pop(start_idx)
        
        # Insert fixed lines with proper hierarchical indentation
        for i, fixed_line in enumerate(fixed_lines):
            if fixed_line.strip():  # Don't process empty lines
                indented_line = self._apply_hierarchical_indentation(fixed_line, base_indentation)
            else:
                indented_line = fixed_line
            lines.insert(start_idx + i, indented_line)
    
    def _context_based_insertion(self, lines, fix, target_line_idx):
        """Insert code based on context when original code is not found"""
        if target_line_idx >= len(lines):
            return False
        
        # Get indentation from target line or surrounding lines
        indentation = self._get_appropriate_indentation(lines, target_line_idx)
        
        # Prepare fixed code with proper hierarchical indentation
        fixed_lines = fix.fixed_code.strip().split('\n')
        indented_fixed_lines = []
        
        for line in fixed_lines:
            if line.strip():  # Don't process empty lines
                indented_line = self._apply_hierarchical_indentation(line, indentation)
                indented_fixed_lines.append(indented_line)
            else:
                indented_fixed_lines.append(line)
        
        # Insert the fixed code at the target line
        for i, fixed_line in enumerate(indented_fixed_lines):
            lines.insert(target_line_idx + i, fixed_line)
        
        self.logger.info(f"Inserted fix code at line {target_line_idx + 1} with proper indentation")
        return True
    
    def _get_appropriate_indentation(self, lines, target_line_idx):
        """Get appropriate indentation for the context"""
        # Try to get indentation from target line
        if target_line_idx < len(lines):
            line = lines[target_line_idx]
            if line.strip():
                return line[:len(line) - len(line.lstrip())]
        
        # Look at surrounding lines for indentation
        for offset in [-1, 1, -2, 2]:
            check_idx = target_line_idx + offset
            if 0 <= check_idx < len(lines):
                line = lines[check_idx]
                if line.strip():
                    return line[:len(line) - len(line.lstrip())]
        
        # Default to 4 spaces if no indentation found
        return '    '
    
    def _apply_hierarchical_indentation(self, line, base_indentation):
        """Apply proper hierarchical indentation to a line of code"""
        stripped_line = line.strip()
        
        # Get the original indentation level from the line
        original_line_indent = len(line) - len(line.lstrip())
        
        # Determine additional indentation based on the line content
        indent_unit = '    '  # 4 spaces
        
        # Calculate relative indentation based on original structure
        if original_line_indent > 0:
            # Preserve the relative indentation from the original code
            relative_indent_level = original_line_indent // 4  # Assuming 4-space indents
            additional_indent = indent_unit * relative_indent_level
        else:
            additional_indent = ''
        
        # Apply base indentation + relative indentation
        return base_indentation + additional_indent + stripped_line
    
    def _is_safe_to_apply(self, fix: FixSuggestion) -> bool:
        """Additional safety check to prevent dangerous operations"""
        
        # Skip safety checks if disabled in config
        if not config.enable_safety_checks:
            return True
        
        # Block fixes that contain dangerous file operations
        dangerous_file_patterns = [
            '.env', 'config.php', 'database.php', '.htaccess',
            'composer.json', 'package.json', 'artisan', 'web.config'
        ]
        
        for pattern in dangerous_file_patterns:
            if pattern in fix.file_path.lower():
                if not config.allow_config_file_fixes:
                    self.logger.warning(f"Blocking fix to sensitive file: {fix.file_path}")
                    return False
        
        # Block fixes that contain command execution
        dangerous_code_patterns = [
            'artisan migrate', 'composer install', 'npm install',
            'php artisan', 'shell_exec', 'exec(', 'system(',
            'proc_open', 'passthru', '`', 'eval(',
            'migration', 'schema', 'database'
        ]
        
        code_content = f"{fix.original_code} {fix.fixed_code}".lower()
        for pattern in dangerous_code_patterns:
            if pattern in code_content:
                # Check configuration overrides
                if ('migration' in pattern or 'schema' in pattern) and config.allow_migration_fixes:
                    continue
                if any(cmd in pattern for cmd in ['exec', 'system', 'shell_exec']) and config.allow_system_command_fixes:
                    continue
                    
                self.logger.warning(f"Blocking potentially dangerous code pattern: {pattern}")
                return False
        
        # Block fixes to files outside typical source directories
        safe_directories = [
            'app/', 'src/', 'lib/', 'includes/', 'classes/',
            'controllers/', 'models/', 'views/', 'helpers/',
            'services/', 'repositories/', 'middleware/',
            'public/', 'resources/', 'routes/', 'config/',
            'bootstrap/', 'database/', 'tests/'
        ]
        
        # Block vendor files completely - they should never be modified
        if '/vendor/' in fix.file_path or fix.file_path.startswith('vendor/'):
            self.logger.warning(f"Blocking fix to vendor file (should not be modified): {fix.file_path}")
            return False
        
        # Allow if it's in a safe directory or if it's a general helper suggestion
        if fix.line_number == 0:  # General helper methods are usually OK
            return True
            
        file_path_lower = fix.file_path.lower()
        is_in_safe_directory = any(safe_dir in file_path_lower for safe_dir in safe_directories)
        
        if not is_in_safe_directory:
            self.logger.warning(f"Blocking fix outside safe directories: {fix.file_path}")
            return False
        
        return True