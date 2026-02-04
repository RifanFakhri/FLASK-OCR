// comparison.js (FIXED - hanya data asli, tidak ada dummy)
document.addEventListener('DOMContentLoaded', function() {
    // Set current year
    document.getElementById('currentYear').textContent = new Date().getFullYear();
    
    // Global state
    let comparisonData = null;
    let selectedFields = new Set();
    let databaseConnected = false;
    
    // DOM Elements
    const comparisonBody = document.getElementById('comparisonBody');
    const matchCountEl = document.getElementById('matchCount');
    const diffCountEl = document.getElementById('diffCount');
    const totalFieldsEl = document.getElementById('totalFields');
    const certCountEl = document.getElementById('certCount');
    const syncStatusEl = document.getElementById('syncStatus');
    const lastSyncEl = document.getElementById('lastSync');
    const updateAllBtn = document.getElementById('updateAllBtn');
    const ignoreAllBtn = document.getElementById('ignoreAllBtn');
    const reviewBtn = document.getElementById('reviewBtn');
    const selectedSummary = document.getElementById('selectedSummary');
    const selectedList = document.getElementById('selectedList');
    const confirmUpdateBtn = document.getElementById('confirmUpdateBtn');
    const clearSelectionBtn = document.getElementById('clearSelectionBtn');
    const modal = document.getElementById('confirmationModal');
    const modalClose = document.getElementById('modalClose');
    const cancelBtn = document.getElementById('cancelBtn');
    const proceedBtn = document.getElementById('proceedBtn');
    const modalMessage = document.getElementById('modalMessage');
    const modalDetails = document.getElementById('modalDetails');
    
    // Field mapping berdasarkan pola parsing dari model.py
    const FIELD_MAPPING = {
        'jenis_sert': { label: 'Jenis Sertifikat', editable: true },
        'nosert': { label: 'Nomor Sertifikat', editable: false },
        'jenis_survey': { label: 'Jenis Survey', editable: true },
        'lokasi_survey': { label: 'Lokasi Survey', editable: true },
        'pelabuhan': { label: 'Pelabuhan', editable: true },
        'tgl_survey1': { label: 'Tanggal Survey 1', editable: true },
        'tgl_survey2': { label: 'Tanggal Survey 2', editable: true },
        'tgl_sert': { label: 'Tanggal Sertifikat', editable: true },
        'nmkpl': { label: 'Nama Kapal', editable: true },
        'noreg': { label: 'Nomor Register', editable: true },
        'tgl_berlaku': { label: 'Tanggal Berlaku', editable: true },
        'mem01': { label: 'Survey Pembaruan Klas', editable: true }
    };
    
    // Initialize
    initComparison();
    
    // Initialize comparison data
    async function initComparison() {
        try {
            // Get data from URL parameters
            const urlParams = new URLSearchParams(window.location.search);
            const sessionId = urlParams.get('session');
            
            if (!sessionId) {
                showError("Tidak ada data sertifikat untuk dibandingkan. Silakan proses PDF terlebih dahulu.");
                showEmptyState("Silakan upload dan proses PDF sertifikat terlebih dahulu.");
                return;
            }
            
            // Update sync status
            updateSyncStatus('syncing', 'Memuat data sertifikat...');
            
            // 1. Check database connection
            await checkDatabaseConnection();
            
            // 2. Fetch OCR data from session
            const ocrData = await fetchOCRData(sessionId);
            if (!ocrData) return;
            
            // 3. Fetch database data if connected
            let dbData = null;
            if (databaseConnected) {
                dbData = await fetchDatabaseData(ocrData.certificate_numbers);
            }
            
            // 4. Process and compare data
            comparisonData = processComparisonData(ocrData, dbData);
            
            if (!comparisonData || !comparisonData.fields || comparisonData.fields.length === 0) {
                showEmptyState("Tidak ada data sertifikat yang dapat dibandingkan.");
                return;
            }
            
            // 5. Render the comparison
            updateSyncStatus('success', 'Data perbandingan siap');
            renderComparisonTable();
            updateSummary();
            updateLastSync();
            
        } catch (error) {
            console.error('Error loading comparison data:', error);
            showError(`Gagal memuat data perbandingan: ${error.message}`);
            updateSyncStatus('error', 'Gagal memuat data');
            showEmptyState("Terjadi kesalahan saat memuat data perbandingan.");
        }
    }
    
    // Check database connection
    async function checkDatabaseConnection() {
        try {
            const response = await fetch('/api/check_db_connection');
            const result = await response.json();
            
            if (result.status === 'connected') {
                databaseConnected = true;
                showNotification('Koneksi database berhasil', 'success');
            } else {
                databaseConnected = false;
                showNotification('Koneksi database gagal. Hanya menampilkan data OCR.', 'warning');
            }
        } catch (error) {
            databaseConnected = false;
            showNotification('Tidak dapat terhubung ke database. Hanya menampilkan data OCR.', 'warning');
        }
    }
    
    // Fetch OCR data
    async function fetchOCRData(sessionId) {
        try {
            const response = await fetch(`/api/get_ocr_data?session=${sessionId}`);
            const data = await response.json();
            
            if (data.status === 'error') {
                throw new Error(data.message || 'Gagal mengambil data OCR');
            }
            
            if (!data.parsed_data || data.parsed_data.length === 0) {
                throw new Error('Tidak ada data sertifikat yang ditemukan');
            }

            return data;
        } catch (error) {
            // Coba dari localStorage sebagai fallback
            const storedData = localStorage.getItem('last_ocr_data');
            if (storedData) {
                showNotification('Menggunakan data dari cache', 'info');
                return JSON.parse(storedData);
            }
            throw error;
        }
    }
    
    // Fetch database data
    async function fetchDatabaseData(certificateNumbers) {
        if (!certificateNumbers || certificateNumbers.length === 0) {
            return null;
        }
        
        try {
            const response = await fetch(`/api/get_db_data?nosert=${certificateNumbers.join(',')}`);
            const data = await response.json();
            
            if (data.status === 'db_error') {
                showNotification('Gagal mengambil data dari database. Hanya menampilkan data OCR.', 'warning');
                return null;
            }
            
            return data;
        } catch (error) {
            console.warn('Failed to fetch database data:', error);
            return null;
        }
    }
    
    // Process comparison data
    function processComparisonData(ocrData, dbData) {
        const parsedCerts =
          ocrData?.metadata?.certificates?.map(c => c.extracted_fields) || [];
        
        if (parsedCerts.length === 0) {
            return null;
        }
        
        // Gunakan sertifikat pertama untuk perbandingan (bisa dikembangkan untuk multiple)
        const firstCert = parsedCerts[0];
        const certNo = firstCert.nosert || 'N/A';
        
        // Cari data database yang sesuai
        let dbCert = null;
        if (dbData && dbData.data && dbData.data.length > 0) {
            dbCert = dbData.data.find(d => d.nosert === certNo) || 
                    dbData.data[0]; // Fallback ke data pertama
        }
        
        const result = {
            certificate_no: certNo,
            certificate_count: parsedCerts.length,
            database_connected: databaseConnected,
            db_record_exists: !!dbCert,
            fields: []
        };
        
        // Process each field based on FIELD_MAPPING
        Object.keys(FIELD_MAPPING).forEach(fieldKey => {
            const fieldConfig = FIELD_MAPPING[fieldKey];
            
            // Ambil nilai dari database jika tersedia
            let dbValue = 'N/A';
            if (dbCert && dbCert[fieldKey]) {
                dbValue = dbCert[fieldKey];
            } else if (dbCert && fieldKey === 'lokasi_survey' && dbCert.pelabuhan) {
                dbValue = dbCert.pelabuhan;
            }
            
            // Ambil nilai dari OCR
            let ocrValue = 'N/A';
            if (firstCert[fieldKey]) {
                ocrValue = firstCert[fieldKey];
            } else if (fieldKey === 'lokasi_survey' && firstCert.pelabuhan) {
                ocrValue = firstCert.pelabuhan;
            }
            
            // Determine status
            let status = 'different';
            let statusMessage = 'Beda';
            
            if (!databaseConnected || !dbCert) {
                status = 'no_db';
                statusMessage = 'Tidak ada DB';
            } else if (dbValue === ocrValue || (dbValue === 'N/A' && ocrValue === 'N/A')) {
                status = 'match';
                statusMessage = 'Sama';
            } else if (!ocrValue || ocrValue === 'N/A') {
                status = 'missing_ocr';
                statusMessage = 'Tidak ada OCR';
            } else if (!dbValue || dbValue === 'N/A') {
                status = 'missing_db';
                statusMessage = 'Tidak ada DB';
            }
            
            // Format values for display
            const formattedDbValue = formatFieldValue(fieldKey, dbValue);
            const formattedOcrValue = formatFieldValue(fieldKey, ocrValue);
            
            result.fields.push({
                field: fieldKey,
                label: fieldConfig.label,
                db_value: formattedDbValue,
                ocr_value: formattedOcrValue,
                db_raw: dbValue,
                ocr_raw: ocrValue,
                status: status,
                status_message: statusMessage,
                editable: fieldConfig.editable && databaseConnected && dbCert && status !== 'match'
            });
        });
        
        return result;
    }
    
    // Format field value for display
    function formatFieldValue(fieldKey, value) {
        if (!value || value === 'N/A' || value === '-' || value === '') {
            return 'N/A';
        }
        
        // Format dates
        if (fieldKey.includes('tgl_') || fieldKey.includes('tanggal')) {
            return formatDate(value);
        }
        
        return value;
    }
    
    // Format date to readable format
    function formatDate(dateString) {
        if (!dateString || dateString === 'N/A') {
            return 'N/A';
        }
        
        try {
            // Clean date string
            let cleanDate = dateString.toString().trim();
            
            // Try parsing Indonesian date format: 01/01/2024
            const parts = cleanDate.split('/');
            if (parts.length === 3) {
                const day = parts[0].padStart(2, '0');
                const month = parts[1].padStart(2, '0');
                const year = parts[2];
                
                const date = new Date(`${year}-${month}-${day}`);
                if (!isNaN(date.getTime())) {
                    return date.toLocaleDateString('id-ID', {
                        day: '2-digit',
                        month: 'long',
                        year: 'numeric'
                    });
                }
            }
            
            // Try parsing other formats
            const date = new Date(cleanDate);
            if (!isNaN(date.getTime())) {
                return date.toLocaleDateString('id-ID', {
                    day: '2-digit',
                    month: 'long',
                    year: 'numeric'
                });
            }
            
            // Return as-is if cannot parse
            return cleanDate;
            
        } catch (e) {
            console.warn('Date formatting error:', e);
            return dateString;
        }
    }
    
    // Show empty state
    function showEmptyState(message) {
        comparisonBody.innerHTML = `
            <tr>
                <td colspan="5" class="loading-cell">
                    <i class="fas fa-exclamation-circle" style="color: #EFB10E; font-size: 2rem; margin-bottom: 1rem;"></i>
                    <h4 style="color: white; margin-bottom: 0.5rem;">${message}</h4>
                    <p style="color: #a5b1c2;">Silakan kembali ke halaman utama untuk memproses sertifikat.</p>
                    <a href="/" class="btn-back" style="margin-top: 1rem;">
                        <i class="fas fa-arrow-left"></i> Kembali ke Upload
                    </a>
                </td>
            </tr>
        `;
        
        updateSyncStatus('error', 'Tidak ada data');
        certCountEl.textContent = 'Tidak ada sertifikat';
        matchCountEl.textContent = '0';
        diffCountEl.textContent = '0';
        totalFieldsEl.textContent = '0';
        
        // Hide action buttons
        document.querySelector('.action-buttons').style.display = 'none';
    }
    
    // Render comparison table
    function renderComparisonTable() {
        if (!comparisonData || !comparisonData.fields) {
            showEmptyState("Data perbandingan tidak tersedia.");
            return;
        }
        
        // Update certificate info
        const certInfo = comparisonData.certificate_no === 'N/A' ? 
            'Sertifikat: Tidak terdeteksi' : 
            `Sertifikat: ${comparisonData.certificate_no}`;
        
        certCountEl.textContent = certInfo;
        
        let html = '';
        comparisonData.fields.forEach((field, index) => {
            const statusClass = getStatusClass(field.status);
            const statusText = field.status_message || getStatusText(field.status);
            const isEditable = field.editable;
            const isSelected = selectedFields.has(field.field);
            
            // Database value display
            let dbDisplay = formatDisplayValue(field.db_value);
            if (!comparisonData.database_connected || !comparisonData.db_record_exists) {
                dbDisplay = '<em style="color: #FF9800;">Database tidak tersedia</em>';
            }
            
            // OCR value display
            let ocrDisplay = formatDisplayValue(field.ocr_value);
            if (field.ocr_value === 'N/A') {
                ocrDisplay = '<em style="color: #a5b1c2;">(tidak terdeteksi)</em>';
            }
            
            html += `
                <tr>
                    <td class="value-cell">
                        <strong>${field.label}</strong>
                        <br><small class="field-name">${field.field}</small>
                    </td>
                    <td class="value-cell value-db">${dbDisplay}</td>
                    <td class="value-cell value-ocr">${ocrDisplay}</td>
                    <td>
                        <span class="status-badge-table ${statusClass}">${statusText}</span>
                    </td>
                    <td class="action-cell">
                        <button class="btn-select ${isEditable ? '' : 'disabled'} ${isSelected ? 'selected' : ''}"
                                data-field="${field.field}"
                                data-index="${index}"
                                ${!isEditable ? 'disabled' : ''}
                                onclick="window.toggleFieldSelection('${field.field}', ${index})">
                            ${isSelected ? 
                                '<i class="fas fa-check"></i> Dipilih' : 
                                '<i class="fas fa-plus"></i> Pilih'}
                        </button>
                    </td>
                </tr>
            `;
        });
        
        comparisonBody.innerHTML = html;
        
        // Show warning if database not connected
        if (!comparisonData.database_connected) {
            const warningRow = `
                <tr>
                    <td colspan="5" style="background: rgba(255,152,0,0.1); border-left: 4px solid #FF9800; padding: 1rem;">
                        <i class="fas fa-exclamation-triangle" style="color: #FF9800; margin-right: 8px;"></i>
                        <strong style="color: #FF9800;">Peringatan:</strong>
                        <span style="color: white;">Koneksi database tidak tersedia. Data hanya ditampilkan dari hasil OCR.</span>
                    </td>
                </tr>
            `;
            comparisonBody.insertAdjacentHTML('afterbegin', warningRow);
        }
    }
    
    // Update summary counters
    function updateSummary() {
        if (!comparisonData || !comparisonData.fields) return;
        
        const fields = comparisonData.fields;
        const matchCount = fields.filter(f => f.status === 'match').length;
        const diffCount = fields.filter(f => f.status === 'different' || 
                                           f.status === 'missing_ocr' || 
                                           f.status === 'missing_db').length;
        
        matchCountEl.textContent = matchCount;
        diffCountEl.textContent = diffCount;
        totalFieldsEl.textContent = fields.length;
        
        // Enable/disable buttons based on database connection
        const hasDatabase = comparisonData.database_connected && comparisonData.db_record_exists;
        const hasDifferences = diffCount > 0;
        
        updateAllBtn.disabled = !hasDatabase || !hasDifferences;
        reviewBtn.disabled = !hasDatabase || selectedFields.size === 0;
        confirmUpdateBtn.disabled = !hasDatabase || selectedFields.size === 0;
        
        // Update review button text
        reviewBtn.innerHTML = `<i class="fas fa-eye"></i> Review Selected (${selectedFields.size})`;
        
        // Show/hide action buttons based on database connection
        const actionButtons = document.querySelector('.action-buttons');
        if (!hasDatabase) {
            actionButtons.style.opacity = '0.5';
            actionButtons.title = 'Tombol dinonaktifkan karena koneksi database tidak tersedia';
        } else {
            actionButtons.style.opacity = '1';
            actionButtons.removeAttribute('title');
        }
    }
    
    // Toggle field selection
    window.toggleFieldSelection = function(field, index) {
        if (!comparisonData.database_connected || !comparisonData.db_record_exists) {
            showNotification('Tidak dapat memilih field karena koneksi database tidak tersedia.', 'warning');
            return;
        }
        
        if (selectedFields.has(field)) {
            selectedFields.delete(field);
        } else {
            selectedFields.add(field);
        }
        
        // Update button state
        const btn = document.querySelector(`button[data-field="${field}"]`);
        if (btn) {
            if (selectedFields.has(field)) {
                btn.classList.add('selected');
                btn.innerHTML = '<i class="fas fa-check"></i> Dipilih';
            } else {
                btn.classList.remove('selected');
                btn.innerHTML = '<i class="fas fa-plus"></i> Pilih';
            }
        }
        
        updateSelectedSummary();
        updateSummary();
    };
    
    // Update selected fields summary
    function updateSelectedSummary() {
        if (selectedFields.size === 0) {
            selectedSummary.style.display = 'none';
            return;
        }
        
        selectedSummary.style.display = 'block';
        
        let html = '';
        selectedFields.forEach(field => {
            const fieldData = comparisonData.fields.find(f => f.field === field);
            if (fieldData) {
                html += `
                    <div class="selected-item">
                        <div>
                            <strong>${fieldData.label}</strong>
                            <br>
                            <small>Database: ${formatDisplayValue(fieldData.db_value)}</small>
                            <br>
                            <small>OCR: ${formatDisplayValue(fieldData.ocr_value)}</small>
                        </div>
                        <button class="remove-btn" onclick="window.removeSelectedField('${field}')">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                `;
            }
        });
        
        selectedList.innerHTML = html;
    }
    
    // Remove field from selection
    window.removeSelectedField = function(field) {
        selectedFields.delete(field);
        updateSelectedSummary();
        updateSummary();
        
        // Update button in table
        const btn = document.querySelector(`button[data-field="${field}"]`);
        if (btn) {
            btn.classList.remove('selected');
            btn.innerHTML = '<i class="fas fa-plus"></i> Pilih';
        }
    };
    
    // Update all differences button
    updateAllBtn.addEventListener('click', function() {
        if (!comparisonData.database_connected) {
            showNotification('Tidak dapat memperbarui karena koneksi database tidak tersedia.', 'error');
            return;
        }
        
        // Select all different fields
        selectedFields.clear();
        comparisonData.fields.forEach(field => {
            if (field.editable && field.status !== 'match') {
                selectedFields.add(field.field);
            }
        });
        
        if (selectedFields.size === 0) {
            showNotification('Tidak ada field yang berbeda untuk diperbarui.', 'info');
            return;
        }
        
        renderComparisonTable();
        updateSelectedSummary();
        updateSummary();
        showConfirmationModal('all');
    });
    
    // Ignore all button
    ignoreAllBtn.addEventListener('click', function() {
        if (confirm('Apakah Anda yakin ingin mengabaikan semua perbedaan dan tetap menggunakan nilai database?')) {
            selectedFields.clear();
            renderComparisonTable();
            updateSelectedSummary();
            updateSummary();
            showNotification('Semua perbedaan diabaikan', 'info');
        }
    });
    
    // Review button
    reviewBtn.addEventListener('click', function() {
        if (selectedFields.size === 0) {
            alert('Silakan pilih setidaknya satu field untuk direview.');
            return;
        }
        showConfirmationModal('selected');
    });
    
    // Confirm update button
    confirmUpdateBtn.addEventListener('click', function() {
        if (selectedFields.size === 0) {
            alert('Tidak ada field yang dipilih untuk update.');
            return;
        }
        showConfirmationModal('selected');
    });
    
    // Clear selection button
    clearSelectionBtn.addEventListener('click', function() {
        selectedFields.clear();
        renderComparisonTable();
        updateSelectedSummary();
        updateSummary();
        showNotification('Seleksi dibersihkan', 'info');
    });
    
    // Show confirmation modal
    function showConfirmationModal(action) {
        let message = '';
        let details = '';
        
        if (action === 'all') {
            const diffCount = comparisonData.fields.filter(f => f.editable && f.status !== 'match').length;
            message = `Update semua ${diffCount} field yang berbeda?`;
            
            details = '<ul style="margin-top: 10px; padding-left: 20px; max-height: 200px; overflow-y: auto;">';
            comparisonData.fields.forEach(field => {
                if (field.editable && field.status !== 'match') {
                    details += `
                        <li style="margin-bottom: 8px; padding: 5px; background: rgba(255,255,255,0.05); border-radius: 4px;">
                            <strong>${field.label}:</strong><br>
                            <small style="color: #2196F3;">Database: ${formatDisplayValue(field.db_value)}</small><br>
                            <small style="color: #9C27B0;">OCR: ${formatDisplayValue(field.ocr_value)}</small>
                        </li>`;
                }
            });
            details += '</ul>';
        } else if (action === 'selected') {
            message = `Update ${selectedFields.size} field yang dipilih?`;
            
            details = '<ul style="margin-top: 10px; padding-left: 20px; max-height: 200px; overflow-y: auto;">';
            selectedFields.forEach(field => {
                const fieldData = comparisonData.fields.find(f => f.field === field);
                if (fieldData) {
                    details += `
                        <li style="margin-bottom: 8px; padding: 5px; background: rgba(255,255,255,0.05); border-radius: 4px;">
                            <strong>${fieldData.label}:</strong><br>
                            <small style="color: #2196F3;">Database: ${formatDisplayValue(fieldData.db_value)}</small><br>
                            <small style="color: #9C27B0;">OCR: ${formatDisplayValue(fieldData.ocr_value)}</small>
                        </li>`;
                }
            });
            details += '</ul>';
        }
        
        modalMessage.textContent = message;
        modalDetails.innerHTML = details;
        
        // Set up modal buttons
        proceedBtn.onclick = function() {
            performUpdate(action);
            modal.style.display = 'none';
        };
        
        modal.style.display = 'flex';
    }
    
    // Perform update action
    async function performUpdate(action) {
        try {
            if (!comparisonData.database_connected) {
                throw new Error('Database connection not available');
            }
            
            updateSyncStatus('syncing', 'Memperbarui database...');
            
            let fieldsToUpdate = [];
            let updateData = [];
            
            if (action === 'all') {
                fieldsToUpdate = comparisonData.fields
                    .filter(f => f.editable && f.status !== 'match')
                    .map(f => f.field);
            } else if (action === 'selected') {
                fieldsToUpdate = Array.from(selectedFields);
            }
            
            // Prepare update data
            fieldsToUpdate.forEach(field => {
                const fieldData = comparisonData.fields.find(f => f.field === field);
                if (fieldData) {
                    updateData.push({
                        field: field,
                        db_value: fieldData.db_raw,
                        ocr_value: fieldData.ocr_raw,
                        certificate_no: comparisonData.certificate_no
                    });
                }
            });
            
            // Send update to server
            const response = await fetch('/api/update_database', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    updates: updateData,
                    session_id: new URLSearchParams(window.location.search).get('session')
                })
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                // Update local state
                fieldsToUpdate.forEach(field => {
                    const fieldIndex = comparisonData.fields.findIndex(f => f.field === field);
                    if (fieldIndex !== -1) {
                        comparisonData.fields[fieldIndex].db_value = comparisonData.fields[fieldIndex].ocr_value;
                        comparisonData.fields[fieldIndex].db_raw = comparisonData.fields[fieldIndex].ocr_raw;
                        comparisonData.fields[fieldIndex].status = 'match';
                        comparisonData.fields[fieldIndex].status_message = 'Sama';
                    }
                });
                
                // Clear selection
                selectedFields.clear();
                
                // Re-render
                renderComparisonTable();
                updateSummary();
                updateSelectedSummary();
                updateSyncStatus('success', 'Update berhasil');
                updateLastSync();
                
                // Show success message
                showNotification(`${result.updated_count} field berhasil diperbarui!`, 'success');
                
            } else {
                throw new Error(result.message || 'Update failed');
            }
            
        } catch (error) {
            console.error('Update failed:', error);
            updateSyncStatus('error', 'Update gagal');
            showNotification(`Update gagal: ${error.message}`, 'error');
        }
    }
    
    // Modal close handlers
    modalClose.addEventListener('click', function() {
        modal.style.display = 'none';
    });
    
    cancelBtn.addEventListener('click', function() {
        modal.style.display = 'none';
    });
    
    // Close modal when clicking outside
    window.addEventListener('click', function(event) {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Helper functions
    function getStatusClass(status) {
        switch(status) {
            case 'match': return 'status-match';
            case 'different': return 'status-different';
            case 'missing_ocr': 
            case 'missing_db': return 'status-missing';
            case 'no_db': return 'status-missing';
            default: return 'status-different';
        }
    }
    
    function getStatusText(status) {
        switch(status) {
            case 'match': return 'Sama';
            case 'different': return 'Beda';
            case 'missing_ocr': return 'Tidak ada OCR';
            case 'missing_db': return 'Tidak ada DB';
            case 'no_db': return 'DB Tidak Tersedia';
            default: return 'Unknown';
        }
    }
    
    function formatDisplayValue(value) {
        if (!value || value === 'N/A' || value === '-' || value === '') {
            return '<em style="color: #a5b1c2;">(tidak tersedia)</em>';
        }
        return value;
    }
    
    function updateSyncStatus(type, message) {
        const statusMap = {
            'syncing': { class: 'syncing', text: 'Menyinkronkan...' },
            'success': { class: 'success', text: 'Tersinkron' },
            'error': { class: 'error', text: 'Error' },
            'warning': { class: 'warning', text: 'Peringatan' }
        };
        
        const status = statusMap[type] || statusMap.syncing;
        syncStatusEl.textContent = message || status.text;
        
        // Update badge class
        syncStatusEl.className = 'status-badge';
        syncStatusEl.classList.add(status.class);
    }
    
    function updateLastSync() {
        const now = new Date();
        lastSyncEl.textContent = now.toLocaleTimeString('id-ID', { 
            hour: '2-digit', 
            minute: '2-digit',
            second: '2-digit'
        });
    }
    
    function showNotification(message, type) {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.innerHTML = `
            <i class="fas fa-${type === 'success' ? 'check-circle' : 
                             type === 'error' ? 'exclamation-circle' : 
                             type === 'warning' ? 'exclamation-triangle' : 'info-circle'}"></i>
            <span>${message}</span>
            <button class="notification-close">&times;</button>
        `;
        
        // Add to page
        document.body.appendChild(notification);
        
        // Add styles
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'success' ? 'rgba(76, 175, 80, 0.9)' : 
                       type === 'error' ? 'rgba(244, 67, 54, 0.9)' : 
                       type === 'warning' ? 'rgba(255, 152, 0, 0.9)' : 'rgba(33, 150, 243, 0.9)'};
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 10px;
            z-index: 1001;
            animation: slideIn 0.3s ease;
            border: 1px solid ${type === 'success' ? 'rgba(76, 175, 80, 0.3)' : 
                       type === 'error' ? 'rgba(244, 67, 54, 0.3)' : 
                       type === 'warning' ? 'rgba(255, 152, 0, 0.3)' : 'rgba(33, 150, 243, 0.3)'};
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
            max-width: 400px;
        `;
        
        // Close button
        notification.querySelector('.notification-close').onclick = function() {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        };
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => notification.remove(), 300);
            }
        }, 5000);
        
        // Add animations
        if (!document.querySelector('#notification-styles')) {
            const style = document.createElement('style');
            style.id = 'notification-styles';
            style.textContent = `
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                @keyframes slideOut {
                    from { transform: translateX(0); opacity: 1; }
                    to { transform: translateX(100%); opacity: 0; }
                }
            `;
            document.head.appendChild(style);
        }
    }
    
    function showError(message) {
        showNotification(message, 'error');
    }
    
    // Add status badge styles
    const style = document.createElement('style');
    style.textContent = `
        .status-badge.syncing {
            background: rgba(33, 150, 243, 0.2);
            color: #2196F3;
            border-color: rgba(33, 150, 243, 0.3);
        }
        .status-badge.success {
            background: rgba(76, 175, 80, 0.2);
            color: #4CAF50;
            border-color: rgba(76, 175, 80, 0.3);
        }
        .status-badge.error {
            background: rgba(244, 67, 54, 0.2);
            color: #F44336;
            border-color: rgba(244, 67, 54, 0.3);
        }
        .status-badge.warning {
            background: rgba(255, 152, 0, 0.2);
            color: #FF9800;
            border-color: rgba(255, 152, 0, 0.3);
        }
        .field-name {
            color: #a5b1c2;
            font-size: 0.8rem;
        }
        .notification {
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            font-weight: 500;
        }
        .notification-close {
            background: none;
            border: none;
            color: white;
            font-size: 1.2rem;
            cursor: pointer;
            margin-left: 10px;
            opacity: 0.8;
            transition: opacity 0.2s;
        }
        .notification-close:hover {
            opacity: 1;
        }
        .btn-back {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 0.8rem 1.5rem;
            background: rgba(255, 255, 255, 0.1);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.3s ease;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .btn-back:hover {
            background: rgba(255, 255, 255, 0.2);
            transform: translateY(-2px);
        }
    `;
    document.head.appendChild(style);
});