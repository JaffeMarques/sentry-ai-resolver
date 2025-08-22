// Global state
let currentProject = null;
let refreshInterval = null;
let allProjects = [];
let filteredProjects = [];

// DOM elements
const projectSearch = document.getElementById('projectSearch');
const projectDropdown = document.getElementById('projectDropdown');
const selectedProjectSlug = document.getElementById('selectedProjectSlug');
const workDirectory = document.getElementById('workDirectory');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const runOnceBtn = document.getElementById('runOnceBtn');
const refreshBtn = document.getElementById('refreshIssues');
const statusFilter = document.getElementById('statusFilter');

// Git Configuration elements
const toggleGitConfigBtn = document.getElementById('toggleGitConfigBtn');
const gitConfigCard = document.querySelector('.git-config');

// Issue Filter Configuration elements
const toggleFilterConfigBtn = document.getElementById('toggleFilterConfigBtn');
const filterConfigCard = document.querySelector('.issue-filters');
const minSeverity = document.getElementById('minSeverity');
const environments = document.getElementById('environments');
const minOccurrences = document.getElementById('minOccurrences');
const maxAgeDays = document.getElementById('maxAgeDays');
const saveFilterConfigBtn = document.getElementById('saveFilterConfig');
const resetFilterConfigBtn = document.getElementById('resetFilterConfig');

// Git Configuration elements
const branchPrefix = document.getElementById('branchPrefix');
const includeIssueId = document.getElementById('includeIssueId');
const includeTimestamp = document.getElementById('includeTimestamp');
const commitPrefix = document.getElementById('commitPrefix');
const commitFormat = document.getElementById('commitFormat');
const autoPush = document.getElementById('autoPush');
const saveGitConfigBtn = document.getElementById('saveGitConfig');
const resetGitConfigBtn = document.getElementById('resetGitConfig');

// Status elements
const solverStatus = document.getElementById('solverStatus');
const currentProjectSpan = document.getElementById('currentProject');
const startedAtSpan = document.getElementById('startedAt');

// Stats elements
const totalIssues = document.getElementById('totalIssues');
const fixedIssues = document.getElementById('fixedIssues');
const resolvedIssues = document.getElementById('resolvedIssues');
const pendingIssues = document.getElementById('pendingIssues');

// Table elements
const issuesTableBody = document.getElementById('issuesTableBody');
const fixesTableBody = document.getElementById('fixesTableBody');

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    loadProjects();
    loadSavedWorkDirectory();
    setupEventListeners();
    initGitConfig();
    initFilterConfig();
    
    // Start auto-refresh every 30 seconds
    refreshInterval = setInterval(() => {
        if (currentProject) {
            refreshData();
        }
    }, 30000);
});

// Setup event listeners
function setupEventListeners() {
    // Simple project search functionality
    projectSearch.addEventListener('input', (e) => {
        filterProjects(e.target.value);
        showDropdown();
    });
    
    projectSearch.addEventListener('focus', () => {
        if (filteredProjects.length === 0) {
            filteredProjects = [...allProjects];
            updateDropdown();
        }
        showDropdown();
    });
    
    // Hide dropdown when clicking outside
    document.addEventListener('mousedown', (e) => {
        // Only hide if clicking outside all relevant areas
        const isInsideSearch = e.target.closest('.project-search-container');
        const isInsideDropdown = e.target.closest('.project-dropdown');
        const isInsideSelector = e.target.closest('.project-selector');
        const isInsideCard = e.target.closest('.card');
        
        if (!isInsideSearch && !isInsideDropdown && !isInsideSelector && !isInsideCard) {
            hideDropdown();
        }
    });
    
    // Keyboard navigation
    projectSearch.addEventListener('keydown', (e) => {
        const items = projectDropdown.querySelectorAll('.dropdown-item.selectable');
        let currentIndex = Array.from(items).findIndex(item => item.classList.contains('selected'));
        
        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (items.length === 0) break;
                if (currentIndex < items.length - 1) currentIndex++;
                else currentIndex = 0;
                updateSelection(items, currentIndex);
                break;
            case 'ArrowUp':
                e.preventDefault();
                if (items.length === 0) break;
                if (currentIndex > 0) currentIndex--;
                else currentIndex = items.length - 1;
                updateSelection(items, currentIndex);
                break;
            case 'Enter':
                e.preventDefault();
                if (currentIndex >= 0 && items[currentIndex]) {
                    items[currentIndex].click();
                }
                break;
            case 'Escape':
                hideDropdown();
                projectSearch.blur();
                break;
        }
    });
    
    // Clear search when field is cleared
    projectSearch.addEventListener('keyup', (e) => {
        if (e.target.value === '') {
            clearProject();
        }
    });
    workDirectory.addEventListener('change', handleWorkDirectoryChange);
    startBtn.addEventListener('click', startSolver);
    stopBtn.addEventListener('click', stopSolver);
    runOnceBtn.addEventListener('click', runOnce);
    refreshBtn.addEventListener('click', refreshData);
    statusFilter.addEventListener('change', loadIssues);
}

// Load available projects
async function loadProjects() {
    try {
        const response = await fetch('/api/projects');
        const data = await response.json();
        
        allProjects = data.projects;
        filteredProjects = [...allProjects];
        
        updateDropdown();
        showToast('Projetos carregados com sucesso', 'success');
    } catch (error) {
        console.error('Failed to load projects:', error);
        showToast('Erro ao carregar projetos', 'error');
        projectDropdown.innerHTML = '<div class="dropdown-item error">Erro ao carregar projetos</div>';
    }
}

// Simple dropdown functions
function showDropdown() {
    projectDropdown.classList.add('show');
    document.body.classList.add('dropdown-open');
}

function hideDropdown() {
    projectDropdown.classList.remove('show');
    document.body.classList.remove('dropdown-open');
}

// Update dropdown with filtered projects
function updateDropdown() {
    if (filteredProjects.length === 0) {
        projectDropdown.innerHTML = '<div class="dropdown-item">Nenhum projeto encontrado</div>';
        return;
    }
    
    projectDropdown.innerHTML = '';
    
    const searchTerm = projectSearch.value.trim();
    const maxDisplay = searchTerm ? filteredProjects.length : Math.min(50, filteredProjects.length);
    
    // Search hint
    if (!searchTerm && allProjects.length > 50) {
        const searchHint = document.createElement('div');
        searchHint.className = 'dropdown-item search-hint';
        searchHint.innerHTML = `<i class="fas fa-search"></i> Digite para buscar entre ${allProjects.length} projetos`;
        projectDropdown.appendChild(searchHint);
    }
    
    // Results count
    if (searchTerm && filteredProjects.length > 0) {
        const resultCount = document.createElement('div');
        resultCount.className = 'dropdown-item result-count';
        resultCount.innerHTML = `<i class="fas fa-search"></i> ${filteredProjects.length} resultado(s)`;
        projectDropdown.appendChild(resultCount);
    }
    
    // Project items
    filteredProjects.slice(0, maxDisplay).forEach(project => {
        const item = document.createElement('div');
        item.className = 'dropdown-item selectable';
        
        let projectName = project.name;
        let projectSlug = project.slug;
        
        // Highlight search term
        if (searchTerm) {
            const regex = new RegExp(`(${searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
            projectName = projectName.replace(regex, '<mark>$1</mark>');
            projectSlug = projectSlug.replace(regex, '<mark>$1</mark>');
        }
        
        item.innerHTML = `
            <div class="project-name">${projectName}</div>
            <div class="project-slug">${projectSlug}</div>
            ${project.platform ? `<div class="project-platform">${project.platform}</div>` : ''}
        `;
        
        item.addEventListener('click', () => selectProject(project));
        projectDropdown.appendChild(item);
    });
    
    // More results message
    if (!searchTerm && filteredProjects.length > maxDisplay) {
        const moreItem = document.createElement('div');
        moreItem.className = 'dropdown-item';
        moreItem.textContent = `... e mais ${filteredProjects.length - maxDisplay} projetos`;
        projectDropdown.appendChild(moreItem);
    }
}

// Filter projects based on search term
function filterProjects(searchTerm) {
    const term = searchTerm.toLowerCase().trim();
    
    if (!term) {
        filteredProjects = [...allProjects];
    } else {
        filteredProjects = allProjects.filter(project => {
            return project.name.toLowerCase().includes(term) || 
                   project.slug.toLowerCase().includes(term) ||
                   (project.platform && project.platform.toLowerCase().includes(term));
        });
    }
    
    updateDropdown();
}

// Select a project
function selectProject(project) {
    projectSearch.value = `${project.name} (${project.slug})`;
    selectedProjectSlug.value = project.slug;
    hideDropdown();
    
    // Trigger project change
    handleProjectChange(project.slug);
}

// Clear project selection
function clearProject() {
    projectSearch.value = '';
    selectedProjectSlug.value = '';
    currentProject = null;
    disableControls();
    filteredProjects = [...allProjects];
    updateDropdown();
}

// Update selection for keyboard navigation
function updateSelection(items, currentIndex) {
    items.forEach((item, index) => {
        if (index === currentIndex) {
            item.classList.add('selected');
            item.scrollIntoView({ block: 'nearest' });
        } else {
            item.classList.remove('selected');
        }
    });
}

// Handle project selection change
function handleProjectChange(projectSlug) {
    if (projectSlug) {
        currentProject = projectSlug;
        enableControls();
        loadSolverStatus();
        loadStats();
        loadIssues();
        loadFixes();
    } else {
        currentProject = null;
        disableControls();
        resetDisplay();
    }
}

// Handle work directory change
function handleWorkDirectoryChange() {
    // Save to localStorage for persistence
    if (workDirectory.value) {
        localStorage.setItem('workDirectory', workDirectory.value);
    }
}

// Load saved work directory
function loadSavedWorkDirectory() {
    const saved = localStorage.getItem('workDirectory');
    if (saved) {
        workDirectory.value = saved;
    }
}

// Enable/disable controls
function enableControls() {
    startBtn.disabled = false;
    runOnceBtn.disabled = false;
    refreshBtn.disabled = false;
}

function disableControls() {
    startBtn.disabled = true;
    stopBtn.disabled = true;
    runOnceBtn.disabled = true;
    refreshBtn.disabled = true;
}

// Reset display
function resetDisplay() {
    solverStatus.textContent = 'Parado';
    solverStatus.className = 'status-badge stopped';
    currentProjectSpan.textContent = '-';
    startedAtSpan.textContent = '-';
    
    totalIssues.textContent = '0';
    fixedIssues.textContent = '0';
    resolvedIssues.textContent = '0';
    pendingIssues.textContent = '0';
    
    issuesTableBody.innerHTML = '<tr><td colspan="8" class="text-center">Selecione um projeto</td></tr>';
    fixesTableBody.innerHTML = '<tr><td colspan="6" class="text-center">Selecione um projeto</td></tr>';
}

// Start solver
async function startSolver() {
    if (!currentProject) return;
    
    try {
        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Iniciando...';
        
        const response = await fetch('/api/solver/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                project_slug: currentProject,
                work_directory: workDirectory.value || null
            })
        });
        
        if (response.ok) {
            showToast('Solver iniciado com sucesso', 'success');
            loadSolverStatus();
        } else {
            const error = await response.json();
            showToast(`Erro ao iniciar solver: ${error.detail}`, 'error');
        }
    } catch (error) {
        console.error('Failed to start solver:', error);
        showToast('Erro ao iniciar solver', 'error');
    } finally {
        startBtn.innerHTML = '<i class="fas fa-play"></i> Iniciar Monitoramento';
        startBtn.disabled = false;
    }
}

// Stop solver
async function stopSolver() {
    if (!currentProject) return;
    
    try {
        stopBtn.disabled = true;
        stopBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Parando...';
        
        const response = await fetch('/api/solver/stop', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ project_slug: currentProject })
        });
        
        if (response.ok) {
            showToast('Solver parado com sucesso', 'success');
            loadSolverStatus();
        } else {
            const error = await response.json();
            showToast(`Erro ao parar solver: ${error.detail}`, 'error');
        }
    } catch (error) {
        console.error('Failed to stop solver:', error);
        showToast('Erro ao parar solver', 'error');
    } finally {
        stopBtn.innerHTML = '<i class="fas fa-stop"></i> Parar Monitoramento';
        stopBtn.disabled = false;
    }
}

// Run once
async function runOnce() {
    if (!currentProject) return;
    
    try {
        runOnceBtn.disabled = true;
        runOnceBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Executando...';
        
        const response = await fetch('/api/solver/run-once', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                project_slug: currentProject,
                work_directory: workDirectory.value || null
            })
        });
        
        if (response.ok) {
            showToast('Execução única iniciada', 'success');
            setTimeout(() => {
                refreshData();
            }, 3000);
        } else {
            const error = await response.json();
            showToast(`Erro na execução: ${error.detail}`, 'error');
        }
    } catch (error) {
        console.error('Failed to run once:', error);
        showToast('Erro na execução única', 'error');
    } finally {
        runOnceBtn.innerHTML = '<i class="fas fa-refresh"></i> Executar Uma Vez';
        runOnceBtn.disabled = false;
    }
}

// Load solver status
async function loadSolverStatus() {
    if (!currentProject) return;
    
    try {
        const response = await fetch(`/api/solver/status/${currentProject}`);
        const data = await response.json();
        
        // Update status
        solverStatus.textContent = data.status === 'running' ? 'Executando' : 
                                  data.status === 'stopping' ? 'Parando' : 'Parado';
        solverStatus.className = `status-badge ${data.status}`;
        
        currentProjectSpan.textContent = data.project_slug || '-';
        startedAtSpan.textContent = data.started_at ? 
            new Date(data.started_at).toLocaleString('pt-BR') : '-';
        
        // Update button states
        if (data.status === 'running') {
            startBtn.disabled = true;
            stopBtn.disabled = false;
        } else {
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
        
    } catch (error) {
        console.error('Failed to load solver status:', error);
    }
}

// Load statistics
async function loadStats() {
    if (!currentProject) return;
    
    try {
        const response = await fetch(`/api/stats/${currentProject}`);
        const data = await response.json();
        
        const stats = data.stats;
        totalIssues.textContent = stats.total || 0;
        fixedIssues.textContent = stats.fixed || 0;
        resolvedIssues.textContent = stats.resolved || 0;
        pendingIssues.textContent = stats.pending || 0;
        
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// Load issues
async function loadIssues() {
    if (!currentProject) return;
    
    const status = statusFilter.value;
    
    try {
        issuesTableBody.innerHTML = '<tr><td colspan="8" class="text-center">Carregando...</td></tr>';
        
        let url = `/api/issues/${currentProject}`;
        if (status) {
            url += `?status=${status}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.issues.length === 0) {
            issuesTableBody.innerHTML = '<tr><td colspan="8" class="text-center">Nenhuma issue encontrada</td></tr>';
            return;
        }
        
        issuesTableBody.innerHTML = data.issues.map(issue => `
            <tr>
                <td>${issue.id}</td>
                <td title="${issue.title}">${truncateText(issue.title, 50)}</td>
                <td><span class="issue-level ${issue.level}">${issue.level}</span></td>
                <td><span class="issue-status ${issue.status}">${issue.status}</span></td>
                <td>${issue.count}</td>
                <td><span class="fix-status ${issue.fix_applied ? 'applied' : 'not-applied'}">
                    ${issue.fix_applied ? 'Aplicada' : 'Não aplicada'}
                </span></td>
                <td>
                    <div class="confidence-bar">
                        <div class="confidence-fill ${getConfidenceClass(issue.fix_confidence)}" 
                             style="width: ${(issue.fix_confidence * 100).toFixed(1)}%"></div>
                    </div>
                    ${(issue.fix_confidence * 100).toFixed(1)}%
                </td>
                <td>${issue.processed_at ? new Date(issue.processed_at).toLocaleString('pt-BR') : '-'}</td>
            </tr>
        `).join('');
        
    } catch (error) {
        console.error('Failed to load issues:', error);
        issuesTableBody.innerHTML = '<tr><td colspan="8" class="text-center">Erro ao carregar issues</td></tr>';
    }
}

// Load fixes
async function loadFixes() {
    if (!currentProject) return;
    
    try {
        const response = await fetch(`/api/stats/${currentProject}`);
        const data = await response.json();
        
        if (data.recent_fixes.length === 0) {
            fixesTableBody.innerHTML = '<tr><td colspan="6" class="text-center">Nenhuma correção ainda</td></tr>';
            return;
        }
        
        fixesTableBody.innerHTML = data.recent_fixes.map(fix => `
            <tr>
                <td title="${fix.title}">${truncateText(fix.title, 30)}</td>
                <td>${fix.file_path}</td>
                <td>${fix.line_number}</td>
                <td title="${fix.explanation}">${truncateText(fix.explanation, 50)}</td>
                <td>
                    <div class="confidence-bar">
                        <div class="confidence-fill ${getConfidenceClass(fix.confidence)}" 
                             style="width: ${(fix.confidence * 100).toFixed(1)}%"></div>
                    </div>
                    ${(fix.confidence * 100).toFixed(1)}%
                </td>
                <td>${new Date(fix.applied_at).toLocaleString('pt-BR')}</td>
            </tr>
        `).join('');
        
    } catch (error) {
        console.error('Failed to load fixes:', error);
        fixesTableBody.innerHTML = '<tr><td colspan="6" class="text-center">Erro ao carregar correções</td></tr>';
    }
}

// Refresh all data
function refreshData() {
    if (currentProject) {
        loadSolverStatus();
        loadStats();
        loadIssues();
        loadFixes();
    }
}

// Utility functions
function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substr(0, maxLength) + '...';
}

function getConfidenceClass(confidence) {
    if (confidence >= 0.8) return 'high';
    if (confidence >= 0.6) return 'medium';
    return 'low';
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icon = type === 'success' ? 'fa-check-circle' : 
                 type === 'error' ? 'fa-exclamation-circle' : 
                 type === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle';
    
    toast.innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px;">
            <i class="fas ${icon}"></i>
            <span>${message}</span>
        </div>
    `;
    
    document.getElementById('toastContainer').appendChild(toast);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        toast.remove();
    }, 5000);
    
    // Click to remove
    toast.addEventListener('click', () => toast.remove());
}

// Connection status monitoring
function updateConnectionStatus() {
    fetch('/api/health')
        .then(response => {
            const statusEl = document.getElementById('connectionStatus');
            if (response.ok) {
                statusEl.className = 'status-indicator';
                statusEl.innerHTML = '<i class="fas fa-circle"></i><span>Conectado</span>';
            } else {
                throw new Error('Health check failed');
            }
        })
        .catch(() => {
            const statusEl = document.getElementById('connectionStatus');
            statusEl.className = 'status-indicator disconnected';
            statusEl.innerHTML = '<i class="fas fa-circle"></i><span>Desconectado</span>';
        });
}

// Git Configuration Management
function initGitConfig() {
    // Toggle Git Config visibility
    toggleGitConfigBtn.addEventListener('click', function() {
        const isVisible = gitConfigCard.style.display !== 'none';
        gitConfigCard.style.display = isVisible ? 'none' : 'block';
        
        // Update button content
        const icon = toggleGitConfigBtn.querySelector('i');
        if (isVisible) {
            toggleGitConfigBtn.innerHTML = '<i class="fas fa-cog"></i> Git Config';
        } else {
            toggleGitConfigBtn.innerHTML = '<i class="fas fa-times"></i> Fechar Config';
        }
    });
    
    // Save Git Configuration
    saveGitConfigBtn.addEventListener('click', saveGitConfig);
    
    // Reset Git Configuration
    resetGitConfigBtn.addEventListener('click', resetGitConfig);
    
    // Load current configuration
    loadGitConfig();
}

async function loadGitConfig() {
    try {
        const response = await fetch('/api/git-config');
        const config = await response.json();
        
        // Update form fields with current config
        branchPrefix.value = config.git_branch_prefix || 'sentry-fix';
        includeIssueId.checked = config.git_include_issue_id !== false;
        includeTimestamp.checked = config.git_include_timestamp !== false;
        commitPrefix.value = config.commit_message_prefix || 'fix';
        commitFormat.value = config.commit_message_format || 'conventional';
        autoPush.checked = config.git_auto_push !== false;
        
    } catch (error) {
        console.error('Failed to load git config:', error);
        showToast('Erro ao carregar configurações Git', 'error');
    }
}

async function saveGitConfig() {
    const config = {
        git_branch_prefix: branchPrefix.value.trim() || 'sentry-fix',
        git_include_issue_id: includeIssueId.checked,
        git_include_timestamp: includeTimestamp.checked,
        commit_message_prefix: commitPrefix.value.trim() || 'fix',
        commit_message_format: commitFormat.value,
        git_auto_push: autoPush.checked
    };
    
    try {
        const response = await fetch('/api/git-config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(config)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast('Configurações Git salvas com sucesso!', 'success');
            // Preview example branch/commit names
            showGitPreview(config);
        } else {
            showToast(result.error || 'Erro ao salvar configurações', 'error');
        }
        
    } catch (error) {
        console.error('Failed to save git config:', error);
        showToast('Erro ao salvar configurações Git', 'error');
    }
}

function resetGitConfig() {
    if (confirm('Restaurar configurações padrão do Git?')) {
        branchPrefix.value = 'sentry-fix';
        includeIssueId.checked = true;
        includeTimestamp.checked = true;
        commitPrefix.value = 'fix';
        commitFormat.value = 'conventional';
        autoPush.checked = true;
        
        showToast('Configurações Git restauradas', 'info');
    }
}

function showGitPreview(config) {
    // Generate example branch and commit names
    const exampleBranch = generateExampleBranchName(config);
    const exampleCommit = generateExampleCommitMessage(config);
    
    const previewHtml = `
        <div style="margin-top: 15px; padding: 15px; background: rgba(139, 233, 253, 0.1); border-radius: 8px; border: 1px solid rgba(139, 233, 253, 0.2);">
            <h5 style="color: #8be9fd; margin-bottom: 10px;"><i class="fas fa-eye"></i> Preview</h5>
            <p><strong>Branch:</strong> <code>${exampleBranch}</code></p>
            <p><strong>Commit:</strong> <code>${exampleCommit}</code></p>
        </div>
    `;
    
    // Find a place to show the preview (after save button)
    const existingPreview = document.querySelector('.git-preview');
    if (existingPreview) {
        existingPreview.remove();
    }
    
    const previewDiv = document.createElement('div');
    previewDiv.className = 'git-preview';
    previewDiv.innerHTML = previewHtml;
    
    saveGitConfigBtn.parentNode.insertBefore(previewDiv, saveGitConfigBtn.nextSibling);
    
    // Remove preview after 5 seconds
    setTimeout(() => {
        if (previewDiv.parentNode) {
            previewDiv.remove();
        }
    }, 5000);
}

function generateExampleBranchName(config) {
    let parts = [config.git_branch_prefix];
    
    if (config.git_include_issue_id) {
        parts.push('12345');
    }
    
    parts.push('badrequest');
    
    if (config.git_include_timestamp) {
        const now = new Date();
        const timestamp = now.getFullYear().toString() + 
                         (now.getMonth() + 1).toString().padStart(2, '0') + 
                         now.getDate().toString().padStart(2, '0') + '-' +
                         now.getHours().toString().padStart(2, '0') + 
                         now.getMinutes().toString().padStart(2, '0');
        parts.push(timestamp);
    }
    
    return parts.join('-');
}

function generateExampleCommitMessage(config) {
    return `${config.commit_message_prefix}: BadRequestException in LogHelper.php`;
}

// Toast notification system
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <i class="fas fa-${getToastIcon(type)}"></i>
        <span>${message}</span>
    `;
    
    // Create toast container if it doesn't exist
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    
    container.appendChild(toast);
    
    // Remove toast after 4 seconds
    setTimeout(() => {
        if (toast.parentNode) {
            toast.remove();
        }
    }, 4000);
}

function getToastIcon(type) {
    switch (type) {
        case 'success': return 'check-circle';
        case 'error': return 'exclamation-circle';
        case 'warning': return 'exclamation-triangle';
        default: return 'info-circle';
    }
}

// Issue Filter Configuration Management
function initFilterConfig() {
    // Toggle Filter Config visibility
    toggleFilterConfigBtn.addEventListener('click', function() {
        const isVisible = filterConfigCard.style.display !== 'none';
        filterConfigCard.style.display = isVisible ? 'none' : 'block';
        
        // Update button content
        const icon = toggleFilterConfigBtn.querySelector('i');
        if (isVisible) {
            toggleFilterConfigBtn.innerHTML = '<i class="fas fa-filter"></i> Filtros';
        } else {
            toggleFilterConfigBtn.innerHTML = '<i class="fas fa-times"></i> Fechar Filtros';
        }
    });
    
    // Save Filter Configuration
    saveFilterConfigBtn.addEventListener('click', saveFilterConfig);
    
    // Reset Filter Configuration
    resetFilterConfigBtn.addEventListener('click', resetFilterConfig);
    
    // Load current configuration
    loadFilterConfig();
}

async function loadFilterConfig() {
    try {
        const response = await fetch('/api/issue-filters');
        const config = await response.json();
        
        // Update form fields with current config
        minSeverity.value = config.issue_min_severity || 'all';
        environments.value = config.issue_environments || 'all';
        minOccurrences.value = config.issue_min_occurrences || 1;
        maxAgeDays.value = config.issue_max_age_days || 30;
        
    } catch (error) {
        console.error('Failed to load filter config:', error);
        showToast('Erro ao carregar configurações de filtros', 'error');
    }
}

async function saveFilterConfig() {
    const config = {
        issue_min_severity: minSeverity.value,
        issue_environments: environments.value.trim() || 'all',
        issue_min_occurrences: parseInt(minOccurrences.value) || 1,
        issue_max_age_days: parseInt(maxAgeDays.value) || 30
    };
    
    try {
        const response = await fetch('/api/issue-filters', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(config)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast('Configurações de filtros salvas com sucesso!', 'success');
            // Preview example filter criteria
            showFilterPreview(config);
        } else {
            console.error('Save filter config error:', result);
            showToast(result.detail || result.error || 'Erro ao salvar configurações', 'error');
        }
        
    } catch (error) {
        console.error('Failed to save filter config:', error);
        showToast('Erro ao salvar configurações de filtros', 'error');
    }
}

function resetFilterConfig() {
    if (confirm('Restaurar configurações padrão dos filtros?')) {
        minSeverity.value = 'all';
        environments.value = 'all';
        minOccurrences.value = 1;
        maxAgeDays.value = 30;
        
        showToast('Configurações de filtros restauradas', 'info');
    }
}

function showFilterPreview(config) {
    // Generate example filter description
    const severityLevels = {
        'all': 'todas as severidades',
        'debug': 'debug, info, warning, error, fatal',
        'info': 'info, warning, error, fatal',
        'warning': 'warning, error, fatal',
        'error': 'error, fatal',
        'fatal': 'apenas fatal'
    };
    
    const envText = config.issue_environments === 'all' ? 'todos os environments' : 
                   config.issue_environments.split(',').map(e => e.trim()).join(', ');
    
    const previewHtml = `
        <div style="margin-top: 15px; padding: 15px; background: rgba(80, 250, 123, 0.1); border-radius: 8px; border: 1px solid rgba(80, 250, 123, 0.2);">
            <h5 style="color: #50fa7b; margin-bottom: 10px;"><i class="fas fa-eye"></i> Filtros Ativos</h5>
            <p><strong>Severidade:</strong> ${severityLevels[config.issue_min_severity] || config.issue_min_severity}</p>
            <p><strong>Environments:</strong> ${envText}</p>
            <p><strong>Min. Ocorrências:</strong> ${config.issue_min_occurrences}+ vezes</p>
            <p><strong>Idade Máxima:</strong> ${config.issue_max_age_days} dias</p>
        </div>
    `;
    
    // Find a place to show the preview (after save button)
    const existingPreview = document.querySelector('.filter-preview');
    if (existingPreview) {
        existingPreview.remove();
    }
    
    const previewDiv = document.createElement('div');
    previewDiv.className = 'filter-preview';
    previewDiv.innerHTML = previewHtml;
    
    saveFilterConfigBtn.parentNode.insertBefore(previewDiv, saveFilterConfigBtn.nextSibling);
    
    // Remove preview after 5 seconds
    setTimeout(() => {
        if (previewDiv.parentNode) {
            previewDiv.remove();
        }
    }, 5000);
}

// Check connection every 60 seconds
setInterval(updateConnectionStatus, 60000);