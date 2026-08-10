document.addEventListener('DOMContentLoaded', function () {
    const findJobsForm = document.getElementById('find-jobs-form');
    const progressContainer = document.getElementById('progress-container');
    const progressStage = document.getElementById('progress-stage');
    const progressDetails = document.getElementById('progress-details');
    const progressBarFill = document.getElementById('progress-bar-fill');
    const btnFindJobs = document.getElementById('btn-find-jobs');

    let pollInterval = null;

    if (findJobsForm) {
        findJobsForm.addEventListener('submit', function (e) {
            e.preventDefault();

            const formData = new FormData(findJobsForm);
            btnFindJobs.disabled = true;
            btnFindJobs.innerText = '⏳ RUNNING SEARCH...';

            if (progressContainer) {
                progressContainer.classList.remove('hidden');
                progressContainer.classList.add('active');
            }

            fetch('/run', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'started') {
                    startPolling();
                } else {
                    alert(data.message || 'Error starting job search.');
                    btnFindJobs.disabled = false;
                    btnFindJobs.innerText = '🚀 FIND JOBS';
                }
            })
            .catch(err => {
                console.error('Error triggering job run:', err);
                btnFindJobs.disabled = false;
                btnFindJobs.innerText = '🚀 FIND JOBS';
            });
        });
    }

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(checkStatus, 2500);
        checkStatus();
    }

    function checkStatus() {
        fetch('/run/status')
            .then(res => res.json())
            .then(data => {
                const prog = data.progress;
                if (!prog) return;

                if (progressStage) progressStage.innerText = prog.stage || 'Running...';
                if (progressDetails) progressDetails.innerText = prog.details || '';

                if (prog.status === 'completed' || prog.status === 'partial' || prog.status === 'failed') {
                    clearInterval(pollInterval);
                    if (btnFindJobs) {
                        btnFindJobs.disabled = false;
                        btnFindJobs.innerText = '🚀 FIND JOBS';
                    }
                    if (progressStage) progressStage.innerText = 'Run Finished (' + prog.status + ')';
                    if (progressBarFill) progressBarFill.style.width = '100%';
                    
                    setTimeout(() => {
                        window.location.href = '/results';
                    }, 1500);
                }
            })
            .catch(err => console.error('Status check error:', err));
    }
});

function updateJobStatus(jobId, status) {
    fetch(`/jobs/${jobId}/${status}`, {
        method: 'POST'
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            const row = document.getElementById(`job-row-${jobId}`);
            if (row) {
                row.className = `job-row status-${status}`;
                const buttons = row.querySelectorAll('.btn-icon');
                buttons.forEach(b => b.classList.remove('active'));
                const targetBtn = row.querySelector(`.btn-mark-${status}`);
                if (targetBtn) targetBtn.classList.add('active');
            }
        } else {
            alert('Failed to update status.');
        }
    })
    .catch(err => console.error('Error updating job status:', err));
}
