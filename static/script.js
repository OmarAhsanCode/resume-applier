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

function confirmClearDb() {
    confirmClearDatabase();
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

// ---------------------------------------------------------------------------
// Company Watchlist & Discovery Handlers
// ---------------------------------------------------------------------------

let activeDiscoveryTaskId = null;
let activeDiscoveryInterval = null;
let currentCandidatePayload = null;

function triggerCompanyDiscovery() {
    const inputEl = document.getElementById('add-company-name');
    if (!inputEl) return;
    const companyName = inputEl.value.trim();
    if (!companyName) {
        showToast('Please enter a company name.', 'error');
        return;
    }

    const btnAdd = document.getElementById('btn-add-company');
    if (btnAdd) btnAdd.disabled = true;

    // Show discovery progress modal
    openCompanyDiscoveryModal(companyName);

    fetch('/companies/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_name: companyName })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'started' && data.task_id) {
            activeDiscoveryTaskId = data.task_id;
            if (activeDiscoveryInterval) clearInterval(activeDiscoveryInterval);
            activeDiscoveryInterval = setInterval(pollCompanyDiscoveryStatus, 1000);
        } else {
            showToast(data.message || 'Discovery error', 'error');
            closeCompanyDiscoveryModal();
            if (btnAdd) btnAdd.disabled = false;
        }
    })
    .catch(err => {
        showToast('Failed to start discovery.', 'error');
        closeCompanyDiscoveryModal();
        if (btnAdd) btnAdd.disabled = false;
    });
}

function pollCompanyDiscoveryStatus() {
    if (!activeDiscoveryTaskId) return;

    fetch(`/companies/discover/status/${activeDiscoveryTaskId}`)
    .then(r => r.json())
    .then(data => {
        if (data.status === 'completed' || data.status === 'failed') {
            clearInterval(activeDiscoveryInterval);
            activeDiscoveryInterval = null;

            const btnAdd = document.getElementById('btn-add-company');
            if (btnAdd) btnAdd.disabled = false;

            if (data.status === 'completed' && data.candidate) {
                closeCompanyDiscoveryModal();
                openCompanyConfirmationModal(data.candidate);
            } else {
                const logBox = document.getElementById('discovery-log-box');
                if (logBox) {
                    logBox.innerHTML += `<div class="console-line text-danger">Could not verify a working career/job source for this company.</div>`;
                }
                showToast(data.error || 'Verification failed.', 'error');
            }
        } else if (data.logs && data.logs.length > 0) {
            const logBox = document.getElementById('discovery-log-box');
            if (logBox) {
                logBox.innerHTML = data.logs.map(l => `<div class="console-line">${escapeHtml(l)}</div>`).join('');
                logBox.scrollTop = logBox.scrollHeight;
            }
        }
    })
    .catch(err => {
        console.error('Error polling discovery status:', err);
    });
}

function openCompanyDiscoveryModal(compName) {
    const modal = document.getElementById('modal-company-discovery');
    const titleEl = document.getElementById('disc-modal-title');
    const logBox = document.getElementById('discovery-log-box');
    if (titleEl) titleEl.innerText = `Finding official career portal for ${compName}...`;
    if (logBox) logBox.innerHTML = `<div class="console-line">Searching for official company...</div>`;
    if (modal) modal.classList.remove('hidden');
}

function closeCompanyDiscoveryModal() {
    const modal = document.getElementById('modal-company-discovery');
    if (modal) modal.classList.add('hidden');
    if (activeDiscoveryInterval) clearInterval(activeDiscoveryInterval);
    activeDiscoveryInterval = null;
    const btnAdd = document.getElementById('btn-add-company');
    if (btnAdd) btnAdd.disabled = false;
}

function openCompanyConfirmationModal(cand) {
    currentCandidatePayload = cand;
    const modal = document.getElementById('modal-company-confirmation');
    
    document.getElementById('conf-company-name').innerHTML = `<strong>${escapeHtml(cand.company_name)}</strong>`;
    
    const careersLink = document.getElementById('conf-careers-url');
    if (careersLink) {
        careersLink.href = cand.careers_url || '#';
        careersLink.innerText = cand.careers_url || 'N/A';
    }

    const platformEl = document.getElementById('conf-ats-platform');
    if (platformEl) platformEl.innerText = (cand.ats_platform || 'Unknown').toUpperCase();

    const statusEl = document.getElementById('conf-verification-status');
    if (statusEl) {
        const verStatus = cand.verification_status || (cand.verified ? 'verified' : 'verification_failed');
        if (verStatus === 'verified' && cand.verified && (cand.jobs_found || 0) > 0) {
            statusEl.innerHTML = `<span class="badge badge-success">✓ VERIFIED</span>`;
        } else if (verStatus === 'no_jobs_found') {
            statusEl.innerHTML = `<span class="badge badge-warning">⚠ VERIFIED SOURCE — NO CURRENT JOBS</span>`;
        } else {
            statusEl.innerHTML = `<span class="badge badge-danger">✗ VERIFICATION FAILED</span>`;
        }
    }

    const reasonEl = document.getElementById('conf-verification-reason');
    if (reasonEl) reasonEl.innerText = cand.verification_reason || 'N/A';

    const jobsEl = document.getElementById('conf-jobs-found');
    if (jobsEl) jobsEl.innerText = cand.jobs_found || 0;

    const countryEl = document.getElementById('conf-country');
    if (countryEl) countryEl.innerText = cand.country || 'India';

    const prioInput = document.getElementById('conf-priority');
    if (prioInput) prioInput.value = 75;

    const addBtn = document.getElementById('btn-confirm-add-company');
    if (addBtn) {
        if (cand.addable === false || !cand.verified || (cand.jobs_found || 0) <= 0) {
            addBtn.disabled = true;
            addBtn.title = "Cannot add unverified or zero-job company";
            addBtn.style.opacity = '0.5';
            addBtn.style.cursor = 'not-allowed';
        } else {
            addBtn.disabled = false;
            addBtn.title = "";
            addBtn.style.opacity = '1.0';
            addBtn.style.cursor = 'pointer';
        }
    }

    if (modal) modal.classList.remove('hidden');
}

function retryCompanyDiscovery() {
    const compName = currentCandidatePayload ? currentCandidatePayload.company_name : '';
    closeCompanyConfirmationModal();
    const compInput = document.getElementById('watchlist-company-input');
    if (compInput && compName) {
        compInput.value = compName;
    }
    triggerCompanyDiscovery();
}

function closeCompanyConfirmationModal() {
    const modal = document.getElementById('modal-company-confirmation');
    if (modal) modal.classList.add('hidden');
    currentCandidatePayload = null;
}

function confirmAddCompany() {
    if (!currentCandidatePayload) return;
    const prioInput = document.getElementById('conf-priority');
    const priorityVal = prioInput ? parseInt(prioInput.value, 10) : 75;
    currentCandidatePayload.priority = priorityVal;

    fetch('/companies/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentCandidatePayload)
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            showToast(`Added ${data.company.company} to Watchlist!`, 'success');
            closeCompanyConfirmationModal();
            setTimeout(() => window.location.reload(), 600);
        } else {
            showToast(data.message || 'Failed to save company', 'error');
        }
    })
    .catch(err => {
        showToast('Error saving company.', 'error');
    });
}

function openEditCompanyModalFromEl(el) {
    if (!el) return;
    const compName = el.getAttribute('data-company');
    const currentPrio = parseInt(el.getAttribute('data-priority') || '75', 10);
    const currentEnabled = el.getAttribute('data-enabled') === 'true';
    openEditCompanyModal(compName, currentPrio, currentEnabled);
}

function openEditCompanyModal(compName, currentPrio, currentEnabled) {
    const modal = document.getElementById('modal-edit-company');
    document.getElementById('edit-company-name').value = compName;
    document.getElementById('edit-display-name').innerText = compName;
    document.getElementById('edit-priority').value = currentPrio || 75;
    document.getElementById('edit-enabled').value = currentEnabled ? 'true' : 'false';
    if (modal) modal.classList.remove('hidden');
}

function closeEditCompanyModal() {
    const modal = document.getElementById('modal-edit-company');
    if (modal) modal.classList.add('hidden');
}

function confirmSaveEditCompany() {
    const compName = document.getElementById('edit-company-name').value;
    const priorityVal = parseInt(document.getElementById('edit-priority').value, 10);
    const enabledVal = document.getElementById('edit-enabled').value === 'true';

    Promise.all([
        fetch('/companies/priority', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ company: compName, priority: priorityVal })
        }),
        fetch('/companies/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ company: compName, enabled: enabledVal })
        })
    ])
    .then(() => {
        showToast(`Updated ${compName}.`, 'success');
        closeEditCompanyModal();
        setTimeout(() => window.location.reload(), 600);
    })
    .catch(err => showToast('Failed to update company.', 'error'));
}

function verifyCompany(compName) {
    showToast(`Verifying ${compName}...`, 'info');
    fetch('/companies/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company: compName })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success' && data.company) {
            const comp = data.company;
            if (comp.verified) {
                showToast(`✓ ${comp.company}: Verified (${comp.jobs_found} jobs found)`, 'success');
            } else {
                showToast(`✗ ${comp.company}: Verification failed`, 'error');
            }
            setTimeout(() => window.location.reload(), 1000);
        } else {
            showToast(data.message || 'Verification error', 'error');
        }
    })
    .catch(err => showToast('Failed to verify company.', 'error'));
}

function openDeleteCompanyModal(compName) {
    const modal = document.getElementById('modal-delete-company');
    document.getElementById('delete-company-name').value = compName;
    document.getElementById('delete-company-display-name').innerText = compName;
    if (modal) modal.classList.remove('hidden');
}

function closeDeleteCompanyModal() {
    const modal = document.getElementById('modal-delete-company');
    if (modal) modal.classList.add('hidden');
}

function confirmRemoveCompany() {
    const compName = document.getElementById('delete-company-name').value;
    fetch('/companies/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company: compName })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            showToast(`Removed ${compName} from Watchlist.`, 'success');
            closeDeleteCompanyModal();
            setTimeout(() => window.location.reload(), 600);
        } else {
            showToast(data.message || 'Failed to remove company', 'error');
        }
    })
    .catch(err => showToast('Error removing company.', 'error'));
}

let verifyAllInterval = null;

function verifyAllCompanies() {
    const modal = document.getElementById('modal-verify-all');
    if (modal) modal.classList.remove('hidden');
    
    document.getElementById('verify-all-progress-text').innerText = 'Initializing batch verification...';
    document.getElementById('verify-all-log-box').innerHTML = '';
    document.getElementById('btn-close-verify-all').disabled = true;
    
    fetch('/companies/verify-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'started') {
            verifyAllInterval = setInterval(pollVerifyAllStatus, 1000);
        } else {
            showToast(data.message || 'Failed to start verification.', 'error');
            closeVerifyAllModal();
        }
    })
    .catch(err => {
        showToast('Error starting batch verification.', 'error');
        closeVerifyAllModal();
    });
}

function pollVerifyAllStatus() {
    fetch('/companies/verify-all/status')
    .then(r => r.json())
    .then(data => {
        const progText = `[${data.current}/${data.total}] Verifying ${data.current_company}...`;
        document.getElementById('verify-all-progress-text').innerText = progText;
        
        const logBox = document.getElementById('verify-all-log-box');
        logBox.innerText = data.logs.join('\n');
        logBox.scrollTop = logBox.scrollHeight;
        
        if (data.status === 'completed') {
            clearInterval(verifyAllInterval);
            document.getElementById('verify-all-progress-text').innerText = 'Batch verification completed successfully!';
            document.getElementById('btn-close-verify-all').disabled = false;
            showToast('Batch verification completed.', 'success');
            setTimeout(() => window.location.reload(), 1500);
        } else if (data.status === 'failed') {
            clearInterval(verifyAllInterval);
            document.getElementById('verify-all-progress-text').innerText = 'Batch verification failed.';
            document.getElementById('btn-close-verify-all').disabled = false;
            showToast('Batch verification failed.', 'error');
        }
    })
    .catch(err => {
        console.error('Error polling verify-all status:', err);
    });
}

function closeVerifyAllModal() {
    const modal = document.getElementById('modal-verify-all');
    if (modal) modal.classList.add('hidden');
    if (verifyAllInterval) {
        clearInterval(verifyAllInterval);
        verifyAllInterval = null;
    }
}
