document.addEventListener('DOMContentLoaded', () => {
  const uploadForm = document.getElementById('upload-form');
  const processBtn = document.getElementById('process-btn');
  const progressContainer = document.getElementById('progress-container');
  const alertContainer = document.getElementById('alert-container');
  const documentsTbody = document.getElementById('documents-tbody');
  const refreshBtn = document.getElementById('refresh-btn');

  // Load documents on page load
  loadDocuments();

  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => loadDocuments());
  }

  // Handle Upload Form Submission
  if (uploadForm) {
    uploadForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const fileInput = document.getElementById('document-file');
      const docTypeSelect = document.getElementById('document-type');

      if (!fileInput.files || fileInput.files.length === 0) {
        showAlert('Please select a file to upload.', 'error');
        return;
      }

      // UI Loading State
      processBtn.disabled = true;
      progressContainer.style.display = 'flex';
      alertContainer.innerHTML = '';

      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      formData.append('document_type', docTypeSelect.value);

      try {
        const response = await fetch('/api/v1/documents/process', {
          method: 'POST',
          body: formData,
        });

        const data = await response.json();

        if (response.ok) {
          const docName = data.document_name;
          const viewUrl = `/documents/${encodeURIComponent(docName)}/view`;
          const overallStatus = data.validation && data.validation.overall_status
            ? data.validation.overall_status.toUpperCase()
            : null;

          if (overallStatus === 'FAIL' || overallStatus === 'FAILED') {
            showAlert(
              `Document \"${escapeHtml(docName)}\" was processed, but financial validation <strong>FAILED</strong>. <a href="${viewUrl}" style="color: #fbbf24; font-weight: 600; margin-left: 0.5rem;">View Details &rarr;</a>`,
              'warning'
            );
          } else {
            showAlert(
              `Document \"${escapeHtml(docName)}\" processed successfully! <a href="${viewUrl}" style="color: #86efac; font-weight: 600; underline: underline; margin-left: 0.5rem;">View Results &rarr;</a>`,
              'success'
            );
          }

          uploadForm.reset();
          await loadDocuments();
        } else {
          let errorMsg = 'An error occurred during processing.';
          if (data && data.error && data.error.message) {
            errorMsg = `[${data.error.code || 'ERROR'}] ${data.error.message}`;
          } else if (data && data.detail) {
            errorMsg = data.detail;
          }
          showAlert(errorMsg, 'error');
        }

      } catch (err) {
        console.error('Fetch error:', err);
        showAlert(`Network error: ${err.message || 'Failed to connect to backend server.'}`, 'error');
      } finally {
        processBtn.disabled = false;
        progressContainer.style.display = 'none';
      }
    });
  }

  // Fetch all documents from relative endpoint /api/v1/documents
  async function loadDocuments() {
    try {
      const response = await fetch('/api/v1/documents');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      const docs = data.documents || [];

      renderDocumentsTable(docs);
    } catch (err) {
      console.error('Error loading documents:', err);
      documentsTbody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center; color: #fca5a5; padding: 1.5rem;">
            Failed to load documents: ${escapeHtml(err.message)}
          </td>
        </tr>
      `;
    }
  }

  // Render list of documents in table
  function renderDocumentsTable(docs) {
    if (!docs || docs.length === 0) {
      documentsTbody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">
            No documents processed yet. Upload a document above to get started.
          </td>
        </tr>
      `;
      return;
    }

    documentsTbody.innerHTML = docs.map(doc => {
      const name = doc.document_name || 'Unnamed';
      const typeDisplay = formatDocType(doc.document_type);
      
      // Determine validation status badge from doc.validation or status
      let status = 'COMPLETED';
      if (doc.validation && doc.validation.overall_status) {
        status = doc.validation.overall_status;
      } else if (doc.processing_status) {
        status = doc.processing_status;
      }

      const statusBadge = getStatusBadge(status);
      const processedAt = doc.processed_at ? new Date(doc.processed_at).toLocaleString() : 'N/A';
      const viewUrl = `/documents/${encodeURIComponent(name)}/view`;

      return `
        <tr class="clickable-row" onclick="window.location.href='${viewUrl}'">
          <td style="font-weight: 600;">${escapeHtml(name)}</td>
          <td>${escapeHtml(typeDisplay)}</td>
          <td>${statusBadge}</td>
          <td style="color: var(--text-secondary);">${escapeHtml(processedAt)}</td>
          <td style="text-align: right;" onclick="event.stopPropagation();">
            <a href="${viewUrl}" class="btn btn-secondary btn-sm">View Result</a>
          </td>
        </tr>
      `;
    }).join('');
  }

  // Helper: Format Document Type String
  function formatDocType(type) {
    if (!type) return 'Unknown';
    const map = {
      'invoice': 'Invoice',
      'balance_sheet': 'Balance Sheet',
      'profit_and_loss': 'Profit & Loss',
      'cash_flow_statement': 'Cash Flow Statement',
      'p&l': 'Profit & Loss',
      'cash_flow': 'Cash Flow Statement'
    };
    return map[type.toLowerCase()] || type;
  }

  // Helper: Get Badge HTML for status
  function getStatusBadge(status) {
    if (!status) return '<span class="badge badge-neutral">UNKNOWN</span>';
    const upper = String(status).toUpperCase();
    if (upper === 'PASS' || upper === 'SUCCESS') {
      return `<span class="badge badge-pass">PASS</span>`;
    } else if (upper === 'FAIL' || upper === 'FAILED') {
      return `<span class="badge badge-fail">FAILED</span>`;
    } else {
      return `<span class="badge badge-neutral">${escapeHtml(upper)}</span>`;
    }
  }

  // Helper: Show Alert Message
  function showAlert(message, type = 'info') {
    alertContainer.innerHTML = `
      <div class="alert alert-${type}">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;">
          ${type === 'error' ? '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>' : '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>'}
        </svg>
        <div>${message}</div>
      </div>
    `;
  }

  // Helper: Escape HTML
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
