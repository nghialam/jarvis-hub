/* ========================================
   Jarvis Hub 3.0 — Async Task Manager
   Polls task status and displays results
   ======================================== */

const ASYNC_API = {
    tasks: '/api/v1/llm/tasks',
    taskDetail: '/api/v1/llm/tasks',
    health: '/api/v1/llm/health',
    stats: '/api/v1/llm/stats',
    circuitBreaker: '/api/v1/llm/circuit/reset',
    newsScore: '/api/v1/news/score',
    newsTrending: '/api/v1/news/trending',
    intelligenceStatus: '/api/v1/intelligence/pipeline/status',
};

// Task status polling state
let taskPollingInterval = null;
let taskPollTimer = null;

/* ========================================
   Task Status Polling
   ======================================== */

/**
 * Start polling for async task status updates.
 * Polls every 2 seconds until all tasks are completed/failed.
 */
function startTaskPolling(taskIds, onComplete) {
    if (taskPollingInterval) {
        clearInterval(taskPollingInterval);
    }

    const activeTaskIds = new Set(taskIds);
    let pollCount = 0;
    const maxPolls = 600; // Stop after 20 minutes (600 * 2s)

    taskPollingInterval = setInterval(() => {
        pollCount++;

        // Stop if max polls reached
        if (pollCount > maxPolls) {
            stopTaskPolling();
            return;
        }

        // Check each active task
        let allDone = true;
        let completedCount = 0;
        let failedCount = 0;

        for (const taskId of activeTaskIds) {
            const taskStatus = getTaskStatus(taskId);
            if (!taskStatus) continue;

            const statusEl = document.getElementById(`task-status-${taskId}`);
            const resultEl = document.getElementById(`task-result-${taskId}`);

            if (taskStatus.status === 'completed') {
                if (statusEl) {
                    statusEl.className = 'task-status completed';
                    statusEl.textContent = '✓ Completed';
                }
                if (resultEl && taskStatus.result) {
                    displayTaskResult(resultEl, taskId, taskStatus.result);
                }
                completedCount++;
            } else if (taskStatus.status === 'failed') {
                if (statusEl) {
                    statusEl.className = 'task-status failed';
                    statusEl.textContent = `✗ Failed: ${taskStatus.error || 'Unknown error'}`;
                }
                failedCount++;
            } else if (taskStatus.status === 'processing') {
                if (statusEl) {
                    statusEl.className = 'task-status processing';
                    statusEl.textContent = '⏳ Processing...';
                }
                allDone = false;
            }
        }

        // All tasks done?
        if (allDone && activeTaskIds.size > 0) {
            stopTaskPolling();
            if (onComplete) {
                onComplete({ completed: completedCount, failed: failedCount });
            }
        }
    }, 2000);
}

/**
 * Stop polling for async task status.
 */
function stopTaskPolling() {
    if (taskPollingInterval) {
        clearInterval(taskPollingInterval);
        taskPollingInterval = null;
    }
}

/**
 * Get cached task status.
 */
function getTaskStatus(taskId) {
    const cached = localStorage.getItem(`async-task-${taskId}`);
    if (cached) {
        try {
            return JSON.parse(cached);
        } catch (e) {
            return null;
        }
    }
    return null;
}

/**
 * Cache task status.
 */
function cacheTaskStatus(taskId, status) {
    localStorage.setItem(`async-task-${taskId}`, JSON.stringify(status));
}

/**
 * Display task result in the UI.
 */
function displayTaskResult(container, taskId, result) {
    if (!container) return;

    let html = '<div class="task-result">';

    // Format result based on type
    if (result.summary) {
        html += `<h4>${result.summary}</h4>`;
    }

    if (result.details) {
        html += `<div class="result-details">${escapeHtml(JSON.stringify(result.details, null, 2))}</div>`;
    }

    if (result.sentiment) {
        html += `<div class="sentiment-badge ${result.sentiment.toLowerCase()}">${result.sentiment}</div>`;
    }

    if (result.recommendation) {
        html += `<div class="recommendation">Recommendation: ${result.recommendation}</div>`;
    }

    html += `<div class="task-meta">Generated at ${new Date().toLocaleTimeString()}</div>`;
    html += '</div>';

    container.innerHTML = html;
}

/**
 * Poll the API for latest task statuses.
 */
async function pollTaskStatus() {
    try {
        const response = await fetch(ASYNC_API.tasks);
        if (!response.ok) return;

        const tasks = await response.json();

        // Update each task
        for (const task of tasks) {
            cacheTaskStatus(task.task_id, task);

            const statusEl = document.getElementById(`task-status-${task.task_id}`);
            if (statusEl) {
                if (task.status === 'completed') {
                    statusEl.className = 'task-status completed';
                    statusEl.textContent = '✓ Completed';
                } else if (task.status === 'failed') {
                    statusEl.className = 'task-status failed';
                    statusEl.textContent = `✗ Failed: ${task.error || 'Unknown error'}`;
                } else if (task.status === 'processing') {
                    statusEl.className = 'task-status processing';
                    statusEl.textContent = '⏳ Processing...';
                } else if (task.status === 'pending') {
                    statusEl.className = 'task-status pending';
                    statusEl.textContent = '⏸ Queued';
                }
            }
        }
    } catch (e) {
        console.error('Task status poll failed:', e);
    }
}

/* ========================================
   Task Status Display
   ======================================== */

/**
 * Create task status UI element.
 */
function createTaskStatusElement(taskId, taskType) {
    const container = document.getElementById('task-status-container');
    if (!container) return;

    const html = `
        <div class="task-item" id="task-item-${taskId}">
            <div class="task-info">
                <span class="task-type">${escapeHtml(taskType)}</span>
                <span class="task-id">${taskId}</span>
            </div>
            <div class="task-status pending" id="task-status-${taskId}">⏸ Queued</div>
            <div class="task-result-container" id="task-result-${taskId}"></div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', html);
}

/**
 * Clear all task status UI elements.
 */
function clearTaskStatusUI() {
    const container = document.getElementById('task-status-container');
    if (container) {
        container.innerHTML = '';
    }
}

/* ========================================
   LLM Health & Circuit Breaker UI
   ======================================== */

/**
 * Check LLM health and display status.
 */
async function checkLLMHealth() {
    try {
        const response = await fetch(ASYNC_API.health);
        if (!response.ok) return;

        const health = await response.json();

        const statusEl = document.getElementById('llm-health-status');
        if (statusEl) {
            if (health.available) {
                statusEl.className = 'health-indicator available';
                statusEl.textContent = `✓ LLM Available (${health.circuit_breaker_state})`;
            } else {
                statusEl.className = 'health-indicator unavailable';
                statusEl.textContent = '✗ LLM Unavailable (using heuristics)';
            }
        }

        const circuitEl = document.getElementById('circuit-breaker-state');
        if (circuitEl) {
            circuitEl.textContent = health.circuit_breaker_state || 'unknown';
        }

        return health;
    } catch (e) {
        console.error('LLM health check failed:', e);
        const statusEl = document.getElementById('llm-health-status');
        if (statusEl) {
            statusEl.className = 'health-indicator unavailable';
            statusEl.textContent = '✗ LLM Check Failed';
        }
        return null;
    }
}

/**
 * Reset circuit breaker.
 */
async function resetCircuitBreaker() {
    try {
        const response = await fetch(ASYNC_API.circuitBreaker, { method: 'POST' });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();
        alert(result.message || 'Circuit breaker reset');

        // Refresh health status
        await checkLLMHealth();
    } catch (e) {
        console.error('Circuit breaker reset failed:', e);
        alert('Failed to reset circuit breaker');
    }
}

/**
 * Get LLM stats.
 */
async function getLLMStats() {
    try {
        const response = await fetch(ASYNC_API.stats);
        if (!response.ok) return null;

        return await response.json();
    } catch (e) {
        console.error('LLM stats fetch failed:', e);
        return null;
    }
}

/* ========================================
   Intelligence Pipeline Status
   ======================================== */

/**
 * Get MI pipeline status.
 */
async function getPipelineStatus() {
    try {
        const response = await fetch(ASYNC_API.intelligenceStatus);
        if (!response.ok) return null;

        return await response.json();
    } catch (e) {
        console.error('Pipeline status fetch failed:', e);
        return null;
    }
}

/**
 * Trigger MI pipeline run.
 */
async function triggerPipelineRun() {
    try {
        const response = await fetch(ASYNC_API.intelligenceStatus, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();
        alert(result.message || 'Pipeline started');

        // Refresh status
        setTimeout(getPipelineStatus, 2000);
    } catch (e) {
        console.error('Pipeline trigger failed:', e);
        alert('Failed to trigger pipeline');
    }
}

/* ========================================
   News Scoring & Trending UI
   ======================================== */

/**
 * Score news articles.
 */
async function scoreNews() {
    try {
        const response = await fetch(ASYNC_API.newsScore);
        if (!response.ok) return null;

        return await response.json();
    } catch (e) {
        console.error('News scoring failed:', e);
        return null;
    }
}

/**
 * Get trending articles.
 */
async function getTrendingArticles(hours = 24, limit = 10) {
    try {
        const response = await fetch(`${ASYNC_API.newsTrending}?hours=${hours}&limit=${limit}`);
        if (!response.ok) return [];

        return await response.json();
    } catch (e) {
        console.error('Trending articles fetch failed:', e);
        return [];
    }
}

/* ========================================
   Utility Functions
   ======================================== */

/**
 * Escape HTML to prevent XSS.
 */
function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Format duration from seconds to human-readable.
 */
function formatDuration(seconds) {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

/* ========================================
   Initialize
   ======================================== */

/**
 * Initialize async task manager.
 */
function initAsyncTaskManager() {
    // Add health check button if element exists
    const healthBtn = document.getElementById('llm-health-check-btn');
    if (healthBtn) {
        healthBtn.addEventListener('click', checkLLMHealth);
    }

    // Add reset button if element exists
    const resetBtn = document.getElementById('circuit-breaker-reset-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', resetCircuitBreaker);
    }

    // Add pipeline trigger if element exists
    const pipelineBtn = document.getElementById('trigger-pipeline-btn');
    if (pipelineBtn) {
        pipelineBtn.addEventListener('click', triggerPipelineRun);
    }

    // Start periodic polling
    setInterval(() => {
        pollTaskStatus();
        checkLLMHealth();
    }, 30000); // Every 30 seconds

    // Initial check
    checkLLMHealth();
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAsyncTaskManager);
} else {
    initAsyncTaskManager();
}

// Export for manual initialization
window.asyncTaskManager = {
    startTaskPolling,
    stopTaskPolling,
    createTaskStatusElement,
    clearTaskStatusUI,
    checkLLMHealth,
    resetCircuitBreaker,
    getLLMStats,
    getPipelineStatus,
    triggerPipelineRun,
    scoreNews,
    getTrendingArticles,
    initAsyncTaskManager,
};
