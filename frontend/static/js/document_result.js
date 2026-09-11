document.addEventListener('DOMContentLoaded', async () => {
  const contextEl = document.getElementById('document-context');
  const errorContainer = document.getElementById('error-container');
  const resultView = document.getElementById('result-view');

  if (!contextEl) return;

  let docName = contextEl.getAttribute('data-document-name');
  if (!docName || docName.trim() === '' || docName.includes('{{')) {
    // Fallback: parse from URL path /documents/{document_name}/view
    const pathParts = window.location.pathname.split('/');
    const viewIndex = pathParts.indexOf('view');
    if (viewIndex > 1) {
      docName = decodeURIComponent(pathParts[viewIndex - 1]);
    }
  }

  if (!docName) {
    showError('No document name specified in URL.');
    return;
  }

  try {
    const response = await fetch(`/api/v1/documents/${encodeURIComponent(docName)}`);
    if (!response.ok) {
      if (response.status === 404) {
        showError(`Document "${escapeHtml(docName)}" was not found in the database.`);
      } else {
        const errorData = await response.json().catch(() => ({}));
        const msg = (errorData.error && errorData.error.message) || errorData.detail || `Server returned HTTP ${response.status}`;
        showError(msg);
      }
      return;
    }

    const doc = await response.json();
    renderDocumentDetails(doc);

  } catch (err) {
    console.error('Fetch error:', err);
    showError(`Network error while retrieving document details: ${err.message}`);
  }

  // Render document data to DOM
  function renderDocumentDetails(doc) {
    resultView.style.display = 'block';

    // Top Overview Header
    document.getElementById('doc-title').textContent = doc.document_name || docName;
    document.getElementById('doc-subtitle').textContent = formatDocType(doc.document_type);
    
    let overallStatus = 'COMPLETED';
    if (doc.validation && doc.validation.overall_status) {
      overallStatus = doc.validation.overall_status;
    } else if (doc.processing_status) {
      overallStatus = doc.processing_status;
    }
    document.getElementById('doc-overall-badge').innerHTML = getStatusBadge(overallStatus);

    // Section 1: File Validation
    renderFileValidation(doc.file_validation);

    // Section 2: Extracted Data Fields
    renderExtractedFields(doc);

    // Section 3: Line Items / Breakdown Tables
    renderLineItems(doc);

    // Section 4: Financial Validation
    renderFinancialValidation(doc.validation);

    // Section 5: Metadata
    renderMetadata(doc);

    // Section 6: Raw JSON
    const rawJsonCode = document.getElementById('raw-json-code');
    if (rawJsonCode) {
      rawJsonCode.textContent = JSON.stringify(doc, null, 2);
    }
  }

  // Section 1: File Validation
  function renderFileValidation(fv) {
    const grid = document.getElementById('file-validation-grid');
    if (!fv) {
      grid.innerHTML = '<div class="kv-item"><div class="kv-label">Status</div><div class="kv-value">No file validation data</div></div>';
      return;
    }

    const items = [
      { label: 'File Type', value: fv.file_type || 'N/A' },
      { label: 'Supported Format', value: fv.is_supported !== undefined ? (fv.is_supported ? 'Yes' : 'No') : 'N/A' },
      { label: 'Readable Content', value: fv.is_readable !== undefined ? (fv.is_readable ? 'Yes' : 'No') : 'N/A' },
      { label: 'Page Count', value: fv.page_count !== undefined && fv.page_count !== null ? fv.page_count : 'N/A' },
      { label: 'Validation Status', value: getStatusBadge(fv.status || 'PASS') }
    ];

    grid.innerHTML = items.map(item => `
      <div class="kv-item">
        <div class="kv-label">${escapeHtml(item.label)}</div>
        <div class="kv-value">${typeof item.value === 'string' && item.value.startsWith('<span') ? item.value : escapeHtml(String(item.value))}</div>
      </div>
    `).join('');
  }

  // Section 2: Extracted Fields
  function renderExtractedFields(doc) {
    const grid = document.getElementById('extracted-fields-grid');
    
    // Extracted data may be in doc.extracted_data.extracted_data or doc.extracted_data
    let dataObj = {};
    if (doc.extracted_data) {
      if (doc.extracted_data.extracted_data && typeof doc.extracted_data.extracted_data === 'object') {
        dataObj = doc.extracted_data.extracted_data;
      } else {
        dataObj = doc.extracted_data;
      }
    }

    const entries = Object.entries(dataObj).filter(([key]) => {
      // Exclude arrays/nested objects handled elsewhere
      return !['line_items', 'statement_rows', 'asset_items', 'liability_items', 'evidence', 'document_type'].includes(key);
    });

    if (entries.length === 0) {
      grid.innerHTML = '<div class="kv-item"><div class="kv-value missing-value">No extracted key-value fields found</div></div>';
      return;
    }

    grid.innerHTML = entries.map(([key, val]) => {
      const label = formatKeyLabel(key);
      let valHtml = '';

      if (val === null || val === undefined || val === '') {
        valHtml = `<span class="missing-value">Not found</span>`;
      } else if (typeof val === 'number') {
        valHtml = val.toLocaleString();
      } else if (typeof val === 'object') {
        valHtml = escapeHtml(JSON.stringify(val));
      } else {
        valHtml = escapeHtml(String(val));
      }

      return `
        <div class="kv-item">
          <div class="kv-label">${escapeHtml(label)}</div>
          <div class="kv-value">${valHtml}</div>
        </div>
      `;
    }).join('');
  }

  // Section 3: Line Items / Breakdown Tables
  function renderLineItems(doc) {
    const container = document.getElementById('line-items-container');
    const ext = doc.extracted_data || {};
    const innerExt = ext.extracted_data || {};

    const lineItems = ext.line_items || innerExt.line_items;
    const statementRows = ext.statement_rows || innerExt.statement_rows;
    const assetItems = ext.asset_items || innerExt.asset_items;
    const liabilityItems = ext.liability_items || innerExt.liability_items;

    let html = '';

    if (lineItems && Array.isArray(lineItems) && lineItems.length > 0) {
      html += renderTable('Invoice Line Items', lineItems);
    }

    if (statementRows && Array.isArray(statementRows) && statementRows.length > 0) {
      html += renderTable('Statement Rows', statementRows);
    }

    if (assetItems && Array.isArray(assetItems) && assetItems.length > 0) {
      html += renderTable('Asset Items', assetItems);
    }

    if (liabilityItems && Array.isArray(liabilityItems) && liabilityItems.length > 0) {
      html += renderTable('Liability & Equity Items', liabilityItems);
    }

    if (!html) {
      html = '<div style="color: var(--text-muted); font-style: italic;">No line items or statement rows present in document.</div>';
    }

    container.innerHTML = html;
  }

  function renderTable(title, items) {
    if (!items || items.length === 0) return '';
    const keys = Object.keys(items[0]);

    return `
      <div style="margin-bottom: 1.5rem;">
        <h3 style="font-size: 0.95rem; color: var(--text-secondary); margin-bottom: 0.75rem; font-weight: 600;">${escapeHtml(title)} (${items.length})</h3>
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                ${keys.map(k => `<th>${escapeHtml(formatKeyLabel(k))}</th>`).join('')}
              </tr>
            </thead>
            <tbody>
              ${items.map(item => `
                <tr>
                  ${keys.map(k => {
                    const val = item[k];
                    let display = '';
                    if (val === null || val === undefined || val === '') {
                      display = '<span class="missing-value">Not found</span>';
                    } else if (typeof val === 'number') {
                      display = val.toLocaleString();
                    } else {
                      display = escapeHtml(String(val));
                    }
                    return `<td>${display}</td>`;
                  }).join('')}
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // Section 4: Financial Validation
  function renderFinancialValidation(valData) {
    const tbody = document.getElementById('validation-tbody');
    if (!valData || !valData.checks || !Array.isArray(valData.checks) || valData.checks.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
            No financial validation checks performed for this document type.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = valData.checks.map(check => {
      const isFail = check.status === 'FAIL' || check.status === 'FAILED';
      const rowClass = isFail ? 'class="row-failed"' : '';
      
      const calcVal = (check.calculated_value !== null && check.calculated_value !== undefined) 
        ? check.calculated_value.toLocaleString() 
        : '<span class="missing-value">N/A</span>';
      
      const repVal = (check.reported_value !== null && check.reported_value !== undefined) 
        ? check.reported_value.toLocaleString() 
        : '<span class="missing-value">N/A</span>';
      
      const variance = (check.variance !== null && check.variance !== undefined) 
        ? check.variance.toLocaleString() 
        : '0';

      return `
        <tr ${rowClass}>
          <td style="font-weight: 600;">${escapeHtml(check.name || 'Check')}</td>
          <td style="color: var(--text-secondary); font-family: monospace; font-size: 0.85rem;">${escapeHtml(check.formula || 'N/A')}</td>
          <td>${calcVal}</td>
          <td>${repVal}</td>
          <td>${variance}</td>
          <td>${getStatusBadge(check.status)}</td>
        </tr>
      `;
    }).join('');
  }

  // Section 5: Processing Metadata
  function renderMetadata(doc) {
    const grid = document.getElementById('metadata-grid');
    const meta = doc.processing_metadata || {};

    const timeSec = meta.processing_time_ms ? (meta.processing_time_ms / 1000).toFixed(2) + ' seconds' : 'N/A';
    const ocrBadge = meta.ocr_used ? '<span class="badge badge-neutral">YES (OCR)</span>' : '<span class="badge badge-neutral">NO (Native)</span>';
    const processedAt = doc.processed_at ? new Date(doc.processed_at).toLocaleString() : 'N/A';

    const items = [
      { label: 'Processing Time', value: timeSec },
      { label: 'OCR Engine Used', value: ocrBadge },
      { label: 'Pages Processed', value: meta.pages_processed || 'N/A' },
      { label: 'Pipeline Status', value: doc.processing_status || 'COMPLETED' },
      { label: 'Processed Timestamp', value: processedAt }
    ];

    grid.innerHTML = items.map(item => `
      <div class="kv-item">
        <div class="kv-label">${escapeHtml(item.label)}</div>
        <div class="kv-value">${typeof item.value === 'string' && item.value.startsWith('<span') ? item.value : escapeHtml(String(item.value))}</div>
      </div>
    `).join('');
  }

  // Helpers
  function showError(message) {
    errorContainer.innerHTML = `
      <div class="card" style="border-color: #ef4444; background-color: rgba(127, 29, 29, 0.2);">
        <h2 style="color: #fca5a5; font-size: 1.25rem; font-weight: 600; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem;">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          Document View Error
        </h2>
        <p style="color: #fca5a5; margin-bottom: 1rem;">${escapeHtml(message)}</p>
        <a href="/" class="btn btn-secondary btn-sm">&larr; Return to Dashboard</a>
      </div>
    `;
  }

  function formatDocType(type) {
    if (!type) return 'Unknown Document';
    const map = {
      'invoice': 'Invoice',
      'balance_sheet': 'Balance Sheet',
      'profit_and_loss': 'Profit & Loss Statement',
      'cash_flow_statement': 'Cash Flow Statement',
      'p&l': 'Profit & Loss Statement',
      'cash_flow': 'Cash Flow Statement'
    };
    return map[type.toLowerCase()] || type;
  }

  function formatKeyLabel(key) {
    if (!key) return '';
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());
  }

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
