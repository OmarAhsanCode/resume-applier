document.addEventListener('DOMContentLoaded', function () {
    const findJobsForm = document.getElementById('find-jobs-form');
    const btnFindJobs = document.getElementById('btn-find-jobs');
    const btnStopRun = document.getElementById('btn-stop-run');

    let pollInterval = null;

    if (findJobsForm) {
        findJobsForm.addEventListener('submit', function (e) {
            e.preventDefault();

            const formData = new FormData(findJobsForm);
            if (btnFindJobs) {
                btnFindJobs.disabled = true;
                btnFindJobs.innerText = 'SEARCH RUNNING...';
            }
            if (btnStopRun) {
                btnStopRun.disabled = false;
            }

            showToast('Run started.', 'info');

            fetch('/run', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'started') {
                    startPolling();
                } else {
                    showToast(data.message || 'Error starting job search.', 'error');
                    resetRunButtons();
                }
            })
            .catch(err => {
                console.error('Error triggering job run:', err);
                showToast('Failed to start run.', 'error');
                resetRunButtons();
            });
        });
    }

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(checkStatus, 800);
        checkStatus();
    }

    function checkStatus() {
        fetch('/run/status')
            .then(res => res.json())
            .then(data => {
                const prog = data.progress || {};
                const active = data.active;

                // Update Status Panel
                const statusVal = document.getElementById('panel-status-val');
                const runIdVal = document.getElementById('panel-run-id-val');
                const stageVal = document.getElementById('panel-stage-val');
                const detailsVal = document.getElementById('panel-details');

                if (statusVal) statusVal.innerText = (prog.status || 'idle').toUpperCase();
                if (runIdVal && data.run_id) runIdVal.innerText = data.run_id;
                if (stageVal) stageVal.innerText = prog.stage || 'Ready';
                if (detailsVal) detailsVal.innerText = prog.details || '';

                if (data.latest_run) {
                    const disc = document.getElementById('panel-discovered-val');
                    const ana = document.getElementById('panel-analyzed-val');
                    const sel = document.getElementById('panel-selected-val');
                    if (disc) disc.innerText = data.latest_run.discovered_count || 0;
                    if (ana) ana.innerText = data.latest_run.analyzed_count || 0;
                    if (sel) sel.innerText = data.latest_run.selected_count || 0;
                }

                // Update Live Log Terminal
                if (data.logs && Array.isArray(data.logs)) {
                    updateLiveConsole(data.logs);
                }

                const liveIndicator = document.getElementById('console-live-indicator');
                if (liveIndicator) {
                    if (active) {
                        liveIndicator.innerText = '● RUNNING';
                        liveIndicator.style.color = '#10b981';
                    } else {
                        liveIndicator.innerText = '● IDLE';
                        liveIndicator.style.color = '#9ca3af';
                    }
                }

                if (btnStopRun) btnStopRun.disabled = !active;
                if (btnFindJobs) btnFindJobs.disabled = active;

                if (!active && prog.status && prog.status !== 'running' && prog.status !== 'idle') {
                    clearInterval(pollInterval);
                    resetRunButtons();
                    if (prog.status === 'stopped') {
                        showToast(prog.details || 'Run stopped by user.', 'stop');
                    } else if (prog.status === 'completed') {
                        showToast('Run completed successfully.', 'success');
                    }
                }
            })
            .catch(err => console.error('Status check error:', err));
    }

    function resetRunButtons() {
        if (btnFindJobs) {
            btnFindJobs.disabled = false;
            btnFindJobs.innerText = 'FIND JOBS';
        }
        if (btnStopRun) {
            btnStopRun.disabled = true;
        }
    }

    // Start polling if already running on page load
    fetch('/run/status')
        .then(res => res.json())
        .then(data => {
            if (data.active) startPolling();
        });
});

function updateLiveConsole(logs) {
    const consoleBox = document.getElementById('live-console');
    if (!consoleBox) return;

    consoleBox.innerHTML = logs.map(line => `<div class="console-line">${escapeHtml(line)}</div>`).join('');
    consoleBox.scrollTop = consoleBox.scrollHeight;
}

function stopRun() {
    const btnStopRun = document.getElementById('btn-stop-run');
    if (btnStopRun) {
        btnStopRun.disabled = true;
        btnStopRun.innerText = 'STOPPING...';
    }
    showToast('Stopping run at safe checkpoint...', 'stop');

    fetch('/run/stop', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            showToast(data.message || 'Stop requested.', 'info');
        })
        .catch(err => {
            console.error('Error stopping run:', err);
            showToast('Failed to request stop.', 'error');
        });
}

function openClearDbModal() {
    fetch('/run/status')
        .then(res => res.json())
        .then(data => {
            if (data.active) {
                showToast('Stop the current run before clearing the database.', 'warning');
            } else {
                const modal = document.getElementById('modal-clear-db');
                if (modal) modal.classList.remove('hidden');
            }
        });
}

function closeClearDbModal() {
    const modal = document.getElementById('modal-clear-db');
    if (modal) modal.classList.add('hidden');
}

function confirmClearDatabase() {
    closeClearDbModal();
    fetch('/database/clear', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                showToast('Database cleared successfully.', 'success');
                setTimeout(() => { window.location.reload(); }, 1000);
            } else {
                showToast(data.message || 'Failed to clear database.', 'error');
            }
        })
        .catch(err => {
            console.error('Error clearing database:', err);
            showToast('Failed to clear database.', 'error');
        });
}

function openDetailsModal(jobId, company, title) {
    const scriptEl = document.getElementById(`job-detail-data-${jobId}`);
    const modal = document.getElementById('modal-job-details');
    const modalTitle = document.getElementById('details-modal-title');
    const modalBody = document.getElementById('details-modal-body');

    if (!scriptEl || !modal || !modalBody) return;

    if (modalTitle) modalTitle.innerText = `${company} — ${title}`;

    let data = {};
    try {
        data = JSON.parse(scriptEl.textContent);
    } catch (e) {
        console.error('Error parsing job detail JSON:', e);
    }

    let html = '';

    // SECTION 1: OBJECTIVE JOB FACTS
    html += `<div style="border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; margin-bottom: 12px;">`;
    html += `<h5 style="margin: 0 0 6px 0; color: #111827; font-size: 0.95rem; font-weight: 700;">📋 JOB INFORMATION</h5>`;

    if (data.role_summary) {
        html += `<div style="margin-bottom: 6px;"><strong>Role Summary:</strong> ${escapeHtml(data.role_summary)}</div>`;
    }
    if (data.key_technologies && Array.isArray(data.key_technologies) && data.key_technologies.length > 0) {
        html += `<div style="margin-bottom: 6px;"><strong>Key Technologies:</strong> ${data.key_technologies.map(escapeHtml).join(', ')}</div>`;
    }
    if (data.key_points && Array.isArray(data.key_points) && data.key_points.length > 0) {
        html += `<div style="margin-bottom: 6px;"><strong>Key Responsibilities & Highlights:</strong>`;
        html += `<ul style="margin: 4px 0 0 0; padding-left: 20px;">`;
        data.key_points.forEach(pt => { html += `<li>${escapeHtml(pt)}</li>`; });
        html += `</ul></div>`;
    }
    html += `</div>`;

    // SECTION 2: CANDIDATE MATCH DETAILS
    html += `<div>`;
    html += `<h5 style="margin: 0 0 6px 0; color: #1d4ed8; font-size: 0.95rem; font-weight: 700;">🎯 CANDIDATE MATCH ANALYSIS</h5>`;

    if (data.score) {
        html += `<div style="margin-bottom: 6px;"><strong>AI Match Score:</strong> <span class="badge badge-info">${data.score} / 100</span> (${escapeHtml(data.recommendation || 'consider')})</div>`;
    }
    if (data.matching_requirements && Array.isArray(data.matching_requirements) && data.matching_requirements.length > 0) {
        html += `<div style="margin-bottom: 6px;"><strong>Matching Skills:</strong> ${data.matching_requirements.map(escapeHtml).join(', ')}</div>`;
    }
    if (data.missing_preferred_skills && Array.isArray(data.missing_preferred_skills) && data.missing_preferred_skills.length > 0) {
        html += `<div style="margin-bottom: 6px;"><strong>Missing Preferred Skills:</strong> ${data.missing_preferred_skills.map(escapeHtml).join(', ')}</div>`;
    }
    if (data.reason) {
        html += `<div style="margin-top: 6px;"><strong>Match Evaluation:</strong><p style="margin-top: 4px; color: #374151; font-size: 0.85rem;">${escapeHtml(data.reason)}</p></div>`;
    }
    html += `</div>`;

    modalBody.innerHTML = html || '<p>No additional details available.</p>';
    modal.classList.remove('hidden');
}

function closeDetailsModal() {
    const modal = document.getElementById('modal-job-details');
    if (modal) modal.classList.add('hidden');
}

function updateJobStatus(jobId, status) {
    fetch(`/jobs/${jobId}/${status}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                showToast(`Job status updated to ${status}.`, 'success');
                const row = document.getElementById(`job-row-${jobId}`);
                if (row) {
                    row.className = `job-row status-${status}`;
                    const buttons = row.querySelectorAll('.btn-icon');
                    buttons.forEach(b => b.classList.remove('active'));
                    const targetBtn = row.querySelector(`.btn-mark-${status}`);
                    if (targetBtn) targetBtn.classList.add('active');
                }
            } else {
                showToast('Failed to update status.', 'error');
            }
        })
        .catch(err => console.error('Error updating job status:', err));
}

function generateResume(jobId, buttonEl) {
    if (!buttonEl) buttonEl = document.getElementById(`resume-btn-${jobId}`);
    if (!buttonEl || buttonEl.disabled) return;

    const originalText = buttonEl.innerText;
    buttonEl.disabled = true;
    buttonEl.innerText = 'Generating...';

    fetch(`/jobs/${jobId}/generate-resume`, { method: 'POST' })
        .then(res => res.json().then(data => ({ status: res.status, body: data })))
        .then(result => {
            if (result.status === 200 && result.body.status === 'success') {
                showToast('Resume created successfully.', 'success');
                const cell = document.getElementById(`resume-cell-${jobId}`);
                if (cell) {
                    cell.innerHTML = `
                        <span class="badge badge-success">✓ Created</span>
                        <div class="resume-btn-group" style="margin-top: 4px;">
                            <a href="${result.body.view_url}" target="_blank" class="btn btn-xs btn-outline">Overleaf / .tex</a>
                            <a href="${result.body.download_url}" class="btn btn-xs btn-secondary">Download</a>
                        </div>
                    `;
                }
            } else {
                const msg = (result.body && result.body.message) ? result.body.message : 'Resume generation failed.';
                showToast(msg, 'error');
                buttonEl.disabled = false;
                buttonEl.innerText = originalText;
            }
        })
        .catch(err => {
            console.error('Error generating resume:', err);
            showToast('Resume generation failed.', 'error');
            buttonEl.disabled = false;
            buttonEl.innerText = originalText;
        });
}

function showToast(message, type) {
    let toast = document.getElementById('toast-notification');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast-notification';
        document.body.appendChild(toast);
    }
    toast.className = `toast toast-${type} show`;
    toast.innerText = message;
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3500);
}

function triggerSheetSync() {
    showToast("Syncing jobs to Google Sheet...", "info");
    fetch("/sync-sheets", { method: "POST" })
        .then(r => r.json())
        .then(data => {
            if (data.status === "success") {
                showToast(data.message, "success");
            } else {
                showToast(data.message || "Sync failed", "error");
            }
        })
        .catch(err => showToast("Error syncing sheet: " + err, "error"));
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
