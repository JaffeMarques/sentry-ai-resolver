import re
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

from sentry_client import SentryIssue
from config import config

@dataclass
class FixSuggestion:
    file_path: str
    line_number: int
    original_code: str
    fixed_code: str
    explanation: str
    confidence: float

class IssueAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Blacklist of dangerous commands and patterns that should never be suggested
        self.dangerous_patterns = [
            # Database operations
            'migration', 'migrate', 'schema', 'database', 'db:',
            'artisan migrate', 'php artisan', 'composer', 'npm run',
            'yarn', 'pnpm', 'drop table', 'truncate', 'delete from',
            'alter table', 'create table', 'update ', 'insert into',
            
            # System commands
            'exec', 'system', 'shell_exec', 'passthru', 'proc_open',
            'eval', 'assert', 'include', 'require', 'file_get_contents',
            'file_put_contents', 'unlink', 'rmdir', 'chmod', 'chown',
            
            # Network operations
            'curl', 'wget', 'http_get', 'http_post', 'fopen', 'fsockopen',
            'socket_create', 'mail', 'sendmail',
            
            # Other dangerous operations
            'serialize', 'unserialize', '$$', 'backticks', '`', 'shell',
            'cmd', 'command', 'process', 'subprocess'
        ]

    def _detect_language(self, stack_trace: Optional[str]) -> str:
        """Detect programming language based on stack trace contents"""
        if not stack_trace:
            return "unknown"

        stack_trace = stack_trace.lower()
        if ".php" in stack_trace:
            return "php"
        if ".py" in stack_trace:
            return "python"
        if ".js" in stack_trace:
            return "javascript"
        if ".java" in stack_trace:
            return "java"
        return "unknown"
    
    def analyze_issue(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        """Analyze issue using pattern-based analysis"""
        language = self._detect_language(issue.stack_trace)
        self.logger.info(f"Detected language {language} for issue {issue.id}")
        fix_suggestion = self._pattern_based_analysis(issue, language)
        
        if fix_suggestion:
            # Validate the fix suggestion for security
            if self._is_safe_fix(fix_suggestion):
                return fix_suggestion
            else:
                self.logger.warning(f"Rejected potentially dangerous fix for issue {issue.id}")
                return None
        
        return fix_suggestion
    
    def _basic_analysis(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        if not issue.stack_trace:
            return None
        
        common_fixes = {
            "AttributeError": self._fix_attribute_error,
            "KeyError": self._fix_key_error,
            "IndexError": self._fix_index_error,
            "TypeError": self._fix_type_error,
            "ValueError": self._fix_value_error,
            "ImportError": self._fix_import_error,
            "NameError": self._fix_name_error
        }
        
        error_type = self._extract_error_type(issue.title)
        if error_type in common_fixes:
            return common_fixes[error_type](issue)

        return None

    def _basic_analysis_js(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        """Basic analysis for common JavaScript errors"""
        if not issue.stack_trace:
            return None

        js_fixers = [
            self._fix_js_reference_error,
            self._fix_js_type_error,
            self._fix_js_property_error,
        ]

        for fixer in js_fixers:
            result = fixer(issue)
            if result:
                return result

        return None
    
    
    def _pattern_based_analysis(self, issue: SentryIssue, language: str) -> Optional[FixSuggestion]:
        """Pattern-based analysis using language detection"""
        title = issue.title.lower()

        if language == "php":
            if "google\\cloud\\core\\exception\\serviceexception" in title:
                return self._fix_gcp_service_exception(issue)
            if "google\\cloud\\core\\exception\\badrequestexception" in title:
                return self._fix_gcp_bad_request_exception(issue)
            if "carbon\\exceptions\\invalidformatexception" in title:
                return self._fix_carbon_date_exception(issue)
            return None

        if language == "javascript":
            if "cannot read property" in title:
                return self._fix_js_property_error(issue)
            if "is not a function" in title:
                return self._fix_js_type_error(issue)
            if "is not defined" in title:
                return self._fix_js_reference_error(issue)
            return self._basic_analysis_js(issue)

        # Default to Python-style analysis
        return self._basic_analysis(issue)
    
    def _fix_gcp_service_exception(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        """Fix Google Cloud Service Exception"""
        # Extract file path from stack trace
        file_path = self._extract_file_from_stacktrace(issue.stack_trace)
        line_number = self._extract_line_from_stacktrace(issue.stack_trace)
        
        # Convert Docker path to local path
        if file_path.startswith('/app/'):
            file_path = 'app/' + file_path[5:]
        
        # If we couldn't find the specific file, suggest a general approach
        if file_path == "unknown":
            self.logger.warning(f"Creating general fix suggestion for GCP Service Exception (issue {issue.id})")
            return FixSuggestion(
                file_path="app/Helpers/LogHelper.php",  # Common location for logging helpers
                line_number=0,  # Will create new method
                original_code="// Add GCP logging with error handling",
                fixed_code="""// GCP logging helper method
public static function safeGcpLog($level, $message, $context = [])
{
    try {
        if (config('logging.gcp.enabled', false)) {
            logs('gcp')->{$level}($message, $context);
        }
    } catch (\\Exception $e) {
        \\Log::{$level}('GCP logging failed: ' . $e->getMessage(), $context);
    }
}""",
                explanation="Creates a safe GCP logging helper to prevent service exceptions. Replace direct logs('gcp') calls with LogHelper::safeGcpLog()",
                confidence=0.7
            )
        
        return FixSuggestion(
            file_path=file_path,
            line_number=line_number,
            original_code="logs('gcp')->error($message, $context);",
            fixed_code="""try {
    if (config('logging.gcp.enabled', false)) {
        logs('gcp')->error($message, $context);
    }
} catch (\\Exception $e) {
    \\Log::error('GCP logging failed: ' . $e->getMessage(), $context);
}""",
            explanation="Wraps GCP logging in try-catch to handle service exceptions and adds configuration check",
            confidence=0.85
        )
    
    def _fix_gcp_bad_request_exception(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        """Fix Google Cloud Bad Request Exception"""
        file_path = self._extract_file_from_stacktrace(issue.stack_trace)
        line_number = self._extract_line_from_stacktrace(issue.stack_trace)
        
        if file_path.startswith('/app/'):
            file_path = 'app/' + file_path[5:]
        
        return FixSuggestion(
            file_path=file_path,
            line_number=line_number,
            original_code="logs('gcp')->info($data);",
            fixed_code="""try {
    // Sanitize data for GCP logging
    $sanitizedData = $this->sanitizeForGCP($data);
    logs('gcp')->info($sanitizedData);
} catch (\\Exception $e) {
    \\Log::info('GCP logging failed, using default logger', ['error' => $e->getMessage()]);
}""",
            explanation="Sanitizes data before sending to GCP and handles bad request exceptions",
            confidence=0.8
        )
    
    def _fix_carbon_date_exception(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        """Fix Carbon date parsing exceptions"""
        file_path = self._extract_file_from_stacktrace(issue.stack_trace) 
        line_number = self._extract_line_from_stacktrace(issue.stack_trace)
        
        if file_path.startswith('/app/'):
            file_path = 'app/' + file_path[5:]
        
        # If we couldn't find the specific file, suggest a general helper
        if file_path == "unknown":
            self.logger.warning(f"Creating general fix suggestion for Carbon InvalidFormat Exception (issue {issue.id})")
            return FixSuggestion(
                file_path="app/Helpers/DateHelper.php",
                line_number=0,
                original_code="// Add safe date parsing helper",
                fixed_code="""// Safe Carbon date parsing helper
public static function safeParse($dateString, $fallback = null)
{
    try {
        return Carbon::parse($dateString);
    } catch (\\Carbon\\Exceptions\\InvalidFormatException $e) {
        \\Log::warning('Invalid date format: ' . $dateString, ['exception' => $e->getMessage()]);
        return $fallback ?: Carbon::now();
    }
}""",
                explanation="Creates a safe date parsing helper to handle InvalidFormatException. Replace Carbon::parse() calls with DateHelper::safeParse()",
                confidence=0.8
            )
        
        return FixSuggestion(
            file_path=file_path,
            line_number=line_number,
            original_code="Carbon::parse($dateString);",
            fixed_code="""try {
    $date = Carbon::parse($dateString);
} catch (\\Carbon\\Exceptions\\InvalidFormatException $e) {
    \\Log::warning('Invalid date format: ' . $dateString);
    $date = Carbon::now(); // or appropriate default
}""",
            explanation="Adds proper exception handling for Carbon date parsing with fallback",
            confidence=0.9
        )
    
    
    def _extract_error_type(self, title: str) -> str:
        match = re.search(r'(\w+Error|\w+Exception)', title)
        return match.group(1) if match else ""
    
    def _fix_attribute_error(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        match = re.search(r"'(\w+)' object has no attribute '(\w+)'", issue.title)
        if not match:
            return None
        
        obj_type, attr_name = match.groups()
        
        return FixSuggestion(
            file_path=self._extract_file_from_stacktrace(issue.stack_trace),
            line_number=self._extract_line_from_stacktrace(issue.stack_trace),
            original_code=f"obj.{attr_name}",
            fixed_code=f"getattr(obj, '{attr_name}', None)",
            explanation=f"Use getattr to safely access the '{attr_name}' attribute",
            confidence=0.7
        )
    
    def _fix_key_error(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        match = re.search(r"KeyError: '(\w+)'", issue.title)
        if not match:
            return None
        
        key_name = match.group(1)
        
        return FixSuggestion(
            file_path=self._extract_file_from_stacktrace(issue.stack_trace),
            line_number=self._extract_line_from_stacktrace(issue.stack_trace),
            original_code=f"dict['{key_name}']",
            fixed_code=f"dict.get('{key_name}')",
            explanation=f"Use .get() method to safely access the '{key_name}' key",
            confidence=0.8
        )
    
    def _fix_index_error(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        return FixSuggestion(
            file_path=self._extract_file_from_stacktrace(issue.stack_trace),
            line_number=self._extract_line_from_stacktrace(issue.stack_trace),
            original_code="list[index]",
            fixed_code="list[index] if index < len(list) else None",
            explanation="Add bounds checking before accessing list index",
            confidence=0.6
        )
    
    def _fix_type_error(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        if "NoneType" in issue.title:
            return FixSuggestion(
                file_path=self._extract_file_from_stacktrace(issue.stack_trace),
                line_number=self._extract_line_from_stacktrace(issue.stack_trace),
                original_code="obj.method()",
                fixed_code="obj.method() if obj is not None else None",
                explanation="Add None check before method call",
                confidence=0.7
            )
        return None
    
    def _fix_value_error(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        return FixSuggestion(
            file_path=self._extract_file_from_stacktrace(issue.stack_trace),
            line_number=self._extract_line_from_stacktrace(issue.stack_trace),
            original_code="value = func()",
            fixed_code="try:\n    value = func()\nexcept ValueError:\n    value = default_value",
            explanation="Add try-catch block to handle ValueError",
            confidence=0.5
        )
    
    def _fix_import_error(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        match = re.search(r"No module named '(\w+)'", issue.title)
        if not match:
            return None
        
        module_name = match.group(1)
        
        return FixSuggestion(
            file_path=self._extract_file_from_stacktrace(issue.stack_trace),
            line_number=self._extract_line_from_stacktrace(issue.stack_trace),
            original_code=f"import {module_name}",
            fixed_code=f"try:\n    import {module_name}\nexcept ImportError:\n    {module_name} = None",
            explanation=f"Add fallback for missing '{module_name}' module",
            confidence=0.6
        )
    
    def _fix_name_error(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        match = re.search(r"name '(\w+)' is not defined", issue.title)
        if not match:
            return None
        
        var_name = match.group(1)
        
        return FixSuggestion(
            file_path=self._extract_file_from_stacktrace(issue.stack_trace),
            line_number=self._extract_line_from_stacktrace(issue.stack_trace),
            original_code=f"result = {var_name}",
            fixed_code=f"result = {var_name} if '{var_name}' in locals() else None",
            explanation=f"Add check for undefined variable '{var_name}'",
            confidence=0.4
        )

    def _fix_js_reference_error(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        match = re.search(r"ReferenceError: (\w+) is not defined", issue.title)
        if not match:
            return None

        var_name = match.group(1)

        return FixSuggestion(
            file_path=self._extract_file_from_stacktrace(issue.stack_trace),
            line_number=self._extract_line_from_stacktrace(issue.stack_trace),
            original_code=var_name,
            fixed_code=f"typeof {var_name} !== 'undefined' ? {var_name} : undefined",
            explanation=f"Check if '{var_name}' is defined before use",
            confidence=0.5,
        )

    def _fix_js_type_error(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        match = re.search(r"TypeError: (\w+) is not a function", issue.title)
        if not match:
            return None

        func_name = match.group(1)

        return FixSuggestion(
            file_path=self._extract_file_from_stacktrace(issue.stack_trace),
            line_number=self._extract_line_from_stacktrace(issue.stack_trace),
            original_code=f"{func_name}()",
            fixed_code=f"if (typeof {func_name} === 'function') {func_name}();",
            explanation=f"Ensure {func_name} is a function before calling",
            confidence=0.5,
        )

    def _fix_js_property_error(self, issue: SentryIssue) -> Optional[FixSuggestion]:
        match = re.search(r"Cannot read property '(\w+)' of undefined", issue.title)
        if not match:
            return None

        prop_name = match.group(1)

        return FixSuggestion(
            file_path=self._extract_file_from_stacktrace(issue.stack_trace),
            line_number=self._extract_line_from_stacktrace(issue.stack_trace),
            original_code=f"obj.{prop_name}",
            fixed_code=f"obj ? obj.{prop_name} : undefined",
            explanation=f"Check object before accessing '{prop_name}'",
            confidence=0.5,
        )
    
    def _extract_file_from_stacktrace(self, stack_trace: Optional[str]) -> str:
        if not stack_trace:
            self.logger.warning("No stack trace available for file extraction")
            return "unknown"
        
        self.logger.debug(f"Extracting file from stack trace: {stack_trace[:200]}...")
        
        # Try multiple patterns for different stack trace formats
        patterns = [
            # PHP stack trace patterns
            r'(/[^:\s]+\.php):\d+',  # /path/to/file.php:123
            r'in (/[^:\s]+\.php) on line \d+',  # in /path/to/file.php on line 123
            r'(/app/[^:\s]+\.php)',  # Docker path
            # Python patterns  
            r'File "([^"]+)"',  # File "/path/to/file.py"
            r'File \'([^\']+)\'',  # File '/path/to/file.py'
            # JavaScript patterns
            r'at .* \(([^)]+):\d+:\d+\)',  # at function (file.js:123:45)
            r'at ([^:\s]+):\d+:\d+',  # at file.js:123:45
            # Generic patterns
            r'([^:\s]+\.[a-zA-Z]{2,4}):\d+',  # file.ext:123
        ]
        
        for pattern in patterns:
            match = re.search(pattern, stack_trace)
            if match:
                file_path = match.group(1)
                self.logger.info(f"Extracted file path: {file_path}")
                return file_path
        
        # If no pattern matches, log the stack trace for debugging
        self.logger.warning(f"Could not extract file path from stack trace. Stack trace sample: {stack_trace[:500]}")
        return "unknown"
    
    def _extract_line_from_stacktrace(self, stack_trace: Optional[str]) -> int:
        if not stack_trace:
            return 0
        
        # Try multiple patterns for line number extraction
        patterns = [
            r'line (\d+)',  # "on line 123"
            r':(\d+):\d+',  # file.js:123:45
            r'\.php:(\d+)',  # file.php:123
            r'\.py:(\d+)',  # file.py:123
            r'\.js:(\d+)',  # file.js:123
        ]
        
        for pattern in patterns:
            match = re.search(pattern, stack_trace)
            if match:
                line_number = int(match.group(1))
                self.logger.debug(f"Extracted line number: {line_number}")
                return line_number
        
        self.logger.debug("Could not extract line number from stack trace")
        return 0
    
    def _is_safe_fix(self, fix: FixSuggestion) -> bool:
        """Validate that a fix suggestion doesn't contain dangerous patterns"""
        
        # Skip safety checks if disabled in config
        if not config.enable_safety_checks:
            return True
            
        code_to_check = f"{fix.fixed_code} {fix.explanation}".lower()
        
        for dangerous_pattern in self.dangerous_patterns:
            if dangerous_pattern.lower() in code_to_check:
                # Check if specific patterns are allowed by configuration
                if 'migration' in dangerous_pattern and config.allow_migration_fixes:
                    continue
                if any(cmd in dangerous_pattern for cmd in ['exec', 'system', 'shell']) and config.allow_system_command_fixes:
                    continue
                    
                self.logger.warning(f"Dangerous pattern '{dangerous_pattern}' found in fix suggestion")
                return False
        
        # Additional checks for specific dangerous constructs
        dangerous_constructs = [
            '<?php', '<?=',  # PHP opening tags (shouldn't be in fixes)
            'rm -', 'sudo', 'chmod +x',  # System commands
            'DROP ', 'TRUNCATE ', 'DELETE FROM ',  # SQL operations
            '__construct', '__destruct', '__call',  # PHP magic methods that could be dangerous
        ]
        
        for construct in dangerous_constructs:
            if construct.lower() in code_to_check:
                self.logger.warning(f"Dangerous construct '{construct}' found in fix suggestion")
                return False
        
        # Check for code injection patterns
        injection_patterns = [
            '${', '$_GET', '$_POST', '$_REQUEST', '$_COOKIE',  # PHP superglobals
            'eval(', 'exec(', 'system(',  # Direct execution functions
            '`', 'shell_exec(',  # Command execution
        ]
        
        for pattern in injection_patterns:
            if pattern in fix.fixed_code:
                self.logger.warning(f"Potential code injection pattern '{pattern}' found in fix")
                return False
        
        return True