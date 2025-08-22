import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

@dataclass
class SentryIssue:
    id: str
    title: str
    culprit: str
    permalink: str
    count: int
    level: str
    status: str
    first_seen: str
    last_seen: str
    stack_trace: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class SentryMCPClient:
    def __init__(self, config_path: str = "sentry-mcp-config.json", project_slug: Optional[str] = None):
        self.config_path = config_path
        self.project_slug = project_slug or "ms-leads"
        self.logger = logging.getLogger(__name__)
        
        from config import config
        # Server parameters for MCP connection
        self.server_params = StdioServerParameters(
            command="mcp-sentry",
            args=[
                "--auth-token", config.sentry_auth_token,
                "--project-slug", self.project_slug,
                "--organization-slug", config.sentry_organization_slug
            ]
        )
    
    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call an MCP tool and return the text response"""
        try:
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    
                    # Extract text content from the response
                    response_text = ""
                    for content in result.content:
                        if hasattr(content, 'text'):
                            response_text += content.text
                        else:
                            response_text += str(content)
                    
                    return response_text
        except Exception as e:
            self.logger.error(f"MCP tool call failed: {e}")
            raise
    
    def _run_async(self, coro):
        """Helper to run async functions from sync methods"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(coro)
    
    def get_issues(self, limit: int = 10, status: str = "unresolved", 
                   min_severity: str = None, environments: str = None, 
                   min_occurrences: int = None, max_age_days: int = None) -> List[SentryIssue]:
        """Get a list of Sentry issues with filtering options"""
        
        # Build query with filters
        query_parts = [f"is:{status}"]
        
        # Add severity filter
        if min_severity and min_severity != "all":
            severity_levels = ["debug", "info", "warning", "error", "fatal"]
            if min_severity in severity_levels:
                min_index = severity_levels.index(min_severity)
                allowed_levels = severity_levels[min_index:]
                if len(allowed_levels) == 1:
                    query_parts.append(f"level:{min_severity}")
                else:
                    level_query = " OR ".join([f"level:{level}" for level in allowed_levels])
                    query_parts.append(f"({level_query})")
        
        # Add environment filter
        if environments and environments.lower() != "all":
            env_list = [env.strip() for env in environments.split(",")]
            if len(env_list) == 1:
                query_parts.append(f"environment:{env_list[0]}")
            else:
                env_query = " OR ".join([f"environment:{env}" for env in env_list])
                query_parts.append(f"({env_query})")
        
        # Add minimum occurrences filter
        if min_occurrences and min_occurrences > 1:
            query_parts.append(f"times_seen:>={min_occurrences}")
        
        # Add age filter (last seen within X days)
        if max_age_days:
            query_parts.append(f"lastSeen:-{max_age_days}d")
        
        final_query = " ".join(query_parts)
        
        arguments = {
            "query": final_query,
            "limit": limit
        }
        
        try:
            response_text = self._run_async(self._call_mcp_tool("get_list_issues", arguments))
            return self._parse_issues_from_text(response_text)
        except Exception as e:
            self.logger.error(f"Failed to fetch issues: {e}")
            return []
    
    def get_issue_details(self, issue_id: str) -> Optional[SentryIssue]:
        """Get detailed information about a specific issue"""
        arguments = {"issue_id_or_url": issue_id}
        
        try:
            response_text = self._run_async(self._call_mcp_tool("get_sentry_issue", arguments))
            issues = self._parse_issues_from_text(response_text, include_stack_trace=True)
            return issues[0] if issues else None
        except Exception as e:
            self.logger.error(f"Failed to fetch issue details for {issue_id}: {e}")
            return None
    
    def _parse_issues_from_text(self, text: str, include_stack_trace: bool = False) -> List[SentryIssue]:
        """Parse issues from the MCP response text"""
        issues = []
        
        # Split the text by issue separators
        issue_blocks = text.split("Sentry Issue:")
        
        for block in issue_blocks[1:]:  # Skip the first empty block
            try:
                issue = self._parse_single_issue(block, include_stack_trace)
                if issue:
                    issues.append(issue)
            except Exception as e:
                self.logger.warning(f"Failed to parse issue block: {e}")
                continue
        
        return issues
    
    def _parse_single_issue(self, block: str, include_stack_trace: bool = False) -> Optional[SentryIssue]:
        """Parse a single issue from a text block"""
        lines = block.strip().split('\n')
        
        if not lines:
            return None
        
        # Parse the title (first line)
        title = lines[0].strip()
        
        # Initialize default values
        issue_id = ""
        status = "unknown"
        level = "unknown"
        first_seen = ""
        last_seen = ""
        count = 0
        culprit = ""
        permalink = ""
        stack_trace = None
        
        # Parse other fields
        for line in lines[1:]:
            line = line.strip()
            if line.startswith("Issue ID:"):
                issue_id = line.split(":", 1)[1].strip()
            elif line.startswith("Status:"):
                status = line.split(":", 1)[1].strip()
            elif line.startswith("Level:"):
                level = line.split(":", 1)[1].strip()
            elif line.startswith("First Seen:"):
                first_seen = line.split(":", 1)[1].strip()
            elif line.startswith("Last Seen:"):
                last_seen = line.split(":", 1)[1].strip()
            elif line.startswith("Event Count:"):
                try:
                    count = int(line.split(":", 1)[1].strip())
                except ValueError:
                    count = 0
        
        # Generate permalink
        if issue_id:
            permalink = f"https://movida-rent.sentry.io/issues/{issue_id}/"
        
        # Extract stack trace if available and requested
        if include_stack_trace and "Stacktrace:" in block:
            stack_trace_start = block.find("Stacktrace:")
            if stack_trace_start != -1:
                stack_trace = block[stack_trace_start + len("Stacktrace:"):].strip()
        
        # Use title as culprit if no specific culprit is found
        culprit = title.split(":")[0] if ":" in title else title
        
        if not issue_id:
            return None
        
        return SentryIssue(
            id=issue_id,
            title=title,
            culprit=culprit,
            permalink=permalink,
            count=count,
            level=level,
            status=status,
            first_seen=first_seen,
            last_seen=last_seen,
            stack_trace=stack_trace,
            context={}
        )
    
    def resolve_issue(self, issue_id: str) -> bool:
        """Mark an issue as resolved (not implemented in current MCP server)"""
        self.logger.warning("resolve_issue not implemented in current MCP server")
        return False
    
    def get_projects(self) -> List[Dict[str, str]]:
        """Get available projects from Sentry API"""
        projects = []
        
        try:
            import requests
            
            # Use Sentry REST API to get projects
            from config import config
            auth_token = config.sentry_auth_token
            org_slug = config.sentry_organization_slug
            
            url = f"https://sentry.io/api/0/organizations/{org_slug}/projects/"
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            }
            
            # Fetch all pages of projects
            page_num = 1
            current_url = url
            all_projects_data = []
            
            while current_url and page_num <= 10:  # Limit to 10 pages as safety
                self.logger.info(f"Fetching page {page_num} from Sentry API: {current_url}")
                response = requests.get(current_url, headers=headers, timeout=15)
                
                if response.status_code != 200:
                    break
                    
                page_projects = response.json()
                all_projects_data.extend(page_projects)
                self.logger.info(f"Page {page_num} returned {len(page_projects)} projects")
                
                # Check for next page
                link_header = response.headers.get('Link', '')
                next_url = None
                
                if 'rel="next"' in link_header:
                    import re
                    next_match = re.search(r'<([^>]+)>; rel="next"', link_header)
                    if next_match:
                        next_url = next_match.group(1)
                
                current_url = next_url
                page_num += 1
            
            if response.status_code == 200:
                self.logger.info(f"API returned {len(all_projects_data)} total projects across {page_num-1} pages")
                
                for project in all_projects_data:
                    # Include all projects (status field is often None/null in Sentry API)
                    # Skip projects with empty or None slug
                    if project.get("slug"):
                        projects.append({
                            "name": project.get("name", project.get("slug", "Unknown")),
                            "slug": project.get("slug", ""),
                            "id": str(project.get("id", "")),
                            "platform": project.get("platform", ""),
                            "status": project.get("status", "active")  # Default to active if not set
                        })
                
                self.logger.info(f"Successfully fetched {len(projects)} projects from Sentry API")
                
            elif response.status_code == 401:
                self.logger.error("Unauthorized access to Sentry API - check auth token")
                raise Exception("Unauthorized - check Sentry auth token")
            elif response.status_code == 403:
                self.logger.error("Forbidden access to Sentry API - check permissions")
                raise Exception("Forbidden - check Sentry organization permissions")
            else:
                self.logger.warning(f"Sentry API returned status {response.status_code}: {response.text}")
                raise Exception(f"API call failed with status {response.status_code}")
                
        except ImportError:
            self.logger.warning("requests library not available, using fallback project list")
        except Exception as e:
            self.logger.error(f"Failed to fetch projects from Sentry API: {e}")
        
        # If we got projects from API, try to add known missing ones
        if projects:
            known_projects = ['ms-leads', 'movida-app', 'movida-backend', 'movida-web', 'movida-api', 'movida-dashboard']
            
            for known_slug in known_projects:
                if not any(p.get('slug') == known_slug for p in projects):
                    self.logger.info(f"Testing direct access to missing project: {known_slug}")
                    try:
                        # Test if we can access the project directly
                        test_client = SentryMCPClient(project_slug=known_slug)
                        test_issues = test_client.get_issues(limit=1)
                        
                        # If successful, add to the list
                        platform_map = {
                            'ms-leads': 'php',
                            'movida-app': 'react-native',
                            'movida-backend': 'php',
                            'movida-web': 'javascript',
                            'movida-api': 'php',
                            'movida-dashboard': 'react'
                        }
                        
                        name_map = {
                            'ms-leads': 'MS Leads',
                            'movida-app': 'Movida App',
                            'movida-backend': 'Movida Backend',
                            'movida-web': 'Movida Web',
                            'movida-api': 'Movida API',
                            'movida-dashboard': 'Movida Dashboard'
                        }
                        
                        projects.append({
                            "name": name_map.get(known_slug, known_slug.title()),
                            "slug": known_slug,
                            "id": "",
                            "platform": platform_map.get(known_slug, ""),
                            "status": "active"
                        })
                        self.logger.info(f"Successfully added missing project: {known_slug}")
                        
                    except Exception as e:
                        self.logger.debug(f"Project {known_slug} not accessible: {e}")
            
            # Sort projects alphabetically by name
            projects.sort(key=lambda x: x['name'].lower())
            self.logger.info(f"Final project list has {len(projects)} projects")
            return projects
        
        # Fallback to expanded project list based on common Movida projects
        self.logger.info("Using fallback project list")
        return [
            {"name": "MS Leads", "slug": "ms-leads", "id": "", "platform": "php", "status": "active"},
            {"name": "Movida App", "slug": "movida-app", "id": "", "platform": "react-native", "status": "active"},
            {"name": "Movida Backend", "slug": "movida-backend", "id": "", "platform": "php", "status": "active"},
            {"name": "Movida Web", "slug": "movida-web", "id": "", "platform": "javascript", "status": "active"},
            {"name": "Movida API", "slug": "movida-api", "id": "", "platform": "php", "status": "active"},
            {"name": "Movida Dashboard", "slug": "movida-dashboard", "id": "", "platform": "react", "status": "active"}
        ]
