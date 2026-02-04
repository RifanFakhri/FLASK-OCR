<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Data Comparison | PT Biro Klasifikasi Indonesia</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/comparison.css') }}">
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <h1><i class="fas fa-code-compare"></i> Data Comparison & Update</h1>
            <p>Compare OCR results with database records and update if necessary</p>
            <div class="header-actions">
                <a href="/" class="btn-back"><i class="fas fa-arrow-left"></i> Back to Upload</a>
                <div class="cert-info">
                    <span class="cert-badge" id="certCount">Loading...</span>
                    <span class="status-badge" id="syncStatus">Syncing...</span>
                </div>
            </div>
        </header>

        <!-- Comparison Results -->
        <main class="comparison-main">
            <!-- Summary Card -->
            <div class="summary-card">
                <div class="summary-item">
                    <div class="summary-icon success">
                        <i class="fas fa-check-circle"></i>
                    </div>
                    <div class="summary-text">
                        <h4 id="matchCount">0</h4>
                        <p>Matching Fields</p>
                    </div>
                </div>
                <div class="summary-item">
                    <div class="summary-icon warning">
                        <i class="fas fa-exclamation-triangle"></i>
                    </div>
                    <div class="summary-text">
                        <h4 id="diffCount">0</h4>
                        <p>Different Fields</p>
                    </div>
                </div>
                <div class="summary-item">
                    <div class="summary-icon info">
                        <i class="fas fa-database"></i>
                    </div>
                    <div class="summary-text">
                        <h4 id="totalFields">0</h4>
                        <p>Total Fields Checked</p>
                    </div>
                </div>
            </div>

            <!-- Comparison Table -->
            <div class="card">
                <h3><i class="fas fa-table"></i> Field Comparison</h3>
                <div class="table-container">
                    <table id="comparisonTable">
                        <thead>
                            <tr>
                                <th>Field</th>
                                <th>Database Value</th>
                                <th>OCR Value</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody id="comparisonBody">
                            <!-- Data will be populated by JavaScript -->
                            <tr>
                                <td colspan="5" class="loading-cell">
                                    <i class="fas fa-spinner fa-spin"></i> Loading comparison data...
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Action Buttons -->
            <div class="action-buttons">
                <button class="btn-update" id="updateAllBtn" disabled>
                    <i class="fas fa-sync-alt"></i> Update All Differences
                </button>
                <button class="btn-ignore" id="ignoreAllBtn">
                    <i class="fas fa-times"></i> Ignore All
                </button>
                <button class="btn-review" id="reviewBtn">
                    <i class="fas fa-eye"></i> Review Selected
                </button>
            </div>

            <!-- Selected Items Summary -->
            <div class="selected-summary" id="selectedSummary" style="display: none;">
                <h4><i class="fas fa-list-check"></i> Selected for Update</h4>
                <div class="selected-list" id="selectedList">
                    <!-- Selected items will appear here -->
                </div>
                <div class="selected-actions">
                    <button class="btn-confirm" id="confirmUpdateBtn">
                        <i class="fas fa-check"></i> Confirm Update Selected Items
                    </button>
                    <button class="btn-clear" id="clearSelectionBtn">
                        <i class="fas fa-trash"></i> Clear Selection
                    </button>
                </div>
            </div>
        </main>

        <!-- Footer -->
        <footer class="footer">
            <p>© <span id="currentYear"></span> <span class="footer-logo">PT Biro Klasifikasi Indonesia</span> | Data Comparison System</p>
            <p class="footer-info"><i class="fas fa-info-circle"></i> Last Sync: <span id="lastSync">Just now</span></p>
        </footer>
    </div>

    <!-- Confirmation Modal -->
    <div class="modal" id="confirmationModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3><i class="fas fa-exclamation-triangle"></i> Confirm Update</h3>
                <button class="modal-close" id="modalClose">&times;</button>
            </div>
            <div class="modal-body">
                <p id="modalMessage">Are you sure you want to update the selected fields?</p>
                <div class="modal-details" id="modalDetails">
                    <!-- Update details will appear here -->
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-cancel" id="cancelBtn">Cancel</button>
                <button class="btn-proceed" id="proceedBtn">Proceed with Update</button>
            </div>
        </div>
    </div>

    <script src="{{ url_for('static', filename='js/comparison.js') }}"></script>
</body>
</html>